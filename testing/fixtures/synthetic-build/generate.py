#!/usr/bin/env python3
"""Seeded generator for the SYNBUILD fixture — the database manager's build-task inputs.

SYNTHETIC TEST STUDY — "SYNBUILD — Synthetic Build Study". Every value in every
file this script writes is fabricated. No real people, sites, patients, or data.

Regenerates byte-identically on every run (stdlib only, deterministic by
construction — there is no RNG here, so SEED is recorded for provenance only):

    fields.json                dd_builder.py CLI input (28 fields, 2 forms)
    dirty_datadictionary.csv   18-column REDCap DD with engineered violations
    MANIFEST.json              exact violation list + fields.json inventory

Run:  python3 generate.py     (writes into its own directory)

fields.json format
------------------
Exactly what `python3 dd_builder.py fields.json out.csv` consumes: a JSON list of
objects whose keys are `DD.field()` keyword arguments —
var / type / label / choices / note / valid / min / max / identifier / branching /
required / section / align / qnum / matrix / annotation / form / mdc.
The FIRST entry's "form" also becomes the default form for the whole DD.

MDC policy in fields.json (per argo-core mdc-rules + ARGO practice)
------------------------------------------------------------------
MDC is left to dd_builder.py, which applies it by construction: choices for
radio/dropdown/checkbox, text-format field note for text/notes, date-format
field note for date_dmy/datetime_dmy. Exemptions used here: the record-ID field
(first row), descriptive/calc/file types, and hospital_number/hospital_site.
The `sev_*` matrix group is a STUDY-AUTHORED severity grid, not a validated
psychometric instrument, so it takes MDC normally. No validated Likert scale is
included in this fixture: validated scales are MDC-exempt by ARGO practice but
validate_dd.py has no waiver mechanism for them, so any such scale would make
the clean DD un-clean by design. See MANIFEST.notes.

dirty_datadictionary.csv
------------------------
One engineered instance of (nearly) every check validate_dd.py implements, with
each row perturbed in exactly one intended way — every other column on that row
is deliberately clean so the row's violations are the manifest's violations and
nothing else. Checks that cannot be engineered alongside the others are recorded
in MANIFEST.not_engineerable with the reason.
"""

from __future__ import annotations

import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20260820  # provenance only — this generator is RNG-free

# ---------------------------------------------------------------------------
# MDC strings (must match dd_builder.py / validate_dd.py expectations exactly)
# ---------------------------------------------------------------------------
MDC_CHOICES = ("-666, Patient does not know | -777, Patient refused to answer | "
               "-888, Missing in case notes | -999, Other missing")
TEXT_MDC = ("[-666, Patient does not know  -777, Patient refused to answer  "
            "-888, Missing in case notes  -999, Other missing (add comment for reason missing)]")
DATE_MDC = ("[06-06-6666, Patient does not know  07-07-7777, Patient refused to answer  "
            "08-08-8888, Missing in case notes  09-09-9999, Other missing (add comment for reason missing)]")

HEADER = ["Variable / Field Name", "Form Name", "Section Header", "Field Type", "Field Label",
          "Choices, Calculations, OR Slider Labels", "Field Note",
          "Text Validation Type OR Show Slider Number", "Text Validation Min",
          "Text Validation Max", "Identifier?", "Branching Logic (Show field only if...)",
          "Required Field?", "Custom Alignment", "Question Number (surveys only)",
          "Matrix Group Name", "Matrix Ranking?", "Field Annotation"]


# ===========================================================================
# 1. fields.json — the clean build input
# ===========================================================================

SEV_CHOICES = "0, None | 1, Mild | 2, Moderate | 3, Severe"

FIELDS = [
    # ---- screening form ---------------------------------------------------
    {"var": "synb_id", "type": "text", "label": "Synthetic registration ID (TEST DATA)",
     "form": "screening", "section": "SYNTHETIC TEST STUDY — fabricated data, no real patients"},
    {"var": "hospital_number", "type": "text", "label": "Hospital number",
     "identifier": "y", "form": "screening"},
    {"var": "hospital_site", "type": "radio", "label": "Recruiting site",
     "choices": "1, Alpha Teaching Hospital | 2, Beta General Hospital", "form": "screening"},
    {"var": "enrol_date", "type": "text", "label": "Date of enrolment",
     "valid": "date_dmy", "form": "screening"},
    {"var": "age_years", "type": "text", "label": "Age at enrolment (years)",
     "valid": "integer", "min": "18", "max": "99", "form": "screening"},
    {"var": "sex", "type": "radio", "label": "Sex", "choices": "1, Male | 2, Female",
     "form": "screening"},
    {"var": "education", "type": "dropdown", "label": "Highest level of education",
     "choices": "1, None | 2, Primary | 3, Secondary | 4, Tertiary", "form": "screening"},
    {"var": "marital_status", "type": "radio", "label": "Marital status",
     "choices": "1, Single | 2, Married | 3, Widowed | 4, Divorced", "form": "screening"},
    {"var": "occupation", "type": "text", "label": "Occupation", "form": "screening"},
    {"var": "pregnant_now", "type": "radio", "label": "Currently pregnant?",
     "choices": "1, Yes | 0, No", "branching": "[sex] = '2'", "form": "screening"},
    {"var": "consent_given", "type": "radio", "label": "Written consent obtained?",
     "choices": "1, Yes | 0, No", "form": "screening"},
    {"var": "screening_notes", "type": "notes", "label": "Screening notes",
     "form": "screening"},
    # ---- assessment form --------------------------------------------------
    {"var": "assess_intro", "type": "descriptive",
     "label": "<div>Complete the assessment from the case notes.</div>",
     "form": "assessment", "section": "Clinical assessment"},
    {"var": "symptom_list", "type": "checkbox", "label": "Presenting symptoms (tick all that apply)",
     "choices": "1, Abdominal pain | 2, Bleeding | 3, Weight loss | 4, Fatigue",
     "form": "assessment"},
    {"var": "bleeding_days", "type": "text", "label": "Duration of bleeding (days)",
     "valid": "integer", "min": "0", "max": "365",
     "branching": "[symptom_list(2)] = '1'", "form": "assessment"},
    {"var": "onset_date", "type": "text", "label": "Date of symptom onset",
     "valid": "date_dmy", "form": "assessment"},
    {"var": "weight_kg", "type": "text", "label": "Weight (kg)",
     "valid": "number", "min": "20", "max": "200", "form": "assessment"},
    {"var": "height_cm", "type": "text", "label": "Height (cm)",
     "valid": "integer", "min": "100", "max": "220", "form": "assessment"},
    {"var": "bmi_calc", "type": "calc", "label": "BMI (auto-calculated)",
     "choices": "round([weight_kg]/(([height_cm]/100)*([height_cm]/100)),1)",
     "form": "assessment"},
    # study-authored severity grid (matrix group) — NOT a validated scale
    {"var": "sev_pain", "type": "radio", "label": "Abdominal pain", "choices": SEV_CHOICES,
     "matrix": "sev_grid", "align": "RH", "form": "assessment",
     "section": "Symptom severity in the past week"},
    {"var": "sev_nausea", "type": "radio", "label": "Nausea", "choices": SEV_CHOICES,
     "matrix": "sev_grid", "align": "RH", "form": "assessment"},
    {"var": "sev_fatigue", "type": "radio", "label": "Fatigue", "choices": SEV_CHOICES,
     "matrix": "sev_grid", "align": "RH", "form": "assessment"},
    {"var": "sev_appetite", "type": "radio", "label": "Loss of appetite", "choices": SEV_CHOICES,
     "matrix": "sev_grid", "align": "RH", "form": "assessment"},
    {"var": "sev_sleep", "type": "radio", "label": "Poor sleep", "choices": SEV_CHOICES,
     "matrix": "sev_grid", "align": "RH", "form": "assessment"},
    {"var": "tumor_stage", "type": "dropdown", "label": "Stage at assessment",
     "choices": "1, Stage I | 2, Stage II | 3, Stage III | 4, Stage IV", "form": "assessment"},
    {"var": "referral_source", "type": "text", "label": "Referred from (free text)",
     "form": "assessment"},
    {"var": "followup_plan", "type": "radio", "label": "Follow-up plan",
     "choices": "1, Clinic review | 2, Phone review | 3, No follow-up",
     "branching": "[consent_given] = '1'", "form": "assessment"},
    {"var": "path_report_file", "type": "file", "label": "Pathology report (upload)",
     "form": "assessment"},
]


def fields_inventory():
    types = {}
    forms = {}
    for f in FIELDS:
        types[f["type"]] = types.get(f["type"], 0) + 1
        forms[f["form"]] = forms.get(f["form"], 0) + 1
    mdc_exempt = [f["var"] for f in FIELDS
                  if f is FIELDS[0]
                  or f["type"] in ("descriptive", "calc", "file")
                  or f["var"] in ("hospital_number", "hospital_site")]
    return {
        "file": "fields.json",
        "consumer": "dd_builder.py (CLI: python3 dd_builder.py fields.json out.csv)",
        "n_fields": len(FIELDS),
        "forms": dict(sorted(forms.items())),
        "field_types": dict(sorted(types.items())),
        "record_id_field": FIELDS[0]["var"],
        "identifier_fields": [f["var"] for f in FIELDS if f.get("identifier") == "y"],
        "validation_types": sorted({f["valid"] for f in FIELDS if f.get("valid")}),
        "branching_fields": {f["var"]: f["branching"] for f in FIELDS if f.get("branching")},
        "matrix_groups": {"sev_grid": [f["var"] for f in FIELDS if f.get("matrix") == "sev_grid"]},
        "mdc_exempt_fields": mdc_exempt,
        "mdc_applied_fields": [f["var"] for f in FIELDS if f["var"] not in mdc_exempt],
        "expected_validate_dd": {"errors": 0, "warnings": 0,
                                 "patient_level_flag_safe": True},
    }


# ===========================================================================
# 2. dirty_datadictionary.csv — one engineered instance per validate_dd check
# ===========================================================================
# severity + a wording-tolerant regex the tests use to bucket messages + whether the
# validator's message actually names the offending variable (a few report the row only).
CHECK_META = {
    # --- errors ---
    "first_field_not_text":            ("error", r"first field must be", False),
    "wrong_column_count":              ("error", r"has \d+ columns, expected 18", False),
    "empty_variable_name":             ("error", r"variable name is empty"),
    # NB: "cannot begin with a number" also appears in the form-name message — scope it.
    "variable_name_starts_with_digit": ("error",
                                        r"variable name '[^']*' cannot begin with a number"),
    "variable_name_invalid_chars":     ("error", r"variable name '[^']*' must be lowercase"),
    "duplicate_variable_name":         ("error", r"duplicate variable name"),
    "form_name_empty":                 ("error", r"form name is empty"),
    "form_name_invalid_chars":         ("error", r"form name '[^']*' must be lowercase"),
    "invalid_field_type":              ("error", r"invalid field type"),
    "yesno_field_type_prohibited":     ("error", r"'yesno' field type cannot"),
    "choices_required":                ("error", r"field requires choices"),
    "invalid_validation_type":         ("error", r"invalid validation type"),
    "validation_on_non_text_field":    ("error", r"only valid on 'text' fields"),
    "invalid_identifier_value":        ("error", r"invalid identifier value"),
    "invalid_required_value":          ("error", r"invalid required value"),
    "invalid_custom_alignment":        ("error", r"invalid custom alignment"),
    "matrix_group_name_too_long":      ("error", r"matrix group name exceeds"),
    "matrix_group_name_invalid_chars": ("error", r"matrix group name must be lowercase"),
    "matrix_group_wrong_field_type":   ("error", r"matrix group fields must be radio or checkbox"),
    "invalid_matrix_ranking_value":    ("error", r"invalid matrix ranking value"),
    "branching_unbalanced_brackets":   ("error", r"unbalanced brackets"),
    "mdc_missing_in_choices":          ("error", r"missing mdc in choices"),
    "mdc_date_field_has_text_format":  ("error", r"date field has text-format mdc"),
    "mdc_date_field_missing":          ("error", r"date field missing date-format mdc"),
    "mdc_text_field_has_date_format":  ("error", r"field has date-format mdc"),
    "mdc_text_field_missing":          ("error", r"field missing text-format mdc"),
    # --- warnings ---
    "variable_name_too_long":          ("warning", r"recommended max 26"),
    "field_label_empty":               ("warning", r"field label is empty"),
    "single_choice_select":            ("warning", r"has only 1 choice"),
    "branching_undefined_reference":   ("warning", r"hasn't been defined yet"),
    "redundant_mdc_in_field_note":     ("warning", r"redundant mdc in field note"),
    # --- errors only raised with --patient-level ---
    "patient_level_identifier_flag":   ("error", r"hospital_number must have identifier"),
}

ENTRIES = []  # (cells, [check_name, ...])


def dirty(checks, var, form="clinical", section="", ftype="text", label="Label",
          choices="", note="", valid="", vmin="", vmax="", identifier="",
          branching="", required="", align="", qnum="", matrix="", ranking="",
          annotation="", raw=None):
    """Append one dirty row. `checks` = the violations this row is engineered to raise."""
    cells = raw if raw is not None else [
        var, form, section, ftype, label, choices, note, valid, vmin, vmax,
        identifier, branching, required, align, qnum, matrix, ranking, annotation]
    ENTRIES.append((cells, list(checks)))


LONG_MATRIX = "a_matrix_group_name_that_is_deliberately_longer_than_sixty_chars"  # 64 chars

# Row 2 — first field must be 'text'; everything else on the row is clean.
dirty(["first_field_not_text"], "reg_id", ftype="radio",
      label="Registration ID (wrong type on purpose)",
      choices="1, Prospective | 2, Retrospective",
      section="SYNTHETIC TEST FIXTURE — engineered violations, not a real study")
# Row 3 — clean by default; raises only under --patient-level (Identifier? blank).
dirty(["patient_level_identifier_flag"], "hospital_number", label="Hospital number")
# Row 4 — clean anchor for the duplicate on row 5.
dirty([], "vital_status", ftype="radio", label="Vital status",
      choices="1, Alive | 0, Dead | " + MDC_CHOICES)
# Row 5 — duplicate variable name.
dirty(["duplicate_variable_name"], "vital_status", ftype="radio", label="Vital status (repeat)",
      choices="1, Alive | 0, Dead | " + MDC_CHOICES)
# Row 6 — empty variable name.
dirty(["empty_variable_name"], "", label="Field with no variable name", note=TEXT_MDC)
# Row 7 — variable name begins with a number.
dirty(["variable_name_starts_with_digit"], "2nd_visit_date", label="Second visit date",
      valid="date_dmy", note=DATE_MDC)
# Row 8 — variable name has invalid (uppercase) characters.
dirty(["variable_name_invalid_chars"], "Weight_KG", label="Weight (kg)",
      valid="number", note=TEXT_MDC)
# Row 9 — variable name longer than 26 characters (warning).
dirty(["variable_name_too_long"], "very_long_variable_name_for_testing",
      label="Deliberately long variable name", note=TEXT_MDC)
# Row 10 — form name empty.
dirty(["form_name_empty"], "no_form_var", form="", label="Field with no form", note=TEXT_MDC)
# Row 11 — form name with invalid characters.
dirty(["form_name_invalid_chars"], "bad_form_var", form="Clinical Form",
      label="Field on a badly named form", note=TEXT_MDC)
# Row 12 — invalid field type.
dirty(["invalid_field_type"], "odd_type_var", ftype="radiobutton",
      label="Field with a made-up type")
# Row 13 — yesno is prohibited (cannot hold MDC).
dirty(["yesno_field_type_prohibited"], "surgery_done", ftype="yesno",
      label="Surgery performed?")
# Row 14 — empty field label (warning).
dirty(["field_label_empty"], "unlabelled_var", label="", note=TEXT_MDC)
# Row 15 — select with no choices at all (also fails the MDC-in-choices check).
dirty(["choices_required", "mdc_missing_in_choices"], "tumor_grade", ftype="dropdown",
      label="Tumour grade")
# Row 16 — select with a single choice (warning) — cannot carry MDC, so it also errors.
dirty(["single_choice_select", "mdc_missing_in_choices"], "single_choice", ftype="radio",
      label="Select with one option", choices="1, Only option")
# Row 17 — invalid validation type.
dirty(["invalid_validation_type"], "onset_date", label="Date of symptom onset",
      valid="date_dmyy", note=DATE_MDC)
# Row 18 — validation set on a non-text field.
dirty(["validation_on_non_text_field"], "contact_pref", ftype="radio",
      label="Preferred contact method",
      choices="1, Phone | 2, In person | " + MDC_CHOICES, valid="integer")
# Row 19 — invalid Identifier? value.
dirty(["invalid_identifier_value"], "patient_initials", label="Patient initials",
      note=TEXT_MDC, identifier="yes")
# Row 20 — invalid Required Field? value.
dirty(["invalid_required_value"], "consent_given", ftype="radio", label="Consent obtained?",
      choices="1, Yes | 0, No | " + MDC_CHOICES, required="1")
# Row 21 — invalid Custom Alignment.
dirty(["invalid_custom_alignment"], "bmi_value", label="BMI", valid="number",
      note=TEXT_MDC, align="LEFT")
# Row 22 — matrix group name longer than 60 characters.
dirty(["matrix_group_name_too_long"], "matrix_long_name", ftype="radio",
      label="Matrix item with an over-long group name",
      choices="0, None | 1, Mild | " + MDC_CHOICES, matrix=LONG_MATRIX)
# Row 23 — matrix group name with invalid characters.
dirty(["matrix_group_name_invalid_chars"], "matrix_bad_name", ftype="radio",
      label="Matrix item with a badly named group",
      choices="0, None | 1, Mild | " + MDC_CHOICES, matrix="Symptom Matrix")
# Row 24 — matrix group on a field type that cannot be in a matrix.
dirty(["matrix_group_wrong_field_type"], "matrix_text_item", label="Matrix item as free text",
      note=TEXT_MDC, matrix="sev_grid")
# Row 25 — invalid Matrix Ranking? value.
dirty(["invalid_matrix_ranking_value"], "rank_item", ftype="radio",
      label="Field with a bad ranking flag",
      choices="1, First | 2, Second | " + MDC_CHOICES, ranking="x")
# Row 26 — branching logic with unbalanced brackets.
dirty(["branching_unbalanced_brackets"], "brack_var", label="Field with broken branching",
      note=TEXT_MDC, branching="[vital_status = '1'")
# Row 27 — branching logic referencing a variable that does not exist (warning).
dirty(["branching_undefined_reference"], "ref_var", label="Field branching off a ghost",
      note=TEXT_MDC, branching="[nonexistent_field] = '1'")
# Row 28 — select missing two of the four MDC codes.
dirty(["mdc_missing_in_choices"], "smoking_status", ftype="radio", label="Smoking status",
      choices="1, Never | 2, Former | 3, Current | -666, Patient does not know | "
              "-777, Patient refused to answer")
# Row 29 — MDC duplicated into the field note of a select (warning).
dirty(["redundant_mdc_in_field_note"], "alcohol_use", ftype="radio", label="Alcohol use",
      choices="1, Never | 2, Former | 3, Current | " + MDC_CHOICES, note=TEXT_MDC)
# Row 30 — date field carrying text-format MDC.
dirty(["mdc_date_field_has_text_format"], "dx_date", label="Date of diagnosis",
      valid="date_dmy", note=TEXT_MDC)
# Row 31 — date field with no MDC at all.
dirty(["mdc_date_field_missing"], "surgery_date", label="Date of surgery", valid="date_dmy")
# Row 32 — non-date text field carrying date-format MDC.
dirty(["mdc_text_field_has_date_format"], "referral_source", label="Referred from",
      note=DATE_MDC)
# Row 33 — notes field with no MDC at all.
dirty(["mdc_text_field_missing"], "clinical_summary", ftype="notes", label="Clinical summary")
# Row 34 — row with the wrong number of columns (17, not 18).
dirty(["wrong_column_count"], "short_row_var",
      raw=["short_row_var", "clinical", "", "text", "Row with a missing column",
           "", TEXT_MDC, "", "", "", "", "", "", "", "", "", ""])


NOT_ENGINEERABLE = [
    {"check": "header_column_count",
     "message": "Header has N columns, expected 18",
     "reason": "validate_dd returns immediately after this error, so no other violation on the "
               "file could be observed. Needs a single-purpose fixture file."},
    {"check": "no_data_rows",
     "message": "No data rows found",
     "reason": "Requires a header-only file — mutually exclusive with every row-level check."},
    {"check": "patient_level_hospital_number_missing",
     "message": "--patient-level: required field 'hospital_number' not present",
     "reason": "Mutually exclusive with patient_level_identifier_flag, which needs the field to "
               "be present. Only one of the three --patient-level checks can fire per file."},
    {"check": "patient_level_hospital_number_wrong_type",
     "message": "hospital_number must be type 'text'",
     "reason": "Same row as patient_level_identifier_flag; engineering it too would put two "
               "violations on one row and make hospital_number non-text, which drags in the MDC "
               "checks. One check per row is the fixture's rule."},
]


def build_manifest_checks():
    """Aggregate ENTRIES into {check_name: {severity, match_regex, count, fields, rows}}."""
    checks = {}
    for idx, (cells, names) in enumerate(ENTRIES):
        row_no = idx + 2  # header is row 1; validate_dd numbers data rows from 2
        for name in names:
            meta = CHECK_META[name]
            sev, rx = meta[0], meta[1]
            names_field = meta[2] if len(meta) > 2 else True
            c = checks.setdefault(name, {"severity": sev, "match_regex": rx,
                                         "field_named_in_message": names_field,
                                         "count": 0, "fields": [], "rows": []})
            c["count"] += 1
            c["fields"].append(cells[0])
            c["rows"].append(row_no)
    return dict(sorted(checks.items()))


def main():
    # --- fields.json -------------------------------------------------------
    with open(os.path.join(HERE, "fields.json"), "w") as fh:
        json.dump(FIELDS, fh, indent=2)
        fh.write("\n")

    # --- dirty_datadictionary.csv -----------------------------------------
    with open(os.path.join(HERE, "dirty_datadictionary.csv"), "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(HEADER)
        for cells, _ in ENTRIES:
            w.writerow(cells)

    # --- MANIFEST.json -----------------------------------------------------
    checks = build_manifest_checks()
    default_mode = {k: v for k, v in checks.items() if k != "patient_level_identifier_flag"}
    manifest = {
        "contract_version": 1,
        "synthetic": True,
        "seed": SEED,
        "study": {
            "title": "SYNBUILD — Synthetic Build Study (SYNTHETIC TEST FIXTURE)",
            "purpose": "Database-manager build-task inputs: a clean dd_builder spec and a "
                       "deliberately dirty data dictionary with a known violation set.",
        },
        "fields_json": fields_inventory(),
        "dirty_dd": {
            "file": "dirty_datadictionary.csv",
            "validator": "plugins/argo-database-manager/skills/build-study/validate_dd.py",
            "n_data_rows": len(ENTRIES),
            "row_numbering": "validate_dd numbers the first data row 'Row 2' (header is row 1)",
            "expected_errors_total": sum(c["count"] for c in default_mode.values()
                                         if c["severity"] == "error"),
            "expected_warnings_total": sum(c["count"] for c in default_mode.values()
                                           if c["severity"] == "warning"),
            "checks": default_mode,
            "patient_level_only": {
                "flag": "--patient-level",
                "checks": {k: v for k, v in checks.items()
                           if k == "patient_level_identifier_flag"},
                "note": "With --patient-level these fire IN ADDITION to every check above.",
            },
            "not_engineerable": NOT_ENGINEERABLE,
        },
        "notes": [
            "Every row in dirty_datadictionary.csv is otherwise clean: it carries only the "
            "violations listed for it, so the manifest is an exact expectation, not a floor.",
            "Two rows unavoidably raise two violations each: a select with no choices and a "
            "select with a single choice both also fail the MDC-in-choices check, because MDC "
            "choices cannot exist without pipe-separated options.",
            "fields.json contains no validated Likert/psychometric scale. ARGO practice exempts "
            "those from MDC, but validate_dd.py implements no waiver, so including one would "
            "make the clean fixture fail by design. The sev_grid matrix is a study-authored "
            "severity grid and takes MDC normally.",
            "match_regex values are lowercase, wording-tolerant patterns; tests lowercase the "
            "validator's messages before matching.",
        ],
    }
    with open(os.path.join(HERE, "MANIFEST.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(f"Wrote synthetic-build fixture files to {HERE} "
          f"({len(FIELDS)} fields.json entries, {len(ENTRIES)} dirty DD rows, "
          f"{manifest['dirty_dd']['expected_errors_total']} engineered errors, "
          f"{manifest['dirty_dd']['expected_warnings_total']} engineered warnings)")


if __name__ == "__main__":
    main()
