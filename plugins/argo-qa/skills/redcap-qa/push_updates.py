"""Push QA writeback payloads to REDCap.

⚠️ DEPRECATED — MIGRATION-ONLY. See argo-core redcap-api-gotchas.md §0
"no programmatic writes to cohort patient data". The QA loop is read-only:
RAs fill REDCap directly against the worklists. This script bypasses REDCap's
branching logic, field validation, and audit trail, and is retained only for
deliberate one-off legacy migrations.

This is the only script in the ARGO suite that can change patient data at scale, so it is the
most locked down (Tier 3 in argo-core's access-tiers.md). Four things must all be true before
it will write anything:

  1. You reviewed a preview of the exact data being sent (--dry-run), and it matched.
  2. You named the project you intend to write to, and the access key really opens that project.
  3. You passed --force-migration, acknowledging this isn't routine QA.
  4. You took a snapshot first (snapshot_project.py) — REDCap has no undo.

Concatenates one or more `push_drafts/<site>_<wb>.csv` files (the per-site
review outputs) into a single import, then sends it with `overwriteBehavior=normal`
so blank cells leave existing values alone and only the named columns get touched.

Usage:
  # Step 1 — always. Shows exactly what would be sent, changes nothing.
  python3 push_updates.py --token-env CRC_TOKEN --dry-run push_drafts/*.csv

  # Step 2 — only after reviewing step 1's output, and after snapshotting.
  python3 push_updates.py --token-env CRC_TOKEN --expect-project "Colorectal Cancer" \\
                          --force-migration push_drafts/*.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path

def _add_argo_core_to_path():
    """Find argo-core's scripts folder and make it importable.

    Searches for the FILE argo_redcap_client.py, never for a directory named "argo-core":
    plugin directories are named differently per environment (Claude Code uses
    <marketplace>/<plugin>/<version>/; Cowork uses opaque plugin_<id>/ names with the plugin
    name only inside its manifest), so a name-based search finds nothing in some of them.
    """
    from pathlib import Path as _P
    marker = "argo_redcap_client.py"
    override = os.environ.get("ARGO_CORE_SCRIPTS")
    if override and (_P(override).expanduser() / marker).exists():
        sys.path.insert(0, str(_P(override).expanduser())); return
    for parent in _P(__file__).resolve().parents:
        for cand in (parent / "plugins" / "argo-core" / "skills" / "redcap-api" / "scripts",
                     parent / "plugins" / "argo-core" / "scripts",
                     parent / "argo-core" / "scripts"):
            if (cand / marker).exists():
                sys.path.insert(0, str(cand)); return
    for root in ("/mnt/.remote-plugins", "/mnt/skills", "~/.claude/plugins", "~/.claude/plugins/cache"):
        base = _P(root).expanduser()
        if base.is_dir():
            hits = list(base.glob(f"**/{marker}"))
            if hits:  # newest file, never name order — version dirs sort lexically ("0.9" > "0.12")
                sys.path.insert(0, str(max(hits, key=lambda h: h.stat().st_mtime).parent)); return


_add_argo_core_to_path()
from argo_redcap_client import RedcapClient, RedcapError  # noqa: E402

# Where the record of "you previewed this exact data" is kept.
RECEIPT_DIR = Path.home() / ".argo" / "qa-dry-run-receipts"
# How long a preview stays valid. Long enough to review carefully, short enough that you can't
# accidentally rely on a preview from last month.
RECEIPT_MAX_AGE_SECONDS = 24 * 60 * 60


def _merge_csvs(paths: list[str]) -> str:
    """Outer-union of headers across input CSVs, blanks where a row didn't have a col."""
    all_rows = []
    columns = []
    seen = set()
    for p in paths:
        path = Path(p).expanduser()
        if not path.exists():
            sys.exit(
                f"I couldn't find one of the files you asked me to send:\n"
                f"    {path}\n"
                "\n"
                "Check the name and folder are right. These are normally the CSV files the\n"
                "review step wrote into the push_drafts folder."
            )
        with open(path) as f:
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


def _fingerprint(merged: str, token_env: str) -> str:
    """A short code identifying this exact data going to this exact project."""
    return hashlib.sha256(f"{token_env}\n{merged}".encode()).hexdigest()[:16]


def write_receipt(fingerprint: str, rows: int, paths: list[str]) -> Path:
    """Record that this exact data was previewed, so the real push can check it was."""
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    receipt = RECEIPT_DIR / f"{fingerprint}.json"
    receipt.write_text(json.dumps({
        "fingerprint": fingerprint,
        "previewed_at": time.time(),
        "rows": rows,
        "files": [str(Path(p).expanduser()) for p in paths],
    }, indent=2))
    return receipt


def check_receipt(fingerprint: str) -> "str | None":
    """Return None if a valid preview exists, else a plain-language reason why not."""
    receipt = RECEIPT_DIR / f"{fingerprint}.json"
    if not receipt.exists():
        return (
            "I can't find a record that you previewed this exact data.\n"
            "\n"
            "Before anything is written to REDCap, you need to look at exactly what would be\n"
            "sent, so nothing goes in unseen. Run the same command again with --dry-run instead\n"
            "of --force-migration, read what it prints, and if it's right, run the real command.\n"
            "\n"
            "If you did already preview it, then something in the files has changed since — even\n"
            "one edited cell counts as different data and needs previewing again."
        )
    try:
        data = json.loads(receipt.read_text())
        age = time.time() - float(data.get("previewed_at", 0))
    except Exception:
        return (
            "The record of your preview is unreadable, so I can't confirm you saw this data.\n"
            "Run the command again with --dry-run to preview it freshly."
        )
    if age > RECEIPT_MAX_AGE_SECONDS:
        hours = int(age // 3600)
        return (
            f"You previewed this data {hours} hours ago, which is too long ago to rely on.\n"
            "Run the command again with --dry-run, check it still looks right, then push."
        )
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="REDCap API address. Defaults to REDCAP_URL from ~/.argo/.env")
    ap.add_argument("--token-env", required=True,
                    help="Name of the environment variable holding the access key for the study")
    ap.add_argument("--expect-project", metavar="NAME_OR_PID",
                    help="The project you intend to write to, by name or project number. "
                         "Required for a real push — the write is refused if the access key "
                         "opens anything else.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show exactly what would be sent and change nothing. Always do this first.")
    ap.add_argument("--force-migration", action="store_true",
                    help="Required to actually write. Acknowledges this is a deliberate "
                         "one-off legacy migration, NOT routine QA (see redcap-api-gotchas §0). "
                         "Snapshot first.")
    ap.add_argument("payloads", nargs="+", help="CSV files to merge and push")
    args = ap.parse_args()

    if args.url:
        os.environ["REDCAP_URL"] = args.url

    merged = _merge_csvs(args.payloads)
    if not merged.strip():
        sys.exit(
            "There's nothing to send — every file you gave me was empty.\n"
            "This usually means the review step found no changes to push, which is fine."
        )

    rows = merged.count("\n") - 1
    fingerprint = _fingerprint(merged, args.token_env)
    print(f"Merged {len(args.payloads)} file(s) → {rows} record(s) to update.")

    # ---- Preview path: show everything, write nothing, and record that it was shown.
    if args.dry_run:
        print("--- exactly what would be sent to REDCap ---")
        print(merged)
        print("--- end ---")
        write_receipt(fingerprint, rows, args.payloads)
        print(
            f"\nNothing has been changed — this was a preview of {rows} record(s).\n"
            "\n"
            "Read the rows above carefully. If they're right, and you have taken a snapshot\n"
            "(python3 snapshot_project.py), you can send them for real with:\n"
            "\n"
            f"    python3 {os.path.basename(__file__)} --token-env {args.token_env} \\\n"
            f"        --expect-project \"<the project name>\" --force-migration "
            f"{' '.join(args.payloads)}"
        )
        return

    # ---- Real push: every gate must pass.
    if not args.force_migration:
        sys.exit(
            "REFUSING TO WRITE — this script is for one-off legacy migrations only.\n"
            "\n"
            "Cohort patient data is entered by RAs directly in REDCap, not pushed from a\n"
            "spreadsheet, because pushing bypasses REDCap's own checks and its record of who\n"
            "changed what (see redcap-api-gotchas §0).\n"
            "\n"
            "If this really is a deliberate one-off migration: take a snapshot first, then add\n"
            "--force-migration to the command."
        )

    problem = check_receipt(fingerprint)
    if problem:
        sys.exit("REFUSING TO WRITE.\n\n" + problem)

    if not args.expect_project:
        sys.exit(
            "REFUSING TO WRITE — you haven't said which project this is meant to go to.\n"
            "\n"
            "Several ARGO projects share the same REDCap address, so an access key pointing at\n"
            "the wrong one would silently write patient data into the wrong study. Naming the\n"
            "project lets me check before anything is sent.\n"
            "\n"
            "Add it to the command, either as the project's name or its number:\n"
            "\n"
            '    --expect-project "Colorectal Cancer"      (or)      --expect-project 251'
        )

    client = RedcapClient.from_env(args.token_env)
    if client is None:
        sys.exit(RedcapClient.explain_missing_token(
            args.token_env,
            "write these records to REDCap",
            fallback=(
                "For this task you need the access key — there's no file-upload alternative,\n"
                "because the whole point of this script is writing directly. Ask your REDCap\n"
                "administrator for the key for this study, add it to ~/.argo/.env, and try again."
            ),
        ))

    expect = str(args.expect_project).strip()
    by_pid = expect.isdigit()

    print("Checking the access key opens the project you named...")
    try:
        info = client.confirm_project(
            expect_title=None if by_pid else expect,
            expect_pid=expect if by_pid else None,
        )
        print(f"  Confirmed: {info.get('project_title')!r} (project {info.get('project_id')})")
        # Tier 3: the rule that this must run under a permission-restricted account is otherwise
        # only a sentence in a document. Check it and say so out loud.
        client.warn_if_over_permissioned("changing patient data in this study")
        print(f"Writing {rows} record(s). Blank cells will leave existing values alone.")
        response = client.import_records_csv(merged, overwrite="normal")
    except RedcapError as e:
        sys.exit(f"\n{e}")

    print(f"\nDone. REDCap reports: {response}")
    print(
        "If this went wrong, restore from the snapshot you took before running this — REDCap\n"
        "has no undo of its own."
    )


if __name__ == "__main__":
    main()
