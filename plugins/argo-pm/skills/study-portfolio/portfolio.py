#!/usr/bin/env python3
"""ARGO study portfolio tracker.

Reads all 5 admin REDCaps and surfaces a weekly snapshot:
- Study Initiation Requests pending build vs. built
- Personnel Requests
- Data Linking Requests
- Data Requests
- Support Tickets

Saves a JSON snapshot per run so weekly diffs are possible.

Usage:
    set -a; source ~/.argo/.env; set +a
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

REDCAP_URL = os.environ.get("REDCAP_URL")


def state_dir() -> Path:
    """Where snapshots are saved. Resolved when needed, not at import.

    Nothing is required just to *import* this file or to run --check — that way a broken or
    unconfigured setup can still be diagnosed. Falls back to a sensible location so the tool
    works out of the box in any environment, and says where it put things.
    """
    pm_root = os.environ.get("ARGO_PM_ROOT")
    if pm_root:
        root = Path(pm_root).expanduser()
    else:
        root = Path.home() / ".argo" / "pm"
        print(
            f"Note: saving snapshots to {root} because ARGO_PM_ROOT isn't set.\n"
            "If you keep your ARGO project folder somewhere specific, add a line like\n"
            "    ARGO_PM_ROOT=/path/to/ARGO/REDCap/PM\n"
            "to ~/.argo/.env so snapshots land next to the rest of your work.",
            file=sys.stderr,
        )
    directory = root / "portfolio-snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    return directory

# The admin trackers and the canonical build steps come from argo-core's argo_trackers.py, so
# this list exists in exactly one place. If argo-core isn't reachable we fall back to a local
# copy rather than failing outright — but the shared file is the source of truth.
def _load_trackers():
    # Self-contained locator: find_argo_core() is defined further down this file, and this runs
    # at import time. Searches by marker file, never by directory name (see access-tiers.md).
    core = None
    marker = "argo_redcap_client.py"
    override = os.environ.get("ARGO_CORE_SCRIPTS")
    if override and (Path(override).expanduser() / marker).exists():
        core = str(Path(override).expanduser())
    if core is None:
        for root in ("/mnt/.remote-plugins", "/mnt/skills", "~/.claude/plugins", "~/.claude/plugins/cache"):
            base = Path(root).expanduser()
            if base.is_dir():
                hits = sorted(base.glob(f"**/{marker}"))
                if hits:
                    core = str(hits[-1].parent); break
    if core is None:
        for parent in Path(__file__).resolve().parents:
            for cand in (parent / "plugins" / "argo-core" / "scripts",
                         parent / "argo-core" / "scripts"):
                if (cand / marker).exists():
                    core = str(cand); break
            if core:
                break
    if core:
        sys.path.insert(0, core)
        try:
            from argo_trackers import as_portfolio_rows, SIR_BUILD_STEPS as steps
            return as_portfolio_rows(), steps
        except ImportError:
            pass
    print("Note: couldn't load the shared tracker list from argo-core; using a local copy. "
          "Re-install the ARGO plugins together if this persists.", file=sys.stderr)
    return ([
        ("STUDY_INITIATION_REQUEST", "Study Tracker", "study_initiation_request", "study_production", "Yes"),
        ("STUDY_PERSONELL_REQUEST",  "Study Personnel Request",  "study_personnel_request",  "completed", "Yes"),
        ("DATA_LINKING_REQUEST",     "Data Linking Request",     "data_linking_request",     "completed", "Yes"),
        ("DATA_REQUEST",             "Data Request",             "data_request",             "completed", "Yes"),
        ("SUPPORT_TICKET_REQUEST",   "Support Ticket Request",   "support_ticket",           "completed", "Yes"),
    ], ["project_created", "dd_uploaded", "user_rights_complete", "data_imported",
        "review_internal", "review_pi", "study_production"])


ADMIN_REDCAPS, SIR_BUILD_STEPS = _load_trackers()


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
            f"Refusing to proceed — check ~/.argo/.env."
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
    Counts a step done if the value is yesno=Yes OR any non-empty radio label (data_imported is radio:
    either 'Yes. data was...' or 'Prospective study, not required' both count as settled)."""
    NOT_DONE = {"", "no", "0"}
    done = 0
    for s in SIR_BUILD_STEPS:
        v = (rec.get(s) or "").strip()
        if v and v.lower() not in NOT_DONE:
            done += 1
    return f"{done}/{len(SIR_BUILD_STEPS)}"


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
    """Find the folder holding argo-core's shared REDCap code.

    Searches for the FILE argo_redcap_client.py, never for a directory named "argo-core".
    Plugin directories are named differently per environment — Claude Code uses
    <marketplace>/<plugin>/<version>/, Cowork uses opaque plugin_<id>/ names with the plugin
    name recorded only inside its manifest — so a name-based search finds nothing in some.
    A relative '../argo-core' path never works either: plugins are siblings only in some layouts.
    """
    marker = "argo_redcap_client.py"
    override = os.environ.get("ARGO_CORE_SCRIPTS")
    if override and (Path(override).expanduser() / marker).exists():
        return str(Path(override).expanduser())

    for root in ("/mnt/.remote-plugins", "/mnt/skills", "~/.claude/plugins", "~/.claude/plugins/cache"):
        base = Path(root).expanduser()
        if base.is_dir():
            hits = sorted(base.glob(f"**/{marker}"))
            if hits:
                return str(hits[-1].parent)

    for parent in Path(__file__).resolve().parents:
        for candidate in (parent / "plugins" / "argo-core" / "skills" / "redcap-api" / "scripts",
                          parent / "plugins" / "argo-core" / "scripts",
                          parent / "argo-core" / "scripts"):
            if (candidate / marker).exists():
                return str(candidate)
    return None


def run_setup_check() -> int:
    """Check every tracker key without pulling any data. Delegates to argo-core's shared client."""
    core = find_argo_core()
    if core is None:
        print(
            "I couldn't find the shared ARGO REDCap code, which this check needs.\n"
            "\n"
            "It lives in the argo-core plugin. This usually means argo-core isn't installed\n"
            "alongside argo-pm. Ask whoever set up your ARGO tools to reinstall the plugins, or\n"
            "set ARGO_CORE_SCRIPTS to the folder containing argo_redcap_client.py."
        )
        return 1
    sys.path.insert(0, core)
    from argo_redcap_client import run_check
    return run_check()


def main():
    if "--check" in sys.argv:
        sys.exit(run_setup_check())

    if not REDCAP_URL:
        sys.exit(
            "This tool needs to know the web address of your REDCap system before it can check\n"
            "anything, and that address isn't set on this computer yet.\n"
            "\n"
            "It's a single line of text ending in /api/ — ask your ARGO REDCap administrator for\n"
            "it if you don't have it. Add it to the file ~/.argo/.env like this:\n"
            "\n"
            "    REDCAP_URL=https://your-redcap-site.org/api/\n"
            "\n"
            "then load it into this terminal window and try again:\n"
            "\n"
            "    set -a; source ~/.argo/.env; set +a"
        )

    want_diff = "--diff" in sys.argv

    stamp = datetime.now(timezone.utc).isoformat().replace(":", "-").split(".")[0]
    snap_dir = state_dir() / f"snapshot-{stamp}"
    snap_dir.mkdir(parents=True, exist_ok=True)

    prev = load_previous(snap_dir.parent) if want_diff else None
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
        print("keys in ~/.argo/.env were never loaded into this terminal window (run")
        print("'set -a; source ~/.argo/.env; set +a' and try again), the REDCap address changed,")
        print("or REDCap is temporarily down.")
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
