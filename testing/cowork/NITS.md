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
