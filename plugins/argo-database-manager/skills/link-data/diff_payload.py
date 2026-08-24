#!/usr/bin/env python3
"""diff_payload.py — build a safe, diff-only REDCap write-back payload, plus the gap reports.

Given the COMPUTED state (what linkage says each field should be) and the
CURRENT state (what's in REDCap now), both keyed by an ID field, emit five
files. Three are the payload, and they enforce the core ARGO write-back
guardrail — computed values only ever FILL blanks; disagreements are quarantined
for human review, never auto-pushed:

    <prefix>_update.csv     safe-fills only (current blank -> computed value),
                            and only for records that already exist in REDCap.
                            Push with overwriteBehavior=normal.
    <prefix>_conflicts.csv  long format: id, field, existing, computed.
                            For human triage. NOT pushed.
    <prefix>_overwrite.csv  the conflict rows, wide, with computed values.
                            Push ONLY after explicit sign-off (overwrite mode).

The other two are the gap report — the two ways the id spaces fail to line up:

    <prefix>_orphans.csv    ids present ONLY on the computed side. There is no
                            record to fill, so these are never in the payload:
                            pushing them would CREATE records. A human decides
                            whether they belong in the project at all.
    <prefix>_missing_link.csv  ids present ONLY on the current side — records
                            the linkage found nothing for. Nothing is written
                            for them; they are here so the gap is visible.

Stdlib only. Compares only the fields present in BOTH files, unless --fields is
given. By default the ID field, REDCap's structural columns
(redcap_data_access_group, redcap_event_name, redcap_repeat_instrument,
redcap_repeat_instance) and the per-form `*_complete` status columns are left
out of the comparison — they describe how REDCap stores a record, not what the
record says, and treating them as linkable data moves people between data access
groups. Name them in --fields if you really do mean to compare them.

Reading the two sides for an ANALYSIS merge, with no intention of writing anything back? Add
`--for-analysis`. The same comparison runs, but the two payload files are named for what they
mean to a reader rather than for a REDCap import — `<prefix>_fills.csv` (values one source has
and the other doesn't) and `<prefix>_disagreements.csv` (values the two sources contradict each
other on) — and nothing is printed about pushing. The conflicts, orphans and missing-link
reports are written either way; they are the merge's gap report, not a payload.

Usage:
    python3 diff_payload.py --computed computed.csv --current current.csv \\
        --id-field record_id --out-dir database-manager/linkage/<name>/ \\
        [--prefix linkage] [--fields a,b,c] [--for-analysis]
"""
import argparse
import csv
import sys
from pathlib import Path


# The shared ARGO scripts are vendored into this skill's own scripts/ folder by release.py,
# so imports never depend on where — or whether — other plugins are installed. The parents walk
# is only for running from a source checkout before the first sync.
_here = Path(__file__).resolve().parent
for _cand in (_here / "scripts",
              *(p / "plugins/argo-core/skills/redcap-api/scripts" for p in _here.parents)):
    if (_cand / "argo_redcap_client.py").exists():
        sys.path.insert(0, str(_cand))
        break
# The fill-vs-conflict rule lives in argo-core so qa-worklists and link-data share one
# implementation of the same guarantee, rather than each owning a slightly different copy.
from argo_diff import norm, diff_records, FILL, CONFLICT, NOOP, ORPHAN  # noqa: E402


# REDCap's own bookkeeping columns. They appear in every export, so a plain intersection of
# column names picks them up and quietly treats them as data to link on — which for
# redcap_data_access_group means proposing to move records between sites.
REDCAP_STRUCTURAL_COLUMNS = (
    "redcap_data_access_group",
    "redcap_event_name",
    "redcap_repeat_instrument",
    "redcap_repeat_instance",
)


def is_structural(column: str) -> bool:
    """True for REDCap's own bookkeeping columns, which are never linkage data by default."""
    return column in REDCAP_STRUCTURAL_COLUMNS or column.endswith("_complete")


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
    ap.add_argument("--out-dir", required=True, help="Directory for the five output files — "
                                                     "normally database-manager/linkage/<name>/")
    ap.add_argument("--prefix", default="linkage", help="Filename prefix (default: linkage)")
    ap.add_argument("--fields", default="",
                    help="Comma-separated fields to compare (default: every shared column except "
                         "the ID, REDCap's structural columns and the *_complete columns)")
    ap.add_argument("--for-analysis", action="store_true",
                    help="Merging two sources for analysis, not writing back to REDCap: name the "
                         "two files _fills.csv and _disagreements.csv, and say nothing about "
                         "pushing")
    args = ap.parse_args()

    computed, comp_cols = load(args.computed, args.id_field)
    current, curr_cols = load(args.current, args.id_field)

    # Fields to compare: explicit list, else the intersection (minus the ID and the columns
    # REDCap keeps for itself — see REDCAP_STRUCTURAL_COLUMNS).
    skipped = []
    if args.fields:
        fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    else:
        shared = [c for c in comp_cols if c in set(curr_cols) and c != args.id_field]
        fields = [c for c in shared if not is_structural(c)]
        skipped = [c for c in shared if is_structural(c)]
    if not fields:
        raise SystemExit(
            "The two files have no columns in common to compare.\n"
            "\n"
            "Check that both files really are the ones you meant, and that their column headings\n"
            "match. If the same information is under different headings in each file, say which\n"
            "ones to compare with --fields."
            + ("\n\nThe only shared columns were REDCap's own bookkeeping ones (" +
               ", ".join(skipped) + "), which aren't compared unless you name them in --fields."
               if skipped else "")
        )

    result = diff_records(computed, current, fields, args.id_field)
    updates, conflicts, overwrites = result["updates"], result["conflicts"], result["overwrites"]
    orphans, missing_link = result["orphans"], result["missing_link"]
    n_fill = result["counts"][FILL]
    n_conflict = result["counts"][CONFLICT]
    n_noop = result["counts"][NOOP]
    n_orphan_cells = result["counts"][ORPHAN]

    out = Path(args.out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    def write(name, rows, header):
        path = out / name
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(rows)
        return path

    # The two file names carry the whole framing. For a write-back they name REDCap import
    # modes; for an analysis merge that language is wrong — nobody is pushing anything — and
    # telling a user to "push with overwriteBehavior=normal" when they asked for a merged table
    # is how a read-only task starts looking like a write to the person doing it.
    fills_name = "fills" if args.for_analysis else "update"
    disagree_name = "disagreements" if args.for_analysis else "overwrite"

    header = [args.id_field] + fields
    p_update = write(f"{args.prefix}_{fills_name}.csv", updates, header)
    p_conf = write(f"{args.prefix}_conflicts.csv", conflicts,
                   [args.id_field, "field", "existing", "computed"])
    p_over = write(f"{args.prefix}_{disagree_name}.csv", overwrites, header)
    p_orph = write(f"{args.prefix}_orphans.csv", orphans, header)
    p_miss = write(f"{args.prefix}_missing_link.csv", missing_link, [args.id_field])

    print(f"comparing  : {', '.join(fields)}")
    if skipped:
        print(f"not compared: {', '.join(skipped)} (REDCap's own columns — "
              f"name them in --fields to include them)")
    fills_label = "fills      " if args.for_analysis else "safe-fills "
    print(f"{fills_label}: {n_fill}  ({len(updates)} records)  -> {p_update.name}")
    print(f"conflicts  : {n_conflict}  ({len(overwrites)} records) -> {p_conf.name} / {p_over.name}")
    print(f"no-ops     : {n_noop}")
    print(f"orphans    : {len(orphans)} records ({n_orphan_cells} values) only in the computed file -> {p_orph.name}")
    print(f"no link    : {len(missing_link)} records only in the current file -> {p_miss.name}")

    if args.for_analysis:
        print(f"\nAnalysis merge — nothing here is pushed anywhere. {p_update.name} is where one "
              f"source has a value and the other doesn't; {p_over.name} is where they disagree "
              f"and a human has to pick.")
        if orphans:
            print(f"{p_orph.name} holds the records only the first file knows about, and "
                  f"{p_miss.name} the ones only the second does — say both counts out loud, "
                  f"they are what the merge could NOT do.")
        return

    print(f"\nDry-run complete. Review before pushing. Push {p_update.name} with overwriteBehavior=normal.")
    print(f"Only push {p_over.name} (overwrite) after explicit sign-off on {p_conf.name}.")
    if orphans:
        print(f"{p_orph.name} is a report, not a payload: those ids have no record in REDCap, so "
              f"importing them would create new records. That's a decision for the user.")


if __name__ == "__main__":
    main()
