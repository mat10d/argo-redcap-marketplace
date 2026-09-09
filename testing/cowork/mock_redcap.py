#!/usr/bin/env python3
"""Build a mock REDCap folder from the synthetic fixtures — what a test workspace talks to.

    python3 mock_redcap.py --out <workspace>/.mock-redcap [--files-root DIR] [--study-key]

Projects it lays out (every one synthetic; see testing/fixtures/*/MANIFEST.json):

    study_tracker, personnel_requests, data_requests, data_linking_requests, support_tickets
        the five admin trackers, from testing/fixtures/synthetic-trackers — same titles and
        PIDs as the real ones, so the toolkit's confirm-before-write checks pass
    syn
        the synthetic colorectal cohort (200 records, two DAGs), from synthetic-study — plays
        the "CRC" study whose key a QA specialist or database manager holds

The Study Tracker's File Repository is served from --files-root if given — point it at a folder
holding the real fetched templates (they carry staff contact details, so that folder lives
outside any repo and is never committed) — otherwise it is empty, which is also a legitimate
test: the skills must fall back to their skeletons and say so.

Prints the fake tokens as KEY=VALUE lines; round.py writes them into the workspace settings
file. They are deterministic 32-hex strings that open nothing anywhere real.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "testing/fixtures"
sys.path.insert(0, str(REPO / "plugins/argo-core/skills/redcap-api/scripts"))
from argo_redcap_mock import fake_token  # noqa: E402
from argo_trackers import ADMIN_TRACKERS  # noqa: E402

TRACKER_FILES = {
    "STUDY_INITIATION_REQUEST": "study_tracker",
    "STUDY_PERSONELL_REQUEST": "personnel_requests",
    "DATA_REQUEST": "data_requests",
    "DATA_LINKING_REQUEST": "data_linking_requests",
    "SUPPORT_TICKET_REQUEST": "support_tickets",
}
STUDY_ENV = "CRC_TOKEN"
STUDY_NAME = "syn"
STUDY_PID = "9077"


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False))


def build(out: Path, files_root: "Path | None", study_key: bool) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    keys: dict = {}
    env_lines: dict = {}

    # the five trackers
    src = FIXTURES / "synthetic-trackers"
    for env_var, title, pid, _marker in ADMIN_TRACKERS:
        name = TRACKER_FILES[env_var]
        pdir = out / "projects" / name
        _write(pdir / "project.json", {"project_id": pid, "project_title": title,
                                       "_stored_mode": "label", "_synthetic": True})
        shutil.copy(src / f"metadata_{name}.json", pdir / "metadata.json")
        shutil.copy(src / f"{name}.json", pdir / "records.json")
        token = fake_token(name)
        keys[token] = name
        env_lines[env_var] = token

    # the Study Tracker's File Repository
    if files_root:
        dest = out / "projects/study_tracker/files"
        # fetch_templates.py expects "ARGO Templates" at the root plus the two extras as
        # sibling folders — which is exactly how a fetched tree is laid out on disk.
        (dest / "ARGO Templates").mkdir(parents=True)
        for item in sorted(Path(files_root).iterdir()):
            if item.name.startswith(("_", ".")):
                continue
            if item.name in ("ARGO Quality Assurance (QA)", "ARGO Standard Operating Procedures (SOPs)"):
                shutil.copytree(item, dest / item.name)
            elif item.is_dir():
                shutil.copytree(item, dest / "ARGO Templates" / item.name)

    # the synthetic study
    sdir = out / "projects" / STUDY_NAME
    study = FIXTURES / "synthetic-study"
    manifest = json.loads((study / "MANIFEST.json").read_text())
    with open(study / "datadictionary.csv", newline="") as fh:
        metadata = list(csv.DictReader(fh))
    with open(study / "records.csv", newline="") as fh:
        records = list(csv.DictReader(fh))
    _write(sdir / "project.json", {"project_id": STUDY_PID,
                                   "project_title": manifest["study"]["title"],
                                   "_stored_mode": "raw", "_synthetic": True})
    _write(sdir / "metadata.json", metadata)
    _write(sdir / "records.json", records)
    token = fake_token(STUDY_NAME)
    keys[token] = STUDY_NAME
    if study_key:
        env_lines[STUDY_ENV] = token

    _write(out / "keys.json", keys)
    _write(out / "config.json", {"apply_writes": False, "simulate_egress_block": False})
    (out / "README.md").write_text(
        "# Mock REDCap — synthetic, for testing the ARGO toolkit\n\n"
        "This folder stands in for REDCap during a test session. Every project, record, name\n"
        "and study in it is fabricated. Nothing here is real, and nothing written to it goes\n"
        "anywhere: writes are appended to WRITES.jsonl and not applied.\n")
    return {"env": env_lines, "study_token": token, "study_pid": STUDY_PID,
            "study_title": manifest["study"]["title"], "keys": keys}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--files-root", help="folder of fetched official templates to serve as the "
                                         "Study Tracker's File Repository (never committed)")
    ap.add_argument("--study-key", action="store_true", help="also emit CRC_TOKEN for the synthetic study")
    a = ap.parse_args()
    info = build(Path(a.out).expanduser(), Path(a.files_root).expanduser() if a.files_root else None,
                 a.study_key)
    for k, v in info["env"].items():
        print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
