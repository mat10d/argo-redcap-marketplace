#!/usr/bin/env python3
"""Create the four standard ARGO roles on a REDCap project.

Roles created: Study Builder, Principal Investigator, Project Manager, Data Entry.
Canonical role JSON lives in argo-core/references/standard-roles.md and is duplicated
here as STANDARD_ROLES so the script is self-contained.

Usage:
    set -a; source ~/.argo/.env; set +a
    python3 set_roles.py ARGO_TOKEN_HPB_HEPATECTOMY

The script always confirms the target project title before any write. It also asks
the user to confirm the clinical_forms vs all_forms split before posting roles —
not all forms are necessarily clinical (e.g., qa_*, internal_tracking).
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

REDCAP_URL = os.environ.get("REDCAP_URL")

# Canonical ARGO roles. The "forms" / "forms_export" objects use placeholders that
# get filled in at runtime from the target DD's actual form names. Source:
# argo-core/references/standard-roles.md
STANDARD_ROLES = [
    {
        "role_label": "Study Builder",
        "design": 1, "alerts": 1, "user_rights": 1, "data_access_groups": 1,
        "reports": 1, "stats_and_charts": 1, "manage_survey_participants": 1,
        "calendar": 1, "data_import_tool": 1, "data_comparison_tool": 1,
        "logging": 1, "file_repository": 1, "data_quality_create": 1,
        "data_quality_execute": 1, "api_export": 1, "api_import": 1,
        "mobile_app": 0, "mobile_app_download_data": 0,
        "record_create": 1, "record_rename": 1, "record_delete": 1,
        "lock_records_customization": 1, "lock_records": 1, "lock_records_all_forms": 1,
        "_forms_template": "all_full",
        "_forms_export_template": "all_full",
    },
    {
        "role_label": "Principal Investigator",
        "design": 0, "alerts": 1, "user_rights": 1, "data_access_groups": 1,
        "reports": 1, "stats_and_charts": 1, "manage_survey_participants": 1,
        "calendar": 1, "data_import_tool": 1, "data_comparison_tool": 1,
        "logging": 1, "file_repository": 1, "data_quality_create": 1,
        "data_quality_execute": 1, "api_export": 1, "api_import": 1,
        "mobile_app": 0, "mobile_app_download_data": 0,
        "record_create": 1, "record_rename": 1, "record_delete": 1,
        "lock_records_customization": 1, "lock_records": 1, "lock_records_all_forms": 1,
        "_forms_template": "all_full",
        "_forms_export_template": "all_deidentified",
    },
    {
        "role_label": "Project Manager",
        "design": 0, "alerts": 0, "user_rights": 1, "data_access_groups": 1,
        "reports": 1, "stats_and_charts": 1, "manage_survey_participants": 1,
        "calendar": 1, "data_import_tool": 0, "data_comparison_tool": 0,
        "logging": 1, "file_repository": 1, "data_quality_create": 1,
        "data_quality_execute": 1, "api_export": 0, "api_import": 0,
        "mobile_app": 0, "mobile_app_download_data": 0,
        "record_create": 1, "record_rename": 1, "record_delete": 1,
        "lock_records_customization": 0, "lock_records": 0, "lock_records_all_forms": 0,
        "_forms_template": "all_full",
        "_forms_export_template": "all_full",
    },
    {
        "role_label": "Data Entry",
        "design": 0, "alerts": 0, "user_rights": 0, "data_access_groups": 0,
        "reports": 1, "stats_and_charts": 1, "manage_survey_participants": 1,
        "calendar": 1, "data_import_tool": 0, "data_comparison_tool": 0,
        "logging": 0, "file_repository": 1, "data_quality_create": 1,
        "data_quality_execute": 1, "api_export": 0, "api_import": 0,
        "mobile_app": 0, "mobile_app_download_data": 0,
        "record_create": 1, "record_rename": 0, "record_delete": 0,
        "lock_records_customization": 0, "lock_records": 0, "lock_records_all_forms": 0,
        "_forms_template": "clinical_full_qa_readonly",
        "_forms_export_template": "all_noexport",
    },
]


def api_post(token, **params):
    data = urllib.parse.urlencode({"token": token, "format": "json", **params}).encode()
    req = urllib.request.Request(REDCAP_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def api_post_data(token, content, payload):
    """Import via content=... with data=<JSON array>."""
    data = urllib.parse.urlencode({
        "token": token, "format": "json", "content": content,
        "data": json.dumps(payload),
    }).encode()
    req = urllib.request.Request(REDCAP_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode()


def confirm(prompt):
    """Ask before writing. Works whether or not anyone is sitting at a keyboard.

    With no keyboard attached (agent session, scheduled job, cloud runner) there is nobody to
    answer, so waiting would hang forever. Require --yes up front instead.
    """
    if "--yes" in sys.argv or os.environ.get("ARGO_ASSUME_YES") == "1":
        print(f"{prompt} [y/N] y   (--yes was given)")
        return True
    if not sys.stdin.isatty():
        sys.exit(
            f"{prompt}\n"
            "\n"
            "I need you to approve this before writing, but nothing here can accept a typed\n"
            "answer — there's no keyboard attached to this session.\n"
            "\n"
            "Check what's listed above. If it's right, run the same command again with --yes on\n"
            "the end. If you want a different clinical/non-clinical split, pass it explicitly\n"
            "with --clinical form1,form2,... instead of being asked."
        )
    ans = input(f"{prompt} [y/N] ").strip().lower()
    return ans in ("y", "yes")


def split_forms(all_forms):
    """Heuristic: clinical = everything that isn't qa_*, internal_tracking, admin_*."""
    non_clinical_patterns = [r"^qa(_|$)", r"^internal_tracking$", r"^admin(_|$)"]
    clinical, non_clinical = [], []
    for f in all_forms:
        if any(re.match(p, f) for p in non_clinical_patterns):
            non_clinical.append(f)
        else:
            clinical.append(f)
    return clinical, non_clinical


def build_forms_block(template, all_forms, clinical_forms):
    """Translate a _forms_template / _forms_export_template into a {form: level} dict."""
    if template == "all_full":          # View & Edit on everything
        return {f: 1 for f in all_forms}
    if template == "all_deidentified":  # De-identified export
        return {f: 2 for f in all_forms}
    if template == "all_noexport":      # No export
        return {f: 0 for f in all_forms}
    if template == "clinical_full_qa_readonly":
        out = {}
        for f in all_forms:
            if f in clinical_forms:
                out[f] = 1                              # View & Edit
            elif f == "qa" or f.startswith("qa_"):
                out[f] = 2                              # Read Only
            else:
                out[f] = 0                              # No Access (internal_tracking, etc.)
        return out
    raise ValueError(f"Unknown template: {template}")


def materialize_roles(all_forms, clinical_forms):
    """Take STANDARD_ROLES and fill in the _forms_template placeholders."""
    materialized = []
    for r in STANDARD_ROLES:
        role = {k: v for k, v in r.items() if not k.startswith("_")}
        role["forms"] = build_forms_block(r["_forms_template"], all_forms, clinical_forms)
        role["forms_export"] = build_forms_block(r["_forms_export_template"], all_forms, clinical_forms)
        materialized.append(role)
    return materialized


def main():
    if not REDCAP_URL:
        sys.exit(
        "This tool needs to know the web address of your REDCap system before it can do\n"
        "anything, and that address isn't set on this computer yet.\n"
        "\n"
        "It's a single line of text ending in /api/ — ask your ARGO REDCap administrator for it\n"
        "if you don't have it. Add it to the file ~/.argo/.env like this:\n"
        "\n"
        "    REDCAP_URL=https://your-redcap-site.org/api/\n"
        "\n"
        "then load it into this terminal window and try again:\n"
        "\n"
        "    set -a; source ~/.argo/.env; set +a"
    )
    # Flags are handled by hand here (this script predates argparse use in the suite).
    # --clinical lets a caller state the split up front, so nothing has to be typed mid-run.
    argv = sys.argv[1:]
    clinical_override = None
    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--yes":
            pass  # read directly by confirm()
        elif arg == "--clinical" and i + 1 < len(argv):
            i += 1
            clinical_override = [f.strip() for f in argv[i].split(",") if f.strip()]
        elif arg.startswith("--clinical="):
            clinical_override = [f.strip() for f in arg.split("=", 1)[1].split(",") if f.strip()]
        elif arg.startswith("-"):
            sys.exit(
                f"I don't recognise the option {arg!r}.\n"
                "\n"
                "The options are:\n"
                "    --yes                    approve the changes without being asked\n"
                "    --clinical form1,form2   say which forms are clinical, instead of being asked"
            )
        else:
            positional.append(arg)
        i += 1

    if len(positional) != 1:
        sys.exit(
        "Tell me which study to set the roles up on, by naming the setting that holds its\n"
        "access key. For example:\n"
        "\n"
        "    python3 set_roles.py CRC_TOKEN\n"
        "\n"
        "If you don't have an access key for the study, you don't need one — run\n"
        "make_roles_csv.py instead and upload the file it makes through the REDCap website."
    )

    env_var = positional[0]
    token = os.environ.get(env_var)
    if not token:
        sys.exit(
        f"No access key for {env_var} is set up on this computer, so I can't reach REDCap.\n"
        "\n"
        "An access key (REDCap calls it an API token) is a long password that lets a tool read\n"
        "or update one specific REDCap project on your behalf. Your REDCap administrator\n"
        "creates it for you — it isn't something you can generate yourself.\n"
        "\n"
        "If you already have one, add it to the file ~/.argo/.env, then load it into this\n"
        "terminal window and try again:\n"
        "\n"
        "    set -a; source ~/.argo/.env; set +a"
    )

    # --- Step 1: confirm project ---
    info = api_post(token, content="project")
    print(f"\n  Target project")
    print(f"  ───────────────")
    print(f"  title:      {info.get('project_title')}")
    print(f"  pid:        {info.get('project_id')}")
    print(f"  purpose:    {info.get('purpose_other') or info.get('purpose')}")
    print(f"  access key ending: ...{token[-4:]}")
    if not confirm("\nIs this the project you want to set roles on?"):
        sys.exit("Aborted by user.")

    # --- Step 2: get form names ---
    metadata = api_post(token, content="metadata")
    all_forms = sorted({f["form_name"] for f in metadata})
    record_id_field = metadata[0]["field_name"]
    print(f"\n  Record ID field: {record_id_field}")
    print(f"  Forms ({len(all_forms)}):")
    for f in all_forms:
        print(f"    - {f}")

    # --- Step 3: clinical vs non-clinical split ---
    if clinical_override is not None:
        clinical = clinical_override
        non_clinical = [f for f in all_forms if f not in clinical]
        unknown = [f for f in clinical if f not in all_forms]
        if unknown:
            sys.exit(
                f"These form names aren't in this study: {', '.join(unknown)}\n"
                "\n"
                f"The study's forms are: {', '.join(all_forms)}\n"
                "\n"
                "Check the spelling and try again — form names are the short internal ones, not\n"
                "the titles shown to data entry staff."
            )
        print(f"\n  Using the clinical/non-clinical split you supplied:")
        print(f"    clinical:     {clinical}")
        print(f"    non-clinical: {non_clinical}")
    else:
        clinical, non_clinical = split_forms(all_forms)
        print(f"\n  Proposed clinical/non-clinical split (Data Entry role gets View+Edit on clinical, Read Only on qa):")
        print(f"    clinical:     {clinical}")
        print(f"    non-clinical: {non_clinical}  (Data Entry → No Access, except qa → Read Only)")
        if not confirm("\nUse this split?"):
            manual = input("Comma-separated list of CLINICAL form names (others will be non-clinical): ").strip()
            clinical = [f.strip() for f in manual.split(",") if f.strip()]
            non_clinical = [f for f in all_forms if f not in clinical]
            print(f"\n  Updated clinical:     {clinical}")
            print(f"  Updated non-clinical: {non_clinical}")

    # --- Step 4: show what will be posted ---
    roles = materialize_roles(all_forms, clinical)
    print(f"\n  About to create {len(roles)} roles. Per-role form access summary:\n")
    for r in roles:
        print(f"  ── {r['role_label']} ──")
        print(f"     design={r['design']} api_import={r['api_import']} api_export={r['api_export']} record_delete={r['record_delete']}")
        print(f"     forms:        {r['forms']}")
        print(f"     forms_export: {r['forms_export']}")
        print()
    if not confirm("Post these roles to the project?"):
        sys.exit("Aborted by user — no changes made.")

    # --- Step 5: post ---
    resp = api_post_data(token, "userRole", roles)
    print(f"\n  Server response: {resp}")

    # --- Step 6: re-export to get unique_role_name values ---
    created = api_post(token, content="userRole")
    print(f"\n  Roles now on project (re-exported):")
    for r in created:
        print(f"    {r.get('unique_role_name'):20s}  {r.get('role_label')}")
    print(f"\n  Done. Use the unique_role_names above to assign users via content=userRoleMapping.")


if __name__ == "__main__":
    main()
