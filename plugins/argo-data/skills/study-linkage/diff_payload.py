#!/usr/bin/env python3
"""diff_payload.py — build a safe, diff-only REDCap write-back payload.

Given the COMPUTED state (what linkage says each field should be) and the
CURRENT state (what's in REDCap now), both keyed by an ID field, emit three
files that enforce the core ARGO write-back guardrail: computed values only ever
FILL blanks; disagreements are quarantined for human review, never auto-pushed.

    <prefix>_update.csv     safe-fills only (current blank -> computed value).
                            Push with overwriteBehavior=normal.
    <prefix>_conflicts.csv  long format: id, field, existing, computed.
                            For human triage. NOT pushed.
    <prefix>_overwrite.csv  the conflict rows, wide, with computed values.
                            Push ONLY after explicit sign-off (overwrite mode).

Stdlib only. Compares only the fields present in BOTH files (minus the ID),
unless --fields is given.

Usage:
    python3 diff_payload.py --computed computed.csv --current current.csv \\
        --id-field record_id --out-dir outputs/ [--prefix linkage] [--fields a,b,c]
"""
import argparse
import csv
import os
import sys
from pathlib import Path


def _add_argo_core_to_path():
    """Locate argo-core by marker file — never by directory name (see access-tiers.md)."""
    marker = "argo_redcap_client.py"
    override = os.environ.get("ARGO_CORE_SCRIPTS")
    if override and (Path(override).expanduser() / marker).exists():
        sys.path.insert(0, str(Path(override).expanduser())); return
    for root in ("/mnt/.remote-plugins", "/mnt/skills", "~/.claude/plugins", "~/.claude/plugins/cache"):
        base = Path(root).expanduser()
        if base.is_dir():
            hits = sorted(base.glob(f"**/{marker}"))
            if hits:
                sys.path.insert(0, str(hits[-1].parent)); return
    for parent in Path(__file__).resolve().parents:
        for cand in (parent / "plugins" / "argo-core" / "skills" / "redcap-api" / "scripts",
                     parent / "plugins" / "argo-core" / "scripts",
                     parent / "argo-core" / "scripts"):
            if (cand / marker).exists():
                sys.path.insert(0, str(cand)); return


_add_argo_core_to_path()
# The fill-vs-conflict rule lives in argo-core so redcap-qa and study-linkage share one
# implementation of the same guarantee, rather than each owning a slightly different copy.
from argo_diff import norm, diff_records, FILL, CONFLICT, NOOP  # noqa: E402


def load(path, id_field):
    """Load a CSV into {id: {field: value}} and return (rows, fieldnames)."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if id_field not in (reader.fieldnames or []):
            raise SystemExit(f"ERROR: id field '{id_field}' not in {path}")
        rows = {}
        for r in reader:
            rows[norm(r[id_field])] = r
        return rows, reader.fieldnames


def main():
    ap = argparse.ArgumentParser(description="Build a diff-only REDCap write-back payload.")
    ap.add_argument("--computed", required=True, help="CSV of desired/computed state")
    ap.add_argument("--current", required=True, help="CSV of current REDCap state")
    ap.add_argument("--id-field", required=True, help="Key field present in both CSVs")
    ap.add_argument("--out-dir", required=True, help="Directory for the three output files")
    ap.add_argument("--prefix", default="linkage", help="Filename prefix (default: linkage)")
    ap.add_argument("--fields", default="", help="Comma-separated fields to compare (default: all shared)")
    args = ap.parse_args()

    computed, comp_cols = load(args.computed, args.id_field)
    current, curr_cols = load(args.current, args.id_field)

    # Fields to compare: explicit list, else the intersection (minus the ID).
    if args.fields:
        fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    else:
        fields = [c for c in comp_cols if c in set(curr_cols) and c != args.id_field]
    if not fields:
        raise SystemExit(
            "The two files have no columns in common, so there's nothing to compare.\n"
            "\n"
            "Check that both files really are the ones you meant, and that their column headings\n"
            "match. If the same information is under different headings in each file, say which\n"
            "ones to compare with --fields."
        )

    result = diff_records(computed, current, fields, args.id_field)
    updates, conflicts, overwrites = result["updates"], result["conflicts"], result["overwrites"]
    n_fill = result["counts"][FILL]
    n_conflict = result["counts"][CONFLICT]
    n_noop = result["counts"][NOOP]

    out = Path(args.out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    def write(name, rows, header):
        path = out / name
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(rows)
        return path

    header = [args.id_field] + fields
    p_update = write(f"{args.prefix}_update.csv", updates, header)
    p_conf = write(f"{args.prefix}_conflicts.csv", conflicts,
                   [args.id_field, "field", "existing", "computed"])
    p_over = write(f"{args.prefix}_overwrite.csv", overwrites, header)

    print(f"safe-fills : {n_fill}  ({len(updates)} records)  -> {p_update.name}")
    print(f"conflicts  : {n_conflict}  ({len(overwrites)} records) -> {p_conf.name} / {p_over.name}")
    print(f"no-ops     : {n_noop}")
    print(f"\nDry-run complete. Review before pushing. Push {p_update.name} with overwriteBehavior=normal.")
    print(f"Only push {p_over.name} (overwrite) after explicit sign-off on {p_conf.name}.")


if __name__ == "__main__":
    main()
