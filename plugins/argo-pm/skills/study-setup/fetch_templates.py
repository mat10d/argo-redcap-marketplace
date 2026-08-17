#!/usr/bin/env python3
"""Download ARGO's official Word templates from the Study Tracker's File Repository.

The real templates — official formatting, letterhead and all — live in REDCap, where ARGO
governance maintains them. They are deliberately NOT bundled with this skill: the toolkit's
repository is public, and the templates contain internal contact details. Fetching also means
you always get the current official version, never a stale copy.

    python3 fetch_templates.py --to <folder>            # download the ARGO Templates tree
    python3 fetch_templates.py --to <folder> --refresh  # re-download even if already present

Needs the Study Tracker access key (STUDY_INITIATION_REQUEST) — the same Tier 1 key the PM
already holds. Without it, download the File Repository by hand instead: open the Study Tracker
in REDCap → File Repository → ARGO Templates → download, and put the folder inside your ARGO
workspace so the tools can find it.
"""
from __future__ import annotations

import argparse
import os
import sys
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


# The File Repository folder holding the official templates.
TEMPLATES_FOLDER = "ARGO Templates"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Download ARGO's official templates from the Study Tracker File Repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--to", metavar="FOLDER",
                    help="Where to save them — normally <your ARGO workspace>/templates-official")
    ap.add_argument("--refresh", action="store_true",
                    help="Re-download files that are already present")
    args = ap.parse_args()

    if not args.to:
        print(__doc__)
        print("Tell me where to save the templates with --to, for example:")
        print("\n    python3 fetch_templates.py --to ~/argo-work/templates-official")
        return 2

    _add_argo_core_to_path()
    from argo_redcap_client import RedcapClient, RedcapError

    client = RedcapClient.from_env("STUDY_INITIATION_REQUEST", label="Study Tracker")
    if client is None:
        print(RedcapClient.explain_missing_token(
            "STUDY_INITIATION_REQUEST",
            "download the official templates",
            fallback=(
                "You can get them by hand instead: open the Study Tracker in REDCap, go to\n"
                "File Repository → ARGO Templates, download the folder, and put it inside your\n"
                "ARGO workspace folder. The tools find it there by name."
            ),
        ))
        return 1

    target = Path(args.to).expanduser()
    try:
        client.confirm_project(expect_title="Study Tracker", expect_pid="224")

        def find_folder(name, folder_id=None):
            for item in client.list_file_repository(folder_id):
                if "folder_id" in item and item.get("name") == name:
                    return item["folder_id"]
            return None

        root = find_folder(TEMPLATES_FOLDER)
        if root is None:
            print(f"The Study Tracker's File Repository has no folder called {TEMPLATES_FOLDER!r}.\n"
                  "It may have been renamed — open the File Repository in REDCap to see, and pass\n"
                  "nothing here until this script is updated to match.")
            return 1

        downloaded = skipped = 0

        def walk(folder_id, into: Path):
            nonlocal downloaded, skipped
            for item in client.list_file_repository(folder_id):
                if "folder_id" in item:
                    walk(item["folder_id"], into / item.get("name", "folder"))
                    continue
                name, doc_id = item.get("name"), item.get("doc_id")
                if not name or not doc_id:
                    continue
                dest = into / name
                if dest.exists() and not args.refresh:
                    skipped += 1
                    continue
                into.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(client.export_file_repository(doc_id))
                print(f"  downloaded {dest.relative_to(target)}")
                downloaded += 1

        walk(root, target)
        print(f"\nDone: {downloaded} downloaded, {skipped} already present "
              f"({'re-run with --refresh to replace them' if skipped else 'all fresh'}).")
        print(f"Templates are in: {target}")
        print("\nThese contain internal ARGO contact details — keep them in your workspace,")
        print("don't publish or commit them anywhere public.")
        return 0
    except RedcapError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
