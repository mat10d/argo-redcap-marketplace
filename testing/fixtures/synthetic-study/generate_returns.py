#!/usr/bin/env python3
"""Seeded generator for RA-RETURNED worklists on the SYN synthetic study.

SYNTHETIC TEST STUDY — every value written here is fabricated. No real people,
sites, or data. This is the input fixture for the QA specialist's **task 2**
(audit what the RAs send back), which otherwise had no test coverage at all.

What it does, deterministically, from the committed fixture:

  1. Runs `build_worklists.py` on records.csv + datadictionary.csv + qa_fields.yaml
     into `<out>/build/` (with `--round=` so the path has no date in it).
  2. Takes the four `with_MDC/` workbooks (2 workbooks x 2 DAGs) and writes an
     RA-RETURNED copy of each into `<out>/returned/`, with ENGINEERED edits:

       filled_value   yellow cells filled with a plausible in-choice-list value
       filled_mdc     yellow cells filled with an MDC sentinel code (-666/-777/-888/-999)
       untouched      yellow cells left exactly as sent
       notes_on_changed  rows that got a fill AND an RA note in the RESPONSE column
       notes_only        rows with an RA note but NO cell change  (the "VERIFY" case)
       out_of_scope   cells the RA edited that were NEVER flagged (gate-context columns)
       amber_filled   amber "we couldn't read this condition" cells the RA filled

  3. Writes `<out>/returned/returned_counts.json` with the exact counts, and with
     `--update-manifest` merges the same numbers into MANIFEST.json's `returned`
     block (leaving every other key untouched).

No .xlsx is ever committed: `tests/test_qa_audit_round_trip.py` runs this into a
temp directory and asserts what `review_responses.py` reports against MANIFEST.

NOTE: `generate.py` rewrites MANIFEST.json from scratch and does not know about
the `returned` block. If you rerun `generate.py`, rerun this with
`--update-manifest` afterwards. The round-trip test fails loudly if the block is
missing or stale — it is never silently wrong.

Run:
    python3 generate_returns.py --out /tmp/syn-returns [--update-manifest]

Requires pandas / openpyxl / pyyaml (same dependencies build_worklists.py needs).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BUILDER = os.path.join(REPO, "plugins", "argo-qa-specialist", "skills",
                       "qa-worklists", "build_worklists.py")

SEED = 20260820

YELLOW_HEX = "FFC7CE"   # build_worklists.YELLOW  — "this applies and is blank"
AMBER_HEX = "FFE9B8"    # build_worklists.UNCERTAIN — "we couldn't read the condition"
SENTINELS = ["-888", "-777", "-999", "-666"]
RESPONSE_HEADER_TOKENS = ("response", "comment", "note")

# The with_MDC workbooks this fixture engineers, and the exact edit budget for each.
# Sized so every count fits inside the smallest workbook (8 yellow cells, 8 rows).
PLAN = {
    "clinical_core_site_alpha": {
        "filled_value": 8, "filled_mdc": 5, "notes_on_changed": 4,
        "notes_only": 3, "out_of_scope": 3, "amber_filled": 3,
    },
    "clinical_core_site_beta": {
        "filled_value": 5, "filled_mdc": 3, "notes_on_changed": 3,
        "notes_only": 2, "out_of_scope": 2, "amber_filled": 2,
    },
    "demo_followup_site_alpha": {
        "filled_value": 4, "filled_mdc": 2, "notes_on_changed": 2,
        "notes_only": 2, "out_of_scope": 2, "amber_filled": 0,
    },
    "demo_followup_site_beta": {
        "filled_value": 2, "filled_mdc": 2, "notes_on_changed": 2,
        "notes_only": 1, "out_of_scope": 2, "amber_filled": 0,
    },
}

# Synthetic RA wording. Deliberately mixed: clean "RESOLVED" markers, an
# explanation that warrants no recode, and one vague note.
NOTES_ON_CHANGED = [
    "Checked the synthetic chart and entered these in REDCap.",
    "Values found in the fake source folder; REDCap updated.",
    "Entered in REDCap — please re-pull to confirm.",
    "Filled from the test source sheet, nothing outstanding now.",
]
NOTES_ONLY = [
    "RESOLVED",
    "Synthetic participant transferred; no chart held at this site.",
    "RESOLVED in REDCap already, spreadsheet not updated.",
]


# ---------------------------------------------------------------------------
# Data dictionary helpers (stdlib — mirrors build_worklists' label conventions)
# ---------------------------------------------------------------------------

def clean_label(label: str) -> str:
    """Same normalisation build_worklists.clean_label applies to header labels."""
    if not label:
        return label
    return re.sub(r"\s+", " ", label).strip().rstrip(" ?.:;")


def parse_choices(raw: str) -> dict:
    out = {}
    for part in (raw or "").split("|"):
        if "," in part:
            code, label = part.split(",", 1)
            out[code.strip()] = label.strip()
    return out


def load_dd(path: str) -> dict:
    """cleaned field_label -> {'field': name, 'choices': {code: label}}"""
    by_label = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            label = clean_label(row.get("field_label", ""))
            if not label:
                continue
            by_label.setdefault(label, {
                "field": row["field_name"],
                "choices": parse_choices(row.get("select_choices_or_calculations", "")),
            })
    return by_label


def plausible_value(header: str, current, dd_by_label: dict, rng) -> str:
    """A value an RA could plausibly have typed: a real choice label for the
    field, never an MDC label, and never equal to what is already in the cell."""
    spec = dd_by_label.get(str(header).strip(), {})
    choices = spec.get("choices") or {}
    options = [lbl for code, lbl in choices.items() if code not in SENTINELS]
    cur = "" if current is None else str(current).strip()
    options = [o for o in options if o != cur]
    if options:
        return options[rng.randrange(len(options))]
    return "filled"      # text/date fields: the SKILL's documented "filled" marker


# ---------------------------------------------------------------------------
# Workbook edits
# ---------------------------------------------------------------------------

def _fill_hex(cell) -> str:
    f = cell.fill
    if not f or not f.fgColor:
        return ""
    return str(f.fgColor.rgb or "").upper()


def _response_col(headers) -> int | None:
    for i, h in enumerate(headers, 1):
        if h and any(t in str(h).lower() for t in RESPONSE_HEADER_TOKENS):
            return i
    return None


def engineer_return(src_path: str, dst_path: str, plan: dict, dd_by_label: dict,
                    seed: int) -> dict:
    """Write an RA-returned copy of `src_path` and return its exact edit counts."""
    from openpyxl import load_workbook

    rng = random.Random(seed)
    wb = load_workbook(src_path)
    ws = wb.active
    headers = [c.value for c in ws[1]]
    resp_col = _response_col(headers)
    if resp_col is None:
        raise SystemExit(f"{src_path}: no RESPONSE column — build_worklists should add one")

    # Cells are keyed by (row, HEADER) rather than (row, column index) on purpose:
    # build_worklists.py inserts its gate-context columns from a set, so their left-to-right
    # order changes between runs (see tests/test_qa_audit_round_trip.py). Sorting by header
    # keeps this generator's picks identical regardless.
    yellow, amber, plain = [], [], []
    for r in range(3, ws.max_row + 1):
        rid = str(ws.cell(row=r, column=1).value or "").strip()
        if not rid:
            continue
        for c in range(2, ws.max_column + 1):
            if c == resp_col:
                continue
            cell = ws.cell(row=r, column=c)
            hexv = _fill_hex(cell)
            entry = (r, str(headers[c - 1]), c, rid)
            if hexv.endswith(YELLOW_HEX):
                yellow.append(entry)
            elif hexv.endswith(AMBER_HEX):
                amber.append(entry)
            elif cell.value not in (None, ""):
                plain.append(entry)

    n_fill = plan["filled_value"] + plan["filled_mdc"]
    if n_fill > len(yellow):
        raise SystemExit(f"{src_path}: plan wants {n_fill} fills, only {len(yellow)} yellow cells")

    order = sorted(yellow)
    rng.shuffle(order)
    to_value = sorted(order[:plan["filled_value"]])
    to_mdc = sorted(order[plan["filled_value"]:n_fill])

    for r, header, c, _rid in to_value:
        cell = ws.cell(row=r, column=c)
        cell.value = plausible_value(header, cell.value, dd_by_label, rng)
    mdc_on_mdc_field = 0
    for i, (r, header, c, _rid) in enumerate(to_mdc):
        code = SENTINELS[i % len(SENTINELS)]
        spec = dd_by_label.get(header.strip(), {})
        if code in (spec.get("choices") or {}):
            mdc_on_mdc_field += 1
        ws.cell(row=r, column=c).value = code

    changed_rows = sorted({e[0] for e in to_value + to_mdc})
    changed_ids = sorted({e[3] for e in to_value + to_mdc})

    # Notes on rows that DID change something.
    note_rows = changed_rows[:plan["notes_on_changed"]]
    if len(note_rows) < plan["notes_on_changed"]:
        raise SystemExit(f"{src_path}: only {len(note_rows)} changed rows, "
                         f"plan wants {plan['notes_on_changed']} notes on changed rows")
    for i, r in enumerate(note_rows):
        ws.cell(row=r, column=resp_col).value = NOTES_ON_CHANGED[i % len(NOTES_ON_CHANGED)]

    # Notes on rows with NO cell change at all — the "RA said RESOLVED but the
    # cell is still blank" case the audit is supposed to surface as VERIFY.
    untouched_rows = [r for r in range(3, ws.max_row + 1)
                      if r not in set(changed_rows)
                      and str(ws.cell(row=r, column=1).value or "").strip()]
    note_only_rows = untouched_rows[:plan["notes_only"]]
    if len(note_only_rows) < plan["notes_only"]:
        raise SystemExit(f"{src_path}: only {len(untouched_rows)} unchanged rows, "
                         f"plan wants {plan['notes_only']} note-only rows")
    for i, r in enumerate(note_only_rows):
        ws.cell(row=r, column=resp_col).value = NOTES_ONLY[i % len(NOTES_ONLY)]
    note_only_ids = sorted(str(ws.cell(row=r, column=1).value).strip() for r in note_only_rows)

    # Out-of-scope edits: cells that were never flagged, on rows that are
    # otherwise silent. A correct audit should notice these; today's does not.
    used_rows = set(changed_rows) | set(note_only_rows)
    candidates = sorted(p for p in plain if p[0] not in used_rows)
    if len(candidates) < plan["out_of_scope"]:
        raise SystemExit(f"{src_path}: {len(candidates)} out-of-scope candidates, "
                         f"plan wants {plan['out_of_scope']}")
    rng.shuffle(candidates)
    oos = sorted(candidates[:plan["out_of_scope"]])
    oos_detail = []
    for r, header, c, rid in oos:
        cell = ws.cell(row=r, column=c)
        before = "" if cell.value is None else str(cell.value)
        cell.value = plausible_value(header, cell.value, dd_by_label, rng)
        oos_detail.append({"record": rid, "column": header,
                           "was": before, "now": str(cell.value)})

    # Amber ("please check whether this applies") cells the RA filled in.
    amber_pick = sorted(amber)
    rng.shuffle(amber_pick)
    amber_pick = sorted(amber_pick[:plan["amber_filled"]])
    if len(amber_pick) < plan["amber_filled"]:
        raise SystemExit(f"{src_path}: {len(amber)} amber cells, "
                         f"plan wants {plan['amber_filled']} filled")
    amber_ids = []
    for r, header, c, rid in amber_pick:
        cell = ws.cell(row=r, column=c)
        cell.value = plausible_value(header, cell.value, dd_by_label, rng)
        amber_ids.append(rid)

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    wb.save(dst_path)

    return {
        "source_worklist": os.path.basename(src_path),
        "returned_file": os.path.basename(dst_path),
        "yellow_cells_total": len(yellow),
        "amber_cells_total": len(amber),
        "filled_with_value": len(to_value),
        "filled_with_mdc": len(to_mdc),
        "filled_with_mdc_on_mdc_enabled_field": mdc_on_mdc_field,
        "left_untouched": len(yellow) - n_fill,
        "notes_on_changed_rows": len(note_rows),
        "notes_only_rows": len(note_only_rows),
        "out_of_scope_edits": len(oos),
        "amber_cells_filled": len(amber_pick),
        "records_with_changed_cells": len(changed_ids),
        "changed_cells_total": n_fill,
        "note_only_record_ids": note_only_ids,
        "out_of_scope_detail": oos_detail,
        "amber_filled_record_ids": sorted(amber_ids),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_builder(out_root: str) -> str:
    build_dir = os.path.join(out_root, "build")
    proc = subprocess.run(
        [sys.executable, BUILDER,
         "--records-csv", os.path.join(HERE, "records.csv"),
         "--metadata-csv", os.path.join(HERE, "datadictionary.csv"),
         "--fields", os.path.join(HERE, "qa_fields.yaml"),
         "--out", build_dir, "--id-field", "syn_id", "--round="],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        raise SystemExit("build_worklists.py failed:\n" + proc.stdout + proc.stderr)
    return build_dir


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True,
                    help="Directory for the generated build/ and returned/ workbooks")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--update-manifest", action="store_true",
                    help="Merge the counts into MANIFEST.json's `returned` block")
    args = ap.parse_args()

    build_dir = run_builder(args.out)
    dd_by_label = load_dd(os.path.join(HERE, "datadictionary.csv"))
    returned_dir = os.path.join(args.out, "returned")

    per_file, totals = {}, {}
    for i, name in enumerate(sorted(PLAN)):
        src = os.path.join(build_dir, "with_MDC", f"{name}.xlsx")
        if not os.path.exists(src):
            raise SystemExit(f"expected worklist not produced: {src}")
        dst = os.path.join(returned_dir, f"{name}_RETURNED.xlsx")
        counts = engineer_return(src, dst, PLAN[name], dd_by_label, args.seed + i)
        per_file[name] = counts
        for k, v in counts.items():
            if isinstance(v, int):
                totals[k] = totals.get(k, 0) + v
        print(f"  wrote {dst}  "
              f"({counts['filled_with_value']} values, {counts['filled_with_mdc']} MDC, "
              f"{counts['left_untouched']} untouched, {counts['notes_only_rows']} note-only, "
              f"{counts['out_of_scope_edits']} out-of-scope)")

    block = {
        "synthetic": True,
        "seed": args.seed,
        "source_mode": "with_MDC",
        "generator": "generate_returns.py",
        "note": "RA-returned workbooks are generated at test time; no .xlsx is committed.",
        "per_file": per_file,
        "totals": {k: totals[k] for k in sorted(totals)},
        # What review_responses.py should report, derived from the edits above.
        "expected_review_responses": {
            name: {
                "records_with_proposed_updates": c["records_with_changed_cells"],
                "changed_cells": c["changed_cells_total"],
                "note_only_records": c["notes_only_rows"],
                "response_column_present": True,
                # Known gaps in review_responses.py — see the round-trip test.
                "out_of_scope_edits_detected": 0,
                "amber_cells_detected": 0,
            }
            for name, c in per_file.items()
        },
    }

    os.makedirs(returned_dir, exist_ok=True)
    with open(os.path.join(returned_dir, "returned_counts.json"), "w") as fh:
        json.dump(block, fh, indent=2, sort_keys=True)
        fh.write("\n")

    if args.update_manifest:
        mpath = os.path.join(HERE, "MANIFEST.json")
        manifest = json.load(open(mpath))
        manifest["returned"] = block
        with open(mpath, "w") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"Updated {mpath} → `returned` block")

    print(f"Done. {len(per_file)} returned workbook(s) in {returned_dir}")


if __name__ == "__main__":
    main()
