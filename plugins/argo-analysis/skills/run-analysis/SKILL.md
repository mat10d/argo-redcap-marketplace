---
name: run-analysis
description: Run a reproducible, auditable analysis on a REDCap study whose data export and data dictionary are already on disk. Interviews the user to understand the study, proposes a basic analysis plan, then executes it under a fixed contract — every analysis is a saved, well-commented script (Python/R/Stata) with organized, traceable outputs. Use when the user wants to analyze, summarize, tabulate, or explore a downloaded REDCap dataset, or asks for a Table 1, descriptive stats, comparison, or figure from a local export.
allowed-tools: Read, Bash, Write, Edit, Glob, Grep
---

# run-analysis

Turn a downloaded REDCap dataset into analysis — **reproducibly**. This skill never runs
ad-hoc, throwaway analysis. Every result is produced by a saved, commented script, written to
an organized directory, so a teammate (or a reviewer, or future-you) can see exactly what was
run and re-run it.

This is the analysis counterpart to [[data-export]]: `data-export` gets the data onto disk;
`run-analysis` analyzes it. It assumes the export already exists locally and does **not** call
the REDCap API or need a token.

## When to use

A teammate says any of: "analyze this export," "make a Table 1," "summarize the CRC cohort,"
"compare X by Y," "plot …," "run some descriptives on the data I downloaded." If they haven't
downloaded the data yet, point them to [[data-export]] first.

## Inputs (assumed already on disk)

1. **The data export** — a REDCap record export, normally CSV (raw-coded preferred; labeled is
   fine if that's what they have).
2. **The data dictionary** — the project's data dictionary / codebook CSV (REDCap "Download
   Data Dictionary"). This is how you understand field types, coded values, validation,
   branching, and the record-ID field. Do not proceed without it — guessing variable meaning is
   how analyses go wrong.
3. *(optional)* **Existing analysis scripts** — Python/R/Stata the team already wrote. Reuse and
   adapt these rather than reinventing; ask the user where they live.

If either required input is missing, ask the user for its path before doing anything else.

## The contract (non-negotiable)

These rules are what make the skill trustworthy. Do not break them to "save time."

1. **Script-first.** No analysis happens except by writing a script and running it. Never
   compute a result with an inline one-liner you don't save. If it's worth reporting, it's worth
   a saved script.
2. **Self-contained & re-runnable.** Each script reads its inputs from `data/`, writes its
   outputs to `outputs/`, and runs start-to-finish with one command. No manual editing between
   steps, no reliance on in-memory state.
3. **Well-commented.** Every script opens with a header block (purpose, inputs, outputs, author,
   date, assumptions) and has commented sections. A non-coder should be able to read the script
   and follow what it does and why.
4. **Organized & traceable.** Outputs go in the fixed structure below. Every output file is
   produced by exactly one script, and `ANALYSIS_LOG.md` records what was run.
5. **Inputs are read-only.** Never modify the files in `data/`. Derived/cleaned data is written
   to `outputs/`, never back over the source.
6. **Confirm before running.** Propose the plan and the script, get a thumbs-up, then run. Show
   the user the result and where it was saved.
7. **Stay basic unless asked.** Default to descriptive, defensible analysis (counts, summaries,
   simple comparisons, clear figures). Don't reach for sophisticated modeling unless the user
   explicitly asks and the design supports it.

## Directory contract

Scaffold this once per study with `scaffold.py` (below):

```
<analysis_dir>/
├── README.md            # study description + the agreed analysis plan
├── ANALYSIS_LOG.md      # append-only: what was run, when, which script, result/notes
├── data/                # READ-ONLY inputs
│   ├── export.csv           # the REDCap record export
│   └── data_dictionary.csv  # the codebook
├── scripts/             # saved, commented analysis scripts: NN_short_name.{py,R,do}
└── outputs/
    ├── tables/          # CSV / XLSX results
    └── figures/         # PNG (dpi 150) / PDF
```

Scripts are numbered in run order (`01_table1.py`, `02_survival_by_stage.R`, …).

## Workflow

### 1. Orient on the data
- Locate `export.csv` and `data_dictionary.csv`. Read the **data dictionary first**: list the
  forms, field types, the record-ID field (it is often NOT `record_id` — see
  [[record-id-safety]]), coded choice maps, validation ranges, and branching logic.
- Load the export and report shape: N records, N fields, key variables, obvious grouping/outcome
  candidates. Note missing-data codes present ([[mdc-rules]]: `-666/-777/-888/-999`, and `666`
  as N/A sentinel) — these must be handled explicitly, never treated as real values.

### 2. Understand the study (interview)
Ask the user, grounded in what the dictionary shows:
- What **is** this study — cancer site / cohort, design (cross-sectional, cohort, pre/post)?
- What's the **unit of analysis** (one row per patient? per sample? longitudinal events)?
- What's the **question** — the outcome(s) of interest and the grouping/comparison variable(s)?
- Any **inclusion/exclusion** criteria for who counts in the analysis?
Write the answers into `README.md`.

### 3. Propose an analysis plan
Based on the study + variable types, propose a short, concrete plan — e.g. "Table 1 of
demographics & disease characteristics by treatment group (n(%) for categorical, median[IQR] for
skewed continuous), with chi-square / Mann-Whitney tests." Keep it modest and defensible. List
each planned script. Get explicit sign-off and record the plan in `README.md`.

### 4. Run it, one script at a time
For each approved analysis:
- Write `scripts/NN_name.{py,R,do}` following the **script template contract** below.
- Reuse the team's existing scripts where they fit — read them, adapt, credit in the header.
- Run it (`python3`, `Rscript`, or `stata -b do`); check availability first (`command -v`).
- Confirm outputs landed in `outputs/`; show the user the table/figure and its path.
- Append a line to `ANALYSIS_LOG.md`: date, script, what it did, headline result.

### 5. Wrap up
Keep `README.md` (plan + study notes) and `ANALYSIS_LOG.md` (run history) current. The folder
should stand alone: someone with only this directory can rerun every script and get every output.

## Language policy

- **Default: Python** (pandas + scipy.stats + statsmodels + matplotlib — the ARGO stack; no
  seaborn). Python 3.9+.
- **R / Stata** when the user prefers them or when adapting an existing R/Stata script. Keep the
  same contract (header block, reads `data/`, writes `outputs/`).
- Detect the interpreter before running; if it's missing, tell the user rather than silently
  switching languages.

## Data-handling rules (don't skip)

- **Record ID:** read it from the dictionary's first field; don't assume `record_id`.
- **Missing-data codes:** convert `-666/-777/-888/-999` (and `666` N/A) to missing before
  computing stats; report missingness explicitly. Never average a column that still contains
  sentinels. See [[mdc-rules]].
- **Coded vs labeled:** compute on raw codes, but label categories in human-facing tables/figures
  using the dictionary's choice map.
- **Checkbox fields:** exported as `field___N` 0/1 columns; expand/label from the dictionary.
- **Dates:** REDCap exports are `YYYY-MM-DD`; watch for MDC date sentinels (see
  [[redcap-date-import]]).

## Script template contract

Every Python script should follow this shape (the scaffolder drops a filled-in template):

```python
#!/usr/bin/env python3
"""01_table1.py — Table 1: characteristics by treatment group.

Study   : <study name>
Inputs  : data/export.csv, data/data_dictionary.csv
Outputs : outputs/tables/table1.csv
Author  : <name>   Date: <YYYY-MM-DD>
Assumes : one row per patient; MDC codes treated as missing.
"""
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
OUT  = Path(__file__).resolve().parent.parent / "outputs"

MDC = {-666, -777, -888, -999, 666}

def load():
    df = pd.read_csv(DATA / "export.csv")
    # ... apply MDC -> NaN, label categories from the dictionary ...
    return df

def main():
    df = load()
    # ... the analysis, in commented sections ...
    OUT.joinpath("tables").mkdir(parents=True, exist_ok=True)
    # result.to_csv(OUT / "tables" / "table1.csv", index=False)

if __name__ == "__main__":
    main()
```

Figures: matplotlib, `fig.savefig(path, dpi=150, bbox_inches="tight")`, then `plt.close(fig)`.

## Scaffolding

`scaffold.py` creates the directory contract and a starter script:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/run-analysis/scaffold.py \
    <analysis_dir> --export /path/to/export.csv --dictionary /path/to/DD.csv
```

It copies the inputs into `data/`, creates `outputs/{tables,figures}` and `scripts/`, and writes
`README.md`, `ANALYSIS_LOG.md`, and `scripts/00_explore.py` (a commented starter that loads the
data and prints a structured summary).

## See also

- [[data-export]] — get the export + data dictionary onto disk first
- [[redcap-api]] (argo-core) — base conventions
- [[mdc-rules]], [[record-id-safety]], [[redcap-date-import]] — data-handling references
