---
name: manage-redcaps
description: The database manager's home base — watch the core ARGO tracking REDCaps and manage access. (1) See what's outstanding: the open study-build, people, data and linking requests across the trackers, and route each to the right skill. (2) Give someone access to a study: set up the four standard ARGO roles, add people to roles, change which forms someone can see, or copy a role set between studies, then log the request as done. Makes an upload-ready roles file when there is no access key for the study, which is the usual case. Use for "show my outstanding requests", "what's waiting for me", adding or removing someone from a project, or changing rights on a live study. Not for building data dictionaries — see build-study.
allowed-tools: Read, Bash, Write, Edit
---

# manage-redcaps

The database manager's home base. Two jobs: (1) watch the core ARGO tracking REDCaps — what
requests are outstanding and where each one goes; (2) give people the right access to a study —
the four standard ARGO roles on a newly built database, adding someone to a role, changing
which forms they can see, or copying a role set from one study to another.

Distinct from [[build-study]] because the access side operates on **live projects** with real
data — every change has blast radius.

## Task 1 — See what's outstanding

The landing view. Run it whenever the user asks what's waiting, or at the start of any
database-manager session:

```bash
Q=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name open_requests.py 2>/dev/null | head -1)
python3 "$Q"
```

It reads the tracking REDCaps with the five keys everyone holds and prints each queue's open
items with a one-line summary per record (built from each tracker's own data dictionary — no
guessed field names). A queue whose key is missing is reported and skipped, never a blocker.
Present the queues as a short list, then ask **one** question: which one to take. Then route:

| Queue | Fulfil with |
|---|---|
| Studies to build (SIR, with build-step progress shown) | [[build-study]] — enter at the first unticked step |
| People requests (SPR) | Task 2, below |
| Data requests | [[export-data]] |
| Linking requests | [[link-data]] |

`python3 "$Q" --record people <id>` shows one request in full, every filled field by its
label — pull it before starting the fulfilment. Support tickets are shown as a count only
(they're PM triage, not a build queue). When a request is fulfilled, mark its record's
completed box in that tracker on the REDCap website — that's what drains the queue.

## Task 2 — Give someone access

## Before you change anything

Read these — they apply to every operation in this skill:
- [[token-confirmation]] — confirm `project_title` matches user intent before any write
- [[record-id-safety]] — relevant for any operation that also touches records
- [[standard-roles]] — the four canonical ARGO roles (Study Builder, PI, PM, Data Entry)

Multiple projects on the same REDCap instance can share `unique_role_name` values. Modifying the
wrong project is easy and silent. Confirm twice.

## Setting up roles — how to pick, without asking the user

Roles are **Tier 2** ([[access-tiers]]): a study's own project rarely has an access key, because
each one has to be issued by an administrator per person per project
([[project-no-super-token]]).

**Decide it from what's available, then say what you did:**

- **No access key for this study** (the common case) → make the roles CSV (Path A) and tell the
  user the exact REDCap page to upload it on.
- **A key for this study is in the settings file** → use `set_roles.py` (Path B), and report
  which roles were created.

Prefer Path A whenever the user has said they want to eyeball the role grid before it goes live,
or when they're handing the file to a teammate who has no key. Don't put the choice to them
as a question.

### Path A (DEFAULT): CSV upload via the REDCap website

```bash
M=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name make_roles_csv.py 2>/dev/null | head -1)
python3 "$M" <path-to-DD-CSV> [--clinical form1,form2,...] [--out path]
```

Produces a `<study>_roles.csv` file in REDCap's exact upload format. By default it lands next to
the data dictionary — i.e. in `database-manager/<study>/` when the DD was built there.

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

People are then added to those roles in the REDCap UI. We don't know anyone's real REDCap
username, so present who→role as a table for them to work from — don't generate an assignment
file.

#### Access-level codes (used by both paths)

`forms` — what someone can do with a form:

| Value | Meaning |
|---|---|
| 0 | No Access |
| 1 | View & Edit |
| 2 | Read Only |
| 3 | Edit Survey Responses Only |

`forms_export` — what someone can take out of a form:

| Value | Meaning |
|---|---|
| 0 | No Access |
| 1 | Full Data Set |
| 2 | De-Identified |
| 3 | Remove All Identifier Fields |

### Path B: the API (set_roles.py)

Only when a key for this study is already in the settings file.

```bash
set -a; source ~/.argo/.env; set +a
R=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name set_roles.py 2>/dev/null | head -1)
python3 "$R" ARGO_TOKEN_<STUDY>
```

Walks project confirmation → form discovery → clinical/non-clinical split → role preview → write
→ re-export to capture `unique_role_name` values.

## Changing rights on a study that already exists

Same two paths, same rule about which one to use. Whichever you use, the principle is the same:
**start from the current state and preserve everything you weren't asked to change.** REDCap
takes the complete `forms` and `forms_export` picture on an update, not just the parts that
moved — so export what's there now, change the one thing, and put the whole thing back. Then
re-export and confirm the change landed.

Copying a role set from one study to another follows the same shape, plus a form-name mapping
between the two studies. The step-by-step API version of both is in the last section.

## Push to the Study Tracker after roles + users land

Once both the roles CSV is uploaded AND users are assigned to roles in the new REDCap project,
**immediately mark the study's build progress** so the tracker reflects the build state. Use the
Study Tracker step-marking script and flip `user_rights_complete` — see [[build-study]] for the
script and the full per-step push protocol. One push per step, never batched at the end.

If the build is at the point where it's ready for live use, `study_production` is a human go-live
gate: confirm with the responsible person first, then mark it the same way.

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
creation at OAU) → assign each user to a role in the study project (roles section above) → mark
the request done.

**Known gap:** the SPR `study_title` dropdown is still a placeholder ("populate with active
studies"), so the specific study isn't selectable — record it in `account_justification` until that
dropdown is populated.

## Close out the request

When the access is actually in place, mark the request record complete in its tracker (tick
`completed` in the REDCap UI). An unclosed request stays on someone's queue forever.

## When to invoke this skill

- A people request off your request queue
- After [[build-study]] finishes a new DD and the study is ready for users
- Any ad-hoc rights change on a live project

---

## Doing it by hand / debugging

Everything above is the normal path. This section is the raw API underneath it — for debugging a
failed write, or for something the scripts don't cover yet. All calls are `POST` to the REDCap
API URL with the project's access key.

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

### By hand: setting up roles on a new study

1. Confirm the target project (see [[token-confirmation]])
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

### By hand: modifying form access on an existing study

1. Confirm the target project (see [[token-confirmation]])
2. Export current roles to get the full state (form names, access levels, `unique_role_name`)
3. Build the update payload **preserving all existing form access levels**, only changing the specific forms requested
4. REDCap requires the complete `forms` and `forms_export` objects on import — not just changed ones
5. Re-export after import to confirm changes took effect

### By hand: copying roles between studies

1. Export roles from source study (`content=userRole`)
2. Export DD from both source and target to map form names
3. Transform the `forms` / `forms_export` objects to use target form names, preserving access-level patterns
4. Import roles to target — **omit `unique_role_name`** so REDCap auto-generates new IDs
5. Export new roles from target to capture generated IDs
6. Import role mappings (`content=userRoleMapping`) to assign users
