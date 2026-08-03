# Setup guide

Step-by-step setup for the ARGO REDCap plugins. Aimed at teammates who don't write code — you
only need to copy a few commands.

## 1. Prerequisites

- **Claude Code** installed and signed in.
- **Python 3.9+** (`python3 --version`). The plugins use only the standard library, except
  `argo-qa` which needs `pandas` and `openpyxl`:
  ```bash
  python3 -m pip install pandas openpyxl
  ```

## 2. Get your REDCap API tokens

A token is a per-user, per-project password for the REDCap API. In REDCap, open a project →
**API** (left menu) → request/copy your token. You need a token for each project you work on.
Tokens are secrets — never paste them into chats, scripts, or git.

## 3. Create your working folder and settings file

```bash
python3 plugins/argo-core/scripts/argo_setup.py --dir ~/argo-work
$EDITOR ~/argo-work/.env      # paste your tokens after each =
python3 plugins/argo-core/scripts/argo_setup.py --check --dir ~/argo-work
```

The setup script writes the file readable only by you (0600) and never overwrites keys you've
already filled in. Tools find the settings on their own when run from inside the folder; to load
them into a terminal by hand instead:

```bash
set -a; source ~/argo-work/.env; set +a
```

(An existing `~/.argo/.env` from an older setup keeps working — the tools check there too.)

The variable names the setup script writes are the exact names the skills read — don't rename them.
Study-project keys follow the `<NAME>_TOKEN` convention (e.g. `CRC_TOKEN`) and are passed to
tools via `--token-env CRC_TOKEN`; per [[access-tiers]], supply them per task rather than
keeping them beside the tracker keys.

## 4. Which tokens does each role need?

| Role | Plugin | Tokens needed in `~/.argo/.env` |
|---|---|---|
| Everyone | `argo-core` | `REDCAP_URL` (no tokens — it's reference material) |
| Admins | `argo-pm` | `REDCAP_URL`, `ARGO_PM_ROOT`, and the admin tokens: `STUDY_INITIATION_REQUEST`, `STUDY_PERSONELL_REQUEST`, `DATA_LINKING_REQUEST`, `DATA_REQUEST`, `SUPPORT_TICKET_REQUEST` |
| Builder | `argo-build` | `REDCAP_URL` + the token for the project you're building/administering (e.g. `CRC_TOKEN`). Study intake also uses `STUDY_INITIATION_REQUEST`. |
| QA | `argo-qa` | `REDCAP_URL` + one `<NAME>_TOKEN` per cohort you QA (e.g. `CRC_TOKEN`); pass it with `--token-env CRC_TOKEN` |
| Data management | `argo-data` | `REDCAP_URL` + one `<NAME>_TOKEN` per project you export/import/link (e.g. `CRC_TOKEN`) |
| Analyst | `argo-analysis` | **No token** — works on an export + data dictionary already on disk. Ask the data-management seat (or `argo-data`) for the export. |

**Cohort/study token convention:** add one line per project, named `<NAME>_TOKEN`
(e.g. `CRC_TOKEN=...`). QA scripts take it as `--token-env CRC_TOKEN`; data exports reference it
as `$CRC_TOKEN`.

## 5. Install the plugins

```bash
# Register the marketplace — from a local clone of this repo:
/plugin marketplace add .
# ...or once it's published to GitHub:
/plugin marketplace add mat10d/argo-redcap-marketplace

# Install argo-core (everyone) plus the plugin(s) for your role:
/plugin install argo-core@argo-redcap
/plugin install argo-pm@argo-redcap        # admins
/plugin install argo-build@argo-redcap     # builder
/plugin install argo-qa@argo-redcap        # QA
/plugin install argo-data@argo-redcap      # data management (export/import/linkage)
/plugin install argo-analysis@argo-redcap  # analyst (local analysis, no token)
```

## 6. Verify it works

In a Claude Code session, ask in plain English — e.g. *"build a REDCap data dictionary from this
Word questionnaire"* (builder), *"generate QA worklists for the CRC cohort"* (QA), or *"give me
the weekly study portfolio status"* (admin). The matching skill should activate.

If a skill reports a missing token or `ARGO_PM_ROOT is not set`, you haven't sourced `~/.argo/.env`
in that terminal — re-run `set -a; source ~/.argo/.env; set +a`.

## Team distribution (for the org owner)

To preload these for everyone on a Claude for Teams/Enterprise (nonprofit) account, push the
marketplace centrally via **claude.ai → Admin Settings → Claude Code → Managed settings**:

```json
{
  "extraKnownMarketplaces": {
    "argo-redcap": { "source": { "source": "github", "repo": "mat10d/argo-redcap-marketplace" } }
  },
  "enabledPlugins": {
    "argo-core@argo-redcap": true,
    "argo-pm@argo-redcap": true,
    "argo-build@argo-redcap": true,
    "argo-data@argo-redcap": true,
    "argo-qa@argo-redcap": true,
    "argo-analysis@argo-redcap": true
  }
}
```

Teammates who sign in with org OAuth then get the marketplace and plugins automatically — they
still create their own `~/.argo/.env` with their personal tokens (step 3). This requires the
marketplace to be on GitHub; no MDM needed.
