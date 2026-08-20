# Nits log — noted during the freeze, fixed in batches (see PLAN.md)

- **generate.py: add `expected_workbooks` to MANIFEST** (name → {rows, yellow, amber} per
  workbook file) so tests/test_qa_worklists_end_to_end.py's row-count test stops self-skipping.
  Numbers were verified by the fixture agent (e.g. clinical_core site_alpha with_MDC: 30 rows,
  28 yellow, 9 amber).
- **Amber semantics design question** (fixture agent, 2026-08-20): the engineered
  amber field (`adjuvant_therapy`, datediff gate) is never blank — its amber cells come from
  MDC sentinels, so amber only appears in with_MDC workbooks. If amber should also mark BLANK
  cells under an unreadable gate in no_MDC books, that's a small generator tweak + a semantics
  decision for the whole-read review.
- SETUP.md rewrite (Claude-Code-first, pre-roles) — already in PLAN Phase 1.
