---
name: qa-worklists
description: Two QA jobs for the study you're assigned to. (1) Build the worklists: I ask what you want QA'd first, then one Excel workbook per site listing every cell in that scope that should have been filled but is blank, ready to hand to the RAs. (2) Audit what comes back: read the RAs' returned workbooks, sort their answers into resolved / needs-a-question / no-action, and confirm the gaps closed. Works from a downloaded export if you don't have the study's access key.
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

**Where the data is — I ask, I don't hunt.** If you haven't attached or named the export, I ask
you where it is. If there are plausible files already in the folder, I *name what I found* and
ask one question to confirm; I never pick a file because it looked like the right one. (A QA
session once came within a step of auditing the analyst's synthetic export as though it were
the study.)

**If a tool can't run, I say so.** No hand-written stand-in for a script's output, no invented
counts, no "here is roughly what it would have said". If a step fails or a library is missing
you get the plain reason and what to do about it, and the round stops there until it's fixed.

**Shared references**
- [[mdc-rules]] — how MDC sentinels (-666/-777/-888/-999, 666=N/A) are interpreted
- [[redcap-api-gotchas]] — read-side OK; a QA round never writes back

Legacy bulk loads only: [[migration-push]] (requires `--force-migration`; not part of a QA round).

## Task 1 — Build the worklists

Use this for a mid-study cleanup pass ("give the RAs at site X a list of what's missing"), for
pre-lock QA before a data freeze, or to re-check after RAs have updated REDCap.

### What you need

1. **The data** — either the study's access key in your settings file, or a record-export CSV
   plus a Data Dictionary CSV downloaded from REDCap. I ask you where these are; I don't go
   looking (see *Where the data is* above).
2. (Optional) **Scope CSV** — one column of record IDs to restrict to. Use when the project has
   rows the RA cohort doesn't own (e.g. linkage to a parent study).

That is the whole list. *Which* fields get chased is your call and I ask you first; how they are
split into workbooks is mine — next section.

### The workbook plan — scope first, then I write it and you confirm

**Step 1. I ask what you want QA'd, and I wait for the answer.**

> What exactly do you want me to QA — which fields, or which part of the study?

That question comes before any proposal. Nothing is built, and no plan is shown, until scope is
settled.

The reason is size. Real study dictionaries are large — 600+ fields is ordinary, and one live
colorectal project carries 160 fields on a single form. **"Everything blank that could be
chased" is never the default plan.** It produces a workbook no RA will finish, buries the ten
fields you actually needed, and turns a QA round into a wall of yellow.

**Step 2. A broad answer gets narrowed, not guessed at.**

If the answer is an area rather than a field list — "staging", "follow-up", "the pathology
stuff" — I don't interpret it and start building. I read the data dictionary, list the fields
that match, grouped so the list can be read (by form, then by the section headers the form
itself uses), and hand it back to you to narrow:

> "Staging" matches 23 fields across two forms.
> **Pathology form** — tnm_t, tnm_n, tnm_m, histology_grade, margin_status, …
> **Surgery form** — resection_extent, nodes_examined, nodes_positive, …
> Which of these do you want chased this round?

If the narrowed answer is still broad, I narrow it again. Scope is decided by you; I only ever
show you what's there.

**Step 3. Then the workbook plan.**

With the fields agreed, the split is my job. I group them into workbooks (normally one per
form), order each list so gate fields come *before* the fields they gate, pull in any gate field
the branching logic needs, and show you the proposal — the workbooks, the fields in each, the
sites they'll be split across. Then **one** question: is this the right split? Adjust or
confirm, and I build.

`build_worklists.py` is driven by a small YAML file holding that plan. **You are never asked to
produce it, or to have one already.** It is saved as `qa_fields.yaml` beside the worklists (path
below) so the next round reruns identically, and so you can hand-edit it if you ever want to. It
is a working file the tool needs, not homework.

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

### Run it

```bash
python3 .../argo-qa-specialist/skills/qa-worklists/build_worklists.py \
    --token-env CRC_TOKEN \
    --fields qa_fields.yaml \
    --out qa-specialist/<study>/worklists \
    --id-field research_number \
    --extra-id-cols collaboration_identifier \
    --scope-ids cohort_ids.csv         # optional
```

`--token-env` takes the *name* of the setting that holds your access key, never the key itself.
`--fields` points at the `qa_fields.yaml` I wrote and you confirmed. The script finds and reads
your settings file itself — there is nothing to `source` first, and `--url` is only needed if
your REDCap address isn't on the `REDCAP_URL` line of that file.

*No key?* Replace `--token-env` with `--records-csv export.csv --metadata-csv
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

Write the config to `qa-specialist/<study>/worklists/qa_fields.yaml` — one level above the
round folders, so every round shares it and a change to the plan shows up as a diff.

### What the RA sees

- One row per patient, one column per field.
- Cells that are **applicable per branching logic AND blank** (or sentinel, in `with_MDC`) are
  highlighted **yellow** — these are confirmed gaps: the field applies and has no value.
- Cells in **amber** mean *"we couldn't read this field's condition — please check whether it
  applies"*. They are not an accusation that something was missed; the tool is telling you it
  doesn't know. Every condition that caused one is listed at the end of the run so the parser
  can be extended. In practice this is rare — across two live projects and ~11,000 evaluations
  there were none — but it exists so a field is never silently omitted.
- A second header row shows each field's prerequisite in plain English ("only if
  treatment_received includes Surgery"). For an amber column it instead says
  **"couldn't read this condition: `<the raw expression>`"** — the raw REDCap expression is
  shown because that is honestly all we have, and the wording says so rather than presenting an
  expression nobody could parse as if it were an instruction.
- "Gate context" columns are surfaced automatically: if `surgery_intent` is flagged because `treatment_received` includes Surgery, the workbook also shows `treatment_received` so the RA can see *why*.
- Column headings are the fields' labels. REDCap only requires field *names* to be unique, and
  shared labels are common (one live dictionary had 44 labels used by more than one field), so
  where two columns would carry the same heading the later one gets the field name in
  parentheses — `Date of surgery (surgery_date_2)`. No two columns ever read the same.
- Workbook is filtered — only patients and fields with at least one highlighted cell appear.

### Hand it to the RAs

**Send the `with_MDC/` workbooks.** That is the default, every round, and it is what the rest of
this skill assumes: the RAs revisit cells already holding a coded-missing value (`-666`/`-777`/
`-888`/`-999`/`666`) as well as blank ones, because a code entered in a hurry is not the same as
a code someone stood behind. `no_MDC/` is the exception, and it needs a decision from you as the
QA specialist: send it only when you have decided the coded-missing cells are settled and should
not be revisited this round. Say which variant you sent, in the covering message and in the round
notes — a site that received one and is asked about the other has no way to tell.

Send each site its own workbook, and tell them:

1. Open the workbook for your site.
2. For each highlighted cell — yellow, or amber if the column asks you to check whether the
   field applies — open the patient in REDCap, check source notes, fill in REDCap.
3. In the spreadsheet, type either the actual value, `filled`, or an MDC code into that cell to
   mark it resolved. The last column, `RESPONSE`, is for per-row context (why you couldn't
   fill it, a "RESOLVED" marker, patient died, etc.) — `review_responses.py` reads it, and
   picks up a differently-named comment column if a site adds their own.
4. Change only the highlighted cells and `RESPONSE`. Anything else you edit is reported back to
   us as an unrequested change — if something elsewhere in the row is wrong, say so in
   `RESPONSE` instead.
5. Send the workbook back.

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
- **Cells the RA answered** — a cell the worklist flagged that now holds a different, non-blank
  value — with the RA's RESPONSE note next to them. Yellow *and* amber cells count: an answer
  in an amber cell is still an answer. Amber ones are tagged `[AMBER …]` in the output, because
  amber meant "we couldn't read this field's condition" — confirm the field applies at all
  before you act on the value.
- **Records with RA notes but no cell changes** (often "RESOLVED" without filling — verify
  directly in REDCap, or "patient died/care elsewhere" — no action)
- **Cells changed that were NOT on the worklist** — a gate-context column, an ID column, any
  field nobody flagged. Listed separately, at the end, because they are not answers to anything
  we asked.

A worklist built before ARGO 0.18 highlighted its gaps in a pale **rose** rather than yellow.
Those returns still audit correctly — the rose fill is read exactly like yellow — and the run
prints one line saying it recognised the old colour. Nothing needs rebuilding to read them.

Sort each answer into one of four buckets:

| Bucket | What it is | What you do |
|---|---|---|
| **READY** | Clean answer — a value or MDC code that maps directly to a field | Confirm it's in REDCap; if the RA only wrote it in the spreadsheet, ask them to enter it |
| **QUESTION_FOR_RA** | Ambiguous (e.g. RA wrote "NO SURGERY" into a select field, or a value that doesn't exist in the DD's choice list) | Append to `RA_questions.md` |
| **NO_ACTION** | RA explained why blank (patient died with no chart, care happened off-site) and no recode is warranted | Nothing |
| **VERIFY** | RA marked RESOLVED but didn't fill the cell — likely fixed directly in REDCap | Re-pull and confirm; if filled, drop. If still blank, ask. |

Out-of-scope edits are **not** one of the four buckets — nobody asked for them, so none of the
four applies. Each one becomes its own question to the RA: what did you change here, and why?
And if a *gate* field changed, rebuild that site's worklist afterwards — different fields may
apply now.

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

The **whole** `## ` header is the site name — matched ignoring case and spacing, so
`## Site Alpha`, `## SITE ALPHA` and `## site  alpha` are one site, and `## Site Alpha` and
`## Site Beta` are two. (Only the first word used to count, which quietly served one site's
questions to every RA in the study.) Two headers that collapse to the same name are merged, and
the run says so.

Loop with the RA until all questions resolve; new answers either become READY or NO_ACTION.

### Confirm the gaps closed — and where to stop when you can't yet

Re-run Task 1's build **on a fresh export**. Cells the RAs resolved drop out of the new worklist —
anything still yellow is either a fix that didn't land in REDCap or a new gap. Diff against the
prior round for a clean "did this round do what we expected" check.

**If there is no post-RA export, the round stops here — and that is a finished state, not a
failure.** The RAs enter their answers in REDCap, so the only way to see whether a gap closed is
to pull the data again; re-checking the old export would just re-report the same gaps, and
nothing in a returned workbook is evidence that REDCap changed. So:

1. Send the summaries and the open questions (below) — that work is complete and doesn't wait.
2. Ask for a fresh export: either the study's access key in the settings file, or a new Data
   Export + Data Dictionary download ([[getting-files-from-redcap]]).
3. Say plainly what is outstanding — "N cells answered, verification pending the next pull" —
   and stop. Don't mark anything verified, and don't run VERIFY against the pre-RA export.

The round closes on the next pull, when the rebuild shows the cells gone.

### Send each RA their summary

```bash
python3 .../argo-qa-specialist/skills/qa-worklists/summarize_for_ra.py \
    --metadata-csv data_dictionary.csv \
    --questions qa-specialist/<study>/RA_questions.md \
    --out qa-specialist/<study>/RA_summaries/ --round-label "<today>"
```

*Have the study's key?* Replace `--metadata-csv data_dictionary.csv` with
`--token-env CRC_TOKEN` (it reads your settings file itself). Either way the dictionary is only
used to turn field codes back into the wording the RA will recognise — no key is required for
this step.

Outputs `RA_summaries/<round>/<site>.md` per site, each with the questions still open for that
RA, pulled from the `RA_questions.md` sections matching the site name. A site name with spaces
in it becomes underscores in the filename (`## Site Alpha` → `site_alpha.md`). (`--push-drafts` is a
migration-only input — see [[migration-push]]; a normal QA round stages nothing, so leave it
out entirely.)

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
