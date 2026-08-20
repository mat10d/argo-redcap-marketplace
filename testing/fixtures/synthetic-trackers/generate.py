#!/usr/bin/env python3
"""Seeded generator for the synthetic ARGO admin-tracker fixtures.

SYNTHETIC TEST DATA. Every name, email, institution and study in every file this script
writes is fabricated. No real ARGO people, sites, studies, PIDs or exports appear here.

The five admin trackers are defined once, in
`plugins/argo-core/skills/redcap-api/scripts/argo_trackers.py`. This fixture imitates what
the REDCap API returns for each of them:

    <tracker>.json           content=record, rawOrLabel=label  -> list[dict] of label-mode records
    metadata_<tracker>.json  content=metadata                  -> list[dict] of DD rows

so that the two consumers of that shape can be driven with no network and no keys:

    plugins/argo-core/skills/redcap-api/scripts/open_requests.py        (_open_records,
                                                                        _form_fields,
                                                                        _summarise,
                                                                        _sir_progress)
    plugins/argo-project-manager/skills/monitor-studies/portfolio.py    (sir_progress,
                                                                        summarize, collect
                                                                        bucketing)

Nothing is invented that those two scripts do not read: every field on every form is either
a field one of them looks up by name, the record ID, a form-status field, or one of
open_requests' BORING triage fields (which exist precisely so the summariser can be seen
skipping them).

Regenerates byte-identically on every run (stdlib only, no timestamps, fixed seed).

Run:
    python3 generate.py                # writes into its own directory
    python3 generate.py --out DIR      # writes into DIR (used by the byte-stability test)
"""

from __future__ import annotations

import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20260820

# The record ID field name is the same on all five trackers. portfolio.collect() hardcodes
# `record_id`; open_requests derives it from metadata[0]. Both agree on this fixture.
ID_FIELD = "record_id"

# open_requests.BORING — triage fields the summariser must skip. Mirrored here so the fixture
# deliberately contains them; the test asserts their labels never reach a summary line.
BORING = {"assigned_to", "assignment_date", "completed", "resolution_date", "notes"}

META_COLUMNS = [
    "field_name", "form_name", "section_header", "field_type", "field_label",
    "select_choices_or_calculations", "field_note",
    "text_validation_type_or_show_slider_number", "text_validation_min",
    "text_validation_max", "identifier", "branching_logic", "required_field",
    "custom_alignment", "question_number", "matrix_group_name", "matrix_ranking",
    "field_annotation",
]

YESNO = "1, Yes | 0, No"

# A deliberately long, line-wrapped label. open_requests._summarise collapses whitespace and
# truncates to 40 characters; this field is positioned third on its form so it lands inside
# the three-field summary of every filled linking request.
LONG_LABEL = ("Purpose of the linkage, including which\n        analysis it feeds "
              "and why it is needed")

# One field carries an empty label so _form_fields' "or field_name" fallback is exercised.
# It sits on the support-ticket form, which is a count-only queue, so it never reaches a
# summary line in the normal flow.
BLANK_LABEL_FIELD = "severity"


def meta(name, form, ftype, label, choices="", validation="", vmin="", vmax="",
         note="", section=""):
    row = dict.fromkeys(META_COLUMNS, "")
    row.update({
        "field_name": name, "form_name": form, "section_header": section,
        "field_type": ftype, "field_label": label,
        "select_choices_or_calculations": choices, "field_note": note,
        "text_validation_type_or_show_slider_number": validation,
        "text_validation_min": vmin, "text_validation_max": vmax,
    })
    return row


# --------------------------------------------------------------------------------------
# Data dictionaries — one per tracker, in DD order (the ID field first, as REDCap returns).
# --------------------------------------------------------------------------------------

STUDY_STATUS_CHOICES = ("1, Awaiting review | 2, Approved for build | 3, In build "
                        "| 4, Internal review | 5, In production | 6, On hold")

DATA_IMPORTED_CHOICES = "1, Yes | 2, Prospective study, not required | 0, Not yet"

SIR_META = [
    meta("record_id", "study_initiation_request", "text", "Record ID"),
    meta("project_title", "study_initiation_request", "text", "Full study title",
         section="About the study"),
    meta("shortened_study_name", "study_initiation_request", "text",
         "Short name (study moniker)"),
    meta("pi_surname", "study_initiation_request", "text",
         "Principal investigator surname"),
    meta("study_status", "study_initiation_request", "dropdown",
         "Where the study is right now", choices=STUDY_STATUS_CHOICES),
    meta("request_date", "study_initiation_request", "text",
         "Date the request was submitted", validation="date_ymd"),
    meta("notes", "study_initiation_request", "notes", "Free-text notes for the team"),
    meta("study_initiation_request_complete", "study_initiation_request", "dropdown",
         "Complete?", choices="0, Incomplete | 1, Unverified | 2, Complete"),
    meta("new_project_pid", "build_tracking", "text", "PID of the new REDCap project",
         validation="integer", section="Build tracking"),
    meta("project_created", "build_tracking", "yesno", "Project created", choices=YESNO),
    meta("dd_uploaded", "build_tracking", "yesno", "Data dictionary uploaded", choices=YESNO),
    meta("user_rights_complete", "build_tracking", "yesno", "Roles and users set up",
         choices=YESNO),
    meta("data_imported", "build_tracking", "radio", "Historical data imported",
         choices=DATA_IMPORTED_CHOICES),
    meta("review_internal", "build_tracking", "yesno", "Internal review passed", choices=YESNO),
    meta("review_pi", "build_tracking", "yesno", "PI review passed", choices=YESNO),
    meta("study_production", "build_tracking", "yesno", "Study is in production",
         choices=YESNO),
    meta("assigned_to", "build_tracking", "text", "Assigned to"),
    meta("build_tracking_complete", "build_tracking", "dropdown", "Complete?",
         choices="0, Incomplete | 1, Unverified | 2, Complete"),
]

PERSONNEL_META = [
    meta("record_id", "study_personnel_request", "text", "Record ID"),
    meta("first_name", "study_personnel_request", "text", "Given name",
         section="Who needs access"),
    meta("last_name", "study_personnel_request", "text", "Family name"),
    meta("institution", "study_personnel_request", "text", "Institution or hospital"),
    meta("user_role", "study_personnel_request", "dropdown", "Role being requested",
         choices="1, Data entry | 2, Data manager | 3, Investigator | 4, Monitor"),
    meta("email", "study_personnel_request", "text", "Work email address",
         validation="email"),
    meta("request_date", "study_personnel_request", "text", "Date requested",
         validation="date_ymd"),
    meta("assigned_to", "study_personnel_request", "text", "Assigned to"),
    meta("assignment_date", "study_personnel_request", "text", "Date assigned",
         validation="date_ymd"),
    meta("completed", "study_personnel_request", "yesno", "Request completed",
         choices=YESNO),
    meta("resolution_date", "study_personnel_request", "text", "Date resolved",
         validation="date_ymd"),
    meta("notes", "study_personnel_request", "notes", "Free-text notes for the team"),
    meta("study_personnel_request_complete", "study_personnel_request", "dropdown",
         "Complete?", choices="0, Incomplete | 1, Unverified | 2, Complete"),
]

LINKING_META = [
    meta("record_id", "data_linking_request", "text", "Record ID"),
    meta("request_for_name", "data_linking_request", "text",
         "Name of the person requesting", section="The linkage"),
    meta("needed_by", "data_linking_request", "text", "Date the linked data is needed",
         validation="date_ymd"),
    meta("linking_purpose", "data_linking_request", "notes", LONG_LABEL),
    meta("source_database", "data_linking_request", "text", "Source database"),
    meta("target_database", "data_linking_request", "text", "Target database"),
    meta("assigned_to", "data_linking_request", "text", "Assigned to"),
    meta("completed", "data_linking_request", "yesno", "Request completed", choices=YESNO),
    meta("resolution_date", "data_linking_request", "text", "Date resolved",
         validation="date_ymd"),
    meta("notes", "data_linking_request", "notes", "Free-text notes for the team"),
    meta("data_linking_request_complete", "data_linking_request", "dropdown", "Complete?",
         choices="0, Incomplete | 1, Unverified | 2, Complete"),
]

DATA_META = [
    meta("record_id", "data_request", "text", "Record ID"),
    meta("request_for_name", "data_request", "text", "Name of the person requesting",
         section="The extract"),
    meta("database_name", "data_request", "text", "Database being requested"),
    meta("date_needed_by", "data_request", "text", "Date needed by", validation="date_ymd"),
    meta("variables_requested", "data_request", "notes", "Variables or fields requested"),
    meta("analysis_purpose", "data_request", "notes", "Purpose of the analysis"),
    meta("assigned_to", "data_request", "text", "Assigned to"),
    meta("assignment_date", "data_request", "text", "Date assigned", validation="date_ymd"),
    meta("completed", "data_request", "yesno", "Request completed", choices=YESNO),
    meta("resolution_date", "data_request", "text", "Date resolved", validation="date_ymd"),
    meta("notes", "data_request", "notes", "Free-text notes for the team"),
    meta("data_request_complete", "data_request", "dropdown", "Complete?",
         choices="0, Incomplete | 1, Unverified | 2, Complete"),
]

SUPPORT_META = [
    meta("record_id", "support_ticket", "text", "Record ID"),
    meta("first_name", "support_ticket", "text", "Given name", section="Who is stuck"),
    meta("surname", "support_ticket", "text", "Family name"),
    meta("issue_summary", "support_ticket", "notes", "Summary of the issue"),
    meta("issue_category", "support_ticket", "dropdown", "Category of issue",
         choices="1, Access | 2, Data entry | 3, Export | 4, Other"),
    # Deliberately unlabelled: exercises _form_fields' "label or field_name" fallback.
    meta(BLANK_LABEL_FIELD, "support_ticket", "dropdown", "",
         choices="1, Blocking | 2, Annoying | 3, Cosmetic"),
    meta("assigned_to", "support_ticket", "text", "Assigned to"),
    meta("completed", "support_ticket", "yesno", "Request completed", choices=YESNO),
    meta("resolution_date", "support_ticket", "text", "Date resolved", validation="date_ymd"),
    meta("notes", "support_ticket", "notes", "Free-text notes for the team"),
    meta("support_ticket_complete", "support_ticket", "dropdown", "Complete?",
         choices="0, Incomplete | 1, Unverified | 2, Complete"),
]


# --------------------------------------------------------------------------------------
# Synthetic people, places and studies. All fabricated.
# --------------------------------------------------------------------------------------

PEOPLE = [
    ("Ada", "Testwell"), ("Bruno", "Placeholder"), ("Cleo", "Sampleton"),
    ("Dario", "Mockford"), ("Elin", "Fixtura"), ("Femi", "Dummyson"),
    ("Greta", "Stubbins"), ("Hiro", "Fakeman"), ("Ime", "Synthetica"),
    ("Jonas", "Trialsen"), ("Kemi", "Notreal"), ("Lars", "Exampleby"),
]
INSTITUTIONS = [
    "Fictional Teaching Hospital, Testville",
    "Placeholder Medical Centre, Nowhereton",
    "Example University Clinic, Sampleburg",
]
ROLES = ["Data entry", "Data manager", "Investigator", "Monitor"]
STUDIES = [
    ("SYNTH-A", "Synthetic Anaemia Registry of Testville"),
    ("SYNTH-B", "Fictional Hypertension Cohort, Nowhereton"),
    ("SYNTH-C", "Placeholder Paediatric Nutrition Survey"),
    ("SYNTH-D", "Made-up Maternal Outcomes Study"),
    ("SYNTH-E", "Imaginary Diabetes Follow-up Cohort"),
    ("SYNTH-F", "Notional Trauma Audit"),
    ("SYNTH-G", "Sample Oncology Biobank Registry"),
    ("SYNTH-H", "Dummy Respiratory Symptom Survey"),
    ("SYNTH-J", "Fabricated Renal Transplant Cohort"),
    ("SYNTH-K", "Invented Sickle Cell Care Study"),
    ("SYNTH-L", "Simulated Antenatal Screening Study"),
    ("SYNTH-M", "Counterfeit Cardiology Outcomes Audit"),
]
DATABASES = ["SYNTH-A", "SYNTH-B", "SYNTH-C", "SYNTH-G", "SYNTH-K"]


def email_for(first: str, last: str) -> str:
    return f"{first[0].lower()}.{last.lower()}@example.org"


def blank_record(meta_rows: list) -> dict:
    """Every field on the project, empty — REDCap returns all columns, filled or not."""
    return {row["field_name"]: "" for row in meta_rows}


# --------------------------------------------------------------------------------------
# The engineered records.
# --------------------------------------------------------------------------------------

# (record_id, strict-Yes step values). data_imported on record 7 carries a radio LABEL, not
# "Yes": open_requests._sir_progress counts only literal "Yes", portfolio.sir_progress counts
# any non-empty label that isn't no/0. That one record is the engineered divergence between
# the two progress functions, and the MANIFEST records both answers.
SIR_STEPS = {
    "1": {"project_created": "No", "dd_uploaded": "No", "user_rights_complete": "No",
          "data_imported": "", "review_internal": "No", "review_pi": "No",
          "study_production": "No"},
    "2": {},                                                        # all blank
    "3": {"project_created": "Yes"},
    "4": {"project_created": "Yes"},
    "5": {"project_created": "Yes", "dd_uploaded": "Yes"},
    "6": {"project_created": "Yes", "dd_uploaded": "Yes", "user_rights_complete": "Yes"},
    "7": {"project_created": "Yes", "dd_uploaded": "Yes", "user_rights_complete": "Yes",
          "data_imported": "Prospective study, not required"},
    "8": {"project_created": "Yes", "dd_uploaded": "Yes", "user_rights_complete": "Yes",
          "data_imported": "Yes"},
    "9": {"project_created": "Yes", "dd_uploaded": "Yes", "user_rights_complete": "Yes",
          "data_imported": "Yes", "review_internal": "Yes"},
    "10": {"project_created": "Yes", "dd_uploaded": "Yes", "user_rights_complete": "Yes",
           "data_imported": "Yes", "review_internal": "Yes",
           "review_pi": "Yes"},
    "11": {"project_created": "Yes", "dd_uploaded": "Yes", "user_rights_complete": "Yes",
           "data_imported": "Yes", "review_internal": "Yes",
           "review_pi": "Yes", "study_production": "Yes"},
    "12": {"project_created": "Yes", "dd_uploaded": "Yes", "user_rights_complete": "Yes",
           "data_imported": "Yes", "review_internal": "Yes",
           "review_pi": "Yes", "study_production": "Yes"},
}

SIR_STATUS = {
    "1": "Awaiting review", "2": "", "3": "Approved for build", "4": "On hold",
    "5": "In build", "6": "In build", "7": "In build", "8": "In build",
    "9": "Internal review", "10": "Internal review", "11": "In production",
    "12": "In production",
}

# Record 2 is the engineered "everything on the request form is blank" case: the summariser
# must fall through to "(no details filled in)".
SIR_NO_DETAIL_IDS = ["2"]
# Record 4 has only two filled request-form fields, so its summary is shorter than three bits.
SIR_THIN_IDS = ["4"]


def build_sir(rng: random.Random) -> list:
    records = []
    for i in range(1, 13):
        rid = str(i)
        rec = blank_record(SIR_META)
        rec["record_id"] = rid
        if rid not in SIR_NO_DETAIL_IDS:
            moniker, title = STUDIES[i - 1]
            first, last = PEOPLE[(i - 1) % len(PEOPLE)]
            if rid in SIR_THIN_IDS:
                rec["project_title"] = title
                rec["pi_surname"] = last
            else:
                rec["project_title"] = title
                rec["shortened_study_name"] = moniker
                rec["pi_surname"] = last
                rec["study_status"] = SIR_STATUS[rid]
                rec["request_date"] = f"2026-0{rng.randint(1, 6)}-{rng.randint(10, 28)}"
        rec["study_initiation_request_complete"] = (
            "Complete" if rid not in SIR_NO_DETAIL_IDS else "Incomplete")
        steps = SIR_STEPS[rid]
        for field, value in steps.items():
            rec[field] = value
        if any(v for v in steps.values()):
            rec["new_project_pid"] = str(300 + i)
            rec["assigned_to"] = "Synthetic Build Team"
            rec["build_tracking_complete"] = "Unverified"
        records.append(rec)
    return records


PERSONNEL_DONE_IDS = {"3", "5", "8", "9"}
PERSONNEL_NO_DETAIL_IDS = ["6"]


def build_personnel(rng: random.Random) -> list:
    records = []
    for i in range(1, 10):
        rid = str(i)
        rec = blank_record(PERSONNEL_META)
        rec["record_id"] = rid
        if rid not in PERSONNEL_NO_DETAIL_IDS:
            first, last = PEOPLE[(i * 2) % len(PEOPLE)]
            rec["first_name"] = first
            rec["last_name"] = last
            rec["institution"] = INSTITUTIONS[i % len(INSTITUTIONS)]
            rec["user_role"] = ROLES[i % len(ROLES)]
            rec["email"] = email_for(first, last)
            rec["request_date"] = f"2026-0{rng.randint(1, 7)}-{rng.randint(10, 28)}"
        rec["completed"] = "Yes" if rid in PERSONNEL_DONE_IDS else "No"
        if rid in PERSONNEL_DONE_IDS:
            rec["assigned_to"] = "Synthetic Database Team"
            rec["assignment_date"] = "2026-07-01"
            rec["resolution_date"] = "2026-07-08"
            rec["notes"] = "Access granted in the synthetic project."
        rec["study_personnel_request_complete"] = (
            "Complete" if rid not in PERSONNEL_NO_DETAIL_IDS else "Incomplete")
        records.append(rec)
    return records


LINKING_DONE_IDS = {"2", "5"}
LINKING_NO_DETAIL_IDS = ["4"]


def build_linking(rng: random.Random) -> list:
    records = []
    for i in range(1, 7):
        rid = str(i)
        rec = blank_record(LINKING_META)
        rec["record_id"] = rid
        if rid not in LINKING_NO_DETAIL_IDS:
            first, last = PEOPLE[(i * 3) % len(PEOPLE)]
            rec["request_for_name"] = f"{first} {last}"
            rec["needed_by"] = f"2026-0{rng.randint(6, 9)}-{rng.randint(10, 28)}"
            rec["linking_purpose"] = (
                "Join the synthetic registry to the fabricated pathology sheet "
                "for a fictional descriptive analysis.")
            rec["source_database"] = DATABASES[i % len(DATABASES)]
            rec["target_database"] = DATABASES[(i + 1) % len(DATABASES)]
        rec["completed"] = "Yes" if rid in LINKING_DONE_IDS else "No"
        if rid in LINKING_DONE_IDS:
            rec["assigned_to"] = "Synthetic Database Team"
            rec["resolution_date"] = "2026-07-15"
            rec["notes"] = "Linked and pushed in the synthetic project."
        rec["data_linking_request_complete"] = (
            "Complete" if rid not in LINKING_NO_DETAIL_IDS else "Incomplete")
        records.append(rec)
    return records


DATA_DONE_IDS = {"1", "3", "6", "7"}
DATA_NO_DETAIL_IDS = ["5"]


def build_data(rng: random.Random) -> list:
    records = []
    for i in range(1, 8):
        rid = str(i)
        rec = blank_record(DATA_META)
        rec["record_id"] = rid
        if rid not in DATA_NO_DETAIL_IDS:
            first, last = PEOPLE[(i * 5) % len(PEOPLE)]
            rec["request_for_name"] = f"{first} {last}"
            rec["database_name"] = DATABASES[i % len(DATABASES)]
            rec["date_needed_by"] = f"2026-0{rng.randint(6, 9)}-{rng.randint(10, 28)}"
            rec["variables_requested"] = "age, sex, synthetic outcome flag"
            rec["analysis_purpose"] = "A fabricated Table 1 for a fictional abstract."
        rec["completed"] = "Yes" if rid in DATA_DONE_IDS else "No"
        if rid in DATA_DONE_IDS:
            rec["assigned_to"] = "Synthetic Data Team"
            rec["assignment_date"] = "2026-06-20"
            rec["resolution_date"] = "2026-06-30"
            rec["notes"] = "Extract delivered in the synthetic project."
        rec["data_request_complete"] = (
            "Complete" if rid not in DATA_NO_DETAIL_IDS else "Incomplete")
        records.append(rec)
    return records


SUPPORT_DONE_IDS = {"4", "7"}
SUPPORT_NO_DETAIL_IDS = ["8"]
SUPPORT_ISSUES = [
    "Cannot open the synthetic project on the website.",
    "A fabricated form will not save.",
    "Export button greyed out on the fictional study.",
    "Made-up branching rule hides the wrong question.",
    "Imaginary calendar reminder never arrives.",
    "Notional file upload fails at 90 percent.",
    "Simulated report returns no rows.",
    "",
]
SUPPORT_CATEGORIES = ["Access", "Data entry", "Export", "Other"]
SUPPORT_SEVERITY = ["Blocking", "Annoying", "Cosmetic"]


def build_support(rng: random.Random) -> list:
    records = []
    for i in range(1, 9):
        rid = str(i)
        rec = blank_record(SUPPORT_META)
        rec["record_id"] = rid
        if rid not in SUPPORT_NO_DETAIL_IDS:
            first, last = PEOPLE[(i * 7) % len(PEOPLE)]
            rec["first_name"] = first
            rec["surname"] = last
            rec["issue_summary"] = SUPPORT_ISSUES[i - 1]
            rec["issue_category"] = SUPPORT_CATEGORIES[i % len(SUPPORT_CATEGORIES)]
            rec[BLANK_LABEL_FIELD] = SUPPORT_SEVERITY[i % len(SUPPORT_SEVERITY)]
        rec["completed"] = "Yes" if rid in SUPPORT_DONE_IDS else "No"
        if rid in SUPPORT_DONE_IDS:
            rec["assigned_to"] = "Synthetic PM Team"
            rec["resolution_date"] = "2026-07-22"
            rec["notes"] = "Closed in the synthetic project."
        rec["support_ticket_complete"] = (
            "Complete" if rid not in SUPPORT_NO_DETAIL_IDS else "Incomplete")
        records.append(rec)
    return records


# --------------------------------------------------------------------------------------
# Tracker table — mirrors argo_trackers.ADMIN_TRACKERS / SOURCE_FORMS without importing it
# (fixtures must stand alone), but the MANIFEST records these values so a drift test can
# compare them against the real definitions.
# --------------------------------------------------------------------------------------

TRACKERS = [
    ("STUDY_INITIATION_REQUEST", "Study Tracker", "224", "study_production",
     "study_initiation_request", "study_tracker", SIR_META, build_sir, SIR_NO_DETAIL_IDS),
    ("STUDY_PERSONELL_REQUEST", "Study Personnel Request", "221", "completed",
     "study_personnel_request", "personnel_requests", PERSONNEL_META, build_personnel,
     PERSONNEL_NO_DETAIL_IDS),
    ("DATA_LINKING_REQUEST", "Data Linking Request", "222", "completed",
     "data_linking_request", "data_linking_requests", LINKING_META, build_linking,
     LINKING_NO_DETAIL_IDS),
    ("DATA_REQUEST", "Data Request", "223", "completed",
     "data_request", "data_requests", DATA_META, build_data, DATA_NO_DETAIL_IDS),
    ("SUPPORT_TICKET_REQUEST", "Support Ticket Request", "225", "completed",
     "support_ticket", "support_tickets", SUPPORT_META, build_support,
     SUPPORT_NO_DETAIL_IDS),
]

SIR_BUILD_STEPS = [
    "project_created", "dd_uploaded", "user_rights_complete", "data_imported",
    "review_internal", "review_pi", "study_production",
]


def strict_progress(rec: dict) -> str:
    """open_requests._sir_progress: only the literal label 'Yes' counts."""
    done = sum(1 for f in SIR_BUILD_STEPS if str(rec.get(f, "")).strip() == "Yes")
    return f"{done}/{len(SIR_BUILD_STEPS)}"


def lenient_progress(rec: dict) -> str:
    """portfolio.sir_progress: any non-empty label that isn't no/0 counts."""
    not_done = {"", "no", "0"}
    done = 0
    for f in SIR_BUILD_STEPS:
        v = (rec.get(f) or "").strip()
        if v and v.lower() not in not_done:
            done += 1
    return f"{done}/{len(SIR_BUILD_STEPS)}"


def first_label(meta_rows: list, form: str, rec: dict) -> str:
    """The label that should lead this record's summary line, or '' if it has no details."""
    for row in meta_rows:
        name = row["field_name"]
        if row["form_name"] != form:
            continue
        if name == ID_FIELD or name in BORING or name.endswith("_complete"):
            continue
        if str(rec.get(name, "")).strip():
            return " ".join(row["field_label"].split())[:40]
    return ""


def write_json(path: str, payload) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
        fh.write("\n")


def main() -> int:
    out = HERE
    argv = sys.argv[1:]
    if "--out" in argv:
        out = os.path.abspath(argv[argv.index("--out") + 1])
    os.makedirs(out, exist_ok=True)

    rng = random.Random(SEED)
    manifest = {
        "contract_version": 1,
        "seed": SEED,
        "generated_by": "generate.py",
        "synthetic": True,
        "id_field": ID_FIELD,
        "done_value": "Yes",
        "boring_fields": sorted(BORING),
        "label_fallback_field": BLANK_LABEL_FIELD,
        "sir_build_steps": list(SIR_BUILD_STEPS),
        "trackers": {},
    }

    for (env_var, title, pid, done_marker, form, stem, meta_rows, builder,
         no_detail_ids) in TRACKERS:
        records = builder(rng)
        write_json(os.path.join(out, f"{stem}.json"), records)
        write_json(os.path.join(out, f"metadata_{stem}.json"), meta_rows)

        open_ids = [r[ID_FIELD] for r in records
                    if str(r.get(done_marker, "")).strip() != "Yes"]
        done_ids = [r[ID_FIELD] for r in records
                    if str(r.get(done_marker, "")).strip() == "Yes"]

        entry = {
            "records_file": f"{stem}.json",
            "metadata_file": f"metadata_{stem}.json",
            "project_title": title,
            "pid": pid,
            "source_form": form,
            "done_marker": done_marker,
            "total": len(records),
            "open": len(open_ids),
            "done": len(done_ids),
            "open_record_ids": open_ids,
            "done_record_ids": done_ids,
            "open_with_no_details": [r for r in no_detail_ids if r in open_ids],
            "form_field_count": sum(1 for m in meta_rows if m["form_name"] == form),
            "expected_first_label": {
                r[ID_FIELD]: first_label(meta_rows, form, r) for r in records},
        }
        if env_var == "STUDY_INITIATION_REQUEST":
            strict, lenient, per_rec = {}, {}, {}
            for r in records:
                s, l = strict_progress(r), lenient_progress(r)
                strict[s] = strict.get(s, 0) + 1
                lenient[l] = lenient.get(l, 0) + 1
                per_rec[r[ID_FIELD]] = {"strict": s, "lenient": l}
            entry["sir_progress_strict"] = dict(sorted(strict.items()))
            entry["sir_progress_lenient"] = dict(sorted(lenient.items()))
            entry["sir_progress_per_record"] = per_rec
            entry["progress_divergence_record_ids"] = sorted(
                rid for rid, v in per_rec.items() if v["strict"] != v["lenient"])
        manifest["trackers"][env_var] = entry

    # The long, wrapped label, and what _summarise should render it as.
    manifest["long_label"] = {
        "tracker": "DATA_LINKING_REQUEST",
        "field": "linking_purpose",
        "raw": LONG_LABEL,
        "expected_rendered": " ".join(LONG_LABEL.split())[:40],
    }
    write_json(os.path.join(out, "MANIFEST.json"), manifest)

    print(f"Wrote {len(TRACKERS) * 2 + 1} files to {out}")
    for env_var, entry in manifest["trackers"].items():
        print(f"  {env_var:28} total={entry['total']:>3} "
              f"open={entry['open']:>3} done={entry['done']:>3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
