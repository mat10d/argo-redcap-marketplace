#!/usr/bin/env python3
"""What's waiting for the database manager — the open items across the ARGO request trackers.

    python3 open_requests.py                          # every queue, open items only
    python3 open_requests.py --queue people           # one queue: people|data|linking|builds
    python3 open_requests.py --record people 12       # one record, every filled field, by label

Reads the trackers with the five keys everyone on the team holds. A queue whose key is missing
or failing is reported as unavailable and skipped — the landing never blocks on one bad key.

Field names on the request forms are deliberately NOT hardcoded (they are unverified against the
live projects): each record's summary is built from the tracker's own data dictionary — the
first few filled fields on the request form, shown by their labels. That renders correctly
whatever the forms actually contain.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from argo_trackers import ADMIN_TRACKERS, SOURCE_FORMS, SIR_BUILD_STEPS  # noqa: E402
from argo_redcap_client import RedcapClient, RedcapError  # noqa: E402

# The queues a database manager fulfils. Support tickets (225) are PM triage, so they are
# shown as a count only, never expanded.
QUEUES = {
    "builds":  ("STUDY_INITIATION_REQUEST", "Studies to build"),
    "people":  ("STUDY_PERSONELL_REQUEST",  "People requests"),
    "linking": ("DATA_LINKING_REQUEST",     "Linking requests"),
    "data":    ("DATA_REQUEST",             "Data requests"),
}
ROUTE = {
    "builds":  "build-study",
    "people":  "manage-redcaps",
    "linking": "link-data",
    "data":    "export-data",
}
# Triage/bookkeeping fields that say nothing about what the request IS.
BORING = {"assigned_to", "assignment_date", "completed", "resolution_date", "notes"}


def _tracker(env_var):
    return next(t for t in ADMIN_TRACKERS if t[0] == env_var)


def _form_fields(client: RedcapClient, form: str) -> list:
    """(field_name, field_label) for the request form, in DD order. Empty list on any failure."""
    try:
        meta = client.export_metadata()
    except RedcapError:
        return []
    return [(m.get("field_name", ""), m.get("field_label", "") or m.get("field_name", ""))
            for m in meta if m.get("form_name") == form]


def _summarise(rec: dict, fields: list, id_field: str) -> str:
    """A one-line summary: the first few filled, non-triage fields, by label."""
    bits = []
    for name, label in fields:
        if name == id_field or name in BORING or name.endswith("_complete"):
            continue
        val = str(rec.get(name, "")).strip()
        if not val:
            continue
        label = " ".join(label.split())[:40]
        bits.append(f"{label}: {val[:60]}")
        if len(bits) == 3:
            break
    return "; ".join(bits) if bits else "(no details filled in)"


def _open_records(client: RedcapClient, done_marker: str) -> "tuple[list, str]":
    """(open records, id_field). Label export, mirroring how the portfolio buckets done."""
    id_field = client.record_id_field()
    records = client.export_records(rawOrLabel="label")
    return [r for r in records if str(r.get(done_marker, "")).strip() != "Yes"], id_field


def _sir_progress(rec: dict) -> str:
    done = sum(1 for f in SIR_BUILD_STEPS if str(rec.get(f, "")).strip() == "Yes")
    return f"{done}/{len(SIR_BUILD_STEPS)}"


def show_queue(key: str, expand: bool = True) -> "int | None":
    """Print one queue. Returns the open count, or None when the queue is unavailable."""
    env_var, heading = QUEUES[key]
    _env, title, pid, done_marker = _tracker(env_var)
    client = RedcapClient.from_env(env_var)
    if client is None:
        print(f"{heading}: unavailable — the {title!r} access key isn't set up.")
        return None
    try:
        open_recs, id_field = _open_records(client, done_marker)
    except RedcapError as e:
        first = str(e).strip().splitlines()[0]
        print(f"{heading}: unavailable — {first}")
        return None
    print(f"{heading}: {len(open_recs)} open")
    if expand and open_recs:
        fields = _form_fields(client, SOURCE_FORMS[env_var])
        for rec in open_recs:
            rid = rec.get(id_field, "?")
            extra = f"  [{_sir_progress(rec)} build steps done]" if key == "builds" else ""
            print(f"  {rid}: {_summarise(rec, fields, id_field)}{extra}")
        print(f"  -> fulfilled with the {ROUTE[key]} skill; when done, mark the record's"
              f" '{done_marker}' box in the {title} project on the REDCap website.")
    return len(open_recs)


def show_record(key: str, record_id: str) -> int:
    env_var, heading = QUEUES[key]
    _env, title, _pid, _marker = _tracker(env_var)
    client = RedcapClient.from_env(env_var)
    if client is None:
        print(f"The {title!r} access key isn't set up, so I can't pull that record.")
        return 1
    id_field = client.record_id_field()
    records = client.export_records(rawOrLabel="label", records=str(record_id))
    if not records:
        print(f"No record {record_id!r} in {title}.")
        return 1
    labels = dict(_form_fields(client, SOURCE_FORMS[env_var]))
    print(f"{heading} — record {record_id} ({title}):")
    for name, val in records[0].items():
        val = str(val).strip()
        if val and not name.endswith("_complete"):
            print(f"  {labels.get(name, name)}: {val}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="The database manager's landing view: open requests across the trackers.")
    ap.add_argument("--queue", choices=sorted(QUEUES),
                    help="Show one queue instead of all of them")
    ap.add_argument("--record", nargs=2, metavar=("QUEUE", "RECORD_ID"),
                    help="Show one request in full, every filled field by its label")
    args = ap.parse_args()

    if args.record:
        key, rid = args.record
        if key not in QUEUES:
            print(f"Unknown queue {key!r} — pick from: {', '.join(sorted(QUEUES))}")
            return 1
        return show_record(key, rid)

    keys = [args.queue] if args.queue else ["builds", "people", "data", "linking"]
    counts = [show_queue(k) for k in keys]
    if not args.queue:
        support = RedcapClient.from_env("SUPPORT_TICKET_REQUEST")
        if support is not None:
            try:
                open_tix, _ = _open_records(support, "completed")
                print(f"Support tickets: {len(open_tix)} open (PM triage — not a build queue)")
            except RedcapError:
                pass
    if all(c is None for c in counts):
        print("\nNone of the tracker keys are set up, so there's no queue to show.\n"
              "The five tracker keys go in your ARGO settings file — double-click\n"
              "'Add keys here' in your ARGO folder to open it.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
