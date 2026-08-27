# Plan to Monday (2026-08-24) — written 2026-08-20 after a churn day

Read this first after any context compaction. It is the agreed state and plan.

## CURRENT STATE + TODO (updated 2026-08-24 — supersedes the phase details below)

**Live on Cowork (0.17.1), all passed:** onboarding ×2, returning user, analyst Table 1
(numbers verified), QA worklists (cells verified), queue landing, a REAL study build (study 17:
309 fields from File-Repository questionnaires), documents from a real protocol (parked for
collaborator review), QA audit (worked by improvisation → fixed), export/QA with no key.

**0.20.0 is RELEASED (652 tests) — org refresh pending. LEDGER.md is the status doc.** Five slices +
Tier 1.5 walkthroughs: eight tasks walked through by subagents on the new code, persona-answered,
**8/8 pass, every number matched engineered truth**. They found 21 more defects (NITS 19–39,
incl. a security-shaped one: --check posted any `*_TOKEN` env var to REDCap); all fixed or in
the pre-release fix batch. Q/A logs for Matteo's review: testing/walkthroughs/REVIEW-2026-08-24.md.

**The reorg in 0.17.2:** database manager = `weekly-check` (status + queues, absorbed the old
monitor-studies + queue) → `build-study` → `export-data` → `link-data`; `manage-redcaps`
retired (add-users wiped; roles CSV lives in build-study); PM = `new-study-documents` only.
Lenient progress rule everywhere. Language preflight (Python/R/Stata) in --check and
run-analysis. IRB changelog rule in build-study.

Next, in order:
1. DONE: 0.17.2 released. **Matteo: org refresh (plugin names unchanged from 0.17.0).**
2. Matteo reviews REVIEW-2026-08-24.md: are the QUESTIONS right? Adjust skills accordingly.
3. Cowork sweep on 0.17.2, from a WIPED workspace, user-provided data only
   (~/Desktop/ARGO-test-data is the kit): (a) fresh setup incl. the Analysis-tools line;
   (b) widget correctness per question; (c) wire weekly-check as a Cowork scheduled task
   (template: weekly-check/references/scheduled-weekly-check.md); (d) study-17 step-marking
   writes when the project exists.
4. Windows probe (friend's machine; ARGO-test-data/WINDOWS-PROBE.md) → fixes → SETUP.md
   Windows section.
5. Matteo: OAU batch key request (send first — longest lead time).
6. Fri/Sat: one-page handout; demo = onboarding + analyst rounds.

## Honest stocktake

**Proven live, witnessed in real Cowork sessions:**
- The full core journey, once, end to end (round 5 + continuation): onboarding → scaffold into
  the connected folder → key flow (file card, `Add keys here`) → "all five keys work" →
  **live portfolio against REDCap from inside Cowork**. This is the demo. It already happened.
- Plugins load on every surface tested; `argo-core:start-here` answers every time
  (standalone skill retired on that evidence, 0.14.0).
- The test loop works: `testing/cowork/round.py` prepare/collect, full transcript mining from
  `~/Library/Application Support/Claude/local-agent-mode-sessions/`.
- Toolkit internals: 104 tests, vendored self-contained skills, runtime version stamp
  (`ARGO toolkit X.Y.Z` in --ensure/--check output), release gate on tests.

**Never yet witnessed live (the verification debt):**
- The polished *returning-user* one-liner ("your five tracker keys connect", no add-keys
  option) — built across 0.15.3–0.16.3, every attempt to see it burned on version lag or bugs.
- The analyst round (Table 1 from the staged CRC export). Staged repeatedly, never run.
- QA and builder rounds. Never run.

**Why the loop devolved:** releases outpaced rounds. Each round tested stale code; each
failure triggered another release; the org-refresh step became the recurring point of failure.
The version stamp (0.16.0) finally makes staleness visible in-session.

## The freeze

**Toolkit is FROZEN at 0.16.3.** No releases until either (a) the re-review batch, or (b) a
round exposes a genuine showstopper. Nits found during rounds get LOGGED in
`testing/cowork/NITS.md`, not fixed inline. One fix-batch maximum per day, released as one
version, then rounds continue against it.

## THE PRODUCT SPEC (Matteo, 2026-08-20) — Phase 1 implements this

**Entry point (role-first, not task-first):** "set up ARGO" → asks WHO YOU ARE. Core members
(the four roles below) get solicited to add API keys as part of onboarding. Then the workspace
is created and they land in their role.

| Role | Does | Keys | Skills |
|---|---|---|---|
| **Project manager** | Builds study documents for new studies; submits new study requests | Study Tracker key (templates) | new-study-documents |
| **QA specialist** | Builds and audits RA worklists for their assigned study | 5 trackers + THEIR study's key | qa-worklists |
| **Database manager** | Owns monitoring: the weekly check (programme status + outstanding requests) → routed to the steps to fulfil them. Builds REDCaps, exports data, **links data (the big one)**. Adding people is a REDCap-UI job | 5 trackers + study keys as needed | weekly-check, build-study, export-data, link-data |
| **Data analyst** | Standard REDCap outputs (downloaded, NO API key); cleaning, analysis, QA; linkage when merging >1 database for analysis; Stata/R/Python; figures | none | run-analysis (+link-data read-side) |

**Decided:** workspace uses ROLE-NAMED folders — `project-manager/ qa-specialist/
database-manager/ data-analyst/` — each role's outputs land in their own folder (skills'
write-paths updated accordingly; scaffold, README, harness fixtures follow). Roles are remembered
via `ARGO_ROLES=` (comma list — people hold several) in the settings file; who-are-you is
asked once.

**Refinements (Matteo, pre-compact):**
- **Subskills are task-shaped within their role.** The role is the door; behind it, each skill
  is shaped around that role's actual tasks (PM: monitor / draft the document package / submit
  the request; DB manager: see outstanding requests -> fulfil one: build / add users / export /
  link; QA: build worklists / audit returns; analyst: clean / analyse / figure). Skill
  descriptions and internal structure follow the task, not the API surface.
- **A user can hold MULTIPLE roles** — `ARGO_ROLES=` (comma list) in the settings file. The
  door offers their roles' entry points; asks who-are-you only when unset.
- **argo-core is plumbing, not a destination.** It keeps the cross-role machinery (client,
  setup, references, start-here) but is minimally invoked directly — its capabilities surface
  THROUGH the appropriate role skill. Nothing in core should compete with role skills for
  triggers (start-here excepted: it IS the door).

Notes: DB manager merges what the README called "Builder"+"Data management" — the plugins stay
as-is; roles are the routing layer. DB manager's front door is the REQUEST QUEUES (personnel /
data / linking requests from the trackers) → route into the fulfilment skill. RAs are not a
role here — QA specialists build FOR them; keep the lightweight RA pointer.

## Phase 1 — re-review + ROLE RESTRUCTURE (one batch, 0.17.0) — DONE 2026-08-20

Shipped as 0.17.0: three parallel whole-read reviews (argo-core; pm+qa; build+data+analysis)
found and fixed — start-here rewritten role-first with `ARGO_ROLES=` memory and
`--set-roles`; role-named workspace folders everywhere (scaffold, README, gitignore, every
skill's write paths); qa-worklists rebuilt task-shaped (its audit task was buried inside the
deprecated push section; push extracted to references/migration-push.md); manage-redcaps
inverted to CSV-upload-first; all `${CLAUDE_PLUGIN_ROOT}` user commands replaced with
locate-by-find; stale key policy purged everywhere (incl. the client's self-contradicting
study-key blocks and a `--check`-without-`--dir` no-op bug); `open_requests.py` added as the
DB-manager landing (metadata-driven queues over 221/222/223/224); marketplace descriptions now
sync from plugin.json via release.py + drift test; SETUP.md and README rewritten. Remaining
loose ends logged in testing/cowork/NITS.md.

**Also in 0.17.0 (Matteo, mid-batch): one plugin per role.** argo-build + argo-data merged;
plugins renamed to the roles in full — `argo-core`, `argo-project-manager`,
`argo-qa-specialist`, `argo-database-manager`, `argo-data-analyst` — and skills renamed
task-shaped: `monitor-studies`, `new-study-documents`, `qa-worklists`, `build-study`,
`manage-redcaps` (widened: task 1 = monitor the core tracking REDCaps / outstanding requests
via open_requests.py, task 2 = access management), `export-data`, `link-data`, `run-analysis`.
*(History: 0.17.2 renamed `monitor-studies` to `weekly-check` and moved it to the database
manager, and retired `manage-redcaps` — see the TODO block above.)*
ORG ACTION REQUIRED with the refresh: the managed-settings enabledPlugins list changed —
five plugins now, new names (JSON in SETUP.md).

## Phase 1 (original scope, for reference)

The whole-read review AND the role-first entry, shipped together as one coherent version:
start-here rewritten role-first; scaffold + README aligned; each role's landing experience
defined (PM → portfolio; QA → key check + worklist flow; DB manager → outstanding requests;
analyst → point me at your export).

Read every SKILL.md **whole**, end to end — all 9 skills + start-here + key references
(access-tiers, token-optional, verify-install). The two worst recent bugs were caught by
whole-reads, not diffs. Looking for: internal contradictions from layered edits, stale policy
references (key policy changed twice), instructions that fight the ask-first rule.
Output: ONE batch release (0.17.0). Root hygiene done 2026-08-20: VERIFY.md pointer and the
argo-skill ghost directory deleted. Phase 1 also rewrites SETUP.md (currently
Claude-Code-first and pre-roles) to match the role spec and Cowork-first reality.

## Phase 1.5 — role feasibility suite on SYNTHETIC data (freeze-compatible: tests, not plugins)

Two-tier verification, replacing "Cowork is the only test of the workflows":

**Tier 1 — automated, local, deterministic.** A committed synthetic study at
`testing/fixtures/synthetic-study/`: REDCap-format data dictionary + records (DAGs, branching
incl. unquoted + numeric comparisons, checkboxes, MDC sentinels, engineered missingness), a
linkage source with engineered overlaps/conflicts, concept note, qa fields config, intake
JSON — all generated by a SEEDED committed generator, with a MANIFEST.json stating exact
engineered counts so tests assert numbers, not vibes. On top: per-role feasibility tests
(QA: worklists→audit round-trip; DB manager: validate_dd/dd_builder/roles-csv/diff_payload;
analyst: data supports a scripted Table 1; PM: scriptable parts) wired into run_all.py.
No patient data anywhere in fixtures or rounds thereafter.

**The per-role/task INPUT INVENTORY (define post-compaction — the "what is this, in essence"
question).** Wave 1 (agent running 2026-08-20) builds only the SUBSTRATE: one synthetic study
(DD + records + linkage source + manifest). The full principle: every role-task pair gets the
synthetic input its test needs. Draft inventory to correct:

| Role | Task | Input needed | Status |
|---|---|---|---|
| PM | monitor studies | synthetic tracker records (SIR-like set, statuses mixed) | to build |
| PM | draft study documents | concept note | wave 1 |
| PM | submit new study request | intake.json | wave 1 |
| QA | build worklists | DD + records + qa_fields | wave 1 |
| QA | audit RA returns | a RETURNED workbook (RA-filled xlsx w/ engineered edits+notes) | to build |
| DB mgr | see outstanding requests | synthetic personnel/data/linking request records | to build |
| DB mgr | build a REDCap | fields.json (dd_builder input) + a DIRTY DD w/ known violations | to build |
| DB mgr | add users | roles/users input (who→role table) | to define |
| DB mgr | export data | the study itself | wave 1 |
| DB mgr | link data (the big one) | linkage source w/ engineered fills/conflicts/orphans | wave 1 |
| Analyst | clean/analyse/figures | records + DD | wave 1 |
| Analyst | multi-database merge-analysis | a SECOND synthetic study sharing ids | to build |
| Analyst | Stata/R/Python parity | same data, three reference scripts | to define |

Open essence-questions for post-compaction: do tracker-record fixtures imitate the API's JSON
or live as CSVs? Is the returned-workbook fixture generated or hand-crafted once? How much
Stata/R parity is testable headless (no Stata license on CI)?

**Tier 2 — Cowork rounds (the existing ladder)** = agent-behavior + UI check only, staged on
the synthetic study. Built by subagents; results reviewed before merge.

## Phase 2 — the round ladder (against 0.17.0, then frozen again)

Protocol per round, no exceptions:
1. Org plugins refreshed → verified by the **toolkit stamp in the session's first output**.
   If the stamp is wrong, STOP — don't run the round.
2. One round = one fresh chat (never in a Project), `~/Desktop/ARGO-cowork` connected.
3. Collect + grade. Showstopper → fix-batch next morning. Nit → NITS.md.

| # | Round | Prompt | Pass |
|---|---|---|---|
| A | returning | "help me with ARGO" | one-liner incl. "five tracker keys connect" + stamp; NO add-keys option; routing question; nothing else |
| B | analyst | staged synthetic export → Table 1 | routes to run-analysis, no key talk, script + table in data-analyst/, no record rows in chat |
| C | qa | staged export + qa_fields.yaml → worklists | no-key path, per-DAG xlsx in qa-specialist/, yellow/amber semantics correct |
| D | builder | toy concept note → SOP + questionnaire docx | mines the note, [TODO]s not inventions, real .docx in project-manager/new-studies/ |
| E | repeat A + B once each | same | reproducibility — same result twice |

PM/portfolio: already witnessed live in round 5's continuation; re-run only if time allows.

## Phase 3 — the Monday deliverable (what the group receives)

1. **The plugins** via the org marketplace (they already load everywhere).
2. **The team handout** (to write Fri/Sat, one page): make an ARGO folder on your computer →
   connect it → say "help me get started with ARGO". Key policy: everyone gets the 5 tracker
   keys (batch request to OAU admin — send BEFORE Monday); a study key per QA assignment.
   Keys go in the file, never the chat.
3. **The demo script**: live run of rounds A + B (returning user + analyst), which by then
   have passed twice.
4. Admin prerequisite to trigger now: OAU REDCap admin issues per-person tracker keys
   (rights matrix in access-tiers: only PID 224 needs import; 221 create+import; rest export-only).

## Standing process rules (learned the hard way)

- No pipelines around exit-critical commands; check `$?` explicitly.
- `release.py` is the only release path (it gates on the suite).
- Block-edits to files: verify anchor ORDER before slicing; grep the file on disk afterwards.
- After layered edits to any SKILL.md: read it whole before shipping.
- Never stage credentials inside the connected workspace (baseline lives in
  `~/Desktop/ARGO-cowork-rounds/baseline/`).

## Where things live

- Test loop: `testing/cowork/round.py` (prepare --role X / collect)
- Round reports: `~/Desktop/ARGO-cowork-rounds/round-NN-role/`
- Workspace under test: `~/Desktop/ARGO-cowork`
- Session transcripts: `~/Library/Application Support/Claude/local-agent-mode-sessions/`
- Live-witnessed full journey: round-05 report + its continuation in the same audit file
