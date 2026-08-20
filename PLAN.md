# Plan to Monday (2026-08-24) — written 2026-08-20 after a churn day

Read this first after any context compaction. It is the agreed state and plan.

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
| **Project manager** | Monitors what studies exist; builds study documents for new studies; submits new study requests | 5 tracker keys | study-portfolio, study-setup |
| **QA specialist** | Builds and audits RA worklists for their assigned study | 5 trackers + THEIR study's key | redcap-qa |
| **Database manager** | Builds REDCaps, adds users, exports data, **links data (the big one)**. Entry = what requests are outstanding → routed to the steps to fulfil them | 5 trackers + study keys as needed | redcap-build, redcap-admin, data-export, study-linkage |
| **Data analyst** | Standard REDCap outputs (downloaded, NO API key); cleaning, analysis, QA; linkage when merging >1 database for analysis; Stata/R/Python; figures | none | run-analysis (+study-linkage read-side) |

**Decided:** workspace uses ROLE-NAMED folders — `project-manager/ qa-specialist/
database-manager/ data-analyst/` — each role's outputs land in their own folder (skills'
write-paths updated accordingly; scaffold, README, harness fixtures follow). Role is remembered
via `ARGO_ROLE=` in the settings file, so who-are-you is asked once.

Notes: DB manager merges what the README called "Builder"+"Data management" — the plugins stay
as-is; roles are the routing layer. DB manager's front door is the REQUEST QUEUES (personnel /
data / linking requests from the trackers) → route into the fulfilment skill. RAs are not a
role here — QA specialists build FOR them; keep the lightweight RA pointer.

## Phase 1 — re-review + ROLE RESTRUCTURE (one batch, 0.17.0)

The whole-read review AND the role-first entry, shipped together as one coherent version:
start-here rewritten role-first; scaffold + README aligned; each role's landing experience
defined (PM → portfolio; QA → key check + worklist flow; DB manager → outstanding requests;
analyst → point me at your export).

Read every SKILL.md **whole**, end to end — all 9 skills + start-here + key references
(access-tiers, token-optional, verify-install). The two worst recent bugs were caught by
whole-reads, not diffs. Looking for: internal contradictions from layered edits, stale policy
references (key policy changed twice), instructions that fight the ask-first rule.
Output: ONE batch release (0.17.0). Also delete/park: `VERIFY.md` pointer file check,
round reports clutter.

## Phase 2 — the round ladder (against 0.17.0, then frozen again)

Protocol per round, no exceptions:
1. Org plugins refreshed → verified by the **toolkit stamp in the session's first output**.
   If the stamp is wrong, STOP — don't run the round.
2. One round = one fresh chat (never in a Project), `~/Desktop/ARGO-cowork` connected.
3. Collect + grade. Showstopper → fix-batch next morning. Nit → NITS.md.

| # | Round | Prompt | Pass |
|---|---|---|---|
| A | returning | "help me with ARGO" | one-liner incl. "five tracker keys connect" + stamp; NO add-keys option; routing question; nothing else |
| B | analyst | staged CRC export → Table 1 | routes to run-analysis, no token talk, script + table in analysis/, no patient rows in chat |
| C | qa | staged export + qa_fields.yaml → worklists | no-token path, per-DAG xlsx in worklists/, yellow/amber semantics correct |
| D | builder | toy concept note → SOP + questionnaire docx | mines the note, [TODO]s not inventions, real .docx in builds/ |
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
