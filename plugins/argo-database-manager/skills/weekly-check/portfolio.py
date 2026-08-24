#!/usr/bin/env python3
"""ARGO study portfolio tracker.

Reads all 5 admin REDCaps and surfaces a weekly snapshot:
- Study Initiation Requests pending build vs. built
- Personnel Requests
- Data Linking Requests
- Data Requests
- Support Tickets

Saves a JSON snapshot per run so weekly diffs are possible.

Usage (it finds your ARGO settings file by itself — there is nothing to load first):
    python3 portfolio.py              # render dashboard, save snapshot
    python3 portfolio.py --diff       # also show diff vs previous snapshot
"""
import csv
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Filled in by main(), from the settings file this script loads itself. NOT read at import:
# reading it here meant the weekly check only worked for someone who had already sourced their
# settings file by hand, which is the one thing every other ARGO script does for you.
REDCAP_URL = None


def state_dir() -> Path:
    """Where snapshots are saved. Resolved when needed, not at import.

    The weekly check belongs to the database manager, so snapshots land in
    `database-manager/weekly-check/` inside the ARGO folder. `ARGO_PM_ROOT` names that folder
    (the variable keeps its old name so nobody's existing settings file breaks; setup writes
    the database-manager path into it). An explicit value is always honoured as-is.

    Nothing is required just to *import* this file or to run --check — that way a broken or
    unconfigured setup can still be diagnosed. Falls back to a sensible location so the tool
    works out of the box in any environment, and says where it put things.
    """
    snap_root = os.environ.get("ARGO_PM_ROOT")
    if snap_root:
        root = Path(snap_root).expanduser()
    else:
        root = Path.home() / ".argo" / "database-manager"
        print(
            f"I saved the snapshot to {root}. If your ARGO folder is somewhere else, add\n"
            "ARGO_PM_ROOT to your settings file so it lands next to the rest of your work:\n"
            "    ARGO_PM_ROOT=/path/to/your/ARGO-folder/database-manager\n",
            file=sys.stderr,
        )
    directory = root / "weekly-check"
    directory.mkdir(parents=True, exist_ok=True)
    return directory

# The admin trackers and the canonical build steps come from argo-core's argo_trackers.py, so
# this list exists in exactly one place. If argo-core isn't reachable we fall back to a local
# copy rather than failing outright — but the shared file is the source of truth.
def _load_trackers():
    # Vendored copy first (this skill's own scripts/), argo-core source tree as dev fallback.
    core = None
    _here = Path(__file__).resolve().parent
    for cand in (_here / "scripts",
                 *(par / "plugins/argo-core/skills/redcap-api/scripts" for par in _here.parents)):
        if (cand / "argo_redcap_client.py").exists():
            core = str(cand)
            break
    if core:
        sys.path.insert(0, core)
        try:
            from argo_trackers import (as_portfolio_rows, SIR_BUILD_STEPS as steps,
                                       sir_progress as progress)
            return as_portfolio_rows(), steps, progress
        except ImportError:
            pass
    print("Note: couldn't load the shared tracker list from argo-core; using a local copy. "
          "Re-install the ARGO plugins together if this persists.", file=sys.stderr)
    fallback_steps = ["project_created", "dd_uploaded", "user_rights_complete", "data_imported",
                      "review_internal", "review_pi", "study_production"]

    def fallback_progress(record: dict) -> tuple:
        not_done = {"", "no", "0"}
        done = sum(1 for s in fallback_steps
                   if str(record.get(s) or "").strip().lower() not in not_done)
        return done, len(fallback_steps)

    return ([
        ("STUDY_INITIATION_REQUEST", "Study Tracker", "study_initiation_request", "study_production", "Yes"),
        ("STUDY_PERSONELL_REQUEST",  "Study Personnel Request",  "study_personnel_request",  "completed", "Yes"),
        ("DATA_LINKING_REQUEST",     "Data Linking Request",     "data_linking_request",     "completed", "Yes"),
        ("DATA_REQUEST",             "Data Request",             "data_request",             "completed", "Yes"),
        ("SUPPORT_TICKET_REQUEST",   "Support Ticket Request",   "support_ticket",           "completed", "Yes"),
    ], fallback_steps, fallback_progress)


ADMIN_REDCAPS, SIR_BUILD_STEPS, _sir_progress_counts = _load_trackers()


def api_post(token: str, **params) -> "list | dict":
    """POST to the REDCap API and return parsed JSON."""
    data = urllib.parse.urlencode({"token": token, "format": "json", **params}).encode()
    req = urllib.request.Request(REDCAP_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def api_post_raw(token: str, **params) -> str:
    """POST to the REDCap API and return the raw response (used for CSV pull)."""
    data = urllib.parse.urlencode({"token": token, **params}).encode()
    req = urllib.request.Request(REDCAP_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def confirm_token(token: str, expected_title: str) -> dict:
    """Confirm the token points at the expected project. Returns project info."""
    info = api_post(token, content="project")
    title = info.get("project_title", "").strip()
    if expected_title.lower() not in title.lower():
        raise RuntimeError(
            f"Token title mismatch: expected '{expected_title}', got '{title}'. "
            f"Refusing to proceed — check the access keys in your ARGO settings file."
        )
    return info


def collect(csv_dir: Path) -> dict:
    """Pull records from all 5 admin REDCaps. Save per-project CSV and bucket them in the snapshot."""
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "projects": {},
    }
    for env_var, label, _form, status_field, done_val in ADMIN_REDCAPS:
        token = os.environ.get(env_var)
        if not token:
            snapshot["projects"][env_var] = {"error": "token not set"}
            continue
        try:
            info = confirm_token(token, label)
            records = api_post(token, content="record", rawOrLabel="label", exportCheckboxLabel="true")
            # Per-REDCap CSV snapshot for human review (Excel-friendly)
            csv_text = api_post_raw(token, content="record", format="csv",
                                    rawOrLabel="label", exportCheckboxLabel="true")
            (csv_dir / f"{env_var}.csv").write_text(csv_text)
        except Exception as e:
            snapshot["projects"][env_var] = {"error": str(e)}
            continue

        open_items = []
        done_items = []
        for r in records:
            rid = r.get("record_id")
            if status_field and r.get(status_field) == done_val:
                done_items.append({"record_id": rid, "summary": summarize(env_var, r)})
            else:
                open_items.append({"record_id": rid, "summary": summarize(env_var, r)})

        snapshot["projects"][env_var] = {
            "label": label,
            "pid": info.get("project_id"),
            "total": len(records),
            "open": open_items,
            "done": done_items,
        }
    return snapshot


# Build-side technical detail (hospital_number, file import fields, separate roles vs users granularity)
# is enforced by the DD validator + collapsed into user_rights_complete. Document checklist + weekly
# reports tracked granularly in study_metadata.


def sir_progress(rec: dict) -> str:
    """Render build progress as 'N/M' completed steps.

    The counting rule itself lives in argo-core's `argo_trackers.sir_progress` and is shared
    with the open-requests queue, so the same study can never read 3/7 in one view and 4/7 in
    the other. A step is done when its field holds any settled answer that isn't "no" —
    `data_imported` is a radio whose "Prospective study, not required" settles it.
    """
    done, total = _sir_progress_counts(rec)
    return f"{done}/{total}"


def summarize(env_var: str, rec: dict) -> str:
    """One-line summary of a record for the dashboard."""
    if env_var == "STUDY_INITIATION_REQUEST":
        status = rec.get("study_status") or "?"
        pid = rec.get("new_project_pid") or "no PID"
        progress = sir_progress(rec)
        short = rec.get("shortened_study_name") or rec.get("project_title", "(no title)")[:60]
        return f"[{status:14s}] PID {pid:>4} {progress:>4} — {short[:55]} — PI: {rec.get('pi_surname','?')}"
    if env_var == "STUDY_PERSONELL_REQUEST":
        return f"{rec.get('first_name','?')} {rec.get('last_name','?')} → {rec.get('institution','?')} ({rec.get('user_role','?')})"
    if env_var == "DATA_LINKING_REQUEST":
        return f"For {rec.get('request_for_name','?')} — needed by {rec.get('needed_by','?')}"
    if env_var == "DATA_REQUEST":
        return f"For {rec.get('request_for_name','?')} — {rec.get('database_name','?')} — needed by {rec.get('date_needed_by','?')}"
    if env_var == "SUPPORT_TICKET_REQUEST":
        return f"{rec.get('first_name','?')} {rec.get('surname','?')}: {(rec.get('issue_summary') or '')[:60]}"
    return str(rec)[:80]


def render(snapshot: dict, diff: "dict | None" = None) -> str:
    lines = [f"# ARGO Portfolio — {snapshot['captured_at']}\n"]
    for env_var, _, _, _, _ in ADMIN_REDCAPS:
        p = snapshot["projects"].get(env_var, {})
        if "error" in p:
            lines.append(f"## {env_var}\n  ⚠️  {p['error']}\n")
            continue
        lines.append(f"## {p['label']} (PID {p['pid']}) — {len(p['open'])} open / {len(p['done'])} done")
        if p["open"]:
            for item in p["open"]:
                marker = ""
                if diff and item["record_id"] in diff.get(env_var, {}).get("new_open", set()):
                    marker = " 🆕"
                lines.append(f"  - [{item['record_id']:>3}] {item['summary']}{marker}")
        else:
            lines.append("  (no open items)")
        if diff:
            newly_done = diff.get(env_var, {}).get("newly_done", set())
            if newly_done:
                lines.append(f"  Recently completed: {sorted(newly_done)}")
        lines.append("")
    return "\n".join(lines)


def compute_diff(curr: dict, prev: dict) -> dict:
    """Diff two snapshots: new open items, newly done items per project."""
    out = {}
    for env_var, *_ in ADMIN_REDCAPS:
        c = curr["projects"].get(env_var, {})
        p = prev["projects"].get(env_var, {})
        if "error" in c or "error" in p:
            continue
        c_open = {i["record_id"] for i in c.get("open", [])}
        p_open = {i["record_id"] for i in p.get("open", [])}
        c_done = {i["record_id"] for i in c.get("done", [])}
        p_done = {i["record_id"] for i in p.get("done", [])}
        out[env_var] = {
            "new_open": c_open - p_open - p_done,         # genuinely new submissions
            "newly_done": (c_done - p_done),              # transitioned to done this period
            "still_open": c_open & p_open,                # carryover
        }
    return out


def load_previous(state: Path) -> "dict | None":
    # Current layout: snapshot-<stamp>/summary.json
    snapshots = sorted(state.glob("snapshot-*/summary.json"))
    if not snapshots:
        # Older runs saved a single flat file, snapshot-<stamp>.json. Those can't be compared
        # against, but say so rather than silently reporting "nothing changed".
        legacy = sorted(state.glob("snapshot-*.json"))
        if legacy:
            print(
                f"Note: found {len(legacy)} snapshot(s) saved in the older format, which this\n"
                f"version can't compare against (for example {legacy[-1].name}).\n"
                "There's nothing to compare this week's numbers to yet — from the next run\n"
                "onwards, comparisons will work normally.",
                file=sys.stderr,
            )
        return None
    return json.loads(snapshots[-1].read_text())


def save(snapshot: dict, snap_dir: Path) -> Path:
    path = snap_dir / "summary.json"
    path.write_text(json.dumps(snapshot, indent=2))
    return path


def find_argo_core() -> "str | None":
    """The folder holding the shared ARGO scripts — this skill's own vendored copy."""
    here = Path(__file__).resolve().parent
    for cand in (here / "scripts",
                 *(par / "plugins/argo-core/skills/redcap-api/scripts" for par in here.parents)):
        if (cand / "argo_redcap_client.py").exists():
            return str(cand)
    return None


def load_settings() -> "Path | None":
    """Find and load the ARGO settings file, exactly the way every other ARGO script does.

    The shared client owns the search list (`load_env_file`), so the weekly check can never
    disagree with `--check` about which file is in force. Returns the file it read, or None if
    there is nothing to read — never raises, because a missing settings file is a thing to
    explain in plain words a moment later, not a crash.
    """
    core = find_argo_core()
    if core is None:
        return None
    sys.path.insert(0, core)
    try:
        from argo_redcap_client import load_env_file
    except ImportError:
        return None
    try:
        return load_env_file()
    except Exception:
        return None


def run_setup_check() -> int:
    """Check every tracker key without pulling any data. Delegates to argo-core's shared client."""
    core = find_argo_core()
    if core is None:
        print(
            "I couldn't find the shared ARGO REDCap code, which this check needs.\n"
            "\n"
            "It lives in the argo-core plugin. This usually means argo-core isn't installed\n"
            "alongside argo-database-manager. Ask whoever set up your ARGO tools to reinstall\n"
            "the plugins, or set ARGO_CORE_SCRIPTS to the folder containing\n"
            "argo_redcap_client.py."
        )
        return 1
    sys.path.insert(0, core)
    from argo_redcap_client import run_check
    return run_check()


def main():
    global REDCAP_URL

    if "--check" in sys.argv:
        sys.exit(run_setup_check())

    # Load the settings file first — before anything reads REDCAP_URL or a tracker key.
    settings = load_settings()
    REDCAP_URL = os.environ.get("REDCAP_URL")

    if not REDCAP_URL:
        where = (f"Your settings file is here:\n\n    {settings}\n"
                 if settings else
                 "Open your ARGO folder and double-click 'Add keys here' — that opens your\n"
                 "settings file in a text editor.\n")
        sys.exit(
            "This tool needs to know the web address of your REDCap system before it can check\n"
            "anything, and that address isn't set yet.\n"
            "\n"
            "It's a single line of text ending in /api/ — ask your ARGO REDCap administrator for\n"
            "it if you don't have it. It goes in your ARGO settings file, on its own line:\n"
            "\n"
            "    REDCAP_URL=https://your-redcap-site.org/api/\n"
            "\n"
            + where +
            "\nSave it, then run this again. There is nothing to load by hand — this tool reads\n"
            "the settings file itself."
        )

    want_diff = "--diff" in sys.argv

    stamp = datetime.now(timezone.utc).isoformat().replace(":", "-").split(".")[0]
    snap_dir = state_dir() / f"snapshot-{stamp}"
    snap_dir.mkdir(parents=True, exist_ok=True)

    prev = load_previous(snap_dir.parent) if want_diff else None
    if want_diff and prev is None:
        # Saying nothing here reads as "nothing changed this week", which is the opposite of
        # the truth: there is no earlier snapshot to have changed FROM.
        print("First snapshot — nothing to compare against yet; next run will show what "
              "changed.\n")
    curr = collect(snap_dir)
    diff = compute_diff(curr, prev) if prev else None

    # If every single tracker failed, this is an outage — not a quiet week. Say so at the top,
    # and exit non-zero so an automated weekly run can tell the difference.
    projects = curr.get("projects", {})
    failed = [k for k, v in projects.items() if "error" in v]
    total_failed = len(failed) == len(projects) and projects

    if total_failed:
        print("!" * 72)
        print("COULD NOT READ ANY OF THE ARGO TRACKERS — this report is empty because something")
        print("is wrong, NOT because there was no activity this week.")
        print("")
        print("Each tracker below says what went wrong. The most common causes are: the access")
        print("keys are missing from your ARGO settings file (run this with --check to see which")
        print("ones), the REDCap address changed, or REDCap is temporarily down.")
        print("!" * 72)
        print("")

    print(render(curr, diff))
    save(curr, snap_dir)
    print(f"# Snapshot dir: {snap_dir}", file=sys.stderr)
    print(f"# Per-project CSVs + summary.json", file=sys.stderr)

    if total_failed:
        print(
            "\nStopping with an error because none of the trackers could be read. "
            "Nothing above should be treated as a real portfolio update.",
            file=sys.stderr,
        )
        sys.exit(1)
    if failed:
        print(
            f"\nNote: {len(failed)} of {len(projects)} trackers could not be read "
            f"({', '.join(failed)}). Everything else in this report is accurate.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
