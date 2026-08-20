#!/usr/bin/env python3
"""table1.py — Table 1: demographics by site, for the SYN synthetic cohort.

Study   : SYN — Synthetic Colorectal Cohort (SYNTHETIC TEST STUDY)
Inputs  : ../records.csv           the REDCap record export (raw codes)
          ../datadictionary.csv    the codebook — labels, types, choice maps
Outputs : <--out>/table1.csv       one tidy Table 1
Author  : ARGO toolkit fixtures    Date: 2026-08-20
Assumes : one row per participant; `redcap_data_access_group` is the site;
          MDC codes (-666/-777/-888/-999, and 666) are missing, not values.

WHAT THIS FILE IS FOR
---------------------
Two jobs, both deliberate:

1. **A parity reference.** `table1.R` and `table1.do` sit beside this file and
   must produce the SAME numbers from the same inputs. `expected_table1.csv`
   (this script's output, committed) is the golden copy, and
   `tests/test_analysis_parity.py` checks Python against it always and R
   against it whenever `Rscript` is installed.

2. **A worked example of what a run-analysis output should look like** — the
   header block above, sections that say why and not just what, inputs read
   from disk and never modified, one command from start to finish, and a
   result that a non-coder can read. If you are writing an analysis script for
   a real ARGO study, this is the shape.

Stdlib only, on purpose: the analyst role must be able to run it on a laptop
with nothing installed. pandas would be perfectly fine for real work.

TABLE SHAPE
-----------
Tidy long-ish format, one row per (variable, level, statistic), one column per
site plus an `overall` column:

    variable,level,statistic,site_alpha,site_beta,overall

`statistic` is one of:
    n        a count (of records, or of that level, or non-missing)
    missing  how many records had no usable value
    pct      percent of the NON-MISSING records in that column
    mean/sd  for the continuous variable

Keeping every cell numeric (rather than pre-formatted "12 (34.5%)" strings) is
what lets three languages be compared for equality, and lets a user paste the
table into anything without unpicking it.

Run:
    python3 table1.py --out ./out
"""

from __future__ import annotations

import argparse
import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# --- study-specific choices, stated once ------------------------------------

SITE_FIELD = "redcap_data_access_group"
CONTINUOUS = "age"                       # the age-like variable
CATEGORICALS = ["sex", "education", "marital_status", "tobacco_use",
                # Not a demographic. Included on purpose: histology_grade is the
                # one field in the fixture carrying BOTH engineered blanks and
                # MDC sentinel codes, so it is what actually exercises the
                # missing-data path — in all three languages, identically.
                "histology_grade"]

# Missing-data codes. REDCap stores these as ordinary values, so they must be
# removed explicitly or they silently poison every mean. See mdc-rules.
MDC = {"-666", "-777", "-888", "-999", "666"}

DECIMALS = 2      # every non-count statistic is rounded here, in all 3 languages


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def choice_map(dd):
    """{field: {code: label}} from the data dictionary.

    REDCap encodes choices as "1, Male | 2, Female". yes/no fields carry no
    choice string at all, so they get the implicit 0=No / 1=Yes map — a
    detail that is easy to miss and produces an empty table when missed.
    """
    out = {}
    for row in dd:
        ftype = row["field_type"]
        if ftype == "yesno":
            out[row["field_name"]] = {"0": "No", "1": "Yes"}
            continue
        raw = row["select_choices_or_calculations"]
        if ftype not in ("radio", "dropdown", "checkbox") or not raw.strip():
            continue
        mapping = {}
        for chunk in raw.split("|"):
            if "," not in chunk:
                continue
            code, label = chunk.split(",", 1)
            mapping[code.strip()] = label.strip()
        out[row["field_name"]] = mapping
    return out


def labels_of(dd):
    return {row["field_name"]: row["field_label"] for row in dd}


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def usable(value):
    """A value we may compute on: present, and not a missing-data code."""
    v = (value or "").strip()
    return v if v != "" and v not in MDC else None


def mean_sd(values):
    """Mean and SAMPLE standard deviation (n-1 denominator).

    n-1 is stated explicitly because it is the single most common source of a
    third-decimal disagreement between Python, R and Stata: R's sd() and
    Stata's summarize both use n-1, and numpy's std() defaults to n.
    """
    n = len(values)
    if n == 0:
        return None, None
    m = sum(values) / n
    if n < 2:
        return m, None
    var = sum((x - m) ** 2 for x in values) / (n - 1)
    return m, math.sqrt(var)


def fmt(value, is_count):
    if value is None:
        return ""
    if is_count:
        return str(int(value))
    return f"{value:.{DECIMALS}f}"


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

def build(records, dd):
    choices = choice_map(dd)
    labels = labels_of(dd)

    sites = sorted({r[SITE_FIELD] for r in records if r[SITE_FIELD].strip()})
    columns = sites + ["overall"]
    # Each column is a subset of the records; "overall" is all of them.
    subsets = {s: [r for r in records if r[SITE_FIELD] == s] for s in sites}
    subsets["overall"] = records

    rows = []

    def add(variable, level, statistic, per_column, is_count):
        rows.append({
            "variable": variable, "level": level, "statistic": statistic,
            **{c: fmt(per_column[c], is_count) for c in columns},
        })

    # --- 1. how many records are in each column ----------------------------
    add("records", "", "n", {c: len(subsets[c]) for c in columns}, True)

    # --- 2. the continuous variable ----------------------------------------
    # Non-missing count, missing count, then mean and SD over the non-missing.
    vals = {c: [float(v) for v in (usable(r[CONTINUOUS]) for r in subsets[c]) if v is not None]
            for c in columns}
    add(CONTINUOUS, "", "n", {c: len(vals[c]) for c in columns}, True)
    add(CONTINUOUS, "", "missing",
        {c: len(subsets[c]) - len(vals[c]) for c in columns}, True)
    stats = {c: mean_sd(vals[c]) for c in columns}
    add(CONTINUOUS, "", "mean", {c: stats[c][0] for c in columns}, False)
    add(CONTINUOUS, "", "sd", {c: stats[c][1] for c in columns}, False)

    # --- 3. the categorical variables --------------------------------------
    for field in CATEGORICALS:
        mapping = choices.get(field, {})
        # Level order comes from the DATA DICTIONARY, not from the data, so a
        # level nobody happens to have still appears (as a zero) and the row
        # order is identical in all three languages.
        # MDC codes are offered as choices on some fields so an RA can record
        # "missing, and here is why". They are NOT categories of the variable
        # and must never become rows of a Table 1 — they are counted under
        # `missing` instead.
        codes = [c for c in mapping if c not in MDC]
        present = {c: [usable(r[field]) for r in subsets[c]] for c in columns}
        nonmissing = {c: [v for v in present[c] if v is not None] for c in columns}
        for code in codes:
            counts = {c: sum(1 for v in nonmissing[c] if v == code) for c in columns}
            label = mapping[code]
            add(field, label, "n", counts, True)
            # Percent denominator is the non-missing count in that column —
            # stated here because "percent of what" is the question every
            # reader of a Table 1 asks first.
            add(field, label, "pct",
                {c: (100.0 * counts[c] / len(nonmissing[c]) if nonmissing[c] else None)
                 for c in columns}, False)
        add(field, "", "missing",
            {c: len(present[c]) - len(nonmissing[c]) for c in columns}, True)

    header = ["variable", "level", "statistic"] + columns
    return header, rows, labels


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--records", default=os.path.join(HERE, os.pardir, "records.csv"))
    ap.add_argument("--dictionary",
                    default=os.path.join(HERE, os.pardir, "datadictionary.csv"))
    ap.add_argument("--out", required=True, help="directory for table1.csv")
    args = ap.parse_args()

    records = read_csv(args.records)
    dd = read_csv(args.dictionary)
    header, rows, labels = build(records, dd)

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "table1.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    print(f"Table 1 written to {path}  ({len(rows)} rows, {len(header) - 3} columns of results)")
    for field, label in labels.items():
        if field in [CONTINUOUS] + CATEGORICALS:
            print(f"  {field:<16} {label}")


if __name__ == "__main__":
    main()
