---
name: redcap-api-reference
description: What REDCap's API parameters mean, for explaining an option or checking a flag — not a set of commands to run. Exports go through export.py; writes to cohort data are migration-only.
---

# REDCap API reference — for reading, not for running

An export is `export.py`, always ([[export-data]]). This page is here so you can explain what an
option means or check what REDCap supports. It deliberately has no copy-paste commands: an
improvised API call once sent a malformed `fields` parameter and put a raw traceback in front of
the user, and a command with a key in it ends up in the transcript. If a job needs something
`export.py` can't do, say so and ask before doing anything by hand.

## Record export (`content=record`)

| Parameter | Values | Meaning |
|---|---|---|
| `format` | `csv`, `json`, `xml` | Output format |
| `type` | `flat`, `eav` | `flat` = one row per record (standard) |
| `rawOrLabel` | `raw`, `label` | Codes (`1`, `2`) or labels (`Yes`, `No`) |
| `rawOrLabelHeaders` | `raw`, `label` | Column headers: variable names or field labels |
| `exportCheckboxLabel` | `true`, `false` | Checkboxes as 0/1 or Unchecked/Checked |
| `exportSurveyFields` | `true`, `false` | Survey timestamp and identifier fields |
| `exportDataAccessGroups` | `true`, `false` | The `redcap_data_access_group` column |
| `records[n]`, `fields[n]`, `forms[n]`, `events[n]` | names | Filters |
| `dateRangeBegin` / `dateRangeEnd` | `YYYY-MM-DD hh:mm:ss` | Filters on the record's **last-modified** time, not on date fields |
| `returnFormat` | `csv`, `json`, `xml` | Format of error messages only |

`content=report` with `report_id` exports a saved report (the ID is in the report's URL).

## Other read endpoints

| `content=` | Returns |
|---|---|
| `metadata` | The data dictionary |
| `instrument` | Forms list |
| `event`, `arm`, `formEventMapping` | Longitudinal structure |
| `repeatingFormsEvents` | Repeating instruments and events |
| `project` | Title, PID, longitudinal flag, … |
| `dag` | Data Access Groups |
| `file` (`action=export`, `record`, `field`, `event`, `repeat_instance`) | A file attached to a record |
| `log` (`logtype`, `beginTime`, `endTime`) | Audit trail; log types `export`, `manage`, `user`, `record`, `lock_record`, `page_view` |
| `surveyLink`, `surveyReturnCode`, `surveyQueueLink` | Survey links for a record |

## Imports — migration-only

Cohort patient records are entered and corrected by RAs in REDCap, not imported
([[redcap-api-gotchas]] §0). A bulk load of legacy data is a deliberate one-off migration:
validation on, a human-reviewed preview, a snapshot first. Read [[redcap-api-gotchas]] before any
write — dates, overwrite modes, choice codes, checkbox-MDC columns and record-ID renaming all have
silent failure modes.

| Parameter | Values | Meaning |
|---|---|---|
| `overwriteBehavior` | `normal`, `overwrite` | `normal`: blank cells in the import are ignored (existing values stay); non-blank cells still replace. `overwrite`: blanks erase too |
| `forceAutoNumber` | `true`, `false` | Auto-number instead of using the given IDs |
| `returnContent` | `count`, `ids`, `auto_ids` | What the import returns |

### Legacy free-text → structured fields

When a dictionary redesign replaces one free-text field (say `address`) with several structured
ones (`house_number`, `street`, `town`, `state`), the safe choreography reads with the API and
hands a CSV to the user for a **manual** import:

1. **Candidates = source filled AND every target blank.** A record with any new-field data is left
   out entirely, so a re-run can't disturb earlier migration or hand entry.
2. **Literal split only — no inference.** Take what is written; never "correct" a value (a typed
   state that doesn't match geography stays) and never infer one that wasn't typed (leave it
   blank). A locality landing in `street` rather than `town` is acceptable; fabrication is not.
   A model pass tends to over-correct here.
3. **Emit only rows with at least one non-empty target.** Drop pure missing codes (`-777`, `-999`).
4. **Import with "don't let blanks overwrite"** (Data Import Tool default, = `normal`) as a second
   safety net.
5. **Keep an audit CSV** (`record_id, source_raw, <new fields>`) so every split traces to its
   source string.
