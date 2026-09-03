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
Read `ARGO_ROLES` out of the same settings file while you're here — the confirmation line
depends on it.

Fold the result into your ONE confirmation line:

- `Settings found …` + all keys verified → "You're set up — your five tracker keys connect."
- **A key failing** is the exception to brevity: name it plainly ("your Data Request key isn't
  working — the others are fine"), say you can fix it after, then ask the role question anyway.
  Never block on it. **Exception:** if every role they hold is data analyst, say nothing about
  keys at all — the analyst landing's "no key talk" rule wins, because an analyst has no key to
  fix and the failure can't affect their work.
- **Settings found but no keys configured** → one line confirming setup, then **one sentence**
  offering the keys ("I can put your settings file on screen whenever you want to add your
  access keys"), then the role question. Do not lecture, and do not turn it into a menu item.
  This is the *returning* user — they have been through setup before and can be offered rather
  than pushed. **Unless `ARGO_ROLES` is blank too**, which means they haven't: drop the offer,
  because Step 1 puts the file on screen the moment they name a role, and offering first only
  to do it anyway is two asks for one act.
- **The FIRST-TIME SETUP banner** → do **not** relay its contents, and do **not** offer the
  keys here. One line ("You're set up — everything lives in your ARGO folder"), then the role
  question. The keys are Step 1's job, and Step 1 doesn't ask — it puts the file on screen.
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
the full skill list. One question, phrased in their role's words:

| ARGO_ROLES contains | Say |
|---|---|
| `project-manager` | "Which study are we moving forward — and where is it: directors just approved, ready for IRB, or ethical approval received?" |
| `qa-specialist` | "Which study are we QAing today?" |
| `database-manager` | "Shall I run your weekly check — where the studies stand and what's waiting for you?" |
| `data-analyst` | "Point me at your export and tell me what you want out of it." |

Holds several roles → one question naming their roles, not a menu of tasks: "You're down as
database manager and QA — I'll start with your weekly check unless you'd rather go to a study."

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
`database-manager`, `data-analyst`. Don't announce that you saved it.

**Then, before the role landing — put the settings file on screen.** Anyone naming a **core
role** (project manager, QA specialist, database manager) is a core team member, and every core
member should hold the five tracker keys. If none are configured yet, **your next message is the
file itself.** Don't declare setup complete and ask whether they'd like to add keys — putting
the file in front of them *is* the completing act of setup. Present it **unprompted**, by the
ladder in "Putting the settings file on screen" below (file card first, then the fallbacks in
order), with one instruction line and one question:

> Here's your settings file. **Paste each key after its = sign, save, and tell me when you're
> done** — or say "later" and I'll carry on without them.

That is the whole message: the file, one instruction line, one question. The question is no
longer "want me to show you the file?" — the file is already there. Don't explain the five
trackers first, don't list what each key is for, and don't wait for permission to present it.

- **They say they've saved it** → verify (the client `--check`), relay the result in one line
  ("all five keys work" / exactly which one doesn't), then their role landing.
- **"Later", "I don't have them yet", or any other decline** → one line saying the REDCap
  administrator issues them, then straight on to the role landing. **Don't raise it again this
  session.** Nothing is blocked without keys.
- A **QA specialist** gets one extra line: their study's key goes in the same file.
- **Data analysts are the exception — skip this entirely.** If every role they hold is data
  analyst, present nothing and say nothing about keys; go straight to the analyst landing,
  whose "no key talk" rule wins here as it does in Step 0.

If they name a task instead of a role ("I need Table 1 from this export"), **don't re-ask**:
infer the role, do the task, and save the role once it's clear.

## Step 2 — the role landings

Once you know the role, go there and **keep going**. Don't summarise the skill back at them,
don't make them re-ask. This skill's job ends at the hand-off.

### Project manager → the study-launch pipeline

One task lives here: [[new-study-documents]] — it walks a study from the directors' approval to
the REDCap build request, and it is **gate-first**. So the landing *is* its one question:
*"Which study — and where is it: (1) the directors just approved it, (2) ready for stakeholder
review / IRB, or (3) ethical approval received?"* Ask it once (the greeting above already does
when their role was known — then don't repeat it), and hand straight over. The skill works that
gate's tasks one at a time, each filling its official ARGO template (consent, questionnaire, IRB
form, CPL/ECL, study SOP, QA plan, SIV, activation memo), and ends at the study request the PM
submits in REDCap themselves. **No key is required**; where the Study Tracker key is configured it
fetches the official Word templates, and without it the documents come from the built-in skeletons.

If they ask where things stand across the programme instead, say plainly that the weekly check
lives with the database manager now, and run [[weekly-check]] for them — it reads the same five
trackers.

### QA specialist → key check, then worklists

Ask which study. Then check whether a key for that study is configured (it's a line in the same
settings file, named for the study). **A study key is encouraged for each study you're QAing** —
it makes the pull direct. If there isn't one, say so once and carry on: [[qa-worklists]] works
perfectly from a record export and data dictionary downloaded off the REDCap website
([[getting-files-from-redcap]] has click-by-click instructions). Never block.

Then run the worklist flow — per-site (per-DAG) Excel files the RAs fill in — and, when they
come back, the audit side.

### Database manager → run the weekly check

Front door is **the weekly check**, not a tool list. Invoke [[weekly-check]] and let it do both
halves in one run: where every study stands (and what changed since last time), then the open
queues — new study builds (SIR), personnel requests (SPR), data requests, linking requests.
Present the picture in a few lines, then ask **one** question: which one to take.

| Request | Goes to |
|---|---|
| A submitted SIR / "build the database for study X" | [[build-study]] |
| Data request / "they need an export" | [[export-data]] |
| Linking request / "match these two studies" | [[link-data]] |
| Personnel request / "add someone to a project" | the REDCap UI — the study's **User Rights** page. There is no add-users skill; [[weekly-check]] says what to do. |

Keys: the five trackers, plus a study key where one exists — and none of these routes is ever
blocked for want of a key; every one has a files-and-UI path.

### Data analyst → point me at your export

**No key talk at all.** An analyst never needs one. Ask where their export is (the CSV and the
data dictionary they downloaded from REDCap), then go to [[run-analysis]] — it interviews them
about the study, proposes a plan, and every analysis lands as a saved, commented script with
organised outputs. Merging more than one study for an analysis is [[link-data]]'s read side.
The setup check (`argo_setup.py --check`) also reports which of Python, R and Stata this
computer can actually run, and [[run-analysis]] checks again before it writes any script.

### Not one of the four: a research assistant

RAs aren't a role in this toolkit — QA specialists build *for* them. If someone says "I'm the
new RA and was told to fix the yellow cells", they need no skill: the worklist Excel plus REDCap
in a browser. Walk them through the RA workflow section of [[qa-worklists]].

## Agent-facing: if they've already named a task

Don't ask the role question when the task already answers it. Match and go — this table is for
you, never to be shown to the user.

| They say something like… | Role | Route to |
|---|---|---|
| "status of our studies" / "weekly update" / "what's pending" / "what's waiting for me" | database manager | [[weekly-check]] |
| "we're starting a new study" / "the directors approved the study" / "draft the protocol / questionnaire" / "prepare the IRB submission" / "we got ethical approval" / "study activation" | project manager | [[new-study-documents]] |
| "build the REDCap for study X" / "the SIR was submitted" | database manager | [[build-study]] |
| "add someone to a project" / "set up roles / user rights" | database manager | the REDCap UI (User Rights); the roles CSV comes from [[build-study]] step 4 |
| "get the data out" / "I need an export" | database manager | [[export-data]] |
| "match records between studies / with this spreadsheet" | database manager | [[link-data]] |
| "check the data / find missing fields" / "make the RA worklists" | QA specialist | [[qa-worklists]] |
| "analyse this export" / "make Table 1" / "summary stats" | data analyst | [[run-analysis]] |

## The one thing to say about access keys, if it comes up

No key is ever required — everything works from files downloaded off the REDCap website
([[getting-files-from-redcap]]). The standing setup for **everyone on the team is the five
tracker keys** (they power the weekly check and the shared study dashboard). Beyond that,
**add a study key for each study you're QAing** — pulls and exports for it then happen right in
the session. Analysts need none. The REDCap administrator creates keys (ideally tied to accounts
that can only do what's needed — export-only is often enough); there is nothing anyone can do in
this chat to make one.

Full decision record for who holds which key: [[access-tiers]].

## Putting the settings file on screen

The ladder Step 1 uses after setup, and the same one to use whenever keys need to go in later.
Work down it and stop at the first rung that works — you are **presenting** the file, not asking
whether to.

0. **Best: put the file itself into the chat.** Cowork sessions have a file-presenting tool
   (`present_files` on the cowork tool server) — present the settings file with it, unprompted.
   It renders as a clickable card that opens the file in a text editor on their computer, which
   is the whole journey in one click. Only if no such tool exists: try
   `open -t "<full path to the .env>"` (opens on-screen on some setups; errors harmlessly on
   others), then fall back to the double-click below.
1. Next best: tell them to open the ARGO folder on their computer and **double-click
   'Add keys here'** — the settings file opens in a text editor. Fallback: give the exact path
   (the scaffold prints it); on a Mac, Finder → Cmd+Shift+G → paste the path.
2. **One instruction line, whichever rung you landed on**: "paste each key after its = sign,
   save, and tell me when you're done." The variable names are already in the file, one per
   tracker, so there is nothing else to explain.
3. **Wait.** Then verify for them: run the client `--check` and relay the result — "all five
   keys work" or exactly which one doesn't. They say "later" instead → carry on, and don't
   raise it again this session.
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
