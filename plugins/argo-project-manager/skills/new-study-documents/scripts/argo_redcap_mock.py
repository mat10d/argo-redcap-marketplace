#!/usr/bin/env python3
"""A file-backed stand-in for the REDCap API, so the toolkit can be exercised with no network.

Every ARGO script reaches REDCap through `urllib.request.urlopen` — the shared client and the
four scripts that still build their own requests alike. This module replaces that one function
with one that answers from a folder of fixtures, so a whole Cowork session can run the real
skills, the real scripts and the real settings file against synthetic REDCap projects, and
**nothing it does can reach a real server**.

Two conditions, BOTH required, or this module is inert and the real network is used:

  1. the loaded ARGO settings file says   ARGO_REDCAP_MOCK=<folder>   (relative to that file)
  2. REDCAP_URL's host ends in `.invalid`  — e.g. https://mock.argo.invalid/api/

The second is the safety property. `.invalid` is reserved by RFC 2606 and can never resolve,
so a test workspace whose settings file names that address cannot push to REDCap even if this
module never loads. The mock flag with a REAL address is refused outright, loudly — that
configuration is never legitimate.

The mock folder:

    keys.json                 {"<32-hex token>": "<project folder name>", ...}
    config.json               {"apply_writes": false, "simulate_egress_block": false}
    projects/<name>/
        project.json          what content=project returns (project_id, project_title, ...)
        metadata.json         the data dictionary, as content=metadata returns it (list of rows)
        records.json          flat records (list of dicts); label<->code mapping uses metadata
        files/                optional File Repository tree — folders and files, as on disk
    CALLS.jsonl               every request, appended: which project, what content/action
    WRITES.jsonl              every write, appended with its full payload — and NOT applied
                              unless config.apply_writes is true

Grading a test round reads CALLS.jsonl ("the export never touched the Study Tracker") and
WRITES.jsonl ("nothing was written", or "exactly one build step was marked").
"""
from __future__ import annotations

import csv
import email.message
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MOCK_FLAG = "ARGO_REDCAP_MOCK"
REQUIRED_HOST_SUFFIX = ".invalid"

_installed: "MockRedcap | None" = None
_real_urlopen = urllib.request.urlopen


class MockConfigError(RuntimeError):
    """The mock was asked for in a configuration it must refuse."""


# ---------------------------------------------------------------------------- helpers

def _parse_choices(spec: str) -> "list[tuple[str, str]]":
    """'1, Yes | 0, No' -> [('1','Yes'), ('0','No')]. Tolerates missing commas."""
    out = []
    for part in (spec or "").split("|"):
        part = part.strip()
        if not part:
            continue
        code, _, label = part.partition(",")
        out.append((code.strip(), label.strip() if _ else code.strip()))
    return out


def _fake_response(body: bytes, headers: "dict | None" = None):
    """Enough of an HTTPResponse for `with urlopen(...) as resp: resp.read()`."""
    class _Resp(io.BytesIO):
        status = 200

        def __init__(self, data):
            super().__init__(data)
            self.headers = email.message.Message()
            for k, v in (headers or {}).items():
                self.headers[k] = v

        def getcode(self):
            return 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()
            return False

    return _Resp(body)


def _http_error(url: str, code: int, body: str, headers: "dict | None" = None):
    hdrs = email.message.Message()
    for k, v in (headers or {}).items():
        hdrs[k] = v
    return urllib.error.HTTPError(url, code, body, hdrs, io.BytesIO(body.encode()))


def _params_from_body(data: bytes) -> dict:
    """The POST body as a flat dict; REDCap's `records[0]=..&records[1]=..` lists collapse to
    a comma-joined `records` (and likewise fields/forms), which is the other spelling REDCap
    accepts, so the mock only ever handles one shape."""
    raw = urllib.parse.parse_qs(data.decode("utf-8", errors="replace"), keep_blank_values=True)
    flat: dict = {}
    lists: dict = {}
    for key, values in raw.items():
        m = re.fullmatch(r"(\w+)\[\d+\]", key)
        if m:
            lists.setdefault(m.group(1), []).extend(values)
        else:
            flat[key] = values[-1]
    for name, values in lists.items():
        joined = ",".join(v for v in values if v)
        flat[name] = ",".join(x for x in (flat.get(name, ""), joined) if x)
    return flat


def _split_list(value: str) -> list:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def fake_token(name: str) -> str:
    """A deterministic 32-hex token for a mock project — looks like a REDCap token, opens
    nothing anywhere real."""
    return hashlib.sha256(f"argo-mock:{name}".encode()).hexdigest()[:32].upper()


# ---------------------------------------------------------------------------- the mock

class MockRedcap:
    def __init__(self, folder: Path, url: str):
        self.folder = Path(folder)
        self.url = url
        self.keys = json.loads((self.folder / "keys.json").read_text())
        cfg = self.folder / "config.json"
        self.config = json.loads(cfg.read_text()) if cfg.exists() else {}
        self._file_index: "dict[str, dict]" = {}

    # -- storage ------------------------------------------------------------------

    def _project_dir(self, token: str) -> "Path | None":
        name = self.keys.get(token)
        return (self.folder / "projects" / name) if name else None

    def _load(self, pdir: Path, which: str):
        path = pdir / f"{which}.json"
        return json.loads(path.read_text()) if path.exists() else ([] if which != "project" else {})

    def _log(self, name: str, entry: dict) -> None:
        entry = {"ts": round(time.time(), 3), **entry}
        with open(self.folder / name, "a") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # -- File Repository ------------------------------------------------------------

    def _index_files(self, pdir: Path) -> dict:
        """Deterministic ids for every folder and file under files/: id -> {path, is_dir}."""
        key = str(pdir)
        if key in self._file_index:
            return self._file_index[key]
        root = pdir / "files"
        index: dict = {"0": {"path": root, "is_dir": True}}
        n = 0
        if root.is_dir():
            for p in sorted(root.rglob("*")):
                n += 1
                index[str(n)] = {"path": p, "is_dir": p.is_dir()}
        self._file_index[key] = index
        return index

    def _repo_list(self, pdir: Path, folder_id: str) -> list:
        index = self._index_files(pdir)
        parent = index.get(folder_id or "0")
        if not parent:
            return []
        by_path = {v["path"]: k for k, v in index.items()}
        items = []
        for child in sorted(parent["path"].iterdir()) if parent["path"].is_dir() else []:
            cid = by_path.get(child)
            if cid is None:
                continue
            if child.is_dir():
                items.append({"folder_id": int(cid), "name": child.name})
            else:
                items.append({"doc_id": int(cid), "name": child.name})
        return items

    def _repo_export(self, pdir: Path, doc_id: str) -> "bytes | None":
        entry = self._index_files(pdir).get(str(doc_id))
        if not entry or entry["is_dir"]:
            return None
        return entry["path"].read_bytes()

    # -- records ------------------------------------------------------------------

    @staticmethod
    def _choice_maps(metadata: list) -> dict:
        maps = {}
        for row in metadata:
            if row.get("field_type") in ("radio", "dropdown", "checkbox", "yesno", "truefalse"):
                choices = _parse_choices(row.get("select_choices_or_calculations", ""))
                if row.get("field_type") == "yesno":
                    choices = [("1", "Yes"), ("0", "No")]
                if row.get("field_type") == "truefalse":
                    choices = [("1", "True"), ("0", "False")]
                maps[row["field_name"]] = {"type": row.get("field_type"), "choices": choices}
        return maps

    def _records_for(self, pdir: Path, params: dict) -> list:
        metadata = self._load(pdir, "metadata")
        records = self._load(pdir, "records")
        id_field = metadata[0]["field_name"] if metadata else (
            next(iter(records[0])) if records else "record_id")
        stored_mode = (self._load(pdir, "project").get("_stored_mode") or "raw")
        want_label = params.get("rawOrLabel", "raw") == "label"
        checkbox_labels = params.get("exportCheckboxLabel", "false") == "true"
        maps = self._choice_maps(metadata)

        # filters
        wanted_ids = set(_split_list(params.get("records", "")))
        wanted_fields = _split_list(params.get("fields", ""))
        wanted_forms = _split_list(params.get("forms", ""))
        if wanted_forms:
            wanted_fields += [m["field_name"] for m in metadata if m.get("form_name") in wanted_forms]
            wanted_fields += [f"{f}_complete" for f in wanted_forms]
        keep_dag = params.get("exportDataAccessGroups", "false") == "true"

        out = []
        for rec in records:
            if wanted_ids and str(rec.get(id_field, "")) not in wanted_ids:
                continue
            row = {}
            for col, value in rec.items():
                if col == "redcap_data_access_group" and not keep_dag and not want_label:
                    continue
                if wanted_fields and col != id_field and col.split("___")[0] not in wanted_fields \
                        and col not in ("redcap_data_access_group",):
                    continue
                row[col] = self._render(col, value, maps, stored_mode, want_label, checkbox_labels)
            out.append(row)
        return out

    @staticmethod
    def _render(col, value, maps, stored_mode, want_label, checkbox_labels):
        value = "" if value is None else str(value)
        base, _, code = col.partition("___")
        spec = maps.get(base)
        if not spec:
            return value
        if spec["type"] == "checkbox" and code:
            checked = value in ("1", "Checked") or (value and value not in ("0", "Unchecked"))
            if want_label:
                if checkbox_labels:
                    return dict(spec["choices"]).get(code, code) if checked else ""
                return "Checked" if checked else "Unchecked"
            return "1" if checked else "0"
        code_to_label = dict(spec["choices"])
        label_to_code = {v: k for k, v in spec["choices"]}
        if want_label:
            return code_to_label.get(value, value)
        return label_to_code.get(value, value)

    @staticmethod
    def _to_csv(rows: list, metadata: list, id_field: str) -> str:
        if not rows:
            return ""
        order = [id_field, "redcap_data_access_group"]
        seen = set(order)
        for m in metadata:
            for r in rows:
                for col in r:
                    if col not in seen and col.split("___")[0] == m["field_name"]:
                        order.append(col); seen.add(col)
        for r in rows:
            for col in r:
                if col not in seen:
                    order.append(col); seen.add(col)
        present = [c for c in order if any(c in r for r in rows)]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=present, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in present})
        return buf.getvalue()

    @staticmethod
    def _metadata_csv(metadata: list) -> str:
        cols = ["field_name", "form_name", "section_header", "field_type", "field_label",
                "select_choices_or_calculations", "field_note",
                "text_validation_type_or_show_slider_number", "text_validation_min",
                "text_validation_max", "identifier", "branching_logic", "required_field",
                "custom_alignment", "question_number", "matrix_group_name", "matrix_ranking",
                "field_annotation"]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in metadata:
            w.writerow({c: row.get(c, "") for c in cols})
        return buf.getvalue()

    # -- writes -------------------------------------------------------------------

    def _apply_records(self, pdir: Path, payload: list, overwrite: str) -> None:
        metadata = self._load(pdir, "metadata")
        records = self._load(pdir, "records")
        id_field = metadata[0]["field_name"] if metadata else "record_id"
        by_id = {str(r.get(id_field)): r for r in records}
        for new in payload:
            rid = str(new.get(id_field, ""))
            cur = by_id.get(rid)
            if cur is None:
                records.append(dict(new)); by_id[rid] = records[-1]
                continue
            for k, v in new.items():
                if overwrite == "overwrite" or (v not in ("", None)):
                    cur[k] = v
        (pdir / "records.json").write_text(json.dumps(records, indent=1, ensure_ascii=False))

    # -- dispatch -----------------------------------------------------------------

    def handle(self, url: str, data: bytes):
        params = _params_from_body(data)
        token = params.get("token", "")
        content = params.get("content", "")
        action = params.get("action", "")
        fmt = params.get("format", "json")
        pdir = self._project_dir(token)
        pname = pdir.name if pdir else None
        self._log("CALLS.jsonl", {"project": pname, "token_tail": token[-4:], "content": content,
                                  "action": action, "format": fmt,
                                  "params": {k: v for k, v in params.items()
                                             if k not in ("token", "data")},
                                  "is_write": "data" in params or action == "import"})

        if self.config.get("simulate_egress_block"):
            raise _http_error(url, 403, "blocked", {"X-Proxy-Error": "blocked-by-allowlist"})
        if pdir is None:
            raise _http_error(url, 403, '{"error":"You do not have permissions to use the API"}')

        is_write = "data" in params or action == "import"
        if is_write:
            payload_text = params.get("data", "")
            parsed = None
            n = 0
            if content == "record":
                if fmt == "csv":
                    parsed = list(csv.DictReader(io.StringIO(payload_text)))
                else:
                    try:
                        parsed = json.loads(payload_text)
                    except json.JSONDecodeError:
                        parsed = []
                n = len(parsed) if isinstance(parsed, list) else 0
            elif content == "metadata":
                parsed = list(csv.DictReader(io.StringIO(payload_text))) if fmt == "csv" else payload_text
                n = len(parsed) if isinstance(parsed, list) else 0
            self._log("WRITES.jsonl", {"project": pname, "token_tail": token[-4:],
                                       "content": content, "action": action, "format": fmt,
                                       "overwriteBehavior": params.get("overwriteBehavior"),
                                       "count": n, "data": parsed if parsed is not None else payload_text,
                                       "applied": bool(self.config.get("apply_writes"))})
            if self.config.get("apply_writes") and content == "record" and isinstance(parsed, list):
                self._apply_records(pdir, parsed, params.get("overwriteBehavior", "normal"))
            if content == "record":
                if params.get("returnContent") == "count" or fmt == "csv":
                    return _fake_response(str(n).encode())
                return _fake_response(json.dumps({"count": n}).encode())
            if content == "metadata":
                return _fake_response(json.dumps(n).encode())
            return _fake_response(b"{}")

        if content == "project":
            info = {k: v for k, v in self._load(pdir, "project").items() if not k.startswith("_")}
            info.setdefault("is_longitudinal", "0")
            info.setdefault("has_repeating_instruments_or_events", "0")
            return _fake_response(json.dumps(info).encode())
        if content == "metadata":
            metadata = self._load(pdir, "metadata")
            forms = _split_list(params.get("forms", ""))
            if forms:
                metadata = [m for m in metadata if m.get("form_name") in forms]
            body = self._metadata_csv(metadata) if fmt == "csv" else json.dumps(metadata)
            return _fake_response(body.encode())
        if content == "record":
            rows = self._records_for(pdir, params)
            if fmt == "csv":
                metadata = self._load(pdir, "metadata")
                id_field = metadata[0]["field_name"] if metadata else "record_id"
                return _fake_response(self._to_csv(rows, metadata, id_field).encode())
            return _fake_response(json.dumps(rows).encode())
        if content == "fileRepository":
            if action == "list":
                return _fake_response(json.dumps(self._repo_list(pdir, params.get("folder_id", "0"))).encode())
            if action == "export":
                blob = self._repo_export(pdir, params.get("doc_id", ""))
                if blob is None:
                    raise _http_error(url, 400, '{"error":"no such document"}')
                return _fake_response(blob)
        if content == "user":
            users = self._load(pdir, "project").get("_users")
            if users is None:
                raise _http_error(url, 403, '{"error":"You do not have User Rights privileges"}')
            return _fake_response(json.dumps(users).encode())
        raise _http_error(url, 400, json.dumps({"error": f"mock: unsupported content={content!r} action={action!r}"}))


def _mock_urlopen(req, data=None, timeout=None, *args, **kwargs):
    url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
    body = req.data if isinstance(req, urllib.request.Request) else data
    host = urllib.parse.urlparse(url).netloc
    assert _installed is not None
    if url.rstrip("/") == _installed.url.rstrip("/") or host.endswith(REQUIRED_HOST_SUFFIX):
        return _installed.handle(url, body or b"")
    raise urllib.error.URLError(
        f"ARGO mock mode: network is disabled in this session, and something tried to reach "
        f"{host!r}. Only the mock REDCap at {_installed.url} is answered.")


# ---------------------------------------------------------------------------- install

def install(settings_path: "Path | None" = None) -> "MockRedcap | None":
    """Route every REDCap request in this process to the mock folder. Idempotent.

    Called by argo_redcap_client.load_env_file after it loads a settings file. Does nothing
    unless the flag is set. Refuses, loudly, if the flag is set but REDCAP_URL is a real host.
    """
    global _installed
    flag = os.environ.get(MOCK_FLAG, "").strip()
    if not flag:
        return None
    url = os.environ.get("REDCAP_URL", "")
    host = urllib.parse.urlparse(url).netloc
    if not host.endswith(REQUIRED_HOST_SUFFIX):
        raise MockConfigError(
            f"{MOCK_FLAG} is set, but REDCAP_URL points at a real host ({host or url!r}).\n"
            f"The mock only runs against an address ending in '{REQUIRED_HOST_SUFFIX}', for example\n"
            "    REDCAP_URL=https://mock.argo.invalid/api/\n"
            "so that a test workspace can never reach a real REDCap. Fix the settings file.")
    folder = Path(flag).expanduser()
    if not folder.is_absolute():
        base = Path(settings_path).resolve().parent if settings_path else Path.cwd()
        folder = (base / folder).resolve()
    if not (folder / "keys.json").exists():
        raise MockConfigError(f"{MOCK_FLAG}={flag!r} resolves to {folder}, which has no keys.json.")
    if _installed is not None and _installed.folder == folder:
        return _installed
    _installed = MockRedcap(folder, url)
    urllib.request.urlopen = _mock_urlopen
    print(f"  (ARGO mock REDCap active: {folder.name}/ — no real REDCap is reachable)",
          file=sys.stderr)
    return _installed


def uninstall() -> None:
    global _installed
    _installed = None
    urllib.request.urlopen = _real_urlopen


def is_active() -> bool:
    return _installed is not None
