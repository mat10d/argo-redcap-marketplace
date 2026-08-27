---
name: run-analysis
description: Clean, analyse and chart a REDCap study you have already downloaded — the data export and its data dictionary, as files on your computer. Asks about the study, agrees a simple analysis plan with you, then does the work as saved, well-commented scripts (Python, R or Stata) with tidy, traceable outputs anyone can re-run. Use for a Table 1, descriptive statistics, comparing groups, a figure or plot, or tidying a messy export before you work with it. Nothing here connects to REDCap and no access key is involved at any point.
allowed-tools: Read, Bash, Write, Edit, Glob, Grep
---

# run-analysis

Turn a downloaded REDCap dataset into analysis — **reproducibly**. This skill never runs
ad-hoc, throwaway analysis. Every result is produced by a saved, commented script, written to
an organized directory, so a teammate (or a reviewer, or future-you) can see exactly what was
run and re-run it.

It works entirely from the two files on your computer — nothing here connects to REDCap, and no
access key is involved anywhere.

## When to use

A teammate says any of: "analyze this export," "make a Table 1," "summarize the CRC cohort,"
"compare X by Y," "plot …," "run some descriptives on the data I downloaded."

If they haven't downloaded the data yet, walk them through getting it off the REDCap website:
[[getting-files-from-redcap]] has the click-by-click steps, written for someone who doesn't know
REDCap's menus.

## What I can do

The analyses this toolkit knows how to do live in the skill's `analyses/` folder — one
file per analysis. **Read that folder before answering "can you do X?"** Each file states
the analysis's status, what it needs from the user, the files it produces, and the exact
library calls a study script makes.

| Analysis | Status | What it is |
|---|---|---|
| `table1` | **ready** | Table 1 — the cohort described, by a grouping variable you choose. |
| `survival` | **planned** | Time-to-event with Kaplan–Meier + Cox — **not built yet.** |

**Ready** means the library does it — tested once against a golden table — and a study
script is a handful of calls into `lib/`. **Planned** means it does **not exist**: never
tell a user the toolkit does it, never import the module, never generate a script that
calls it. If someone asks for a planned analysis, say plainly that it isn't built yet,
and offer it as an ordinary hand-written script (below) instead.

Anything not in the registry is still possible — it is just a hand-written script held to
the same script-first rules, not a library call.

## Inputs (assumed already on disk)

1. **The data export** — a REDCap record export, normally CSV (raw-coded preferred; labeled is
   fine if that's what they have).
2. **The data dictionary** — the project's data dictionary / codebook CSV (REDCap "Download
   Data Dictionary"). This is how you understand field types, coded values, validation,
   branching, and the record-ID field. Do not proceed without it — guessing variable meaning is
   how analyses go wrong.
3. *(optional)* **Existing analysis scripts** — Python/R/Stata the team already wrote. Reuse and
   adapt these rather than reinventing; ask the user where they live.

**Ask where the data is — never go hunting and assume.** If they haven't attached the files or
named them, ask. If you can see likely candidates in the folder, don't pick one silently: name
what you found and confirm with **one** question — "I can see `crc_export_2026-08-19.csv` and a
data dictionary in `data-analyst/` — are those the two files?" A session once nearly analysed a
synthetic test export as if it were the real study. One wrong file is a wrong answer with no
warning attached.

If a required input doesn't exist yet, [[getting-files-from-redcap]] is the click-by-click
download.

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
data-analyst/<study>/
├── README.md            # study description, the agreed plan, what the toolkit can do
├── ANALYSIS_LOG.md      # append-only: what was run, when, which script, result/notes
├── data/                # READ-ONLY inputs
│   ├── export.csv           # the REDCap record export
│   └── data_dictionary.csv  # the codebook
├── lib/                 # a COPY of the ARGO analysis library (python/ and R/)
├── scripts/             # saved, commented analysis scripts: NN_short_name.{py,R,do}
└── outputs/
    ├── tables/          # XLSX results (one workbook per analysis)
    └── figures/         # PNG, 300 dpi
```

Scripts are numbered in run order (`01_table1.py`, `02_stage_by_site.R`, …). `lib/` is a
copy, not a link: the folder then stands alone — it can be moved, mailed, or reopened a
year later and every script still runs, with no ARGO plugin installed.

## Workflow

### 0. Check what this computer can run, and scaffold the folder

Do this once per study, **before** writing any script — and after you have the two file paths
from the user (see **Inputs** above: ask, don't hunt). Never decide a language is missing from a
bare `command -v` — the session's shell has a thin PATH (it usually leaves out `/usr/local/bin`),
so `command -v Rscript` says "not installed" on machines where R is installed and works. That
exact mistake was made on a machine with `/usr/local/bin/Rscript` sitting right there.

```bash
T=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name argo_tools.py 2>/dev/null | head -1)
python3 "$T"
```

It prints Python, R and Stata with a ✓ or ✗ and the **full path** to each. For R it also
runs a trivial script, so R comes back in one of three states — `R 4.4.0 ✓ (runs)`,
`R found but couldn't run a test script: <error>`, or `R ✗ not found`. Then:

- Tell the user in **one line** which languages are usable ("Python and R are both ready here;
  Stata isn't installed on this computer") — and nothing more unless they ask.
- **Use the full paths it reports, in every command from then on** — `/usr/local/bin/Rscript
  scripts/02_x.R`, not `Rscript scripts/02_x.R`. The bare name is exactly what fails.
- If the language they want is missing, say how to get it (R is free: https://cran.r-project.org;
  Stata is licensed — their IT installs it) and offer the same analysis in a language they do
  have. Never leave them stuck.
- **The check describes the computer it ran on.** If someone says they have R and the check
  says they don't, the check ran somewhere other than their machine — say that plainly instead
  of insisting. Never write "not installed on this computer" into a study folder you can't
  stand behind.
- Then scaffold, passing the check through so the paths land in the study folder — see
  [Scaffolding](#scaffolding) below.

#### If the analysis is going to be in R

R is the one language that fails *after* you've written the script. Two extra beats, both
before you write anything:

1. **Confirm R runs**, not just that it exists — that's the `(runs)` above. If it reports
   *found but couldn't run a test script*, R is broken on that machine: give the user the one
   command to see it for themselves (the check prints it), and offer the analysis in Python
   meanwhile. Don't write R against an R that can't execute.
2. **Check the packages the script needs, before writing it.** Prefer **base R** — a base-R
   script needs nothing installed and runs on any clean R. If a package is genuinely needed
   (`openxlsx` for styled Excel, say), test for it first, using the Rscript path the check
   reported:

   ```bash
   /usr/local/bin/Rscript -e 'requireNamespace("openxlsx", quietly=TRUE)'
   ```

   If it's missing, **tell the user the exact line to run once, plainly** — "R needs one
   package for this. Run `install.packages("openxlsx")` in R once, and I'll carry on" — and
   wait. **Never install packages silently**, and never hand over a script hoping the package
   is there.

**Never try to install R itself.** In Cowork, scripts execute in a Linux sandbox with the
user's disk mounted in: the R (or Stata) on their Mac is *visible* but **cannot run there**
(`Exec format error` — a macOS program inside a Linux VM). There is also no root, `apt` is
locked, and commands are capped at a couple of minutes — an R install cannot finish, and
attempting it burns the session for nothing. This is the normal state of affairs, not a broken
machine: say so in one line, write the R script anyway, and hand the user the exact command to
run it on their own computer (or the RStudio steps), then compare their output with the Python
table for parity.

### 1. Orient on the data
- Open the two files `scaffold.py` copied into `data/`. Read the **data dictionary first**:
  list the forms, field types, the record-ID field (it is often NOT `record_id` — see
  [[record-id-safety]]), coded choice maps, validation ranges, and branching logic.
- Load the export and report shape: N records, N fields, key variables, obvious grouping/outcome
  candidates. Note missing-data codes present ([[mdc-rules]]: `-666/-777/-888/-999`, and `666`
  as N/A sentinel) — these must be handled explicitly, never treated as real values.

### 2. Understand the study (interview)
Ask these **one at a time**, in this order, each time saying what you already worked out from the
dictionary so they only have to correct you. Never send the list as a block.

1. What **is** this study — cancer site / cohort, design (cross-sectional, cohort, pre/post)?
2. What's the **unit of analysis** (one row per patient? per sample? longitudinal events)?
3. What's the **question** — the outcome(s) of interest and the grouping/comparison variable(s)?
4. Any **inclusion/exclusion** criteria for who counts in the analysis?

Where the data dictionary already answers one, infer it and confirm rather than asking cold —
"this looks like one row per patient, with `treatment_group` as the obvious comparison; right?"
Write the answers into `README.md`.

**The grouping variable is asked ONCE, explicitly, and never guessed.** It is the one
thing a Table 1 cannot infer, and getting it wrong is invisible: a session that assumed
**"by site"** when the analyst meant **"by district"** produced a table that looked
entirely correct and answered a different question. So name the candidates you can
actually see in the data dictionary and ask one plain question — "group by `site` (the
data access group), or by `district`?" — take the answer, write it into `README.md`, and
put it into the Table 1 script. Once. Don't re-ask it for every script, and don't quietly
change it later.

The folder is usually scaffolded at step 0, before you have asked — so **both** Table 1
scripts, `01_table1.py` and its R twin `01_table1.R`, start with a marked placeholder, and
`README.md` says the answer is still owed. Once you have it, either set `GROUP_BY` at the
top of both scripts and write it into `README.md`'s Study block, or — while the folder is
still untouched — re-run `scaffold.py --group-by <variable> --force`, which fills in all
three at once (it rewrites `README.md`, so don't reach for it after the interview answers
are in there). Never run a placeholder script hoping; it stops and tells you what it needs.

### 3. Propose an analysis plan
Based on the study + variable types, propose a short, concrete plan — e.g. "Table 1 of
demographics & disease characteristics by treatment group (n(%) for categorical, median[IQR] for
skewed continuous), with chi-square / Mann-Whitney tests." Keep it modest and defensible. List
each planned script, and say for each whether it is a **registry analysis** (a script of
library calls) or a **hand-written** one. Get explicit sign-off and record the plan in
`README.md`.

### 4. Run it, one script at a time
For each approved analysis:
- **If it is in the registry, the script is library calls — not hand-written statistics.**
  `load_study` → `apply_missing` → the analysis → `write_workbook` and a figure.
  **Never re-derive a mean, a percentage or a denominator** inside a study script: those
  live in `lib/`, tested once against a golden table, and a script that recomputes them
  is how two studies end up with two different Table 1s from the same data. `scaffold.py`
  already wrote `scripts/01_table1.py` **and its R twin `scripts/01_table1.R`** — the same
  calls writing the same files, so only one of them is ever run: the Python one here, or —
  where the user works in R and this session cannot execute it (step 0) — the R one handed
  over with its command, for them to run on their own machine. Read it before writing
  anything else.
- **If it is not in the registry**, write `scripts/NN_name.{py,R,do}` by hand, following
  the **script template contract** below — same header block, same folders, same rules.
- Reuse the team's existing scripts where they fit — read them, adapt, credit in the header.
- Run it **by the full interpreter path from step 0** — e.g. `/usr/bin/python3 scripts/01_x.py`,
  `/usr/local/bin/Rscript scripts/02_x.R`, `/Applications/Stata/StataSE.app/Contents/MacOS/StataSE
  -b do scripts/03_x.do`. The paths are recorded in the study's `README.md`.
- Confirm outputs landed in `outputs/`; show the user the table/figure and its path.
- Append a line to `ANALYSIS_LOG.md`: date, script, what it did, headline result.

### 5. Wrap up
Keep `README.md` (plan + study notes) and `ANALYSIS_LOG.md` (run history) current. The folder
should stand alone: someone with only this directory can rerun every script and get every output.

## Language policy

- **Default: the library** — a registry analysis is `lib/` calls in whichever language the
  user works in. Python and R do the same things, with the same function names.
- **Default language: Python** (pandas + scipy.stats + statsmodels + matplotlib — the ARGO
  stack; no seaborn). Python 3.9+. This is what the library itself is built on, and what
  a hand-written script should use.
- **R / Stata** when the user prefers them or when adapting an existing R/Stata script. Keep the
  same contract (header block, reads `data/`, writes `outputs/`).
- **In R, default to base R.** Base R needs nothing installed, so a base-R script runs on any
  machine that has R at all. Reach for a package only when base R genuinely can't do the job,
  and then get it installed by the user first (step 0) rather than discovering it at run time.
- **Which of the three are actually available is settled by step 0's check, not by `command -v`,
  and never by guessing.** For R, "available" means it **ran a test script** — not that the file
  exists. If the language they want isn't installed, say so with how to get it, and offer the
  analysis in one they have — don't switch silently.

## Data-handling rules (don't skip)

- **Record ID:** read it from the dictionary's first field; don't assume `record_id`.
- **Missing-data codes:** convert `-666/-777/-888/-999` (and `666` N/A) to missing before
  computing stats; report missingness explicitly. Never average a column that still contains
  sentinels. See [[mdc-rules]].
- **Level order:** categorical levels appear in **codebook order** (the order of the choice
  list in the data dictionary), never alphabetical — "Single, Married, Widowed, Divorced" as
  the form lists them, not "Divorced, Married, …".
- **Coded vs labeled:** compute on raw codes, but label categories in human-facing tables/figures
  using the dictionary's choice map.
- **Checkbox fields:** exported as `field___N` 0/1 columns; expand/label from the dictionary.
- **Dates:** REDCap exports are `YYYY-MM-DD`; watch for MDC date sentinels (see
  [[redcap-date-import]]).

## House style for outputs

Every analysis produces output that looks the same, so someone who has read one ARGO
table has read them all. **One workbook per analysis** (`outputs/tables/<analysis>.xlsx`)
— not one workbook per table and not a scatter of loose CSVs; **one sheet per table**,
named for the table, bold header row, frozen top row, columns fitted; and a final
**`Notes` sheet** on every workbook carrying N, the missing-data rule, the
applicable-denominator rule, the generating script and the date, so a table that leaves
the folder can be read on its own without anyone guessing what it counted. **Figures are
PNG at 300 dpi**, one consistent look, colourblind-safe, title = the field's label,
subtitle = `n = … ; missing = …` — and **the script that made a figure is its
provenance**: every PNG in `outputs/figures/` comes from exactly one script in `scripts/`,
and that script's name is the answer when someone asks where a figure came from.

`write_workbook` and the figure helpers apply all of this for you. Don't restyle by hand,
and don't invent a different layout for one study.

## Script template contract

A registry analysis is a short script of library calls — this is what `scaffold.py`
writes, and what a hand-written one should look like too:

```python
#!/usr/bin/env python3
"""01_table1.py — Table 1: the cohort described, grouped by site.

Study   : <study name>          Author  : <name>   Date: <YYYY-MM-DD>
Inputs  : data/export.csv, data/data_dictionary.csv
Outputs : outputs/tables/table1.xlsx, outputs/figures/sex_by_site.png
Assumes : one row per patient; MDC codes treated as missing.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "lib" / "python"))
from argo_analysis.core import load_study, apply_missing
from argo_analysis.table1 import table1
from argo_analysis.excel import write_workbook
from argo_analysis.figures import bar_by_group

GROUP_BY  = "site"          # asked once, explicitly — never guessed
VARIABLES = ["age", "sex", "education", "marital_status", "tobacco_use"]

study = apply_missing(load_study(HERE / "data" / "export.csv",
                                 HERE / "data" / "data_dictionary.csv"))
table = table1(study, group_by=GROUP_BY, variables=VARIABLES)
write_workbook({"Table 1": table}, HERE / "outputs" / "tables" / "table1.xlsx",
               notes=["Grouped by " + GROUP_BY + ".", "Made by scripts/01_table1.py."])
bar_by_group(study, "sex", GROUP_BY, HERE / "outputs" / "figures" / "sex_by_site.png")
```

Fifteen lines, and not one statistic of its own. In R it is the same call sequence,
sourced from `lib/R/argo_analysis/`.

For an analysis the library doesn't cover, write it by hand in the same shape:

```python
#!/usr/bin/env python3
"""02_<name>.py — <what this analysis does, in one line>.

Study   : <study name>
Inputs  : data/export.csv, data/data_dictionary.csv
Outputs : outputs/tables/<name>.xlsx
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
    # One workbook, one sheet per table, a Notes sheet — the house style above. Use the
    # library's writer even here: from argo_analysis.excel import write_workbook
    # write_workbook({"<sheet>": result}, OUT / "tables" / "<name>.xlsx", notes=[...])

if __name__ == "__main__":
    main()
```

Figures: matplotlib, `fig.savefig(path, dpi=300, bbox_inches="tight")`, then
`plt.close(fig)` — or just call `argo_analysis.figures`, which already does exactly that.

## Scaffolding

`scaffold.py` creates the directory contract and a starter script:

```bash
S=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name scaffold.py 2>/dev/null | head -1)
T=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name argo_tools.py 2>/dev/null | head -1)
python3 "$S" data-analyst/<study> \
    --export /path/to/export.csv --dictionary /path/to/DD.csv --tools "$T" \
    --group-by <the grouping variable>      # optional at this point — see below
```

It copies the inputs into `data/`, copies the **analysis library** into `lib/` (Python and
R), creates `outputs/{tables,figures}` and `scripts/`, and writes `README.md`,
`ANALYSIS_LOG.md`, `scripts/00_explore.py` (a commented starter that loads the data and
prints a structured summary) and the Table 1 as library calls in **both languages** —
`scripts/01_table1.py` and `scripts/01_table1.R`, twins that make the same numbers and
write the same files. `README.md` records the grouping variable and variable list that
were used, the command for each script with its full interpreter path, and what the
toolkit can do, read from the `analyses/` registry — ready and planned, so the study
folder can't drift from the code.

`--variables` is what Table 1 describes. Leave it out and it defaults to the
demographics form, read off the data dictionary — either way the list is written into
both scripts in full, and into `README.md`, so the table says what it counted and the
analyst can edit it without touching the library.

`--group-by` is the grouping variable, from the one question in step 2. Pass it if you
already have the answer. If you are scaffolding first (the usual order), leave it out:
both generated scripts then carry a clearly marked placeholder and stop with a plain
instruction rather than guessing — no wrong table, but no table either. Fill it in after
step 2, by editing `GROUP_BY` or re-running with `--group-by … --force`.

`--tools` runs the same language check as step 0 and writes the **full path** to each usable
language into `README.md` and the first `ANALYSIS_LOG.md` line, so anyone re-running the folder
later (including you, in a session with a different PATH) has the commands that work.

## The analysis library

`lib/` in this skill is the analysis library: the same capabilities in **Python and R** —
same function names, same output shapes — that an analysis composes rather than
reimplements. `scaffold.py` copies it into each study folder.

- `core` — `load_study`, `apply_missing`, `labels`, `applicable`, `denominator`. Branching
  logic is evaluated, so a categorical percentage is out of the records the field actually
  applied to, not out of everyone.
- `table1` — the Table 1 itself: `table1(study, group_by, variables)`. Both arguments
  are explicit — no default grouping, and the variable list is written into the script.
- `excel` — `write_workbook`: the house style above, applied for you.
- `figures` — `bar_by_group`, `hist`: 300 dpi PNG, one consistent look.
- `survival` — **planned, not built.** Every function in it stops with the same sentence:
  "Survival analysis is planned but not built yet". Don't import it, don't offer it.

**What the library can do is the registry in `analyses/` — read it, don't recall it.**
Ready today: `table1`. Planned: `survival`. When a new analysis lands, its registry file
is what says so; this section and the table at the top of the skill are checked against
those files by a test, so they cannot drift apart.

## See also

- [[getting-files-from-redcap]] — how to download the export + data dictionary from the REDCap
  website, click by click (no access key)
- [[mdc-rules]], [[record-id-safety]], [[redcap-date-import]] — data-handling references
- [[link-data]] (argo-database-manager) — when the analysis needs more than one database merged together
- [[export-data]] — only if you're a database manager with an access key for the study; it does
  the same download for you
