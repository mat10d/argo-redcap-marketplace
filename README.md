# argo-redcap marketplace

Claude plugins for the African Research Group for Oncology (ARGO), built around REDCap as the
system of record for ARGO's multi-site oncology cohorts. **Cowork (the Claude desktop app) is
the primary surface**; Claude Code works identically and is the development environment.

Team member? See **[SETUP.md](SETUP.md)** — make a folder, connect it, say "help me get
started with ARGO". Developer? Read **CLAUDE.md** first.

## The four roles

Entry is role-first: `argo-core:start-here` is the single front door. It asks who you are
(once — remembered as `ARGO_ROLES=` in the settings file; people hold several roles), then
routes into that role's skills. The workspace gets one folder per role the person holds.

| Role | What they do | Keys | Skills |
|---|---|---|---|
| **Project manager** | Monitor what studies exist; draft the new-study document package; submit new study requests | 5 tracker keys | `argo-project-manager`: `monitor-studies`, `new-study-documents` |
| **QA specialist** | Build and audit RA worklists for their assigned study | 5 trackers + their study's key | `argo-qa-specialist`: `qa-worklists` |
| **Database manager** | Fulfil outstanding requests: build REDCaps, add users, export data, **link data**. Their landing view is the request queues from the trackers | 5 trackers + study keys as needed | `argo-database-manager`: `build-study`, `manage-redcaps`, `export-data`, `link-data` |
| **Data analyst** | Cleaning, analysis, QA, figures (Stata/R/Python) on downloaded REDCap exports; linkage read-side when merging databases | **none** | `argo-data-analyst`: `run-analysis` |

`argo-core` is plumbing, not a destination: the shared client, setup, references, and the
`start-here` door. Its capabilities surface *through* the role skills; nothing in core competes
with them for triggers except the door itself.

## Workflow shape

```
project manager      new-study-documents  → draft the document package, submit the request
                     monitor-studies      → monitor: what exists, what's still unbuilt
        ↓  (request lands in the trackers)
database manager     manage-redcaps       → see outstanding requests; add users, manage rights
                     build-study          → build the REDCap from the request
                     export-data          → export a cohort to disk
                     link-data            → link records across studies (diff-only write-back)
        ↓
qa specialist        qa-worklists         → branching-aware worklists per site; audit RA returns
        ↓
data analyst         run-analysis         → scripts, tables, figures from the downloaded export
```

## Developer setup

```bash
python3 plugins/argo-core/skills/redcap-api/scripts/argo_setup.py --dir ~/argo-work
$EDITOR ~/argo-work/.env
python3 plugins/argo-core/skills/redcap-api/scripts/argo_setup.py --check --dir ~/argo-work

# Register the marketplace (local clone or GitHub) and install:
/plugin marketplace add .
/plugin install argo-core@argo-redcap   # …and the rest; all five version in lockstep
```

`.env` is gitignored — never commit keys. Org-wide distribution: managed-settings JSON in
[SETUP.md](SETUP.md).

## Versioning

**All five plugins and the marketplace carry the same version, always.** They release as one
unit; there is no supported mix of old and new.

1. **They're genuinely coupled.** Every script-bearing skill vendors the shared client from
   `argo-core`; `release.py` syncs the copies and a test fails on drift.
2. **It's the only way updates reliably land.** Update-detection keys off the version field,
   and a session snapshots its plugins at conversation start. Bumping everything every time
   removes the stale-copy failure mode; the runtime `ARGO toolkit X.Y.Z` stamp (printed by
   setup's `--ensure`/`--check`) makes staleness visible in-session.

Never edit a version by hand:

```bash
python3 release.py                 # show versions, flag drift
python3 release.py --bump patch|minor|major
python3 release.py --set 1.0.0
```

`release.py` is the only release path — it stamps versions, syncs vendored scripts, and
**refuses to complete if `tests/run_all.py` fails**.

## Testing

- **Tier 1 — deterministic, local:** `python3 tests/run_all.py`. Business logic runs against
  the committed synthetic study (`testing/fixtures/synthetic-study/`, seeded generator +
  MANIFEST of engineered counts). No network, keys, or patient data.
- **Tier 2 — Cowork rounds:** `testing/cowork/round.py` stages a fresh workspace and mines the
  session transcript afterwards. Checks agent behavior and UI, not logic.

## History note

A separately-uploaded standalone `argo` skill existed through 0.13.x and was retired on
transcript evidence (plugins load everywhere; it never fired). Resurrect from git history if a
plugin-less surface ever appears.

## Roadmap (not yet built)

- **Program-management documents** (PM): protocols, ICFs/consent forms, DTAs.
- **Training coordination** (PM): per-site enrollment & sample-collection tracking, Moodle,
  pre/post-test scoring.
- **Ingest & harmonization** (database manager): paper / Stata / Excel → REDCap with variable
  mapping and unit reconciliation.
- **QA depth**: cross-form logic checks, outlier detection, source-document audit, a PM-side
  blocker view.
- **Analysis depth**: canned Table 1 and survival templates on top of `run-analysis`.
