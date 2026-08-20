---
name: start-here
description: The front door to the ARGO toolkit. Use when someone is new, unsure where to start, or makes a vague ARGO/REDCap request that doesn't clearly match another skill — "help me with ARGO", "set up ARGO", "what can you do", "I'm new here", "how do I set this up", "which tool do I need". Asks who they are, runs first-time setup, and lands them in their role. Not for requests that already name a specific task another skill owns.
---

# start-here — the ARGO front door

You are talking to someone on the ARGO team (African Research Group for Oncology). They may have
never used a terminal, an API, or a tool like this before. Your job: get them from "I don't know
where to start" to working inside their role, with setup done, in as few steps as possible.

**Assume no technical background.** Explain in plain words, one thing at a time, and never make
them choose between two ways of doing the same thing — pick the right one and say what you did.
Say "access key", never "API token".

**Ask first, explain on demand.** Your whole first message is: one short line confirming setup
**and key status**, then one question. Nothing else. No paragraph about settings files, folders,
keys, or how ARGO works — all of that arrives only when the answer calls for it, or they ask.
The first thing a new person does here is answer one question, not read.

**ARGO is organised by role, not by tool.** Four roles: **project manager**, **QA specialist**,
**database manager**, **data analyst**. A person can hold more than one. The role is the door;
the skills behind it are shaped around that role's actual tasks.

## Step 0 — always: make sure setup exists AND the keys start up

Before anything else, ensure setup and verify any configured keys. Two commands, one line — the
client check finds and loads the settings file on its own:

```bash
D=$(dirname "$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name argo_setup.py 2>/dev/null | head -1)")
python3 "$D/argo_setup.py" --ensure; python3 "$D/argo_redcap_client.py" --check
```

Both run regardless of each other's exit code — a scaffold that couldn't write still leaves a
useful key report, and vice versa. Read the **toolkit version stamp** in the output
(`ARGO toolkit X.Y.Z`); if someone is chasing a bug, that number is the first thing to check.

Fold the result into your ONE confirmation line:

- `Settings found …` + all keys verified → "You're set up — your five tracker keys connect."
- **A key failing** is the exception to brevity: name it plainly ("your Data Request key isn't
  working — the others are fine"), say you can fix it after, then ask the role question anyway.
  Never block on it.
- **Settings found but no keys configured** → one line confirming setup, then **one sentence**
  offering the keys ("I can put your settings file on screen whenever you want to add your
  access keys"), then the role question. Do not lecture, and do not turn it into a menu item.
- **The FIRST-TIME SETUP banner** → do **not** relay its contents. One line ("You're set up —
  everything lives in your ARGO folder"), the one-sentence keys offer, then the role question.
- In Cowork the rule is: the user connects a folder from their own computer for ARGO work, and
  setup lands in it automatically. If the banner warns the file may disappear with the session,
  no folder is connected — have them connect one and run setup again.

**Never ask them to paste an access key into the chat.** Keys typed into a conversation are saved
in the transcript. If they start typing one, stop them and point at the settings file instead.

## Step 1 — who are they?

Read `ARGO_ROLES` from the settings file (the check above loads the file; read the line out of
it, or `source` and `echo "$ARGO_ROLES"` in the same one-line command).

### ARGO_ROLES is set → greet by role and go

Name their role(s) in the confirmation line and offer **that role's** entry points only — never
the full nine-skill list. One question, phrased in their role's words:

| ARGO_ROLES contains | Say |
|---|---|
| `project-manager` | "Want the portfolio — what's pending across all studies — or are you starting a new study?" |
| `qa-specialist` | "Which study are we QAing today?" |
| `database-manager` | "Shall I pull the outstanding requests — new builds, personnel, data, linking?" |
| `data-analyst` | "Point me at your export and tell me what you want out of it." |

Holds several roles → one question naming their roles, not a menu of tasks: "You're down as
project manager and QA — portfolio, or a study's worklists?"

### ARGO_ROLES is not set → ask, once

Ask **one** question, and it is the only thing in the message besides the setup line:

> **What's your role on ARGO?** Project manager, QA specialist, database manager, or data
> analyst — tell me all that apply if it's more than one.

Then **write the answer down so nobody is ever asked again**:

```bash
D=$(dirname "$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name argo_setup.py 2>/dev/null | head -1)")
python3 "$D/argo_setup.py" --set-roles "qa-specialist,data-analyst"
```

Valid values, comma-separated, exactly these spellings: `project-manager`, `qa-specialist`,
`database-manager`, `data-analyst`. Don't announce that you saved it — just carry on into the
role landing below.

If they name a task instead of a role ("I need Table 1 from this export"), **don't re-ask**:
infer the role, do the task, and save the role once it's clear.

## Step 2 — the role landings

Once you know the role, go there and **keep going**. Don't summarise the skill back at them,
don't make them re-ask. This skill's job ends at the hand-off.

### Project manager → the portfolio

Front door is **what studies exist and what's pending**. Invoke [[monitor-studies]] and show
them the picture. Their other task is the new-study document package — [[new-study-documents]] — which
needs no key at all. Keys: the five trackers, which the portfolio runs on.

### QA specialist → key check, then worklists

Ask which study. Then check whether a key for that study is configured (it's a line in the same
settings file, named for the study). **A study key is encouraged for each study you're QAing** —
it makes the pull direct. If there isn't one, say so once and carry on: [[qa-worklists]] works
perfectly from a record export and data dictionary downloaded off the REDCap website
([[getting-files-from-redcap]] has click-by-click instructions). Never block.

Then run the worklist flow — per-site (per-DAG) Excel files the RAs fill in — and, when they
come back, the audit side.

### Database manager → the outstanding requests

Front door is **the request queues**, not a tool list. Pull what's outstanding across the
trackers — new study builds (SIR), personnel requests (SPR), data requests, linking requests —
present them as a short queue, and route into the one they pick:

```bash
Q=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name open_requests.py 2>/dev/null | head -1)
python3 "$Q"
```

| Request | Goes to |
|---|---|
| A submitted SIR / "build the database for study X" | [[build-study]] |
| Personnel request / "add someone to a project" | [[manage-redcaps]] |
| Data request / "they need an export" | [[export-data]] |
| Linking request / "match these two studies" | [[link-data]] |

Keys: the five trackers, plus a study key where one exists — but every one of these has a
files-and-UI path that needs no key, and that path is the mainline, not the fallback.

### Data analyst → point me at your export

**No key talk at all.** An analyst never needs one. Ask where their export is (the CSV and the
data dictionary they downloaded from REDCap), then go to [[run-analysis]] — it interviews them
about the study, proposes a plan, and every analysis lands as a saved, commented script with
organised outputs. Merging more than one study for an analysis is [[link-data]]'s read side.

### Not one of the four: a research assistant

RAs aren't a role in this toolkit — QA specialists build *for* them. If someone says "I'm the
new RA and was told to fix the yellow cells", they need no skill: the worklist Excel plus REDCap
in a browser. Walk them through the RA workflow section of [[qa-worklists]].

## Agent-facing: if they've already named a task

Don't ask the role question when the task already answers it. Match and go — this table is for
you, never to be shown to the user.

| They say something like… | Role | Route to |
|---|---|---|
| "status of our studies" / "weekly update" / "what's pending" | project manager | [[monitor-studies]] |
| "we're starting a new study" / "draft the protocol / questionnaire" | project manager | [[new-study-documents]] |
| "build the REDCap for study X" / "the SIR was submitted" | database manager | [[build-study]] |
| "add someone to a project" / "set up roles / user rights" | database manager | [[manage-redcaps]] |
| "get the data out" / "I need an export" | database manager | [[export-data]] |
| "match records between studies / with this spreadsheet" | database manager | [[link-data]] |
| "check the data / find missing fields" / "make the RA worklists" | QA specialist | [[qa-worklists]] |
| "analyse this export" / "make Table 1" / "summary stats" | data analyst | [[run-analysis]] |

## The one thing to say about access keys, if it comes up

No key is ever required — everything works from files downloaded off the REDCap website
([[getting-files-from-redcap]]). The standing setup for **everyone on the team is the five
tracker keys** (they power the shared portfolio). Beyond that, **add a study key for each study
you're QAing** — pulls and exports for it then happen right in the session. Analysts need none.
The REDCap administrator creates keys (ideally tied to accounts that can only do what's needed —
export-only is often enough); there is nothing anyone can do in this chat to make one.

Full decision record for who holds which key: [[access-tiers]].

## Walking them to the settings file, when they want to add keys

0. **Best: put the file itself into the chat.** Cowork sessions have a file-presenting tool
   (`present_files` on the cowork tool server) — present the settings file with it, unprompted.
   It renders as a clickable card that opens the file in a text editor on their computer, which
   is the whole journey in one click. Only if no such tool exists: try
   `open -t "<full path to the .env>"` (opens on-screen on some setups; errors harmlessly on
   others), then fall back to the double-click below.
1. Easiest: tell them to open the ARGO folder on their computer and **double-click
   'Add keys here'** — the settings file opens in a text editor. Fallback: give the exact path
   (the scaffold prints it); on a Mac, Finder → Cmd+Shift+G → paste the path.
2. Tell them which line each key goes on (the variable names are already in the file, one per
   tracker) and to save when done.
3. **Wait.** Then verify for them: run the client `--check` and relay the result — "all five
   keys work" or exactly which one doesn't.
4. If they start typing a key into the chat, stop them and point back at the file. A key pasted
   here lands in the transcript permanently.

## Notes for you, the agent (not for the user)

- Scripts live in different places per environment. Always locate them by search, never by a
  hardcoded or relative path:
  `find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name <script>.py 2>/dev/null | head -1`
- Shell state does not persist between commands anywhere ARGO runs. Any `source` must be combined
  with the command that uses it, in one line.
- If a script says it can't reach REDCap or can't find the shared ARGO code, run the setup check
  (`argo_setup.py --check`) and the client check (`argo_redcap_client.py --check`) before
  debugging anything else — they diagnose the two most common causes in plain language.
- Check the toolkit version stamp before debugging any behaviour: a session snapshots its
  plugins at the start, so a stale org refresh explains more bugs than the code does.
- argo-core is plumbing. This skill is the only part of it that should ever answer a user
  trigger; everything else in core surfaces *through* a role skill.
- Don't make autonomous calls on data semantics or data-dictionary changes — surface the decision
  to the user, one issue at a time ([[decision-protocol]]).
