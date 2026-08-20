#!/usr/bin/env python3
"""The Cowork test loop: reset the workspace, hand over one prompt, mine the session afterwards.

Cowork desktop sessions leave a full transcript (audit.jsonl) and their deliverables (outputs/)
under ~/Library/Application Support/Claude/local-agent-mode-sessions/ on this Mac. That makes an
iterative test loop possible with exactly one human step per round — opening a fresh session and
pasting the canned prompt. Everything else is scripted:

    python3 round.py prepare --role onboarding   # reset workspace, snapshot state, print prompt
    ... human: fresh Cowork chat, connect ~/Desktop/ARGO-cowork, paste the prompt, let it run ...
    python3 round.py collect                     # mine the new session into a round report

Roles: onboarding, analyst, qa, builder, pm — each resets the workspace to a different starting
state (onboarding gets a bare folder; the rest get the baseline .env and role fixtures).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

WORKSPACE = Path.home() / "Desktop" / "ARGO-cowork"
ROUNDS = Path.home() / "Desktop" / "ARGO-cowork-rounds"   # reports + baseline, OUTSIDE the workspace
# The baseline holds REAL KEYS — it must never live inside the connected workspace,
# because a connected folder is readable in full by every session. Round 1 proved it:
# the session found .baseline/env-with-keys and helpfully merged the keys in.
BASELINE = ROUNDS / "baseline"
STORE = Path.home() / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
STATE = BASELINE / "round-state.json"

ROLES = {
    "onboarding": {
        "env": False, "fixtures": [],
        "prompt": "help me get started with ARGO",
        "expect": [
            "argo front-door skill fires (standalone or start-here)",
            "setup scaffolds INTO the connected folder (not the sandbox home)",
            ".env created with the ARGO REDCap URL pre-filled",
            "asks at most ONE question; no menu of options",
            "if keys are configured, verifies them up front and folds status into the one-liner",
            "never asks for a key to be pasted into the chat",
        ],
    },
    "returning": {
        "env": True, "fixtures": [],
        "prompt": "help me with ARGO",
        "expect": [
            "one-liner INCLUDES key status: 'your five tracker keys connect'",
            "NO 'add my access keys' option — keys exist and verified",
            "toolkit version visible in the --ensure/--check output",
            "then the routing question, nothing else",
        ],
    },
    "analyst": {
        "env": True, "fixtures": ["records", "dd"],
        "prompt": ("I'm the ARGO analyst. There's a CRC export and its data dictionary in my "
                   "connected folder — make me a Table 1 of the demographics from it, saved "
                   "into the analysis folder."),
        "expect": [
            "routes to run-analysis; never asks for a token",
            "finds both CSVs in the connected folder on its own",
            "produces a saved, commented script + Table 1 in analysis/",
            "no patient-level data pasted into the chat",
        ],
    },
    "qa": {
        "env": True, "fixtures": ["records", "dd", "qa_fields.yaml"],
        "prompt": ("I'm doing QA for the CRC study. Using the export, data dictionary and "
                   "qa_fields.yaml in my connected folder, build the per-site RA worklists."),
        "expect": [
            "routes to redcap-qa, uses the no-token --records-csv/--metadata-csv path",
            "worklists written under worklists/, split by DAG",
            "yellow = confirmed gap; amber only if a condition couldn't be read",
            "unparseable branching conditions listed at the end, if any",
        ],
    },
    "builder": {
        "env": True, "fixtures": ["concept-note-toy.md"],
        "prompt": ("A new study concept note is in my connected folder — draft the study SOP "
                   "and the questionnaire proforma from it as Word documents, into builds/."),
        "expect": [
            "routes to study-setup; mines the concept note instead of interviewing",
            "unknown facts become [TODO], never invented",
            "notes it's using markdown skeletons unless official templates are reachable",
            "real .docx files land in builds/",
        ],
    },
    "pm": {
        "env": True, "fixtures": [],
        "prompt": ("I'm the ARGO program manager. Give me the weekly portfolio update across "
                   "the admin trackers."),
        "expect": [
            "routes to study-portfolio; finds the .env in the connected folder",
            "if the sandbox has network: dashboard for all 5 trackers, keys never printed",
            "if egress is blocked: says it's an org restriction, NOT a bad key",
            "snapshot lands in the workspace or names where it went",
        ],
    },
}


def known_sessions() -> set:
    if not STORE.is_dir():
        return set()
    return {str(p) for p in STORE.glob("*/*/local_*") if p.is_dir()}


def prepare(role: str) -> int:
    spec = ROLES[role]
    if not BASELINE.is_dir():
        sys.exit(f"No baseline at {BASELINE} — stage it first (env-with-keys + fixtures/).")

    # Reset: the workspace is wiped completely — the baseline lives outside it.
    WORKSPACE.mkdir(exist_ok=True)
    for item in WORKSPACE.iterdir():
        shutil.rmtree(item) if item.is_dir() else item.unlink()

    staged = []
    if spec["env"]:
        env = WORKSPACE / ".env"
        env.write_bytes((BASELINE / "env-with-keys").read_bytes())
        env.chmod(0o600)
        staged.append(".env (baseline keys)")
    fixtures = BASELINE / "fixtures"
    for want in spec["fixtures"]:
        for f in fixtures.iterdir():
            name = f.name.lower()
            if (want == "records" and "records" in name) or \
               (want == "dd" and "datadictionary" in name) or \
               (want == name) or (want == f.name):
                dest = WORKSPACE / "exports" / f.name if want in ("records", "dd") else WORKSPACE / f.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                staged.append(str(dest.relative_to(WORKSPACE)))

    prior = json.loads(STATE.read_text()) if STATE.exists() else {}
    n = prior.get("round", 0) + 1
    STATE.write_text(json.dumps({
        "round": n, "role": role, "prepared_at": time.time(),
        "sessions_before": sorted(known_sessions()),
    }, indent=2))

    print(f"Round {n} ({role}) — workspace reset.")
    print(f"  staged: {', '.join(staged) if staged else 'nothing (bare folder, by design)'}")
    print("\nNow, in Cowork: NEW chat (not inside a Project), connect ~/Desktop/ARGO-cowork,")
    print("and paste exactly this prompt:\n")
    print(f"    {spec['prompt']}\n")
    print("When it finishes: python3 round.py collect")
    return 0


def _narrate(audit_path: Path, out) -> None:
    """Chronological digest of one session transcript."""
    for line in audit_path.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = e.get("type")
        msg = e.get("message") or {}
        if t == "system" and e.get("subtype") == "init":
            plugins = e.get("plugins") or []
            out.write(f"\n**session init** — model {e.get('model')}, "
                      f"plugins: {json.dumps(plugins)[:400]}\n\n")
        elif t == "user":
            content = msg.get("content")
            if isinstance(content, str):
                out.write(f"**USER:** {content[:600]}\n\n")
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result" and block.get("is_error"):
                        out.write(f"  TOOL ERROR: {str(block.get('content'))[:400]}\n")
        elif t == "assistant":
            for block in (msg.get("content") or []):
                if block.get("type") == "text" and block.get("text", "").strip():
                    out.write(f"ASSISTANT: {block['text'][:800]}\n\n")
                elif block.get("type") == "tool_use":
                    cmd = block.get("input", {}).get("command") or json.dumps(block.get("input", {}))[:200]
                    out.write(f"  -> {block.get('name')}: {str(cmd)[:300]}\n")
        elif t == "result":
            out.write(f"\n**RESULT** — turns {e.get('num_turns')}, "
                      f"errors: {e.get('is_error')}, denials: {e.get('permission_denials')}\n")


def collect() -> int:
    if not STATE.exists():
        sys.exit("No round in progress — run prepare first.")
    state = json.loads(STATE.read_text())
    new = sorted(known_sessions() - set(state["sessions_before"]))
    n, role = state["round"], state["role"]
    dest = ROUNDS / f"round-{n:02d}-{role}"
    dest.mkdir(parents=True, exist_ok=True)

    report = dest / "report.md"
    with open(report, "w") as out:
        out.write(f"# Round {n} — {role}\n\nPrompt given:\n> {ROLES[role]['prompt']}\n\n")
        out.write("## Expected\n" + "".join(f"- [ ] {x}\n" for x in ROLES[role]["expect"]))

        out.write("\n## Workspace after the session\n```\n")
        for p in sorted(WORKSPACE.rglob("*")):
            if ".baseline" in p.parts or not p.is_file():
                continue
            out.write(f"{p.relative_to(WORKSPACE)}  ({p.stat().st_size:,} B)\n")
        out.write("```\n")

        if not new:
            out.write("\n## Sessions\nNO new Cowork session found — was the round actually run?\n")
        for s in new:
            s = Path(s)
            out.write(f"\n## Session {s.name}\n")
            audit = s / "audit.jsonl"
            if audit.exists():
                _narrate(audit, out)
                shutil.copy2(audit, dest / f"{s.name}-audit.jsonl")
            outputs = s / "outputs"
            if outputs.is_dir() and any(outputs.iterdir()):
                shutil.copytree(outputs, dest / f"{s.name}-outputs", dirs_exist_ok=True)
                out.write(f"\noutputs copied: {[f.name for f in outputs.iterdir()]}\n")

    print(f"Round {n} ({role}) collected -> {report}")
    print(f"  new sessions found: {len(new)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="reset the workspace for a role and print the prompt")
    p.add_argument("--role", required=True, choices=sorted(ROLES))
    sub.add_parser("collect", help="mine the newest Cowork session into a round report")
    args = ap.parse_args()
    return prepare(args.role) if args.cmd == "prepare" else collect()


if __name__ == "__main__":
    sys.exit(main())
