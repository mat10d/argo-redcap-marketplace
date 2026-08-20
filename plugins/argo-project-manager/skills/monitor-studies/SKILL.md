---
name: monitor-studies
description: See what's happening across all ARGO studies. Which studies are waiting to be built and how far each one has got, plus the open personnel requests, data and linkage requests, and support tickets — pulled live from the five ARGO trackers, with what changed since last time. Use for "what's the status of our studies", "weekly update", "what's pending", "which studies aren't built yet", "any new requests".
---

# monitor-studies

Your standing view of every ARGO study and every open request. Run it when you want to know
where things stand.

## What you get

A dashboard covering all five ARGO trackers:

- **Studies** — which are still waiting to be built, which are in production, and how far each
  build has got
- **Personnel requests** — who needs access to what, still open
- **Data linking requests** and **data requests** — still open
- **Support tickets** — still open

Plus what changed since the last run, and a saved snapshot so the next run can do the same.

### Reading a study's row

Each study renders as:

```
[study_status]  PID 242  6/7  Hepatectomy — PI: Alatise
```

Where:
- `study_status` is the current state (Building / In Production / Completed / Paused / Closed)
- `PID` is the new project's PID
- `6/7` is per-step progress across the **7** canonical build flags:
  `project_created`, `dd_uploaded`, `user_rights_complete`, `data_imported`, `review_internal`,
  `review_pi`, `study_production`
- The short name comes from `shortened_study_name`

A record counts as **done** purely on its tracker's done-marker field equalling `Yes` (see the
table at the bottom).

## Run it

```bash
set -a; source ~/.argo/.env; set +a
python3 ${CLAUDE_PLUGIN_ROOT}/skills/monitor-studies/portfolio.py --diff
```

Monday morning is the natural rhythm: run it, review what's new, then drill into each
pending-build study via [[build-study]].

To check which trackers are reachable from your machine at any time:

```bash
set -a; source ~/.argo/.env; set +a
python3 ${CLAUDE_PLUGIN_ROOT}/skills/monitor-studies/portfolio.py --check
```

It prints one line per tracker — its title, its record-ID column, and whether the key works —
and never prints a full key.

## What to do with what you see

When you pick a record to act on:

- **Study waiting to be built** → [[build-study]] (argo-database-manager) to triage, build the data
  dictionary, and mark build progress
- **Personnel request** → [[manage-redcaps]] (in argo-database-manager) to assign roles
- **Data linking request** → [[link-data]] (argo-database-manager). Builds the master linkage table,
  separates safe-fills from conflicts, and reports gaps/orphans before any write-back.
- **Data request** → extraction via [[export-data]]
- **Support ticket** → triage manually; if technical, route to [[manage-redcaps]]

## Where it saves

| Artifact | Path |
|---|---|
| Snapshots | `project-manager/portfolio-snapshots/snapshot-<ISO timestamp>/` — a **directory**, not a single file |
| ↳ the snapshot itself | `snapshot-<ISO timestamp>/summary.json` |
| ↳ per-project raw exports | `snapshot-<ISO timestamp>/<ENV_VAR>.csv` (Excel-friendly, one per tracker) |
| Per-ticket working dirs | `database-manager/tickets/<ticket-id>/` (created by [[build-study]]) |
| Your access keys | the settings file in your ARGO folder — never shared, never pasted into chat |

Snapshots land in `project-manager/` inside your ARGO folder. Set `ARGO_PM_ROOT` only if you
keep them somewhere else.

`--diff` compares against the most recent `snapshot-*/summary.json`.

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

## See also
- [[build-study]] (argo-database-manager) — triages and builds a specific study from this portfolio
- [[manage-redcaps]] (argo-database-manager) — personnel and role changes
- [[token-confirmation]] (argo-core) — applied automatically by `portfolio.py` before every fetch
