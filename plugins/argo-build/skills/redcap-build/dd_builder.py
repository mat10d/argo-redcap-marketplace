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
  - text/notes               -> text-format MDC in the Field Note
  - date_dmy/datetime_dmy    -> date-format MDC in the Field Note
Pass mdc=False on a field to opt out (e.g. admin fields like hospital_site);
note that validate_dd.py still requires MDC on radio/dropdown/checkbox, so an
opt-out there will be flagged — keep opt-outs to genuinely exempt fields.

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
        is_first = not self.rows  # first field is the record identifier — never gets MDC
        if mdc and not is_first and type not in EXEMPT_TYPES and var not in EXEMPT_VARS:
            if type in CHOICE_TYPES:
                choices = (choices + " | " + MDC_CHOICES) if choices else MDC_CHOICES
            elif type in ("text", "notes") and not note:
                note = DATE_MDC if valid in ("date_dmy", "datetime_dmy") else TEXT_MDC
        self.rows.append([var, form or self.form, section, type, label, choices, note, valid,
                          min, max, identifier, branching, required, align, qnum, matrix,
                          "y" if matrix and False else "", annotation])

    def write(self, path):
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(self.rows)
        return path


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: python3 dd_builder.py fields.json out.csv")
    spec = json.load(open(sys.argv[1]))
    dd = DD(form=spec[0].get("form", "data") if spec else "data")
    for fld in spec:
        dd.field(**{k: v for k, v in fld.items()})
    out = dd.write(sys.argv[2])
    print(f"wrote {out} ({len(dd.rows)} fields). Now run validate_dd.py on it.")


if __name__ == "__main__":
    main()
