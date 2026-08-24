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

  # (b) CLI from a JSON field spec:
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


class DD:
    def __init__(self, form="data"):
        self.form = form
        self.rows = []

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
        if not is_first and type not in EXEMPT_TYPES and var not in EXEMPT_VARS:
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
    if len(sys.argv) != 3:
        sys.exit(
        "Give me two file names: the field definitions to read, and where to save the data\n"
        "dictionary I build from them. For example:\n"
        "\n"
        "    python3 dd_builder.py fields.json my_study_datadictionary.csv"
    )
    spec = json.load(open(sys.argv[1]))
    dd = DD(form=spec[0].get("form", "data") if spec else "data")
    for n, fld in enumerate(spec, 1):
        try:
            dd.field(**{k: v for k, v in fld.items()})
        except (TypeError, ValueError) as e:
            sys.exit(f"I can't build entry {n} of {sys.argv[1]}: {e}")
    out = dd.write(sys.argv[2])
    print(f"wrote {out} ({len(dd.rows)} fields). Now run validate_dd.py on it.")


if __name__ == "__main__":
    main()
