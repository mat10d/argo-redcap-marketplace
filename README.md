# argo-redcap marketplace

Claude Code plugins for the African Research Group for Oncology (ARGO). Each plugin maps to a
role on the team, built around REDCap as the system of record for ARGO's multi-site oncology
cohorts.

New here? See **[SETUP.md](SETUP.md)** for step-by-step install and token setup.

## Plugins by role

| Role | Plugin | Skills | What it does |
|---|---|---|---|
| **Everyone** (foundation) | `argo-core` | `redcap-api` + reference docs | Shared REDCap API conventions, safety rules, and reference tables (MDC codes, standard roles, data-dictionary spec). Required by every other plugin. |
| **Builder** | `argo-build` | `redcap-build`, `redcap-admin` | Construct a data dictionary from a Word questionnaire (or audit/correct an existing one); manage user rights and roles on live projects. |
| **QA** | `argo-qa` | `redcap-qa` | Branching-logic-aware completeness QA — per-site (per-DAG) Excel worklists of applicable-but-blank fields for RAs to resolve in REDCap. |
| **Data management** | `argo-data` | `data-export`, `study-linkage` | The token-holding role. Export/import records, metadata, files, audit logs via the API (`data-export`); link records across studies/sources with safe diff-only write-back (`study-linkage`). |
| **Analyst** | `argo-analysis` | `run-analysis` | Reproducible, auditable analysis on a **local** export (no API token) — interview-driven plan, saved commented scripts (Python/R/Stata), organized outputs. |
| **Admins** (2 seats) | `argo-pm` | `study-portfolio`, `study-intake` | Weekly status dashboard across the admin REDCaps; triage a new study request into the build pipeline. |

`argo-core` is a **library** (references only) and is required by every other plugin.

## Workflow shape

```
argo-pm/study-portfolio       ← weekly dashboard across the admin REDCaps
   ↓
argo-pm/study-intake          ← triage a specific study request
   ↓
argo-build/redcap-build       ← construct DD from Word (Path A) OR audit existing CSV (Path B)
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
# 1. Copy the env template and fill in your REDCap tokens
cp .env.example ~/.argo/.env
$EDITOR ~/.argo/.env

# 2. Source it before running ARGO skills
set -a; source ~/.argo/.env; set +a

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
3. **Shared rules live once.** Anything used by more than one plugin lives in `argo-core/references/`.
4. **Portable by default.** No machine-specific paths; operational folders come from `~/.argo/.env`.

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
