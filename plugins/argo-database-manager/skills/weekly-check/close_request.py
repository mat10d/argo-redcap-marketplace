#!/usr/bin/env python3
"""Close one request on its tracker: tick `completed`, after showing the change and asking.

    python3 close_request.py people 12             # shows the change, asks before writing
    python3 close_request.py data 7 --yes          # approved already (no keyboard here)
    python3 close_request.py data 7 --assigned-to jdoe --yes

Queues: people (Study Personnel Request), data (Data Request), linking (Data Linking Request),
support (Support Ticket Request). Builds are closed with build-study's `sir_update.py
--close-out`, not here.

`assigned_to` is a REDCap username. It is only ever written when you name the real username with
--assigned-to — never guessed, never filled from a display name.

Writes go through the shared client, which confirms the key opens the tracker it should before
anything is written. No key for that tracker? Tick `completed` on the record in REDCap instead.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
for _cand in (_here / "scripts",
              *(p / "plugins/argo-core/skills/redcap-api/scripts" for p in _here.parents)):
    if (_cand / "argo_redcap_client.py").exists():
        sys.path.insert(0, str(_cand))
        break
from argo_redcap_client import RedcapClient, RedcapError  # noqa: E402
from argo_trackers import ADMIN_TRACKERS  # noqa: E402

QUEUES = {
    "people": "STUDY_PERSONELL_REQUEST",
    "data": "DATA_REQUEST",
    "linking": "DATA_LINKING_REQUEST",
    "support": "SUPPORT_TICKET_REQUEST",
}


def plan_close(rec: dict, id_field: str, record_id: str, assigned_to: "str | None" = None):
    """(payload, diff lines) to close this request. Empty payload when nothing would change.

    Pure — no network. Only `completed`, and `assigned_to` when a real username was given.
    """
    payload = {id_field: str(record_id)}
    diff = []
    if str(rec.get("completed", "")).strip() != "1":
        payload["completed"] = "1"
        diff.append(f"    completed:  '{rec.get('completed', '')}'  ->  '1'")
    if assigned_to and str(rec.get("assigned_to", "")).strip() != assigned_to:
        payload["assigned_to"] = assigned_to
        diff.append(f"    assigned_to:  '{rec.get('assigned_to', '')}'  ->  '{assigned_to}'")
    return (payload if len(payload) > 1 else {}), diff


def confirm(prompt: str, yes: bool) -> bool:
    if yes or os.environ.get("ARGO_ASSUME_YES") == "1":
        return True
    if not sys.stdin.isatty():
        sys.exit(f"{prompt}\n\nNothing written. Check the change above; if it's right, run the "
                 "same command again with --yes.")
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


def main() -> int:
    ap = argparse.ArgumentParser(description="Close one request on its tracker.")
    ap.add_argument("queue", choices=sorted(QUEUES))
    ap.add_argument("record_id")
    ap.add_argument("--assigned-to", metavar="USERNAME",
                    help="The real REDCap username of who did it. Leave out unless you know it.")
    ap.add_argument("--yes", action="store_true", help="Approved already — don't ask.")
    args = ap.parse_args()

    env_var = QUEUES[args.queue]
    _env, title, pid, _marker = next(t for t in ADMIN_TRACKERS if t[0] == env_var)
    client = RedcapClient.from_env(env_var, label=title)
    if client is None:
        print(f"No key for the {title} on this computer. Tick 'completed' on record "
              f"{args.record_id} in that project on the REDCap website instead.")
        return 1
    try:
        id_field = client.record_id_field()
        records = client.export_records(records=str(args.record_id))
        if not records:
            print(f"No record {args.record_id} in the {title}.")
            return 1
        payload, diff = plan_close(records[0], id_field, args.record_id, args.assigned_to)
        if not payload:
            print(f"Record {args.record_id} in the {title} is already closed.")
            return 0
        print(f"{title} — record {args.record_id}:")
        print("\n".join(diff))
        if not confirm("Write this?", args.yes):
            print("Nothing written.")
            return 1
        client.import_records([payload], expect_title=title, expect_pid=pid, overwrite="normal")
        print(f"Closed: record {args.record_id} in the {title}.")
        return 0
    except RedcapError as e:
        print(str(e).strip(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
