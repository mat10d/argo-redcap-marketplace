---
name: study-portfolio
description: Weekly portfolio tracker across ARGO's 5 admin REDCaps. Surfaces studies pending build, open personnel requests, data linking/data requests, and support tickets. Saves a JSON snapshot each run so week-over-week diffs are possible. The front door of the ARGO workflow — run this first.
---

# study-portfolio

The weekly-update skill. Pulls all 5 admin REDCaps and produces a dashboard plus a saved snapshot.

## The 5 admin REDCaps (live)

| Env var | Project | PID | Done-marker |
|---|---|---|---|
| `STUDY_INITIATION_REQUEST` | Study Initiation Request | 224 | `study_built == "Yes"` (legacy) ≡ `study_status >= 2` (current) |
| `STUDY_PERSONELL_REQUEST` | Study Personnel Request | 221 | `user_added == "Yes"` (once tracker installed) |
| `DATA_LINKING_REQUEST` | Data Linking Request | 222 | `linkage_complete == "Yes"` |
| `DATA_REQUEST` | Data Request | 223 | `data_extracted == "Yes"` |
| `SUPPORT_TICKET_REQUEST` | Support Ticket Request | 225 | `resolved == "Yes"` |

### SIR rich tracking (added during hardening)

The SIR's `internal_tracking` form was expanded with 28 fields (see `REDCap/PM/tracker-additions/SIR_internal_tracking_expansion.csv`). The dashboard now renders each SIR record as:

```
[study_status]  PID 242  6/9  Hepatectomy — PI: Alatise
```

Where:
- `study_status` is the current state (Building / In Production / Completed / Paused / Closed)
- `PID` is the new project's PID (set via `sir_update.py --pid`)
- `6/9` is per-step progress across the 9 canonical build flags
- The short name comes from `shortened_study_name`

This replaces the Active Databases Excel sheet — see [[feedback-active-dbs-deprecated]].

## How to run

```bash
set -a; source ~/.argo/.env; set +a
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-portfolio/portfolio.py            # dashboard + snapshot
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-portfolio/portfolio.py --diff     # also show diff vs last snapshot
```

## Where things land

| Artifact | Path |
|---|---|
| Snapshots | `REDCap/PM/portfolio-snapshots/snapshot-<ISO timestamp>.json` |
| Per-ticket working dirs | `REDCap/PM/tickets/<ticket-id>/` (created by [[redcap-build]]) |
| Tokens | `~/.argo/.env` (user-specific, mode 600, never committed) |

Override `ARGO_PM_ROOT` to point to a different operational root if needed.

## Hand-off to other skills

When the user picks a record to act on:
- **SIR record (study to build)** → [[redcap-build]] (argo-build) to triage, build the DD, and mark build progress
- **SPR record (personnel request)** → [[redcap-admin]] (in argo-build) to assign roles
- **DATA_LINKING** → linkage workflow (TBD, may live under `argo-analysis/linkages`)
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
