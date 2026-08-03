#!/usr/bin/env python3
"""The one way ARGO code talks to REDCap.

Every ARGO script imports this instead of writing its own urlopen/curl call. It handles:
  - finding your token, and explaining plainly what to do when there isn't one
  - checking REDCAP_URL actually looks like a web address before trying to use it
  - confirming a token points at the project you meant, automatically, before any write
  - retrying when REDCap is briefly unreachable
  - never printing a full token

Check your setup at any time:

    set -a; source ~/.argo/.env; set +a
    python3 argo_redcap_client.py --check

Using it from another script:

    from argo_redcap_client import RedcapClient, find_argo_core

    client = RedcapClient.from_env("STUDY_INITIATION_REQUEST")
    if client is None:
        ...  # no token configured — take the no-token path. Never error out. See [[token-optional]]
    records = client.export_records()
    client.import_records(payload, expect_title="Study Tracker")

To import this from a script in another ARGO plugin, put this at the top:

    import sys, os
    sys.path.insert(0, find_argo_core())   # or copy the _bootstrap block from any ARGO script

See [[access-tiers]] for which skills should hold a token at all.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# How many times to retry a request that failed for a reason that might be temporary,
# and how long to wait between tries (doubling each time).
MAX_RETRIES = 3
BACKOFF_SECONDS = 1.5
TIMEOUT_SECONDS = 30


class RedcapError(RuntimeError):
    """Something went wrong talking to REDCap. The message is written for a human to act on."""


class ProjectMismatch(RedcapError):
    """The token points at a different project than the one the caller intended to write to."""


# Places plugins get installed, across the environments ARGO runs in.
# Claude Code uses ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/.
# Cowork uses /mnt/.remote-plugins/plugin_<opaque-id>/ — the plugin NAME appears only inside each
# .claude-plugin/plugin.json, never in the directory name. So never glob for a directory called
# "argo-core"; always search for the file itself.
PLUGIN_ROOTS = (
    "/mnt/.remote-plugins",   # Cowork: opaque plugin_<id> dirs, read-only
    "/mnt/skills",            # chat containers: /mnt/skills/plugins/<name>/, writable
    "~/.claude/plugins",      # Claude Code
    "~/.claude/plugins/cache",
)
MARKER = "argo_redcap_client.py"


def find_argo_core() -> str:
    """Locate the folder holding this module, so scripts in other plugins can import it.

    Searches by **marker file**, not by directory name, because plugin directories are named
    differently (or opaquely) depending on where ARGO is running. Order: an explicit
    ARGO_CORE_SCRIPTS override, then this file's own location, then the known plugin roots, then
    the marketplace repo layout.
    """
    override = os.environ.get("ARGO_CORE_SCRIPTS")
    if override and (Path(override).expanduser() / MARKER).exists():
        return str(Path(override).expanduser())

    here = Path(__file__).resolve()
    if (here.parent / MARKER).exists():
        return str(here.parent)

    for root in PLUGIN_ROOTS:
        base = Path(root).expanduser()
        if not base.is_dir():
            continue
        hits = sorted(base.glob(f"**/{MARKER}"))
        if hits:
            # Prefer the highest-sorting path — for versioned layouts that's the newest version.
            return str(hits[-1].parent)

    for parent in here.parents:
        for candidate in (parent / "plugins" / "argo-core" / "skills" / "redcap-api" / "scripts",
                          parent / "plugins" / "argo-core" / "scripts",
                          parent / "argo-core" / "scripts"):
            if (candidate / MARKER).exists():
                return str(candidate)

    raise RedcapError(
        "I couldn't find the shared ARGO REDCap code that this tool needs.\n"
        "\n"
        "It's a file called argo_redcap_client.py, which comes with the argo-core plugin. This\n"
        "usually means argo-core isn't installed alongside the plugin you're running.\n"
        "\n"
        "Ask whoever set up your ARGO tools to install all the ARGO plugins together. If you know\n"
        "where the file is, you can point at it directly instead:\n"
        "\n"
        "    export ARGO_CORE_SCRIPTS=/path/to/the/folder/containing/argo_redcap_client.py"
    )


def load_env_file(explicit: str | None = None) -> "Path | None":
    """Load REDCap settings from a .env file, if one can be found and isn't already loaded.

    In a terminal you normally do this yourself with `set -a; source ~/.argo/.env; set +a`.
    In a sandboxed environment there may be no home directory to keep that file in — the settings
    then live in a folder the user has connected. Look in both kinds of place.

    Never overwrites a variable that is already set, so an inline export always wins.
    """
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    env_file = os.environ.get("ARGO_ENV_FILE")
    if env_file:
        candidates.append(Path(env_file).expanduser())
    candidates.append(Path.home() / ".argo" / ".env")
    # Connected/working folders: a credentials file sitting alongside the work.
    # (list(...)[:2] rather than .parents[:2] — slicing parents needs Python 3.10.)
    for base in [Path.cwd()] + list(Path.cwd().parents)[:2]:
        candidates += [base / ".argo" / ".env", base / "argo.env", base / ".env"]
    # Mounted folders in a sandboxed environment.
    mnt = Path("/mnt")
    if mnt.is_dir():
        for entry in sorted(mnt.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                candidates += [entry / ".argo" / ".env", entry / "argo.env", entry / ".env"]

    for path in candidates:
        try:
            if not path.is_file():
                continue
            for raw in path.read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip().removeprefix("export ").strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
            return path
        except (OSError, UnicodeDecodeError):
            continue
    return None


def _normalise_title(title: str) -> str:
    """Lowercase, drop punctuation, collapse spaces — so 'Study Tracker' == 'study  tracker'."""
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", (title or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def check_url(url: str | None) -> str:
    """Make sure REDCAP_URL is set and looks like a web address, with a message a beginner can act on."""
    if not url:
        raise RedcapError(
            "This tool needs to know the web address of your REDCap system before it can do\n"
            "anything, and that address hasn't been set on this computer yet.\n"
            "\n"
            "It's a single line of text ending in /api/ — ask your ARGO REDCap administrator for\n"
            "it if you don't have it. Once you have it, add it to the file ~/.argo/.env like this:\n"
            "\n"
            "    REDCAP_URL=https://your-redcap-site.org/api/\n"
            "\n"
            "then run this once in your terminal to load it:\n"
            "\n"
            "    set -a; source ~/.argo/.env; set +a"
        )
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise RedcapError(
            f"The REDCap web address currently set doesn't look like a web address: {url!r}\n"
            "\n"
            "It should start with https:// and usually ends with /api/, for example:\n"
            "\n"
            "    REDCAP_URL=https://your-redcap-site.org/api/\n"
            "\n"
            "Fix the REDCAP_URL line in ~/.argo/.env, then reload it with:\n"
            "\n"
            "    set -a; source ~/.argo/.env; set +a"
        )
    return url


def mask(token: str | None) -> str:
    """Show only the last 4 characters of a token. Never print the whole thing."""
    if not token:
        return "(none)"
    return f"…{token[-4:]}"


class RedcapClient:
    """A connection to one REDCap project."""

    def __init__(self, token: str, url: str | None = None, label: str | None = None):
        if not token:
            raise RedcapError("RedcapClient needs a token. Use RedcapClient.from_env() instead.")
        self.token = token
        self.url = check_url(url or os.environ.get("REDCAP_URL"))
        self.label = label or "this REDCap project"
        self._info: dict | None = None

    # ---------------------------------------------------------------- construction

    @classmethod
    def from_env(cls, env_var: str, label: str | None = None) -> "RedcapClient | None":
        """Build a client from a token in the environment, or return None if there isn't one.

        Returning None is deliberate: no ARGO skill may hard-require a token ([[token-optional]]).
        Callers should take their no-token path — produce a file the user applies in the REDCap
        UI — and say plainly that's what they did.
        """
        token = os.environ.get(env_var)
        if not token:
            # The settings may be in a file that hasn't been loaded into this session yet —
            # common where each command runs independently, or where there's no home directory
            # to keep them in. Try to find one before giving up.
            load_env_file()
            token = os.environ.get(env_var)
        if not token:
            return None
        return cls(token, label=label or env_var)

    @staticmethod
    def explain_missing_token(env_var: str, what_for: str, fallback: str | None = None) -> str:
        """The plain-language message to show when there's no token and the user should know why.

        `fallback` says what happens next. Pass one whenever the caller has no file-based
        alternative, so the message doesn't promise something that isn't there.
        """
        if fallback is None:
            fallback = (
                "You don't need one to continue: I'll prepare a file for you to upload through\n"
                "the REDCap website instead, and tell you exactly which page to upload it on."
            )
        return (
            f"No access key for {env_var} is set up on this computer, so I can't {what_for}\n"
            "automatically over the internet.\n"
            "\n"
            "An access key (REDCap calls it an API token) is a long password that lets a tool read\n"
            "or update one specific REDCap project on your behalf. Your REDCap administrator\n"
            "creates it for you — it isn't something you can generate yourself.\n"
            "\n"
            f"{fallback}"
        )

    # ---------------------------------------------------------------- transport

    def _post(self, raw: bool = False, **params) -> "list | dict | str":
        """POST to the REDCap API, retrying briefly if REDCap is temporarily unreachable."""
        payload = urllib.parse.urlencode(
            {"token": self.token, "format": "json", "returnFormat": "json", **params}
        ).encode()

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(self.url, data=payload, method="POST")
                with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                return body if raw else (json.loads(body) if body.strip() else {})
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")[:500]
                if e.code in (400, 401, 403):
                    # A permissions/credentials problem. Retrying won't help — explain it instead.
                    raise RedcapError(
                        f"REDCap refused the request for {self.label} "
                        f"(access key ending {mask(self.token)}).\n"
                        f"REDCap said: {detail.strip() or e.reason}\n"
                        "\n"
                        "This usually means the access key is wrong, has been switched off, or\n"
                        "doesn't have permission for what was asked. Ask your REDCap\n"
                        "administrator to check it."
                    ) from e
                last_error = e
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                last_error = e

            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF_SECONDS * (2**attempt))

        raise RedcapError(
            f"Couldn't reach REDCap at {self.url} after {MAX_RETRIES} tries "
            f"(while working on {self.label}).\n"
            f"Last problem: {last_error}\n"
            "\n"
            "Check that you're connected to the internet, and that the address in ~/.argo/.env is\n"
            "correct. If both look fine, REDCap itself may be down — try again in a few minutes."
        ) from last_error

    # ---------------------------------------------------------------- reads

    def project_info(self, refresh: bool = False) -> dict:
        """Basic facts about the project this token points at (title, PID, …). Cached per client."""
        if self._info is None or refresh:
            info = self._post(content="project")
            self._info = info if isinstance(info, dict) else {}
        return self._info

    def project_title(self) -> str:
        return (self.project_info().get("project_title") or "").strip()

    def project_id(self) -> str:
        return str(self.project_info().get("project_id") or "").strip()

    def export_metadata(self, **params) -> list:
        result = self._post(content="metadata", **params)
        return result if isinstance(result, list) else []

    def record_id_field(self) -> str:
        """The real name of this project's first field.

        Never assume it's called 'record_id' — ARGO projects use study_id, participant_id, mrn…
        See [[record-id-safety]].
        """
        metadata = self.export_metadata()
        if not metadata:
            raise RedcapError(
                f"{self.label} returned no field list, so I can't tell what its ID column is "
                "called. The project may be empty, or the access key may not cover it."
            )
        return metadata[0].get("field_name", "")

    def export_metadata_csv(self, **params) -> str:
        """The data dictionary as CSV text, ready to save to a file."""
        result = self._post(raw=True, content="metadata", format="csv", **params)
        return result if isinstance(result, str) else ""

    def export_records(self, **params) -> list:
        result = self._post(content="record", **params)
        return result if isinstance(result, list) else []

    def export_records_csv(self, **params) -> str:
        params.setdefault("rawOrLabel", "label")
        params.setdefault("exportCheckboxLabel", "true")
        result = self._post(raw=True, content="record", format="csv", **params)
        return result if isinstance(result, str) else ""

    # ---------------------------------------------------------------- confirmation

    # Rights that a QA write-back account has no business holding. A REDCap token carries exactly
    # the permissions of the account that made it — there's no way to scope a token down — so the
    # only place this can be checked is the account itself (see [[access-tiers]] Tier 3).
    EXCESSIVE_RIGHTS = {
        "user_rights": "add and remove other users",
        "design": "redesign forms and fields",
        "record_delete": "delete records outright",
        "data_export": "export the full dataset",
    }

    def account_rights(self) -> "dict | None":
        """This token's own user record, or None if REDCap won't tell us (older versions)."""
        try:
            users = self._post(content="user")
        except RedcapError:
            return None
        if not isinstance(users, list) or not users:
            return None
        # The API returns the calling account first when it can identify it.
        return users[0]

    def warn_if_over_permissioned(self, purpose: str = "writing data") -> list:
        """Warn plainly if this token's account can do far more than the task needs.

        Returns the list of concerning rights. This warns rather than blocks: a legitimate
        one-off migration shouldn't be stranded by it. But the Tier 3 rule stops being purely a
        sentence in a document that somebody has to remember.
        """
        rights = self.account_rights()
        if not rights:
            print(
                "  (Couldn't check what this access key is allowed to do — REDCap didn't say. "
                "Carrying on.)",
                file=sys.stderr,
            )
            return []

        # A right counts as held only when REDCap returns a truthy value for it. Absent or null
        # means "not reported", which must not be read as "granted".
        found = []
        for field, desc in self.EXCESSIVE_RIGHTS.items():
            value = rights.get(field)
            if value is None:
                continue
            if str(value).strip() not in ("", "0", "false", "False"):
                found.append((field, desc))
        if not found:
            return []

        username = rights.get("username", "(unknown)")
        print("", file=sys.stderr)
        print("  ⚠ This access key belongs to an account with broad powers.", file=sys.stderr)
        print(f"    Account: {username}", file=sys.stderr)
        print(f"    As well as {purpose}, this key can:", file=sys.stderr)
        for _field, desc in found:
            print(f"      - {desc}", file=sys.stderr)
        print(
            "\n    A key can only ever do what its owner's account can do — there's no way to\n"
            "    limit a key by itself. For routine work, ask your REDCap administrator for a key\n"
            "    tied to an account that can only edit the forms you actually need.\n"
            "    Carrying on, because this may be deliberate.",
            file=sys.stderr,
        )
        return [f for f, _ in found]

    def confirm_project(self, expect_title: str | None = None, expect_pid: str | None = None) -> dict:
        """Check this token points where the caller intended, before writing anything.

        Prefer expect_pid — a project ID is unambiguous. Titles are compared ignoring case and
        punctuation; an exact match passes silently, a partial match passes with a warning, because
        two projects with similar names could otherwise be confused for each other.
        """
        info = self.project_info()
        actual_title = (info.get("project_title") or "").strip()
        actual_pid = str(info.get("project_id") or "").strip()

        if expect_pid and str(expect_pid).strip() != actual_pid:
            raise ProjectMismatch(
                f"Stopping before making any changes.\n"
                f"  Expected project number: {expect_pid}\n"
                f"  This access key opens:   {actual_pid} ({actual_title!r})\n"
                "\n"
                "The access key in ~/.argo/.env points at a different REDCap project than the one\n"
                "this task is meant to change. Nothing has been modified."
            )

        if expect_title:
            want = _normalise_title(expect_title)
            got = _normalise_title(actual_title)
            if want == got:
                return info
            if want and want in got:
                print(
                    f"  Note: expected the project named {expect_title!r} but this one is actually "
                    f"called {actual_title!r}.\n"
                    f"  The names overlap, so I'm continuing — but if that's not the project you "
                    f"meant, stop now (Ctrl-C).",
                    file=sys.stderr,
                )
                return info
            raise ProjectMismatch(
                f"Stopping before making any changes.\n"
                f"  Expected a project named: {expect_title!r}\n"
                f"  This access key opens:    {actual_title!r} (project {actual_pid})\n"
                "\n"
                "The access key in ~/.argo/.env points at a different REDCap project than the one\n"
                "this task is meant to change. Nothing has been modified. Check the settings in\n"
                "~/.argo/.env, or ask your REDCap administrator which key belongs to which project."
            )
        return info

    # ---------------------------------------------------------------- writes

    def import_records(
        self,
        payload: list,
        expect_title: str | None = None,
        expect_pid: str | None = None,
        overwrite: str = "overwrite",
    ) -> dict:
        """Write records. Confirms the project first — always, not optionally.

        overwrite='overwrite' is the ARGO default: with 'normal', REDCap silently drops fields
        belonging to forms not present in the payload. Pass overwrite='normal' deliberately when
        you specifically want to fill only blank cells and never replace an existing value.
        """
        if not payload:
            return {"count": 0}
        self.confirm_project(expect_title=expect_title, expect_pid=expect_pid)
        result = self._post(
            content="record",
            overwriteBehavior=overwrite,
            data=json.dumps(payload),
        )
        return result if isinstance(result, dict) else {"result": result}

    def import_records_csv(
        self,
        csv_text: str,
        expect_title: str | None = None,
        expect_pid: str | None = None,
        overwrite: str = "normal",
    ) -> str:
        """Write records supplied as CSV text. Confirms the project first — always.

        Defaults to overwrite='normal' because CSV imports are typically fill-the-blanks
        corrections: with 'normal', a blank cell in the CSV leaves the existing value alone and
        can never erase data. Pass overwrite='overwrite' only when you mean to replace values.
        """
        if not csv_text.strip():
            return "0"
        self.confirm_project(expect_title=expect_title, expect_pid=expect_pid)
        result = self._post(
            raw=True,
            content="record",
            format="csv",
            type="flat",
            overwriteBehavior=overwrite,
            data=csv_text,
            returnContent="count",
        )
        return result if isinstance(result, str) else str(result)

    def import_metadata(self, csv_text: str, expect_title: str | None = None,
                        expect_pid: str | None = None) -> "dict | list":
        """Upload a data dictionary. Confirms the project first."""
        self.confirm_project(expect_title=expect_title, expect_pid=expect_pid)
        return self._post(content="metadata", format="csv", data=csv_text)


# -------------------------------------------------------------------- setup check

# The admin trackers. Single source of truth lives in argo_trackers.py, next to this file.
# The path insert matters: this module is often loaded by file path rather than imported by
# name, and without it the sibling import fails.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from argo_trackers import ADMIN_TRACKERS  # noqa: E402

TIER1_PROJECTS = [(env, title, pid) for env, title, pid, _marker in ADMIN_TRACKERS]


def run_check() -> int:
    """Print one line per configured project saying whether it works. Returns a shell exit code."""
    print("Checking your REDCap setup\n" + "=" * 60)

    found = load_env_file()
    if found:
        print(f"Read settings from: {found}")

    url = os.environ.get("REDCAP_URL")
    try:
        check_url(url)
    except RedcapError as e:
        print(f"\n{e}\n")
        return 1
    print(f"REDCap address: {url}\n")

    working = 0
    missing = 0
    broken = 0

    for env_var, expected_title, expected_pid in TIER1_PROJECTS:
        client = RedcapClient.from_env(env_var, label=expected_title)
        if client is None:
            print(f"  – {env_var}: no access key set up (skipping)")
            missing += 1
            continue
        try:
            info = client.project_info()
            title = (info.get("project_title") or "?").strip()
            pid = str(info.get("project_id", "?"))
            id_field = client.record_id_field()
            print(f"  ✓ {env_var}: {title!r} (project {pid}), ID column {id_field!r}, "
                  f"key {mask(client.token)}")
            working += 1
            if expected_pid and pid != expected_pid:
                print(f"      warning: this used to be project {expected_pid} and is now {pid} — "
                      f"the key may have been swapped to a different project")
            elif _normalise_title(expected_title) not in _normalise_title(title):
                print(f"      warning: expected a project named {expected_title!r} — "
                      f"this key may be pointing at the wrong project")
        except RedcapError as e:
            first_line = str(e).strip().splitlines()[0]
            print(f"  ✗ {env_var}: {first_line}")
            broken += 1

    # Study tokens don't belong in the same file as the admin-tracker keys. The justification for
    # keeping keys in the shared working folder — "these are only ARGO's own PM records" — stops
    # being true the moment a cohort project's key is pasted in beside them.
    tier1 = {env for env, *_ in TIER1_PROJECTS}
    strays = sorted(k for k in os.environ
                    if k.endswith("_TOKEN") and k not in tier1 and os.environ.get(k))
    if strays:
        print("\n" + "-" * 60)
        print("Note: these look like access keys for individual studies, not the admin trackers:")
        for name in strays:
            print(f"    {name}")
        print(
            "\nIf they're in the same settings file as your tracker keys, be aware that anything\n"
            "in a folder you share with Claude can be read in full — and a study key opens\n"
            "patient data, which the tracker keys don't. Supply a study key just for the task\n"
            "that needs it, or keep it in a separate folder:\n"
            "\n"
            "    python3 argo_setup.py --separate-credentials"
        )

    print("\n" + "-" * 60)
    print(f"{working} working, {missing} not set up, {broken} not working")

    if broken:
        print("\nSomething that is set up isn't working. The lines marked ✗ above say why.")
        return 1
    if working == 0:
        print(
            "\nNo REDCap access keys are set up on this computer yet.\n"
            "That's fine for tasks that work from downloaded files, but anything that reads\n"
            "REDCap directly will need one. Ask your ARGO REDCap administrator to set you up,\n"
            "then add the keys to ~/.argo/.env."
        )
        return 1
    print("\nYour setup looks good.")
    return 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(run_check())
    print(__doc__)
    print("Run with --check to test your REDCap setup.")
