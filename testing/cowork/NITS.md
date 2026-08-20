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
