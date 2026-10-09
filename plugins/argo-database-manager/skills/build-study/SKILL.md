---
name: build-study
description: Fulfil a build request — turn a submitted study request into a working REDCap database. Checks the request is ready to build, produces the paste-ready create-project sheet, builds or audits the data dictionary, sets up roles and study files, and ticks each step off on the Study Tracker as it lands so the tracker stays honest. Works with or without an access key. Use when taking a "build this study" item off your request queue, when a study request (SIR) has come in, when picking a half-finished build back up, or when someone asks you to review, audit or fix an existing data dictionary.
allowed-tools: Read, Bash, Write, Glob, Edit, Grep
---

# build-study

One skill for the whole build: **SIR record → live study.** The spine is a feedback loop: each
step that lands flips one `build_tracking` flag on the Study Tracker, right then, so the
portfolio's progress column is true between runs. Never batch the marks at the end.

**How to talk to the user.** Short sentences, plain words.
- **Lead with the decision you need**, then only what they need to make it. About 120 words a
  reply; detail goes in the build folder, not the chat.
- **Two or more decisions pending?** Ask each as a structured choice (the question widget), one
  per decision — not a numbered list of questions in prose.
- **Status = the brief's Outstanding table** (Step 6): every tracker step and every open request,
  each with who and done / not done. Never a paragraph of status, never a second list. When the
  user asks for something that isn't a tracker step, add it to that list the moment they ask; it
  stays until it's done.
- **Ask once.** A value that follows from something already settled is not a new question: it
  rides in the next tracker push, shown in the diff. `contains_phi=1` follows from any identifier
  field in the DD — `sir_update.py --dd <csv>` adds it for you. If the user declines a value, it
  goes on the Outstanding list once and is never offered again. (A live session offered the same
  `contains_phi=1` four times.)
- **"Close out the build"** (also "it's closed", "it's in production") means: tick every
  remaining step and close the tracker form, in one push — `sir_update.py <RID> --close-out`.
  One diff, one confirmation, no per-step questions. The phrase is the sign-off for the human
  gates; anything less explicit is not.

## Access

- **Build progress** goes to the Study Tracker with `sir_update.py --mark-step`, using the
  Study Tracker key (`STUDY_INITIATION_REQUEST`) everyone on the team holds. It needs no
  per-study permission. It is *the* way to mark progress — don't offer a choice.
- **The new study's own project** (creating it, uploading the DD, roles) is done in the REDCap
  website, because OAU has no Super API Token that could create projects for us
  ([[project-no-super-token]]).

No Study Tracker key on this machine? Tick the same `build_tracking` fields by hand in the Study
Tracker, and say that's what you did and why. It's a fallback for a broken setup, not an option.

Every script is located the same way, because plugin paths differ per environment and shell
state doesn't survive between commands — find and run in one command:

```bash
S=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name sir_update.py 2>/dev/null | head -1)
python3 "$S" <RID> --mark-step <flag>
```

The commands below write just the script name; locate it this way first.

## The pipeline ↔ tracker loop

| # | Step | Do this | Script | → flip `build_tracking` |
|---|---|---|---|---|
| 1 | **Triage** | Pull the SIR | `sir_update.py --pull` | *(no flag)* |
| 1b | **Port the documents** | Build folder, pull the documents in, check the hard stop, read them | *(files)* | *(no flag — the hard stop lives here)* |
| 2 | **Create project** | Paste sheet → create in UI | `fill_new_project.py` | `project_created` (+ `--pid`) |
| 3 | **Build DD** | Construct (Path A) or audit (Path B) → upload | `dd_builder.py`, `validate_dd.py` | `dd_uploaded` |
| 4 | **Roles & users** | Roles CSV, DAGs, assign users | `make_roles_csv.py` | `user_rights_complete` |
| 5 | **Data import** | Map + import, or mark prospective | `validate_import.py` | `data_imported` |
| 6 | **Setup** | File Repository, weekly report, survey settings | `setup_brief.py` | *(part of `review_internal`)* |
| 7 | **Review** | Internal QA, then PI sign-off | — | `review_internal`, `review_pi` |
| 8 | **Production** | Move project to Production | — | `study_production` |

**Two kinds of flags.** `project_created`, `dd_uploaded`, `user_rights_complete` and
`data_imported` are facts about what happened — mark them as each lands. `review_internal`,
`review_pi` and `study_production` assert that a *person* reviewed, signed off or cleared the
study for production. Set those only when that person has said so — or the user says "close out
the build". Flipping one early puts a false statement in a live tracker the whole programme reads.

---

## Step 1 — Triage

```bash
sir_update.py <RID> --pull > intake.json
```

`--pull` returns the whole record (intake + `build_tracking` + `study_metadata`). Don't re-ask
for anything the SIR already captured. A blank required field (PI name, `irb_number`,
`irb_approval_expires`) is not a stop: name the field in one line and who fills it — the PM or
requester, on the Study Tracker — and put it on the Outstanding list. (If the approval letter is in
hand, its number and date can be backfilled with `--irb-number` / `--irb-expires`.) What stops a
build is a missing document: the hard stop in Step 1b.

| SIR field(s) | Drives |
|---|---|
| `quest_universal`, `quest_univ_file`, `quest_site_1..10` | Step 3 questionnaire source |
| `data_collection` | Step 5 (retrospective vs prospective) |
| `num_institutions`, `inst_name_*`, `irb_file_*`, `consent_file_*`, `sop`, `eligibility_checklist` | Step 6 File Repository + DAGs |
| `weekly_stat`, `category` | Step 6 weekly report |
| `pm_*`, `ra_*`, `pi_user_*`, `addl_users` | Step 4 user roles |

**One study, several REDCaps.** A study is sometimes split across several SIRs and projects —
different populations, or data analysed separately. Build them **one SIR at a time**, as normal.
But first put the mapping on screen as a table: **which document belongs to which project, and
which projects are still missing one.** Document and project names drift apart fast, and a build
started from the wrong file is done twice. If a document doesn't map onto a project, say so and
ask — don't guess.

**Several SIRs with the same title** aren't necessarily duplicates (build-pitfalls #17): decide
from the *questionnaires*. Different questionnaires → separate builds (ask for a site/substudy
suffix). Identical questionnaire across all → flag a possible resubmission before building N
copies.

## Step 1b — Port the documents into the build folder (before any analysis)

Collect the request's documents first, as one act, so the rest of the build reads from a folder
instead of hunting for files.

1. **Make the folder.**
   ```bash
   mkdir -p database-manager/<study>/questionnaires database-manager/<study>/protocol \
            database-manager/<study>/ethics
   ```
   `<study>` is the study moniker you'll use everywhere else.
2. **Pull the documents in.** The `--pull` output names the files; they sort into the folders:

   | SIR field(s) | → folder |
   |---|---|
   | `quest_univ_file`, `quest_site_1..10` | `questionnaires/` |
   | `sop`, `eligibility_checklist`, the protocol / proposal | `protocol/` |
   | `irb_file_*`, `consent_file_*`, `consent_prof_*` | `ethics/` |

   Look for each file in the workspace first (`Glob`). Ask for everything that isn't there in
   **one** message — the user downloads them from the SIR record in REDCap (open the record → the
   file field → Download) or from the study's File Repository, and drops them in the folder.
3. **Then read them.** Extract the text (`textutil -convert txt -stdout "file.docx"`) and read
   the questionnaire and the protocol before designing anything. Step 3 builds the DD from this
   folder; Step 6 renames these copies for the File Repository.

### Hard stop: no data dictionary until the documents are complete

The build needs three documents before any DD work starts:

1. **the questionnaire** — every one the SIR names (universal and each site's),
2. **the protocol** (or the approved proposal),
3. **the ethics approval letter** — the committee's approval, with its number and date. An
   ethics *application* or submission form is not an approval: it doesn't count.

If any is missing, **stop**. Don't draft a DD, don't build the parts you can, don't proceed on
assumptions — and don't offer "build ahead and mark the gaps TODO" as a choice. In a real build
that offer was taken, and the ethics document that arrived later overturned the DD. Tell the
user in one or two plain sentences what is missing and what to send:

> I can't start the build yet. Missing: the site 2 questionnaire and the ethics approval letter.
> Please add them to `database-manager/<study>/`, or ask the PM to attach them to SIR <RID>.

Why: a DD drafted from part of the documents is rebuilt when the rest arrive, and its guesses
look like decisions to whoever reads it next. A file that is empty or won't open counts as
missing. This list lives here and nowhere else (`setup_brief.py` checks the SIR against the same
three, guard-tested). Other documents — consent forms, SOP, eligibility checklist — don't block
the DD; they are needed for Step 6 and before production.

**Auditing an existing DD (Path B) without the questionnaire:** run `validate_dd.py`, and say the
label-by-label comparison waits for the questionnaire. That isn't a build, so it isn't blocked —
but it isn't a finished audit either.

## Step 2 — Create project → `project_created`

```bash
fill_new_project.py <RID> [<RID> ...] > database-manager/<study>/CREATE_NEW_PROJECT_<RID>.txt
```

A paste-ready "Create New Project" box per record (Empty project; title, purpose, sub-category,
PI cited, IRB, folder, notes all derived). The SIR title is often ALL-CAPS; normalize it to
sentence case in the saved sheet (keep acronyms and proper nouns). The user pastes it into
REDCap → New Project. Once it exists:

```bash
sir_update.py <RID> --pid <PID> --mark-step project_created
```

## Step 3 — Build the data dictionary → `dd_uploaded`

**Path A** constructs from the questionnaire; **Path B** audits an existing CSV ("review",
"audit", "check", "fix"). Read [[build-pitfalls]] first; column reference: [[dd-column-spec]].

**Form or survey — decide now, from the protocol.** It changes the DD (next blocks), so it can't
wait for setup. Default to **data-entry forms**: ARGO's standard model is paper questionnaire →
RA enters. Survey mode only if the protocol says respondents **self-complete** (online link,
app). Being a questionnaire doesn't make it a survey.

**The questionnaire beats the paperwork.** Where the ethics application or another document
says something the questionnaire doesn't (no identifiers, anonymous, a different item list),
build what the questionnaire says and put the discrepancy on the Outstanding list for the PM. It
doesn't change the build.

> ### MDC on every non-exempt field
> Per [[mdc-rules]]: every radio/dropdown/checkbox gets the four MDC **choices**; every
> text/notes field gets the text-format MDC **field note**; any date/datetime validation gets the
> date-format note. Exempt without asking: the record-ID field, descriptive/calc/file types, and
> the study-team admin fields (`hospital_number`, `hospital_site`). `dd_builder.py` applies all of
> this (a Field Note you wrote is kept, with the MDC note appended); a hand-written DD fails the
> validator on dozens of fields. `yesno` is refused at build time: use `radio` with
> `1, Yes | 0, No`.
>
> **Self-completed surveys get no MDC at all** (decided 2026-10-09). MDC records why staff
> couldn't abstract a value; a respondent has no such reason. Build with `DD(survey=True)` /
> `dd_builder.py --survey` and validate with `validate_dd.py --survey`. With the `dd_uploaded`
> push, clear the SIR's `missing_data_codes` boxes (`--set missing_data_codes___<n>=0` for each
> box the `--pull` shows ticked).
>
> **The one per-field waiver:** a validated psychometric / Likert instrument is MDC-exempt by
> ARGO policy — adding codes changes a published instrument. Build those fields with `mdc=False`,
> which writes `@MDC-EXEMPT` into Field Annotation; `validate_dd.py` honours it (on any field of a
> matrix group it waives the whole group). Never use it to quiet MDC on ordinary clinical fields.

> ### Build the instruments the questionnaire defines — don't over-materialize
> Build what the questionnaire contains. A multi-section questionnaire usually becomes one
> instrument per section. Don't fabricate instruments for follow-up rounds, time-points or arms
> the questionnaire doesn't contain — those live in the proposal's design narrative, and
> follow-up interviews are usually a separate instrument from a separate source.
>
> **One exception, and only one: a link-distributed survey** — next block. There the rounds
> *must* become instruments, because a REDCap survey link addresses an instrument. That is a
> mechanical constraint, not a licence to materialize design narrative anywhere else.

> ### A link-distributed survey needs four things the questionnaire never prints
> When respondents **self-complete via a link**, ARGO's convention adds structure the printed
> instrument can't show. **Propose all four as a design — don't raise them as open questions.**
> None changes an approved question, so none is an IRB amendment.
>
> 1. **An email field, when there is more than one round.** It is how REDCap sends the next
>    instrument, so it stays even where the documents say anonymous or "no PHI". On the baseline
>    instrument, **flagged as an identifier**; that makes the project PHI-bearing, so
>    `contains_phi` on the SIR is `1` (pushed with `--dd`, not asked). An anonymous study gets no
>    name fields. (The two `phi_confirm` attestations say the protocol permits storing PHI: those
>    are the PI's to tick, never yours.)
> 2. **One instrument per collection round**, named for the round — baseline, 3-month, 6-month.
>    Not one instrument with a timepoint field: each round needs its own link and invitation
>    schedule. **Read the round schedule off the protocol** and quote the sentence you used.
> 3. **Branching on baseline-versus-follow-up.** A baseline-only question (prior experience,
>    anything asked "before implementation") must not reappear at follow-up; a question that
>    compares against baseline can't be asked *at* baseline.
> 4. **A consent question first, gating everything else.** A link goes out with no one in the
>    room. Use the approved consent form (in `ethics/`, from Step 1b) as the preamble.
>
> A **repeat-measures study that is not a survey** has the parallel gap: if the same record is
> scored more than once — several rounds, or two independent reviewers per case — it needs a
> **round field, a reviewer field and a case identifier**, or the scores can't be paired and
> disagreement can't be measured. Propose these the same way.

> ### The questionnaire is IRB-approved — mirror it, don't improve it
> Only critically essential changes are allowed (IRB amendments). So the DD matches the **printed
> form exactly**: spelling errors, numbering quirks and answer wordings are reproduced as-is. A
> column printed with **no answer options** becomes free text as printed. None of these — typos,
> numbering, wordings, a missing option list — is a change to propose or a question to ask: they
> appear in **neither** of the two deliverables below.
>
> This governs the **questions**, not the scaffolding around them. The survey structure above
> alters no approved question and is no amendment. Mirroring the form and giving it the structure
> REDCap needs are different jobs.
>
> ### The build always makes headway — best guess in, question out
> This is about ambiguity *inside* documents you have — never a way around the hard stop. Once
> the three documents are in, never stall and never drop a field because the form is unclear.
> Branching you can't resolve, an enumeration not spelled out, an implicit unit: put your **best
> guess in the DD** and keep building. Log every guess in **`OPEN_QUESTIONS.md`** in the build
> folder, one entry each, as a question about what you assumed, pointing at the field — *"Q7 /
> `pain_score`: the printed skip is ambiguous; we assumed it only fires on Yes — right?"* These
> are questions about the build's assumptions, never proposed edits to the form. Write the file
> even when you guessed nothing — one line saying so.
>
> **Keep it short enough to answer.** Only items that need an answer: at most three lines each,
> each naming who must answer. **Never list something built as printed** — a typo, a numbering
> quirk, a column with no options, a wording you kept: that is the rule working, not a question.
> (A 70-field survey once got 20 items and 4,289 words, mostly as-printed reproductions; nobody
> can sign that.)
>
> **Rewrite it, never append.** Each revision regenerates the open questions at the top; an
> answered one leaves the list and becomes one line in a "Resolved" log at the bottom (question,
> answer, who, date). The same goes for every status file in the build folder — a stale "open"
> header above a later "resolutions" section reads as still open.
>
> **Escalate down the ladder, not straight to the PI.** Every question costs a round trip with a
> clinician who has a clinic to run:
> 1. **Resolve it from the documents.** The protocol, the SIR, the SOP and the consent settle
>    most of it — round schedules, sites, who self-completes, what the endpoint counts.
> 2. **Ask the database manager, in this session.** They know ARGO's conventions and answer in
>    seconds what would take the PI a week. Design questions belong here.
> 3. **Only then, the PI** — for what needs their authority: clinical meaning, what counts as one
>    item, wording that would need an amendment, any attestation.
>
> The target is a sign-off packet the PI can mostly tick and return. A packet with nine
> questions is a build that stopped early.

> ### Changes the QUESTIONNAIRE itself needs → tracked changes on the original document
> Substantive defects in the form — a skip pointing at a section that doesn't exist, a question
> the SIR commits to that the form lacks, a structural contradiction — aren't your assumptions;
> they're changes the **questionnaire** needs, delivered *on the questionnaire*:
> - **Word original** → the original with **tracked changes**, saved beside it as
>   `<name>_redcap_changes.docx`. Use the **docx skill's tracked-changes support** (real
>   insertions/deletions, a comment on each saying why and whether it needs an IRB amendment).
>   Edit a copy of the original, never a retyped version: the reviewer accepts or rejects each
>   change in their own document.
> - **PDF original** → `<name>_redcap_changes.md` beside it: where, what it says now, what it
>   should say, why, and whether it needs an IRB amendment.
>
> The DD still mirrors the form **as printed** — surfaced on the document, never pre-applied.

**Path A workflow:**
1. Work from `database-manager/<study>/questionnaires/` (Step 1b).
2. Parse into a field list (instruments → forms; bullets → fields; sub-bullets → choices). Labels
   match the Word text **exactly**. Broken choice **codes** (duplicate or non-sequential numbers,
   `99` for Other) do get normalized — that's a DD mechanic, not a change to the form. Say so in
   the run per [[decision-protocol]], and log it in `OPEN_QUESTIONS.md` if you had to guess the
   intended code. Grids of same-scale items → a **matrix group** (shared `Matrix Group Name` +
   identical choices).
3. Emit with `dd_builder.py`, never a hand-written CSV — import its `DD` class or feed a JSON
   spec: `dd_builder.py fields.json out.csv` (add `--survey` for a self-completed survey).
4. Save as `database-manager/<study>/<Project>_DataDictionary_<YYYY-MM-DD>.csv`. The first field
   is the record ID (a meaningful name, not always `record_id` — [[record-id-safety]]).
   Patient-level DDs also get `hospital_number` (identifier); surveys and non-patient-level DDs
   skip it.
5. Validate: `validate_dd.py <csv>` (`--patient-level` requires `hospital_number`; `--survey`
   expects no MDC).
6. **Show the structure back, unprompted.** A validated DD says the CSV is well-formed, not that
   it is the right study. End every build and rebuild with a short **structure table**:
   instrument by instrument, field count, what branches on what, and every field you added that
   isn't on the printed form, with why. It is how the database manager confirms the build before
   anything is uploaded.

**Path B (audit):** run `validate_dd.py`, then compare field by field against the questionnaire.
Sort findings CRITICAL / ERROR / WARNING, present them, fix via Edit (justify each), re-validate
to clean. Check: duplicate/missing fields, choice-code mismatches, MDC gaps, `yesno` (→ radio),
branching, identifier flags, exact labels. Sister studies (same PI/HREC, separate SIRs) must
share instrument structure — run `make_roles_csv.py` on both and compare `Forms detected`.

The user uploads the clean CSV via Designer → Upload Data Dictionary. Then mark it, passing the
DD so `contains_phi` follows from its identifier flags:
`sir_update.py <RID> --mark-step dd_uploaded --dd <csv>`.

**Revised the DD after upload?** The step isn't done any more — the project holds the old one.
Reset it at once with `sir_update.py <RID> --unmark-step dd_uploaded`, and mark it again only
when the user confirms the new CSV is uploaded. ("The tracker says done and the project isn't.")

## Step 4 — Roles & users → `user_rights_complete`

```bash
make_roles_csv.py <path-to-DD-CSV> [--clinical form1,form2,...] [--out path]
```

Writes `<study>_roles.csv` — the 4 standard ARGO roles ([[standard-roles]]) — next to the DD. No
key needed. Study Builder and Project Manager export with identifier fields removed (decided
2026-10-09), so the DD's `Identifier?` flags are what keep identifiers out of their exports. The
user uploads it at **User Rights → User Roles → Upload user roles (CSV)**; REDCap generates the
`unique_role_name` values. Multi-site study: create one Data Access Group
per institution (`inst_name_*`) on the same page.

People are then added in the REDCap UI. We don't know anyone's real REDCap username, so present
who→role as a table for the user to work from — never generate an assignment file. Someone with
no REDCap account needs an administrator to create one: log them in the Study Personnel Request
tracker (PID 221).

Mark `user_rights_complete` once roles are uploaded and users assigned.

## Step 5 — Data import → `data_imported`

- **Prospective** (`data_collection` = prospective): nothing to import —
  `sir_update.py <RID> --set data_imported=2`.
- **Retrospective data exists:** map the source to `import_ready.csv` (the questionnaire is
  canonical — reshape the source to fit the DD; blanks stay blank, never MDC-filled), check it
  with `validate_import.py <dd_csv> import_ready.csv` (branching-aware), and the user imports it
  in the REDCap UI (Data Import Tool → review changes before saving). Then
  `sir_update.py <RID> --mark-step data_imported`.

## Step 6 — Setup and the outstanding list (the MANUAL_SETUP_BRIEF)

```bash
setup_brief.py <RID> --out database-manager/<study> --moniker <Moniker>
```

Add `--from-json intake.json` to work from the Step 1 pull without a key. The brief opens with
the **Outstanding** table: the 7 tracker steps in tracker order, each with what to do, who does
it, what it waits on, and done / not done read from the Study Tracker. Setup work the tracker
has no flag for — File Repository, weekly report, survey settings — sits inside
`review_internal`, because it has to be finished before the internal check.

Then come the user's own requests that aren't tracker steps ("mark the identifiers so exports
drop them"), read from `outstanding_requests.csv` in the build folder (columns `item, who,
waiting_on, status`). Add a row the moment the user asks; set `status` to `done` when it is.
In a real build such a request vanished from the final status because it lived only in the chat.

This table is the build's status. Regenerate the brief after every mark or request and show the
table whenever the user asks where things stand — including "are we done?". The brief is
rewritten whole each run, never edited by hand.

Below the table the brief derives, from the SIR: the File Repository rename table (each document
**renamed with the study moniker**, into Study Documents vs IRB and Ethics; site-numbered files
take their site tag from this study's own `inst_name_*` — a blank institution is a `[TODO]`,
never a site name from elsewhere), the DAGs, the user→role table, the survey-setup clicks, and
the IRB flags. Review it; a blank the SIR should hold is named with who fills it (Step 1).

The study's folder ends up self-contained for handoff: the Step 1b document folders, the DD CSV,
the roles CSV, `CREATE_NEW_PROJECT_<RID>.txt`, the staged `file-repository/` folder,
`OPEN_QUESTIONS.md` (always), any `<name>_redcap_changes.docx` / `.md` beside the questionnaire
it marks up, and `MANUAL_SETUP_BRIEF.md`.

## Steps 7–8 — Review → Production

Human gates (see "Two kinds of flags"): confirm with the responsible person before each.
- `review_internal` — setup finished and the build checked.
- `review_pi` — PI sign-off.
- **Before `study_production`:** check `irb_approval_expires` against today. If it has passed,
  the approval has lapsed: flag it and don't move to production until the renewal is confirmed
  (backfill with `--irb-expires`). A *blank* `irb_number` or `irb_approval_expires` is a warning,
  not a stop: name the field and that the PM / requester updates it on the Study Tracker, and
  keep it on the Outstanding list (`sir_update.py` warns too). Then Project Setup →
  Move to Production, and mark `study_production` — the portfolio's "done" signal.

---

## sir_update.py — the Study Tracker tool

Every Study Tracker write goes through it — never a hand-written `import_records` call. It
confirms the key opens the Study Tracker, shows the current values and the diff, and asks before
writing. In a session with no keyboard it stops at
the question: show the user the change yourself, get their OK, then re-run with `--yes` (or
`ARGO_ASSUME_YES=1`). Dates are `YYYY-MM-DD` ([[redcap-date-import]]).

```bash
sir_update.py <RID> --pid 242 --mark-step project_created
sir_update.py <RID> --mark-step dd_uploaded --dd <csv>
sir_update.py <RID> --irb-number IPH/OAU/12/3275 --irb-expires 2027-04-16   # any time
```

`--mark-step` is the normal flow — one step, one push, as it happens. When the 7th step lands it
also sets the `build_tracking` form to Complete. `--close-out` is the one-push ending (above).
Other flags: `--pull`, `--pid`, `--status`, `--irb-number` / `--irb-expires`, `--yes`,
`--dd <csv>` (adds `contains_phi=1` when the DD flags an identifier), `--close-out`,
`--unmark-step <step>` (a step that stopped being true — Step 3), `--reopen` (clears
`study_production`, status back to Building).

**Escape hatches — not the normal flow.** Each can move a study to "done" in one go, which is why
none is a routine close-out:

| Flag | Only for | Rule |
|---|---|---|
| `--mark-built` | Recording a build finished outside ARGO | Flips all 7 steps, including the three human gates. Only when the responsible person has confirmed all three |
| `--close` | Opening a production study to accrual | Sets `study_production` + status Open to accrual. Same rule |
| `--set F=V` | `data_imported=2` for a prospective study (Step 5); clearing a survey's `missing_data_codes` boxes with the `dd_uploaded` mark (Step 3); fixing one wrong value | Outside those it bypasses the step-by-step record the tracker exists to keep |

## Scripts in this skill

`fill_new_project.py` (Step 2) · `dd_builder.py` + `validate_dd.py` (Step 3) ·
`make_roles_csv.py` (Step 4) · `validate_import.py` (Step 5) · `setup_brief.py` (Step 6) ·
`sir_update.py` (the tracker tool) · `backfill_sir_from_csv.py` — a one-off bulk load from the
retired Active Databases sheet, not part of the per-study loop. Its record matching is hardcoded
to that migration, so don't point it at a new spreadsheet; it writes nothing without both
`--commit` and `--record-id-range`.

The **docx skill** produces the Step 3 `<name>_redcap_changes.docx` — it can put real tracked
changes into a Word document. Don't hand-roll that file.

## Not here

- **Adding people to a live project** → the REDCap UI, the study's User Rights page. There is no
  add-users skill; the people queue in [[weekly-check]] says what to do.
- **Seeing what's waiting to be built** → [[weekly-check]] ("what's waiting for me").

## References

[[build-pitfalls]] (read first) · [[mdc-rules]] · [[dd-column-spec]] · [[token-optional]] ·
[[token-confirmation]] · [[record-id-safety]] · [[redcap-date-import]] · [[redcap-api-gotchas]] ·
[[standard-roles]] · [[decision-protocol]]
