---
name: weekly-check
description: The database manager's standing check — where every ARGO study stands and what's waiting for you. Programme status across the five trackers (which studies exist, how far each build has got, what changed since last time) plus the open queues: studies to build, people requests, data requests, linking requests. Use for "what's waiting for me", "weekly check", "where do things stand", "what's pending", "any new requests", "which studies aren't built yet".
allowed-tools: Read, Bash, Write, Edit
---

# weekly-check

Your standing check as ARGO's database manager. One run answers both halves of "where are we?":

1. **Programme status** — every study on the tracker, how far each build has got, what changed
   since the last check.
2. **Your queues** — the open requests waiting on you, each routed to the thing that fulfils it.

Monday morning is the natural rhythm, but run it any time someone asks what's outstanding, and
at the start of any database-manager session.

## Part 1 — Programme status

```bash
P=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name portfolio.py 2>/dev/null | head -1)
python3 "$P" --diff
```

`--diff` compares against the last saved snapshot, so you see **what changed** — new
submissions, studies that reached production — not just a list.

You get, for all five trackers: which studies are still waiting to be built, which are in
production and how far each build has got; plus open personnel, linking and data requests and
support tickets. Present the shape of it in a few lines. Don't paste the whole dashboard back
at the user unless they ask for it.

The open-request counts it prints belong to Part 2, not here — present those under the queue
rules below, item by item, rather than repeating them as a count in this half.

### Reading a study's row

```
[study_status]  PID 242  6/7  Hepatectomy — PI: Alatise
```

- `study_status` — the current state (Building / In Production / Completed / Paused / Closed)
- `PID` — the new project's number in REDCap
- `6/7` — steps done across the **7** canonical build flags: `project_created`, `dd_uploaded`,
  `user_rights_complete`, `data_imported`, `review_internal`, `review_pi`, `study_production`
- the short name comes from `shortened_study_name`

A build step counts as **done** when its field holds any settled answer that isn't "No" — some
of these fields are yes/no boxes and one (`data_imported`) is a radio whose "Prospective study,
not required" settles the step just as firmly as "Yes". That one rule lives in argo-core's
`argo_trackers.sir_progress` and is shared with the queue below, so a study never reads 6/7 in
one place and 5/7 in the other.

A **record** counts as finished on its tracker's own done-marker field (the table at the
bottom).

To check which trackers your keys can reach, without pulling anything:

```bash
P=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name portfolio.py 2>/dev/null | head -1)
python3 "$P" --check
```

One line per tracker — its title, its record-ID column, and whether the key works. Never a key.

## Part 2 — What's waiting for you

```bash
Q=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name open_requests.py 2>/dev/null | head -1)
python3 "$Q"
```

Each queue's open items, **one line per open record**, built from each tracker's own data
dictionary — no guessed field names. Every line is the record number, then `Label: value` bits
joined with `; `. The builds queue leads with the study's short name and PI and ends with its
`N/7` progress; the people queue leads with the person's name, email and the access they are
asking for, because a personnel request you can't put a name to is one you can't act on, and
the form lists the role after a phone number, where a plain summary never reached it. A queue
whose key is missing or failing is reported and skipped; the check never blocks on one bad key.

Pull one request in full before you start it:

```bash
Q=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name open_requests.py 2>/dev/null | head -1)
python3 "$Q" --record people 12          # queues: builds | people | data | linking
```

### How to present the queues — the rules

These are not stylistic preferences. Collapsing open work into a count is how a request sits
untouched for a month, and a table of nothing is how the open work gets lost in the noise.

1. **A queue with nothing open gets ONE line — never a table.** "No data requests." "No linking
   requests." That is the entire entry: no header row, no "none" row, no empty table.
2. **Every open item gets its own row.** One record, one row, always. Never collapse several
   into a single line — no "3 builds not started yet", no "the other four are untouched", no
   "…and 5 more". The person reading this has to pick one to take, and a count picks nothing.
3. **The rows go in an inline markdown table, in the message itself** — not a file, not a code
   block, not a bulleted list.
4. **The columns come from the line.** Each `Label: value` bit the script printed is one column,
   headed by that label, in the order printed. The labels are the form's own, straight from its
   data dictionary — don't rename them. If a queue's line carries more bits than read
   comfortably, drop columns down to the ones named below. **Never drop a row.**
5. **Head each table with the queue and its count** — `**People requests — 4 open**`.
6. **Support tickets are the one exception to rule 2** — a count only, as the routing table
   below says. They are triaged by hand in the Support Ticket project, not worked from here.

The columns that must be there:

| Queue | Columns |
|---|---|
| Studies to build (SIR) | record, short name, PI, progress (`N/7`), next step |
| People requests (SPR) | record, first name, last name, email, the role being asked for |
| Data requests · Linking requests | record, then the summary fields the line carries |

**Next step** for a build is the first of the seven canonical flags (listed under "Reading a
study's row" above) that isn't ticked — that's where [[build-study]] picks up. The `N/7`
fraction alone doesn't name it, because the steps aren't always ticked in order, so read it off
`--record builds <id>` when you need to be exact.

The shape, with three builds open:

**Studies to build — 3 open**

| Record | Study | PI | Progress | Next step |
|---|---|---|---|---|
| 12 | Hepatectomy | Alatise | 6/7 | Move to production |
| 14 | Colorectal | Fakeman | 2/7 | Upload the data dictionary |
| 15 | Gastric | Mockford | 0/7 | Create the project |

and two people requests:

**People requests — 2 open**

| Record | Given name | Family name | Work email address | Role being requested |
|---|---|---|---|---|
| 1 | Cleo | Sampleton | c.sampleton@example.org | Data manager |
| 4 | Ime | Synthetica | i.synthetica@example.org | Data entry |

and, in the same message, the two empty ones — one line each, no table:

> No data requests.
> No linking requests.

Then ask **one** question: which one to take. Then route:

| Queue | Fulfil it with |
|---|---|
| **Studies to build** (SIR, with build-step progress shown) | [[build-study]] — enter at the first unticked step |
| **Data requests** | [[export-data]] |
| **Linking requests** | [[link-data]] |
| **People requests** (SPR) | **REDCap itself** — see below. There is no add-users skill. |
| Support tickets | shown as a count only — triaged by hand in the Support Ticket project, not a build queue |

### People requests are done by hand, in REDCap

There is no add-users skill in ARGO, and that is deliberate: a study's own project almost never
has an access key, and giving someone access is a two-minute click-through on a page you are
already logged into. Say that plainly rather than hunting for a tool.

Open the study's project in REDCap → **User Rights** (the *Users & Roles* page):

- **The person already has a REDCap account** → add their username and assign them to one of the
  four standard ARGO roles ([[standard-roles]]).
- **The roles don't exist on the project yet** → [[build-study]] step 4 makes the upload-ready
  roles CSV; upload it at **User Rights → User Roles → Upload user roles (CSV)** first.
- **The person has no REDCap account yet** → only an administrator can create one. Record the
  request in the **Study Personnel Request** tracker (PID 221), one record per person, and say
  which record you created.
- Site isolation is Data Access Groups, on the same page.

We don't know anyone's real REDCap username, so present who→role as a **table** for the user to
work from — never generate an assignment file.

### Closing a request

When a request is fulfilled, tick its `completed` box in that tracker **on the REDCap website** —
that's what drains the queue. (The 222/223 keys don't carry import rights, so this is a UI step
by design, not an oversight.)

## Where it saves

| Artifact | Path |
|---|---|
| Snapshots | `database-manager/weekly-check/snapshot-<ISO timestamp>/` — a **directory**, not a single file |
| ↳ the snapshot itself | `snapshot-<ISO timestamp>/summary.json` |
| ↳ per-project raw exports | `snapshot-<ISO timestamp>/<ENV_VAR>.csv` (Excel-friendly, one per tracker) |
| Per-ticket working dirs | `database-manager/tickets/<ticket-id>/` (created by [[build-study]]) |
| Your access keys | the settings file in your ARGO folder — never shared, never pasted into chat |

Snapshots land in `database-manager/weekly-check/` inside your ARGO folder. `ARGO_PM_ROOT` in
the settings file names the folder they go in (setup fills it in); set it yourself only if you
keep them somewhere else.

`--diff` compares against the most recent `snapshot-*/summary.json`. On the very first run there
isn't one, and it says so — "First snapshot — nothing to compare against yet" — rather than
leaving a silence that reads as "nothing changed this week".

`portfolio.py` reads your ARGO settings file itself, so there is nothing to load or `source`
first. If the REDCap address is missing it says which file to put it in.

## The five trackers

This table mirrors `argo_trackers.py` in argo-core, the single source of truth — change it
there; `release.py` syncs the copies.

| Env var | Project title | PID | Done-marker field |
|---|---|---|---|
| `STUDY_INITIATION_REQUEST` | Study Tracker | 224 | `study_production` |
| `STUDY_PERSONELL_REQUEST` | Study Personnel Request | 221 | `completed` |
| `DATA_LINKING_REQUEST` | Data Linking Request | 222 | `completed` |
| `DATA_REQUEST` | Data Request | 223 | `completed` |
| `SUPPORT_TICKET_REQUEST` | Support Ticket Request | 225 | `completed` |

One note, on the row that trips people up:

- **The Study Tracker's done-marker is `study_production`, not `study_built` or `study_status`.**
  `study_production` is the final canonical build step, so it is the single done-marker. Older
  docs referred to `study_built`/`study_status >= 2`; those are not what the code reads.

The other four trackers share the `tracking` form's `completed` yes/no field. These fields don't
exist until the relevant instrument ZIP has been uploaded to that project — until then every
record stays bucketed as "open", which is expected, not an error.

The Study Tracker's `internal_tracking` form carries the rich per-study detail the dashboard
renders. It replaces the Active Databases Excel sheet.

## Running it on a schedule

To have this arrive every Monday without anyone asking for it, set it up as a scheduled task.
[[scheduled-weekly-check]] (`references/scheduled-weekly-check.md`) is a ready-made,
self-contained instruction file for exactly that: it locates the scripts, runs the same two
commands, writes the report into the ARGO folder and presents a short summary.

## See also
- [[build-study]] (same plugin) — takes one study from the queue and builds it
- [[export-data]] · [[link-data]] — the other two fulfilment paths
- [[standard-roles]] (argo-core) — the four canonical ARGO roles, for people requests
- [[token-confirmation]] (argo-core) — applied automatically by `portfolio.py` before every fetch
