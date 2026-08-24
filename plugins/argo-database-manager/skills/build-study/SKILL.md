---
name: build-study
description: Fulfil a build request — turn a submitted study request into a working REDCap database. Checks the request is ready to build, produces the paste-ready create-project sheet, builds or audits the data dictionary, sets up roles and study files, and ticks each step off on the Study Tracker as it lands so the tracker stays honest. Works with or without an access key. Use when taking a "build this study" item off your request queue, when a study request (SIR) has come in, when picking a half-finished build back up, or when someone asks you to review, audit or fix an existing data dictionary.
allowed-tools: Read, Bash, Write, Glob, Edit, Grep
---

# build-study

One skill for the whole build pipeline: **SIR record → live study.** It merges what used to be two
skills (intake triage + DD build). The spine is a feedback loop — **every pipeline step you finish
lets you flip one `build_tracking` flag on the Study Tracker, so the portfolio gets more accurate
in real time.** Mark as you go; never batch at the end.

## Which access this skill needs (read first)

Two different things get confused here, so be precise ([[access-tiers]]):

- **Writing build progress to the Study Tracker** uses your Study Tracker access key
  (`STUDY_INITIATION_REQUEST`) — one of the five tracker keys everyone on the team has. It needs
  no per-study permission from anyone. `sir_update.py --mark-step` is **the** way to mark
  progress; do not offer the user a choice about it.
- **Anything against the new study's own project** (creating it, uploading the DD) is done in the
  REDCap website regardless, because OAU has no Super Token ([[project-no-super-token]]).

If the Study Tracker key genuinely isn't configured on this machine, fall back to setting the same
`build_tracking` yes/no fields by hand in the Study Tracker — but say that's what you're doing and
why. That's a fallback for a broken setup, not an equal option to present each time.

## The pipeline ↔ tracker loop

| # | Step | Do this | Script | → flip `build_tracking` |
|---|---|---|---|---|
| 1 | **Triage** | Pull the SIR; is there enough to build? | `sir_update.py --pull` | *(gate — no flag)* |
| 2 | **Create project** | Paste sheet → create in UI | `fill_new_project.py` | `project_created` (+ `--pid`) |
| 3 | **Build DD** | Construct (Path A) or audit (Path B) → upload | `dd_builder.py`, `validate_dd.py` | `dd_uploaded` |
| 4 | **Roles & users** | Roles CSV + assign users | `make_roles_csv.py` | `user_rights_complete` |
| 5 | **Data import** | Map + import, or mark prospective | `validate_import.py` | `data_imported` (1 / 2) |
| 6 | **Setup** | File Repository, weekly reports, DAGs | *(MANUAL_SETUP_BRIEF)* | *(part of setup)* |
| 7 | **Review** | Internal QA, then PI sign-off | — | `review_internal`, `review_pi` |
| 8 | **Production** | Move project to Production | — | `study_production` |

After each step, immediately — find the script first, then run it:

```bash
S=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name sir_update.py 2>/dev/null | head -1)
python3 "$S" <RID> --mark-step <flag>
```

One push per step, never batched at the end — that's what keeps the portfolio's progress column
honest between runs.

> ### Two kinds of flags — treat them differently
> - **Mechanical** (`project_created`, `dd_uploaded`, `data_imported`): objective facts about what
>   happened. The agent marks these directly as each step lands.
> - **Sign-off / go-live gates** (`review_internal`, `review_pi`, `study_production`): these assert
>   that a *human* reviewed/approved, or that the study is live. **Never auto-flip them.** Set them
>   only on explicit confirmation from the responsible person (internal QA done / PI signed off /
>   cleared for production). Flipping them early puts false state in a live tracker — and is wrong.

---

## Step 1 — Triage (is there enough to build?)
```bash
set -a; source ~/.argo/.env; set +a
S=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name sir_update.py 2>/dev/null | head -1)
python3 "$S" <RID> --pull > intake.json
```
`--pull` returns the full record (intake + `build_tracking` + `study_metadata`). The build-readiness
gate: a **questionnaire attached** (the linchpin for Path A), plus PI and IRB number. If the
questionnaire is missing, flag back to the PM — don't build. Don't re-ask for anything the SIR
already captured. Key fields drive later steps:

| SIR field(s) | Drives |
|---|---|
| `quest_universal`, `quest_univ_file`, `quest_site_1..10` | Step 3 questionnaire source |
| `data_collection` | Step 5 (`data_imported`: retrospective vs prospective) |
| `num_institutions`, `inst_name_*`, `irb_file_*`, `consent_file_*`, `sop`, `eligibility_checklist` | Step 6 File Repository + DAGs |
| `weekly_stat`, `category` | Step 6 weekly reports |
| `pm_*`, `ra_*`, `pi_user_*`, `addl_users` | Step 4 user roles |

## Step 2 — Create project → `project_created`
```bash
S=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name fill_new_project.py 2>/dev/null | head -1)
python3 "$S" <RID> [<RID> ...]
```
Outputs a paste-ready "Create New Project" box per record (Empty project; title, purpose,
sub-category, PI cited, IRB, folder, notes all pre-derived). **Save it** to the study's folder
(`database-manager/<study>/CREATE_NEW_PROJECT_<RID>.txt`) — don't just print it. The SIR title is
often ALL-CAPS; normalize to sentence case (preserve acronyms/proper nouns) for the project title.
The user pastes it into REDCap → New Project. Once it exists, mark it on the tracker:

```bash
S=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name sir_update.py 2>/dev/null | head -1)
python3 "$S" <RID> --pid <PID> --mark-step project_created
```

**Multiple SIRs, same title:** decide from the *questionnaires*, not the title (build-pitfalls #17).
Different questionnaires → separate builds (ask the user for a site/substudy suffix); identical
questionnaire across all → flag possible resubmission before building N copies.

## Step 3 — Build the data dictionary → `dd_uploaded`

**Path A (construct from Word)** vs **Path B (audit an existing CSV)**. If the user says "review",
"audit", "check", or "fix", use Path B.

> ### MDC goes on EVERY non-exempt field — not just clinical Yes/No
> Per [[mdc-rules]]: every radio/dropdown/checkbox gets the four MDC **choices**; every
> text/notes field gets the text-format MDC **field-note**; any date/datetime validation gets the
> date-format note. Exempt without asking: the **record-ID field**, **descriptive/calc/file**
> types, and the study-team admin fields (`hospital_number`, `hospital_site`).
> `dd_builder.py` applies this automatically (and keeps a Field Note you wrote, appending the MDC
> note to it) — hand-write a DD and the validator will flag dozens of fields. `yesno` is refused at
> build time: use `radio` with `1, Yes | 0, No`.
>
> **The one waiver:** a validated psychometric / Likert instrument is MDC-exempt by ARGO policy.
> Build those fields with `mdc=False`, which writes `@MDC-EXEMPT` into the Field Annotation column;
> `validate_dd.py` honours that annotation (put it on any field of a matrix group and the whole
> group is waived). Never use it to dodge MDC on ordinary clinical fields.

> ### Build the instruments the questionnaire defines — don't over-materialize
> Build exactly what the questionnaire in front of you contains. A multi-section questionnaire
> usually becomes **one instrument per section** (Section A/B/C…). Do NOT fabricate extra
> instruments for follow-up rounds, time-points, or study arms that the questionnaire itself
> doesn't contain — those live in the proposal's *design* narrative, and the follow-up interviews
> are typically a **separate instrument from a separate source**, built separately. Read the
> proposal to understand administration mode (form vs survey, Step 6) and design, but materialize
> only the instrument(s) the questionnaire actually defines.

> ### The questionnaire is IRB-approved — mirror it, don't improve it
> Only critically essential changes to a questionnaire are allowed (IRB amendments). So the
> data dictionary matches the **printed form exactly**: spelling errors, numbering quirks, and
> answer wordings are reproduced as-is, never fixed and never flagged. A column printed with
> **no answer options** becomes free text as printed — not a proposed coded list. What you DO
> surface: substantive defects — skip instructions pointing at sections that don't exist,
> questions the SIR commits the study to that the form lacks, structural contradictions — as a
> **QUESTIONNAIRE_CHANGELOG.md** in the build folder, each item marked "needs IRB amendment:
> yes/no", for the database manager and PI to decide. Surfaced, never applied.

**Path A workflow:**
1. `Glob *.docx`; extract: `textutil -convert txt -stdout "file.docx"`.
2. Parse into a field list (instruments → forms; bullets → fields; sub-bullets → choices). Labels
   must match the Word text **EXACTLY**; but normalize broken choice **codes** (duplicate/non-
   sequential numbers, `99` for Other) and flag those per [[decision-protocol]]. Grids of same-scale
   items → a REDCap **matrix group** (shared `Matrix Group Name` + identical choices).
3. Emit with `dd_builder.py` (do NOT hand-write the CSV) — import its `DD` class or feed a JSON spec:
   ```bash
   B=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name dd_builder.py 2>/dev/null | head -1)
   python3 "$B" fields.json out.csv
   ```
4. Save `database-manager/<study>/<Project>_DataDictionary_<YYYY-MM-DD>.csv`; first field is the
   record ID (meaningful name, not always `record_id` — [[record-id-safety]]). Patient-level DDs
   also get `hospital_number` (identifier); surveys/non-patient-level skip it.
5. Validate before upload:
   ```bash
   V=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name validate_dd.py 2>/dev/null | head -1)
   python3 "$V" <csv>
   ```

**Path B (audit):** run `validate_dd.py`, then compare field-by-field against the Word source.
Categorize CRITICAL / ERROR / WARNING, present, fix via Edit (justify each), re-validate to clean.
Check: duplicate/missing fields, choice-code mismatches, MDC gaps, `yesno` (convert to radio),
branching, identifier flags, exact labels. Sister studies (same PI/HREC, separate SIRs) must share
instrument structure — run `make_roles_csv.py` on both and compare `Forms detected`.

User uploads the clean CSV via Designer → Upload Data Dictionary. Then mark `dd_uploaded`. **Full DD
column reference: [[dd-column-spec]]. Read [[build-pitfalls]] first.**

## Step 4 — Roles & users → `user_rights_complete`
Build the roles file — no access key needed, this is the normal path:

```bash
M=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name make_roles_csv.py 2>/dev/null | head -1)
python3 "$M" <path-to-DD-CSV> [--clinical form1,form2,...] [--out path]
```

It writes `<study>_roles.csv` — the 4 standard ARGO roles ([[standard-roles]], which also
carries REDCap's exact column order and the access-level codes) — next to the data dictionary,
i.e. in `database-manager/<study>/`. The user uploads it at **User Rights → User Roles → Upload
user roles (CSV)**; REDCap generates the `unique_role_name` values on upload.

Then people are added to those roles **in the REDCap UI**, on the same User Rights page. We
don't know anyone's real REDCap username, so present who→role as a table for the user to work
from — never generate an assignment file. Someone with no REDCap account at all needs an
administrator to create one: record that in the Study Personnel Request tracker (PID 221).

Mark `user_rights_complete` as soon as the roles are uploaded and users assigned.

## Step 5 — Data import → `data_imported`
Prospective study (`data_collection` = prospective) → no historical data: `--set data_imported=2`.
Retrospective data exists → map source → `import_ready.csv`, validate with `validate_import.py`
(branching-aware), import via `content=record`, then `--set data_imported=1`.

## Step 6 — Setup: File Repository, weekly reports, DAGs (the MANUAL_SETUP_BRIEF)
Generate the per-study UI checklist with `setup_brief.py`:
```bash
B=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name setup_brief.py 2>/dev/null | head -1)
python3 "$B" <RID> --out database-manager/<study> --moniker <Moniker>
```
It derives — from the SIR record — the File Repository rename table, the Data Access Groups, the
user→role table, the IRB-expiry flag, and the `build_tracking` commands, so the manual work is
copy-paste-and-click. (Works without an access key too: add `--from-json rec.json` to run from a
`sir_update.py --pull` dump.) Review/augment the generated brief, which covers:
- **File Repository:** the `irb_file_*` / `consent_file_*` / `sop` / `eligibility_checklist` /
  questionnaire docs, each **renamed with the study moniker**, into Study Documents vs IRB/Ethics.
  Site-numbered documents take their site tag from this study's own `inst_name_*` institutions —
  a blank institution becomes a `[TODO]` in the rename table, never a site name from elsewhere.
- **Data Access Groups:** one per institution (`inst_name_*`) for multi-site studies; assign users.
- **Weekly reports:** from `weekly_stat` / `category` (skip/confirm with PM if blank).
- **Form vs survey:** default to **data-entry forms** — ARGO's standard model is paper
  questionnaire → RA enters. Only enable **survey mode** if the protocol/methods explicitly say
  respondents *self-complete* (online link / app). Don't infer "survey" from the instrument being a
  questionnaire — check the proposal. (Check the proposal for study **design** too, but build only
  what the questionnaire contains — see Step 3's over-materialize note.)
Flag anything the SIR leaves blank (PM not named, roles for co-investigators, etc.) as TODO.

The study's folder under `database-manager/` should end up self-contained for handoff: the DD CSV,
the roles CSV, the `CREATE_NEW_PROJECT_<RID>.txt` paste sheet, the renamed File Repository docs,
the `QUESTIONNAIRE_CHANGELOG.md` (Step 3 — "none found" if there was nothing to raise), and the
`MANUAL_SETUP_BRIEF.md`.

## Steps 7–8 — Review → Production
These are **human sign-off / go-live gates** (see the flag note above) — confirm with the
responsible person before flipping each; never auto-mark them.
- `review_internal` — internal QA pass on the built project.
- `review_pi` — PM/PI sign-off.
- **Before `study_production`:** check `irb_approval_expires` against today's date — if it's
  **past**, the approval has lapsed: flag for renewal and do NOT move to production until confirmed
  (backfill the renewed date via `--irb-expires`). Also confirm `user_rights_complete`. Then Project
  Setup → Move to Production (`study_production` — the portfolio's "done" signal).

---

## sir_update.py — the Study Tracker tool
All build-state writes go through it (confirms the project is the Study Tracker before writing;
shows a diff and pauses). Dates are `YYYY-MM-DD` on import ([[redcap-date-import]]).

```bash
S=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name sir_update.py 2>/dev/null | head -1)

# mark steps as they land
python3 "$S" <RID> --pid 242 --mark-step project_created
python3 "$S" <RID> --mark-step dd_uploaded
python3 "$S" <RID> --mark-step user_rights_complete --set data_imported=2
# IRB backfill any time
python3 "$S" <RID> --irb-number IPH/OAU/12/3275 --irb-expires 2027-04-16
```
### Which flag to use when

`--mark-step` is **the** way progress reaches the tracker, from the first step to the last —
including the final one. There is no separate "finish the build" command in the normal flow: you
mark `study_production` with `--mark-step` like every other step, once the responsible person has
confirmed it ([[access-tiers]]).

| Situation | Use | Why |
|---|---|---|
| A build step just landed — including the last one | `--mark-step <field>` | One step, one push, as it happens. This is the whole normal flow |

**Escape hatches — not part of the normal flow.** Each of these can move a study to "done" in one
go, which is exactly why none of them is a routine close-out path:

| Flag | Only for | Warning |
|---|---|---|
| `--mark-built` | Retro-recording a build that was completed outside ARGO | It flips the human sign-off gates (`review_internal`, `review_pi`, `study_production`) in one shot. Run it only when the responsible person has confirmed all three |
| `--close` | A study going live whose build was already marked complete | Sets production + open to accrual. Same rule: confirm with the responsible person first |
| `--set F=V` | Fixing one wrong value after the fact | Bypasses the step-by-step record the tracker exists to keep |

Other flags: `--pull`, `--pid`, `--status`, `--irb-number/--irb-expires`, `--reopen`.

If the Study Tracker key isn't configured, set the same `build_tracking` fields by hand in the
Study Tracker and say so — see the access note at the top of this skill.

## Scripts in this skill
`fill_new_project.py` (Step 2 paste sheet) · `dd_builder.py` + `validate_dd.py` (Step 3 build) ·
`make_roles_csv.py` (Step 4 roles CSV) ·
`validate_import.py` (Step 5) · `setup_brief.py` (Step 6 MANUAL_SETUP_BRIEF generator) ·
`sir_update.py` (the tracker tool) ·
`backfill_sir_from_csv.py` (bulk SIR loads from a spreadsheet — not part of the per-study loop;
requires an explicit `--record-id-range` before it will write anything).

## Not here
- **Adding people to a live project** → the REDCap UI, on the study's User Rights page. There
  is no add-users skill; the people queue in [[weekly-check]] says what to do.
- **Seeing what's waiting to be built** → [[weekly-check]] (say "what's waiting for me"), which
  shows programme status and your open queues in one run.

## References
[[build-pitfalls]] (READ FIRST) · [[mdc-rules]] · [[dd-column-spec]] · [[token-optional]] ·
[[token-confirmation]] · [[record-id-safety]] · [[redcap-date-import]] · [[redcap-api-gotchas]] ·
[[standard-roles]] · [[decision-protocol]]
