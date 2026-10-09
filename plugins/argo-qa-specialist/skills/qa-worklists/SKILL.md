---
name: qa-worklists
description: Two QA jobs for the study you're assigned to. (1) Build the worklists: I ask what you want QA'd first, then one Excel workbook per site listing every cell in that scope that should have been filled but is blank, ready to hand to the RAs. (2) Audit what comes back: read the RAs' returned workbooks, check cell by cell that REDCap now holds each answer (field comments included), turn what didn't land into questions for the RA, and upload only missing-data codes into blank cells. Works from a downloaded export if you don't have the study's access key.
allowed-tools: Read, Bash, Write, Edit, Glob, Grep
---

# qa-worklists

Two jobs: build the per-site worklists of missing data, and audit what the RAs send back.

## Before you start

**Keys.** You already hold the five ARGO tracker keys. For QA, a key for the study you're
assigned to makes the pull direct — the administrator issues it, on a right-scoped account, and
it goes in your settings file. It's never required: without one I work from the two files you
download. See [[access-tiers]].

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
- [[redcap-api-gotchas]] — a QA round uploads only missing-data codes into blank cells (§0)

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
W="$(dirname "$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name build_worklists.py 2>/dev/null | head -1)")"

python3 "$W/build_worklists.py" \
    --token-env CRC_TOKEN \
    --fields qa-specialist/<study>/worklists/qa_fields.yaml \
    --out qa-specialist/<study>/worklists \
    --id-field research_number \
    --extra-id-cols collaboration_identifier \
    --scope-ids cohort_ids.csv         # optional
```

`$W` is the folder this skill's scripts are in. Shell variables don't survive between commands,
so keep that first line in front of every block below, or set it once in the same command.

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
notes — `qa-specialist/<study>/worklists/<round>/ROUND_NOTES.md`, which records what went out,
which variant, and when. A site that received one and is asked about the other has no way to tell.

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
python3 "$W/review_responses.py" \
    qa-specialist/<study>/worklists/<round>/with_MDC/<workbook>_<site>.xlsx \
    "qa-specialist/<study>/RA_response/<RA-filename>.xlsx"
```

`review_responses.py` reports, grouped by record:
- **Cells the RA answered** — a cell the worklist flagged that now holds a different, non-blank
  value — with the RA's RESPONSE note next to them. Yellow *and* amber cells count: an answer
  in an amber cell is still an answer. Amber ones are tagged `[AMBER …]` in the output, because
  amber meant "we couldn't read this field's condition" — confirm the field applies at all
  before you act on the value.
- **Records with RA notes but no cell changes** (often "RESOLVED" without filling, or "patient
  died/care elsewhere") — the REDCap check below looks at each of their flagged cells
- **Cells changed that were NOT on the worklist** — a gate-context column, an ID column, any
  field nobody flagged. Listed separately, at the end, because they are not answers to anything
  we asked.

A worklist built before ARGO 0.18 highlighted its gaps in a pale **rose** rather than yellow.
Those returns still audit correctly — the rose fill is read exactly like yellow — and the run
prints one line saying it recognised the old colour. Nothing needs rebuilding to read them.

### Check that REDCap holds it — the RA enters, you check

You don't re-upload what the RAs send back. The RA enters every answer in REDCap; your job is to
check it landed. This needs REDCap's state **after** the RA's work: the study's access key, or a
fresh Data Export (raw) + Data Dictionary downloaded after the return
([[getting-files-from-redcap]]). Add the Field Comment Log if there is one: Applications →
Field Comment Log → download, saved in `RA_response/`.

```bash
python3 "$W/reconcile_return.py" \
    qa-specialist/<study>/worklists/<round>/with_MDC/<workbook>_<site>.xlsx \
    "qa-specialist/<study>/RA_response/<RA-filename>.xlsx" \
    --records-csv export_after_return.csv --metadata-csv data_dictionary.csv \
    --comments qa-specialist/<study>/RA_response/<field-comment-log>.csv \
    --out qa-specialist/<study>/reconcile/<round>/<site>_<workbook>.md
```

*Have the study's key?* Replace the two `--…-csv` options with `--token-env CRC_TOKEN`. With a
key and no `--comments` file, field comments are rebuilt from the project's whole logging
history — no download needed. REDCap has no API for the Field Comment Log itself, but every
comment add, edit and delete is logged. If the key isn't allowed to read logging, the report says
so and you download the log instead (Applications → Field Comment Log → CSV; columns
`Record, Field, User, Datetime, Comment`).

It reads only. Each answered cell gets one status — compared the way REDCap stores values
(labels and codes, any date layout, checkbox options):

| Status | Meaning | What you do |
|---|---|---|
| **IN REDCAP** | REDCap holds the RA's answer | Nothing |
| **NOT ENTERED** | REDCap still shows what the worklist showed — the RA wrote it only in the spreadsheet | Ask the RA to enter it. A missing-data code into a blank cell, you may upload (next section) |
| **DIFFERS** | REDCap holds something else | Ask the RA which is right. Never settle it yourself |
| **UNCLEAR** | Not one of the field's choices, a date we can't read, or a column we can't match | Ask the RA what they meant |

Rows the RA marked **RESOLVED** without filling a cell are checked the same way: each flagged
cell on that row is either in REDCap now, or "marked resolved, still blank" — a question. A row
whose note *explains* a blank ("patient died, chart not available") is listed for you to decide:
no action, or a question.

Field comments sit beside their cells. Comments are evidence, never values: a flagged cell still
blank with a comment explaining it stays blank until you decide — it is never turned into a
missing-data code for you. Comments on cells that weren't on the worklist are listed separately.

The report is short: counts first, then only what needs action, then a block ready to paste into
`RA_questions.md`. Cells changed that were never on the worklist (from `review_responses.py`)
are not checked against REDCap — each is its own question: what did you change, and why? If a
*gate* field changed, rebuild that site's worklist afterwards — different fields may apply now.

### Missing-data codes — the one upload you may do

A missing-data code the RA returned (-666/-777/-888/-999, [[mdc-rules]]) for a cell that is
still blank in REDCap, you may upload yourself. Nothing else — every other value the RA enters.
The codes are checked first, not rubber-stamped. Held back, as a question to the RA:

- the field doesn't take that code (not in its choices or Field Note; @MDC-EXEMPT; a validated
  scale; a self-completed survey — name survey forms with `--survey-forms`; a date-and-time field);
- the code doesn't fit the RA's note or the field comment (-666 "does not know" for a patient who
  died; a note that reads like a different code; -999 with no reason given);
- the note or comment says the value exists ("in the paper chart") — enter it, don't code it;
- an amber cell (confirm the field applies first).

A site whose answers are unusually often codes gets one line in the report. Then:

```bash
python3 "$W/upload_mdc.py" <worklist>.xlsx "<returned>.xlsx" --token-env CRC_TOKEN \
    --comments <field-comment-log>.csv --dry-run
python3 "$W/upload_mdc.py" <worklist>.xlsx "<returned>.xlsx" --token-env CRC_TOKEN \
    --comments <field-comment-log>.csv --upload --expect-project "<project name>" \
    --snapshot-dir qa-specialist/<study>/snapshots
```

The preview shows exactly what would be sent and what was refused, and why. The real upload needs
that same preview, the project named, and saves the before-values first; it refuses any non-code
value and any cell REDCap already holds, then reads the codes back. *No key?* Use
`--records-csv … --metadata-csv … --import-file mdc_import.csv` and upload that file in REDCap's
Data Import Tool (blank values must not overwrite). Checkbox codes are left out of that file — the
RA ticks them.

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

`reconcile_return.py` ends with a block in exactly this shape — paste it in under the site.
Loop with the RA until all questions resolve; re-run the check after each answer.

### Confirm the gaps closed — and where to stop when you can't yet

`reconcile_return.py` is the direct check: every answer is IN REDCAP, or it is a question. To find
**new** gaps, re-run Task 1's build on a fresh export — anything still yellow that the check didn't
already explain is new. Diff against the prior round for a clean "did this round do what we
expected" check.

**If there is no post-RA export, the round stops here — and that is a finished state, not a
failure.** The RAs enter their answers in REDCap, so the only way to see whether a gap closed is
to pull the data again; checking against the old export would report every answer as NOT
ENTERED, and nothing in a returned workbook is evidence that REDCap changed. So:

1. Send the open questions you already have — that work doesn't wait.
2. Ask for a fresh export: either the study's access key in the settings file, or a new Data
   Export + Data Dictionary download ([[getting-files-from-redcap]]).
3. Say plainly what is outstanding — "N cells answered, check pending the next pull" — and stop.
   Don't mark anything as in REDCap, and don't run `reconcile_return.py` against the pre-RA export.

The round closes on the next pull, when every answer checks IN REDCAP or is an open question.

### Send each RA their summary

```bash
python3 "$W/summarize_for_ra.py" \
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
- **No re-upload of RA answers (decided 2026-10-09)** — the RA enters changes in REDCap
  directly so REDCap's branching, validation, and audit trail apply; you check they landed.
  The one QA upload is missing-data codes into blank cells (`upload_mdc.py`). See
  [[redcap-api-gotchas]] §0 and [[access-tiers]] Tier 3. Bulk loads are a separate one-off
  legacy migration: [[migration-push]].

Roadmap (not yet built): source-document audit verification, and a PM-side blocker view that QA
flags should eventually feed into.
