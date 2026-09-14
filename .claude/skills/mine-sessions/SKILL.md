---
name: mine-sessions
description: Read Matteo's real ARGO Cowork sessions for places the toolkit made someone work harder, and turn those into fixes. Use when he says "mine my chats", "what did you find in my sessions", "check the recent ARGO work", after any real study build or PM session, or at the start of a working session to see what has accumulated. Produces NITS entries and, one at a time, the fixes they justify.
allowed-tools: Read, Bash, Edit, Write, Glob, Grep
---

# mine-sessions — real work is the test suite

Every high-value toolkit finding so far came from reading a session **after** real work, not from
a synthetic round. The Synoptic build gave nine (NITS 78–86); the Cervical documents gave ten
(60–69). Both times the signal was the same: a person with a week to lose pushing back on
something the toolkit did. This skill makes that reading routine instead of occasional.

The automated dogfood loop that used to live here was removed on 2026-09-14. It could only ever
find what the 725-test suite already covers — crashes, missing files, wrong folders. It could not
find *"you asked me that twice"* or *"per the SOP, this was already resolved"*, which is where
the real defects were. **Don't rebuild it.**

## Run it

```bash
python3 .claude/skills/mine-sessions/mine_sessions.py             # new ARGO sessions since last pass
python3 .claude/skills/mine-sessions/mine_sessions.py --all       # sweep everything
```

It prints one block per session: how long, which toolkit version, and the flagged turns.
**A flagged turn is a candidate, not a finding.** Read it in context before believing it:

```bash
python3 .claude/skills/mine-sessions/mine_sessions.py --show <session-id> --turn 468 --context 5
```

Widen `--context` until you can see what the assistant did just before the push-back and how it
responded after. That is where the defect is, not in the sentence itself.

The labels — `CORRECTION`, `REPEAT`, `MISSING`, `CONFUSED`, `RULE`, `TOOK-OVER`, `STOPPED`,
`TOOL-ERROR` — are a sorting aid. `REPEAT` and `RULE` are the richest: the first means the toolkit
wasted a question, the second means Matteo just stated a convention it should have known.

## Judging a candidate

Three things it can be. Decide which before writing anything down.

1. **A toolkit defect.** It would happen again, to anyone, on the next study. *This is the only
   kind that becomes a fix.* Test: could you write the rule that would have prevented it, in a
   sentence, without naming this study?
2. **The user changing their mind.** Real, reasonable, and not a defect. "Actually let's do it the
   other way" is not friction.
3. **A one-off.** A file in the wrong place, a flaky sandbox, a question that only made sense for
   this study. Note it if it might recur; don't fix it.

**Check the version stamp first.** A session on an old toolkit reproduces bugs already fixed.
If the header says `no version stamp`, the session never ran setup — the finding may still be
real, but you can't tell which version it is about.

**Log what went right, too.** NITS 78–86 ends with a "what went right — don't 'fix' these"
section, and it earns its place: the session refused to mark `review_pi` without sign-off,
refused to tick a PHI attestation, and diffed rather than asserted when challenged. Without that
note, a later pass reads the surrounding findings and "improves" the very behaviour that worked.

## Turning findings into fixes

**Write the NITS entries first**, all of them, before changing any code. `testing/cowork/NITS.md`,
numbered, one per finding, each carrying the quote that justifies it. The quote is what makes a
finding survive contact with a later disagreement.

Then fix, **one issue at a time**, and stop at anything that is a judgement call about data
semantics, study design, or a data-dictionary change — those are Matteo's, even in auto mode.
Ask him; don't decide. (See the memories: *Walk through decisions*, *Ask Matteo, not the PI*,
*Blanks stay blank*, *IRB minimal-change rule*.)

Two traps specific to this work:

- **A stated rule is often broader than the sentence.** *"Per the SOP, we need an email field and
  multiple survey instruments"* was one study's complaint; it turned out to be ARGO's general
  convention for every link-distributed survey, and it needed asking to find that out. When a
  finding could be a programme convention, ask whether it generalises before encoding it.
- **New doctrine usually contradicts old doctrine.** The survey convention required materialising
  per-round instruments, which Step 3 explicitly forbade. Reconcile in place, with the reason, or
  a session reads the older rule first and refuses the newer one. After layered edits to any
  SKILL.md, **read it whole**.

Then: `python3 release.py --bump minor` (the only release path; it refuses on a failing suite),
commit, push, and tell Matteo to refresh the org marketplace — a running Cowork chat keeps the
version it snapshotted at start.

## Close the loop

```bash
python3 .claude/skills/mine-sessions/mine_sessions.py --mark <session-id> --nits 78-86 \
    --note "Synoptic build, 4 REDCaps"
```

This writes `testing/cowork/mined-sessions.json`, which is both the watermark and the record of
which session produced which findings. Mark a session even when it produced nothing — otherwise
every pass re-reads it.

## What to expect

Most sessions yield nothing, and that is the correct outcome. The two that yielded nineteen
findings between them were both **long sessions of real work under time pressure** — a four-REDCap
build, a full document package. Skim the quiet ones for what people actually ask for; read the
long ones properly.

## See also

- `testing/cowork/NITS.md` — the ranked defect ledger, where findings land
- `LEDGER.md` — what is done and what is outstanding
- `CLAUDE.md` — release discipline, and the process rules each finding paid for
