---
name: study-portfolio
description: Weekly portfolio tracker across ARGO's admin REDCaps. Surfaces studies pending build, open personnel requests, data linking/data requests, and support tickets. Saves a JSON snapshot each run so week-over-week diffs are possible. The front door of the ARGO workflow — run this first.
---

# study-portfolio

The weekly-update skill. Pulls the admin REDCaps and produces a dashboard plus a saved snapshot.

## The admin REDCaps

This table mirrors `ADMIN_REDCAPS` in `portfolio.py` — **if you change one, change the other.**
The env var, project title, and done-marker field must match the code exactly; the dashboard
buckets a record as "done" purely on the done-marker field equalling `Yes`.

| Env var | Project title | PID | Done-marker field |
|---|---|---|---|
| `STUDY_INITIATION_REQUEST` | Study Tracker | 224 | `study_production` |
| `STUDY_PERSONELL_REQUEST` | Study Personnel Request | 221 | `completed` |
| `DATA_LINKING_REQUEST` | Data Linking Request | 222 | `completed` |
| `DATA_REQUEST` | Data Request | 223 | `completed` |
| `SUPPORT_TICKET_REQUEST` | Support Ticket Request | 225 | `completed` |

One note, on the row that trips people up:

- **The SIR's done-marker is `study_production`, not `study_built` or `study_status`.**
  `study_production` is the final canonical build step, so it is the single done-marker. Older
  docs referred to `study_built`/`study_status >= 2`; those are not what the code reads.

The other four trackers share the `tracking` form's `completed` yes/no field. These fields don't
exist until the relevant instrument ZIP has been uploaded to that project — until then every
record stays bucketed as "open", which is expected, not an error.

Check which of these are reachable from your machine at any time:

```bash
set -a; source ~/.argo/.env; set +a
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-portfolio/portfolio.py --check
```

It prints one line per tracker — its title, its record-ID column, and whether the key works —
and never prints a full key.

### SIR rich tracking (added during hardening)

The SIR's `internal_tracking` form was expanded with 28 fields (see `REDCap/PM/tracker-additions/SIR_internal_tracking_expansion.csv`). The dashboard now renders each SIR record as:

```
[study_status]  PID 242  6/7  Hepatectomy — PI: Alatise
```

Where:
- `study_status` is the current state (Building / In Production / Completed / Paused / Closed)
- `PID` is the new project's PID (set via `sir_update.py --pid`)
- `6/7` is per-step progress across the **7** canonical build flags in `SIR_BUILD_STEPS`:
  `project_created`, `dd_uploaded`, `user_rights_complete`, `data_imported`, `review_internal`,
  `review_pi`, `study_production`. (Some older docs said 9 — build-side technical detail is
  collapsed into `user_rights_complete` and enforced by the DD validator instead.)
- The short name comes from `shortened_study_name`

This replaces the Active Databases Excel sheet.

## How to run

```bash
set -a; source ~/.argo/.env; set +a
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-portfolio/portfolio.py            # dashboard + snapshot
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-portfolio/portfolio.py --diff     # also show diff vs last snapshot
```

## Where things land

| Artifact | Path |
|---|---|
| Snapshots | `$ARGO_PM_ROOT/portfolio-snapshots/snapshot-<ISO timestamp>/` — a **directory**, not a single file |
| ↳ the snapshot itself | `snapshot-<ISO timestamp>/summary.json` |
| ↳ per-project raw exports | `snapshot-<ISO timestamp>/<ENV_VAR>.csv` (Excel-friendly, one per tracker) |
| Per-ticket working dirs | `REDCap/PM/tickets/<ticket-id>/` (created by [[redcap-build]]) |
| Tokens | `~/.argo/.env` (user-specific, mode 600, never committed) |

`--diff` compares against the most recent `snapshot-*/summary.json`. Snapshots written by much
older versions were flat `snapshot-<stamp>.json` files; those can't be compared against, and the
script now says so explicitly rather than silently reporting no changes.

Override `ARGO_PM_ROOT` to point to a different operational root if needed.

## Hand-off to other skills

When the user picks a record to act on:
- **SIR record (study to build)** → [[redcap-build]] (argo-build) to triage, build the DD, and mark build progress
- **SPR record (personnel request)** → [[redcap-admin]] (in argo-build) to assign roles
- **DATA_LINKING** → [[study-linkage]] (argo-data). Builds the master linkage table, separates safe-fills from conflicts, and reports gaps/orphans before any write-back.
- **DATA_REQUEST** → extraction via [[data-export]]
- **SUPPORT_TICKET** → triage manually; if technical, route to [[redcap-admin]]

## Weekly cadence

Recommended use: run with `--diff` every Monday morning.

```
Mon AM:  python3 portfolio.py --diff
         → review new submissions, assign to participant
         → drill into each pending-build SIR via redcap-build
Tue–Fri: builds + admin happen via argo-build
Following Mon: re-run --diff, items completed last week show as "newly done"
```

## See also
- [[redcap-build]] (argo-build) — triages and builds a specific record from this portfolio
- [[redcap-build]], [[redcap-admin]] — downstream hand-offs in argo-build
- [[token-confirmation]] (argo-core) — applied automatically by `portfolio.py` before every fetch
