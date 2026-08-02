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

### The drift checks are the interesting ones

`test_docs_match_code.py` exists because `study-portfolio`'s `SKILL.md` and `portfolio.py` had
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
