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
# Operational state (portfolio snapshots) lives outside the repo, in your local
# REDCap project folder. This is machine-specific, so it must be set explicitly.
_pm_root = os.environ.get("ARGO_PM_ROOT")
if not _pm_root:
    raise SystemExit(
        "ARGO_PM_ROOT is not set. Add it to ~/.argo/.env "
        "(e.g. ARGO_PM_ROOT=/path/to/ARGO/REDCap/PM), then re-source:\n"
        "    set -a; source ~/.argo/.env; set +a"
    )
PM_ROOT = Path(_pm_root).expanduser()
STATE_DIR = PM_ROOT / "portfolio-snapshots"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Each admin REDCap: (env var name, project label, source form, status field, status "done" value).
# SIR's done-marker is `study_production` (yesno on build_tracking — final canonical step).
# The 4 other admin REDCaps share the `tracking` form's `completed` yesno field.
# Fields don't exist until the user uploads the relevant instrument ZIP — until then, every record stays bucketed as "open".
ADMIN_REDCAPS = [
    ("STUDY_INITIATION_REQUEST", "Study Tracker", "study_initiation_request", "study_production", "Yes"),
    ("STUDY_PERSONELL_REQUEST",  "Study Personnel Request",  "study_personnel_request",  "completed", "Yes"),
    ("DATA_LINKING_REQUEST",     "Data Linking Request",     "data_linking_request",     "completed", "Yes"),
    ("DATA_REQUEST",             "Data Request",             "data_request",             "completed", "Yes"),
    ("SUPPORT_TICKET_REQUEST",   "Support Ticket Request",   "support_ticket",           "completed", "Yes"),
    ("PATHPRESENTER_INITIATION", "PathPresenter Initiation", "pathpresenter_initiation", "completed", "Yes"),
]


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


SIR_BUILD_STEPS = [
    "project_created", "dd_uploaded", "user_rights_complete", "data_imported",
    "review_internal", "review_pi", "study_production",
]
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


def load_previous() -> "dict | None":
    # New layout: snapshot-<stamp>/summary.json
    snapshots = sorted(STATE_DIR.glob("snapshot-*/summary.json"))
    if not snapshots:
        return None
    return json.loads(snapshots[-1].read_text())


def save(snapshot: dict, snap_dir: Path) -> Path:
    path = snap_dir / "summary.json"
    path.write_text(json.dumps(snapshot, indent=2))
    return path


def main():
    if not REDCAP_URL:
        sys.exit("REDCAP_URL not set. Did you source ~/.argo/.env?")

    want_diff = "--diff" in sys.argv

    stamp = datetime.now(timezone.utc).isoformat().replace(":", "-").split(".")[0]
    snap_dir = STATE_DIR / f"snapshot-{stamp}"
    snap_dir.mkdir(parents=True, exist_ok=True)

    prev = load_previous() if want_diff else None
    curr = collect(snap_dir)
    diff = compute_diff(curr, prev) if prev else None

    print(render(curr, diff))
    path = save(curr, snap_dir)
    print(f"# Snapshot dir: {snap_dir}", file=sys.stderr)
    print(f"# Per-project CSVs + summary.json", file=sys.stderr)


if __name__ == "__main__":
    main()
