---
name: redcap-build
description: Build or audit a REDCap data dictionary. One skill, two directions — Path A constructs a DD CSV from a Word questionnaire; Path B reviews and corrects an existing DD CSV against its Word source. Use for de novo builds, review/audit, or any DD correction work. For user rights / role assignment, use redcap-admin instead.
allowed-tools: Read, Bash, Write, Glob, Edit, Grep
---

# redcap-build

One skill covers both directions of data-dictionary work because building and verifying require the same expertise applied in reverse. Pick a path based on what's in the working directory:

- **Path A (build)** — Word doc present, no CSV → construct the DD
- **Path B (verify)** — CSV already exists → audit and correct against the Word source

If the user says "review", "audit", "check", or "fix", use Path B regardless of what's in the directory.

## Shared references (from argo-core)

All MDC rules, role definitions, DD column specs, and API safety conventions live in `argo-core/references/` and are linked here. Do not restate them in this skill.

- [[build-pitfalls]] — **READ FIRST.** Consolidated gotchas from real ARGO builds.
- [[mdc-rules]] — Missing Data Code conventions by field type
- [[dd-column-spec]] — Full 18-column DD CSV reference, field types, validation, branching syntax, annotation tags
- [[record-id-safety]] — Record ID field is not always `record_id`
- [[token-confirmation]] — Confirm target project before any API write
- [[redcap-date-import]] — Import format YYYY-MM-DD vs display DD-MM-YYYY
- [[redcap-api-gotchas]] — Write-side traps: date format, overwriteBehavior, choice codes, record_id non-renameability

---

# Invocation from a SIR record

When kicked off from `study-intake` (or by hand), the build skill operates on one **SIR record_id** — the record that came from an investigator's submission to the Study Initiation Request form. All study inputs live on that record's `study_initiation_request` form (97 fields); all build-progress writes go back to the same record's `build_tracking` form; long-term state lands on `study_metadata`.

## Pull the SIR record

```bash
set -a; source ~/.argo/.env; set +a
python3 .../argo-pm/skills/study-intake/sir_update.py <SIR_RID> --pull > intake.json
```

`--pull` returns the full record (intake + build_tracking + study_metadata) as JSON. Use this as the canonical input — do not re-ask the user for anything the intake already captured.

## Map intake fields → build decisions

| Intake field(s) | Drives |
|---|---|
| `project_title`, `pi_*`, `irb_number`, `irb_approval_expires`, `review_status` | Step 1 — Main project settings |
| `quest_universal`, `quest_univ_file`, `quest_site_1..10` | Step 2 input — questionnaire source for Path A |
| `missing_data_codes` (checkbox) | Step 2 — which MDCs to apply per [[mdc-rules]] |
| `data_collection` (dropdown) | Drives `data_imported` decision (retrospective vs prospective) |
| `num_institutions`, `inst_name_*`, `irb_file_*`, `consent_file_*`, `consent_prof_*`, `sop`, `eligibility_checklist` | Step 1 — File Repository uploads (rename with study moniker before upload) |
| `weekly_stat`, `category` | Weekly reports config (substep of DD) |
| `pm_name`/`pm_email`, `ra_name`/`ra_email`, `pi_user_name`/`pi_user_email`, `addl_users` | Step 3 — User rights (Who→Role table) |
| `qa_variables` | QA cohort prep |

## Loop: build a step, then push

After each build step lands in the new REDCap project, immediately push to SIR before moving on:
```bash
python3 .../argo-pm/skills/study-intake/sir_update.py <SIR_RID> --mark-step <field_name>
```
where `<field_name>` is one of the 7 yes/no `build_tracking` fields (see checklist below). The push step is non-batchable per [[feedback-push-sir-each-step]].

---

# Path A: De Novo Build (Word to DD CSV)

## Workflow
1. Find the Word document with `Glob *.docx`
2. Extract text: `textutil -convert txt -stdout "filename.docx"`
3. Parse the structure (patterns below)
4. Generate CSV with all 18 columns (see [[dd-column-spec]])
5. Save the CSV in the same directory: `ProjectName_DataDictionary_YYYY-MM-DD.csv`
6. Validate: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/redcap-build/validate_dd.py <csv_file>` — fix all errors before delivering

## Parsing the Word document

### Instrument detection
- Pattern: `Instrument N – Name` or `Instrument N (Survey) – Name`
- form_name = name lowercased with underscores
- Example: "Instrument 1 – Awardee Details" -> `awardee_details`

### Field detection
- Fields appear as bullet points with labels
- Sub-bullets indicate dropdown/radio options
- Cues:
  - `(Required)` -> Required Field = `y`
  - `(Select Year)` / `(Select ... from dropdown)` -> `dropdown`
  - `File Upload` in label -> `file`
  - Yes/No only -> `radio` with `1, Yes | 0, No` + MDC (never `yesno` — cannot hold MDC)
  - Multiple options -> `radio` (up to 5) or `dropdown` (more)
  - Paragraph descriptions -> `notes`
  - Short answer -> `text`

### Branching logic detection
- `Yes -> follow-up text` shows only when parent = Yes: `[parent_field] = '1'`
- `Other... (Input Answer)` shows when Other is selected
- Use REDCap syntax (see [[dd-column-spec]] for full reference)

### Section headers
- Sub-sections WITHIN a form only — not for the first field
- Do not use the instrument name as a section header
- Only when the Word doc has explicit sub-groupings

### Field labels — CRITICAL
- Must match the Word document text EXACTLY
- No paraphrasing, summarizing, or modifying
- Preserve exact wording, punctuation, capitalization

### Rich text for complex labels
When a question has bullet-point sub-items, format using HTML:
```html
<div class="rich-text-field-label"><p>Main question:</p> <ul> <li>Sub item 1</li> <li>Sub item 2</li> </ul></div>
```
Escape inner double quotes as `""` in the CSV.

### Variable naming
- snake_case, lowercase, no punctuation
- Common abbreviations: PI -> `pi`, Institution -> `institution`/`inst`, Date -> `date`
- Under 26 characters when possible
- Prefix with context if ambiguous (`midterm_pi_first` vs `final_pi_first`)

### Identifier flags
Set `Identifier? = y` for: emails, phone numbers, bank details, names (when PII), DOB, addresses. See [[dd-column-spec]] for full list.

## Output
Save at `<ProjectName>_DataDictionary_<YYYY-MM-DD>.csv`. The first field is the record identifier — give it a meaningful name (`registry_id`, `study_id`, etc.). See [[record-id-safety]].

## Push to SIR after upload

After the DD is uploaded to the new REDCap project AND validates clean, **immediately mark the SIR**:

```bash
python3 .../argo-pm/skills/study-intake/sir_update.py <SIR_RID> --mark-step dd_uploaded
```

If this is the first action after project creation, also push the new PID + project_created flag:

```bash
python3 .../argo-pm/skills/study-intake/sir_update.py <SIR_RID> \
    --pid <NEW_PID> --mark-step project_created --mark-step dd_uploaded
```

The mark-step values map 1:1 to `build_tracking` yes/no fields on SIR (see "Canonical per-study build checklist" below). See [[study-intake]] for the full per-step push protocol.

## ARGO-standard fields (include in every patient-level DD)

These are not in the Word questionnaire but ARGO convention requires them. Add them when building Path A; the validator does not enforce their presence (yet), so it's on the builder to remember:

| Field | Position | Type | Identifier? | Why |
|---|---|---|---|---|
| `<study>_id` (e.g., `hepatectomy_id`) | 1st (record ID) | text | no | Per [[record-id-safety]] — first field is always the record identifier |
| `hospital_number` | 2nd | text | **y** | Patient identifier across ARGO studies. Source data often lacks it (e.g., retrospective DBs); leave blank, Alatise's team or equivalent backfills later. |

Studies that are explicitly **non-patient-level** (training programs, research-capacity surveys, biobank specimen tracking without patient linkage) may skip `hospital_number` — document the deviation in the Active Databases sheet.

## Canonical per-study build checklist

The build workflow maps 1:1 to `build_tracking` fields on the SIR record. Each step closes with `sir_update.py --mark-step <name>` (per the "push SIR each step" rule).

| # | `build_tracking` field | What lands | Notes |
|---|---|---|---|
| 1 | `project_created` | New REDCap project exists; PID known | Push PID via `sir_update.py --pid <NEW_PID> --mark-step project_created`. Project settings (title, purpose, PI, IRB) drawn from the SIR intake form (see "Invocation from a SIR record" above) |
| 2 | `dd_uploaded` | Validator-clean DD live on new project | Covers the questionnaire build (Path A), MDCs (per [[mdc-rules]]), hospital_number, file-import fields, and any rich-text labels. All folded into the DD, not separate steps. |
| 3 | `user_rights_complete` | Roles CSV uploaded + users assigned via UI | See `redcap-admin` skill. Who→Role rendered as a table — no user-assignment CSV per [[feedback-dont-generate-user-assignments-csv]] |
| 4 | `data_imported` | Radio: `1` = historical data imported; `2` = prospective, N/A | Only relevant if intake's `data_collection` indicates retrospective data exists |
| 5 | `review_internal` | Internal QA pass on built project | |
| 6 | `review_pi` | PM/PI sign-off | |
| 7 | `study_production` | Project moved to Production status in REDCap | Final flag — portfolio dashboard treats this as "done" |

Substeps folded into step 2 (DD): MDCs, hospital_number, weekly_reports config (per SIR's `weekly_stat` / `category`), file-import fields. File Repository uploads (IRB, consent, SOP, questionnaire from intake's `irb_file_*`/`consent_file_*`/`sop`/`quest_*` fields) are part of step 1's project setup — rename with study moniker per [[feedback-rename-files-with-study-moniker]] before upload.

Long-term study state (cancer_type, funding, IRB expiries, personnel) lands on the `study_metadata` form — not part of the per-build flow; set once at production and maintained over the study lifecycle.

**Not in per-study build flow** (admin/governance, handled separately):
- SOP / SIV verification
- Active Databases is deprecated — that metadata now lives on `study_metadata` (see [[feedback-active-dbs-deprecated]])

The `MANUAL_SETUP_BRIEF.md` generated by `study-intake` for each build walks through these in order with file paths and pre-filled values pulled from the SIR record. See [[study-intake]].

## Example
Word:
```
Instrument 1 – Contact Information
- Email Address
- Phone Number
- Institution (Select from dropdown)
  - Hospital A
  - Hospital B
  - Other... (Input Answer)
- Other Institution (specify)
```

CSV:
```
email_address,contact_information,,text,"Email Address",,,email,,,y,,,,,,,
phone_number,contact_information,,text,"Phone Number",,,,,,y,,,,,,,
institution,contact_information,,dropdown,Institution,"1, Hospital A | 2, Hospital B | 3, Other",,,,,,,,,,,,
institution_other,contact_information,,text,"Other Institution (specify)",,,,,,,"[institution] = '3'",,,,,,
```

---

# Path B: Review / Audit (DD CSV to corrected DD CSV)

## Workflow
1. Run the validator:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/redcap-build/validate_dd.py <csv_file>
   ```
   Record all errors and warnings.
2. Extract the Word source (if available): `textutil -convert txt -stdout "source.docx"`
3. Read the full CSV and compare field-by-field against the Word doc.
4. Categorize findings (see below).
5. Present to the user, await confirmation.
6. Apply fixes via Edit. **Justify each change** — cite Word doc text, validator rule, or logic that motivates it. No silent edits.
7. Re-run the validator until clean.

## What to check

### Structural
- Duplicate fields (same question, different variable names)
- Missing fields (in Word, not in CSV)
- Extra fields (in CSV, not in Word — may be intentional, flag for user)
- Wrong form assignment

### Choices and values
- Choice value mismatches (Word says `0. No`, CSV says `2, No`)
- Missing choice options
- Wrong choice labels

### Missing Data Codes
See [[mdc-rules]] for the authoritative table. Common failure modes:
- Missing MDC suffix on radio/dropdown/checkbox choices
- Wrong MDC format on date fields (must use date-format codes, not numeric)
- `yesno` field type anywhere — convert to `radio` with `1, Yes | 0, No` + MDC
- MDC applied to exempt fields (descriptive/calc/file or admin fields like `hospital_site`)

### Prohibited field types
`yesno` must be converted to `radio` (cannot hold MDC). See [[mdc-rules]].

### Branching logic
- Missing branching on conditional fields
- References to non-existent variables
- Choice code mismatches (`= '39'` when the choice is coded `49`)

### Identifier flags
Names, DOB, phone, email, addresses must have `Identifier? = y`.

### Label accuracy
Labels must match the Word doc EXACTLY. Watch for paraphrasing.

### Variable naming
- Typos (`nonmodal` vs `nonnodal`)
- Length over 26 chars (warning, not blocking)

### Sister-study consistency (Path B-only check)
When a build folder contains **sister studies** (same PI, same HREC/protocol, two separate SIRs for different procedures or arms), the instrument structure must match across them. Word proformas can have different visual organization that misleads parallel build agents into picking different instrument vs. section structures.

Examples encountered: RIDs 17 (Hepatectomy) + 18 (Whipple) both under HREC `IPH/OAU/12/3275` — the parallel agents produced 1-instrument vs 6-instrument structures respectively. Reconciled to 5 instruments each.

When auditing, run `make_roles_csv.py` on both DDs; if the `Forms detected` lists differ in shape (single vs multi), flag for the user.

## Report format
Categorize by severity:
- **CRITICAL** — will cause import failure or data loss (validator errors, duplicate variables)
- **ERROR** — will cause incorrect behavior (wrong branching, missing MDC, choice mismatches)
- **WARNING** — non-blocking but should be fixed (long variable names, missing identifiers)

---

# Where this fits in the full study build

This skill covers the questionnaire build (the `dd_uploaded` step) and any review/correction of the resulting DD. See the **Canonical per-study build checklist** above for the full 7-step `build_tracking` workflow. When invoked from `argo-pm/study-intake`, the intake skill orchestrates the steps and calls back to this skill for the DD step.
