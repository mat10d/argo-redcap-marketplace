---
name: scheduled-weekly-check
description: A ready-made scheduled-task file for the ARGO weekly check — copy it into a scheduled task so the programme status and the open queues arrive on their own each week.
---

# Running the weekly check on a schedule

A scheduled task runs in a fresh session with **no conversation history**, so the instruction
file it runs has to carry everything it needs: what to run, where the output goes, and what to
say afterwards. That's why the template below repeats things this skill already knows — it must
stand alone.

## How to set it up

1. In the Claude app, create a scheduled task (weekly, Monday morning is the usual choice) and
   point it at the connected ARGO folder — the same folder the settings file lives in.
2. Save the block below as that task's instruction file (`SKILL.md`). Change nothing but the
   day, if you want a different one.
3. The first run tells you whether the keys are reachable. If it reports a key problem, fix the
   key in the settings file, not the task.

Everything below the line is the file. It contains no personal paths — the scripts are located
by search at run time, and the report lands wherever the ARGO folder is.

---

````markdown
---
name: argo-weekly-check
description: Runs the ARGO weekly check — programme status across the five trackers plus the open request queues — and writes the report into the ARGO folder.
---

# ARGO weekly check (scheduled)

Run the ARGO database manager's weekly check and leave a written report behind. Work in the
connected ARGO folder. Say "access key", never "API token", and never print a key.

## 1. Find the scripts

They live inside the installed ARGO plugins, whose path differs per machine — always locate
them by search, never by a hardcoded path:

```bash
P=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name portfolio.py 2>/dev/null | head -1)
Q=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name open_requests.py 2>/dev/null | head -1)
echo "$P"; echo "$Q"
```

If either comes back empty, stop and report that the ARGO plugins aren't installed in this
session — don't improvise a replacement.

## 2. Run the check

Two commands. Run both even if the first one complains; each is useful on its own.

```bash
P=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name portfolio.py 2>/dev/null | head -1)
python3 "$P" --diff
```

```bash
Q=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name open_requests.py 2>/dev/null | head -1)
python3 "$Q"
```

The first prints programme status across the five ARGO trackers and what changed since the last
run, and saves a snapshot so next week can do the same. The second prints the open queues:
studies to build, people requests, data requests, linking requests.

A tracker whose access key is missing or failing is reported and skipped — that is not a
failure, and the rest of the report is still accurate. If **every** tracker fails, say so at the
top: the report is empty because something is wrong, not because it was a quiet week.

## 3. Write the report

Save a short markdown report into the ARGO folder at:

    database-manager/weekly-check/report-<YYYY-MM-DD>.md

Structure it as:

- **What changed this week** — new requests, studies that moved forward, anything finished.
- **Studies in flight** — one line each: status, project number, build steps done (N/7), name.
- **Waiting on the database manager** — the open queues, counts first, then the individual
  items, each with where it goes: studies to build → the build-study skill; data requests →
  the export-data skill; linking requests → the link-data skill; people requests → by hand on
  the study project's User Rights page in REDCap (there is no add-users skill).
- **Anything unavailable** — trackers that couldn't be read, in plain words.

Numbers come from the two commands. Don't estimate, and don't fill a gap with a guess: if
something couldn't be read, the report says so.

## 4. Present it

Post a short summary in the conversation — the headline numbers, what changed, and the single
thing most worth doing first — then name the report file you saved. Plain language, no jargon,
no record-level patient data. Never paste the whole dashboard.
````
