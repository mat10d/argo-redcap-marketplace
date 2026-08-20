---
name: qa-worklists
description: Two QA jobs for the study you're assigned to. (1) Build the worklists: one Excel workbook per site listing every cell that should have been filled but is blank, ready to hand to the RAs. (2) Audit what comes back: read the RAs' returned workbooks, sort their answers into resolved / needs-a-question / no-action, and confirm the gaps closed. Works from a downloaded export if you don't have the study's access key.
allowed-tools: Read, Bash, Write, Edit, Glob, Grep
---

# qa-worklists

Two jobs: build the per-site worklists of missing data, and audit what the RAs send back.

## Before you start

**Keys.** You already hold the five ARGO tracker keys. For QA you also need one key for the
study you're assigned to; the administrator issues it, on a right-scoped account. It goes in
your settings file. See [[access-tiers]].

**How I get the data.** If the study's access key is in your settings file, I pull straight from
REDCap. If it isn't, I use the two files you download from REDCap (Data Export + Designer →
Download Data Dictionary) — I'll tell you which one I used. See [[token-optional]].

**Shared references**
- [[mdc-rules]] — how MDC sentinels (-666/-777/-888/-999, 666=N/A) are interpreted
- [[redcap-api-gotchas]] — read-side OK; a QA round never writes back

Legacy bulk loads only: [[migration-push]] (requires `--force-migration`; not part of a QA round).

## Task 1 — Build the worklists

Use this for a mid-study cleanup pass ("give the RAs at site X a list of what's missing"), for
pre-lock QA before a data freeze, or to re-check after RAs have updated REDCap.

### What you need

1. **The data** — either the study's access key in your settings file, or a record-export CSV
   plus a Data Dictionary CSV downloaded from REDCap.
2. **Fields YAML** — names the workbooks and lists the fields each one covers. Order fields so
   gate fields come *before* their dependents.

   ```yaml
   workbooks:
     - name: clinical
       title: Clinical
       fields:
         - biopsy
         - biopsy_site         # gated by [biopsy]="1"
         - treatment_received  # checkbox
         - surgery_intent      # gated by [treatment_received(1)]="1"
     - name: followup
       title: Follow-up
       fields:
         - last_followup_status
         - death_date1
         - recur1
   ```

3. (Optional) **Scope CSV** — one column of record IDs to restrict to. Use when the project has
   rows the RA cohort doesn't own (e.g. linkage to a parent study).

### Run it

```bash
set -a; source ~/.argo/.env; set +a   # makes REDCAP_URL and your access keys available
python3 .../argo-qa-specialist/skills/qa-worklists/build_worklists.py \
    --url "$REDCAP_URL" \
    --token-env CRC_TOKEN \
    --fields fields.yaml \
    --out qa-specialist/<study>/worklists \
    --id-field research_number \
    --extra-id-cols collaboration_identifier \
    --scope-ids cohort_ids.csv         # optional
```

`--token-env` takes the *name* of the setting that holds your access key, never the key itself.

*No key?* Replace `--url`/`--token-env` with `--records-csv export.csv --metadata-csv
data_dictionary.csv` — everything else is the same, and the Data Dictionary's human column
headers are mapped automatically.

Outputs (`build_worklists.py` appends a per-round subdir, today's date by default):
```
qa-specialist/<study>/worklists/<round>/
  with_MDC/    # flags blanks AND -666/-777/-888/-999/666 sentinels
    clinical_<DAG>.xlsx
    followup_<DAG>.xlsx
  no_MDC/      # flags only true blanks (sentinels treated as "RA already looked")
    clinical_<DAG>.xlsx
    followup_<DAG>.xlsx
```

### What the RA sees

- One row per patient, one column per field.
- Cells that are **applicable per branching logic AND blank** (or sentinel, in `with_MDC`) are
  highlighted **yellow** — these are confirmed gaps: the field applies and has no value.
- Cells in **amber** mean *"we couldn't read this field's condition — please check whether it
  applies"*. They are not an accusation that something was missed; the tool is telling you it
  doesn't know. Every condition that caused one is listed at the end of the run so the parser
  can be extended. In practice this is rare — across two live projects and ~11,000 evaluations
  there were none — but it exists so a field is never silently omitted.
- A second header row (`only if ...`) shows each field's prerequisite in plain English ("only if treatment_received includes Surgery").
- "Gate context" columns are surfaced automatically: if `surgery_intent` is flagged because `treatment_received` includes Surgery, the workbook also shows `treatment_received` so the RA can see *why*.
- Workbook is filtered — only patients and fields that have at least one yellow cell appear.

### Hand it to the RAs

Send each site its own workbook, and tell them:

1. Open the workbook for your site.
2. For each yellow cell: open the patient in REDCap, check source notes, fill in REDCap.
3. In the spreadsheet, type either the actual value, `filled`, or an MDC code into the yellow
   cell to mark it resolved. RAs often add a `RESPONSE` column with per-row context (why they
   couldn't fill, "RESOLVED" marker, patient died, etc.) — `review_responses.py` picks this up.
4. Send the workbook back.

RAs enter changes in REDCap directly so REDCap's branching, validation, and audit trail apply.
The spreadsheet is a worklist, not a data-entry form.

## Task 2 — Audit what comes back

Work site by site. Drop the returned files in `qa-specialist/<study>/RA_response/` (flat — RAs
name them however they name them).

### Read each site's return

For each returned file:

```bash
python3 .../argo-qa-specialist/skills/qa-worklists/review_responses.py \
    qa-specialist/<study>/worklists/<round>/with_MDC/<workbook>_<site>.xlsx \
    "qa-specialist/<study>/RA_response/<RA-filename>.xlsx"
```

`review_responses.py` reports, grouped by record:
- **Cells the RA changed** (was-yellow + now-non-blank) with the RA's RESPONSE note next to them
- **Records with RA notes but no cell changes** (often "RESOLVED" without filling — verify
  directly in REDCap, or "patient died/care elsewhere" — no action)

Sort each answer into one of four buckets:

| Bucket | What it is | What you do |
|---|---|---|
| **READY** | Clean answer — a value or MDC code that maps directly to a field | Confirm it's in REDCap; if the RA only wrote it in the spreadsheet, ask them to enter it |
| **QUESTION_FOR_RA** | Ambiguous (e.g. RA wrote "NO SURGERY" into a select field, or a value that doesn't exist in the DD's choice list) | Append to `RA_questions.md` |
| **NO_ACTION** | RA explained why blank (patient died with no chart, care happened off-site) and no recode is warranted | Nothing |
| **VERIFY** | RA marked RESOLVED but didn't fill the cell — likely fixed directly in REDCap | Re-pull and confirm; if filled, drop. If still blank, ask. |

### Ask the open questions

Keep one `RA_questions.md` at `qa-specialist/<study>/RA_questions.md` — it is the single source
for the outgoing questions. One section per site. Each entry: record ID, field, what the RA
wrote, why it's ambiguous, what we need to know. Write the questions in second person
("Could you…?") rather than triage-style ("Action: ask RA…") — `summarize_for_ra.py` copies them
verbatim into what the RA receives.

Section structure expected in `RA_questions.md`:

```markdown
## LASUTH
### 40-65 — could you clarify your "RESOLVED" note?
...
## OAUTHC
### 46-608, 46-613 — what does "patient was disqualified" mean?
...
```

The `## <SITE>` headers are matched (case-insensitive) against the site names so the right
questions show up in the right summary.

Loop with the RA until all questions resolve; new answers either become READY or NO_ACTION.

### Confirm the gaps closed

Re-run Task 1's build. Cells the RAs resolved drop out of the new worklist — anything still
yellow is either a fix that didn't land in REDCap or a new gap. Diff against the prior round for
a clean "did this round do what we expected" check.

### Send each RA their summary

```bash
python3 .../argo-qa-specialist/skills/qa-worklists/summarize_for_ra.py \
    --url "$REDCAP_URL" --token-env CRC_TOKEN \
    --questions qa-specialist/<study>/RA_questions.md \
    --out qa-specialist/<study>/RA_summaries/ --round-label "<today>"
```

Outputs `RA_summaries/<round>/<site>.md` per site, each with the questions still open for that
RA, pulled from the `RA_questions.md` sections matching the site name. (`--push-drafts` is a
migration-only input — see [[migration-push]]; in a QA round point it at an empty folder.)

## When a field is "applicable"

`build_worklists.py` evaluates the branching logic literally. It supports `[field]='val'` and `[field]=val` (**unquoted — what REDCap's Designer actually emits for numeric codes**), `[field(N)]` for checkbox option N, `AND`, `OR`, `=`, `!=`, `<>`, and the numeric comparisons `<`, `>`, `<=`, `>=`.

A condition it cannot read does **not** cause the field to be dropped. The cell is surfaced in a distinct amber fill meaning *"we couldn't tell whether this applies — please check"*, as opposed to the normal yellow *"this applies and is blank"*. Every unreadable condition is listed once at the end of the run so the parser can be extended.

## Limits

- **Field-completeness only for now** — cross-form logic (e.g. surgery_date ≥ diagnosis_date),
  outliers, and impossible-value detection are planned follow-ups.
- **Single form / single arm only for now** — multi-event REDCap projects need a per-event
  split; not yet wired.
- **No write-back (by design, enforced by policy)** — the RA enters changes in REDCap directly
  so REDCap's branching, validation, and audit trail apply. We do not round-trip dirty Excel
  into REDCap. See [[redcap-api-gotchas]] §0. The only exception is a one-off legacy migration:
  [[migration-push]].

Roadmap (not yet built): source-document audit verification, and a PM-side blocker view that QA
flags should eventually feed into.
