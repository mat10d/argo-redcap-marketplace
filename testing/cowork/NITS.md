# Nits log — noted during the freeze, fixed in batches (see PLAN.md)

## Queue for the 0.17.1 fix batch (found by the wave-2 fixture agents, 2026-08-20; each has a pinning test)

Ranked. The top two are silent-data-loss class.

1. **`review_responses.py` drops all RA answers when the workbook has ONE id column** — it
   hardcodes `id_col_count=2` and scans from column 3; a single-id workbook (the builder's
   default) had all 15 engineered answers silently discarded. Pinned:
   test_qa_audit_round_trip.
2. **`argo_diff.diff_records()` classifies orphan records as safe fills** — ids absent from
   the current side read as all-blank records, so every populated cell becomes a FILL and the
   payload would CREATE records on import. Also: the gap/orphan report link-data's SKILL.md
   advertises does not exist, and without `--fields` the default comparison includes
   `redcap_data_access_group`. Pinned: test_linkage_merge.
3. **`review_responses.py` ignores amber-cell answers** (matches only the yellow fill) and
   **never reports out-of-scope RA edits** despite the skill doc claiming it shows every
   changed cell. Pinned: test_qa_audit_round_trip.
4. **`build_worklists.py` gate-context column order is nondeterministic** (set iteration) —
   columns move run to run, worklists aren't diffable between rounds. Pinned:
   test_qa_audit_round_trip.
5. **`dd_builder.py` defects**: (a) emits text-format MDC on 7 of 9 date validation types, so
   its output fails its own validator for anything but `date_dmy`; (b) a custom Field Note
   silently suppresses MDC on text/notes fields, contradicting its docstring; (c) the
   `Matrix Ranking?` column is dead code (`and False`); (d) `yesno` passes through the builder
   and only fails downstream. Evidence in test_build_study_feasibility's agent report.
6. **The two SIR progress functions disagree by design but only one says so**:
   `portfolio.sir_progress` counts any non-no label on `data_imported` (a radio);
   `open_requests._sir_progress` counts literal "Yes" — the same record can show 3/7 to the DB
   manager and 4/7 to the PM. Decide one rule (lenient looks right for radios) and apply to
   both. Pinned: test_tracker_queues.
7. **`validate_dd.py` has no MDC-waiver mechanism**, so a validated Likert scale can never
   appear in a clean DD even though ARGO policy exempts them — an annotation the validator
   honours (e.g. `@MDC-EXEMPT`) is the obvious design.
8. `synthetic-study/generate.py` rewrites MANIFEST.json wholesale and drops the `returned`
   block; the round-trip test fails loudly with instructions, but the two generators should be
   mechanized into one write path.
9. Future fixture: a study-C with mistyped names/hospital numbers to exercise link-data's
   fuzzy-match path, which currently has no test.
10. **run-analysis needs a language preflight** (analyst round, 2026-08-20): the Cowork
    sandbox shell's PATH misses /usr/local/bin, so `command -v Rscript` reported "R is not
    installed" on a machine where /usr/local/bin/Rscript exists and passes the parity test.
    Fix: at scaffold time probe known locations (/usr/local/bin, /opt/homebrew/bin,
    /usr/bin, /Applications/Stata*/...) for python3/Rscript/stata, report the three
    languages' availability in plain words, and invoke by full path. Matteo: "python
    (critical for all tasks), R, STATA should have some check/setup".

- **generate.py: add `expected_workbooks` to MANIFEST** (name → {rows, yellow, amber} per
  workbook file) so tests/test_qa_worklists_end_to_end.py's row-count test stops self-skipping.
  Numbers were verified by the fixture agent (e.g. clinical_core site_alpha with_MDC: 30 rows,
  28 yellow, 9 amber).
- **Amber semantics design question** (fixture agent, 2026-08-20): the engineered
  amber field (`adjuvant_therapy`, datediff gate) is never blank — its amber cells come from
  MDC sentinels, so amber only appears in with_MDC workbooks. If amber should also mark BLANK
  cells under an unreadable gate in no_MDC books, that's a small generator tweak + a semantics
  decision for the whole-read review.
- SETUP.md rewrite (Claude-Code-first, pre-roles) — DONE in the 0.17.0 batch.
- **`ingest_response.py` is referenced nowhere in qa-worklists's SKILL.md** (found in the 0.17.0
  review) — it belongs to the migration-push flow; document it in
  references/migration-push.md or retire it. Decide, don't leave it orphaned.
- **Tracker field inventories are unverified** (0.17.0 review, DB-manager landing): the field
  names on the Data Request (223) and Data Linking Request (222) forms have never been pulled.
  `open_requests.py` is metadata-driven so it renders whatever exists, but before any
  field-specific queue logic: one `content=metadata` pull per tracker, saved as a committed
  inventory. Needs only the five tracker keys.
- **API close-out for 222/223 needs import rights** those keys don't have (rights matrix grants
  import only to 224/221). Until the OAU batch key request includes that, marking a data/linking
  request complete is a REDCap-UI step — the skills say so. Revisit after keys are issued.
11. **setup_brief.py derives File Repository site names from stale/hardcoded data** (real
    build round, study 17, 2026-08-20): brief said "SiteUch"/"SiteUniosun" (a previous
    Nigerian study's sites) for an MSKCC study sited in Ghana/South Africa/Tanzania. The
    session caught and hand-fixed it. Find where site names come from and derive them from
    the SIR record's institutions.
12. **build-study: QUESTIONNAIRE_CHANGELOG.md is now doctrine** (Matteo, 2026-08-21): the DD
    mirrors the printed IRB-approved form exactly (typos, numbering, no-option columns → free
    text, as-is); substantive defects go in a changelog marked "needs IRB amendment: yes/no".
    SKILL.md updated (uncommitted, rides in 0.17.2); setup_brief/BUILD_NOTES templates should
    reference the changelog deliverable.
13. **Ask about the data, don't hunt for it** (Matteo, 2026-08-21): sessions scan the connected
    folder and assume a found file is "the study" (QA session nearly used the analyst's
    synthetic export as the CRC export). Rule for every file-consuming skill (qa-worklists,
    run-analysis, link-data, export-data): if the user hasn't named/attached the files, ASK
    where the data is — or name what you found and confirm with ONE question — never assume.
14. **export-data: use export.py, never hand-rolled client calls** (export round, 2026-08-21):
    the agent improvised a python snippet with a malformed `fields` param; the client raised a
    plain error but a raw traceback reached the chat. SKILL.md must say: the script is the
    only path. Also: with no study key, export-data should SOLICIT the key (file card, wait,
    verify) rather than default to website instructions — an export to disk is the whole point.
15. **Settings search order: `~/.argo/.env` before the connected folder** made a dev-machine key
    look like a workspace key (Claude Code found CRC_TOKEN in ~/.argo/.env; Cowork sessions
    never could). Users have no ~/.argo, so harmless for them, but --check should say WHICH
    file each key came from when more than one settings file is in play.
16. **qa-worklists: fields.yaml must not be a user-facing input** (Matteo, 2026-08-21): "the
    idea that you show up with a fields yaml is just confusing." The skill authors the config
    from the data dictionary (as the live session did unprompted), proposes the workbooks
    (which forms/fields, per site) and asks ONE confirming question; the yaml is an internal
    artifact saved beside the worklists for reruns, never something the user is asked for.
17. **`summarize_for_ra.py` hard-requires a study key** (audit round, 2026-08-21): no
    file-based mode, so the audit's last step isn't token-optional; the session hand-wrote the
    RA summaries. Give it --records-csv/--metadata-csv like the builder.
18. **Test kit: generate RA returns FROM the session's own worklists**, not from the fixture's
    two-workbook config — the layout mismatch made the session invent "the RAs merged the
    workbooks". Either ship qa-returns generated from a three-workbook build matching what the
    DD-driven config produces, or have generate_returns.py accept an arbitrary worklists dir.

## Found by the Tier 1.5 walkthroughs on the 0.17.2 checkpoint (2026-08-24) — fix BEFORE release
19. **SECURITY: `argo_redcap_client.run_check()` harvests every `*_TOKEN` env var and POSTs it to
    REDCap** as a study key (sent CLAUDE_CODE_MESSAGING_TOKEN in a walkthrough), then reports
    a false "not working" to the user with exit 1. Scope study-key discovery to variables
    defined in the settings file it just loaded — never the whole process environment.
20. **export.py defaults to labelled data; the QA builder and getting-files-from-redcap assume
    raw.** The skill calls the key path and the website path interchangeable — they aren't.
    Default export.py to raw (add --labels), and say which encoding each file is.
21. export.py: a relative `--out` is cwd-anchored; anchor it at the settings file's folder (the
    workspace) when not absolute.
22. testing/walkthroughs/prepare.py: ARGO_PM_ROOT is templated from the task name, so a run dir
    renamed after preparing points outside itself — add --name.
23. **export.py reports physical line counts as "rows"** — 2,143 claimed vs 1,525 actual
    patients (multi-line free-text fields). Count with csv.reader; say "patients/records" only
    after checking for repeat-instrument rows.
24. **BLOCKING: portfolio.py never loads the settings file** (`REDCAP_URL = os.environ.get(...)`
    at import; ignores ARGO_ENV_FILE) — the weekly check's Part 1 fails as documented unless the
    user sources the file by hand. Call the shared client's load_env_file() first, like every
    other script. Add a guard test: every ARGO script that talks to REDCap must self-load.
25. portfolio.py `--diff` on a first run says nothing about being the baseline — print "first
    snapshot, nothing to compare against yet" explicitly.
26. open_requests.py: doubled colons in summaries (DD labels already end with ':'); build-queue
    lines should show the study's short name + PI like the portfolio does, so both halves of
    the weekly check identify studies the same way.
27. (nit) portfolio.py lives at the skill root instead of scripts/ — only such script; move or
    document.
28. qa-worklists SKILL.md never says which variant the RAs get. Decide: **with_MDC is the
    default** (RAs revisit coded-missing cells too); no_MDC only when the QA specialist says
    not to. State it in "Hand it to the RAs".
29. **"Yellow" cells are rose (#FFC7CE).** Every RA instruction says yellow. Make the fill an
    actual yellow (one constant shared by build_worklists, review_responses, ingest_response,
    generate_returns) so the word and the colour agree; amber stays distinct.
30. qa-worklists SKILL.md "Run it" block still opens with `set -a; source ~/.argo/.env` —
    delete; the scripts self-load the settings file. Amber prerequisite row shows the raw
    datediff expression — acceptable, but prefix it "couldn't read this condition:".
31. qa-worklists Task 2 has no defined stopping state when there's no post-RA export (the common
    no-key case): "confirm the gaps closed" and VERIFY both assume one. Say: send the questions,
    ask for a fresh export, and stop — the round closes on the next pull.
32. summarize_for_ra.py site-header parsing takes the first word (`## Site Alpha` → "site");
    warn on collisions / use the whole header.
33. **link-data read side speaks in write-back language**: diff_payload's file names
    (*_update/_overwrite) and stdout ("Push ... with overwriteBehavior") when the user only wants
    an analysis merge. Add `--for-analysis`: names files *_fills / *_disagreements, suppresses
    push instructions.
34. **link-data promises master_linkage.csv + *_integrity.csv but ships no code for them** — the
    walkthrough hand-wrote build_master_linkage.py (adopt it: reads the diff engine's outputs,
    adds cohort_linked/pathology_linked/link_class + suffixed duplicate columns, integrity table
    worst-first).
35. diff_payload.py and portfolio.py live at skill roots rather than scripts/ — fine, but
    document the convention: a skill's OWN scripts at its root, the SHARED vendored ones in scripts/.
36. start-here contradiction: Step 0 "a failing key is the exception to brevity — name it
    plainly" vs the analyst landing's "no key talk at all". Resolve: a role landing that says no
    key talk WINS for data-analyst-only users; key status is folded in silently.
37. run-analysis scaffold.py's 00_explore template matches only website-style DD headers
    ("Field Type", "Choices, ...") — on an API-style dictionary (field_type,
    select_choices_or_calculations) it prints "Coded fields w/ map: 0" with no warning. Accept
    both header styles (build_worklists already does) and warn when neither is found.
38. run-analysis SKILL.md: say that categorical levels are reported in codebook order, never
    alphabetical.
39. new-study-documents template search (`find /mnt ~ -maxdepth 4 -iname "ARGO*Template*"`)
    misses the nested tree fetch_templates.py itself writes, and searching all of `~` can pick
    a stale copy from an unrelated folder. Search ONLY the workspace's
    project-manager/templates-official, recursively.
40. **export-data must never consult the Study Tracker to identify the study** (Cowork CRC round,
    Matteo): the key identifies the project (`export.py --info`); no key → ask which project, one
    question, no tracker lookups. And with a key, "all we want is pull from remote": produce a
    SET of files — records RAW and records LABELLED (both), the data dictionary, plus a short
    README in the export folder saying what each file is, its encoding and its record count.
    (+) Also in the default export SET: a DE-IDENTIFIED records file (every field the data
    dictionary marks Identifier?=y dropped, both encodings or at least raw), named so it's
    obvious which is safe to share; README says which fields were removed. Checkbox-column
    collapsing is a nice-to-have extra file, never a replacement.

## Found in the 0.18.0 Cowork rounds (2026-08-24/26)
41. **build_worklists.py crashes on duplicate field labels** (real CRC round): line ~469 looks
    fields up by LABEL; the live CRC DD has 44 labels shared across 160 fields. Reproducible;
    masked only because the colliding fields are @HIDDEN. Look up by field NAME everywhere;
    labels are display-only.
42. **review_responses.py must recognise the legacy rose fill (FFC7CE) as flagged** alongside
    the new yellow — worklists sent to RAs before the 0.18 colour change come back rose, and the
    audit silently reported 5/36 answers. Accept both hexes (qa_colours.py: LEGACY_FLAG_HEXES),
    and warn when a workbook's flags are all legacy-coloured.

## Matteo's final-round review (2026-08-26) — the 0.19 cleanup list
43. **start-here: after first-time setup, PUSH the settings file** — don't declare completion
    and ask whether they want keys; present the .env (file card) unprompted as the completing
    act of setup, with the one-line instruction. "Should be more explicitly pushing for opening
    the .env after setup is complete."
44. **weekly-check presentation rules**: (a) NO tables for queues/requests that aren't open;
    (b) every OPEN item is its own row in an inline table (status + details) — never collapse
    "untouched" ones into a single line; (c) people requests: open ones in a table with first
    name, last name, email. open_requests.py should emit those fields for the people queue.
45. **qa-worklists: scope FIRST, always** — the databases are massive, so the plan step starts
    from "what exactly do you want me to QA (which variables)?" A vague answer ("staging") →
    drill down: list the staging columns, let the user narrow to what they actually want.
    Branching-logic gating stays as-is (verified working on the real CRC round).
46. **run-analysis R setup**: R detection passed but actually RUNNING an R analysis hit a nit
    at setup time (Matteo progressing through it — mine his chat for the specific failure).
    The scaffold/preflight should verify R can execute a trivial script (and say which base
    packages are needed), not just that Rscript exists.
47. **build-study intake speed**: immediately port the request's attached documents into the
    build folder (questionnaires etc. from the SIR) as the first act — "more quickly make a
    folder of documents to upload".
48. **build-study: changes vs questions split** (RESOLVED with Matteo, 2026-08-26): two
    deliverables, split by KIND. (a) CHANGES — what the questionnaire itself needs changed:
    the ORIGINAL doc with tracked changes as `<name>_redcap_changes.docx`; if the original is
    a PDF, a `<name>_redcap_changes.md` listing them. The document IS the review vehicle.
    (b) OPEN QUESTIONS — assumptions the build made (unparseable branching etc.): "we assumed
    X — accurate?" — a separate questions doc, never a tracked change. FINAL (Matteo,
    2026-08-26): the build always makes headway — the BEST GUESS goes into the DD, and the
    open-questions doc records every guess for confirmation. Typos/numbering stay out of all
    deliverables (default; revisit only if Matteo says so).
49. **link-data redesign around the HARD LINK** (Matteo's spec, near-complete): it's a
    left/inner/right join; the work is DERIVING the join key (hospital number, or a ported
    other-study record-id column) and reasoning aloud about it. Deliverables: (1) name-
    discrepancy review table for matched pairs; (2) `<study>_missing_link.csv` — child records
    with no parent, WITH patient name + surname for review (drop the "orphan" vocabulary);
    (3) the culminating hard-link CSV: child record_id + parent's redcap-number column
    (e.g. r01 record_id + crc_redcap_number) for the user to upload to formalize the link.
50. **run-analysis roadmap (post-Windows design)**: parallel R and Python analysis LIBRARIES,
    composable into analyses — formatting modules (excel styling, figures) now; survival
    analysis vs statistical comparisons as future modules.

Round verdicts from the same review: export-from-API "perfect"; returning-after-keys "perfect".
