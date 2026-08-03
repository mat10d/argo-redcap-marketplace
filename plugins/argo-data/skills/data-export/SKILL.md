---
name: data-export
description: Export and import records, metadata, files, and audit logs from REDCap projects via the API. The data layer for analysis — pull a cleaned cohort export for downstream tables, figures, or manuscripts.
allowed-tools: Read, Bash, Write, Glob, Edit, Grep
---

# data-export

Read/write to REDCap projects via the REST API. Export records, metadata, files, audit trails; import records and files.

For base API conventions (URL form, token handling) see [[redcap-api]] (argo-core).
For project-identification safety see [[token-confirmation]] and [[record-id-safety]].
For whether this study should have a token at all, see [[access-tiers]] — data-export is **Tier 2**:
occasional, one task at a time, no standing credential.

## Start here: `export.py`

**Use the script, not the `curl` recipes below.** `export.py` handles token lookup, checks the key
opens the project you meant, retries when REDCap is briefly unreachable, and names the output
files consistently. The `curl` snippets further down are kept for debugging by hand and for
operations the script doesn't cover yet — they are not the normal path ([[access-tiers]]).

```bash
set -a; source ~/.argo/.env; set +a

# What does this key open? (reads nothing else)
python3 ${CLAUDE_PLUGIN_ROOT}/skills/data-export/export.py --token-env CRC_TOKEN --info

# The usual thing: records + data dictionary into a dated folder
python3 ${CLAUDE_PLUGIN_ROOT}/skills/data-export/export.py --token-env CRC_TOKEN \
    --out ~/Desktop/crc-export

# Refuse to download unless the key opens the project you expect
python3 ${CLAUDE_PLUGIN_ROOT}/skills/data-export/export.py --token-env CRC_TOKEN \
    --expect-project 77 --out ./crc
```

Useful flags: `--what records|metadata|both`, `--forms a,b,c`, `--raw` (codes instead of labels),
`--expect-project NAME_OR_PID`.

## The default path is the REDCap website, not the API

Most ARGO studies have **no API token** — one has to be issued by a REDCap administrator, per
person, per project, and that rarely happens ([[project-no-super-token]]). So the normal way to
get data out is:

1. Open the study in REDCap in a browser.
2. **Data Exports, Reports, and Stats** → "All data" → export as CSV.
3. **Data Dictionary** page → download as CSV.

Those two files are exactly what [[run-analysis]] and the QA tools expect. Click-by-click instructions, written for someone who doesn't know REDCap's menus: [[getting-files-from-redcap]]. Treat `export.py` as
the shortcut for the studies where a key happens to exist — never as a prerequisite, and never
ask the user to go and get a token before helping them.

**Identifiable data:** REDCap decides what an export contains from the permissions of the account
the key belongs to. Nothing in `export.py` can strip identifiers. For a de-identified extract, the
key must belong to an account whose export rights are set to "De-Identified" — ask the REDCap
administrator, and check the file before sharing it.

## Prerequisites (API path only)

- A REDCap API token with the needed permissions for the target project — optional, see above
- The REDCap API URL (e.g., `https://redcap.oauife.edu.ng/api/`), set once as `REDCAP_URL`

## Exporting records (study data)

### All records, all fields (CSV)
```bash
curl -s -X POST API_URL \
  -d token=TOKEN \
  -d content=record \
  -d format=csv \
  -d type=flat \
  -d rawOrLabel=raw \
  -o output.csv
```

### All records, all fields (JSON)
```bash
curl -s -X POST API_URL \
  -d token=TOKEN \
  -d content=record \
  -d format=json \
  -d type=flat \
  -d rawOrLabel=raw | python3 -m json.tool
```

### Key parameters for record export

| Parameter | Values | Description |
|-----------|--------|-------------|
| `format` | `csv`, `json`, `xml` | Output format |
| `type` | `flat`, `eav` | `flat` = one row per record (standard); `eav` = entity-attribute-value |
| `rawOrLabel` | `raw`, `label` | `raw` = coded values (1, 2, 3); `label` = display labels ("Yes", "No") |
| `rawOrLabelHeaders` | `raw`, `label` | Column headers: variable names vs field labels |
| `exportCheckboxLabel` | `true`, `false` | For checkboxes: export 0/1 or Unchecked/Checked |
| `exportSurveyFields` | `true`, `false` | Include survey timestamp and identifier fields |
| `exportDataAccessGroups` | `true`, `false` | Include the `redcap_data_access_group` column |
| `returnFormat` | `csv`, `json`, `xml` | Format of error messages (not the data itself) |

### Filter by specific records
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=csv -d type=flat \
  -d "records[0]=1" -d "records[1]=2" -d "records[2]=3"
```

### Filter by specific fields
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=csv -d type=flat \
  -d "fields[0]=record_id" -d "fields[1]=first_name" -d "fields[2]=last_name"
```

### Filter by specific forms/instruments
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=csv -d type=flat \
  -d "forms[0]=demographics" -d "forms[1]=baseline"
```

### Filter by events (longitudinal projects)
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=csv -d type=flat \
  -d "events[0]=baseline_arm_1" -d "events[1]=followup_arm_1"
```

### Filter by date range
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=csv -d type=flat \
  -d "dateRangeBegin=2025-01-01 00:00:00" \
  -d "dateRangeEnd=2025-12-31 23:59:59"
```
Note: date range filters on the record's *last modified* timestamp, not on date field values.

### Export with labels instead of codes
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=csv -d type=flat \
  -d rawOrLabel=label -d rawOrLabelHeaders=label
```

### Export a saved report
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=report -d format=csv \
  -d report_id=REPORT_ID -d rawOrLabel=raw
```
Find the report ID in the URL when viewing the report in REDCap, or ask the user.

## Exporting metadata (data dictionary)

### Full data dictionary
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=metadata -d format=csv -o data_dictionary.csv
```

### As JSON (useful for parsing form names, field lists)
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=metadata -d format=json | python3 -m json.tool
```

### Extract just the list of forms
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=metadata -d format=json | \
  python3 -c "import json,sys; print('\n'.join(sorted(set(f['form_name'] for f in json.load(sys.stdin)))))"
```

### Extract just the list of field names
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=metadata -d format=json | \
  python3 -c "import json,sys; print('\n'.join(f['field_name'] for f in json.load(sys.stdin)))"
```

## Exporting project structure

### Instruments / forms list
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=instrument -d format=json | python3 -m json.tool
```

### Events (longitudinal projects)
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=event -d format=json | python3 -m json.tool
```

### Arms (longitudinal projects)
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=arm -d format=json | python3 -m json.tool
```

### Instrument-event mappings (longitudinal projects)
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=formEventMapping -d format=json | python3 -m json.tool
```

### Repeating instruments and events
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=repeatingFormsEvents -d format=json | python3 -m json.tool
```

### Project info (title, creation date, longitudinal status, etc.)
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=project -d format=json | python3 -m json.tool
```

## Exporting files

### Download a file attached to a specific record/field
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=file -d action=export \
  -d record=RECORD_ID -d field=FIELD_NAME -d event=EVENT_NAME \
  -o downloaded_file.pdf
```
`event` is only needed for longitudinal projects. The response is the raw file — use `-o`.

### Download a file from a repeating instance
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=file -d action=export \
  -d record=RECORD_ID -d field=FIELD_NAME -d event=EVENT_NAME \
  -d repeat_instance=2 -o downloaded_file.pdf
```

## Other exports

### Data Access Groups
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=dag -d format=json | python3 -m json.tool
```

### Record count
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=json -d type=flat -d "fields[0]=record_id" | \
  python3 -c "import json,sys; data=json.load(sys.stdin); print(f'{len(data)} records')"
```

### Logging / audit trail
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=log -d format=json \
  -d logtype=record \
  -d beginTime=2025-01-01 -d endTime=2025-12-31 | python3 -m json.tool
```
Log types: `export`, `manage`, `user`, `record`, `lock_record`, `page_view`

### Survey link for a record
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=surveyLink \
  -d record=RECORD_ID -d instrument=FORM_NAME -d event=EVENT_NAME
```

### Survey return code
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=surveyReturnCode \
  -d record=RECORD_ID -d instrument=FORM_NAME -d event=EVENT_NAME
```

### Survey queue link
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=surveyQueueLink -d record=RECORD_ID
```

## Importing data (upload)

> ⚠️ **Migration-only — see [[redcap-api-gotchas]] §0 (no programmatic writes to cohort patient data).**
> Cohort patient records are filled by RAs directly in REDCap, not imported from CSV. The recipes below are for deliberate one-off legacy migrations only (validation ON, human-reviewed decode/categorize preview, snapshot first) — not routine data correction. Admin-REDCap and data-dictionary writes are out of scope of this restriction.

Read [[redcap-api-gotchas]] before writing — date format, overwriteBehavior, choice codes, checkbox-MDC columns, and record_id non-renameability all have hard edges.

### Import records from CSV
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=csv -d type=flat \
  -d overwriteBehavior=normal \
  -d data="$(cat import_data.csv)" \
  -d returnContent=count
```

### Import records from JSON
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=json -d type=flat \
  -d overwriteBehavior=normal \
  -d "data=$(cat import_data.json)" \
  -d returnContent=count
```

### Import parameters

| Parameter | Values | Description |
|-----------|--------|-------------|
| `overwriteBehavior` | `normal`, `overwrite` | `normal` = only overwrite non-blank values; `overwrite` = overwrite all |
| `forceAutoNumber` | `true`, `false` | Auto-number records instead of using provided IDs |
| `returnContent` | `count`, `ids`, `auto_ids` | Return: count of imported records, list of IDs, or auto-generated IDs |

### Upload a file to a record
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=file -d action=import \
  -d record=RECORD_ID -d field=FIELD_NAME \
  -F "file=@/path/to/file.pdf"
```

### Import data dictionary (metadata)
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=metadata -d format=csv \
  -d data="$(cat data_dictionary.csv)" -d returnFormat=json
```

### Legacy free-text → structured multistep migration

When a dictionary redesign replaces one legacy free-text field (e.g. a hidden `address`) with several new structured fields (e.g. `house_number`/`street`/`town`/`state`), migrate the old values with this safety choreography. It follows the [[redcap-api-gotchas]] §0 rule (no programmatic writes to cohort patient data): the API is used only to *read*; the fill is handed off as a CSV for a **manual** import.

1. **Candidate set = source filled AND every target field blank.** Records that already have any new-field data are *excluded entirely* — they are never in the CSV, so a re-run can't disturb prior migration or hand-entry.
   ```python
   NEW = ['house_number','street','town','state']
   cands = [r for r in rows
            if r.get('address','').strip()
            and not any(r.get(f,'').strip() for f in NEW)]
   ```
2. **Deterministic, literal-only split — no inference.** Take what is written; do not "correct" values (e.g. never rewrite a typed state to match geography, and never infer a state that wasn't typed — leave it blank). Slightly-rough splits (a locality landing in `street` vs `town`) are acceptable; silent fabrication is not. An LLM pass tends to over-correct here, which is usually *not* what's wanted for a faithful migration.
3. **Emit only rows with ≥1 non-empty target field.** Drop pure missing-codes (`-777`/`-999` …) — there's nothing to fill.
4. **Second safety net: import with `overwriteBehavior=normal`,** which only writes into blank cells and can never replace an existing value — belt-and-suspenders on top of step 1.
5. **Hand off the CSV for manual import** (REDCap Data Import Tool). Keep a companion audit CSV (`record_id, source_raw, <new fields>`) so every split is traceable to its source string.

```
# upload CSV columns: <record_id_field>, house_number, street, town, state
# import via the Data Import Tool with "overwrite = normal" (leave existing data)
```

## Common workflows

### Quick project overview
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=project -d format=json | python3 -m json.tool
curl -s -X POST API_URL -d token=TOKEN -d content=record -d format=json -d type=flat -d "fields[0]=record_id" | \
  python3 -c "import json,sys; data=json.load(sys.stdin); print(f'{len(data)} records')"
curl -s -X POST API_URL -d token=TOKEN -d content=instrument -d format=json | python3 -m json.tool
```

### Full data dump for analysis
```bash
# Labelled version (human-readable)
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=csv -d type=flat \
  -d rawOrLabel=label -d exportCheckboxLabel=true -d exportDataAccessGroups=true \
  -o full_export_labelled.csv

# Raw coded version (the one to feed analysis pipelines)
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=csv -d type=flat \
  -d rawOrLabel=raw -d exportDataAccessGroups=true \
  -o full_export_raw.csv

# DD for reference
curl -s -X POST API_URL -d token=TOKEN -d content=metadata -d format=csv -o data_dictionary.csv
```

### Compare a remote DD against a local CSV
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=metadata -d format=csv -o remote_dd.csv
diff <(sort remote_dd.csv) <(sort local_dd.csv)
```

### Export data for a single form
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=csv -d type=flat \
  -d "forms[0]=demographics" -d rawOrLabel=label -o demographics.csv
```

## Security

- **Never hardcode API tokens** in scripts or commit them to version control. Use env vars: `export REDCAP_TOKEN=xxx` then `-d token=$REDCAP_TOKEN`.
- API tokens are project-specific and carry the permissions of the user who generated them.
- Exports may contain PHI/PII — handle output files accordingly.
- The `Identifier?` column in the DD flags which fields contain identifiers.

## See also

- [[redcap-api]] (argo-core) — base API conventions
- [[record-id-safety]] — the first DD field is the record ID, not always `record_id`
- [[token-confirmation]] — confirm target project before any write
- [[redcap-api-gotchas]] — write-side traps

Downstream descriptive-table and survival-analysis skills (consumers of these exports) are on the roadmap; for now this skill delivers the cleaned export for analysis in your tool of choice.
