#!/usr/bin/env python3
"""dd_builder.py — emit a valid 18-column REDCap data dictionary with MDC applied
by construction, so Path A builds don't round-trip through validate_dd.py.

The hard part of a build is reading the questionnaire and deciding each field's
type/choices/branching — that's the model's job. This helper handles the
*mechanical* part that causes most validator errors: the exact 18-column layout
and applying Missing Data Codes to every non-exempt field per argo-core
mdc-rules (the #1 thing builders forget).

MDC is applied automatically unless the field is exempt:
  - the first field (record identifier) — exempt
  - field types descriptive / calc / file — exempt
  - radio/dropdown/checkbox  -> the four MDC values appended to the choices
  - text/notes with any date/datetime validation -> date-format MDC in the Field Note
  - every other text/notes field -> text-format MDC in the Field Note

A field that already has its own Field Note keeps it: the MDC note is APPENDED to
what you wrote, never substituted for it.

`mdc=False` is the only opt-out, and it is visible in the dictionary — dd_builder
writes `@MDC-EXEMPT` into the Field Annotation column, and validate_dd.py honours
that annotation (on a single field, or on any field of a matrix group, which exempts
the whole group). Use it for validated psychometric / Likert scales, which ARGO
policy exempts; not to dodge MDC on ordinary clinical fields. See [[mdc-rules]].

A self-completed SURVEY carries no MDC at all (ARGO policy, 2026-10-09): MDC records why a
staff member couldn't abstract a value, and a respondent filling in a form has no such reason.
Build it with `DD(survey=True)` (CLI: `--survey`) — no codes, and no `@MDC-EXEMPT` annotations
either, since nothing is being waived — and validate with `validate_dd.py --survey`.

A PATIENT-LEVEL study (individual consented patients) starts with ARGO's standard intake form,
`eligibility_consent`: `redcap_id` (the record ID, "Patient Study ID") and two file uploads for
the signed consent + eligibility checklist and the completed paper questionnaire. Build it with
`DD(patient_level=True)` (CLI: `--patient-level`): the form is written first, and `redcap_id` IS
the record ID, so don't add your own (`exercise_id`, `study_id`...). `hospital_number` comes next,
as the first field of the study's own first form. Surveys and training studies skip all of this.

A patient-level CHILD study also carries one hidden field per parent registry, in the intake form
right after the three standard fields: `parents=[("colorectal_record_id", 77)]` (CLI:
`--parent colorectal_record_id=77`, repeatable). The field holds the patient's record ID in the
parent project; its annotation `@HIDDEN @ARGO-PARENT-PID=77` records which project that is, so
the child says in its own dictionary what it links to. Only the linkage process fills it: no
MDC, never typed by an RA. Established names: `colorectal_record_id` (CRC, PID 77),
`breast_record_id` (Breast, PID 78). Ask Matteo for any other registry's field name.

`yesno` is refused at build time — it cannot hold MDC codes. Use `radio` with
"1, Yes | 0, No" and dd_builder adds the MDC choices for you.

The `Matrix Ranking?` column is always written blank: ARGO does not use REDCap's
ranking matrices and dd_builder has no option to switch one on. A study that needs
ranking has to set that column by hand after the build.

Two ways to use it:

  # (a) importable — write a small build script (recommended for Path A):
  from dd_builder import DD
  dd = DD()
  dd.field("respondent_id", "text", "Record ID")          # first field = record id, no MDC
  dd.field("religion", "radio", "Religion", "1, Christian | 2, Islam | 3, Traditional")
  dd.field("age", "text", "Age (years)", valid="integer")
  dd.write("Study_DataDictionary_2026-06-26.csv")

  # a patient-level study: DD(patient_level=True), then start with hospital_number

  # (b) CLI from a JSON field spec (add --survey for a self-completed survey,
  #     --patient-level for a patient study):
  python3 dd_builder.py fields.json out.csv
  # where fields.json = [{"var": "...", "type": "...", "label": "...", "choices": "...",
  #                       "branching": "...", "section": "...", "valid": "...", ...}, ...]

Always run validate_dd.py on the output before delivering.
"""
import csv
import json
import sys

MDC_CHOICES = ("-666, Patient does not know | -777, Patient refused to answer | "
               "-888, Missing in case notes | -999, Other missing")
TEXT_MDC = ("[-666, Patient does not know  -777, Patient refused to answer  "
            "-888, Missing in case notes  -999, Other missing (add comment for reason missing)]")
DATE_MDC = ("[06-06-6666, Patient does not know  07-07-7777, Patient refused to answer  "
            "08-08-8888, Missing in case notes  09-09-9999, Other missing (add comment for reason missing)]")

HEADER = ["Variable / Field Name", "Form Name", "Section Header", "Field Type", "Field Label",
          "Choices, Calculations, OR Slider Labels", "Field Note",
          "Text Validation Type OR Show Slider Number", "Text Validation Min", "Text Validation Max",
          "Identifier?", "Branching Logic (Show field only if...)", "Required Field?",
          "Custom Alignment", "Question Number (surveys only)", "Matrix Group Name",
          "Matrix Ranking?", "Field Annotation"]

# Written into Field Annotation when a field opts out of MDC (mdc=False).
# validate_dd.py honours it — keep the two spellings identical.
MDC_EXEMPT_ANNOTATION = "@MDC-EXEMPT"

EXEMPT_TYPES = {"descriptive", "calc", "file"}
EXEMPT_VARS = {"hospital_number", "hospital_site"}  # identifiers set by study team, not MDC-coded
CHOICE_TYPES = {"radio", "dropdown", "checkbox"}

# The standard first form of every patient-level ARGO build. validate_dd.py checks for it.
INTAKE_FORM = "eligibility_consent"
PARENT_TAG = "@ARGO-PARENT-PID"  # validate_dd.py reads the same tag
INTAKE_FIELDS = [  # (variable, type, label)
    ("redcap_id", "text", "Patient Study ID"),
    ("patient_consent", "file", "Patient Consent & Eligibility Checklist"),
    ("patient_questionnaire", "file", "Patient Questionnaire"),
]


class DD:
    def __init__(self, form="data", survey=False, patient_level=False, parents=()):
        if survey and patient_level:
            raise ValueError("a study is either a self-completed survey or patient-level, not both")
        if parents and not patient_level:
            raise ValueError("a parent registry link needs a patient-level study (--patient-level)")
        self.form = form
        self.survey = survey
        self.rows = []
        if patient_level:
            for var, ftype, label in INTAKE_FIELDS:
                self.field(var, ftype, label, form=INTAKE_FORM)
            for var, pid in parents:
                self._parent_field(var, pid)

    def _parent_field(self, var, pid):
        if not str(var).endswith("_record_id") or not str(pid).isdigit():
            raise ValueError(f"parent link '{var}={pid}': the field name must end in _record_id "
                             "and the parent must be a REDCap project number, e.g. "
                             "colorectal_record_id=77")
        # Written directly: no MDC and no @MDC-EXEMPT, since nothing is being waived — the
        # linkage process fills this field, never an RA.
        self.rows.append([var, INTAKE_FORM, "", "text",
                          f"Record ID in the parent registry (REDCap project {pid})", "", "", "",
                          "", "", "", "", "", "", "", "", "", f"@HIDDEN {PARENT_TAG}={pid}"])

    def field(self, var, type, label, choices="", note="", valid="", min="", max="",
              identifier="", branching="", required="", section="", align="",
              qnum="", matrix="", annotation="", form=None, mdc=True):
        if type == "yesno":
            raise ValueError(
                f"field '{var}': the REDCap field type 'yesno' can't be used in an ARGO study. "
                "A yes/no field has no room for the missing-data codes ARGO puts on every "
                "clinical field. Use type 'radio' with choices \"1, Yes | 0, No\" instead — "
                "this builder adds the missing-data codes to it for you.")
        is_first = not self.rows  # first field is the record identifier — never gets MDC
        if not is_first and not self.survey and type not in EXEMPT_TYPES and var not in EXEMPT_VARS:
            if mdc:
                if type in CHOICE_TYPES:
                    choices = (choices + " | " + MDC_CHOICES) if choices else MDC_CHOICES
                elif type in ("text", "notes"):
                    # date/datetime validations all take the date-format codes; a custom
                    # Field Note is kept and the MDC note appended to it.
                    mdc_note = DATE_MDC if str(valid).startswith("date") else TEXT_MDC
                    if mdc_note not in note:
                        note = (note + " " + mdc_note) if note else mdc_note
            elif MDC_EXEMPT_ANNOTATION not in annotation.upper():
                # opting out has to be visible in the dictionary itself
                annotation = (annotation + " " + MDC_EXEMPT_ANNOTATION).strip()
        self.rows.append([var, form or self.form, section, type, label, choices, note, valid,
                          min, max, identifier, branching, required, align, qnum, matrix,
                          "", annotation])

    def write(self, path):
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(self.rows)
        return path


def main():
    survey = "--survey" in sys.argv
    patient_level = "--patient-level" in sys.argv
    parents, args = [], []
    it = iter(sys.argv[1:])
    for a in it:
        if a == "--parent":
            var, _, pid = next(it, "").partition("=")
            parents.append((var, pid))
        elif a not in ("--survey", "--patient-level"):
            args.append(a)
    sys.argv = sys.argv[:1] + args
    if len(sys.argv) != 3:
        sys.exit(
        "Give me two file names: the field definitions to read, and where to save the data\n"
        "dictionary I build from them. For example:\n"
        "\n"
        "    python3 dd_builder.py fields.json my_study_datadictionary.csv\n"
        "\n"
        "Add --survey for a questionnaire respondents fill in themselves (no missing-data codes),\n"
        "or --patient-level for a study of consented patients (adds the standard eligibility_consent\n"
        "form first). A child of a registry adds --parent colorectal_record_id=77 (repeatable)."
    )
    spec = json.load(open(sys.argv[1]))
    try:
        dd = DD(form=spec[0].get("form", "data") if spec else "data", survey=survey,
                patient_level=patient_level, parents=parents)
    except ValueError as e:
        sys.exit(f"I can't build this: {e}.")
    for n, fld in enumerate(spec, 1):
        try:
            dd.field(**{k: v for k, v in fld.items()})
        except (TypeError, ValueError) as e:
            sys.exit(f"I can't build entry {n} of {sys.argv[1]}: {e}")
    out = dd.write(sys.argv[2])
    print(f"wrote {out} ({len(dd.rows)} fields). Now run validate_dd.py on it.")


if __name__ == "__main__":
    main()
