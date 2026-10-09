#!/usr/bin/env python3
"""Find the moments in real ARGO sessions where the toolkit made someone work harder.

Cowork writes every desktop session to disk as `audit.jsonl`. The highest-value toolkit
findings so far all came from reading those afterwards — the Synoptic build gave nine, the
Cervical documents ten — and every one of them was a place where a real person with real stakes
pushed back. This finds those places mechanically so the reading is targeted, not archaeological.

    mine_sessions.py                    # new ARGO sessions since the last pass, with candidates
    mine_sessions.py --all              # ignore the watermark, sweep everything
    mine_sessions.py --session <id>     # one session's candidates
    mine_sessions.py --show <id> --turn 481 [--context 4]    # read around one candidate
    mine_sessions.py --mark <id> --nits 78-86                # record it as mined

It flags CANDIDATES, not findings. A candidate is a turn where the user corrected, repeated,
was confused, took over, or stated a rule — plus any tool error. Whether it is a toolkit defect,
a one-off, or the user simply changing their mind is a judgement made by reading it in context.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

STORE = Path.home() / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
REPO = Path(__file__).resolve().parents[3]
WATERMARK = REPO / "testing/cowork/mined-sessions.json"

# A session counts as ARGO if it ran the toolkit's own code. Matching on the word "ARGO" alone
# pulls in any chat that mentions the programme; these strings only appear when a skill ran.
ARGO_MARKERS = (
    "argo_redcap_client", "argo_setup.py", "sir_update.py", "portfolio.py", "validate_dd.py",
    "dd_builder.py", "build_worklists.py", "fetch_templates.py", "open_requests.py",
    "argo-database-manager", "argo-project-manager", "argo-qa-specialist", "argo-data-analyst",
    "ARGO toolkit",
)

# What a person says when a tool has just cost them something. Ordered most to least specific;
# a turn keeps every label that matches.
SIGNALS = [
    ("CORRECTION",  r"\b(wait|actually|no[,—–-]|that'?s (not|wrong)|isn'?t (right|correct)|"
                    r"(isn'?t|is not|aren'?t) (just|only) (a|an|the)|"      # "isn't just a checkbox"
                    r"you (need to|should have|didn'?t)|not what i|nope|incorrect)\b"),
    ("REPEAT",      r"\b(again|i already (said|told|asked)|as i said|like i said|"
                    r"you asked (me )?(that|this) (already|twice)|come on|second time)\b"),
    ("MISSING",     r"\b(aren'?t (present|there)|isn'?t (present|there)|(is|are) missing|"
                    r"where (is|are) the|you (didn'?t|never) (include|make|write|produce)|"
                    r"nothing (was|got)|not in one place)\b"),
    ("CONFUSED",    r"\b(i don'?t understand|confus|not sure what|what (is|does) (that|this)|"
                    r"unclear|makes no sense|why (is|are|did) (that|this|you))\b"),
    ("RULE",        r"\b(we (always|never|want to|need to)|per the|the rule is|"
                    r"you should (always|never)|going forward|from now on|"
                    r"that'?s not (how|what) we)\b"),
    ("TOOK-OVER",   r"\b(i (did|built|made|fixed|wrote) (it|them|these|all) (myself|already)|"
                    r"i'?ve (already|just) (done|built|made|fixed)|never mind,? i)\b"),
    ("STOPPED",     r"\b(stop|forget it|nevermind|never mind|let'?s (not|move on)|skip (it|this))\b"),
]
COMPILED = [(name, re.compile(rx, re.I)) for name, rx in SIGNALS]

# Short acknowledgements are not pushback. "No" answering a yes/no question is the common one.
NOISE = re.compile(r"^\s*(yes|no|ok(ay)?|sure|thanks?|got it|right|good|done|nice|perfect|"
                   r"continue|keep going|go ahead|sounds good)\b[\s.!,]*$", re.I)

# A skill's own SKILL.md arrives in the transcript as a user turn. It is full of the imperative
# voice these signals look for ("never", "don't", "stop") and matched four labels at once on the
# first run — the loudest candidate in the session was the toolkit quoting itself.
INJECTED = re.compile(r"^\s*(Base directory for this skill:|<(command-name|system-reminder|"
                      r"uploaded_files|local-command)|# [A-Za-z-]+\n)")


def is_injected(text: str) -> bool:
    if INJECTED.match(text):
        return True
    # Long, heavily-headed, and speaks in rules: documentation, not a person talking.
    return len(text) > 2500 and text.count("\n#") >= 2


def sessions() -> list:
    if not STORE.is_dir():
        return []
    # Cowork moved from `local_<uuid>/` to bare 8-hex folders around 2026-09-25; match both,
    # or every session after the change is silently invisible.
    return sorted((p for p in STORE.glob("*/*/*/audit.jsonl")),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def _text_blocks(message: dict) -> list:
    """(kind, text) for one message: kind is 'text', 'tool', or 'error'."""
    out = []
    content = message.get("content")
    if isinstance(content, str):
        return [("text", content)]
    for b in content or []:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text":
            out.append(("text", b.get("text", "")))
        elif t == "tool_use":
            inp = b.get("input", {})
            cmd = inp.get("command") or inp.get("file_path") or json.dumps(inp)[:200]
            out.append(("tool", f"{b.get('name')}: {cmd}"))
        elif t == "tool_result":
            c = b.get("content")
            s = c if isinstance(c, str) else json.dumps(c)
            out.append(("error" if b.get("is_error") else "result", s or ""))
    return out


def read_session(path: Path) -> dict:
    """Turns, plus the facts a triage needs: is it ARGO, which version, how long."""
    turns, raw_len = [], 0
    version = None
    argo = False
    last_user = None
    for line in path.read_text(errors="replace").splitlines():
        raw_len += len(line)
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not argo and any(m in line for m in ARGO_MARKERS):
            argo = True
        if version is None:
            # Setup prints the stamp; the init event lists each loaded plugin's version even
            # when setup never ran — without it most sessions read "no version stamp".
            m = (re.search(r"ARGO toolkit (\d+\.\d+\.\d+)", line)
                 or re.search(r'"name":\s*"argo-[a-z-]+"[^}]*?"version":\s*"(\d+\.\d+\.\d+)"', line))
            if m:
                version = m.group(1)
        kind = e.get("type")
        if kind not in ("user", "assistant"):
            continue
        for block_kind, text in _text_blocks(e.get("message") or e):
            text = (text or "").strip()
            if not text:
                continue
            # Cowork echoes each user message; collapse consecutive duplicates.
            if kind == "user" and block_kind == "text":
                if text == last_user:
                    continue
                last_user = text
            turns.append({"i": len(turns), "role": kind, "kind": block_kind, "text": text})
    return {"path": path, "id": path.parent.name, "turns": turns, "argo": argo,
            "version": version, "mtime": path.stat().st_mtime, "bytes": raw_len}


def candidates(session: dict) -> list:
    """Pushback first, then tool errors — they are read differently.

    A user turn is the high-value signal: someone with real stakes saying the tool cost them
    something. A tool error is cheaper: often environmental (a file outside the sandbox, a
    missing node module) and only interesting when it is the toolkit's own code failing.
    """
    pushback, errors = [], []
    for t in session["turns"]:
        if t["kind"] == "error":
            own = any(m in t["text"] for m in ARGO_MARKERS)
            errors.append({**t, "labels": ["TOOL-ERROR" + ("/ARGO" if own else "")], "own": own})
            continue
        if t["role"] != "user" or t["kind"] != "text":
            continue
        text = t["text"]
        if NOISE.match(text) or is_injected(text):
            continue
        labels = [name for name, rx in COMPILED if rx.search(text)]
        if labels:
            pushback.append({**t, "labels": labels})
    return pushback, errors


def load_watermark() -> dict:
    return json.loads(WATERMARK.read_text()) if WATERMARK.exists() else {}


def save_watermark(data: dict) -> None:
    WATERMARK.parent.mkdir(parents=True, exist_ok=True)
    WATERMARK.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


def one_line(text: str, width: int = 150) -> str:
    flat = " ".join(text.split())
    return flat[:width] + ("…" if len(flat) > width else "")


def digest(args) -> int:
    mined = load_watermark()
    paths = sessions()
    if args.session:
        paths = [p for p in paths if args.session in p.parent.name]
    shown = 0
    for path in paths:
        sid = path.parent.name
        if not args.all and not args.session and sid in mined:
            continue
        s = read_session(path)
        if not s["argo"]:
            continue
        pushback, errors = candidates(s)
        own_errors = [e for e in errors if e["own"]]
        shown += 1
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(s["mtime"]))
        status = "" if sid not in mined else f"  [mined {mined[sid].get('mined_at','?')[:10]}]"
        print(f"\n{'=' * 78}")
        print(f"{sid}  {when}  {len(s['turns'])} turns  "
              f"{'toolkit ' + s['version'] if s['version'] else 'no version stamp'}"
              f"  {s['bytes'] // 1024}K{status}")
        print("=" * 78)
        if not pushback and not own_errors:
            print("  (nothing flagged — skim it anyway if it was real work; a session that went "
                  "smoothly still shows what people actually ask for)")
        for c in pushback:
            print(f"\n  turn {c['i']:<5} {'+'.join(c['labels'])}")
            print(f"    {one_line(c['text'])}")
        if own_errors:
            print(f"\n  -- {len(own_errors)} error(s) in the toolkit's own code --")
            for c in own_errors:
                print(f"  turn {c['i']:<5} {one_line(c['text'], 120)}")
        if errors and not own_errors:
            print(f"\n  ({len(errors)} tool error(s), none in toolkit code — environmental)")
        if args.limit and shown >= args.limit:
            break
    if not shown:
        print("No new ARGO sessions since the last pass."
              if not args.all else "No ARGO sessions found.")
    else:
        print(f"\n{shown} session(s). Read a candidate in context:\n"
              f"  mine_sessions.py --show <session-id> --turn <n>")
    return 0


def show(args) -> int:
    paths = [p for p in sessions() if args.show in p.parent.name]
    if not paths:
        sys.exit(f"No session matching {args.show!r}")
    s = read_session(paths[0])
    lo = max(0, args.turn - args.context)
    hi = min(len(s["turns"]), args.turn + args.context + 1)
    for t in s["turns"][lo:hi]:
        marker = ">>" if t["i"] == args.turn else "  "
        head = f"{marker} [{t['i']}] {t['role'].upper()}"
        if t["kind"] in ("tool", "result", "error"):
            head += f" ({t['kind']})"
        print(f"\n{head}\n{t['text'][:args.chars]}")
    return 0


def mark(args) -> int:
    paths = [p for p in sessions() if args.mark in p.parent.name]
    if not paths:
        sys.exit(f"No session matching {args.mark!r}")
    sid = paths[0].parent.name
    mined = load_watermark()
    mined[sid] = {"mined_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                  "nits": args.nits or "", "note": args.note or ""}
    save_watermark(mined)
    print(f"marked {sid}" + (f" -> NITS {args.nits}" if args.nits else " (no findings)"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="ignore the watermark")
    ap.add_argument("--session", help="only this session id (substring)")
    ap.add_argument("--limit", type=int, default=0, help="stop after N sessions")
    ap.add_argument("--show", help="print turns around --turn in this session")
    ap.add_argument("--turn", type=int, default=0)
    ap.add_argument("--context", type=int, default=3)
    ap.add_argument("--chars", type=int, default=2000, help="max characters per turn when showing")
    ap.add_argument("--mark", help="record this session as mined")
    ap.add_argument("--nits", help="NITS numbers it produced, e.g. 78-86")
    ap.add_argument("--note", help="one line on what it was")
    args = ap.parse_args()
    if args.show:
        return show(args)
    if args.mark:
        return mark(args)
    return digest(args)


if __name__ == "__main__":
    sys.exit(main())
