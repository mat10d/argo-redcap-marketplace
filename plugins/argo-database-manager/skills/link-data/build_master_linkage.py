#!/usr/bin/env python3
"""build_master_linkage.py — turn a finished diff into the merged table and the integrity report.

`diff_payload.py` answers "how do these two sources compare, cell by cell". This answers the
question the user actually asked: **give me one table with both studies in it, and tell me where
it can't be trusted.** It writes the two files link-data has always promised:

    master_linkage.csv    one row per entity across BOTH sources, carrying the id, a `_linked`
                          flag for each side, every field from both, and a `link_class` saying
                          how the two sources relate for that row.
    *_integrity.csv       the structural problems, ranked worst first, each with a count and a
                          sentence saying what it means for the analysis.

It reads the diff engine's own output rather than comparing the two files again. The
fill/conflict/no-record rule is a safety rule that lives in one place (`argo_diff.py`, via
`diff_payload.py`); a second implementation here would be a second thing to keep identical, and
the moment they disagreed neither would be trustworthy.

**Nothing here decides a clinical value.** Where the two sources disagree, BOTH values are
carried side by side — the right-hand source's column gets a suffix — and the row is flagged.
A human picks the winner.

Run diff_payload.py first, then:

    python3 build_master_linkage.py \\
        --left cohort_records.csv   --left-name cohort \\
        --right pathology.csv       --right-name pathology \\
        --diff-dir data-analyst/syn-crc/ --diff-prefix pathology \\
        --id-field syn_id \\
        --out data-analyst/syn-crc/master_linkage.csv

`--left` is the file you passed diff_payload.py as `--current`; `--right` is the one you passed
as `--computed`. Getting them the wrong way round is the one mistake that matters here, so the
script checks the ids line up with the diff's own reports and stops if they don't.

Stdlib only. Reads; writes two CSVs; touches no network and no REDCap.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Worst first. A problem with nothing in it is not a problem, so an empty count is reported at
# "info" whatever its usual severity — the ranking has to reflect this run, not the general case.
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def read_rows(path: Path, id_field: str) -> "tuple[list, list]":
    """(rows, column names) from a CSV, with a plain message when the id column isn't there."""
    try:
        with open(path, newline="") as fh:
            reader = csv.DictReader(fh)
            columns = list(reader.fieldnames or [])
            rows = [dict(r) for r in reader]
    except FileNotFoundError:
        raise SystemExit(
            f"I couldn't find this file:\n    {path}\n\n"
            "Check the name and the folder. If the name has spaces in it, put quotation marks\n"
            'around it, like "my export.csv".')
    if id_field not in columns:
        raise SystemExit(
            f"{path.name} has no column called {id_field!r}, so I can't tell which row is which\n"
            f"person or sample.\n\n"
            f"Its columns are: {', '.join(columns[:12])}{' …' if len(columns) > 12 else ''}\n\n"
            "Name the right one with --id-field.")
    return rows, columns


def diff_file(diff_dir: Path, prefix: str, *names: str) -> Path:
    """One of the diff engine's outputs, under either of the names it writes.

    diff_payload.py names its two payload files for what they mean: `_update`/`_overwrite` when
    the plan is to write back to REDCap, `_fills`/`_disagreements` when the two sources are
    being merged for analysis (`--for-analysis`). Both are the same data; accept either, so the
    merge doesn't care which framing the person upstream chose.
    """
    for name in names:
        path = diff_dir / f"{prefix}_{name}.csv"
        if path.exists():
            return path
    wanted = " or ".join(f"{prefix}_{n}.csv" for n in names)
    raise SystemExit(
        f"I couldn't find {wanted} in:\n    {diff_dir}\n\n"
        "That file comes from diff_payload.py — run it on the same two sources first, with the\n"
        f"same --out-dir and --prefix {prefix}.")


def read_ids(path: Path, id_field: str) -> set:
    with open(path, newline="") as fh:
        return {row[id_field] for row in csv.DictReader(fh) if row.get(id_field)}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build the merged master table and the integrity report from a finished diff.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run diff_payload.py first — this reads its output rather than re-comparing.")
    ap.add_argument("--left", required=True,
                    help="The first source CSV — the one diff_payload.py was given as --current")
    ap.add_argument("--right", required=True,
                    help="The second source CSV — the one diff_payload.py was given as --computed")
    ap.add_argument("--left-name", default="left",
                    help="What to call the first source in column names, e.g. cohort")
    ap.add_argument("--right-name", default="right",
                    help="What to call the second source, e.g. pathology")
    ap.add_argument("--diff-dir", required=True,
                    help="The folder diff_payload.py wrote its files into (--out-dir)")
    ap.add_argument("--diff-prefix", default="linkage",
                    help="The prefix diff_payload.py used (--prefix). Default: linkage")
    ap.add_argument("--id-field", required=True, help="The column both sources are keyed on")
    ap.add_argument("--out", required=True, help="Where to write master_linkage.csv")
    ap.add_argument("--integrity-out",
                    help="Where to write the integrity report "
                         "(default: <prefix>_integrity.csv next to --out)")
    args = ap.parse_args()

    left_name, right_name = args.left_name.strip(), args.right_name.strip()
    if left_name == right_name:
        raise SystemExit("--left-name and --right-name have to be different — they become "
                         "column names, and two columns can't share one.")

    idf = args.id_field
    diff_dir = Path(args.diff_dir).expanduser()
    left_rows, left_cols = read_rows(Path(args.left).expanduser(), idf)
    right_rows, right_cols = read_rows(Path(args.right).expanduser(), idf)
    left = {r[idf]: r for r in left_rows}
    right = {r[idf]: r for r in right_rows}

    # Verdicts straight from the diff engine's output — no second implementation of the rule.
    p_fills = diff_file(diff_dir, args.diff_prefix, "fills", "update")
    p_disagree = diff_file(diff_dir, args.diff_prefix, "disagreements", "overwrite")
    p_conflicts = diff_file(diff_dir, args.diff_prefix, "conflicts")
    # `_orphans` was this file's name before 0.19; accept it so an older run still merges.
    p_right_only = diff_file(diff_dir, args.diff_prefix, "no_record_to_fill", "orphans")
    p_nolink = diff_file(diff_dir, args.diff_prefix, "missing_link")

    fill_ids = read_ids(p_fills, idf)
    conflict_ids = read_ids(p_disagree, idf)
    right_only_ids = read_ids(p_right_only, idf)   # ids only the RIGHT source has
    nolink_ids = read_ids(p_nolink, idf)       # ids only the LEFT source has

    conflicts_by_id: dict = {}
    with open(p_conflicts, newline="") as fh:
        for row in csv.DictReader(fh):
            conflicts_by_id.setdefault(row[idf], []).append(row["field"])

    # The fields the diff actually compared: the fills file's header, minus the id.
    with open(p_fills, newline="") as fh:
        compared = [c for c in (next(csv.reader(fh), []) or []) if c != idf]

    # Sanity: the diff's no-record rows are ids only the right file has, its missing-link ids
    # only the left. If that isn't true, --left and --right are the wrong way round and every
    # flag below would be inverted — a merged table that is quietly, completely wrong.
    if right_only_ids and not right_only_ids <= (set(right) - set(left)):
        raise SystemExit(
            f"The ids in {p_right_only.name} aren't the ones only {args.right} has, which means\n"
            "--left and --right are probably swapped.\n\n"
            "--left is the file diff_payload.py was given as --current; --right is the one it\n"
            "was given as --computed. Swap them and run this again.")

    collisions = {c for c in right_cols if c in set(left_cols) and c != idf}
    right_out = {c: (f"{c}_{right_name}" if c in collisions else c)
                 for c in right_cols if c != idf}
    header = ([idf, f"{left_name}_linked", f"{right_name}_linked", "link_class",
               "conflict_fields"]
              + [c for c in left_cols if c != idf]
              + [right_out[c] for c in right_cols if c != idf])

    def classify(rid: str) -> str:
        if rid in right_only_ids:
            return f"{right_name}_only"    # no record on the left at all — never a fill
        if rid in nolink_ids:
            return f"{left_name}_only"
        if rid in conflict_ids:
            return "matched_conflict"
        if rid in fill_ids:
            return "matched_fill"
        return "matched_agree"

    rows = []
    for rid in sorted(set(left) | set(right)):
        lrow, rrow = left.get(rid, {}), right.get(rid, {})
        row = {idf: rid,
               f"{left_name}_linked": int(rid in left),
               f"{right_name}_linked": int(rid in right),
               "link_class": classify(rid),
               "conflict_fields": "; ".join(conflicts_by_id.get(rid, []))}
        for c in left_cols:
            if c != idf:
                row[c] = lrow.get(c, "")
        for c in right_cols:
            if c != idf:
                row[right_out[c]] = rrow.get(c, "")
        rows.append(row)

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    # ---- integrity report: structural issues, worst first ------------------------------
    def n(cls: str) -> int:
        return sum(1 for r in rows if r["link_class"] == cls)

    dup_left = len(left_rows) - len(left)
    dup_right = len(right_rows) - len(right)
    dag = "redcap_data_access_group"
    site_disagree = [rid for rid in set(left) & set(right)
                     if str(left[rid].get(dag, "")).strip()
                     != str(right[rid].get(dag, "")).strip()]
    right_only_sites = sorted({str(right[rid].get(dag, "")).strip()
                               for rid in right_only_ids if rid in right} - {""})
    n_conflict_values = sum(len(v) for v in conflicts_by_id.values())
    matched = len(set(left) & set(right))
    compared_text = ", ".join(compared) if compared else "the compared fields"
    right_only_from = (f"They come from: {', '.join(right_only_sites)}. "
                       if right_only_sites else "")

    issues = [
        ("high", f"{right_name} records with no matching {left_name} record", right_name,
         n(f"{right_name}_only"),
         right_only_from
         + "Nothing can be filled for them — decide whether they belong in this analysis at "
           f"all. See {p_right_only.name}."),
        ("high", "Records where the two sources disagree on a value", "both",
         n("matched_conflict"),
         f"{n_conflict_values} disagreeing values across {compared_text}. Both values are "
         f"carried in {out.name}; see {p_conflicts.name}."),
        ("medium", f"{left_name} records with no matching {right_name} record", left_name,
         n(f"{left_name}_only"),
         f"Expected when the second source covers a subset, but it caps the overlap at "
         f"{matched} records. See {p_nolink.name}."),
        ("low", f"Records where {right_name} fills a blank in {left_name}", "both",
         n("matched_fill"),
         f"The {left_name} value is blank and the {right_name} one is present. "
         f"See {p_fills.name}."),
        ("high", "Duplicate join IDs", "both", dup_left + dup_right,
         (f"{idf} is not unique: {dup_left} duplicate(s) in {left_name}, {dup_right} in "
          f"{right_name}. Rows were collapsed by id, so data has been lost — fix the sources."
          if dup_left or dup_right else
          f"None: {idf} is unique in both files ({len(left)} and {len(right)} distinct values).")),
        ("medium", "Matched records whose site disagrees between the sources", "both",
         len(site_disagree),
         (f"Ids: {', '.join(sorted(site_disagree)[:10])}. Site was not linked on, so this is a "
          "flag, not a merge failure."
          if site_disagree else
          "None. Site was checked but deliberately not linked on.")),
        ("info", "Fuzzy matching", "both", 0,
         "Not run: this merge joined on an exact id. Unmatched ids are reported above, never "
         "guessed."),
    ]

    def severity(base: str, count: int) -> str:
        return base if count else "info"

    ranked = sorted(issues, key=lambda i: (SEVERITY_ORDER[severity(i[0], i[3])], -i[3]))
    integrity = (Path(args.integrity_out).expanduser() if args.integrity_out
                 else out.parent / f"{args.diff_prefix}_integrity.csv")
    integrity.parent.mkdir(parents=True, exist_ok=True)
    with open(integrity, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["rank", "severity", "issue", "source", "n_records", "detail"])
        for i, (base, issue, source, count, detail) in enumerate(ranked, 1):
            writer.writerow([i, severity(base, count), issue, source, count, detail])

    print(f"{out.name}: {len(rows)} rows "
          f"({n('matched_agree')} agree, {n('matched_fill')} fill, "
          f"{n('matched_conflict')} disagree, {n(f'{right_name}_only')} {right_name}-only, "
          f"{n(f'{left_name}_only')} {left_name}-only)")
    print(f"{integrity.name}: {len(ranked)} issues, worst first")
    if collisions:
        print(f"Columns in both sources kept both values; the {right_name} one is suffixed "
              f"_{right_name}: {', '.join(sorted(collisions))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
