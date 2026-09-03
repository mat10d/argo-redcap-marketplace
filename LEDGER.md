# ARGO toolkit ledger — updated 2026-09-03 (0.21.0 released)

The single answer to "what's done and what's outstanding". Supersedes PLAN.md's todo block for
status; PLAN keeps the history and the spec.

## Verified complete (live)
1. Onboarding from scratch — 3 reproducible runs (0.17.1 ×2, 0.18.0 ×1)
2. Returning user — one-liner, stamp, no re-asks
3. Door route — role pick → task
4. Weekly check — status + queues (round A)
5. Scheduled weekly check — 2 autonomous runs 2026-08-25 + report-2026-08-25.md
6. Full study build, real (study 17: 309 fields, validator clean)
7. Live Study Tracker writes: project_created + dd_uploaded on PID 7436, confirm-before-write
8. Correct refusal: user_rights_complete blocked with two documented reasons
9. Export with key — full set (raw/labelled/de-identified ×2/tidy/DD/README), correct counts
10. Keys 6/6 verified in the workspace settings file
11. Tier 1: 371 automated checks; Tier 1.5: 8/8 subagent walkthroughs
12. NITS defects 1–69: all fixed and released across 0.17.2 → 0.21.0
13. **0.19.0** — Matteo's review round: door pushes the settings file on screen; weekly-check
    presentation rules (open items one row each, people with name/email/role, next step on the
    line); QA scope-first; build changes/questions split (best guess into the DD +
    OPEN_QUESTIONS.md + tracked-changes docx); hard-link linkage (link_studies.py,
    <study>_missing_link.csv with names, <child>_hard_link.csv); R verified to RUN.
    Environment fact recorded: Cowork executes in a Linux sandbox, so Mac R/Stata are a
    hand-off, not in-session. 4/4 walkthroughs + 26 whole-read findings applied. 511 tests.
14. **0.20.0** — the analysis library: lib/python + lib/R twins (core / table1 / excel house
    style / figures / survival stub), analyses/ registry (table1 ready, survival planned),
    scaffold writes 01_table1.py AND 01_table1.R as library calls, grouping variable asked
    once. Both languages reproduce the Table 1 golden (R byte-identical). 652 tests.
    Known parity gaps logged (NITS 54–55: sparse-table p-value method; checkbox parents).
15. **0.21.0** — the PM study-launch pipeline (the programme's own procedure):
    new-study-documents is GATE-FIRST (directors approved / IRB-ready / ethical approval),
    every task mapped to its verified File Repository template, Gate 3 ending at the SIR
    submission that hands off to build-study. Taught and corrected on ARGO's own teaching
    case — the Cervical Cancer Database originals drafted BLIND, then compared against the
    programme's real finals (NITS 60–69, all applied). New reference:
    redcap-protocol-boilerplate.md; fetch widened to the QA plan + both Study Start-Up SOPs.
    682 tests.
    **OPEN FOR MATTEO/RIVKA:** is "ARGO studies present as Nigerian-led, with ARGO as the
    collaborator" policy, or was it study-specific? (The finals removed MSKCC from every
    document; the skill now ASKS rather than assuming, and no policy is written.)

## Graded complete 2026-08-26 (the five continued chats)
- B Table 1 — pass (district grouping per in-chat answer; self-verified, fixed 2 own-script bugs)
- C+L QA worklists on the REAL CRC study, live key — pass; 3,784 cells verified; found NITS 41
  (label-collision crash) + 2 live-CRC data-quality issues (staging branching, duplicate labels)
- D audit — pass after detecting the legacy-colour drift itself (36/9 exact); found NITS 42
- F merge — pass, every count exact; systematic-conflict insight
- G documents — pass; official templates fetched/used; 2 template findings (memo is a flattened
  image; official questionnaire is a design guide)
- naqiya's study session (real work — unexamined)

## Outstanding tests (all on 0.21.0 after the org refresh)
- K  Export with no key — the CRC line is ALREADY commented out in ~/Desktop/ARGO-cowork/.env;
     fresh chat "Export the CRC study to disk." → at the solicitation, tell Claude "restore the key"
- M  Table 1 in R — now a HAND-OFF by design (Cowork can't run Mac R): expect the R script + the
     command to run it yourself; run it, report the numbers
- Q  Audit on the regenerated kit (new colours; fresh chat, same audit prompt)
- O  Repeat weekly-check + Table 1 once each (demo reproducibility)
- Fresh-folder onboarding once more on 0.19.0 (the door now PUTS the file on screen)
- P  WINDOWS probe (friend's machine; ARGO-test-data/WINDOWS-PROBE.md) — the last real unknown

## Outstanding non-test
- Study 17 user_rights_complete: REDCap admin (User Rights on 7436) or UI by hand
- Live CRC data quality (from round C+L): 5 staging fields missing branching logic; 44
  duplicate field labels — a report for the database manager / study team
- Official templates: activation memo is a flattened image (can't be filled); questionnaire
  template is a design guide — flag to the PM/collaborator
- Collaborator review of the PM document package
- OAU batch tracker-key request (longest lead time)
- Team handout + demo script (delivery pieces)
- Claude: grade the Sunday transcripts; mine naqiya's session on request

## Excluded by design (documented)
- Write-back linkage push (Tier 3, migration-only — suite-tested, not run live)
- Stata execution (no licence; reference script ships, presence-checked only)
