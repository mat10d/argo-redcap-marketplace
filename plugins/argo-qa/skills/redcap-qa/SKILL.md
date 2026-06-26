---
name: redcap-qa
description: Run continuous QA on an active REDCap study. Generates per-site (per-DAG) Excel worklists that highlight applicable-but-blank cells for RAs to resolve in REDCap. First implementation focuses on field-completeness; cross-form logic, outliers, and impossible-value detection are planned follow-ups.
allowed-tools: Read, Bash, Write, Edit, Glob, Grep
---

# redcap-qa

Branching-logic-aware completeness QA for an active REDCap project. Surface every cell that *should* have been filled (applicable per branching logic) but is blank or carries a non-answer MDC sentinel, split by site so each RA gets one workbook for their DAG.

Pattern was developed on the R01 CRC cohort — see `REDCap/Analysis/linkages/R01_linkages/build_ra_worklists.py` for the original, study-specific version. This skill is the generalized form.

## When to use

- Mid-study cleanup pass: "give the RAs at site X a list of what's missing"
- Pre-lock QA before a data freeze
- Re-running after RAs have updated REDCap to confirm coverage

## Shared references

- [[mdc-rules]] — how MDC sentinels (-666/-777/-888/-999, 666=N/A) are interpreted
- [[redcap-api-gotchas]] — read-side OK; this skill never writes back

## Inputs

1. **REDCap project token** — set as an env var (e.g. `CRC_TOKEN`).
2. **Fields YAML** — names the workbooks and lists the fields each one covers. Order fields so gate fields come *before* their dependents.

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

3. (Optional) **Scope CSV** — one column of record IDs to restrict to. Use when the project has rows the RA cohort doesn't own (e.g. linkage to a parent study).

## Run

```bash
set -a; source ~/.argo/.env; set +a   # exposes REDCAP_URL and the token
python3 .../argo-qa/skills/redcap-qa/build_worklists.py \
    --url "$REDCAP_URL" \
    --token-env CRC_TOKEN \
    --fields fields.yaml \
    --out outputs/qa_worklists \
    --id-field research_number \
    --extra-id-cols collaboration_identifier \
    --scope-ids cohort_ids.csv         # optional
```

Outputs:
```
outputs/qa_worklists/
  with_MDC/    # flags blanks AND -666/-777/-888/-999/666 sentinels
    clinical_<DAG>.xlsx
    followup_<DAG>.xlsx
  no_MDC/      # flags only true blanks (sentinels treated as "RA already looked")
    clinical_<DAG>.xlsx
    followup_<DAG>.xlsx
```

## Workbook conventions (what the RA sees)

- One row per patient, one column per field.
- Cells that are **applicable per branching logic AND blank** (or sentinel, in `with_MDC`) are highlighted yellow.
- A second header row (`only if ...`) shows each field's prerequisite in plain English ("only if treatment_received includes Surgery").
- "Gate context" columns are surfaced automatically: if `surgery_intent` is flagged because `treatment_received` includes Surgery, the workbook also shows `treatment_received` so the RA can see *why*.
- Workbook is filtered — only patients and fields that have at least one yellow cell appear.

## RA workflow

1. Open the workbook for your site.
2. For each yellow cell: open the patient in REDCap, check source notes, fill in REDCap.
3. In the spreadsheet, type either the actual value, `filled`, or an MDC code into the yellow cell to mark it resolved. RAs often add a `RESPONSE` column with per-row context (why they couldn't fill, "RESOLVED" marker, patient died, etc.) — `review_responses.py` picks this up.
4. Re-run this skill to confirm — resolved cells drop out of the next worklist.

## Review → snapshot → push workflow (round-trip)

> ⚠️ **DEPRECATED — read [[redcap-api-gotchas]] §0 (no programmatic writes to cohort patient data).**
> This skill is **read-only by default**: produce worklists, RAs fill REDCap directly, re-pull to confirm. The push steps below (`verify_push.py`, `push_updates.py`) are retained only as a **migration-only escape hatch** for one-off bulk loads of legacy data, and require an explicit acknowledgment flag to run. Do **not** use them in the routine QA cycle. `snapshot_project.py` (read-only export) is fine to use anytime.

When RAs return updated worklists, the workflow is **per-site review first, push only once everything is resolved**:

```
QA/<study>/
├── config/{fields.yaml, scope_ids.csv}
├── outputs/<round>/               # original worklists (build_worklists.py)
├── RA_response/                   # files dropped here by RAs (flat — RA naming)
├── push_drafts/<round>/           # one CSV per (site, workbook) — staged updates
├── RA_summaries/<round>/          # per-RA markdown (summarize_for_ra.py)
├── RA_questions.md                # open items, RA-facing tone, single source
└── snapshots/                     # timestamped full project exports (snapshot_project.py)
```

`<round>` defaults to today's date (`YYYY-MM-DD`) — every script that writes derived artifacts auto-appends this subdir so reruns within a round overwrite cleanly *within* the round folder, and the next round (next day, or whatever you pass to `--round`) gets a fresh folder instead of stomping the prior cycle. Pass `--round=` (empty) to disable the subdir (legacy flat layout).

### 1. Walk site by site through the responses

For each RA_response file:
```bash
python3 .../argo-qa/skills/redcap-qa/review_responses.py \
    outputs/with_MDC/<workbook>_<site>.xlsx \
    "RA_response/<RA-filename>.xlsx"
```

`review_responses.py` reports, grouped by record:
- **Cells the RA changed** (was-yellow + now-non-blank) with the RA's RESPONSE note next to them
- **Records with RA notes but no cell changes** (often "RESOLVED" without filling — verify directly in REDCap, or "patient died/care elsewhere" — no action)

Categorize each proposed change into one of four buckets:

| Bucket | What it is | Where it goes |
|---|---|---|
| **READY** | Clean update — value or MDC code that maps directly to a field | `push_drafts/<site>_<workbook>.csv` |
| **QUESTION_FOR_RA** | Ambiguous (e.g. RA wrote "NO SURGERY" into a select field, or a value that doesn't exist in the DD's choice list) | Append to `RA_questions.md` |
| **NO_ACTION** | RA explained why blank (patient died with no chart, care happened off-site) and no recode is warranted | Nothing |
| **VERIFY** | RA marked RESOLVED but didn't fill the cell — likely fixed directly in REDCap | Re-pull and confirm; if filled, drop. If still blank, ask. |

### 2. Build per-site push CSVs

One CSV per (site, workbook), columns = record-ID + only the fields touched. Use REDCap's coded values:
- Radio/dropdown: numeric code (e.g. `m_score = -888`)
- Checkbox: `field___N = 0|1` for positive codes, `field____N = 0|1` for negative codes (4 underscores — REDCap strips the minus). To recode a checkbox from -999 to -888, write both `field____999=0` AND `field____888=1`.
- Blank cells = "leave alone" under `overwriteBehavior=normal`. So only the named fields get touched.

### 3. Maintain RA_questions.md in parallel

One section per site. Each entry: record ID, field, what the RA wrote, why it's ambiguous, what we need to know. Loop with the RA until all questions resolve; new answers either become READY or NO_ACTION.

### 4. Snapshot before push

When all sites are resolved (push_drafts complete, RA_questions cleared), take a full project snapshot as the rollback point:

```bash
python3 .../argo-qa/skills/redcap-qa/snapshot_project.py \
    --url "$REDCAP_URL" --token-env CRC_TOKEN \
    --out snapshots/ --tag pre-qa-push
```

This writes `snapshots/snapshot_<timestamp>_pre-qa-push.csv` — a raw flat export of every record, every field, with DAGs. If a push goes wrong, restore via `overwriteBehavior=overwrite` against this file.

### 5a. Verify before push (handle RA direct edits)

RAs often update REDCap directly between when we stage `push_drafts/` and when we push. If we push blindly with `overwriteBehavior=normal`, any cell we'd overwrite that the RA already filled differently will be clobbered. To avoid that, re-pull and emit only the deltas that are still needed:

```bash
python3 .../argo-qa/skills/redcap-qa/verify_push.py \
    --url "$REDCAP_URL" --token-env CRC_TOKEN \
    --push-drafts push_drafts/<round>/
```

Writes:
- `push_drafts/<round>/_verified/<original>.csv` — safe-to-push deltas (cells still needed)
- `push_drafts/<round>/_conflicts.md` — REDCap is now non-blank and *differs* from our planned write; review each one

Push the `_verified/` copies, not the originals.

### 5b. Push atomically

Push all sites in one merged call:

```bash
python3 .../argo-qa/skills/redcap-qa/push_updates.py \
    --url "$REDCAP_URL" --token-env CRC_TOKEN \
    push_drafts/*.csv --dry-run        # preview merged payload
# then, without --dry-run, to actually push:
python3 .../argo-qa/skills/redcap-qa/push_updates.py \
    --url "$REDCAP_URL" --token-env CRC_TOKEN \
    push_drafts/*.csv
```

Uses `overwriteBehavior=normal` so blank cells in the payload don't clobber existing values. Returns the count of records touched.

### 6. Re-run build_worklists.py to verify

After the push, regenerate the worklists. Cells that were resolved should drop out — anything still yellow is either a push that didn't take or a new gap. Diff this against the prior run for a clean "did the push do what we expected" check.

### 7. Close the loop: send a summary back to each RA

After the push, produce per-RA markdown summaries combining (a) what we changed based on their responses and (b) anything still open for them:

```bash
python3 .../argo-qa/skills/redcap-qa/summarize_for_ra.py \
    --url "$REDCAP_URL" --token-env CRC_TOKEN \
    --push-drafts push_drafts/ --questions RA_questions.md \
    --out RA_summaries/ --round-label "2026-05-24"
```

Outputs `RA_summaries/<site>.md` per site, each with:
- **Changes we're making to REDCap based on your responses** — grouped by workbook, then by field (largest groups first). Codes are decoded to human-readable labels using metadata.
- **Questions for you** — pulled from `RA_questions.md` sections that match the site name.

`RA_questions.md` is the single source for the outgoing questions, so write its question sections in second-person ("Could you…?") rather than triage-style ("Action: ask RA…") — the summary script copies them verbatim.

Section structure expected in `RA_questions.md`:
```markdown
## LASUTH
### 40-65 — could you clarify your "RESOLVED" note?
...
## OAUTHC
### 46-608, 46-613 — what does "patient was disqualified" mean?
...
```

The `## <SITE>` headers are matched (case-insensitive) against push_drafts filenames so the right questions show up in the right summary.

## What gates a field

`build_worklists.py` evaluates the branching logic literally — supports `[field]='val'`, `[field(N)]='val'` (checkbox option N), `AND`, `OR`, and `=/!=/<>`. Unparseable clauses are treated as True (fail-open) so the field is still surfaced — better than silently dropping it.

## Limits / known gaps

- **Single form / single arm only for now** — multi-event REDCap projects need a per-event split; not yet wired.
- **No cross-form logic checks** (e.g. surgery_date ≥ diagnosis_date). Planned.
- **No outlier / impossible-value detection** — planned.
- **No write-back (by design, enforced by policy)** — the RA enters changes in REDCap directly so REDCap's branching, validation, and audit trail apply. We do not round-trip dirty Excel into REDCap. See [[redcap-api-gotchas]] §0; the push scripts are deprecated/migration-only.

## See also

- `REDCap/Analysis/linkages/R01_linkages/build_ra_worklists.py` — the study-specific original this was generalized from

Roadmap (not yet built): source-document audit verification, and a PM-side blocker view that QA flags should eventually feed into.
