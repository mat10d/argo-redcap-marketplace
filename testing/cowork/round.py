#!/usr/bin/env python3
"""The Cowork dogfood loop: a driver plays the user, the toolkit runs against a mock REDCap,
and the transcript is graded afterwards. Nothing in it can reach a real REDCap.

    python3 round.py list                      # every round, one line each
    python3 round.py setup <round>             # reset the TEST workspace, stage the round, print the card
    ... the driver runs the round in a FRESH Cowork chat on ~/Desktop/ARGO-cowork-test ...
    python3 round.py grade <round>             # mine the new session, check expectations, verdict
    python3 round.py reset                     # wipe the test workspace

Rounds live in rounds/<id>.json — prompt, persona, files to stage, expectations. The driver's
brief is DRIVER.md; the operator loop is LOOP.md.

The workspace is ~/Desktop/ARGO-cowork-test — a folder that exists for this and nothing else.
Its settings file points REDCAP_URL at an address that cannot resolve (`.invalid`) and names
a mock folder inside the workspace that answers every request from the synthetic fixtures.
Reports go to ~/Desktop/ARGO-cowork-test-rounds, outside the workspace.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ROUNDS_DIR = HERE / "rounds"
FIXTURES = REPO / "testing/fixtures"
KIT = Path.home() / "Desktop" / "ARGO-test-data"
WORKSPACE = Path.home() / "Desktop" / "ARGO-cowork-test"
REPORTS = Path.home() / "Desktop" / "ARGO-cowork-test-rounds"
STATE = REPORTS / "state.json"
STORE = Path.home() / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
DEFAULT_FILES_ROOT = Path.home() / "Desktop" / "ARGO-templates-work"
MOCK_DIRNAME = ".mock-redcap"
MOCK_URL = "https://mock.argo.invalid/api/"

sys.path.insert(0, str(REPO / "plugins/argo-core/skills/redcap-api/scripts"))
sys.path.insert(0, str(HERE))
from argo_trackers import ARGO_REDCAP_URL  # noqa: E402

# The real instance's host. It never appears in a test workspace's settings file, so if it
# shows up in a transcript or a script's output, a REAL settings file was loaded — the session
# reached the real REDCap. That is the one thing this loop exists to make impossible, so it is
# a red alert, not a failed check.
REAL_HOST = ARGO_REDCAP_URL.split("//", 1)[-1].split("/", 1)[0]


def real_host_seen(text: str) -> bool:
    return REAL_HOST.lower() in (text or "").lower()


# ---------------------------------------------------------------------------- rounds

def load_round(rid: str) -> dict:
    path = ROUNDS_DIR / f"{rid}.json"
    if not path.exists():
        sys.exit(f"No round called {rid!r}. Try: python3 round.py list")
    spec = json.loads(path.read_text())
    spec["id"] = rid
    return spec


def all_rounds() -> list:
    return [json.loads(p.read_text()) | {"id": p.stem} for p in sorted(ROUNDS_DIR.glob("*.json"))]


def known_sessions() -> set:
    return {str(p) for p in STORE.glob("*/*/local_*") if p.is_dir()} if STORE.is_dir() else set()


# ---------------------------------------------------------------------------- setup

def _resolve_source(ref: str) -> Path:
    """'kit:qa-returns/returned' -> ~/Desktop/ARGO-test-data/...; 'fx:synthetic-study/records.csv'
    -> testing/fixtures/...; anything else is a path."""
    if ref.startswith("kit:"):
        return KIT / ref[4:]
    if ref.startswith("fx:"):
        return FIXTURES / ref[3:]
    return Path(ref).expanduser()


def _rewrite_env(env_path: Path, values: dict, comment_out: "list[str]" = ()) -> None:
    """Set KEY=VALUE lines in the scaffolded settings file, keeping everything else."""
    lines = env_path.read_text().splitlines()
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip().lstrip("#").strip()
        if key in values and (line.startswith(key) or line.startswith(f"# {key}") or line.startswith(f"#{key}")):
            out.append(f"{key}={values[key]}"); seen.add(key)
        elif key in comment_out and line.startswith(key):
            out.append(f"# {line}")
        else:
            out.append(line)
    for key, value in values.items():
        if key not in seen:
            out.append(f"{key}={value}")
    env_path.write_text("\n".join(out) + "\n")
    env_path.chmod(0o600)


def setup(rid: str, files_root: "str | None", no_templates: bool) -> int:
    spec = load_round(rid)
    import argo_setup            # the real scaffold: role folders, settings file, 'Add keys here'
    import mock_redcap

    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    WORKSPACE.mkdir(parents=True)
    env_path = argo_setup.scaffold(WORKSPACE)
    if env_path is None:
        sys.exit("scaffold failed")

    root = None
    if spec.get("files_root", True) and not no_templates:
        cand = Path(files_root).expanduser() if files_root else DEFAULT_FILES_ROOT
        root = cand if cand.is_dir() else None
    info = mock_redcap.build(WORKSPACE / MOCK_DIRNAME, root, study_key=bool(spec.get("study_key")))
    (WORKSPACE / MOCK_DIRNAME / "config.json").write_text(json.dumps(
        {"apply_writes": False, "simulate_egress_block": False, **spec.get("config", {})}, indent=1))

    values = {"REDCAP_URL": MOCK_URL, "ARGO_ROLES": spec.get("roles", ""),
              "ARGO_REDCAP_MOCK": MOCK_DIRNAME, **info["env"]}
    _rewrite_env(env_path, values)

    staged = []
    for item in spec.get("stage", []):
        src = _resolve_source(item["from"])
        dest = WORKSPACE / item["to"]
        if not src.exists():
            print(f"  !! missing fixture {src} — round may not be runnable", file=sys.stderr)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)
        staged.append(item["to"])

    REPORTS.mkdir(parents=True, exist_ok=True)
    prior = json.loads(STATE.read_text()) if STATE.exists() else {}
    n = prior.get("n", 0) + 1
    STATE.write_text(json.dumps({"n": n, "round": rid, "prepared_at": time.time(),
                                 "sessions_before": sorted(known_sessions()),
                                 "study_token": info["study_token"]}, indent=1))

    card = render_card(spec, info, staged, root is not None, n)
    (REPORTS / "CARD.md").write_text(card)
    print(card)
    print(f"\n[card also written to {REPORTS / 'CARD.md'}]")
    return 0


def render_card(spec: dict, info: dict, staged: list, templates: bool, n: int) -> str:
    p = spec["persona"]
    L = [f"# ROUND {n} — {spec['id']}: {spec['title']}", ""]
    L += ["## Where you are",
          f"A FRESH Cowork chat (not inside a Project), with the folder `{WORKSPACE}` connected.",
          "Setup is already done — the settings file and your role are in place. Do not run setup.", ""]
    L += ["## Who you are", f"**{p['role']}.** {p.get('bio', '')}".strip(), ""]
    if p.get("facts"):
        L += ["## What you know (answer from this; do not invent beyond it)"]
        L += [f"- **{k}:** {v}" for k, v in p["facts"].items()]
        L += [""]
    if staged:
        L += ["## Files already in your folder", *[f"- `{s}`" for s in staged],
              "When the assistant needs them, say where they are (or drag them in if the round says drag).", ""]
    L += ["## Your first message — paste exactly", "", f"    {spec['prompt']}", ""]
    if p.get("answers"):
        L += ["## When it asks you something"]
        L += [f"- If it asks {a['if_asked']} → say: *{a['say']}*" for a in p["answers"]]
        L += ["- Anything else → answer as this person plausibly would, and note it as an IMPROVISATION in your report.", ""]
    if spec.get("driver_notes"):
        L += ["## Round-specific instructions", *[f"- {x}" for x in spec["driver_notes"]], ""]
    if spec.get("study_key") is False and spec.get("reveal_study_token"):
        L += ["## If it asks you to add your study key",
              "Open `Add keys here.command` in the folder (double-click), find the line `# CRC_TOKEN=`,",
              f"replace it with exactly `CRC_TOKEN={info['study_token']}`, save, close, then tell the chat you're done.",
              "(This is a synthetic key that opens a synthetic project — it is safe to type.)", ""]
    L += ["## Stop when", f"- {p.get('stop_when', 'the task is delivered and nothing is being asked of you')}",
          "- OR the assistant is stuck, looping, or has asked the same thing twice → stop early and say so",
          "- OR 25 exchanges have passed", ""]
    L += ["## Then type this as your LAST message (the transcript captures it)", "",
          "    DRIVER REPORT", "    outcome: DELIVERED | PARTIAL | STUCK",
          "    problems:", "      - [BLOCKER|WRONG|FRICTION] what happened, quoting the assistant where useful",
          "    improvisations:", "      - what you answered that wasn't on your sheet",
          "    would-a-real-user-notice: one sentence", ""]
    L += ["## Mock REDCap is on", f"The address in the settings file cannot reach a real server. Templates served: {'yes' if templates else 'no (fallback to skeletons expected)'}."]
    return "\n".join(L)


# ---------------------------------------------------------------------------- grade

def _narrate(audit_path: Path, out) -> tuple:
    """Chronological digest; returns (assistant_text, user_text, full_text, version)."""
    assistant, user, full = [], [], []
    version = None
    for line in audit_path.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        full.append(line)
        t = e.get("type"); msg = e.get("message") or {}
        if t == "user":
            content = msg.get("content")
            if isinstance(content, str):
                user.append(content); out.write(f"**USER:** {content[:700]}\n\n")
            elif isinstance(content, list):
                for b in content:
                    if b.get("type") == "text":
                        user.append(b.get("text", "")); out.write(f"**USER:** {b.get('text','')[:700]}\n\n")
                    elif b.get("type") == "tool_result":
                        s = b.get("content"); s = s if isinstance(s, str) else json.dumps(s)
                        m = re.search(r"ARGO toolkit (\d+\.\d+\.\d+)", s or "")
                        if m: version = m.group(1)
                        if b.get("is_error"): out.write(f"  TOOL ERROR: {str(s)[:300]}\n")
        elif t == "assistant":
            for b in (msg.get("content") or []):
                if b.get("type") == "text" and b.get("text", "").strip():
                    assistant.append(b["text"]); out.write(f"ASSISTANT: {b['text'][:900]}\n\n")
                elif b.get("type") == "tool_use":
                    cmd = b.get("input", {}).get("command") or json.dumps(b.get("input", {}))[:200]
                    out.write(f"  -> {b.get('name')}: {str(cmd)[:240]}\n")
        elif t == "result":
            out.write(f"\n**RESULT** — turns {e.get('num_turns')}, errors: {e.get('is_error')}\n")
    return "\n".join(assistant), "\n".join(user), "\n".join(full), version


def _driver_report(user_text: str) -> str:
    i = user_text.rfind("DRIVER REPORT")
    return user_text[i:].strip() if i >= 0 else ""


def _jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def grade(rid: str, audit_override: "Path | None" = None, workspace: "Path | None" = None,
          reports: "Path | None" = None) -> int:
    """Grade the newest session(s) since setup. `audit_override` grades one transcript file
    instead — how the grader itself is tested, with no Cowork involved."""
    global WORKSPACE, REPORTS, STATE
    if workspace:
        WORKSPACE = Path(workspace)
    if reports:
        REPORTS = Path(reports); STATE = REPORTS / "state.json"
    spec = load_round(rid)
    if audit_override:
        state = {"n": 0, "round": rid, "sessions_before": []}
        new = [str(Path(audit_override).parent)]
    else:
        if not STATE.exists():
            sys.exit("No round set up — run setup first.")
        state = json.loads(STATE.read_text())
        if state.get("round") != rid:
            print(f"  note: state says the round set up was {state.get('round')!r}, grading {rid!r} anyway")
        new = sorted(known_sessions() - set(state["sessions_before"]))
    n = state["n"]
    dest = REPORTS / f"{n:03d}-{rid}"
    dest.mkdir(parents=True, exist_ok=True)
    exp = spec.get("expect", {})
    mock_dir = WORKSPACE / MOCK_DIRNAME
    keys = json.loads((mock_dir / "keys.json").read_text()) if (mock_dir / "keys.json").exists() else {}
    calls = _jsonl(mock_dir / "CALLS.jsonl")
    writes = _jsonl(mock_dir / "WRITES.jsonl")

    checks: list = []          # (ok: bool|None, label, detail)
    def check(ok, label, detail=""):
        checks.append((ok, label, detail))

    assistant = user = full = ""; version = None
    with open(dest / "report.md", "w") as out:
        out.write(f"# Round {n} — {rid}: {spec['title']}\n\nPrompt:\n> {spec['prompt']}\n\n")
        if not new:
            out.write("## NO new Cowork session found — was the round run?\n")
        for s in new:
            s = Path(s); audit = Path(audit_override) if audit_override else s / "audit.jsonl"
            out.write(f"\n## Session {s.name}\n\n")
            if audit.exists():
                a, u, f, v = _narrate(audit, out)
                assistant += a; user += u; full += f; version = version or v
                shutil.copy2(audit, dest / f"{s.name}-audit.jsonl")
            outputs = s / "outputs"
            if outputs.is_dir() and any(outputs.iterdir()):
                shutil.copytree(outputs, dest / f"{s.name}-outputs", dirs_exist_ok=True)

        # ---- the checks
        check(bool(new), "a new session was recorded", f"{len(new)} found")
        check(version is not None, "toolkit version stamp seen", version or "none — stale session or setup skipped?")
        # The canaries. Either one failing means the boundary did not hold — stop and find out why
        # before running anything else.
        check(not real_host_seen(full), f"!! REAL REDCAP ADDRESS NEVER SEEN ({REAL_HOST})",
              "the session loaded a REAL settings file — the mock was bypassed")
        touches_redcap = bool(exp.get("calls", {}).get("must")) or bool(exp.get("writes", {}).get("allow"))
        if touches_redcap:
            check(bool(calls), "!! MOCK WAS ACTIVE (CALLS.jsonl non-empty)",
                  "no calls reached the mock — if the task ran, it ran against something else")
        for token in keys:
            check(token not in full, "no synthetic key leaked into the transcript", f"…{token[-4:]}")
        for rx in exp.get("must_say", []):
            check(bool(re.search(rx, assistant, re.I | re.S)), f"says: /{rx}/")
        for rx in exp.get("must_not_say", []):
            m = re.search(rx, assistant, re.I | re.S)
            check(m is None, f"never says: /{rx}/", m.group(0)[:80] if m else "")
        present = [str(p.relative_to(WORKSPACE)) for p in WORKSPACE.rglob("*") if p.is_file()
                   and MOCK_DIRNAME not in p.parts]
        for g in exp.get("files", []):
            hits = fnmatch.filter(present, g)
            check(bool(hits), f"file exists: {g}", ", ".join(hits[:3]))
        for g in exp.get("no_files", []):
            hits = fnmatch.filter(present, g)
            check(not hits, f"no file: {g}", ", ".join(hits[:3]))
        called = {c.get("project") for c in calls}
        for p in exp.get("calls", {}).get("must", []):
            check(p in called, f"REDCap called: {p}")
        for p in exp.get("calls", {}).get("never", []):
            check(p not in called, f"REDCap never called: {p}", f"called {len([c for c in calls if c.get('project')==p])}×")
        allow = exp.get("writes", {}).get("allow", [])
        if not allow:
            check(not writes, "no writes reached the mock", f"{len(writes)} write(s)")
        else:
            for rule in allow:
                got = [w for w in writes if w.get("project") == rule["project"]
                       and w.get("content") == rule.get("content", w.get("content"))]
                ok = 1 <= len(got) <= rule.get("max", 1) if rule.get("required", True) else len(got) <= rule.get("max", 1)
                check(ok, f"writes to {rule['project']}/{rule.get('content','*')} within [{1 if rule.get('required', True) else 0}, {rule.get('max',1)}]", f"{len(got)}")
            stray = [w for w in writes if not any(w.get("project") == r["project"] for r in allow)]
            check(not stray, "no writes outside the allowed list", f"{len(stray)} stray")
        report = _driver_report(user)
        check(bool(report), "driver report present")
        if report:
            m = re.search(r"outcome:\s*(\w+)", report)
            check(bool(m) and m.group(1).upper() == "DELIVERED", "driver outcome DELIVERED", m.group(1) if m else "no outcome line")
            check("BLOCKER" not in report, "driver reported no BLOCKER")

        failed = [c for c in checks if c[0] is False]
        out.write("\n## Checks\n\n")
        for ok, label, detail in checks:
            mark = "PASS" if ok else "FAIL"
            out.write(f"- [{mark}] {label}" + (f" — {detail}" if detail else "") + "\n")
        out.write(f"\n## Verdict: {'PASS' if not failed else 'FAIL'} ({len(checks) - len(failed)}/{len(checks)})\n")
        if report:
            out.write("\n## Driver report\n\n```\n" + report + "\n```\n")
        if writes:
            out.write("\n## Writes the mock received\n\n```\n" + "\n".join(json.dumps(w)[:400] for w in writes) + "\n```\n")
        out.write("\n## REDCap calls\n\n```\n" + "\n".join(
            f"{c.get('project')}  {c.get('content')}/{c.get('action') or '-'}  {'WRITE' if c.get('is_write') else ''}" for c in calls) + "\n```\n")

    (dest / "verdict.json").write_text(json.dumps(
        {"round": rid, "n": n, "pass": not failed, "version": version,
         "checks": [{"ok": ok, "label": l, "detail": d} for ok, l, d in checks]}, indent=1))
    for snap in (mock_dir / "CALLS.jsonl", mock_dir / "WRITES.jsonl"):
        if snap.exists():
            shutil.copy2(snap, dest / snap.name)

    print(f"Round {n} ({rid}): {'PASS' if not failed else 'FAIL'} — {len(checks) - len(failed)}/{len(checks)} checks"
          + (f", toolkit {version}" if version else ", NO VERSION STAMP"))
    for ok, label, detail in checks:
        if ok is False:
            print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))
    print(f"  report: {dest / 'report.md'}")
    return 0 if not failed else 1


# ---------------------------------------------------------------------------- smoke

SMOKE = [
    ("--check", "plugins/argo-core/skills/redcap-api/scripts/argo_redcap_client.py", ["--check"]),
    ("weekly portfolio", "plugins/argo-database-manager/skills/weekly-check/portfolio.py", ["--diff"]),
    ("open queues", "plugins/argo-core/skills/redcap-api/scripts/open_requests.py", []),
    ("SIR pull", "plugins/argo-database-manager/skills/build-study/sir_update.py", ["1", "--pull"]),
    ("templates", "plugins/argo-project-manager/skills/new-study-documents/fetch_templates.py",
     ["--to", "project-manager/templates-official"]),
]


def smoke() -> int:
    """Run the real scripts against the test workspace's mock, from this Mac, safely.

    On a Mac the settings search finds ~/.argo/.env — the REAL keys — before the working
    directory, so running a script from inside the test folder silently uses the real REDCap.
    (That is exactly what happened the first time this loop was smoke-tested, 2026-09-09: every
    call read the live instance.) ARGO_ENV_FILE is the explicit override that puts one file first
    in the search; this verb sets it and refuses to continue if the mock still isn't the thing
    answering. Inside Cowork the problem doesn't arise — the sandbox has no ~/.argo/.env — but
    the grader's canary checks that every round, rather than trusting it.
    """
    import os
    import subprocess
    env_path = WORKSPACE / ".env"
    if not env_path.exists():
        sys.exit("No test workspace — run setup <round> first.")
    if MOCK_URL.split("//")[1].split("/")[0] not in env_path.read_text():
        sys.exit("The test workspace's .env does not point at the mock address — refusing.")
    env = {**os.environ, "ARGO_ENV_FILE": str(env_path)}
    for k in list(env):
        if k.endswith("_TOKEN") or k in ("REDCAP_URL", "STUDY_INITIATION_REQUEST", "STUDY_PERSONELL_REQUEST",
                                          "DATA_LINKING_REQUEST", "DATA_REQUEST", "SUPPORT_TICKET_REQUEST"):
            env.pop(k, None)          # nothing inherited from this shell may outrank the file
    mock_dir = WORKSPACE / MOCK_DIRNAME
    failures = 0
    steps = list(SMOKE)
    if re.search(r"^CRC_TOKEN=\S", env_path.read_text(), re.M):
        steps.append(("study export", "plugins/argo-database-manager/skills/export-data/export.py",
                      ["--token-env", "CRC_TOKEN", "--out", "database-manager/exports/syn"]))
    templates_served = any((mock_dir / "projects/study_tracker/files").glob("*"))
    for label, rel, args in steps:
        r = subprocess.run([sys.executable, str(REPO / rel), *args], cwd=WORKSPACE, env=env,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr)
        if real_host_seen(out):
            print(f"!! {label}: REAL REDCAP ADDRESS in output — ABORTING. Wipe the workspace (round.py reset).")
            return 3
        ok = r.returncode == 0
        if label == "templates" and not templates_served and "no folder called 'ARGO Templates'" in out:
            ok = True   # the round served an empty File Repository on purpose; saying so is the pass
        failures += 0 if ok else 1
        tail = out.strip().splitlines()[-1][:100] if out.strip() else ""
        print(f"  {'ok  ' if ok else 'FAIL'} {label:<18} {tail}")
    if any(l == "study export" for l, _, _ in steps):
        got = sorted(p.name for p in (WORKSPACE / "database-manager/exports/syn").glob("*")) \
            if (WORKSPACE / "database-manager/exports/syn").is_dir() else []
        print(f"  export wrote {len(got)} file(s): {', '.join(got)[:200]}")
    calls = _jsonl(mock_dir / "CALLS.jsonl")
    writes = _jsonl(mock_dir / "WRITES.jsonl")
    projects = sorted({c.get("project") or "?" for c in calls})
    print(f"\n  mock answered {len(calls)} call(s) across {projects}; {len(writes)} write(s) logged")
    if not calls:
        print("!! the mock answered NOTHING — the scripts did not use the test settings file")
        return 3
    return 1 if failures else 0


# ---------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("setup"); p.add_argument("round")
    p.add_argument("--files-root", help=f"official templates to serve (default {DEFAULT_FILES_ROOT} if present)")
    p.add_argument("--no-templates", action="store_true", help="serve an empty File Repository")
    p = sub.add_parser("grade"); p.add_argument("round")
    p.add_argument("--audit", help="grade this transcript file instead of the newest session")
    sub.add_parser("smoke", help="run the real scripts against the mock from this Mac, safely")
    sub.add_parser("reset")
    a = ap.parse_args()
    if a.cmd == "smoke":
        return smoke()
    if a.cmd == "list":
        for r in all_rounds():
            print(f"{r['id']:<18} {r['title']}")
        return 0
    if a.cmd == "setup":
        return setup(a.round, a.files_root, a.no_templates)
    if a.cmd == "grade":
        return grade(a.round, Path(a.audit) if a.audit else None)
    if a.cmd == "reset":
        if WORKSPACE.exists():
            shutil.rmtree(WORKSPACE)
        print(f"wiped {WORKSPACE}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
