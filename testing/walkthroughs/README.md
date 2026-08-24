# Tier 1.5 — skill walkthroughs by subagent (between the unit tests and the Cowork rounds)

A subagent plays the ASSISTANT: it reads a skill's SKILL.md from the repo tree (unreleased code),
receives the user's opening message, and follows the skill exactly, running the real scripts on
the retest kit. A second voice — the PERSONA in PERSONA.md — answers every question the skill
asks, the way a real ARGO team member would. Every question and answer is logged verbatim so a
human can judge afterwards whether the QUESTIONS were the right ones.

What it tests: routing, the ask-first choreography, script invocation, plain language, outputs
on disk — graded against testing/fixtures/*/MANIFEST.json where engineered truth exists.
What it cannot test (Cowork rounds stay for these): setup/onboarding, the file card and
widgets, sandbox PATH/mount quirks, Windows.

Inputs: ~/Desktop/ARGO-test-data/ (the dogfood kit, outside the workspace) — never the
fixtures dir directly, so the walkthrough sees files the way a user provides them.
Outputs: a scratch workspace per walkthrough (testing/walkthroughs/runs/<task>/, gitignored),
scaffolded with argo_setup.py so the role folders exist; no keys unless the task needs one
(then the developer's ~/.argo/.env is used, read-only operations only — never a write to a
real tracker record).

Protocol per task:
1. Fresh scratch workspace; copy the task's inputs from the kit into an `uploads/` folder
   (mirrors how Cowork exposes attachments).
2. Agent prompt = PERSONA.md + the skill path + the opening message + "when the skill would ask
   the user, answer as the persona and LOG `Q:`/`A:` verbatim; when the skill says stop/wait,
   say what you'd wait for and continue as if the user did it".
3. Agent returns: the Q/A log, every command it ran, files written, and its own claim of pass.
4. The orchestrator grades: outputs vs MANIFEST counts; transcript vs the round's pass criteria
   (testing/cowork/round.py ROLES + RUN-SHEET); any raw traceback or improvised client call
   = fail.
