"""Snapshot a REDCap project's full record state to a timestamped CSV.

Use before pushing QA writebacks so you have a rollback point. The snapshot
is a raw flat export with DAGs included — same shape as build_worklists.py
pulls, so it round-trips cleanly through `overwriteBehavior=overwrite` if
you ever need to restore.

Usage:
  python3 snapshot_project.py --url $REDCAP_URL --token-env CRC_TOKEN \\
                              --out snapshots/
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import requests


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--token-env", required=True)
    ap.add_argument("--out", required=True, help="Directory for snapshot files")
    ap.add_argument("--tag", default="", help="Optional tag appended to filename")
    args = ap.parse_args()

    tok = os.environ.get(args.token_env)
    if not tok:
        sys.exit(f"Env var {args.token_env} is not set")

    os.makedirs(args.out, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    suffix = f"_{args.tag}" if args.tag else ""
    path = os.path.join(args.out, f"snapshot_{stamp}{suffix}.csv")

    r = requests.post(args.url, data={
        "token": tok, "content": "record", "format": "csv", "type": "flat",
        "rawOrLabel": "raw", "exportDataAccessGroups": "true",
        "returnFormat": "json",
    }, timeout=600)
    r.raise_for_status()
    with open(path, "w") as f:
        f.write(r.text)
    print(f"Wrote {path}  ({len(r.text):,} bytes)")


if __name__ == "__main__":
    main()
