#!/usr/bin/env python3
"""link_studies.py — work out how two studies join, then produce the HARD LINK.

This is the first thing to run when someone says "link these two studies". It
answers the question the whole job turns on — **which column do these two files
have in common that identifies the same person?** — and then produces the file
that formalises the answer inside REDCap.

Two steps, in this order.

STEP 1  --suggest
    Survey both files and print the candidate join keys, best first, with the
    numbers behind each one: how many rows they match, whether the column is
    unique on each side, and whether it is a hospital number, a name, or one
    study's record ID carried inside the other. Nothing is written. The point is
    to REASON OUT LOUD and then confirm the key with the user in ONE question
    before anything is built.

STEP 2  the run
    Join on the confirmed key and write four files:

      <child>_hard_link.csv   THE DELIVERABLE. Exactly two columns — the child
                              study's own record ID and the parent study's
                              number — one row per person the link was
                              established for. Upload it into the child project
                              on the REDCap website and the link is permanent.
      <child>_missing_link.csv  child records with no parent match, WITH the
                              patient's name and surname so they can be reviewed
                              by eye.
      <parent>_missing_link.csv  the same the other way round.
      <child>_name_review.csv   matched pairs whose names disagree between the
                              two studies, worst first. A near-miss is a
                              transcription slip; two unrelated names mean the
                              key matched the wrong people.

Which side is which: the PARENT is the study whose number gets carried (the CRC
cohort, the registry); the CHILD is the study that will hold the link (the R01,
the sub-study). The hard link is uploaded into the CHILD.

Stdlib only. Reads two files; writes four. Touches no network and no REDCap:
the link is established from downloaded files, and only the user's own upload
puts it into a project.

    python3 link_studies.py --parent crc.csv --child r01.csv --suggest

    python3 link_studies.py \\
        --parent crc.csv --parent-name crc \\
        --child  r01.csv --child-name  r01 \\
        --key hospital_no --link-field crc_redcap_number \\
        --out-dir database-manager/linkage/r01-crc/
"""
from __future__ import annotations

import argparse
import csv
import difflib
import re
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
# `norm` decides when two ID values are the same value — '007' and '7', 1 and '1.0'.
# diff_payload.py keys its comparison the same way, so a pair that links here is the
# same pair there. One definition of "the same id", used by both halves of the skill.
from argo_diff import norm  # noqa: E402


# REDCap's own bookkeeping columns. They are in every export and are never a join key.
STRUCTURAL_COLUMNS = (
    "redcap_data_access_group",
    "redcap_event_name",
    "redcap_repeat_instrument",
    "redcap_repeat_instance",
)

# What a column has to look like to be worth proposing as a key: near-unique on
# both sides. A column with a handful of repeated values (a grade, a site, a
# yes/no) can overlap enormously and join nobody to anybody.
UNIQUENESS_FLOOR = 0.95

FIRST_NAME_HINTS = ("first_name", "firstname", "given_name", "givenname",
                    "forename", "fname", "patient_name", "pt_name")
SURNAME_HINTS = ("surname", "last_name", "lastname", "family_name",
                 "familyname", "lname")
HOSPITAL_HINTS = ("hospital", "hosp_no", "hospno", "mrn", "medical_record",
                  "folder_no", "file_no", "clinic_no", "patient_no")


def is_structural(column: str) -> bool:
    return column in STRUCTURAL_COLUMNS or column.endswith("_complete")


def read_csv(path: Path):
    """(rows, column names), with a plain message when the file isn't there."""
    try:
        with open(path, newline="") as fh:
            reader = csv.DictReader(fh)
            columns = [c for c in (reader.fieldnames or [])]
            rows = [dict(r) for r in reader]
    except FileNotFoundError:
        raise SystemExit(
            f"I couldn't find this file:\n    {path}\n\n"
            "Check the name and the folder. If the name has spaces in it, put quotation marks\n"
            'around it, like "my export.csv".')
    if not columns:
        raise SystemExit(f"{path} has no column headings in it, so there is nothing to join on.")
    return rows, columns


def values(rows, column):
    """Every non-blank value in a column, normalised the way IDs compare."""
    out = []
    for row in rows:
        v = norm(row.get(column, ""))
        if v != "":
            out.append(v)
    return out


def find_column(columns, hints):
    """The first column whose name contains one of these hints."""
    for column in columns:
        low = column.strip().lower()
        for hint in hints:
            if hint in low:
                return column
    return None


def name_columns(columns, override=None):
    """(first-name column, surname column) — named explicitly, or found by name."""
    if override:
        parts = [p.strip() for p in override.split(",")]
        if len(parts) != 2:
            raise SystemExit("Give the name columns as two names separated by a comma, "
                             'like --child-names "first_name,surname".')
        for part in parts:
            if part not in columns:
                raise SystemExit(f"There is no column called {part!r}. "
                                 f"The columns are: {', '.join(columns[:15])}")
        return parts[0], parts[1]
    # The two hint lists are disjoint on purpose — no surname spelling contains a
    # first-name hint — so the order these are looked up in cannot matter.
    return find_column(columns, FIRST_NAME_HINTS), find_column(columns, SURNAME_HINTS)


# ---------------------------------------------------------------------------
# Step 1 — survey the candidate join keys
# ---------------------------------------------------------------------------

def survey(parent_rows, parent_cols, child_rows, child_cols):
    """Rank every column pair that could be the join key.

    Same-named columns and differently-named ones are surveyed together: a
    sub-study that carries the parent's record ID under a name of its own
    (`crc_redcap_number`) is exactly as good a key as one that copied the name.
    """
    parent_sets, child_sets = {}, {}
    for column in parent_cols:
        if not is_structural(column):
            parent_sets[column] = values(parent_rows, column)
    for column in child_cols:
        if not is_structural(column):
            child_sets[column] = values(child_rows, column)

    floor = max(2, int(0.02 * min(len(parent_rows), len(child_rows))))
    candidates = []
    for p_col, p_vals in parent_sets.items():
        p_set = set(p_vals)
        if not p_vals or len(p_set) < UNIQUENESS_FLOOR * len(p_vals):
            continue
        for c_col, c_vals in child_sets.items():
            c_set = set(c_vals)
            if not c_vals or len(c_set) < UNIQUENESS_FLOOR * len(c_vals):
                continue
            overlap = len(p_set & c_set)
            if overlap < floor:
                continue
            candidates.append({
                "parent_column": p_col,
                "child_column": c_col,
                "matched": overlap,
                "same_name": p_col == c_col,
                "parent_filled": len(p_vals),
                "child_filled": len(c_vals),
                "parent_unique": len(p_set) == len(p_vals),
                "child_unique": len(c_set) == len(c_vals),
            })
    # Most people matched wins; a shared column name breaks a tie, because a
    # shared name means the two studies already agree what the column is.
    candidates.sort(key=lambda c: (-c["matched"], not c["same_name"],
                                   c["parent_column"], c["child_column"]))
    return candidates


def print_survey(args, parent_rows, parent_cols, child_rows, child_cols):
    candidates = survey(parent_rows, parent_cols, child_rows, child_cols)
    p_name, c_name = args.parent_name, args.child_name
    print(f"{c_name}: {len(child_rows)} rows, {len(child_cols)} columns  ({args.child})")
    print(f"{p_name}: {len(parent_rows)} rows, {len(parent_cols)} columns  ({args.parent})")
    print()

    if not candidates:
        print("No column in these two files looks like a shared identifier.")
        print()
        print("Nothing was written. Two files can only be linked on something that identifies")
        print("the same person in both — a hospital number, or one study's record number")
        print("carried in the other. Check that both files are the ones you meant, and look")
        print("for a column that holds the OTHER study's number.")
        return 0

    print("Columns that could join these two files, best first:")
    print()
    for i, c in enumerate(candidates[:6], 1):
        if c["same_name"]:
            print(f"  {i}. {c['child_column']} — both files use this heading")
        else:
            print(f"  {i}. {c['child_column']} — {c_name}'s heading; the same values are in "
                  f"{p_name}'s {c['parent_column']}")
        print(f"     matches {c['matched']} of the {len(child_rows)} {c_name} rows "
              f"to {c['matched']} of the {len(parent_rows)} {p_name} rows")
        print(f"     {'one row per value' if c['parent_unique'] else 'REPEATS values'} in "
              f"{p_name}; "
              f"{'one row per value' if c['child_unique'] else 'REPEATS values'} in {c_name}")
        kind = []
        if find_column([c["child_column"]], HOSPITAL_HINTS):
            kind.append("looks like a hospital number")
        if c["child_column"] != c["parent_column"]:
            kind.append(f"looks like {p_name}'s own number carried inside {c_name}")
        if kind:
            print(f"     {'; '.join(kind)}")
        print()

    p_first, p_sur = name_columns(parent_cols, args.parent_names)
    c_first, c_sur = name_columns(child_cols, args.child_names)
    if (p_first or p_sur) and (c_first or c_sur):
        print(f"Names to check the join against: {p_name} has "
              f"{', '.join(filter(None, (p_first, p_sur)))}; {c_name} has "
              f"{', '.join(filter(None, (c_first, c_sur)))}.")
    elif (p_first or p_sur) or (c_first or c_sur):
        print("Only one of the two files carries names, so a matched pair can't be "
              "checked by name.")
    else:
        print("Neither file carries names, so a matched pair can't be checked by name — "
              "the key has to be right on its own.")
    print()

    best = candidates[0]
    key = best["child_column"] if best["same_name"] else \
        f"{p_name} `{best['parent_column']}` to {c_name} `{best['child_column']}`"
    unique = ("and has one row per value on both sides"
              if best["parent_unique"] and best["child_unique"]
              else "though it REPEATS some values, which has to be sorted out first")
    print(f"Best guess: join on {key} — it matches the most people "
          f"({best['matched']}) {unique}.")
    if len(candidates) > 1:
        second = candidates[1]
        print(f"The next best, {second['child_column']}, matches "
              f"{second['matched']}, which is {best['matched'] - second['matched']} fewer.")
    print()
    print("NOTHING HAS BEEN WRITTEN. Confirm the key before the run.")
    return 0


# ---------------------------------------------------------------------------
# Step 2 — the join, the name check, and the hard link
# ---------------------------------------------------------------------------

def norm_name(value) -> str:
    """Compare names the way a person reads them: case, punctuation and spacing don't count."""
    s = re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower())
    return re.sub(r"\s+", " ", s).strip()


def index_by_key(rows, key_column, side, path):
    """{normalised key: row}, refusing to guess when a key value repeats."""
    index, repeated = {}, {}
    for row in rows:
        k = norm(row.get(key_column, ""))
        if k == "":
            continue
        if k in index:
            repeated.setdefault(k, 1)
            repeated[k] += 1
        index[k] = row
    if repeated:
        listed = ", ".join(sorted(repeated)[:8])
        raise SystemExit(
            f"{path.name} has the same {key_column} on more than one row "
            f"({len(repeated)} value(s) repeat: {listed}).\n\n"
            f"A link has to point at ONE {side} record per person, so I've stopped rather than\n"
            "pick one of them. Either the export has repeating rows in it (one row per visit or\n"
            "per sample), in which case export one row per person, or two records are genuinely\n"
            "duplicates and need merging in REDCap first.")
    return index


def write_csv_rows(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def review_columns(columns, key_column, id_column, first, sur):
    """The columns that make an unmatched row reviewable by eye, in reading order."""
    wanted, seen = [], set()
    for column in (id_column, key_column, find_column(columns, HOSPITAL_HINTS), first, sur):
        if column and column in columns and column not in seen:
            wanted.append(column)
            seen.add(column)
    return wanted


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Work out how two studies join, then write the hard-link file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run with --suggest first, confirm the key with the user, then run for real.")
    ap.add_argument("--parent", required=True,
                    help="The study whose number gets carried (the cohort, the registry)")
    ap.add_argument("--child", required=True,
                    help="The study that will hold the link — the hard link is uploaded here")
    ap.add_argument("--parent-name", default="", help="What to call the parent study, e.g. crc")
    ap.add_argument("--child-name", default="", help="What to call the child study, e.g. r01")
    ap.add_argument("--suggest", action="store_true",
                    help="Survey the candidate join keys and stop. Writes nothing.")
    ap.add_argument("--key", help="The join column, when both files use the same heading")
    ap.add_argument("--parent-key", help="The join column in the parent file")
    ap.add_argument("--child-key", help="The join column in the child file")
    ap.add_argument("--child-id",
                    help="The child study's own record-ID column "
                         "(default: the first column of the child file)")
    ap.add_argument("--link-field",
                    help="The heading for the parent's number in the hard-link file — the name "
                         "of the field in the CHILD project that will hold it, e.g. "
                         "crc_redcap_number (default: the parent's key column name)")
    ap.add_argument("--parent-names", help='Name columns in the parent file, "first,surname"')
    ap.add_argument("--child-names", help='Name columns in the child file, "first,surname"')
    ap.add_argument("--out-dir", help="Where to write the four files (required for a real run)")
    args = ap.parse_args()

    parent_path, child_path = Path(args.parent).expanduser(), Path(args.child).expanduser()
    parent_rows, parent_cols = read_csv(parent_path)
    child_rows, child_cols = read_csv(child_path)
    args.parent_name = (args.parent_name or parent_path.stem).strip()
    args.child_name = (args.child_name or child_path.stem).strip()
    if args.parent_name == args.child_name:
        raise SystemExit("--parent-name and --child-name have to be different — they become "
                         "file names, and one would overwrite the other.")

    if args.suggest:
        return print_survey(args, parent_rows, parent_cols, child_rows, child_cols)

    parent_key = args.parent_key or args.key
    child_key = args.child_key or args.key
    if not parent_key or not child_key:
        raise SystemExit(
            "Say which column to join on: --key <column> when both files use the same\n"
            "heading, or --parent-key <column> --child-key <column> when they differ.\n\n"
            "Run with --suggest first to see the candidates and their numbers.")
    for column, columns, side, path in ((parent_key, parent_cols, "parent", parent_path),
                                        (child_key, child_cols, "child", child_path)):
        if column not in columns:
            raise SystemExit(
                f"{path.name} has no column called {column!r}.\n\n"
                f"Its columns are: {', '.join(columns[:15])}"
                f"{' …' if len(columns) > 15 else ''}")
    if not args.out_dir:
        raise SystemExit("Say where the files should go with --out-dir.")

    child_id = args.child_id or child_cols[0]
    if child_id not in child_cols:
        raise SystemExit(f"{child_path.name} has no column called {child_id!r} — name the "
                         "child study's record-ID column with --child-id.")
    link_field = args.link_field or parent_key
    if link_field == child_id:
        raise SystemExit(
            f"The hard-link file would have two columns both called {child_id!r}.\n\n"
            f"Its two columns are the child study's record ID and the field in the child\n"
            f"project that holds the parent's number. Name the second one with --link-field.")

    parent = index_by_key(parent_rows, parent_key, "parent", parent_path)
    child = index_by_key(child_rows, child_key, "child", child_path)
    matched = [k for k in child if k in parent]
    child_only = [k for k in child if k not in parent]
    parent_only = [k for k in parent if k not in child]

    if not matched:
        raise SystemExit(
            f"Nothing matched: no value of {child_key} in {child_path.name} appears as "
            f"{parent_key} in {parent_path.name}.\n\n"
            "Nothing was written — an empty hard-link file is worse than none. That almost\n"
            "always means the join column is the wrong one, or one file writes the numbers in\n"
            "a different format. Run the same command with --suggest instead of --out-dir to\n"
            "see which columns actually share values.")

    out = Path(args.out_dir).expanduser()
    p_first, p_sur = name_columns(parent_cols, args.parent_names)
    c_first, c_sur = name_columns(child_cols, args.child_names)

    # -- 1. THE HARD LINK ---------------------------------------------------
    # Two columns, nothing else: this file goes into REDCap, and every extra
    # column in an import is a chance to overwrite something.
    hard = [{child_id: child[k][child_id], link_field: parent[k][parent_key]} for k in matched]
    p_hard = write_csv_rows(out / f"{args.child_name}_hard_link.csv", [child_id, link_field], hard)

    # -- 2. the two missing-link reports, each with names to review by eye ---
    c_review = review_columns(child_cols, child_key, child_id, c_first, c_sur)
    p_review = review_columns(parent_cols, parent_key, parent_cols[0], p_first, p_sur)
    p_child_missing = write_csv_rows(out / f"{args.child_name}_missing_link.csv", c_review,
                                     [child[k] for k in child_only])
    p_parent_missing = write_csv_rows(out / f"{args.parent_name}_missing_link.csv", p_review,
                                      [parent[k] for k in parent_only])

    # -- 3. the name-discrepancy review table -------------------------------
    name_rows, name_note = [], ""
    can_check = (p_first or p_sur) and (c_first or c_sur)
    if can_check:
        for k in matched:
            crow, prow = child[k], parent[k]
            differs, worst = [], 1.0
            for label, c_col, p_col in (("first name", c_first, p_first),
                                        ("surname", c_sur, p_sur)):
                if not c_col or not p_col:
                    continue
                a, b = norm_name(crow.get(c_col)), norm_name(prow.get(p_col))
                if a and b and a != b:
                    differs.append(label)
                    worst = min(worst, difflib.SequenceMatcher(None, a, b).ratio())
            if differs:
                name_rows.append({
                    child_id: crow[child_id],
                    "join_key": k,
                    f"first_name_{args.child_name}": crow.get(c_first, "") if c_first else "",
                    f"first_name_{args.parent_name}": prow.get(p_first, "") if p_first else "",
                    f"surname_{args.child_name}": crow.get(c_sur, "") if c_sur else "",
                    f"surname_{args.parent_name}": prow.get(p_sur, "") if p_sur else "",
                    "what_differs": " and ".join(differs),
                    "how_alike": f"{worst:.2f}",
                })
        # Worst first: two unrelated names are a wrong match, a near-miss is a typo.
        name_rows.sort(key=lambda r: (float(r["how_alike"]), r[child_id]))
    name_header = [child_id, "join_key",
                   f"first_name_{args.child_name}", f"first_name_{args.parent_name}",
                   f"surname_{args.child_name}", f"surname_{args.parent_name}",
                   "what_differs", "how_alike"]
    p_names = write_csv_rows(out / f"{args.child_name}_name_review.csv", name_header, name_rows)
    if not can_check:
        name_note = ("only one of the two files carries names, so nothing could be "
                     "cross-checked")

    # -- what happened, in plain words --------------------------------------
    join = (f"{child_key}" if child_key == parent_key
            else f"{args.child_name} {child_key} to {args.parent_name} {parent_key}")
    print(f"Joined {args.child_name} to {args.parent_name} on {join}.")
    print()
    print(f"  matched                 {len(matched):>5}  found in both studies")
    print(f"  only in {args.child_name:<16}{len(child_only):>5}  no {args.parent_name} record "
          f"-> {p_child_missing.name}")
    print(f"  only in {args.parent_name:<16}{len(parent_only):>5}  no {args.child_name} record "
          f"-> {p_parent_missing.name}")
    print()
    if name_note:
        print(f"Names   : not checked — {name_note}.")
    elif name_rows:
        by_field = {}
        for row in name_rows:
            by_field[row["what_differs"]] = by_field.get(row["what_differs"], 0) + 1
        detail = ", ".join(f"{n} {label}" for label, n in sorted(by_field.items()))
        print(f"Names   : {len(name_rows)} of the {len(matched)} matched pairs disagree "
              f"({detail}) -> {p_names.name}")
        print(f"          Worst first. A near-miss is a spelling slip; two unrelated names "
              f"mean the key matched the wrong people.")
    else:
        print(f"Names   : all {len(matched)} matched pairs agree on the name -> "
              f"{p_names.name} (empty)")
    print()
    print(f"HARD LINK: {p_hard.name} — {len(hard)} rows, two columns "
          f"({child_id}, {link_field}).")
    print(f"Upload it into the {args.child_name} project on the REDCap website "
          f"(Data Import Tool) to record each participant's {args.parent_name} number "
          f"permanently. Nothing has been written to REDCap by this script.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
