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

Two queues lead with what the request is ABOUT before that generic summary: builds with the
study's short name and PI, people with the person's name, email and the access they're asking
for. Both degrade to the plain summary when a record doesn't carry those fields — nothing is
assumed to exist.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from argo_trackers import ADMIN_TRACKERS, SOURCE_FORMS, sir_progress  # noqa: E402
from argo_redcap_client import RedcapClient, RedcapError  # noqa: E402

# The queues a database manager fulfils. Support tickets (225) are PM triage, so they are
# shown as a count only, never expanded.
QUEUES = {
    "builds":  ("STUDY_INITIATION_REQUEST", "Studies to build"),
    "people":  ("STUDY_PERSONELL_REQUEST",  "People requests"),
    "linking": ("DATA_LINKING_REQUEST",     "Linking requests"),
    "data":    ("DATA_REQUEST",             "Data requests"),
}
# Where each queue is fulfilled. People requests have no skill: access is granted by hand on
# the study project's User Rights page in REDCap, so the line says the page, not a skill.
ROUTE = {
    "builds":  "the build-study skill",
    "people":  "REDCap itself — the study project's User Rights page (Users & Roles)",
    "linking": "the link-data skill",
    "data":    "the export-data skill",
}
# Triage/bookkeeping fields that say nothing about what the request IS.
BORING = {"assigned_to", "assignment_date", "completed", "resolution_date", "notes"}

# A people request is ABOUT a person: who they are, how to reach them, and what they are asking
# for. The Study Personnel Request form (PID 221, verified against its live data dictionary)
# names those fields first_name / last_name / email / user_study / user_role, so the queue leads
# with them instead of whatever the form happens to list first — which is the REDCap instance,
# then a phone number. The weekly check puts every open request in its own table row, and a row
# that doesn't name the person, carry their email, or say what they want is a row nobody can act
# on. Labels still come from the tracker's own data dictionary, and any of these fields the
# record doesn't carry is simply dropped — nothing here is assumed to be filled in.
PERSON_FIELDS = ("first_name", "last_name", "email")
PERSON_ASK_FIELDS = ("user_study", "user_role")
PEOPLE_LEAD_FIELDS = PERSON_FIELDS + PERSON_ASK_FIELDS

NO_DETAILS = "(no details filled in)"


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


def _clean_label(label: str, width: "int | None" = 40) -> str:
    """A DD field label, ready to have ': value' appended to it.

    REDCap labels are written to be read on a form, so most of them already end in a colon
    ("Full study title:"). Appending our own produced "Full study title:: Hepatectomy" on every
    line of the queue. Collapse the wrapping the Designer inserts, drop the trailing colon, and
    drop it again after truncation in case the cut landed on one. `width=None` keeps the whole
    label, for the one-record view where there is room for it.
    """
    text = " ".join(str(label or "").split()).rstrip(" :")
    return (text if width is None else text[:width]).rstrip(":")


def _summarise(rec: dict, fields: list, id_field: str, skip=()) -> str:
    """A one-line summary: the first few filled, non-triage fields, by label.

    `skip` drops fields another part of the line already showed, so nothing is said twice.
    """
    bits = []
    for name, label in fields:
        if name == id_field or name in BORING or name in skip or name.endswith("_complete"):
            continue
        val = str(rec.get(name, "")).strip()
        if not val:
            continue
        bits.append(f"{_clean_label(label)}: {val[:60]}")
        if len(bits) == 3:
            break
    return "; ".join(bits) if bits else NO_DETAILS


def _person_bits(rec: dict, labels: dict) -> list:
    """The person a people request is about: name, email, and the access they're asking for.

    Written as the same 'Label: value' bits the summary uses, so one splitting rule turns any
    queue line into table columns. Fields the record doesn't carry are dropped — a half-filled
    request still gets a usable row rather than empty columns.
    """
    bits = []
    for name in PEOPLE_LEAD_FIELDS:
        val = str(rec.get(name, "")).strip()
        if val:
            bits.append(f"{_clean_label(labels.get(name, name))}: {val[:60]}")
    return bits


def _detail_line(key: str, rec: dict, fields: list, id_field: str) -> str:
    """The detail half of one queue line — labelled bits joined with '; '.

    Every queue renders the same way; the people queue just leads with who it is about.
    """
    lead = _person_bits(rec, dict(fields)) if key == "people" else []
    rest = _summarise(rec, fields, id_field, skip=PEOPLE_LEAD_FIELDS if lead else ())
    if lead:
        return "; ".join(lead if rest == NO_DETAILS else lead + [rest])
    return rest


def _study_label(rec: dict) -> str:
    """'<short name> — PI: <surname>', for the studies-to-build queue.

    The weekly check's other half (the portfolio) identifies every study by its short name and
    PI. When this half showed only a record number and the first few form fields, the two halves
    named the same study differently and nobody could match them up by eye. Either part is
    dropped when the record doesn't carry it — a half-filled request still gets a useful line.
    """
    short = str(rec.get("shortened_study_name") or "").strip()
    pi = str(rec.get("pi_surname") or "").strip()
    bits = []
    if short:
        bits.append(short[:55])
    if pi:
        bits.append(f"PI: {pi}")
    return " — ".join(bits)


def _open_records(client: RedcapClient, done_marker: str) -> "tuple[list, str]":
    """(open records, id_field). Label export, mirroring how the portfolio buckets done."""
    id_field = client.record_id_field()
    records = client.export_records(rawOrLabel="label")
    return [r for r in records if str(r.get(done_marker, "")).strip() != "Yes"], id_field


def _sir_progress(rec: dict) -> str:
    """'N/M' build steps done. The counting rule lives in argo_trackers.sir_progress, which
    the weekly check reads too — one rule, so a study never shows 3/7 here and 4/7 there."""
    done, total = sir_progress(rec)
    return f"{done}/{total}"


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
            study = _study_label(rec) if key == "builds" else ""
            lead = f"{study} — " if study else ""
            extra = f"  [{_sir_progress(rec)} build steps done]" if key == "builds" else ""
            print(f"  {rid}: {lead}{_detail_line(key, rec, fields, id_field)}{extra}")
        print(f"  -> fulfilled in {ROUTE[key]}; when done, mark the record's"
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
            print(f"  {_clean_label(labels.get(name, name), width=None)}: {val}")
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
                print(f"Support tickets: {len(open_tix)} open "
                      f"(triaged by hand in that project — not a build queue)")
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
