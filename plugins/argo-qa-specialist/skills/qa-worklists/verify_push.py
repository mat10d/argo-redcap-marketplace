"""Re-pull REDCap state and emit only the push-draft cells that are still needed.

⚠️ DEPRECATED — supports the migration-only push path. See argo-core
redcap-api-gotchas.md §0 (no programmatic writes to cohort patient data). The QA
loop is read-only; only use this as part of a deliberate one-off legacy migration.
NOTE: its conflict heuristic skips planned="0", so it under-flags real overwrites
(e.g. a yes/no field going Yes→No). Cross-check with a full decode/categorize
preview before trusting it.


Closes the race condition where an RA updates REDCap directly between when
we staged push_drafts/ and when we push. For each (record, field) in the
draft:
  - If REDCap currently equals the value we'd push → drop it (no-op).
  - If REDCap currently is non-blank and DIFFERS from our planned value
    → flag as CONFLICT (RA wrote something else; needs human eyes).
  - Otherwise (REDCap blank, sentinel matches our intended pre-state, etc.)
    → keep in the delta payload.

Outputs (next to the inputs):
  <push_drafts_dir>/_verified/<original>.csv   — safe-to-push deltas
  <push_drafts_dir>/_conflicts.md               — any conflicts to review

Usage:
  python3 verify_push.py --url $REDCAP_URL --token-env CRC_TOKEN \\
      --push-drafts push_drafts/2026-05-24/ \\
      [--id-field research_number]
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from io import StringIO

import requests


def pull_records(url: str, token: str, ids: list[str], fields: list[str],
                 id_field: str) -> dict:
    """Pull only the records and fields we need. Returns {rid: {field: value}}."""
    data = {"token": token, "content": "record", "format": "csv", "type": "flat",
            "rawOrLabel": "raw", "returnFormat": "json"}
    for i, rid in enumerate(ids):
        data[f"records[{i}]"] = rid
    for i, f in enumerate(fields):
        data[f"fields[{i}]"] = f
    r = requests.post(url, data=data, timeout=300)
    r.raise_for_status()
    out = {}
    for row in csv.DictReader(StringIO(r.text)):
        out[row[id_field]] = row  # key by the record ID, not fields[0] (alpha-first)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--token-env", required=True)
    ap.add_argument("--push-drafts", required=True,
                    help="Directory holding the staged *.csv files")
    ap.add_argument("--id-field", default="research_number")
    args = ap.parse_args()

    tok = os.environ.get(args.token_env)
    if not tok:
        sys.exit(
        f"No access key for {args.token_env} is set up on this computer, so I can't reach REDCap.\n"
        "\n"
        "An access key (REDCap calls it an API token) is a long password that lets a tool read\n"
        "or update one specific REDCap project on your behalf. Your REDCap administrator\n"
        "creates it for you — it isn't something you can generate yourself.\n"
        "\n"
        "If you already have one, add it to the file ~/.argo/.env, then load it into this\n"
        "terminal window and try again:\n"
        "\n"
        "    set -a; source ~/.argo/.env; set +a"
    )

    # Gather all (id, field) targets across every push CSV
    all_ids: set[str] = set()
    all_fields: set[str] = {args.id_field}
    drafts = []
    for fn in sorted(os.listdir(args.push_drafts)):
        if not fn.endswith(".csv") or fn.startswith("_"):
            continue
        path = os.path.join(args.push_drafts, fn)
        rows = list(csv.DictReader(open(path)))
        drafts.append((fn, rows))
        for row in rows:
            rid = row.get(args.id_field, "").strip()
            if rid:
                all_ids.add(rid)
        if rows:
            all_fields.update(c for c in rows[0] if c != args.id_field)

    if not all_ids:
        sys.exit(
            "There are no records to check — the push_drafts folder is empty.\n"
            "\n"
            "That folder is filled in by the review step. If you haven't run that yet, do it\n"
            "first; if you have, it may simply have found nothing needing changes, which is fine."
        )

    print(f"Re-pulling {len(all_ids)} records × {len(all_fields)} fields...")
    current = pull_records(args.url, tok, sorted(all_ids), sorted(all_fields), args.id_field)

    out_dir = os.path.join(args.push_drafts, "_verified")
    os.makedirs(out_dir, exist_ok=True)
    conflict_lines = ["# Push conflicts — REDCap state has changed since the push_drafts were staged",
                       "", "These records/fields had a value in REDCap that doesn't match what we",
                       "were about to push. Human-review each one before deciding whether to push.",
                       ""]

    grand_kept = grand_dropped = grand_conflict = 0
    for fn, rows in drafts:
        out_rows = []
        for row in rows:
            rid = row.get(args.id_field, "").strip()
            cur = current.get(rid, {})
            kept = {args.id_field: rid}
            for col, planned in row.items():
                if col == args.id_field or planned == "":
                    continue
                live = (cur.get(col, "") or "").strip()
                if live == planned:
                    grand_dropped += 1
                    continue
                # Conflict heuristic: REDCap is non-blank, our planned write differs,
                # and our intent isn't simply "unset a checkbox we already see set"
                # (unset = `planned == "0"`).
                if live and planned != "0" and live != "":
                    conflict_lines.append(
                        f"- **{rid}** `{col}`: planned `{planned}`, REDCap now `{live}`"
                    )
                    grand_conflict += 1
                    continue
                kept[col] = planned
                grand_kept += 1
            if len(kept) > 1:  # has at least one cell beyond the id
                out_rows.append(kept)

        if out_rows:
            # Preserve the original column order
            orig_cols = list(rows[0].keys()) if rows else [args.id_field]
            with open(os.path.join(out_dir, fn), "w") as f:
                w = csv.DictWriter(f, fieldnames=orig_cols)
                w.writeheader()
                for r in out_rows:
                    w.writerow({c: r.get(c, "") for c in orig_cols})
            print(f"  {fn}: {len(out_rows)} record(s) with deltas → _verified/{fn}")
        else:
            print(f"  {fn}: nothing to push (all cells already current in REDCap)")

    if grand_conflict:
        cpath = os.path.join(args.push_drafts, "_conflicts.md")
        open(cpath, "w").write("\n".join(conflict_lines) + "\n")
        print(f"\n  ⚠️  {grand_conflict} conflict(s) → review {cpath} before pushing")
    print(f"\nSummary: {grand_kept} cells to push, {grand_dropped} already current, {grand_conflict} conflicts.")


if __name__ == "__main__":
    main()
