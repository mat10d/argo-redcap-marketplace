#!/usr/bin/env python3
"""scaffold.py — create the run-analysis directory contract for a study.

Sets up an organized, auditable analysis folder from a REDCap export + data
dictionary that are already on disk. Stdlib only, so it always runs.

Usage:
    python3 scaffold.py <analysis_dir> --export EXPORT.csv --dictionary DD.csv [--force]

Creates:
    <analysis_dir>/
        README.md            # study description + analysis plan (fill in)
        ANALYSIS_LOG.md      # append-only run history
        data/export.csv          # copy of the export (read-only input)
        data/data_dictionary.csv # copy of the codebook (read-only input)
        scripts/00_explore.py    # commented starter that summarizes the data
        outputs/tables/          # CSV / XLSX results land here
        outputs/figures/         # PNG / PDF figures land here
"""
import argparse
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
    choice_col = next((c for c in dd.columns if "Choices" in c), None)
    type_col = next((c for c in dd.columns if c.strip().lower() == "field type"), None)
    choice_maps = {}
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

## Analysis plan
<numbered list of planned analyses; each maps to a script in scripts/>
1.

## How to reproduce
Run scripts in order from this directory, e.g. `python3 scripts/00_explore.py`.
Every output in `outputs/` is produced by exactly one script in `scripts/`.
"""

LOG_TEMPLATE = """# Analysis log

Append one line per run: date — script — what it did — headline result/notes.

"""


def main():
    ap = argparse.ArgumentParser(description="Scaffold a run-analysis study folder.")
    ap.add_argument("analysis_dir", help="Directory to create the analysis in")
    ap.add_argument("--export", required=True, help="Path to the REDCap record export CSV")
    ap.add_argument("--dictionary", required=True, help="Path to the data dictionary CSV")
    ap.add_argument("--force", action="store_true", help="Overwrite existing README/log/starter")
    args = ap.parse_args()

    export = Path(args.export).expanduser()
    dictionary = Path(args.dictionary).expanduser()
    for label, p in (("export", export), ("dictionary", dictionary)):
        if not p.is_file():
            sys.exit(f"ERROR: --{label} not found: {p}")

    root = Path(args.analysis_dir).expanduser()
    data = root / "data"
    scripts = root / "scripts"
    for d in (data, scripts, root / "outputs" / "tables", root / "outputs" / "figures"):
        d.mkdir(parents=True, exist_ok=True)

    # Copy inputs into data/ (originals stay untouched; data/ is the read-only input set).
    shutil.copy2(export, data / "export.csv")
    shutil.copy2(dictionary, data / "data_dictionary.csv")

    # Write docs + starter, refusing to clobber unless --force.
    targets = {
        root / "README.md": README_TEMPLATE,
        root / "ANALYSIS_LOG.md": LOG_TEMPLATE,
        scripts / "00_explore.py": EXPLORE_TEMPLATE,
    }
    for path, content in targets.items():
        if path.exists() and not args.force:
            print(f"skip (exists): {path}")
            continue
        path.write_text(content)
        print(f"wrote: {path}")

    print(f"\nScaffolded: {root}")
    print("Next: python3 scripts/00_explore.py   (from inside the analysis dir)")


if __name__ == "__main__":
    main()
