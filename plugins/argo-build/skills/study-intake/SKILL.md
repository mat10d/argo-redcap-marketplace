---
name: study-intake
description: The builder's intake gate. Triage a Study Initiation Request (SIR) or Study Personnel Request (SPR) record — pull it, evaluate whether there's enough to build, download attached files, and generate the paste-ready "Create New REDCap Project" value sheet, then proceed to redcap-build. Until a Super API Token is granted, REDCap project creation is manual UI work — this skill prepares every value so the human paste step is trivial. Use when picking up a submitted study request to assess readiness and start a build.
allowed-tools: Read, Bash, Write, Glob, Edit, Grep, Agent
---

# study-intake

Per-ticket triage. Invoked from [[study-portfolio]] once a PM picks a ticket to act on, or directly when a record ID is known. **Migrated** from the prior `~/.claude/skills/study-intake/` (3-step build process and field mapping) into the marketplace structure.

## Why this skill exists

REDCap project creation is a UI form on the OAU REDCap instance — there is no API path without a Super API Token (which ARGO does not currently have). This skill's value is in **preparing the human paste step** so it's mechanical: every field is pre-derived from the SIR record, formatted correctly, and presented as one box you can copy field-by-field.

Email the OAU REDCap admin if a Super Token is desired — once granted, this skill grows a `--auto-create` flag and the entire flow becomes one command.

## End-to-end flow for a single SIR record

```
study-portfolio       picks RID N as next to build
       │
       ▼
study-intake          1. Pull SIR record, validate completeness
                      2. Download attached files (questionnaire, IRB, consent, SOP, ECL)
                         to REDCap/PM/tickets/<RID>/source/
                      3. Generate the Create New Project paste sheet
                         (fill_new_project.py)
                      4. WAIT for user to create project in REDCap UI
                         and add the new token to ~/.argo/.env
       │
       ▼
redcap-build          5. Construct DD from the questionnaire (Path A)
   (argo-build)          → CSV in REDCap/Builds/<study_slug>/
       │
       ▼
USER (REDCap UI)      6. Upload DD CSV via Designer → Data Dictionary
       │
       ▼
redcap-admin          7. set_roles.py against the new project's token
   (argo-build)          → creates 4 standard ARGO roles
       │
       ▼
(manual import)       8. (if applicable) Map source data → import_ready.csv
                         + mapping_report.md walk-through
       │
       ▼
redcap-admin          9. Import data via content=record
   (argo-build)
       │
       ▼
study-intake         10. Set study_production = Yes + mark all 4 forms complete
                         → portfolio dashboard moves it to "done"
                         (one call: sir_update.py <RID> --mark-built)
```

## Step 1: Create New Project (manual UI, scripted prep)

Run:

```bash
set -a; source ~/.argo/.env; set +a
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/fill_new_project.py <RID> [<RID> ...]
```

The script outputs a paste-ready box per RID. It derives:

| Output field | Source / rule |
|---|---|
| Project title | `project_title` (exactly as submitted) |
| Purpose | "Research" if `project_type` starts with research, else "Operational Support" |
| Please specify (sub-category) | Pattern-matched against `project_title + project_description`. See [Sub-category rules](#sub-category-rules) below. Falls back to "(unclear — ask user)". |
| PI First / MI / Last / Email | Verbatim from SIR fields |
| PI Name (cited) | "Surname Initial" format with honorifics stripped (e.g., "DR. FUNMILOLA" → "WURAOLA F") |
| IRB Number | `irb_number` |
| Project Folder | PI surname (or "(decide manually)" if absent) |
| Project Notes | "PI phone number: {pi_whatsapp}" + "IRB approval expires: {DD/MM/YYYY}" |
| Creation option | Always "Empty project (blank slate)" (DD uploads separately in Step 6) |

### Sub-category rules

First match wins. Patterns are case-insensitive regex on `project_title + " " + project_description`.

| Pattern (high-level) | "Please specify" value |
|---|---|
| `biobank`, `repository`, `tissue.bank`, `specimen.collection` | Repository |
| `qualitative`, `interview`, `focus.group`, `survey`, `questionnaire`, `behavioral`, `psychosocial` | Behavioral or psychosocial research study |
| `clinical.trial`, `randomi(s\|z)ed`, `rct`, `phase.[i1234]` | Clinical research study or trial |
| `deep.learning`, `machine.learning`, `ai`, `algorithm`, `diagnostic`, `imaging.classifier` | Translational research 1 |
| `implementation`, `dissemination`, `capacity.building`, `training.evaluation` | Translational research 2 |
| `epidemiolog`, `incidence`, `prevalence`, `cohort.study`, `case.control`, `retrospective.review`, `retroactive.review`, `outcomes.review` | Epidemiology |
| `bench`, `molecular`, `single.cell`, `in.vitro`, `cell.line` | Basic or bench research |

For ambiguous descriptions, the script outputs `(unclear — ask user)` and the user picks during walk-through. See [[decision-protocol]] for when to escalate decisions.

## Step 2: Download attached documents

```bash
# Universal:
sop, eligibility_checklist, quest_univ_file, qa_variables

# Per-institution (loop 1..num_institutions):
irb_file_N, consent_file_N, consent_prof_N, quest_site_N
```

Use `content=file action=export` per field. Save to `REDCap/PM/tickets/<RID>/source/`. The `redcap-build` skill in argo-build picks up from this folder for Path A.

## Step 3: After the user creates the REDCap project

The user pastes the box from Step 1 into REDCap → New Project → submits. The new project gets a PID and an API token. **The user copies that token into `~/.argo/.env`** with a meaningful name, e.g. `ARGO_TOKEN_HPB_HEPATECTOMY`. Re-source.

## Step 4: Upload DD via UI

Designer → Upload Data Dictionary → upload the CSV from `REDCap/Builds/<study_slug>/`. The validator must be clean before this step (handled by `redcap-build`).

## Step 5: Set roles

```bash
python3 .../argo-build/skills/redcap-admin/set_roles.py ARGO_TOKEN_<STUDY>
```

Creates the 4 standard ARGO roles ([[standard-roles]]). Walks token confirmation, clinical/non-clinical form split, role preview, post, verify.

## Step 6: Import data (if applicable)

For studies with historical data to load (e.g., RIDs 17, 18 — hepatectomy + Whipple Excel sheets), map the source data to `import/import_ready.csv` + `mapping_report.md` (a dedicated ingest/harmonization skill is on the roadmap). Walk through the report, then push via `content=record action=import` against the new project token.

## Step 7: Remaining setup (manual, prepared)

After the project exists with DD + data + roles:

| Item | What this skill provides |
|---|---|
| **File Repository uploads** | Filename → folder mapping (Study Documents vs IRB/Ethics) with moniker-rename column ([[feedback-rename-files-with-study-moniker]]). |
| **Weekly Reports** | Spec from `weekly_stat` + `category` SIR fields. User creates report in Reports module. |
| **Personnel assignments** | Who→role table from `pm_name`, `ra_name`, `pi_user_name`, `addl_users` SIR fields ([[feedback-dont-generate-user-assignments-csv]] — table only, not a CSV). |

**Eliminated from per-study build flow** (handled separately, not in MANUAL_SETUP_BRIEF.md):
- Active Databases Excel sheet row — admin/governance, not per-study
- SOP / SIV verification — governance/study-team activity, not a build step

## Step 8: Push build state back to SIR — REQUIRED at each step

**MANDATORY for any build orchestrated by Claude Code.** As each canonical step lands, immediately push the corresponding flag back to the SIR's `build_tracking` form via `sir_update.py`. This keeps the portfolio dashboard accurate in real time, replaces the Active Databases Excel sheet, and means we don't lose track if the build pauses mid-flow.

Do not batch the writes at the end of the build. Push after each step's completion event.

### The 7 build_tracking flags + when to mark each

| Build event → | Mark this field via sir_update.py |
|---|---|
| User reports the new REDCap project's PID (UI step done) | `--pid <PID> --status building --mark-step project_created` |
| DD upload succeeds + validator clean on the new project | `--mark-step dd_uploaded` |
| Roles CSV uploaded AND users assigned (both done) | `--mark-step user_rights_complete` |
| Historical data import succeeded (or marked "Prospective study, not required" for studies with no prior data) | `--set data_imported=1` (imported) or `--set data_imported=2` (prospective) |
| Build reviewed by the marketplace team / Claude before handover | `--mark-step review_internal` |
| Build reviewed and signed off by PM/PI | `--mark-step review_pi` |
| Study moved to In Production (live for data entry) | `--mark-step study_production --status production` |

### Concrete examples

```bash
set -a; source ~/.argo/.env; set +a

# Right after the user creates the project and reports the PID:
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/sir_update.py <RID> \
    --pid 242 \
    --status building \
    --mark-step project_created

# Right after DD is confirmed live on the new project:
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/sir_update.py <RID> \
    --mark-step dd_uploaded

# After both roles + users are in:
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/sir_update.py <RID> \
    --mark-step user_rights_complete

# For a study with historical data import:
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/sir_update.py <RID> \
    --set data_imported=1

# For a prospective study with no historical data:
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/sir_update.py <RID> \
    --set data_imported=2

# When the build is ready for live use:
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/sir_update.py <RID> \
    --mark-step study_production --status production

# Backfill IRB at any point during the build:
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/sir_update.py <RID> \
    --irb-number IPH/OAU/12/3275 --irb-expires 2027-04-16 \
    --mark-step ethical_clearance_obtained

# Document checklist + personnel assignments (study_metadata, any time):
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/sir_update.py <RID> \
    --set biostatistician_assigned="Dr. So-and-so" \
    --set admin_support_assignment="Lawal" \
    --set cancer_type=5 \
    --mark-step sop_uploaded \
    --mark-step consent_sheet

# Move to In Production once all build steps are complete:
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/sir_update.py <RID> --close
# (--close sets study_production=1 AND bumps study_status to 2 = Open to accrual)

# Or use --mark-built to fully close out (all 7 steps + production + all forms Complete):
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/sir_update.py <RID> --mark-built

# Pull a record's full intake + build state (read-only, prints JSON):
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/sir_update.py <RID> --pull > intake.json
```

All flags:
- `--pull` — read-only; prints record JSON to stdout (use as input for downstream skills)
- `--pid PID` — record the new project's PID
- `--status building|accruing|analysis|published|locked|inactive|shelved` (maps to study_status 1–7)
- `--mark-step <field>` — sets a yesno field to "1" (repeatable; canonical 7: project_created, dd_uploaded, user_rights_complete, data_imported, review_internal, review_pi, study_production)
- `--set FIELD=VALUE` — any field (repeatable)
- `--irb-number`, `--irb-expires` — convenience for IRB backfill
- `--close` — set study_production=1 + study_status=2 (Open to accrual)
- `--mark-built` — full completion: all 7 build_tracking steps + study_production=1 + study_status=2 + tracking.completed=Yes + all 4 instrument_complete=2. Use at the very end of a build.
- `--reopen` — undo --close (clears study_production, resets status to 1)

Dates must be YYYY-MM-DD per [[redcap-date-import]] (REDCap requires this format on import regardless of how the field is displayed; see [[redcap-api-gotchas]]). Confirms `project_title` contains "Study Tracker" or "Study Initiation" before any write. Shows current-vs-proposed diff and pauses for user confirmation.

## Bulk backfill — populating SIR from a portfolio spreadsheet

Use `backfill_sir_from_csv.py` to seed SIR from an external portfolio (e.g., a master "active databases" Excel sheet). Designed for one-time migration; subsequent updates should flow through `sir_update.py` per-step.

```bash
set -a; source ~/.argo/.env; set +a
CSV="$ARGO_PM_ROOT/active_dbs_normalized_with_pid.csv"   # your portfolio export

# Dry-run (prints planned writes, no API calls):
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/backfill_sir_from_csv.py --csv "$CSV"

# Smoke-test (1 record):
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/backfill_sir_from_csv.py --csv "$CSV" --commit --limit 1

# Full backfill:
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-intake/backfill_sir_from_csv.py --csv "$CSV" --commit
```

**What it does:**
1. Pulls existing SIR records (titles + record_ids)
2. Loads the portfolio CSV
3. Fuzzy-matches each portfolio row to an existing SIR record (≥0.78 SequenceMatcher ratio) — matched rows become UPDATEs (`overwriteBehavior=normal`, preserves intake data); unmatched become CREATEs (`overwriteBehavior=overwrite`, full payload)
4. Sorts: MSK → UCSF → OAU by PID ascending → no-PID at bucket end
5. Assigns explicit record_ids per the sort

**Mandatory pre-checks before commit:**
- Existing SIR record_ids should be **manually renamed in the REDCap UI** to free up the low record_ids for the backfill (no API exists for record_id rename — see [[redcap-api-gotchas]])
- Source CSV must use the schema in `active_dbs_normalized_with_pid.csv` (29 columns) — field map is in the script
- Any fuzzy matches at borderline ratios should be reviewed manually before commit

**Field translation rules built in:**
- `cancer_type`: label → numeric code (CRC→1, Breast→2, etc.)
- `redcap_location`: OAU/MSK/UCSF → 1/2/3 for `redcap_location_built`
- `source_sheet` → `study_type` (main studies→1 Core ARGO, NCAT→4, surveys→6, etc.)
- IRB expiry free text → parsed into `irb_site_count` + `irb_site_N` + `irb_site_N_expiry` (YYYY-MM-DD), raw kept in `build_notes`
- Excel `study_status` ≥ 2 implies `study_production=1`
- "Inactiveprospective studies" sheet → `study_status=6` (Inactive)

After backfill, mark fully-built studies with `--mark-built` (one call per record) so all 4 instrument-complete flags + tracking.completed land. In-flight (mid-build) records get only the partial build_tracking yes/no's they've achieved.

## Processing Personnel Requests (SPR)

For SPR records, two sub-flows:

### A. Generate admin account request message
For users without REDCap accounts, generate a Slack-ready message grouped by `redcap_instance` (OAUTHC / MSKCC). Template:

```
New REDCap User Account Requests — {OAUTHC | MSKCC}
Please create the following REDCap accounts:
1. First name: {first_name}, Last name: {last_name}, Email: {email}
...
Study: {study title from account_justification or study_title}
```

### B. Assign existing users to project roles
Once accounts exist, use `redcap-admin` (argo-build) → `content=userRoleMapping` to assign users to the right role per `user_role`. Default mapping:
- `pm_name` / `pm_email` → Project Manager
- `ra_name` / `ra_email` → Data Entry
- `pi_user_name` / `pi_user_email` → Principal Investigator
- `addl_users` → parse and ask user for role assignments

## See also
- [[build-pitfalls]] — **READ FIRST.** Consolidated gotchas (admin-PID vs new-PID confusion, honorifics in PI fields, etc.)
- [[study-portfolio]] — weekly dashboard, surfaces tickets for triage
- [[redcap-build]] (argo-build) — DD construction (Path A) and audit (Path B)
- [[redcap-admin]] (argo-build) — role creation + user assignment
- [[token-confirmation]] (argo-core) — always called before any write
- [[record-id-safety]] (argo-core) — relevant for Step 6 imports
- [[decision-protocol]] (argo-core) — walk through judgment calls
- [[project-no-super-token]] — UI path is primary; API is enhancement
