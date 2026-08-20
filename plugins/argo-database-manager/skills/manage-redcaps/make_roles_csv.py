#!/usr/bin/env python3
"""Generate a REDCap-ready roles CSV from a data dictionary.

This is the **CSV-upload** path — the file is uploaded via the REDCap UI:
  User Rights → User Roles → Upload user roles (CSV)

Use this when you don't have / don't want to use the project's API token. The
API-driven sibling is set_roles.py.

Usage:
    python3 make_roles_csv.py <DD_CSV_PATH> [--clinical FORM1,FORM2,...]
                                            [--out OUTPUT_PATH]

If --clinical is omitted, the script applies the same heuristic as set_roles.py:
non-clinical = forms whose names match qa_*, internal_tracking, or admin_*.
Everything else is clinical (gets View+Edit for the Data Entry role).

For single-form studies this is unambiguous and no flag is needed.
"""
import argparse
import csv
import re
import sys
from pathlib import Path

# Columns in the exact order REDCap expects for roles CSV upload.
COLUMNS = [
    "unique_role_name", "role_label",
    "design", "alerts", "user_rights", "data_access_groups",
    "reports", "stats_and_charts", "manage_survey_participants", "calendar",
    "data_import_tool", "data_comparison_tool",
    "logging", "file_repository",
    "data_quality_create", "data_quality_execute",
    "api_export", "api_import",
    "mobile_app", "mobile_app_download_data",
    "record_create", "record_rename", "record_delete",
    "lock_records_customization", "lock_records", "lock_records_all_forms",
    "forms", "forms_export",
]

# Canonical ARGO roles. forms / forms_export use _template strings filled in at runtime.
ROLES = [
    # (label, perm-dict, forms-template, forms-export-template)
    ("Study Builder", {
        "design": 1, "alerts": 1, "user_rights": 1, "data_access_groups": 1,
        "reports": 1, "stats_and_charts": 1, "manage_survey_participants": 1,
        "calendar": 1, "data_import_tool": 1, "data_comparison_tool": 1,
        "logging": 1, "file_repository": 1,
        "data_quality_create": 1, "data_quality_execute": 1,
        "api_export": 1, "api_import": 1,
        "mobile_app": 0, "mobile_app_download_data": 0,
        "record_create": 1, "record_rename": 1, "record_delete": 1,
        "lock_records_customization": 1, "lock_records": 1, "lock_records_all_forms": 1,
    }, "all_full", "all_full"),
    ("Principal Investigator", {
        "design": 0, "alerts": 1, "user_rights": 1, "data_access_groups": 1,
        "reports": 1, "stats_and_charts": 1, "manage_survey_participants": 1,
        "calendar": 1, "data_import_tool": 1, "data_comparison_tool": 1,
        "logging": 1, "file_repository": 1,
        "data_quality_create": 1, "data_quality_execute": 1,
        "api_export": 1, "api_import": 1,
        "mobile_app": 0, "mobile_app_download_data": 0,
        "record_create": 1, "record_rename": 1, "record_delete": 1,
        "lock_records_customization": 1, "lock_records": 1, "lock_records_all_forms": 1,
    }, "all_full", "all_deidentified"),
    ("Project Manager", {
        "design": 0, "alerts": 0, "user_rights": 1, "data_access_groups": 1,
        "reports": 1, "stats_and_charts": 1, "manage_survey_participants": 1,
        "calendar": 1, "data_import_tool": 0, "data_comparison_tool": 0,
        "logging": 1, "file_repository": 1,
        "data_quality_create": 1, "data_quality_execute": 1,
        "api_export": 0, "api_import": 0,
        "mobile_app": 0, "mobile_app_download_data": 0,
        "record_create": 1, "record_rename": 1, "record_delete": 1,
        "lock_records_customization": 0, "lock_records": 0, "lock_records_all_forms": 0,
    }, "all_full", "all_full"),
    ("Data Entry", {
        "design": 0, "alerts": 0, "user_rights": 0, "data_access_groups": 0,
        "reports": 1, "stats_and_charts": 1, "manage_survey_participants": 1,
        "calendar": 1, "data_import_tool": 0, "data_comparison_tool": 0,
        "logging": 0, "file_repository": 1,
        "data_quality_create": 1, "data_quality_execute": 1,
        "api_export": 0, "api_import": 0,
        "mobile_app": 0, "mobile_app_download_data": 0,
        "record_create": 1, "record_rename": 0, "record_delete": 0,
        "lock_records_customization": 0, "lock_records": 0, "lock_records_all_forms": 0,
    }, "clinical_full_qa_readonly", "all_noexport"),
]


def extract_forms_from_dd(dd_path: Path) -> list:
    """Pull unique form names from a REDCap DD CSV, preserving order of first occurrence."""
    seen = []
    with open(dd_path) as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if len(row) < 2:
                continue
            form = row[1].strip()
            if form and form not in seen:
                seen.append(form)
    return seen


def split_clinical(all_forms: list, override: list = None) -> tuple:
    """If override is given, use it. Otherwise apply the qa_*/internal_tracking/admin_* heuristic."""
    if override is not None:
        clinical = [f for f in all_forms if f in override]
        non_clinical = [f for f in all_forms if f not in override]
        return clinical, non_clinical
    non_clinical_patterns = [r"^qa(_|$)", r"^internal_tracking$", r"^admin(_|$)"]
    clinical, non_clinical = [], []
    for f in all_forms:
        if any(re.match(p, f) for p in non_clinical_patterns):
            non_clinical.append(f)
        else:
            clinical.append(f)
    return clinical, non_clinical


def forms_block(template: str, all_forms: list, clinical_forms: list) -> str:
    """Render a forms / forms_export cell as 'form1:level,form2:level,...'."""
    levels = {}
    for f in all_forms:
        if template == "all_full":
            levels[f] = 1
        elif template == "all_deidentified":
            levels[f] = 2
        elif template == "all_noexport":
            levels[f] = 0
        elif template == "clinical_full_qa_readonly":
            if f in clinical_forms:
                levels[f] = 1
            elif f == "qa" or f.startswith("qa_"):
                levels[f] = 2
            else:
                levels[f] = 0
        else:
            raise ValueError(f"Unknown template: {template}")
    return ",".join(f"{f}:{levels[f]}" for f in all_forms)


def build_csv(dd_path: Path, clinical_override: list = None) -> str:
    all_forms = extract_forms_from_dd(dd_path)
    if not all_forms:
        sys.exit(
            f"That file doesn't seem to contain any forms:\n"
            f"    {dd_path}\n"
            "\n"
            "It should be the study's data dictionary, downloaded from REDCap's Data Dictionary\n"
            "page. If you opened and re-saved it in Excel, try downloading a fresh copy."
        )

    clinical, non_clinical = split_clinical(all_forms, clinical_override)

    out = []
    out.append(",".join(COLUMNS))  # header
    for label, perms, ft, fet in ROLES:
        row = {c: "" for c in COLUMNS}
        row["unique_role_name"] = ""    # leave blank — REDCap auto-generates on upload
        row["role_label"] = label
        for k, v in perms.items():
            row[k] = str(v)
        row["forms"] = forms_block(ft, all_forms, clinical)
        row["forms_export"] = forms_block(fet, all_forms, clinical)
        # Quote the forms / forms_export cells because they contain commas
        out.append(",".join(
            f'"{row[c]}"' if c in ("forms", "forms_export") else row[c]
            for c in COLUMNS
        ))

    return "\n".join(out) + "\n", all_forms, clinical, non_clinical


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dd_path", help="Path to the data dictionary CSV")
    ap.add_argument("--clinical", help="Comma-separated list of clinical form names (overrides heuristic)")
    ap.add_argument("--out", help="Output path — normally next to the data dictionary, i.e. "
                                  "database-manager/<study>/ (default: <dd_dir>/<study>_roles.csv)")
    args = ap.parse_args()

    dd_path = Path(args.dd_path).resolve()
    if not dd_path.exists():
        sys.exit(
            f"I couldn't find the data dictionary file:\n"
            f"    {dd_path}\n"
            "\n"
            "This is the CSV describing the study's fields — you can download it from the\n"
            "REDCap project's Data Dictionary page. Check the file name and folder are right."
        )

    clinical_override = None
    if args.clinical:
        clinical_override = [s.strip() for s in args.clinical.split(",") if s.strip()]

    csv_text, all_forms, clinical, non_clinical = build_csv(dd_path, clinical_override)

    out_path = Path(args.out) if args.out else (dd_path.parent / (dd_path.stem.split("_DataDictionary")[0] + "_roles.csv"))
    out_path.write_text(csv_text)

    print(f"\n  Forms detected ({len(all_forms)}): {all_forms}")
    print(f"  Clinical (Data Entry: View+Edit): {clinical}")
    print(f"  Non-clinical (Data Entry: No Access, qa→Read Only): {non_clinical}")
    print(f"\n  Wrote: {out_path}")
    print(f"  Upload via: REDCap → User Rights → User Roles → Upload user roles (CSV)")


if __name__ == "__main__":
    main()
