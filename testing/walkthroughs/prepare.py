#!/usr/bin/env python3
"""Stage a scratch workspace for one Tier 1.5 walkthrough (see README.md).

    python3 testing/walkthroughs/prepare.py --task qa        # qa|audit|analyst|linkage|documents|export|weekly-check
    python3 testing/walkthroughs/prepare.py --task qa --keys # also copy ~/.argo/.env in (read-only tasks only)

Creates testing/walkthroughs/runs/<task>/workspace (scaffolded by argo_setup.py, so the role
folders exist) and .../uploads/ holding that task's inputs copied from the dogfood kit at
~/Desktop/ARGO-test-data — the way Cowork exposes attachments. Prints the opening message.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KIT = Path.home() / "Desktop" / "ARGO-test-data"
RUNS = REPO / "testing" / "walkthroughs" / "runs"
SETUP = REPO / "plugins/argo-core/skills/redcap-api/scripts/argo_setup.py"

TASKS = {
    "qa": {
        "skill": "plugins/argo-qa-specialist/skills/qa-worklists/SKILL.md",
        "inputs": ["records.csv", "datadictionary.csv"],
        "prompt": "I'm QAing a study and need to build the RA worklists for the sites.",
        "roles": "qa-specialist",
    },
    "audit": {
        "skill": "plugins/argo-qa-specialist/skills/qa-worklists/SKILL.md",
        "inputs": ["qa-returns/returned", "qa-returns/build/with_MDC"],
        "prompt": "The RAs sent their worklists back — here are the originals and what came back. Audit them for me.",
        "roles": "qa-specialist",
    },
    "analyst": {
        "skill": "plugins/argo-data-analyst/skills/run-analysis/SKILL.md",
        "inputs": ["records.csv", "datadictionary.csv"],
        "prompt": "I've downloaded a study export and its data dictionary — make me a Table 1 of the demographics by site.",
        "roles": "data-analyst",
    },
    "linkage": {
        "skill": "plugins/argo-database-manager/skills/link-data/SKILL.md",
        "inputs": ["records.csv", "datadictionary.csv", "study-b"],
        "prompt": "Merge these two studies for analysis and show me the matches, conflicts and orphans.",
        "roles": "database-manager,data-analyst",
    },
    "documents": {
        "skill": "plugins/argo-project-manager/skills/new-study-documents/SKILL.md",
        "inputs": ["concept-note.md"],
        "prompt": "We're starting a new study — draft the study SOP and questionnaire proforma from this concept note.",
        "roles": "project-manager",
    },
    "export": {
        "skill": "plugins/argo-database-manager/skills/export-data/SKILL.md",
        "inputs": [],
        "prompt": "Export the CRC study — records and data dictionary — to disk.",
        "roles": "database-manager",
    },
    "weekly-check": {
        "skill": "plugins/argo-database-manager/skills/weekly-check/SKILL.md",
        "inputs": [],
        "prompt": "Run my weekly check.",
        "roles": "database-manager",
    },
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, choices=sorted(TASKS))
    ap.add_argument("--keys", action="store_true", help="copy ~/.argo/.env into the workspace")
    ap.add_argument("--name", help="run folder name (default: the task name)")
    a = ap.parse_args()
    spec = TASKS[a.task]
    run = RUNS / (a.name or a.task)
    if run.exists():
        shutil.rmtree(run)
    ws, up = run / "workspace", run / "uploads"
    up.mkdir(parents=True)
    env = dict(os.environ, ARGO_SETUP_NO_OPEN="1")
    subprocess.run([sys.executable, str(SETUP), "--dir", str(ws)], check=True, env=env,
                   capture_output=True)
    subprocess.run([sys.executable, str(SETUP), "--set-roles", spec["roles"], "--dir", str(ws)],
                   check=True, env=env, capture_output=True)
    if a.keys:
        src = Path.home() / ".argo" / ".env"
        # Merge only key lines the template already has blank; keep ARGO_ROLES/paths intact.
        keys = {l.split("=", 1)[0]: l.split("=", 1)[1] for l in src.read_text().splitlines()
                if "=" in l and not l.startswith("#") and l.split("=", 1)[1].strip()}
        lines = (ws / ".env").read_text().splitlines()
        seen = set()
        for i, l in enumerate(lines):
            k = l.split("=", 1)[0]
            if "=" in l and not l.startswith("#") and k in keys and not l.split("=", 1)[1].strip():
                lines[i] = f"{k}={keys[k]}"; seen.add(k)
        for k, v in keys.items():
            if k.endswith("_TOKEN") and k not in seen and not any(l.startswith(k + "=") for l in lines):
                lines.append(f"{k}={v}")
        (ws / ".env").write_text("\n".join(lines) + "\n"); (ws / ".env").chmod(0o600)
    for item in spec["inputs"]:
        s = KIT / item
        d = up / s.name
        shutil.copytree(s, d) if s.is_dir() else shutil.copy2(s, d)
    print(f"task:      {a.task}")
    print(f"skill:     {REPO / spec['skill']}")
    print(f"workspace: {ws}")
    print(f"uploads:   {up}  ({', '.join(spec['inputs']) or 'nothing'})")
    print(f"keys:      {'yes (from ~/.argo/.env)' if a.keys else 'none'}")
    print(f"\nopening message:\n    {spec['prompt']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
