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
