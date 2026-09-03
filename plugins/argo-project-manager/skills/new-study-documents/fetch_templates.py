#!/usr/bin/env python3
"""Download ARGO's official Word templates from the Study Tracker's File Repository.

The real templates — official formatting, letterhead and all — live in REDCap, where ARGO
governance maintains them. They are deliberately NOT bundled with this skill: the toolkit's
repository is public, and the templates contain internal contact details. Fetching also means
you always get the current official version, never a stale copy.

    python3 fetch_templates.py --to <folder>            # download the templates the pipeline needs
    python3 fetch_templates.py --to <folder> --refresh  # re-download even if already present

It brings the whole ARGO Templates tree, plus two things the study-launch pipeline needs that
live outside it: the ARGO QA Plan, and the two Study Start-Up SOPs (NIH / non-NIH).

Needs the Study Tracker access key (STUDY_INITIATION_REQUEST) — one of the five tracker keys you
already have. Without it, download the File Repository by hand instead: open the Study Tracker
in REDCap → File Repository → ARGO Templates (and ARGO Quality Assurance (QA), and ARGO Standard
Operating Procedures (SOPs) → Study Start-Up) → download, and put the folders in your ARGO folder
as project-manager/templates-official so the tools can find it.
"""
from __future__ import annotations

import argparse
import os
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


# What to fetch from the File Repository: (folder path from the root, where it lands under --to).
# ARGO Templates is the bulk of it and lands at the root, so a fetched tree looks the same as a
# hand-downloaded "ARGO Templates" folder. The other two are the study-launch pipeline's
# documents that live OUTSIDE ARGO Templates — the QA plan and the two Study Start-Up SOPs — and
# they keep their own folder names so the layout mirrors REDCap.
TEMPLATES_FOLDER = "ARGO Templates"
FETCH = [
    ((TEMPLATES_FOLDER,), ""),
    (("ARGO Quality Assurance (QA)",), "ARGO Quality Assurance (QA)"),
    (("ARGO Standard Operating Procedures (SOPs)", "Study Start-Up"),
     "ARGO Standard Operating Procedures (SOPs)/Study Start-Up"),
]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Download ARGO's official templates from the Study Tracker File Repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--to", metavar="FOLDER",
                    help="Where to save them — normally <your ARGO folder>/project-manager/templates-official")
    ap.add_argument("--refresh", action="store_true",
                    help="Re-download files that are already present")
    args = ap.parse_args()

    if not args.to:
        print(__doc__)
        print("Tell me where to save the templates with --to, for example:")
        print("\n    python3 fetch_templates.py --to ~/ARGO/project-manager/templates-official")
        return 2

    from argo_redcap_client import RedcapClient, RedcapError

    client = RedcapClient.from_env("STUDY_INITIATION_REQUEST", label="Study Tracker")
    if client is None:
        print(RedcapClient.explain_missing_token(
            "STUDY_INITIATION_REQUEST",
            "download the official templates",
            fallback=(
                "You can get them by hand instead: open the Study Tracker in REDCap, go to\n"
                "File Repository → ARGO Templates, download the folder, and put it in your ARGO\n"
                "folder as project-manager/templates-official. The tools find it there by name.\n"
                "Two more the pipeline uses sit outside that folder — ARGO Quality Assurance (QA)\n"
                "and ARGO Standard Operating Procedures (SOPs) → Study Start-Up. Download those\n"
                "into the same place if you need the QA plan or the Study Start-Up SOPs."
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

        def resolve(path):
            """Walk a folder path from the File Repository root; None if any part is missing."""
            folder_id = None
            for part in path:
                folder_id = find_folder(part, folder_id)
                if folder_id is None:
                    return None
            return folder_id

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

        for path, into in FETCH:
            folder_id = resolve(path)
            label = "/".join(path)
            if folder_id is None:
                if path[0] == TEMPLATES_FOLDER:
                    print(f"The Study Tracker's File Repository has no folder called {label!r}.\n"
                          "It may have been renamed — open the File Repository in REDCap to see, and pass\n"
                          "nothing here until this script is updated to match.")
                    return 1
                # The extras are useful, not essential — say what's missing and carry on.
                print(f"  (no {label!r} folder in the File Repository — skipped)")
                continue
            walk(folder_id, target / into)

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
