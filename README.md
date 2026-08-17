# argo-redcap marketplace

Claude Code plugins for the African Research Group for Oncology (ARGO). Each plugin maps to a
role on the team, built around REDCap as the system of record for ARGO's multi-site oncology
cohorts.

New here? See **[SETUP.md](SETUP.md)** for step-by-step install and token setup.

## Plugins by role

| Role | Plugin | Skills | What it does |
|---|---|---|---|
| **Everyone** (foundation) | `argo-core` | `start-here`, `redcap-api` + reference docs | **`start-here` is the front door** — orients anyone new, runs first-time setup, routes by role/task. Plus shared API conventions, the common client, safety rules, and reference tables. Required by every other plugin. |
| **Builder** | `argo-build` | `redcap-build`, `redcap-admin` | Build a study end to end from a submitted request — triage readiness, construct/audit the data dictionary, set up files, and flip the Study Tracker's `build_tracking` flags as each step lands (`redcap-build`); manage user rights and roles on live projects (`redcap-admin`). |
| **QA** | `argo-qa` | `redcap-qa` | Branching-logic-aware completeness QA — per-site (per-DAG) Excel worklists of applicable-but-blank fields for RAs to resolve in REDCap. |
| **Data management** | `argo-data` | `data-export`, `study-linkage` | The token-holding role. Export/import records, metadata, files, audit logs via the API (`data-export`); link records across studies/sources with safe diff-only write-back (`study-linkage`). |
| **Analyst** | `argo-analysis` | `run-analysis` | Reproducible, auditable analysis on a **local** export (no API token) — interview-driven plan, saved commented scripts (Python/R/Stata), organized outputs. |
| **Admins** (2 seats) | `argo-pm` | `study-setup`, `study-portfolio` | Draft the new-study document package from canonical templates so the PM isn't the bottleneck (`study-setup`); weekly status dashboard across the admin REDCaps that also surfaces which studies are still unbuilt (`study-portfolio`). PMs set up and track — they don't build. |

`argo-core` is required by every other plugin. Anyone unsure where to begin starts with its `start-here` skill — say "help me get started with ARGO" and it takes it from there.

## Workflow shape

```
argo-pm/study-setup           ← draft the new-study document package (questionnaire, etc.) via /docx
   ↓  (PM submits the Study Initiation Request survey on REDCap)
argo-pm/study-portfolio       ← weekly dashboard; surfaces which studies are still unbuilt
   ↓
argo-build/redcap-build       ← triage SIR → build DD (Path A/B) → mark Study Tracker flags as steps land
argo-build/redcap-admin       ← assign roles, manage user rights on live projects
   ↓
(manual import)               ← load historical data, if any (dedicated ingest skill on roadmap)
   ↓
argo-qa/redcap-qa             ← continuous completeness QA on the live database
   ↓
argo-data/data-export         ← export a cohort to disk (and import/push back)
argo-data/study-linkage       ← link records across studies; safe diff-only write-back
   ↓
argo-analysis/run-analysis    ← analysis on the local export (no token needed)
```

`argo-pm` is the front door for the admins. `argo-build` does both construction and verification
— the same expertise in opposite directions.

## Setup

```bash
# 1. Create a working folder + settings file (never overwrites existing keys)
python3 plugins/argo-core/skills/redcap-api/scripts/argo_setup.py --dir ~/argo-work
$EDITOR ~/argo-work/.env        # paste in your REDCap address and tracker keys

# 2. Check it works
python3 plugins/argo-core/skills/redcap-api/scripts/argo_setup.py --check --dir ~/argo-work

# 3. Register the marketplace and install the plugins for your role
#    From a local clone of this repo:
/plugin marketplace add .
#    ...or once it's published to GitHub:
/plugin marketplace add mat10d/argo-redcap-marketplace

/plugin install argo-core@argo-redcap      # everyone
/plugin install argo-pm@argo-redcap        # admins
/plugin install argo-build@argo-redcap     # builder
/plugin install argo-qa@argo-redcap        # QA
/plugin install argo-data@argo-redcap      # data management (export/import/linkage)
/plugin install argo-analysis@argo-redcap  # analyst (local analysis, no token)
```

`.env` is gitignored — never commit tokens. See **[SETUP.md](SETUP.md)** for which tokens each
skill needs.

## The standalone bootstrap skill (Cowork / claude.ai)

Sessions can load **skills before plugins** — so a front door that lives inside the plugin suite
can't be the thing that opens it. `argo-skill/` is a self-contained skill you upload to Cowork /
claude.ai directly, separate from the marketplace. It bundles its own copies of the setup scripts
(synced automatically by `release.py`, byte-identical by test), so on any ARGO request it can:

1. run first-time setup (`--ensure` — loud when needed, one skipped line when not),
2. verify any configured access keys (`--check`),
3. find the full plugin suite in the session and route into its `start-here` front door — or say
   plainly that the plugins aren't installed and how to get them.

To install: upload the `argo-skill/` folder as a skill named **argo**. Update it whenever you
update the plugins — same release, same version.

## Distribution

A GitHub repo is the keystone for both routes below — it's the portable source.

- **Self-serve:** each teammate runs `/plugin marketplace add mat10d/argo-redcap-marketplace`
  once, then installs the plugins for their role.
- **Enterprise preload (nonprofit/enterprise account):** an org owner can push the marketplace
  and auto-enable plugins for everyone via **claude.ai → Admin Settings → Claude Code → Managed
  settings** (`extraKnownMarketplaces` + `enabledPlugins`). Teammates who sign in with org OAuth
  then get the skills with no per-laptop setup. No MDM required.

## Design principles

1. **One entry point per role.** The QA teammate shouldn't need to learn the build skill.
2. **Build and verify are unified.** `redcap-build` Path A (construct) and Path B (audit) are one skill.
3. **Shared rules live once.** Anything used by more than one plugin lives in `argo-core/skills/redcap-api/references/`.
4. **Portable by default.** No machine-specific paths; operational folders come from the settings file `argo_setup.py` creates.

## Versioning

**All six plugins and the marketplace carry the same version, always.** They are released as one
unit and there is no supported mix of old and new.

Two reasons, both concrete:

1. **They're genuinely coupled.** `argo-core` ships `argo_redcap_client.py`, which `argo-build`,
   `argo-data`, `argo-pm` and `argo-qa` all import. An old argo-core beside a new argo-build is a
   broken install, not a supported combination. Independent version numbers would advertise an
   independence that doesn't exist.
2. **It's the only way updates reliably land.** Marketplace update-detection keys off the version
   field, and a session's plugin copies are an immutable snapshot taken when the conversation
   starts. A plugin whose version didn't move may never register as changed. Bumping everything
   every time removes that failure mode entirely.

Never edit a version by hand — the numbers live in seven files and drift silently. Use:

```bash
python3 release.py                 # show current versions, and flag any drift
python3 release.py --bump patch    # fixes only
python3 release.py --bump minor    # new behaviour or new scripts
python3 release.py --bump major    # something that changes how existing things work
python3 release.py --set 1.0.0     # an exact version
```

`tests/run_all.py` fails if the versions ever disagree, so this can't quietly rot.

**After releasing, refresh the installed copies.** A running session keeps whatever it snapshotted
at the start, so a new session is needed to pick up changes — see
[[verify-install]] for the checklist to run there.

## Roadmap (not yet built)

These are intended additions, deliberately not shipped as empty skills:

- **Program-management documents** (admin): generate/track protocols, ICFs/consent forms, and DTAs.
- **Training coordination** (admin): per-site enrollment & sample-collection tracking across the
  cohort REDCaps (CRC, gastric, prostate, breast), Moodle integration, pre/post-test scoring.
- **Ingest & harmonization** (builder): paper / Stata / Excel → REDCap with variable mapping,
  unit reconciliation, and controlled-vocabulary lookups.
- **QA depth** (QA): cross-form logic checks, outlier/impossible-value detection, source-document
  audit verification, and a PM-side blocker view that QA flags feed into.
- **Analysis depth** (analyst): `run-analysis` provides the reproducible analysis workflow today;
  canned Table 1 and survival-analysis templates on top of it are the next additions.
