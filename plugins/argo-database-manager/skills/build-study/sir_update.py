#!/usr/bin/env python3
"""Apply targeted updates to a Study Initiation Request (SIR) record.

The SIR record is the canonical handle for one study's full lifecycle:
  - study_initiation_request form (97 fields): investigator's intake
  - build_tracking form (10 fields): build progress (7 yes/no steps)
  - study_metadata form (44 fields): long-term study state

Usage (it finds your ARGO settings file by itself — there is nothing to load first):

    # Pull the full record (for use as input to the build skill)
    python3 sir_update.py <RID> --pull > intake.json

    # Backfill IRB number + expiry (YYYY-MM-DD)
    python3 sir_update.py <RID> --irb-number IPH/OAU/12/3275 --irb-expires 2027-04-16

    # Mark a build step done (one push per step, no batching). With --dd, a DD that flags an
    # identifier also sets contains_phi=1 in the same push.
    python3 sir_update.py <RID> --mark-step dd_uploaded --dd Study_DataDictionary.csv

    # The DD changed after upload: the step is not done until the new one is uploaded
    python3 sir_update.py <RID> --unmark-step dd_uploaded

    # "Close out the build": every remaining step + the build_tracking form, one push
    python3 sir_update.py <RID> --close-out

    # Push the project to production (sets study_production=1 + study_status=2 Open to accrual)
    python3 sir_update.py <RID> --close

Always confirms project_title before posting. Always shows current values + diff
before posting. Never silent.
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# The shared ARGO scripts are vendored into this skill's own scripts/ folder by release.py,
# so imports never depend on where — or whether — other plugins are installed. The parents walk
# is only for running from a source checkout before the first sync.
_here = Path(__file__).resolve().parent
for _cand in (_here / "scripts",
              *(p / "plugins/argo-core/skills/redcap-api/scripts" for p in _here.parents)):
    if (_cand / "argo_redcap_client.py").exists():
        sys.path.insert(0, str(_cand))
        break
from argo_redcap_client import load_env_file  # noqa: E402

# Filled in by main(), from the settings file this script loads itself — never read at import.
REDCAP_URL = None
SIR_TOKEN = None


def api_post(token, **params):
    data = urllib.parse.urlencode({"token": token, "format": "json", **params}).encode()
    req = urllib.request.Request(REDCAP_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def overwrite_mode(payload):
    """REDCap's import mode for this payload.

    With overwriteBehavior=normal REDCap IGNORES blank values, so `--reopen` (which blanks
    study_production) and `--set field=` reported success and changed nothing. The payload only
    ever holds the fields this run is changing, so 'overwrite' is safe whenever one of them is
    meant to become blank — it cannot touch a field the diff didn't show.
    """
    blanking = any(str(v) == "" for rec in payload for k, v in rec.items() if k != "record_id")
    return "overwrite" if blanking else "normal"


def api_post_record(token, payload):
    data = urllib.parse.urlencode({
        "token": token, "format": "json",
        "content": "record", "overwriteBehavior": overwrite_mode(payload),
        "data": json.dumps(payload),
    }).encode()
    req = urllib.request.Request(REDCAP_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def confirm(prompt):
    """Ask before writing. Works whether or not anyone is sitting at a keyboard.

    When this runs somewhere with no keyboard attached — an agent session, a scheduled job, a
    cloud runner — there is nobody to answer, so waiting would hang forever. In that case require
    --yes up front instead, which makes the approval explicit rather than assumed.
    """
    if "--yes" in sys.argv or os.environ.get("ARGO_ASSUME_YES") == "1":
        print(f"{prompt} [y/N] y   (--yes was given)")
        return True
    if not sys.stdin.isatty():
        sys.exit(
            f"{prompt}\n"
            "\n"
            "I need you to approve this before writing, but nothing here can accept a typed\n"
            "answer — there's no keyboard attached to this session.\n"
            "\n"
            "Look at the changes listed above. If they're right, run the same command again with\n"
            "--yes on the end, which records that you approved them."
        )
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


STATUS_MAP = {
    "building": "1",   # Building/Pending
    "accruing": "2",   # Open to accrual
    "analysis": "3",   # Closed to Accrual; In Analysis
    "published": "4",  # Published
    "locked": "5",     # Closed -- locked
    "inactive": "6",   # Inactive
    "shelved": "7",    # Closed; Will not be Published
}

BUILD_STEPS = (
    "project_created", "dd_uploaded", "user_rights_complete",
    "data_imported", "review_internal", "review_pi", "study_production",
)


def dd_identifier_fields(path):
    """Fields a data dictionary CSV flags `Identifier? = y` (website or API header style)."""
    import csv
    try:
        with open(path, newline="") as fh:
            rows = list(csv.DictReader(fh))
    except FileNotFoundError:
        sys.exit(f"I couldn't find the data dictionary {path}. Check the name and folder.")
    out = []
    for row in rows:
        name = row.get("Variable / Field Name") or row.get("field_name") or ""
        flag = row.get("Identifier?") or row.get("identifier") or ""
        if name and flag.strip().lower() in ("y", "yes", "1"):
            out.append(name.strip())
    return out


def _done(value):
    """The tracker's own rule (argo_trackers): any settled answer that isn't "no" is done."""
    return str(value or "").strip().lower() not in ("", "no", "0")


def plan(rec, args, dd_identifiers=None):
    """The write this run would make: (payload, diff lines, notes). Pure — no network.

    `rec` is the record as it stands; `args` the parsed flags; `dd_identifiers` the identifier
    fields of the DD given with --dd (None when no --dd).
    """
    payload = {"record_id": str(args.rid)}
    diff_lines, notes = [], []

    def queue(field, new_value, label=None):
        """Add an update to the payload if it would change the current value."""
        cur_val = rec.get(field, "")
        if cur_val == new_value:
            notes.append(f"{field} already '{new_value}' — skipping")
            return
        payload[field] = new_value
        diff_lines.append(f"    {field}:  '{cur_val}'  ->  '{new_value}'" + (f"  ({label})" if label else ""))

    if args.irb_number is not None:
        queue("irb_number", args.irb_number)
    if args.irb_expires is not None:
        queue("irb_approval_expires", args.irb_expires)
    if args.close:
        queue("study_production", "1", "Pushed to production")
        if not args.status:
            queue("study_status", "2", "Open to accrual")
    if args.close_out:
        # "Close out the build": every step not yet done is ticked, in one push, one diff. A step
        # already settled keeps its answer (data_imported=2 stays "prospective"). The form-complete
        # rule below then closes build_tracking. Saying the phrase IS the confirmation of the
        # three human gates — the diff still shows them before anything is written.
        for step in BUILD_STEPS:
            if not _done(rec.get(step)):
                queue(step, "1", "done — close-out")
    if args.mark_built:
        for step in BUILD_STEPS:  # all 7 yes/no
            queue(step, "1", "done")
        if not args.status:
            queue("study_status", "2", "Open to accrual")
        queue("completed", "1", "tracking.completed = Yes")
        for form in ("study_initiation_request_complete", "build_tracking_complete",
                     "study_metadata_complete", "tracking_complete"):
            queue(form, "2", "form Complete")
    if args.reopen:
        queue("study_production", "", "blank (reopened)")
        if not args.status:
            queue("study_status", "1", "Building/Pending")
    if args.pid:
        queue("new_project_pid", args.pid)
    if args.status:
        queue("study_status", STATUS_MAP[args.status], args.status)
    for step in args.mark_step:
        if step not in BUILD_STEPS:
            notes.append(f"⚠️  '{step}' is not one of the canonical build_tracking fields "
                         f"({', '.join(BUILD_STEPS)}). Proceeding anyway — confirm this is intentional.")
        queue(step, "1", "done")
    for step in args.unmark_step:
        # "0", not blank: the step is answered "not done", and a blank would be ignored by an
        # overwriteBehavior=normal import.
        if str(rec.get(step, "")).strip() in ("", "0"):
            notes.append(f"{step} already not done — skipping")
            continue
        queue(step, "0", "not done — re-mark when it's done again")
    for pair in args.set_pairs:
        if "=" not in pair:
            sys.exit(f"--set requires FIELD=VALUE format, got: {pair}")
        field, value = pair.split("=", 1)
        queue(field.strip(), value.strip())

    # A DD with an identifier field makes the project PHI-bearing. That follows from the DD, so
    # it rides in this push (shown in the diff) instead of being asked as a separate question.
    # Only ever set to 1 — a DD without identifiers says nothing about other PHI.
    if dd_identifiers:
        queue("contains_phi", "1", f"the DD flags identifiers: {', '.join(dd_identifiers[:5])}")

    after = {**rec, **payload}
    # When the 7th step lands, close the build_tracking form too — two closings left it
    # "Incomplete" because nothing set it.
    if all(_done(after.get(step)) for step in BUILD_STEPS) and \
            str(after.get("build_tracking_complete", "")) != "2":
        queue("build_tracking_complete", "2", "all 7 steps done — form Complete")

    # Production with no IRB number or expiry on the record: say so out loud. A warning for now
    # (Matteo may make it a stop); a PAST expiry is already flagged by the build before this.
    if _done(payload.get("study_production")):
        for field, what in (("irb_number", "IRB number"), ("irb_approval_expires", "IRB expiry date")):
            if not str(after.get(field, "")).strip():
                notes.append(f"⚠️  `{field}` ({what}) is blank. The PM / requester updates it on the "
                             f"Study Tracker (or add it with --{field.replace('_approval', '').replace('_', '-')}). "
                             f"Going ahead; it stays on the Outstanding list.")
    return payload, diff_lines, notes


def main():
    ap = argparse.ArgumentParser(description="Apply targeted updates to a SIR record.")
    ap.add_argument("rid", help="SIR record_id")
    # Read mode
    ap.add_argument("--yes", action="store_true",
                    help="Approve the change without being asked. Required when running where "
                         "there's no keyboard to answer a prompt (agent sessions, scheduled jobs).")
    ap.add_argument("--pull", action="store_true", help="Print the full record (intake + build_tracking + study_metadata) as JSON to stdout. Read-only; ignores all write flags.")
    # Convenience flags (common cases)
    ap.add_argument("--irb-number", help="Set irb_number (e.g. IPH/OAU/12/3275)")
    ap.add_argument("--irb-expires", help="Set irb_approval_expires as YYYY-MM-DD")
    ap.add_argument("--close", action="store_true", help="Push to production: study_production=1 + study_status=2 (Open to accrual)")
    ap.add_argument("--mark-built", action="store_true", help="Mark study fully built/in-production: all 7 build_tracking steps=1, study_production=1, study_status=2, tracking.completed=1, all 4 instrument_complete=2.")
    ap.add_argument("--close-out", action="store_true",
                    help="Close out the build: tick every build step not yet done and set the "
                         "build_tracking form to Complete, in one push with one diff.")
    ap.add_argument("--reopen", action="store_true", help="Clear study_production and reset study_status to 1 (Building/Pending)")
    ap.add_argument("--pid", help="Set new_project_pid (the PID of the newly-created REDCap project)")
    ap.add_argument("--status", choices=list(STATUS_MAP.keys()), help=f"Set study_status. Choices: {'/'.join(STATUS_MAP.keys())}")
    ap.add_argument("--mark-step", action="append", default=[], help=f"Mark a build_tracking yesno as done. Repeatable. Canonical 7: {', '.join(BUILD_STEPS)}. Warns (but proceeds) for fields outside this list.")
    ap.add_argument("--dd", metavar="CSV",
                    help="The study's data dictionary. If it flags any identifier field, "
                         "contains_phi=1 is added to this push (shown in the diff).")
    ap.add_argument("--unmark-step", action="append", default=[], choices=BUILD_STEPS,
                    help="Set a build step back to not done (0) — e.g. dd_uploaded after the DD is "
                         "revised, until the new one is uploaded. Repeatable.")
    # Escape hatch for any field
    ap.add_argument("--set", action="append", default=[], dest="set_pairs", metavar="FIELD=VALUE", help="Set any field (intake, build_tracking, or study_metadata). Repeatable.")
    args = ap.parse_args()

    global REDCAP_URL, SIR_TOKEN
    settings = load_env_file()
    REDCAP_URL = os.environ.get("REDCAP_URL")
    SIR_TOKEN = os.environ.get("STUDY_INITIATION_REQUEST")

    if not REDCAP_URL or not SIR_TOKEN:
        where = (f"Your settings file is here:\n\n    {settings}\n"
                 if settings else
                 "Open your ARGO folder and double-click 'Add keys here' — that opens your\n"
                 "settings file in a text editor.\n")
        sys.exit(
        "This tool needs to know the web address of your REDCap system, and the access key for\n"
        "the Study Tracker, before it can do anything. One or both isn't set yet.\n"
        "\n"
        "Both live in your ARGO settings file, one per line (REDCAP_URL= and\n"
        "STUDY_INITIATION_REQUEST=).\n"
        "\n"
        + where +
        "\nIf you don't have the key yet, ask your ARGO REDCap administrator to set you up."
    )

    # Pull mode: read-only, dump JSON, exit
    if args.pull:
        rec = api_post(SIR_TOKEN, content="record", **{f"records[0]": args.rid})
        if not rec:
            sys.exit(
            f"There's no record numbered {args.rid} in the Study Tracker.\n"
            "\n"
            "Check the number — you can see the full list by running the portfolio tool\n"
            "(the weekly check), which prints each study's record number in square brackets."
        )
        json.dump(rec[0], sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    if not (args.irb_number or args.irb_expires or args.close or args.reopen
            or args.pid or args.status or args.mark_step or args.unmark_step or args.set_pairs
            or args.mark_built or args.dd or args.close_out):
        sys.exit("Nothing to do — pass at least one of: --pull, --irb-number, --irb-expires, --close, --reopen, --pid, --status, --mark-step, --unmark-step, --close-out, --mark-built, --dd, --set FIELD=VALUE")
    clash = set(args.mark_step) & set(args.unmark_step)
    if clash:
        sys.exit(f"Can't mark and unmark the same step in one run: {', '.join(sorted(clash))}")

    if args.irb_expires and not re.match(r"^\d{4}-\d{2}-\d{2}$", args.irb_expires):
        sys.exit(
            f"The IRB expiry date needs to be written year-month-day, with dashes, like\n"
            f"2027-04-16. I got: {args.irb_expires}\n"
            "\n"
            "REDCap only accepts that exact format on import, so 16/04/2027 or Apr 16 2027\n"
            "won't work."
        )

    # Step 1: confirm token
    info = api_post(SIR_TOKEN, content="project")
    print(f"\n  Target project")
    print(f"  ──────────────")
    print(f"  title: {info.get('project_title')}")
    print(f"  pid:   {info.get('project_id')}")
    print(f"  access key ending: ...{SIR_TOKEN[-4:]}")
    if "Study Tracker" not in info.get("project_title", "") and "Study Initiation" not in info.get("project_title", ""):
        sys.exit(
            "Stopping before making any changes.\n"
            "\n"
            "The access key set up on this computer doesn't open the Study Tracker — it opens a\n"
            "different REDCap project. Writing build progress to the wrong project would put\n"
            "false information in someone else's study, so nothing has been changed.\n"
            "\n"
            "Check the STUDY_INITIATION_REQUEST line in ~/.argo/.env, or ask your REDCap\n"
            "administrator which key belongs to the Study Tracker."
        )

    # Step 2: fetch the full record so we can diff against any field
    cur = api_post(SIR_TOKEN, content="record",
                   **{f"records[0]": args.rid})
    if not cur:
        sys.exit(f"Record {args.rid} not found in SIR.")
    rec = cur[0]
    print(f"\n  Record {args.rid} — {rec.get('pi_surname')}: {rec.get('project_title','')[:60]}")
    print(f"    irb_number              = '{rec.get('irb_number','')}'")
    print(f"    irb_approval_expires    = '{rec.get('irb_approval_expires','')}'")
    print(f"    new_project_pid         = '{rec.get('new_project_pid','')}'")
    print(f"    study_status            = '{rec.get('study_status','')}'")
    print(f"    study_production        = '{rec.get('study_production','')}'")
    for step in BUILD_STEPS[:-1]:  # all but study_production (already shown)
        v = rec.get(step, '')
        if v:
            print(f"    {step:24s}= '{v}'")

    # Step 3: build the diff
    dd_identifiers = dd_identifier_fields(args.dd) if args.dd else None
    payload, diff_lines, notes = plan(rec, args, dd_identifiers)
    for note in notes:
        print(f"  {note}")

    if len(payload) == 1:
        print("\n  No changes to apply.")
        return

    print(f"\n  Proposed write:")
    for line in diff_lines:
        print(line)
    if not confirm("\nPost this update?"):
        sys.exit("Aborted by user — no changes made.")

    # Step 4: post
    resp = api_post_record(SIR_TOKEN, [payload])
    print(f"\n  Server response: {resp}")

    # Step 5: verify — show only the fields we just wrote
    verify = api_post(SIR_TOKEN, content="record", **{f"records[0]": args.rid})
    v = verify[0]
    written_fields = [f for f in payload if f != "record_id"]
    print(f"  Verified:")
    for f in written_fields:
        print(f"    {f}: '{v.get(f, '')}'")


if __name__ == "__main__":
    main()
