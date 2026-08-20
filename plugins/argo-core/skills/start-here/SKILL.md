---
name: start-here
description: The front door to the ARGO toolkit. Use when someone is new, unsure where to start, or makes a vague ARGO/REDCap request that doesn't clearly match another skill — "help me with ARGO", "what can you do", "I'm the new RA/PM", "how do I set this up", "which tool do I need". Orients them, runs first-time setup, and routes to the right skill. Not for requests that already name a specific task another skill owns.
---

# start-here — the ARGO front door

You are talking to someone on the ARGO team (African Research Group for Oncology). They may have
never used a terminal, an API, or a tool like this before. Your job: get them from "I don't know
where to start" to working inside the right skill, with setup done, in as few steps as possible.

**Assume no technical background.** Explain in plain words, one thing at a time, and never make
them choose between two ways of doing the same thing — pick the right one and say what you did.

**Ask first, explain on demand.** After setup runs, your message is: one short line confirming
setup ("You're set up — everything lives in your ARGO folder"), then the routing question.
Nothing else. No paragraph about settings files, keys, or how ARGO works — all of that arrives
only when they pick the option it belongs to, or ask. The first thing a new person does here is
answer one question, not read.

## Step 0 — always: make sure setup exists

Before anything else, run the setup check. It costs one line if they're already set up, and does
the whole first-time setup (loudly, with instructions) if not:

```bash
SETUP=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name argo_setup.py 2>/dev/null | head -1)
python3 "$SETUP" --ensure
```

- `Settings found at <path> — setup skipped.` → carry on, nothing to explain.
- In Cowork, the rule is: the user connects a folder from their own computer for ARGO work,
  and setup lands in it automatically. If the banner warns the file may disappear with the
  session, no folder is connected — have them connect one and run setup again.
- The FIRST-TIME SETUP banner → relay its instructions in your own words: a settings file was
  created, here is where it is, the ARGO REDCap address is already filled in, and they paste
  their access keys into it **in a text editor** when they have them — and they can also just carry on, because most ARGO work needs no
  keys at all.

**Never ask them to paste an access key into the chat.** Keys typed into a conversation are saved
in the transcript. If they start typing one, stop them and point at the settings file instead.

## Offering and adding access keys

**Offer it — don't wait to be asked.** When setup has just created a fresh settings file, your
single routing question must include **"add my access keys"** as one of its options (alongside the
task options). Most people will skip it, and that's fine — say so.

When they choose it, or ask at any point, walk them to it and close the loop:

0. **Best: put the file itself into the chat.** Cowork sessions have a file-presenting tool
   (`present_files` on the cowork tool server) — present the settings file with it, unprompted.
   It renders as a clickable card that opens the file in a text editor on their computer, which
   is the whole journey in one click. Only if no such tool exists: try
   `open -t "<full path to the .env>"` (opens on-screen on some setups; errors harmlessly on
   others), then fall back to the double-click below.

1. Easiest: tell them to open the ARGO folder on their computer and **double-click
   'Add keys here'** — the settings file opens in a text editor. Fallback: give the exact
   path (the scaffold prints it); on a Mac, Finder → Cmd+Shift+G → paste the path.
2. Tell them which line each key goes on (the variable names are already in the file, one per
   tracker) and to save when done.
3. **Wait.** Then verify for them: run `argo_setup.py --check` and then the client `--check`, and
   relay the result — "all five keys work" or exactly which one doesn't.
4. If they start typing a key into the chat, stop them and point back at the file. A key pasted
   here lands in the transcript permanently.

## Step 1 — find out what they're here to do

If it isn't already obvious from what they said, ask **one** question — what are they trying to do
today — and route on the answer. Don't present the whole table below and ask them to pick; match
their words to a row and go.

| They say something like… | Route to | Needs a key? |
|---|---|---|
| "What's the status of our studies?" / "weekly update" / "what's pending?" | [[study-portfolio]] (argo-pm) | Yes — the 5 tracker keys (usually already configured) |
| "We're starting a new study" / "draft the protocol / questionnaire" | [[study-setup]] (argo-pm) | No |
| "Build the REDCap database for study X" / "the SIR was submitted" | [[redcap-build]] (argo-build) | Tracker key for progress-marking; the build itself is files + UI |
| "Add someone to a project" / "set up roles / user rights" | [[redcap-admin]] (argo-build) | No — makes a CSV to upload; API only if a key exists |
| "Get the data out" / "I need an export" | [[data-export]] (argo-data) | No — website download is the normal path |
| "Check the data / find missing fields" / "make the RA worklists" | [[redcap-qa]] (argo-qa) | No — works from downloaded files |
| "Analyze this export" / "make Table 1" / "summary stats" | [[run-analysis]] (argo-analysis) | Never |
| "Match records between studies / with this spreadsheet" | [[study-linkage]] (argo-data) | No for the linkage; write-back is a separate careful step |
| "I'm the new RA and was told to fix the yellow cells" | They don't need a skill — the worklist Excel + REDCap in a browser. Explain the [[redcap-qa]] RA workflow section. | No |

Once routed, **invoke that skill and keep going** — don't summarise it back at them or make them
re-ask. This skill's job ends at the hand-off.

## The one thing to say about access keys, if it comes up

No key is ever required — everything works from files downloaded off the REDCap website
([[getting-files-from-redcap]] has click-by-click instructions). The standing setup for
**everyone on the team is the five tracker keys** (they power the shared portfolio dashboard).
Beyond that, **add a study key for each study you're QAing** — pulls and exports for it then
happen right in the session. The REDCap administrator creates keys (ideally tied to accounts
that can only do what's needed — export-only is often enough); there is nothing anyone can do
in this chat to make one.

Full decision record for who holds which key: [[access-tiers]].

## Notes for you, the agent (not for the user)

- Scripts live in different places per environment. Always locate them by search, never by a
  hardcoded or relative path:
  `find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name <script>.py 2>/dev/null | head -1`
- Shell state does not persist between commands anywhere ARGO runs. Any `source` must be combined
  with the command that uses it, in one line.
- If a script says it can't reach REDCap or can't find the shared ARGO code, run the setup check
  (`argo_setup.py --check`) and the client check (`argo_redcap_client.py --check`) before
  debugging anything else — they diagnose the two most common causes in plain language.
- Don't make autonomous calls on data semantics or data-dictionary changes — surface the decision
  to the user, one issue at a time ([[decision-protocol]]).
