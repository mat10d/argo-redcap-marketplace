#!/usr/bin/env python3
"""scaffold.py — create the run-analysis directory contract for a study.

Sets up an organized, auditable analysis folder from a REDCap export + data
dictionary that are already on disk. Stdlib only, so it always runs.

Usage:
    python3 scaffold.py <analysis_dir> --export EXPORT.csv --dictionary DD.csv [--force]
                        [--tools /path/to/argo_tools.py] [--group-by FIELD]

Creates:
    <analysis_dir>/
        README.md            # study description + analysis plan (fill in)
        ANALYSIS_LOG.md      # append-only run history
        data/export.csv          # copy of the export (read-only input)
        data/data_dictionary.csv # copy of the codebook (read-only input)
        lib/                     # copy of the ARGO analysis library (Python + R)
        scripts/00_explore.py    # commented starter that summarizes the data
        scripts/01_table1.py     # Table 1, as a short list of library calls
        outputs/tables/          # CSV / XLSX results land here
        outputs/figures/         # PNG / PDF figures land here

The library is COPIED IN, not referenced: the study folder is then standalone —
someone can move it, mail it, or open it a year later and every script still runs
without the plugin being installed. README.md records what the library can do,
read from the skill's analyses/ registry, so "ready" and "planned" never drift
apart from the code.

--variables is the fields Table 1 describes; it defaults to the demographics form,
read off the data dictionary and written into the script as an explicit list, so the
script says what it counted instead of relying on a default that could change.

--group-by is the variable Table 1 is grouped by. Table 1 cannot guess it ("by
site" and "by district" are different tables), so the skill asks once and passes
the answer here. Without it the generated script carries a clearly marked
placeholder and stops with a plain instruction until someone fills it in.

It also records which analysis languages this computer can run — Python, R, Stata —
and the FULL PATH to each, into README.md and ANALYSIS_LOG.md, so every script is
run by a path that works whatever the session's PATH happens to contain. That check
lives in argo_tools.py (argo-core); point at it with --tools.

For R the check goes further and actually RUNS a trivial script, because an Rscript
that exists is not necessarily an Rscript that works. README.md records which of the
three states R is in — runs, found-but-broken, or absent — so nobody writes an R
analysis against an R that was never going to execute it.
"""
import argparse
import csv
import datetime
import shutil
import sys
import textwrap
from pathlib import Path

# The starter analysis script written into scripts/. It is intentionally
# heavily commented — it models the script-first, auditable contract and gives
# the analyst a correct, runnable starting point that already handles the
# REDCap-specific traps (record-ID detection, MDC sentinels, choice maps).
EXPLORE_TEMPLATE = '''#!/usr/bin/env python3
"""00_explore.py — orient on the dataset before any analysis.

Study   : <fill in>
Inputs  : data/export.csv, data/data_dictionary.csv
Outputs : prints a structured summary to stdout (no files written)
Author  : <fill in>   Date: <fill in>
Purpose : Understand structure (record ID, field types, choice maps) and data
          quality (missingness, MDC sentinels) so the analysis plan is grounded
          in what the data actually contains.
"""
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# REDCap missing-data codes (see argo-core mdc-rules). Treat as missing, never
# as real values. 666 is the N/A sentinel.
MDC = {-666, -777, -888, -999, 666, "-666", "-777", "-888", "-999", "666"}


def load_dictionary():
    """Read the data dictionary and return (record_id_field, choice_maps)."""
    dd = pd.read_csv(DATA / "data_dictionary.csv", dtype=str).fillna("")
    # The record-ID field is the FIRST field in the dictionary — not always
    # literally named "record_id".
    var_col = dd.columns[0]                # "Variable / Field Name"
    record_id = dd[var_col].iloc[0]
    # Build code -> label maps for radio/dropdown/checkbox fields from the
    # "Choices, Calculations, OR Slider Labels" column ("1, Yes | 2, No").
    # Two header styles exist: the website download ("Field Type", "Choices, Calculations,
    # OR Slider Labels") and the API/export style (field_type, select_choices_or_calculations).
    choice_col = next((c for c in dd.columns
                       if "Choices" in c or c.strip() == "select_choices_or_calculations"), None)
    type_col = next((c for c in dd.columns
                     if c.strip().lower() in ("field type", "field_type")), None)
    choice_maps = {}
    if not choice_col or not type_col:
        print("WARNING: couldn't find the field-type / choices columns in the data dictionary — "
              "coded fields won't be labelled. Expected 'Field Type' + 'Choices, Calculations, "
              "OR Slider Labels' (website download) or field_type + "
              "select_choices_or_calculations (API export).")
    if choice_col:
        for _, row in dd.iterrows():
            ftype = (row.get(type_col, "") if type_col else "")
            if ftype in ("radio", "dropdown", "checkbox") and row[choice_col]:
                pairs = {}
                for chunk in row[choice_col].split("|"):
                    if "," in chunk:
                        code, label = chunk.split(",", 1)
                        pairs[code.strip()] = label.strip()
                if pairs:
                    choice_maps[row[var_col]] = pairs
    return record_id, choice_maps, dd


def main():
    record_id, choice_maps, dd = load_dictionary()
    df = pd.read_csv(DATA / "export.csv", dtype=str)

    print(f"Records (rows)     : {len(df)}")
    print(f"Fields (columns)   : {df.shape[1]}")
    print(f"Record-ID field    : {record_id}")
    print(f"Coded fields w/ map: {len(choice_maps)}")

    # Missingness, counting blanks AND MDC sentinels as missing.
    print("\\nTop fields by missing/MDC rate:")
    rates = {}
    for col in df.columns:
        s = df[col]
        missing = s.isna() | (s.astype(str).str.strip() == "") | s.isin(MDC)
        rates[col] = missing.mean()
    for col, rate in sorted(rates.items(), key=lambda kv: kv[1], reverse=True)[:15]:
        print(f"  {rate:5.1%}  {col}")

    print("\\nNext: write scripts/01_<name>.py for your first analysis.")
    print("Read the data dictionary for field meanings before interpreting anything.")


if __name__ == "__main__":
    main()
'''

# The Table 1 script. It is short on purpose: every statistic comes from the
# analysis library copied into lib/, which is tested once against a golden table.
# Study scripts are lists of library calls -- they never re-derive a mean, a
# percentage or a denominator of their own.
TABLE1_TEMPLATE = '''#!/usr/bin/env python3
"""01_table1.py — Table 1: the cohort described, grouped by {GROUP_BY}.

Study   : <fill in>
Inputs  : data/export.csv, data/data_dictionary.csv
Outputs : outputs/tables/table1.xlsx, one PNG in outputs/figures/
Author  : <fill in>   Date: <fill in>
Assumes : one row per record; MDC sentinels (-666/-777/-888/-999, 666) are missing.

Every number below is produced by the ARGO analysis library in lib/python.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

# The grouping variable. Table 1 cannot guess this — "by site" and "by district"
# are different tables — so it is asked once, explicitly, and recorded here.
GROUP_BY = "{GROUP_BY}"

# The variables Table 1 describes, in the order they appear. This is the
# demographics form, read off the data dictionary when the folder was scaffolded.
# It is written out in full on purpose: a table should say what it counted.
# Edit the list to add, drop or reorder rows.
VARIABLES = {VARIABLES}

# The one variable charted by group, to go with the table. Swap in any other
# categorical variable, or set it to "" for no figure.
FIGURE_FIELD = "{FIGURE_FIELD}"

if GROUP_BY.startswith("<"):
    sys.exit("This script needs to know which variable to group Table 1 by.\\n"
             "Open scripts/01_table1.py, put the variable name into GROUP_BY near\\n"
             "the top (in quotation marks, spelled as it is in the data\\n"
             "dictionary), save the file, and run it again.")
if not VARIABLES:
    sys.exit("This script has no variables to describe.\\n"
             "Open scripts/01_table1.py and list the field names Table 1 should\\n"
             "cover in VARIABLES near the top, spelled as they are in the data\\n"
             "dictionary, then run it again.")

sys.path.insert(0, str(HERE / "lib" / "python"))
from argo_analysis.core import load_study, apply_missing         # noqa: E402
from argo_analysis.table1 import table1                          # noqa: E402
from argo_analysis.excel import write_workbook                   # noqa: E402
from argo_analysis.figures import bar_by_group                   # noqa: E402

study = apply_missing(load_study(HERE / "data" / "export.csv",
                                 HERE / "data" / "data_dictionary.csv"))
table = table1(study, group_by=GROUP_BY, variables=VARIABLES)
write_workbook({"Table 1": table}, HERE / "outputs" / "tables" / "table1.xlsx",
               notes=["Grouped by " + GROUP_BY + ".", "Made by scripts/01_table1.py."])
print("Wrote outputs/tables/table1.xlsx")

if FIGURE_FIELD:
    figure = HERE / "outputs" / "figures" / (FIGURE_FIELD + "_by_" + GROUP_BY + ".png")
    bar_by_group(study, FIGURE_FIELD, GROUP_BY, figure)
    print("Wrote outputs/figures/" + figure.name)
'''

README_TEMPLATE = """# Analysis: <study name>

## Study
- **Cohort / site:** <fill in>
- **Design:** <cross-sectional / cohort / pre-post / ...>
- **Unit of analysis:** <one row per patient / sample / event>
- **Question(s):** <outcome(s) and grouping/comparison variable(s)>
- **Inclusion / exclusion:** <who counts in the analysis>

## Data
- `data/export.csv` — REDCap record export (read-only)
- `data/data_dictionary.csv` — codebook (read-only)

## Analysis tools on this computer
{TOOLS}

## What this toolkit can do
{REGISTRY}

## Analysis plan
<numbered list of planned analyses; each maps to a script in scripts/>
1.

## How to reproduce
Run scripts in order from this directory, e.g. `{PYTHON} scripts/00_explore.py`.
Every output in `outputs/` is produced by exactly one script in `scripts/`.
`lib/` is a copy of the ARGO analysis library — the scripts import from it, so this
folder runs on its own, without the ARGO plugins installed.
"""

LOG_TEMPLATE = """# Analysis log

Append one line per run: date — script — what it did — headline result/notes.

{TOOLS}
"""

# Goes in README.md whenever R is usable here. R analyses fail at the last moment for
# a reason Python ones don't: a package the script needs isn't installed, and only the
# person at the keyboard can install it.
R_PACKAGES_NOTE = (
    "**Writing R scripts here:** prefer **base R** — it needs nothing installed and so it\n"
    "runs everywhere. If a script genuinely needs a package, check for it BEFORE running the\n"
    "script:\n"
    "\n"
    "```bash\n"
    "<full path to Rscript> -e 'requireNamespace(\"openxlsx\", quietly=TRUE)'\n"
    "```\n"
    "\n"
    "If it is missing, the person who owns this computer runs the install once, themselves:\n"
    "`install.packages(\"openxlsx\")`. Packages are never installed on someone's behalf, and a\n"
    "script is never handed over hoping the package happens to be there."
)

# What goes in README.md when the language check couldn't be run at all.
TOOLS_UNKNOWN = (
    "- Not checked. Ask your assistant to run the ARGO setup check (\"help me with ARGO\")\n"
    "  to see which of Python, R and Stata this computer can run, and always call them by\n"
    "  their full path — a session's PATH often leaves installed programs out."
)


LIB_SOURCE = Path(__file__).resolve().parent / "lib"
ANALYSES_SOURCE = Path(__file__).resolve().parent / "analyses"

# What goes in README.md when the registry couldn't be read (a stray copy of this
# script, run away from the skill). Never guesses a list of analyses.
REGISTRY_UNKNOWN = (
    "- Not listed — the analysis registry wasn't readable from here. Ask your\n"
    "  assistant what the ARGO analysis toolkit can do before assuming anything."
)


# What a Table 1 row can be made of. Coded fields have levels to count; a text
# field only has a number in it if REDCap validated it as one. Everything else --
# free text, notes, dates, uploads, section headers -- is left out here rather
# than passed to the library for it to warn about, field by field, on every run.
CATEGORICAL_TYPES = ("radio", "dropdown", "checkbox", "yesno", "truefalse")
NUMERIC_TYPES = ("calc", "slider")
NUMERIC_VALIDATIONS = ("number", "integer")


def _summarisable(kind: str, validation: str) -> bool:
    """Can this field be a Table 1 row at all?"""
    if kind in CATEGORICAL_TYPES or kind in NUMERIC_TYPES:
        return True
    if kind == "text":
        return validation.startswith(NUMERIC_VALIDATIONS)
    return False


def _dd_cell(row: dict, *names: str) -> str:
    """One cell, whichever header style the dictionary uses (website or API export)."""
    for name in names:
        if name in row and row[name]:
            return str(row[name]).strip()
    return ""


def demographics_variables(dictionary_csv: Path, group_by: "str | None" = None) -> list:
    """The default Table 1 variable list: the fields on the demographics form.

    Resolved HERE, once, and written into the generated script as an explicit list —
    not left to a library default. A Table 1 should say on its face which variables
    it counted, and the analyst should be able to edit that list without reading the
    library. Returns [] rather than guessing if the dictionary can't be read.
    """
    try:
        with open(dictionary_csv, newline="", encoding="utf-8-sig") as handle:
            rows = [r for r in csv.DictReader(handle) if r]
    except (OSError, csv.Error, UnicodeDecodeError, ValueError):
        return []
    if not rows:
        return []

    id_field = _dd_cell(rows[0], "field_name", "Variable / Field Name")
    forms = []
    for row in rows:
        form = _dd_cell(row, "form_name", "Form Name")
        if form and form not in forms:
            forms.append(form)
    if not forms:
        return []
    target = next((f for f in forms if "demograph" in f.lower()), forms[0])

    chosen = []
    for row in rows:
        name = _dd_cell(row, "field_name", "Variable / Field Name")
        form = _dd_cell(row, "form_name", "Form Name")
        kind = _dd_cell(row, "field_type", "Field Type").lower()
        validation = _dd_cell(row, "text_validation_type_or_show_slider_number",
                              "Text Validation Type OR Show Slider Number").lower()
        if not name or form != target:
            continue
        if name == id_field or (group_by and name == group_by):
            continue
        if not _summarisable(kind, validation):
            continue
        chosen.append(name)
    return chosen


def figure_field(dictionary_csv: Path, variables: list) -> str:
    """The variable the starter figure charts: the first one that HAS bars to draw.

    A coded field with a choice list, or a yes/no — anything else (a free-text
    field, a data access group) has no levels and the figure helper rightly refuses.
    Returns "" when nothing qualifies, and the generated script then writes the
    table without a figure rather than failing.
    """
    if not variables:
        return ""
    try:
        with open(dictionary_csv, newline="", encoding="utf-8-sig") as handle:
            rows = [r for r in csv.DictReader(handle) if r]
    except (OSError, csv.Error, UnicodeDecodeError, ValueError):
        return ""
    meta = {}
    for row in rows:
        name = _dd_cell(row, "field_name", "Variable / Field Name")
        if name:
            meta[name] = (
                _dd_cell(row, "field_type", "Field Type").lower(),
                _dd_cell(row, "select_choices_or_calculations",
                         "Choices, Calculations, OR Slider Labels"),
            )
    # A real choice list first — it makes the more informative chart than a yes/no.
    for name in variables:
        kind, choices = meta.get(name, ("", ""))
        if kind in ("radio", "dropdown", "checkbox") and choices:
            return name
    for name in variables:
        kind, _ = meta.get(name, ("", ""))
        if kind in ("yesno", "truefalse"):
            return name
    return ""


def render_variables(names: list) -> str:
    """The VARIABLES literal, wrapped so the generated script stays readable."""
    if not names:
        return "[]  # ← empty: list the fields Table 1 should describe"
    body = ", ".join(f'"{n}"' for n in names)
    lines = textwrap.wrap(body, width=76, break_long_words=False, break_on_hyphens=False)
    if len(lines) == 1:
        return f"[{lines[0]}]"
    return "[\n" + "\n".join(f"    {line}" for line in lines) + "\n]"


def parse_front_matter(path: Path) -> dict:
    """The `key: value` block between the first two `---` lines. Stdlib only."""
    fields = {}
    try:
        text = path.read_text()
    except OSError:
        return fields
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return fields
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def read_registry(folder: "Path | None" = None) -> list:
    """Every analyses/*.md as {name, status, summary, ...}, ready ones first.

    The registry is the ONE place that says what the toolkit can do. This function
    reads it; nothing anywhere hand-maintains a second list of analyses.
    """
    folder = Path(folder) if folder else ANALYSES_SOURCE
    if not folder.is_dir():
        return []
    entries = []
    for path in sorted(folder.glob("*.md")):
        entry = parse_front_matter(path)
        entry.setdefault("name", path.stem)
        entry.setdefault("status", "planned")
        entries.append(entry)
    entries.sort(key=lambda e: (e.get("status") != "ready", e.get("name", "")))
    return entries


def registry_block(entries: list) -> str:
    """The README section listing each analysis as ready or planned."""
    if not entries:
        return REGISTRY_UNKNOWN
    lines = []
    for entry in entries:
        ready = entry.get("status") == "ready"
        state = "**ready**" if ready else "**planned — not built yet**"
        summary = entry.get("summary", "").strip()
        lines.append(f"- **{entry.get('name')}** — {state}. {summary}".rstrip())
    lines.append("")
    lines.append("A ready analysis is written as a short script of calls into `lib/`. A planned "
                 "one does not exist: no script here can run it, and nothing should import it.")
    return "\n".join(lines)


def copy_library(root: Path) -> bool:
    """Copy the skill's analysis library (Python + R) into <study>/lib/.

    Copied rather than imported from the plugin, so the study folder stands alone:
    it can be moved, shared or reopened later and the scripts still run.
    """
    if not LIB_SOURCE.is_dir():
        return False
    shutil.copytree(
        LIB_SOURCE, root / "lib", dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )
    return True


def load_tools(explicit: "str | None" = None):
    """Load argo_tools.py — the one place language detection lives — or return None.

    Order: the path handed to us (--tools, which the skill looks up), then a copy sitting
    beside this script. This script never goes hunting through plugin folders for it:
    that search is what broke script discovery four times over, and the skill that calls
    us already knows where the file is.
    """
    here = Path(__file__).resolve().parent
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates += [here / "argo_tools.py", here / "scripts" / "argo_tools.py"]
    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            import importlib.util
            spec = importlib.util.spec_from_file_location("argo_tools", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception:
            continue
    return None


def detect_tools(module) -> "dict | None":
    """Run the language check, or return None if it isn't available. Never raises."""
    if module is None:
        return None
    try:
        return module.detect()
    except Exception:
        return None


def tools_python(found: "dict | None") -> str:
    """The full path to Python, or the bare name when the check couldn't run."""
    if not found:
        return "python3"
    return (found.get("python") or {}).get("path") or "python3"


def describe_tools(module, found: "dict | None") -> "tuple[str, str]":
    """(README block, one-line log entry) describing what this computer can run.

    Full paths, always: a script started as `Rscript ...` fails in a session whose PATH
    misses /usr/local/bin, and the same script started as `/usr/local/bin/Rscript ...`
    works. Never says a language is missing without saying how to get it.
    """
    today = datetime.date.today().isoformat()
    if module is None or found is None:
        return TOOLS_UNKNOWN, f"{today} — scaffold — folder created (analysis tools not checked)."

    lines, log_bits = [], []
    r_usable = False
    for key, name, _names, advice in module.LANGUAGES:
        entry = found.get(key, {})
        if entry.get("found") and entry.get("runs") is False:
            # Present on disk but it won't run a script. Recorded as its own state:
            # writing "R — /usr/local/bin/Rscript" here once sent an analyst off to
            # run an R script that could never have worked.
            error = entry.get("run_error") or "no reason given"
            lines.append(f"- **{name}** — found at `{entry['path']}`, but it could not run a "
                         f"test script here: {error}. Nothing R-based will run until that is "
                         f"fixed. Check it yourself with "
                         f"`{entry['path']} -e 'cat(\"ok\")'`.")
            log_bits.append(f"{name} found but not runnable")
        elif entry.get("found"):
            version = f" {entry['version']}" if entry.get("version") else ""
            runs = " — runs" if entry.get("runs") else ""
            lines.append(f"- **{name}**{version} — `{entry['path']}`{runs}")
            log_bits.append(f"{name} {entry['path']}")
            r_usable = r_usable or (key == "r" and entry.get("runs") is not False)
        else:
            lines.append(f"- **{name}** — not installed. {advice}")
            log_bits.append(f"{name} not installed")
    lines.append("")
    lines.append(f"Checked {today}. **Run every script with the full path above** — for example "
                 "`/usr/local/bin/Rscript scripts/02_name.R` — because a session's PATH often "
                 "leaves installed programs out and they then look missing.")
    lines.append("")
    lines.append("This check describes **the computer the check ran on**. If you know you have "
                 "a language that is listed as missing, the check ran somewhere else than you "
                 "expected — say so rather than trusting the line above.")
    if r_usable:
        lines.append("")
        lines.append(R_PACKAGES_NOTE)
    return "\n".join(lines), f"{today} — scaffold — folder created. Tools: " + "; ".join(log_bits) + "."


def main():
    ap = argparse.ArgumentParser(description="Scaffold a run-analysis study folder.")
    ap.add_argument("analysis_dir", help="Directory to create the analysis in — normally "
                                         "data-analyst/<study>")
    ap.add_argument("--export", required=True, help="Path to the REDCap record export CSV")
    ap.add_argument("--dictionary", required=True, help="Path to the data dictionary CSV")
    ap.add_argument("--force", action="store_true", help="Overwrite existing README/log/starter")
    ap.add_argument("--variables", default=None, metavar="F1,F2,…",
                    help="The fields Table 1 describes, comma-separated. Defaults to the "
                         "demographics form, read from the data dictionary. Whatever is "
                         "used is written into the generated script as an explicit list.")
    ap.add_argument("--group-by", default=None, metavar="FIELD",
                    help="The variable Table 1 is grouped by, spelled as in the data "
                         "dictionary. Table 1 cannot guess it — 'by site' and 'by district' "
                         "are different tables — so ask the user once and pass the answer "
                         "here. Without it the generated script carries a marked placeholder "
                         "and stops with a plain instruction until it is filled in.")
    ap.add_argument("--tools", default=None, metavar="ARGO_TOOLS.PY",
                    help="Path to argo_tools.py (the Python/R/Stata check in argo-core). The "
                         "skill finds it for you; the detected full paths are written into "
                         "README.md so scripts are always run by a path that works.")
    args = ap.parse_args()

    export = Path(args.export).expanduser()
    dictionary = Path(args.dictionary).expanduser()
    for label, p in (("export", export), ("dictionary", dictionary)):
        if not p.is_file():
            sys.exit(
                f"I couldn't find the {label} file:\n"
                f"    {p}\n"
                "\n"
                "Check the name and folder are right. If the path has spaces in it, put quotation\n"
                "marks around it."
            )

    root = Path(args.analysis_dir).expanduser()
    data = root / "data"
    scripts = root / "scripts"
    for d in (data, scripts, root / "outputs" / "tables", root / "outputs" / "figures"):
        d.mkdir(parents=True, exist_ok=True)

    # Copy inputs into data/ (originals stay untouched; data/ is the read-only input set).
    shutil.copy2(export, data / "export.csv")
    shutil.copy2(dictionary, data / "data_dictionary.csv")

    # Copy the analysis library in, so the scripts below run from this folder alone.
    library_copied = copy_library(root)

    # What the library can do, read from the skill's registry — never hand-listed.
    registry = read_registry()

    # Which languages this computer can run, and where they live. Recorded in the folder
    # so every script that gets written here is invoked by a full path.
    tools_module = load_tools(args.tools)
    tools_found = detect_tools(tools_module)
    tools_block, tools_log = describe_tools(tools_module, tools_found)

    # Write docs + starter, refusing to clobber unless --force.
    group_by = args.group_by or "<FILL IN — the variable to group Table 1 by>"
    if args.variables:
        variables = [v.strip() for v in args.variables.split(",") if v.strip()]
    else:
        variables = demographics_variables(data / "data_dictionary.csv", args.group_by)
    charted = figure_field(data / "data_dictionary.csv", variables)
    targets = {
        root / "README.md": (README_TEMPLATE.replace("{TOOLS}", tools_block)
                             .replace("{REGISTRY}", registry_block(registry))
                             .replace("{PYTHON}", tools_python(tools_found))),
        root / "ANALYSIS_LOG.md": LOG_TEMPLATE.replace("{TOOLS}", tools_log),
        scripts / "00_explore.py": EXPLORE_TEMPLATE,
        scripts / "01_table1.py": (TABLE1_TEMPLATE.replace("{GROUP_BY}", group_by)
                                   .replace("{VARIABLES}", render_variables(variables))
                                   .replace("{FIGURE_FIELD}", charted)),
    }
    for path, content in targets.items():
        if path.exists() and not args.force:
            print(f"skip (exists): {path}")
            continue
        path.write_text(content)
        print(f"wrote: {path}")

    print(f"\nScaffolded: {root}")
    if library_copied:
        print(f"Analysis library copied to: {root / 'lib'} (Python + R)")
    else:
        print("NOTE: the analysis library wasn't found next to this script, so lib/ is "
              "empty and scripts/01_table1.py has nothing to import yet.")
    if registry:
        ready = [e["name"] for e in registry if e.get("status") == "ready"]
        planned = [e["name"] for e in registry if e.get("status") != "ready"]
        print("What this toolkit can do: "
              + "; ".join([f"{n} — ready" for n in ready] + [f"{n} — planned" for n in planned]))
    if variables:
        print(f"Table 1 variables ({len(variables)}, from the demographics form): "
              + ", ".join(variables[:8]) + ("…" if len(variables) > 8 else ""))
    else:
        print("NOTE: no variables could be read from the data dictionary — list them in "
              "VARIABLES at the top of scripts/01_table1.py.")
    if charted:
        print(f"Table 1 figure: {charted} by the grouping variable.")
    else:
        print("NOTE: no variable on that form can be charted as bars — 01_table1.py will "
              "write the table only. Set FIGURE_FIELD to chart one.")
    if not args.group_by:
        print("No --group-by given: scripts/01_table1.py will stop and ask for the grouping "
              "variable until it is filled in.")
    print("\nAnalysis tools on this computer:")
    if tools_found is None:
        print("  Not checked — pass --tools /path/to/argo_tools.py to have this filled in.")
        python = "python3"
    else:
        tools_module.report(tools_found)
        python = tools_python(tools_found)
    print(f"\nNext: {python} scripts/00_explore.py   (from inside the analysis dir)")


if __name__ == "__main__":
    main()
