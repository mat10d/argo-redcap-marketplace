#!/usr/bin/env python3
"""
REDCap Data Dictionary Validator

Checks a REDCap data dictionary CSV for common errors that would cause
upload failures. Run before importing into REDCap.

Missing Data Codes are required on every non-exempt field ([[mdc-rules]]). A field
can be waived explicitly by putting `@MDC-EXEMPT` in its Field Annotation column
(on any field of a matrix group, that waives the whole group) — the mechanism for
validated psychometric / Likert scales, which ARGO policy exempts.

Usage: python3 validate_dd.py <path_to_csv>
"""
import csv
import sys
import re

VALID_FIELD_TYPES = {"text", "notes", "radio", "dropdown", "calc", "file",
                     "checkbox", "yesno", "truefalse", "descriptive", "slider"}

VALID_VALIDATION_TYPES = {"date_dmy", "date_mdy", "date_ymd",
                          "datetime_dmy", "datetime_mdy", "datetime_ymd",
                          "datetime_seconds_dmy", "datetime_seconds_mdy", "datetime_seconds_ymd",
                          "email", "integer", "number", "phone",
                          "time_hh_mm_ss", "time", "zipcode", ""}

VALID_IDENTIFIER_VALUES = {"y", "Y", ""}
VALID_REQUIRED_VALUES = {"y", "Y", ""}
VALID_ALIGNMENT_VALUES = {"LV", "LH", "RV", "RH", ""}
VALID_MATRIX_RANKING_VALUES = {"y", "Y", ""}

# Missing Data Code (MDC) constants
# Choice-based MDC fragments expected in radio/dropdown/checkbox choices
CHOICE_MDC_FRAGMENTS = [
    "-666, Patient does not know",
    "-777, Patient refused to answer",
    "-888, Missing in case notes",
    "-999, Other missing",
]
# Date-field MDC pattern in field notes (for date-validated text fields)
DATE_MDC_MARKER = "06-06-6666"
# Text-field MDC marker — matches [-666 or -666 but NOT 06-06-6666
TEXT_MDC_RE = re.compile(r'(?<![\d-])-666')
# Field types that do not need MDC
MDC_EXEMPT_TYPES = {"descriptive", "calc", "file"}
# Forms that are administrative-only (no patient data) — MDC + no-yesno rules don't apply.
# These are tracker forms maintained by the study team, not by patients.
MDC_EXEMPT_FORMS = {
    "internal_tracking", "build_tracking", "study_metadata", "tracking",
    "library_record_id",
}
# Administrative/system variable names exempt from MDC (not patient-reported clinical data)
MDC_EXEMPT_VARS = {"hospital_site", "hospital_number"}  # identifiers set by study team, not MDC-coded
# Explicit per-field MDC waiver, written in the Field Annotation column (dd_builder.py
# writes it when a field is built with mdc=False). ARGO policy exempts validated
# psychometric / Likert instruments from MDC — this is how that exemption is declared,
# visibly, in the dictionary itself. Put it on any field of a matrix group and the whole
# group is exempt. See [[mdc-rules]].
MDC_EXEMPT_ANNOTATION = "@MDC-EXEMPT"

EXPECTED_HEADER = [
    "Variable / Field Name", "Form Name", "Section Header", "Field Type",
    "Field Label", "Choices, Calculations, OR Slider Labels", "Field Note",
    "Text Validation Type OR Show Slider Number", "Text Validation Min",
    "Text Validation Max", "Identifier?", "Branching Logic (Show field only if...)",
    "Required Field?", "Custom Alignment", "Question Number (surveys only)",
    "Matrix Group Name", "Matrix Ranking?", "Field Annotation"
]

COL = {name: i for i, name in enumerate(EXPECTED_HEADER)}


def validate(filepath, patient_level=False):
    errors = []
    warnings = []
    var_names_seen = set()

    with open(filepath, newline='') as f:
        reader = csv.reader(f)
        header = next(reader)

        # Check header
        if len(header) != 18:
            errors.append(f"Header has {len(header)} columns, expected 18")
            return errors, warnings

        rows = list(reader)

    if not rows:
        errors.append("No data rows found")
        return errors, warnings

    # Check first row field type (REDCap uses the first field as the record identifier regardless of name)
    first_type = rows[0][COL["Field Type"]]
    if first_type != "text":
        errors.append(f"Row 2: First field must be 'text' type, got '{first_type}'")

    # --patient-level: hospital_number must exist and be Identifier=y
    # See build-pitfalls.md item #2.
    if patient_level:
        hosp_row = next((r for r in rows if r[COL["Variable / Field Name"]] == "hospital_number"), None)
        if hosp_row is None:
            errors.append("--patient-level: required field 'hospital_number' not present (ARGO standard, see build-pitfalls.md)")
        else:
            if hosp_row[COL["Field Type"]] != "text":
                errors.append("hospital_number must be type 'text'")
            if hosp_row[COL["Identifier?"]] != "y":
                errors.append("hospital_number must have Identifier? = y (PII)")

    # Matrix groups with the MDC waiver on any of their fields — the whole group is exempt.
    mdc_exempt_groups = {
        row[COL["Matrix Group Name"]] for row in rows
        if len(row) == 18 and row[COL["Matrix Group Name"]]
        and MDC_EXEMPT_ANNOTATION in row[COL["Field Annotation"]].upper()
    }

    for i, row in enumerate(rows, 2):
        if len(row) != 18:
            errors.append(f"Row {i}: Has {len(row)} columns, expected 18")
            continue

        var_name = row[COL["Variable / Field Name"]]
        form_name = row[COL["Form Name"]]
        field_type = row[COL["Field Type"]]
        field_label = row[COL["Field Label"]]
        choices = row[COL["Choices, Calculations, OR Slider Labels"]]
        validation = row[COL["Text Validation Type OR Show Slider Number"]]
        identifier = row[COL["Identifier?"]]
        branching = row[COL["Branching Logic (Show field only if...)"]]
        required = row[COL["Required Field?"]]
        alignment = row[COL["Custom Alignment"]]
        matrix_group = row[COL["Matrix Group Name"]]
        matrix_ranking = row[COL["Matrix Ranking?"]]

        # Variable name checks
        if not var_name:
            errors.append(f"Row {i}: Variable name is empty")
        elif var_name[0].isdigit():
            errors.append(f"Row {i}: Variable name '{var_name}' cannot begin with a number")
        elif not re.match(r'^[a-z][a-z0-9_]*$', var_name):
            errors.append(f"Row {i}: Variable name '{var_name}' must be lowercase letters, numbers, and underscores only")
        if len(var_name) > 26:
            warnings.append(f"Row {i}: Variable name '{var_name}' is {len(var_name)} chars (recommended max 26)")

        # Duplicate variable names
        if var_name in var_names_seen:
            errors.append(f"Row {i}: Duplicate variable name '{var_name}'")
        var_names_seen.add(var_name)

        # Form name checks
        if not form_name:
            errors.append(f"Row {i} ({var_name}): Form name is empty")
        elif not re.match(r'^[a-z][a-z0-9_]*$', form_name):
            errors.append(f"Row {i} ({var_name}): Form name '{form_name}' must be lowercase letters, numbers, and underscores, cannot begin with a number")

        # Field type checks
        if field_type not in VALID_FIELD_TYPES:
            errors.append(f"Row {i} ({var_name}): Invalid field type '{field_type}'")
        if field_type == "yesno" and form_name not in MDC_EXEMPT_FORMS:
            errors.append(f"Row {i} ({var_name}): 'yesno' field type cannot hold MDC codes — convert to 'radio' with '1, Yes | 0, No' + MDC choices")

        # Field label check
        if not field_label and field_type != "descriptive":
            warnings.append(f"Row {i} ({var_name}): Field label is empty")

        # Choices required for radio/dropdown/checkbox
        if field_type in ("radio", "dropdown", "checkbox") and not choices:
            errors.append(f"Row {i} ({var_name}): {field_type} field requires choices")

        # Choices should have more than one option (warning)
        if field_type in ("radio", "dropdown") and choices:
            parts = [p.strip() for p in choices.split("|")]
            if len(parts) == 1:
                warnings.append(f"Row {i} ({var_name}): {field_type} has only 1 choice")

        # Validation type checks
        if validation and validation not in VALID_VALIDATION_TYPES:
            errors.append(f"Row {i} ({var_name}): Invalid validation type '{validation}'")

        # Validation only on text fields
        if validation and field_type != "text":
            errors.append(f"Row {i} ({var_name}): Validation type '{validation}' only valid on 'text' fields, not '{field_type}'")

        # Identifier column checks
        if identifier not in VALID_IDENTIFIER_VALUES:
            errors.append(f"Row {i} ({var_name}): Invalid Identifier value '{identifier}' (must be 'y' or blank)")

        # Required column checks
        if required not in VALID_REQUIRED_VALUES:
            errors.append(f"Row {i} ({var_name}): Invalid Required value '{required}' (must be 'y' or blank)")

        # Custom alignment checks
        if alignment not in VALID_ALIGNMENT_VALUES:
            errors.append(f"Row {i} ({var_name}): Invalid Custom Alignment '{alignment}' (must be LV/LH/RV/RH or blank)")

        # Matrix group name checks
        if matrix_group:
            if len(matrix_group) > 60:
                errors.append(f"Row {i} ({var_name}): Matrix group name exceeds 60 characters")
            if not re.match(r'^[a-z0-9_]+$', matrix_group):
                errors.append(f"Row {i} ({var_name}): Matrix group name must be lowercase letters, numbers, and underscores")
            if field_type not in ("radio", "checkbox"):
                errors.append(f"Row {i} ({var_name}): Matrix group fields must be radio or checkbox, not '{field_type}'")

        # Matrix ranking checks
        if matrix_ranking not in VALID_MATRIX_RANKING_VALUES:
            errors.append(f"Row {i} ({var_name}): Invalid Matrix Ranking value '{matrix_ranking}' (must be 'y' or blank)")

        # Branching logic syntax check
        if branching:
            # Check for balanced brackets
            if branching.count('[') != branching.count(']'):
                errors.append(f"Row {i} ({var_name}): Branching logic has unbalanced brackets")
            # Check referenced variables exist (collect for later)
            refs = re.findall(r'\[([a-z0-9_]+?)(?:\([^\)]*\))?\]', branching)
            for ref in refs:
                if ref not in var_names_seen and ref != var_name:
                    warnings.append(f"Row {i} ({var_name}): Branching logic references '{ref}' which hasn't been defined yet (may be a forward reference)")

        # --- Missing Data Code (MDC) checks ---
        # Skip the first field (record identifier) and exempt types
        field_note = row[COL["Field Note"]]
        annotation = row[COL["Field Annotation"]]
        is_first_field = (i == 2)
        # An explicit waiver (on the field, or on its matrix group) exempts it from every
        # MDC check below — that is how validated Likert/psychometric scales stay clean.
        mdc_waived = (MDC_EXEMPT_ANNOTATION in annotation.upper()
                      or (matrix_group and matrix_group in mdc_exempt_groups))
        if (not is_first_field
                and not mdc_waived
                and field_type not in MDC_EXEMPT_TYPES
                and var_name not in MDC_EXEMPT_VARS
                and form_name not in MDC_EXEMPT_FORMS):
            is_date = validation.startswith("date") if validation else False
            is_choice_field = field_type in ("radio", "dropdown", "checkbox")

            if is_choice_field:
                # Choice fields: MDC should be in the choices
                missing_codes = []
                for frag in CHOICE_MDC_FRAGMENTS:
                    if frag not in choices:
                        missing_codes.append(frag.split(",")[0].strip())
                if missing_codes:
                    errors.append(f"Row {i} ({var_name}): {field_type} missing MDC in choices: {', '.join(missing_codes)}")

                # Warn if MDC also appears redundantly in field note
                if field_note and (TEXT_MDC_RE.search(field_note) or DATE_MDC_MARKER in field_note):
                    warnings.append(f"Row {i} ({var_name}): {field_type} has redundant MDC in field note (already in choices)")

            elif field_type in ("text", "notes"):
                # Text/notes fields: MDC should be in the field note
                has_date_mdc = DATE_MDC_MARKER in field_note
                has_text_mdc = bool(TEXT_MDC_RE.search(field_note)) and not has_date_mdc

                if is_date:
                    # Date fields need date-format MDC
                    if not has_date_mdc:
                        if has_text_mdc:
                            errors.append(f"Row {i} ({var_name}): date field has text-format MDC — should use date-format (06-06-6666...)")
                        else:
                            errors.append(f"Row {i} ({var_name}): date field missing date-format MDC in field note")
                else:
                    # Non-date text/notes fields need text-format MDC
                    if has_date_mdc:
                        errors.append(f"Row {i} ({var_name}): {field_type} field has date-format MDC — should use text-format (-666...)")
                    elif not TEXT_MDC_RE.search(field_note or ""):
                        errors.append(f"Row {i} ({var_name}): {field_type} field missing text-format MDC in field note")

    return errors, warnings


def main():
    args = sys.argv[1:]
    patient_level = False
    if "--patient-level" in args:
        patient_level = True
        args = [a for a in args if a != "--patient-level"]
    if not args:
        print("Usage: python3 validate_dd.py [--patient-level] <csv_file> [csv_file2 ...]")
        print("  --patient-level   require hospital_number field (ARGO standard for patient-level DDs)")
        sys.exit(1)

    total_errors = 0
    for filepath in args:
        print(f"\n{'='*60}")
        print(f"Validating: {filepath}  (patient-level: {patient_level})")
        print(f"{'='*60}")

        try:
            errors, warnings = validate(filepath, patient_level=patient_level)
        except FileNotFoundError:
            print(f"  FILE NOT FOUND: {filepath}")
            total_errors += 1
            continue

        if errors:
            print(f"\n  ERRORS ({len(errors)}):")
            for e in errors:
                print(f"    ✗ {e}")
        else:
            print(f"\n  No errors found.")

        if warnings:
            print(f"\n  WARNINGS ({len(warnings)}):")
            for w in warnings:
                print(f"    ⚠ {w}")

        total_errors += len(errors)

    print(f"\n{'='*60}")
    if total_errors == 0:
        print("ALL FILES PASSED VALIDATION")
    else:
        print(f"TOTAL ERRORS: {total_errors}")
    print(f"{'='*60}")
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
