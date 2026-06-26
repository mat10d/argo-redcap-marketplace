"""Push QA writeback payloads to REDCap.

⚠️ DEPRECATED — MIGRATION-ONLY. See argo-core redcap-api-gotchas.md §0
"no programmatic writes to cohort patient data". The QA loop is read-only:
RAs fill REDCap directly against the worklists. This script bypasses REDCap's
branching logic, field validation, and audit trail, and is retained only for
deliberate one-off legacy migrations. It refuses to run without --force-migration.

Concatenates one or more `push_drafts/<site>_<wb>.csv` files (the per-site
review outputs) into a single import, then POSTs to the records endpoint
with `overwriteBehavior=normal` so blank cells leave existing values alone
and only the named columns get touched.

Always snapshot first (see snapshot_project.py) — REDCap has no undo.

Usage:
  python3 push_updates.py --url $REDCAP_URL --token-env CRC_TOKEN \\
                          push_drafts/*.csv
  # add --dry-run to print the merged CSV without sending
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys

import requests


def _merge_csvs(paths: list[str]) -> str:
    """Outer-union of headers across input CSVs, blanks where a row didn't have a col."""
    all_rows = []
    columns = []
    seen = set()
    for p in paths:
        with open(p) as f:
            r = csv.DictReader(f)
            for h in (r.fieldnames or []):
                if h not in seen:
                    columns.append(h); seen.add(h)
            for row in r:
                all_rows.append(row)
    if not all_rows:
        return ""
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=columns)
    w.writeheader()
    for row in all_rows:
        w.writerow({c: row.get(c, "") for c in columns})
    return out.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--token-env", required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the merged CSV and exit without sending")
    ap.add_argument("--force-migration", action="store_true",
                    help="Required to actually POST. Acknowledges this is a deliberate "
                         "one-off legacy migration, NOT routine QA (see redcap-api-gotchas §0). "
                         "Snapshot first.")
    ap.add_argument("payloads", nargs="+", help="CSV files to merge and push")
    args = ap.parse_args()

    tok = os.environ.get(args.token_env)
    if not tok:
        sys.exit(f"Env var {args.token_env} is not set")

    merged = _merge_csvs(args.payloads)
    if not merged.strip():
        sys.exit("Nothing to push — all payloads were empty.")

    rows = merged.count("\n") - 1
    print(f"Merged {len(args.payloads)} payload(s) → {rows} record(s) to update.")
    if args.dry_run:
        print("--- merged CSV ---")
        print(merged)
        return

    if not args.force_migration:
        sys.exit(
            "\nREFUSING TO PUSH — deprecated/migration-only per policy "
            "(redcap-api-gotchas §0).\nCohort patient data is entered by RAs directly "
            "in REDCap, not pushed from CSV. If this is a deliberate one-off legacy "
            "migration, snapshot first, then re-run with --force-migration."
        )

    print("Pushing with overwriteBehavior=normal (blank cells leave existing values alone)...")
    r = requests.post(args.url, data={
        "token": tok, "content": "record", "format": "csv", "type": "flat",
        "overwriteBehavior": "normal", "data": merged,
        "returnContent": "count", "returnFormat": "json",
    }, timeout=300)
    if not r.ok:
        sys.exit(f"REDCap returned HTTP {r.status_code}:\n{r.text}")  # surface the reason, don't hide it
    print("Response:", r.text)


if __name__ == "__main__":
    main()
