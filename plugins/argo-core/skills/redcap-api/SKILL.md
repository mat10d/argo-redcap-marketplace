---
name: redcap-api
description: Base conventions for talking to REDCap APIs across ARGO projects — token handling, record-ID safety, common curl/python patterns. Loaded transitively by other ARGO skills; rarely invoked directly.
---

# redcap-api

Shared API conventions used by every other ARGO plugin. If you are reading this directly you probably want a more specific skill (`build-study`, `export-data`, `monitor-studies`, etc.), or [[start-here]] if you don't know which — but the rules below apply universally.

## Tokens are optional — never block on one

Study-project keys are scarce and admin-gated; requesting one per study doesn't scale, and the
five admin-tracker keys — which everyone on the team holds — are the exception, not the model.
**No skill may hard-require a token.** Check whether a token for the target project is present — if it is, use the
API; if not, take the no-token path (work from an on-disk export/download and produce files the
user applies in the REDCap UI) and say so. Never error out demanding a token. This is the single
most important cross-cutting rule — see **[[token-optional]]** for the per-operation fallback table.

Where tokens should live at all (which skills hold one permanently, which get one for a single
task, which never touch the API) is decided in **[[access-tiers]]**. That page also records which
single pathway wins wherever two ways of doing the same thing used to be documented — read it
before adding a flag, a mode, or a "would you like to…" prompt to any skill.

## Use the shared client — do not write your own HTTP call

`argo_redcap_client.py` (in `argo-core/skills/redcap-api/scripts/`) is the one way ARGO code talks to REDCap. It
handles token lookup, `REDCAP_URL` validation, automatic project confirmation before writes,
retry/backoff, and plain-language errors. **No script should write its own `urlopen` or `curl`
call.** The raw `curl` snippets further down this page are for a human debugging by hand, not a
pattern for new scripts to copy.

```python
import sys; sys.path.insert(0, ...)  # see any ARGO script for the resolve_argo_core() helper
from argo_redcap_client import RedcapClient, TokenMissing

client = RedcapClient.from_env("STUDY_INITIATION_REQUEST")   # None if no token configured
if client is None:
    ...  # take the no-token path — never error out
records = client.export_records()
client.import_records(payload, expect_title="Study Tracker")  # confirms the project first
```

## Critical safety rules

### 1. Confirm the target project token before any write
Multiple ARGO projects (admin REDCaps, cohort REDCaps, dev copies) use the same API endpoint. Before any call that imports, modifies, or deletes data: read back the project's `project_info` and confirm the title/PID matches what the user intended. See [[token-confirmation]].

The shared client does this for you — pass `expect_title=` to any write method and it will refuse
to post if the token points somewhere else. Do not re-implement this check per script.

### 2. Do not assume the record ID field is named `record_id`
Some ARGO projects use `study_id`, `participant_id`, `mrn`, etc. Always export metadata and read the first field name before constructing imports. See [[record-id-safety]].

### 3. Never log full API tokens
Truncate to last 4 chars when echoing. Never write tokens to files committed to git.

## Reference tables

These live in `references/` and are linked from skills in `argo-database-manager`, `argo-project-manager`, etc. Update them here, not in the downstream skills:

- [[token-optional]] — **cross-cutting:** use the API only when a token is present; else fall back to files + UI
- [[access-tiers]] — **decision record:** which skills hold tokens, and which pathway wins at each fork
- [[verify-install]] — checklist for confirming an install works, to run in a **fresh** session
- [[getting-files-from-redcap]] — click-by-click download instructions for the no-token path
- [[mdc-rules]] — Missing Data Codes by field type
- [[standard-roles]] — ARGO's four standard REDCap roles
- [[dd-column-spec]] — Data dictionary CSV column reference

## Common patterns

### Export metadata
```bash
curl -X POST "$REDCAP_URL" \
  -d "token=$TOKEN" -d "content=metadata" -d "format=json" -d "returnFormat=json"
```

### Export project info (for token confirmation)
```bash
curl -X POST "$REDCAP_URL" \
  -d "token=$TOKEN" -d "content=project" -d "format=json"
```

## First-time setup

**The default first step of any ARGO task is `--ensure`** — run it before anything else, every
time. It costs one line when set up, and does the whole first-time setup when not:

```bash
SETUP=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name argo_setup.py 2>/dev/null | head -1)
python3 "$SETUP" --ensure
```

- **Settings file exists anywhere the tools look** → `Settings found at <path> — setup skipped.`
  Nothing touched.
- **Nothing exists** → it creates the working folder and settings file and says so LOUDLY, ending
  with exactly where the user should paste their REDCap address and keys.

Scripts that need a key also do this on their own: the shared client scaffolds the settings file
automatically the first time a token lookup finds no settings file at all. So even a task started
without `--ensure` ends with a file to fill in, never a dead end.

To set up a specific folder instead (e.g. a connected folder), the explicit form still exists.

```bash
python3 argo_setup.py --dir ~/argo-work          # local
python3 argo_setup.py --dir /mnt/<folder>/argo-work   # a folder connected in Cowork
```

It creates one folder per ARGO role — `project-manager/`, `qa-specialist/`, `database-manager/`,
`data-analyst/` — a `.gitignore`, and a `.env` holding the
REDCap web address and any access keys — written `0600`, and never overwritten if it already
exists. **The keys live in the working folder** so one connected folder is all anyone needs;
`--separate-credentials` splits them out for anyone who wants a smaller footprint.

`argo_setup.py` never asks for a token interactively and takes no token argument, deliberately:
anything typed as a command can end up in shell history and transcripts. The user pastes keys into
the file in an editor. Then:

```bash
python3 argo_setup.py --check --dir ~/argo-work
```

Once the file exists, scripts find it on their own — the shared client searches `ARGO_ENV_FILE`,
the working directory and its parents, `/mnt/*`, and `~/.argo/.env`. Sourcing it by hand still
works and still wins.

## Checking your setup works

Before doing anything else on a new machine, or if a skill says it can't reach REDCap:

```bash
C=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name argo_redcap_client.py 2>/dev/null | head -1)
python3 "$C" --check
```

(No `source` line needed — the client finds the settings file itself.)

This prints one line per configured project — its title, its record-ID field name, and whether the
token works — and says plainly what to do about anything that fails. It never prints a full token.

## Settled decisions

These were open questions during early pilot. They are now decided; see [[access-tiers]] for the
full decision record.

- **Shared Python client, not raw curl.** `argo_redcap_client.py` is the one HTTP path. Raw `curl`
  remains in docs only for humans debugging by hand.
- **Credentials live in the ARGO working folder's settings file** (`.env` inside it), one
  variable per project. The tools find it themselves; `set -a; source <file>; set +a` still
  works and still wins. Everyone holds the five tracker keys; a study key is added per QA
  assignment ([[access-tiers]] Tier 2). Tier 3 write-back keys are still supplied per task.
- **Token check ships as `--check` on the shared client** (above) rather than a separate slash
  command, so it lives next to the code it validates.
