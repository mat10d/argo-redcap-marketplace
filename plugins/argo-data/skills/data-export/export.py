#!/usr/bin/env python3
"""Download things out of a REDCap study — records, the data dictionary, or both.

Everything is saved as a file on your computer. Nothing in this script changes anything in
REDCap; it only reads. (Importing is a separate, more careful path — see the SKILL.md.)

Usage:
    set -a; source ~/.argo/.env; set +a

    # See what a key opens, without downloading anything
    python3 export.py --token-env CRC_TOKEN --info

    # The usual thing: records + data dictionary into a dated folder
    python3 export.py --token-env CRC_TOKEN --out ~/Desktop/crc-export

    # Just the data dictionary
    python3 export.py --token-env CRC_TOKEN --out ./dd --what metadata

    # Only some forms
    python3 export.py --token-env CRC_TOKEN --out ./sub --forms demographics,followup

A note on identifiable data: REDCap decides how much you can see based on the permissions of the
account the access key belongs to — there is no switch in this script that can strip identifiers.
If you need a de-identified extract, ask your REDCap administrator for a key tied to an account
whose export rights are set to "De-Identified", and always open the resulting file and check it
before sharing it with anyone.

If you don't have an access key for the study, that's expected — most ARGO studies don't have one
(see access-tiers.md, Tier 2). Download the export from the REDCap website instead: go to the
project, choose Data Exports, Reports and Stats, then export "All data" as CSV, and download the
data dictionary from the Dictionary page. Every ARGO analysis tool works from those two files.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
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
    for root in ("/mnt/.remote-plugins", "~/.claude/plugins", "~/.claude/plugins/cache"):
        base = _P(root).expanduser()
        if base.is_dir():
            hits = sorted(base.glob(f"**/{marker}"))
            if hits:
                sys.path.insert(0, str(hits[-1].parent)); return
    for parent in _P(__file__).resolve().parents:
        for cand in (parent / "plugins" / "argo-core" / "scripts",
                     parent / "argo-core" / "scripts"):
            if (cand / marker).exists():
                sys.path.insert(0, str(cand)); return


_add_argo_core_to_path()
from argo_redcap_client import RedcapClient, RedcapError  # noqa: E402


NO_TOKEN_ADVICE = (
    "You don't need an access key to carry on — you can download the same thing from the REDCap\n"
    "website by hand, and every ARGO analysis tool reads those files happily:\n"
    "\n"
    "  1. Open the study in REDCap in your web browser.\n"
    "  2. For the data: go to 'Data Exports, Reports, and Stats', choose 'All data', and export\n"
    "     it as CSV.\n"
    "  3. For the field list: go to the 'Data Dictionary' page and download it as CSV.\n"
    "\n"
    "Save both files somewhere you'll find them again, then point the analysis tools at them."
)


def human_size(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "bytes" else f"{n / 1:,.1f} {unit}"
        n /= 1024
    return f"{n} bytes"


def write_file(path: Path, text: str, label: str) -> None:
    path.write_text(text)
    size = path.stat().st_size
    lines = max(text.count("\n") - 1, 0)
    print(f"  Saved {label}: {path.name}  ({lines:,} rows, {human_size(size)})")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Download records and/or the data dictionary from a REDCap study.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=NO_TOKEN_ADVICE,
    )
    ap.add_argument("--token-env", required=True,
                    help="Name of the environment variable holding the study's access key, "
                         "e.g. CRC_TOKEN")
    ap.add_argument("--out", help="Folder to save the downloaded files into")
    ap.add_argument("--what", choices=["records", "metadata", "both"], default="both",
                    help="What to download. Default: both")
    ap.add_argument("--forms", help="Only these forms, comma-separated (default: all forms)")
    ap.add_argument("--raw", action="store_true",
                    help="Save the underlying codes (1, 2, 3) instead of the readable labels")
    ap.add_argument("--info", action="store_true",
                    help="Just say which project this key opens, and stop")
    ap.add_argument("--expect-project", metavar="NAME_OR_PID",
                    help="Refuse to download unless the key opens this project, by name or number")
    args = ap.parse_args()

    client = RedcapClient.from_env(args.token_env)
    if client is None:
        print(RedcapClient.explain_missing_token(
            args.token_env, "download anything from this study", fallback=NO_TOKEN_ADVICE))
        return 1

    try:
        info = client.project_info()
        title = (info.get("project_title") or "?").strip()
        pid = info.get("project_id", "?")

        if args.expect_project:
            expect = str(args.expect_project).strip()
            client.confirm_project(
                expect_title=None if expect.isdigit() else expect,
                expect_pid=expect if expect.isdigit() else None,
            )

        id_field = client.record_id_field()
        print(f"Study: {title!r} (project {pid})")
        print(f"The column identifying each record is called {id_field!r}.")

        if args.info:
            forms = sorted({f.get("form_name", "") for f in client.export_metadata()} - {""})
            print(f"It has {len(forms)} form(s): {', '.join(forms)}")
            return 0

        if not args.out:
            print(
                "\nTell me where to save the download, with --out, for example:\n"
                "\n"
                f"    python3 {os.path.basename(__file__)} --token-env {args.token_env} "
                "--out ~/Desktop/my-export"
            )
            return 2

        out = Path(args.out).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        slug = "".join(c if c.isalnum() else "-" for c in title.lower())[:40].strip("-")

        print(f"\nSaving into {out}")

        if args.what in ("metadata", "both"):
            params = {}
            if args.forms:
                for i, form in enumerate(f.strip() for f in args.forms.split(",")):
                    params[f"forms[{i}]"] = form
            dd = client.export_metadata_csv(**params)
            write_file(out / f"{slug}_datadictionary_{stamp}.csv", dd, "data dictionary")

        if args.what in ("records", "both"):
            params = {"rawOrLabel": "raw" if args.raw else "label",
                      "exportCheckboxLabel": "false" if args.raw else "true",
                      "exportDataAccessGroups": "true"}
            if args.forms:
                for i, form in enumerate(f.strip() for f in args.forms.split(",")):
                    params[f"forms[{i}]"] = form
            records = client.export_records_csv(**params)
            write_file(out / f"{slug}_records_{stamp}.csv", records, "records")

        print("\nDone. Nothing in REDCap was changed — this only read data out.")
        return 0

    except RedcapError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
