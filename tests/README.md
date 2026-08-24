# Tests

Run everything, from the repo root:

```bash
python3 tests/run_all.py
```

**No REDCap connection, tokens, or network access are needed.** Every test here works from
fixtures and from the code itself, so they can be run on any machine, including one with no
`~/.argo/.env` set up at all.

## What's covered, and why

| File | Guards against |
|---|---|
| `test_pure_logic.py` | The logic that decides what the dashboards say and what the safety gates allow: URL validation, token masking, project-title matching, SIR build progress (`N/7`), week-over-week diffing, record-ID range parsing, and the QA dry-run receipt system. |
| `test_docs_match_code.py` | Documentation drifting away from code, and scripts crashing instead of explaining themselves. |
| `test_branching_logic.py` | The QA worklist branching evaluator — known logic strings against known records. Exists because a silent inversion here dropped 28–70% of gated fields with no crash, so no infrastructure test could see it. |
| `test_write_back_safety.py` | The fill-vs-conflict rule in `argo_diff.py`: computed values only ever fill blanks, a blank never erases, conflicts are quarantined. |
| `test_qa_worklists_end_to_end.py` | QA task 1: `build_worklists.py` run on the synthetic study, asserted against `MANIFEST.json`. Exists because a refactor left the builder unable to produce a nonempty worklist at all, and no unit test could see it. |
| `test_tracker_queues.py` | PM/DB-manager landing logic: `open_requests.py` and the portfolio's bucketing driven with the synthetic tracker JSON (`testing/fixtures/synthetic-trackers/`), asserted against its MANIFEST — open/done counts, label-based summaries, SIR progress per bucket. Also pins the engineered divergence between the two progress functions. |
| `test_build_study_feasibility.py` | DB-manager build task: `dd_builder.py` on `fields.json` must produce a DD that `validate_dd.py` passes clean, and the engineered `dirty_datadictionary.csv` must report exactly its MANIFEST's violations (`testing/fixtures/synthetic-build/`). |
| `test_linkage_merge.py` | Analyst/DB-manager task: merging TWO studies. Drives `link-data`'s `diff_payload.py` across `synthetic-study` and `synthetic-study-b` (which share the `syn_id` space) and asserts fills, conflicts, no-ops and orphans against study B's `MANIFEST.json`. Also pins the orphan defect: ids absent from the current side are classified as safe-fills and no orphan report is emitted. |
| `test_analysis_parity.py` | Analyst task: the same Table 1 from Python, R and Stata. `table1.py` is compared byte-for-byte with the committed `expected_table1.csv`; `table1.R` numerically with tolerance, and only where `Rscript` exists; `table1.do` is reference-only (no headless Stata licence) and only its presence is checked. |
| `test_qa_audit_round_trip.py` | QA task 2: build → seeded RA-returned workbooks (`generate_returns.py`) → `review_responses.py`, triage counts asserted against `MANIFEST.json`'s `returned` block. Also covers `--from-worklists` (returns for an arbitrary session's build) and `summarize_for_ra.py`'s no-key file mode. The four defects it used to pin were fixed in 0.17.2; the assertions now hold the correct behaviour. |

### The drift checks are the interesting ones

`test_docs_match_code.py` exists because `weekly-check`'s `SKILL.md` and `portfolio.py` had
quietly diverged in four separate ways at once — a missing tracker, wrong done-marker fields,
wrong project titles, a wrong build-step count, and a snapshot path that described a file where
the code writes a directory. Each was individually plausible and collectively meant the doc
couldn't be trusted. The tests now read `ADMIN_REDCAPS` and `SIR_BUILD_STEPS` directly and assert
the SKILL.md matches, so the next divergence fails immediately instead of being discovered by
someone acting on a wrong instruction.

### The smoke test

`test_no_args_never_tracebacks` runs **every** Python script in the suite with no arguments and
with all REDCap environment variables stripped — the exact situation a new team member hits on
their first day — and fails if any of them produces a raw Python traceback. A script may exit with
an error; it may not crash. This is the cheapest possible guard on the plain-language rule: a
traceback is never an acceptable thing to show someone who has never opened a terminal.

## Adding a test

Prefer testing a function that takes data and returns data. Anything needing a live REDCap belongs
in a manual check, not here — the whole point is that these run anywhere, instantly.
