---
name: export-data
description: Fulfil a data request — get a study's records and its data dictionary out of REDCap and onto disk as files someone can actually work with. Downloads them directly with the study's access key; when there isn't one yet it offers to add it to your settings file, and falls back to click-by-click website instructions if a key can't be had. Use when taking a data request off your request queue, when someone asks for an export or "the data", or when you need a clean cohort export before analysis, tables or a manuscript. Analysing the export itself is run-analysis.
allowed-tools: Read, Bash, Write, Glob, Edit, Grep
---

# export-data

Get a study's records and its data dictionary out of REDCap and onto disk. Your entry point is
your request queue — say "show my outstanding requests" and pick the data request you're
fulfilling. That record says *what was asked for and by whom*, and it is the thing you tick when
you're done; it does not say which project to pull from or which key opens it. Once you're
exporting, the trackers are out of the picture (see below).

For base API conventions (URL form, key handling) see [[redcap-api]] (argo-core).
For project-identification safety see [[token-confirmation]] and [[record-id-safety]].
Studies you're assigned to may already have an access key in your settings file — if one is
there, use it. If there isn't one yet, offer to put the settings file on screen so they can add
it (below), and fall back to the website download only if they can't get a key ([[access-tiers]]).

## Ask which study, and where the files go

Don't infer the study from whatever happens to be in the folder. If the user hasn't said which
study they mean, **ask — one question.** If you already looked and found something plausible,
name it and confirm in that same question ("the request says the CRC cohort — is that
`database-manager/exports/crc`?"). Two studies in one workspace look alike from the outside, and
a synthetic or test export looks exactly like the real thing.

The same applies to files coming the other way: if they've downloaded an export by hand, ask
where they put it rather than picking the closest-looking CSV.

### The key identifies the study. Nothing else does.

**Do not open the Study Tracker or SIR records during an export — they are irrelevant to pulling
data.** The trackers are ARGO's bookkeeping: they hold no access keys, and no tracker can say
which REDCap project a given key opens. Only `export.py --info` can, because only REDCap knows.

So when the user says "the CRC data", the question is *which access key*, not *which tracker
record*. Look in the settings file for a key whose name matches; run `--info` on it and read back
the project name and number it actually opens. If there is no key for the study, **ask the user
which project they mean and solicit the key** (next section) — do not go looking for the answer
in the trackers, and never probe other keys to find out which one fits.

## `export.py` is the only path

**Run `export.py`. Never hand-roll the export.** Not a `python3 -c` snippet, not a
`RedcapClient` call you write yourself, not `urllib`/`requests`, not a `curl` you assemble from
the reference below. The one time an agent improvised a snippet it built a malformed `fields`
parameter and put a raw traceback in front of the user.

`export.py` finds the key, confirms the key opens the project you meant, retries when REDCap is
briefly unreachable, names the output files consistently, and fails in plain language rather than
in a traceback. Those are exactly the things a hand-written call leaves out.

**And never go looking for a project through the API.** There is no "list my projects" call worth
improvising — a key opens exactly one project, and `--info` says which. If you're not sure which
study is meant, ask the user; don't probe keys to find out.

`--token-env` takes the *name of the setting* that holds your access key for this study — the key
itself stays in the settings file and is never typed into a command. The script loads the
settings file by itself; there is nothing to `source` first.

```bash
E=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name export.py 2>/dev/null | head -1)

# What does this key open? (reads nothing else)
python3 "$E" --token-env CRC_TOKEN --info

# The usual thing: records + data dictionary into a dated folder
python3 "$E" --token-env CRC_TOKEN --out database-manager/exports/crc

# Refuse to download unless the key opens the project you expect
python3 "$E" --token-env CRC_TOKEN \
    --expect-project 77 --out database-manager/exports/crc
```

Useful flags: `--what records|metadata|both`, `--forms a,b,c`, `--only-raw`, `--only-labelled`,
`--expect-project NAME_OR_PID`.

### What one run produces

**The whole set, every time.** There is no encoding to choose up front, because choosing it
means knowing what you'll need before you've looked:

| File | What it is | Give it to |
|---|---|---|
| `<slug>_datadictionary_<date>.csv` | the field list, with choice codes and the `Identifier?` flags | everything |
| `<slug>_records_raw_<date>.csv` | codes (`1`, `2`) | **[[run-analysis]] and the QA tools — this is the one they read** |
| `<slug>_records_labelled_<date>.csv` | the same records, labels (`Male`) | a human reading by eye |
| `<slug>_records_deidentified_raw_<date>.csv` | raw, minus every field the dictionary flags as an identifier | the one that can leave the building |
| `<slug>_records_deidentified_labelled_<date>.csv` | the same, labelled | reading by eye, shareable |
| `<slug>_records_labelled_tidy_<date>.csv` | labelled, with each checkbox field folded back into one column | a spreadsheet a person will scroll |
| `README.md` | what each file is, how many records, which the tools read, which is safe to share | whoever opens the folder next |

Tell the user in those words — "raw codes", "readable labels", "de-identified" — never just
"the export". The "Saved" lines say the same things, so read them back rather than paraphrasing.

**De-identification is a filter, not a judgement.** The `_deidentified_` files drop the fields
REDCap's own dictionary marks `Identifier?` — and nothing else. A free-text note naming a
relative, or a rare diagnosis in a small district, is still in them. Say that when you hand one
over. If the dictionary flags nothing, **no de-identified copy is written at all** (an identical
file under that name would be a lie); the README says so, and that is worth passing on — it
usually means someone never ticked the boxes in the Designer.

A relative `--out` is measured from the folder holding the ARGO settings file — the user's ARGO
folder — not from wherever the command ran. Absolute paths are used as given.

Counts are real CSV rows, not lines of text: a free-text answer with a line break in it spans
several lines of the file. They say `records`, and add a patient count only when the record-ID
column proves one row per patient; a project with repeat instruments reads "2,143 records across
1,525 patients".

If `export.py` can't do what's needed, say so and ask before doing anything by hand — the `curl`
reference much further down is documentation of REDCap's API for a human reading it, not a set of
commands to run in place of the script.

## No key for this study? Ask for it — the export is the whole point

An export puts files on disk. That is what was asked for, so **ask for the key rather than
handing back instructions**: one line, then one question.

> This study doesn't have an access key in your settings file yet — with one, I can download the
> records and the data dictionary straight into your folder. **Want me to put your settings file
> on screen so you can paste it in?**

Then:

1. **Yes → put the file itself in the chat.** Cowork sessions have a file-presenting tool
   (`present_files` on the cowork tool server); present the settings file with it. Otherwise:
   tell them to open their ARGO folder and double-click **'Add keys here'**, which opens the
   settings file in a text editor. Say which line the key goes on (`<STUDY>_TOKEN=`, one per
   study) and to save.
2. **Wait.** Don't fill the silence with the website instructions — they're doing the thing you
   asked for.
3. **Verify, don't assume.** Run the client check and relay the result in one line:
   ```bash
   D=$(dirname "$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name argo_setup.py 2>/dev/null | head -1)")
   python3 "$D/argo_redcap_client.py" --check
   ```
4. **Then export**, with `export.py` as above.

**Never ask them to paste a key into the chat** — a key typed here is in the transcript forever.
If they start, stop them and point at the file.

**Only if they say they can't get one** (a key is issued by a REDCap administrator per person,
per project — [[project-no-super-token]]), take the website path, which does everything:

1. Open the study in REDCap in a browser.
2. **Data Exports, Reports, and Stats** → "All data" → export as CSV, choosing
   **CSV / Microsoft Excel (raw data)** when it asks about the format.
3. **Data Dictionary** page → download as CSV.

Those two files are what [[run-analysis]] and the QA tools expect — **provided the data export is
the raw one.** The website also offers a labelled export, and that is a different file: the tools
read codes and decode them from the dictionary themselves. The two paths land in the same place
only when both are raw; say which encoding the file in front of you is before using it. Click-by-
click instructions, written for someone who doesn't know REDCap's menus:
[[getting-files-from-redcap]]. Nothing in ARGO requires a key, so this path is never a failure —
but don't reach for it before offering the key, and never make getting a key a precondition for
helping.

Save the two files into `database-manager/exports/<study>/` so the export is where the next
person will look for it.

**Identifiable data:** REDCap decides what an export contains *at all* from the permissions of
the account the key belongs to. `export.py` then writes the `_deidentified_` copies described
above by dropping the fields the data dictionary marks `Identifier?` — a filter, and only as good
as those flags: a field nobody ticked is still in them. For an extract that is de-identified at
source, the key must belong to an account whose export rights are set to "De-Identified" — ask
the REDCap administrator. Either way, check the file before sharing it.

Downloading by hand from the website gives you the raw export and the dictionary and nothing
else — no de-identified copy, no README. If the files need to be shared, either run `export.py`
with a key, or drop the flagged columns by hand and say which ones you dropped.

## Close out the request

When the files are on disk and handed over, mark the request record complete in its tracker (tick
`completed` in the REDCap UI). An unclosed request stays on someone's queue forever.

## Prerequisites (API path only)

- An access key with the needed permissions for the target project — optional, see above
- The REDCap API URL (e.g., `https://redcap.oauife.edu.ng/api/`), set once as `REDCAP_URL`

## REDCap API reference (for reading, not for running)

Everything below documents REDCap's API surface: what the parameters mean, what each `content=`
returns. It's here so you can explain an option, check a flag, or hand a developer a recipe.

**It is not the export path.** Doing an export is `export.py` (top of this file) — including when
a snippet below looks like it would be quicker. If a job genuinely needs something `export.py`
can't do, say that out loud and confirm with the user before running anything by hand.

## Exporting records (study data)

### All records, all fields (CSV)
```bash
curl -s -X POST API_URL \
  -d token=TOKEN \
  -d content=record \
  -d format=csv \
  -d type=flat \
  -d rawOrLabel=raw \
  -o database-manager/exports/<study>/output.csv
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
curl -s -X POST API_URL -d token=TOKEN -d content=metadata -d format=csv -o database-manager/exports/<study>/data_dictionary.csv
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
  -o database-manager/exports/<study>/full_export_labelled.csv

# Raw coded version (the one to feed analysis pipelines)
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=csv -d type=flat \
  -d rawOrLabel=raw -d exportDataAccessGroups=true \
  -o database-manager/exports/<study>/full_export_raw.csv

# DD for reference
curl -s -X POST API_URL -d token=TOKEN -d content=metadata -d format=csv -o database-manager/exports/<study>/data_dictionary.csv
```

### Compare a remote DD against a local CSV
```bash
curl -s -X POST API_URL -d token=TOKEN -d content=metadata -d format=csv -o database-manager/exports/<study>/remote_dd.csv
diff <(sort database-manager/exports/<study>/remote_dd.csv) <(sort local_dd.csv)
```

### Export data for a single form
```bash
curl -s -X POST API_URL \
  -d token=TOKEN -d content=record -d format=csv -d type=flat \
  -d "forms[0]=demographics" -d rawOrLabel=label -o database-manager/exports/<study>/demographics.csv
```

## Security

- Access keys live in your settings file only — never typed into a command, a chat message, or a
  script. Everything here reads them from there.
- Access keys are project-specific and carry the permissions of the person they were issued to.
- Exports may contain PHI/PII — handle output files accordingly.
- The `Identifier?` column in the DD flags which fields contain identifiers.

## See also

- [[redcap-api]] (argo-core) — base API conventions
- [[record-id-safety]] — the first DD field is the record ID, not always `record_id`
- [[token-confirmation]] — confirm target project before any write
- [[redcap-api-gotchas]] — write-side traps

Next step: [[run-analysis]] (argo-data-analyst) turns these two files into tables and figures — no
access key involved.
