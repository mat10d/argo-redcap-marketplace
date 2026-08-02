---
name: redcap-admin
description: User rights and role management on live REDCap projects via the API. Use for setting up the four standard ARGO roles on a new study, assigning users, modifying form access on an existing study, or copying roles between studies. Not for building data dictionaries — see redcap-build.
allowed-tools: Read, Bash, Write, Edit
---

# redcap-admin

API-driven administration of REDCap user rights, roles, and role mappings. Distinct from `redcap-build` because this skill operates on **live projects** with real data — every call has blast radius.

## Before any call

Read these — they apply to every operation in this skill:
- [[token-confirmation]] — confirm `project_title` matches user intent before any write
- [[record-id-safety]] — relevant for any operation that also touches records
- [[standard-roles]] — the four canonical ARGO roles (Study Builder, PI, PM, Data Entry)

Multiple projects on the same REDCap instance can share `unique_role_name` values. Modifying the wrong project is easy and silent. Confirm twice.

## API endpoints

All calls are `POST` to the REDCap API URL with the project token.

| Action | Parameters |
|---|---|
| Export user rights | `content=user`, `format=json` |
| Import user rights | `content=user`, `format=json`, `data=[...]` |
| Export user roles | `content=userRole`, `format=json` |
| Import user roles | `content=userRole`, `format=json`, `data=[...]` |
| Export role assignments | `content=userRoleMapping`, `format=json` |
| Import role assignments | `content=userRoleMapping`, `format=json`, `data=[...]` |

### Export user rights
```bash
curl -s -X POST $REDCAP_URL \
  -d token=$TOKEN \
  -d content=user \
  -d format=json | python3 -m json.tool
```

### Import user rights
```bash
curl -s -X POST $REDCAP_URL \
  -d token=$TOKEN \
  -d content=user \
  -d format=json \
  -d "data=[{...user object...}]"
```

## Form access levels

| Value | Meaning |
|---|---|
| 0 | No Access |
| 1 | View & Edit |
| 2 | Read Only |
| 3 | Edit Survey Responses Only |

## Form export levels

| Value | Meaning |
|---|---|
| 0 | No Access |
| 1 | Full Data Set |
| 2 | De-Identified |
| 3 | Remove All Identifier Fields |

## Workflow: Setting up roles on a new study

1. Confirm target token (see [[token-confirmation]])
2. Export the DD to get form names:
   ```bash
   curl -s -X POST $REDCAP_URL -d token=$TOKEN -d content=metadata -d format=json | \
     python3 -c "import json,sys; print(sorted(set(f['form_name'] for f in json.load(sys.stdin))))"
   ```
3. Create the 4 roles via `content=userRole` — see [[standard-roles]] for the canonical JSON payloads. Replace `<all_forms>` / `<clinical_forms>` placeholders with the actual form names from step 2.
4. Export the created roles to get auto-generated `unique_role_name` values.
5. Assign users via `content=userRoleMapping`:
   ```json
   [{"username": "dibernardo", "unique_role_name": "U-XXXXXXXXXX"}]
   ```
6. Optionally assign Data Access Groups for site isolation.
7. Verify by exporting user rights and role mappings back.

## Workflow: Modifying form access on an existing study

1. Confirm target token (see [[token-confirmation]])
2. Export current roles to get the full state (form names, access levels, `unique_role_name`)
3. Build the update payload **preserving all existing form access levels**, only changing the specific forms requested
4. REDCap requires the complete `forms` and `forms_export` objects on import — not just changed ones
5. Re-export after import to confirm changes took effect

## Workflow: Copying roles between studies

1. Export roles from source study (`content=userRole`)
2. Export DD from both source and target to map form names
3. Transform the `forms` / `forms_export` objects to use target form names, preserving access-level patterns
4. Import roles to target — **omit `unique_role_name`** so REDCap auto-generates new IDs
5. Export new roles from target to capture generated IDs
6. Import role mappings (`content=userRoleMapping`) to assign users

## Setting up roles — how to pick, without asking the user

Roles are **Tier 2** ([[access-tiers]]): a study's own project rarely has an API token, because
each one has to be issued by an admin per person per project ([[project-no-super-token]]).

**Decide it from what's available, then say what you did:**

- **No token for this study** (the common case) → make the roles CSV (Path A) and tell the user
  the exact REDCap page to upload it on.
- **Token is in `~/.argo/.env`** → use `set_roles.py` (Path B), and report which roles were created.

Prefer Path A whenever the user has said they want to eyeball the role grid before it goes live,
or when they're handing the file to a teammate who has no API access. Don't put the choice to them
as a question.

### Path A (DEFAULT): CSV upload via REDCap UI (make_roles_csv.py)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/redcap-admin/make_roles_csv.py \
    <path-to-DD-CSV> [--clinical form1,form2,...] [--out path]
```

Produces a `<study>_roles.csv` file (default location: alongside the DD CSV) in REDCap's exact upload format:

```
unique_role_name,role_label,design,alerts,user_rights,data_access_groups,
reports,stats_and_charts,manage_survey_participants,calendar,
data_import_tool,data_comparison_tool,logging,file_repository,
data_quality_create,data_quality_execute,api_export,api_import,
mobile_app,mobile_app_download_data,record_create,record_rename,record_delete,
lock_records_customization,lock_records,lock_records_all_forms,
forms,forms_export
```

The `unique_role_name` column is left blank — REDCap generates project-specific IDs on upload. The `forms` and `forms_export` cells use `form1:level,form2:level,...` syntax (quoted, because of the inner commas).

Then in the UI: **User Rights → User Roles → Upload user roles (CSV)**.

### Path B: API (set_roles.py)

```bash
set -a; source ~/.argo/.env; set +a
python3 ${CLAUDE_PLUGIN_ROOT}/skills/redcap-admin/set_roles.py ARGO_TOKEN_<STUDY>
```

Walks token confirmation → form discovery → clinical/non-clinical split → role preview → POST → re-export to capture `unique_role_name` values. Use this when the project's API token is already in `~/.argo/.env`.

## Push to SIR after roles + users land

Once both the roles CSV is uploaded AND users are assigned to roles in the new REDCap project, **immediately mark the SIR** so the portfolio dashboard reflects the build state:

```bash
python3 .../argo-build/skills/redcap-build/sir_update.py <SIR_RID> --mark-step user_rights_complete
```

If the build is at the point where it's ready for live use, also push:

```bash
python3 .../argo-build/skills/redcap-build/sir_update.py <SIR_RID> \
    --mark-step user_rights_complete \
    --mark-step study_production --status production
```

See [[redcap-build]] for the full per-step push protocol.

## Adding study personnel — the SPR (PID 221)

New users for a study are recorded in the **Study Personnel Request** admin REDCap (**PID 221**),
one record per user. Don't just send a loose account-request message — create the SPR record(s) so
the request is tracked and resolvable.

**Decide this yourself — don't ask the user which way to do it.** Check whether
`STUDY_PERSONELL_REQUEST` is set, then:

- **It is set** (the normal case — this is a Tier 1 admin tracker, [[access-tiers]]) → create the
  records by API import, and tell the user afterwards which records you created.
- **It isn't set** → fill in the SPR survey in the REDCap UI, one submission per user, and tell
  the user that's what needs doing and why.

Either way, report what happened. Never present this as a choice for the user to make.

**One record per user. Key fields + dropdown codes:**
- `redcap_instance` — REDCap to add the user to: `1` OAUTHC, `2` MSKCC (OAU studies → `1`).
- `first_name`, `last_name`, `email`, `whatsapp_phone`
- `institution` — `1` MSKCC, `2` OAUTHC, `3` Other (+ `institution_other`)
- `user_role` — `1` Study/QA Manager, `2` RA, `3` PI, `4` Other (+ `user_role_other`).
  **No "Co-Investigator" option** → use `4` Other with `user_role_other="Co-Investigator"`.
- `account_justification` — name the study here (e.g. "New personnel for HPV self-sampling study,
  SIR 109 / PID 250").
- Triage fields the PM fills: `assigned_to`, `assignment_date`, `completed`, `resolution_date`, `notes`.

**Only request accounts for users who don't already have one** — exclude existing accounts.

**Workflow:** create the SPR record(s) → admin creates the REDCap account(s) (no API for account
creation at OAU) → assign each user to a role in the study project (roles section above) → mark the
SPR record `completed`.

**Known gap:** the SPR `study_title` dropdown is still a placeholder ("populate with active
studies"), so the specific study isn't selectable — record it in `account_justification` until that
dropdown is populated.

## When to invoke this skill

- After `redcap-build` finishes a new DD and the study is ready for users
- For an SPR (Study Personnel Request) needing role assignment on an existing project
- For any ad-hoc rights change on a live project
