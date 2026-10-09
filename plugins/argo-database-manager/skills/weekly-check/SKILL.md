---
name: weekly-check
description: The database manager's standing check — where every ARGO study stands and what's waiting for you. Programme status across the five trackers (which studies exist, how far each build has got, what changed since last time) plus the open queues: studies to build, people requests, data requests, linking requests. Use for "what's waiting for me", "weekly check", "where do things stand", "what's pending", "any new requests", "which studies aren't built yet".
allowed-tools: Read, Bash, Write, Edit
---

# weekly-check

The database manager's standing check. One run answers both halves of "where are we?":

1. **Programme status** — every study on the tracker, how far each build has got, what changed.
2. **Your queues** — the open requests waiting on you, each routed to what fulfils it.

Monday morning is the rhythm; also run it whenever someone asks what's outstanding, and at the
start of any database-manager session.

**Keep it short.** Short sentences, plain words, the tables below, then one question. An item
marked `(still open)` was already reported last time: give it one line — "still open" and what
it waits on — not a fresh explanation.

Scripts are located by search (plugin paths differ per environment; shell state doesn't survive
between commands, so find and run in one command):

```bash
P=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name portfolio.py 2>/dev/null | head -1)
python3 "$P" --diff
```

The other commands below name the script only; locate it the same way. Every script reads the
ARGO settings file itself — nothing to `source` first.

## Part 1 — Programme status

`portfolio.py --diff` compares against the last snapshot, so you see **what changed** — new
submissions (🆕), studies that reached production — not just a list. It covers all five
trackers. Give the shape of it in a few lines; don't paste the dashboard unless asked. The
open-request counts it prints belong to Part 2 — present those item by item there, not as a
count here.

```
[Building/Pending] PID  242  6/7 — Hepatectomy — PI: Alatise
```

- bracketed: `study_status` (Building/Pending · Open to accrual · Closed to accrual; In analysis ·
  Published · Closed – locked · Inactive · Closed; will not be published)
- `PID` — the study's REDCap project number
- `6/7` — steps done of the **7** canonical build flags: `project_created`, `dd_uploaded`,
  `user_rights_complete`, `data_imported`, `review_internal`, `review_pi`, `study_production`
- the short name is `shortened_study_name`

A step is **done** when its field holds any settled answer that isn't "No" — `data_imported`'s
"Prospective study, not required" counts. The rule lives in argo-core's
`argo_trackers.sir_progress`, shared with the queue, so a study never reads 6/7 in one half and
5/7 in the other.

**Notes that disagree with the flags.** Read the open builds' `build_notes` in the snapshot's
`STUDY_INITIATION_REQUEST.csv`. Where the notes claim more than the flags do (notes: "built and
reviewed", flags: 2/7), list them in one table — **Notes disagree with flags — reconcile**:
record, what the notes say, what the flags say. Don't pick a side; the database manager fixes
whichever is wrong (flags with `sir_update.py`, in [[build-study]]).

To check which trackers your keys reach, without pulling data: `portfolio.py --check` — one line
per tracker (title, record-ID column, works or not), never more than a key's last four
characters.

## Part 2 — What's waiting for you

```bash
open_requests.py                        # every queue
open_requests.py --record people 12     # one request in full; queues: builds | people | data | linking
```

One line per open record, built from each tracker's own data dictionary — no guessed field names:
the record number, then `Label: value` bits joined with `; `. The builds queue leads with short
name and PI and ends `[N/7 build steps done; next: <step>]`. The people queue leads with the
person's name, email and the access asked for — a request you can't put a name to is one you
can't act on. A queue whose key is missing or failing is reported and skipped; one bad key never
blocks the check.

### How to present the queues — the rules

These aren't style. Collapsing open work into a count is how a request sits untouched for a
month; a table of nothing buries the real work.

1. **A queue with nothing open gets ONE line — never a table.** "No data requests." That is the
   whole entry.
2. **Every open item gets its own row.** One record, one row, always. Never collapse several into
   one line — no "3 builds not started yet", no "…and 5 more". The reader has to pick one, and a
   count picks nothing.
3. **The rows go in an inline markdown table, in the message itself** — not a file, not a code
   block, not a list.
4. **Columns come from the line.** Each `Label: value` bit is one column, headed by its label, in
   the order printed (the form's own labels — don't rename them). Too many bits to read? Drop
   columns down to the ones named below. **Never drop a row.**
5. **Head each table with the queue and its count** — `**People requests — 4 open**`.
6. **Support tickets are the one exception to rule 2** — a count only. They are triaged by hand
   in the Support Ticket project, not worked from here.

Columns that must be there:

| Queue | Columns |
|---|---|
| Studies to build (SIR) | record, short name, PI, progress (`N/7`), next step |
| People requests (SPR) | record, first name, last name, email, the study, the role being asked for |
| Data requests · Linking requests | record, then the summary fields the line carries |

**Next step** is the `next:` the builds line ends with — the first of the 7 flags not ticked,
which is where [[build-study]] picks up. Say it in words ("Upload the data dictionary").

**Studies to build — 3 open**

| Record | Study | PI | Progress | Next step |
|---|---|---|---|---|
| 12 | Hepatectomy | Alatise | 6/7 | Move to production |
| 14 | Colorectal | Fakeman | 2/7 | Upload the data dictionary |
| 15 | Gastric | Mockford | 0/7 | Create the project |

**People requests — 2 open**

| Record | Given name | Family name | Work email address | Study | Role being requested |
|---|---|---|---|---|---|
| 1 | Cleo | Sampleton | c.sampleton@example.org | Hepatectomy | Data manager |
| 4 | Ime | Synthetica | i.synthetica@example.org | Colorectal | Data entry |

> No data requests.
> No linking requests.

Then ask **one** question: which one to take. Then route:

| Queue | Fulfil it with |
|---|---|
| **Studies to build** | [[build-study]] — enter at the next step |
| **Data requests** | [[export-data]] |
| **Linking requests** | [[link-data]] |
| **People requests** | REDCap itself — below. There is no add-users skill. |
| Support tickets | count only — triaged by hand in the Support Ticket project |

**A request missing something stays on the queue.** Name the missing Study Tracker field(s) in
one line and who fills them — usually the requester or PM: "Record 14: `irb_number` and
`irb_approval_expires` are blank — the PM updates them." A paused or blocked study likewise stays
listed with its blocker in one line. The session never deletes records itself.

## People requests are done by hand, in REDCap

A study's own project almost never has an access key, and giving someone access is a two-minute
click-through. Say that plainly rather than hunting for a tool.

Open the study's project → **User Rights**:

- **They have a REDCap account** → add their username, assign one of the four standard roles
  ([[standard-roles]]).
- **The roles aren't on the project yet** → [[build-study]] Step 4 makes the roles CSV; upload it
  at **User Rights → User Roles → Upload user roles (CSV)** first.
- **No REDCap account** → only an administrator can create one. Leave the request open and say
  which administrator to ask.
- Site isolation is Data Access Groups, on the same page.

We don't know anyone's real REDCap username, so present who→role as a **table** — never generate
an assignment file.

## Closing a request

**Studies to build** close when `study_production` is marked. When the user says "close out the
build" (or "it's closed", "it's in production"), that is [[build-study]]'s
`sir_update.py <RID> --close-out`: every remaining step and the tracker form in one push, one
diff. Every Study Tracker write goes through `sir_update.py` — never a hand-written
`import_records` call. (The queue's own footer says to tick the box on the website; for builds,
`sir_update.py` does it.)

**People, data, linking and support requests** close by ticking `completed`. Either way is fine:

- from here: `close_request.py <people|data|linking|support> <record>` — shows the change, asks,
  writes only `completed`; or
- in the REDCap UI, on the record.

Never fill `assigned_to` with a guess — it is a REDCap username. Leave it blank unless the user
names the real username (`--assigned-to <username>`). No key for that tracker → the UI.

## Where it saves

| Artifact | Path |
|---|---|
| Snapshots | `database-manager/weekly-check/snapshot-<ISO timestamp>/` — a **directory**, not a single file |
| ↳ the snapshot itself | `snapshot-<ISO timestamp>/summary.json` |
| ↳ per-tracker raw exports | `snapshot-<ISO timestamp>/<ENV_VAR>.csv` (Excel-friendly) |
| Per-study build folders | `database-manager/<study>/` ([[build-study]] Step 1b) |
| Your access keys | the settings file in your ARGO folder — never pasted into chat |

`ARGO_PM_ROOT` in the settings file names the `database-manager/` folder (setup fills it in).
`--diff` compares against the latest `snapshot-*/summary.json` from a run that read at least one
tracker; on the very first run it says "First snapshot — nothing to compare against yet" rather
than a silence that reads as "nothing changed".

## The five trackers

Mirrors `argo_trackers.py` in argo-core, the single source of truth.

| Env var | Project title | PID | Done-marker field |
|---|---|---|---|
| `STUDY_INITIATION_REQUEST` | Study Tracker | 224 | `study_production` |
| `STUDY_PERSONELL_REQUEST` | Study Personnel Request | 221 | `completed` |
| `DATA_LINKING_REQUEST` | Data Linking Request | 222 | `completed` |
| `DATA_REQUEST` | Data Request | 223 | `completed` |
| `SUPPORT_TICKET_REQUEST` | Support Ticket Request | 225 | `completed` |

- **The Study Tracker's done-marker is `study_production`** — the last build step — not
  `study_built` or `study_status`. Older docs said otherwise; the code reads `study_production`.
- The other four share the `tracking` form's `completed` field. Until that instrument is uploaded
  to a project, every record there reads "open" — expected, not an error.
- The Study Tracker's `internal_tracking` form carries the per-study detail the dashboard shows.
  It replaces the Active Databases Excel sheet.

## Running it on a schedule

[[scheduled-weekly-check]] (`references/scheduled-weekly-check.md`) is a self-contained
instruction file for a Cowork scheduled task: it locates the scripts, runs the same two commands,
writes the report into the ARGO folder and posts a short summary.

## See also
- [[build-study]] — takes one study from the queue and builds it
- [[export-data]] · [[link-data]] — the other two fulfilment paths
- [[standard-roles]] (argo-core) — the four ARGO roles, for people requests
- [[token-confirmation]] (argo-core) — applied by `portfolio.py` before every fetch
