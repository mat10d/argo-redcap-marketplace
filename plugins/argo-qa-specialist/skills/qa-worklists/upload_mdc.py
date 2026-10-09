"""Upload the RA's missing-data codes into REDCap — and nothing else.

The one write a QA round allows (decided 2026-10-09, see argo-core access-tiers.md). Every other
value an RA returns, the RA enters in REDCap themselves. This script uploads a cell only when
ALL of these hold, and refuses everything else, out loud:

  1. the cell was on the worklist (flagged), and was a confirmed gap (yellow, or blue — a field
     comment had explained the blank — but not amber);
  2. the RA's answer is a missing-data code: -666 / -777 / -888 / -999 (mdc-rules.md) —
     in date form (8888-08-08) for a date field, as the code's option for a checkbox;
  3. the field can hold that code (a choice field must list it; yes/no, calculated, file,
     datetime and @MDC-EXEMPT fields are refused);
  4. REDCap holds NOTHING in that cell right now (a checkbox: no option ticked) — re-checked
     against a fresh pull at the moment of the upload, so nothing is ever replaced;
  5. the record already exists in REDCap (an upload must never create one);
  6. nothing casts doubt on the code (reconcile_return.mdc_doubt): the field lists it (choices
     or Field Note), isn't a validated scale or a self-completed survey (--survey-forms), and
     the RA's note / field comment fits it — "-999" needs a reason, "-666" for a patient who
     died, or a note saying the value is in the paper chart, is held back as a question.
     Field comments come from field_comments.py (the log file, or logging with a key), the
     same reader reconcile_return.py and build_worklists.py use.

How a real upload is gated (like push_updates.py):
  --dry-run first      shows exactly what would be sent and what was refused; records a preview
  --upload             the real thing: needs the same data as the preview (within 24 hours),
  --expect-project     the project the key must open, by name or number,
  --snapshot-dir       where the current values of those records are saved BEFORE writing.
Sent with overwriteBehavior=normal, then read back to confirm every code landed.

No access key? --import-file PATH writes the same checked codes as a CSV for REDCap's
Data Import Tool (checkbox codes left out — that tool has dropped checkbox columns silently;
those go back to the RA).

Usage:
  python3 upload_mdc.py <original.xlsx> <returned.xlsx> --token-env CRC_TOKEN --dry-run
  python3 upload_mdc.py <original.xlsx> <returned.xlsx> --token-env CRC_TOKEN --upload \\
      --expect-project "Colorectal Cancer" --snapshot-dir qa-specialist/<study>/snapshots
  python3 upload_mdc.py <original.xlsx> <returned.xlsx> \\
      --records-csv export.csv --metadata-csv dd.csv --import-file mdc_import.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import push_updates  # noqa: E402  — the preview receipts, shared rather than copied
from reconcile_return import (  # noqa: E402
    IN_REDCAP, MDC_DATE_IMPORT, MDC_FROM_DATE, MDC_MEANINGS, add_source_args, checkbox_columns,
    choices_for, gather, validation,
)

# Field types that cannot hold a missing-data code at all (mdc-rules.md: exempt, or yesno).
NO_MDC_TYPES = ("yesno", "truefalse", "calc", "file", "descriptive", "sql", "slider")
EXEMPT_MARK = "@MDC-EXEMPT"


class MdcCell(NamedTuple):
    record: str
    field: str
    header: str
    code: str          # -666 / -777 / -888 / -999
    column: str        # the column REDCap takes it in
    value: str         # the value written there


class MdcRefusal(RuntimeError):
    """The payload broke a rule. Nothing is sent."""


def _is_blank_now(row: dict, field: str, meta: dict, columns) -> bool:
    if meta.get("field_type") == "checkbox":
        return not any(str(row.get(col, "")).strip() == "1"
                       for col in checkbox_columns(field, columns).values())
    return str(row.get(field, "") or "").strip() == ""


def field_problem(field: str, meta: dict, id_field: str) -> str:
    """Why this field can't take a missing-data code from us, or ""."""
    ftype = meta.get("field_type", "")
    if field == id_field:
        return "this is the record ID"
    if ftype in NO_MDC_TYPES:
        return f"a {ftype} field can't hold a missing-data code"
    if EXEMPT_MARK in (meta.get("field_annotation") or ""):
        return "this field is marked @MDC-EXEMPT"
    if ftype == "text" and validation(meta).startswith("datetime"):
        return "date-and-time field — the RA enters it"
    return ""


def target_for(field: str, code: str, meta: dict, columns) -> "tuple[str, str, str]":
    """(column, value, problem). The column and value REDCap takes this code in."""
    ftype = meta.get("field_type", "")
    if ftype == "checkbox":
        if code not in choices_for(meta):
            return "", "", f"this field has no {code} option"
        col = checkbox_columns(field, columns).get(code)
        if not col:
            return "", "", f"REDCap's export has no column for option {code}"
        return col, "1", ""
    if ftype in ("radio", "dropdown"):
        if code not in choices_for(meta):
            return "", "", f"{code} is not one of this field's choices"
        return field, code, ""
    if ftype in ("text", "notes"):
        if validation(meta).startswith("date"):
            return field, MDC_DATE_IMPORT[code], ""
        lo = (meta.get("text_validation_min") or "").strip()
        if lo and validation(meta).startswith(("integer", "number")):
            try:
                if float(code) < float(lo):
                    return "", "", f"REDCap would reject {code} (minimum is {lo})"
            except ValueError:
                pass
        return field, code, ""
    return "", "", f"a {ftype or 'unknown'} field can't hold a missing-data code"


def plan(rec, rows: list, columns: list, metadata: list) -> "tuple[list, list, int]":
    """(cells to upload, [(Check, reason)] refused, already-in-REDCap count)."""
    meta_by = {m["field_name"]: m for m in metadata}
    by_id = {str(r.get(rec.id_field, "")).strip(): r for r in rows}
    cells, refused, already = [], [], 0
    for c in rec.checks:
        if c.from_note:
            continue                                   # the RA returned no value here
        if c.status == IN_REDCAP:
            already += 1
            continue
        if not c.mdc:
            refused.append((c, "not a missing-data code — the RA enters it in REDCap"))
            continue
        doubt = dict(((h.record, h.field), why) for h, why in rec.held_back).get((c.record, c.field))
        if doubt:
            refused.append((c, f"held back: {doubt}"))
            continue
        if c.kind == "amber":
            refused.append((c, "amber cell — first confirm the field applies; the RA enters it"))
            continue
        if not c.field or c.field not in meta_by:
            refused.append((c, "couldn't match the column to a REDCap field"))
            continue
        if (c.record, c.field) not in rec.flagged_fields:
            refused.append((c, "not on the worklist"))
            continue
        row = by_id.get(c.record)
        if row is None:
            refused.append((c, "record isn't in REDCap — an upload must never create one"))
            continue
        meta = meta_by[c.field]
        why = field_problem(c.field, meta, rec.id_field)
        if why:
            refused.append((c, why))
            continue
        if not _is_blank_now(row, c.field, meta, columns):
            refused.append((c, f"REDCap already holds {c.redcap_now!r} — the RA decides"))
            continue
        col, value, why = target_for(c.field, c.mdc, meta, columns)
        if why:
            refused.append((c, why))
            continue
        cells.append(MdcCell(c.record, c.field, c.header, c.mdc, col, value))
    return cells, refused, already


def payload_csv(cells: list, id_field: str) -> str:
    """One row per record; only the targeted columns filled. Blank = leave alone (normal)."""
    cols, rows = [id_field], {}
    for c in cells:
        if c.column not in cols:
            cols.append(c.column)
        rows.setdefault(c.record, {id_field: c.record})[c.column] = c.value
    if not rows:
        return ""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for rid in sorted(rows):
        w.writerow({k: rows[rid].get(k, "") for k in cols})
    return buf.getvalue()


def check_payload(text: str, rec, rows: list, columns: list, metadata: list) -> None:
    """The last gate, run on the exact CSV about to be sent. Independent of plan().

    Every non-blank cell must be a missing-data code, for a field on this record's worklist that
    can hold it, landing in a cell REDCap holds nothing in, on a record that already exists.
    """
    meta_by = {m["field_name"]: m for m in metadata}
    by_id = {str(r.get(rec.id_field, "")).strip(): r for r in rows}
    problems = []
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or reader.fieldnames[0] != rec.id_field:
        raise MdcRefusal(f"the first column must be the record ID ({rec.id_field})")
    for r in reader:
        rid = (r.get(rec.id_field) or "").strip()
        row = by_id.get(rid)
        if row is None:
            problems.append(f"{rid}: record isn't in REDCap")
            continue
        for col, value in r.items():
            if col == rec.id_field or not (value or "").strip():
                continue
            field = col.split("___")[0] if col not in meta_by else col
            meta = meta_by.get(field)
            where = f"{rid} {col}={value!r}"
            if meta is None:
                problems.append(f"{where}: no such field"); continue
            if (rid, field) not in rec.flagged_fields:
                problems.append(f"{where}: not on the worklist"); continue
            why = field_problem(field, meta, rec.id_field)
            if why:
                problems.append(f"{where}: {why}"); continue
            if meta.get("field_type") == "checkbox":
                code = next((k for k, v in checkbox_columns(field, columns).items() if v == col), "")
                ok = value == "1" and code in MDC_MEANINGS and code in choices_for(meta)
            elif meta.get("field_type") in ("radio", "dropdown"):
                ok = value in MDC_MEANINGS and value in choices_for(meta)
            elif validation(meta).startswith("date"):
                ok = value in MDC_FROM_DATE
            elif meta.get("field_type") in ("text", "notes"):
                ok = value in MDC_MEANINGS
            else:
                ok = False
            if not ok:
                problems.append(f"{where}: not a missing-data code for this field"); continue
            if not _is_blank_now(row, field, meta, columns):
                problems.append(f"{where}: REDCap already holds a value here")
    if problems:
        raise MdcRefusal("Refusing to upload anything:\n  " + "\n  ".join(problems))


def _print_plan(cells, refused, already) -> None:
    print(f"Missing-data codes to upload: {len(cells)}   Refused: {len(refused)}   "
          f"Already in REDCap: {already}")
    if cells:
        print("\nWill upload (each cell is blank in REDCap now):")
        for c in cells:
            print(f"  {c.record}  {c.header}: {c.code} ({MDC_MEANINGS[c.code]})  → {c.column}={c.value}")
    if refused:
        print("\nNot uploaded — these stay with the RA:")
        for c, why in refused:
            print(f"  {c.record}  {c.header}: {c.ra_wrote!r} — {why}")


def _fingerprint(text: str, token_env: str) -> str:
    return push_updates._fingerprint("mdc-only\n" + text, token_env)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_source_args(ap)
    ap.add_argument("--dry-run", action="store_true", help="Show what would be sent; send nothing")
    ap.add_argument("--upload", action="store_true", help="Send it (after a --dry-run)")
    ap.add_argument("--expect-project", metavar="NAME_OR_PID",
                    help="The project the access key must open. Required with --upload.")
    ap.add_argument("--snapshot-dir", help="Folder for the before-values. Required with --upload.")
    ap.add_argument("--import-file", help="No key: write the codes as a CSV for the Data Import Tool")
    args = ap.parse_args(argv)

    if args.upload and not args.token_env:
        sys.exit("Uploading directly needs the study's access key (--token-env). Without one,\n"
                 "use --import-file to get a file for REDCap's Data Import Tool.")
    if args.import_file and args.token_env:
        sys.exit("--import-file is the no-key path. With a key, use --dry-run, then --upload.")
    if not (args.dry_run or args.upload or args.import_file):
        sys.exit("Say what to do: --dry-run (preview), --upload (send), or --import-file PATH.")

    rec, client, rows, columns, metadata = gather(args)
    cells, refused, already = plan(rec, rows, columns, metadata)

    if args.import_file:
        boxes = [c for c in cells if c.column != c.field]
        cells = [c for c in cells if c.column == c.field]
        _print_plan(cells, refused, already)
        for c in boxes:
            print(f"  {c.record}  {c.header}: {c.code} on a checkbox — left out of the file; "
                  "the RA ticks it in REDCap")
        text = payload_csv(cells, rec.id_field)
        if not text:
            print("\nNothing to put in a file.")
            return 0
        check_payload(text, rec, rows, columns, metadata)
        Path(args.import_file).expanduser().write_text(text)
        print(f"\nWrote {args.import_file}. Upload it in REDCap: Data Import Tool → choose the file →\n"
              "date format YYYY-MM-DD → 'Allow blank values to overwrite existing values?' No.\n"
              "Check REDCap's review screen shows only these codes before you confirm.")
        return 0

    _print_plan(cells, refused, already)
    text = payload_csv(cells, rec.id_field)
    if not text:
        print("\nNothing to upload.")
        return 0
    try:
        check_payload(text, rec, rows, columns, metadata)
    except MdcRefusal as e:
        sys.exit(str(e))
    fp = _fingerprint(text, args.token_env)

    if args.dry_run:
        print("\n--- exactly what would be sent ---\n" + text + "--- end ---")
        push_updates.write_receipt(fp, len(cells), [args.original, args.returned])
        print("\nNothing has been changed. If this is right, run the same command with --upload,\n"
              '--expect-project "<project name>" and --snapshot-dir <folder> instead of --dry-run.')
        return 0

    problem = push_updates.check_receipt(fp, real_flag="--upload")
    if problem:
        sys.exit("REFUSING TO UPLOAD.\n\n" + problem)
    if not args.expect_project:
        sys.exit("REFUSING TO UPLOAD — name the project: --expect-project \"<name>\" (or its number).")
    if not args.snapshot_dir:
        sys.exit("REFUSING TO UPLOAD — say where to save the before-values: --snapshot-dir <folder>.")

    from argo_redcap_client import RedcapError
    expect = str(args.expect_project).strip()
    by_pid = expect.isdigit()
    try:
        info = client.confirm_project(expect_title=None if by_pid else expect,
                                      expect_pid=expect if by_pid else None)
        print(f"Project confirmed: {info.get('project_title')!r} (project {info.get('project_id')})")
        snap = _snapshot(args.snapshot_dir, rows, columns, {c.record for c in cells}, rec.id_field)
        print(f"Saved the before-values: {snap}")
        client.warn_if_over_permissioned("uploading missing-data codes")
        result = client.import_records_csv(
            text, expect_title=None if by_pid else expect,
            expect_pid=expect if by_pid else None, overwrite="normal")
    except RedcapError as e:
        sys.exit(f"\n{e}")
    print(f"REDCap reports: {result}")

    after_rows, after_cols, _, _ = _pull(args.token_env)
    by_id = {str(r.get(rec.id_field, "")).strip(): r for r in after_rows}
    missing = [c for c in cells if str(by_id.get(c.record, {}).get(c.column, "")).strip() != c.value]
    if missing:
        print(f"\n{len(missing)} code(s) did NOT land — check these in REDCap:")
        for c in missing:
            print(f"  {c.record}  {c.header}: {c.code}")
        return 1
    print(f"\nAll {len(cells)} code(s) are in REDCap.")
    return 0


def _pull(token_env):
    from reconcile_return import load_from_key
    return load_from_key(token_env)


def _snapshot(folder, rows, columns, ids, id_field) -> Path:
    out = Path(folder).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"snapshot_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}_pre-mdc.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            if str(r.get(id_field, "")).strip() in ids:
                w.writerow(r)
    return path


if __name__ == "__main__":
    sys.exit(main())
