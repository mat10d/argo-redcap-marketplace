#!/usr/bin/env python3
"""scaffold.py — create the run-analysis directory contract for a study.

Sets up an organized, auditable analysis folder from a REDCap export + data
dictionary that are already on disk. Stdlib only, so it always runs.

Usage:
    python3 scaffold.py <analysis_dir> --export EXPORT.csv --dictionary DD.csv [--force]
                        [--tools /path/to/argo_tools.py]

Creates:
    <analysis_dir>/
        README.md            # study description + analysis plan (fill in)
        ANALYSIS_LOG.md      # append-only run history
        data/export.csv          # copy of the export (read-only input)
        data/data_dictionary.csv # copy of the codebook (read-only input)
        scripts/00_explore.py    # commented starter that summarizes the data
        outputs/tables/          # CSV / XLSX results land here
        outputs/figures/         # PNG / PDF figures land here

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
import datetime
import shutil
import sys
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

## Analysis plan
<numbered list of planned analyses; each maps to a script in scripts/>
1.

## How to reproduce
Run scripts in order from this directory, e.g. `{PYTHON} scripts/00_explore.py`.
Every output in `outputs/` is produced by exactly one script in `scripts/`.
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

    # Which languages this computer can run, and where they live. Recorded in the folder
    # so every script that gets written here is invoked by a full path.
    tools_module = load_tools(args.tools)
    tools_found = detect_tools(tools_module)
    tools_block, tools_log = describe_tools(tools_module, tools_found)

    # Write docs + starter, refusing to clobber unless --force.
    targets = {
        root / "README.md": (README_TEMPLATE.replace("{TOOLS}", tools_block)
                             .replace("{PYTHON}", tools_python(tools_found))),
        root / "ANALYSIS_LOG.md": LOG_TEMPLATE.replace("{TOOLS}", tools_log),
        scripts / "00_explore.py": EXPLORE_TEMPLATE,
    }
    for path, content in targets.items():
        if path.exists() and not args.force:
            print(f"skip (exists): {path}")
            continue
        path.write_text(content)
        print(f"wrote: {path}")

    print(f"\nScaffolded: {root}")
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
