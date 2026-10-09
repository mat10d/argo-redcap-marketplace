---
name: redcap-api
description: Base conventions for talking to REDCap APIs across ARGO projects — token handling, record-ID safety, common curl/python patterns. Loaded transitively by other ARGO skills; rarely invoked directly.
---

# redcap-api

Shared API conventions used by every other ARGO plugin. If you are reading this directly you
probably want a more specific skill (`build-study`, `export-data`, `weekly-check`, …), or
[[start-here]] if you don't know which — but the rules below apply everywhere.

## Tokens are optional — never block on one

**No skill may hard-require a token.** If a token for the target project is present, use the API;
if not, take the no-token path (work from files downloaded off the REDCap website and produce
files the user applies in the REDCap UI) and say so. Study keys are scarce and admin-gated, so a
workflow that demands one doesn't scale. The per-operation fallbacks are in [[token-optional]];
who should hold which key, and which single path wins wherever two used to be documented, is the
decision record [[access-tiers]] — read it before adding a flag, a mode, or a "would you like
to…" prompt to any skill.

In anything the user sees, say **access key**, never "token" or "API token".

## Use the shared client — never write your own HTTP call

`argo_redcap_client.py` is the one way ARGO code talks to REDCap. Its source is
`argo-core/skills/redcap-api/scripts/`; `release.py` copies it into every skill's own `scripts/`
folder, so a script imports it from there, same-folder — never from another plugin. It handles
token lookup, `REDCAP_URL` validation, project confirmation before every write, retry/backoff
and plain-language errors.

```python
# A skill's own script, sitting at the skill root next to its scripts/ folder:
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from argo_redcap_client import RedcapClient, RedcapError

client = RedcapClient.from_env("STUDY_INITIATION_REQUEST")   # None if no key configured
if client is None:
    ...  # take the no-token path — never error out
records = client.export_records()
client.import_records(payload, expect_pid="224")   # confirms the project, then writes
```

The raw `curl` calls at the end of this page are for a human debugging by hand, not a pattern for
scripts.

## Safety rules

1. **Confirm the project before any write.** Many ARGO projects share one API endpoint; only the
   key tells them apart. The client's write methods confirm the project themselves — pass
   `expect_pid=` (or `expect_title=`) to every write call. See [[token-confirmation]].
2. **The record ID field is not always `record_id`.** Read it from the metadata before building an
   import — a wrong header silently creates new records. See [[record-id-safety]].
3. **Never show or store a full key.** Last 4 characters at most; never in a committed file, never
   in a command line.
4. **No routine writes to patient records.** RAs correct cohort data in REDCap itself; bulk record
   import is a deliberate one-off migration. See [[redcap-api-gotchas]] §0.

## References

Update these here, never in a downstream skill:

| Reference | What it holds |
|---|---|
| [[access-tiers]] | Decision record: who holds which key, which path wins at each fork, Cowork vs Claude Code facts |
| [[token-optional]] | The no-token path for each operation |
| [[project-no-super-token]] | Why project creation is always a UI step at OAU |
| [[token-confirmation]] | How the client guards every write |
| [[record-id-safety]] | Reading the real record-ID field name |
| [[redcap-api-gotchas]] | Write-side failures that are silent: overwrite modes, choice codes, renames |
| [[redcap-date-import]] | Import date format and the MDC date codes in import form |
| [[mdc-rules]] | Missing Data Codes by field type |
| [[dd-column-spec]] | Data dictionary CSV columns, field types, branching syntax |
| [[standard-roles]] | ARGO's four standard REDCap roles |
| [[build-pitfalls]] | Mistakes from real builds and ingests |
| [[decision-protocol]] | Which calls go to the user, and how |
| [[getting-files-from-redcap]] | Click-by-click downloads for the no-token path |
| [[verify-install]] | Checklist for confirming an install works, in a fresh session |

## Setup and the settings file

**The first step of any ARGO task is `--ensure`.** It costs one line when set up and does the
whole first-time setup when not:

```bash
SETUP=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name argo_setup.py 2>/dev/null | head -1)
python3 "$SETUP" --ensure
```

- **A settings file exists anywhere the tools look** → `Settings found at <path> — setup skipped.`
- **None exists** → it creates the working folder and settings file and says so, ending with where
  the user pastes their keys. The client does the same on its own the first time a key lookup
  finds no settings file, so a task started without `--ensure` still ends with a file to fill in.

Setup creates one folder per role (`project-manager/`, `qa-specialist/`, `database-manager/`,
`data-analyst/`), a `.gitignore`, and a `.env` written `0600` and never overwritten. The keys live
in that working folder, so one connected folder is all anyone needs (`--separate-credentials`
splits them out). `argo_setup.py` takes no key argument and never prompts for one — the user
pastes keys into the file in an editor, because commands end up in history and transcripts.

**Where scripts look for the settings file, in order** (the one list lives in
`settings_candidates()` in the client): `ARGO_ENV_FILE`, then `~/.argo/.env`, then
`~/argo-work/.env`, then the working directory and the two folders above it, then connected
folders under `/mnt/*` and `~/mnt/*`. A variable already exported in the shell is never
overwritten by a file. **On a Mac, `~/.argo/.env` therefore outranks the folder you are standing
in** — a script run inside a test folder loads the real keys and talks to the real REDCap. Set
`ARGO_ENV_FILE` to pin a test run to its own file. (In Cowork, `~/.argo` doesn't exist, so the
connected folder is what's found.)

## Checking the keys work

```bash
C=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name argo_redcap_client.py 2>/dev/null | head -1)
python3 "$C" --check
```

It finds the settings file itself (no `source` needed), prints one line per configured project —
title, PID, record-ID field, whether the key works — and says plainly what to do about anything
that fails. It never prints a full key. `argo_setup.py --check` reports on the settings file
itself and on which analysis languages this computer can run.

## Debugging by hand

```bash
# Project info — what a key points at
curl -X POST "$REDCAP_URL" -d "token=$TOKEN" -d "content=project" -d "format=json"
# Metadata — the data dictionary
curl -X POST "$REDCAP_URL" -d "token=$TOKEN" -d "content=metadata" -d "format=json" -d "returnFormat=json"
```
