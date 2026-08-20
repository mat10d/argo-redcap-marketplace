# `returned/` — RA-returned worklists (generated, never committed)

Input fixture for the QA specialist's **task 2**: auditing the workbooks RAs send back.

**This folder holds no .xlsx files, on purpose.** Excel workbooks are binaries; the repo is
public and fixtures are synthetic-and-seeded by rule. The returned workbooks are built on
demand by `../generate_returns.py`, which:

1. runs `build_worklists.py` on the committed SYN fixture,
2. copies the four `with_MDC/` workbooks (2 workbooks x 2 DAGs), and
3. applies a fixed, seeded set of RA edits — plausible values, MDC sentinel codes, untouched
   cells, RESPONSE-column notes, out-of-scope edits, and answered amber cells.

Every count is stated exactly in `../MANIFEST.json` under `returned`, and
`tests/test_qa_audit_round_trip.py` regenerates them into a temp directory and asserts what
`review_responses.py` reports against those numbers.

Generate a set locally to look at:

```bash
python3 testing/fixtures/synthetic-study/generate_returns.py --out /tmp/syn-returns
```

Add `--update-manifest` after changing the edit plan (or after rerunning `generate.py`, which
rewrites `MANIFEST.json` from scratch and drops the `returned` block).
