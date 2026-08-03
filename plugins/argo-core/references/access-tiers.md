---
name: access-tiers
description: Decided access tiering for ARGO plugins — which skills hold a REDCap token, which never do, and which single pathway wins at each fork where two ways of doing the same thing used to be documented.
---

# Access tiers — where tokens live, and why

This is a **decision record**, not a suggestion. Tokens used to appear wherever a script happened
to reach for `os.environ`. This page decides on purpose where they live, so nobody has to
re-derive it later. [[token-optional]] still governs *behaviour* (never block on a missing token);
this page governs *placement* (which skills should have one at all).

## The two axes people conflate

Before reading the tiers, note the distinction that matters most in practice:

| | **Admin tracker REDCaps** | **A study's own REDCap project** |
|---|---|---|
| Which projects | The 5 trackers: Study Tracker (SIR), SPR, Data Linking, Data Request, Support Ticket | Every individual cohort/study project |
| Token situation | ARGO holds these already, permanently | Must be issued by a REDCap admin, per user, per project — **rarely happens in practice** |
| Example scripts | `sir_update.py`, `portfolio.py`, `backfill_sir_from_csv.py` | `fill_new_project.py`, DD upload, `data-export`, `push_updates.py` |

"We need admin support to get API access" is only ever true of the **right-hand** column. A script
that writes to the SIR needs no per-study access at all — it uses a tracker token we already hold.
Do not "simplify" tracker-facing scripts away on the grounds that tokens are hard to get; that
removes automation without removing any admin dependency.

## Tier 1 — standing access: the 5 admin trackers

Configured permanently in `~/.argo/.env`. This is the only place a token lives between uses.

- `study-portfolio/portfolio.py` — read-only weekly pull across all 5 trackers. Writes nothing back
  except a local snapshot file.
- `redcap-build/sir_update.py` — writes build progress to the **SIR record** (Study Tracker, PID 224).
  One push per build step, no batching. This is what keeps the portfolio's progress column current.
- `redcap-build/backfill_sir_from_csv.py` — bulk SIR record loads from a CSV. Same tracker token.

Low risk: these touch ARGO's own project-management records, never cohort/patient data.

## Tier 2 — occasional, one task at a time: a study's own project

No standing config. A person supplies a token because they specifically want to do one thing today,
and it isn't sitting around between uses.

- `data-export` — exports and imports against a study project
- `study-linkage` — cross-study record linkage and diff-only write-back
- `redcap-admin/set_roles.py` — role assignment on a study
- `redcap-build/fill_new_project.py` — project setup fields

**Because per-study tokens rarely materialise, the CSV-via-UI path is the documented default for
this tier and the API path is the enhancement** — not the other way round. A skill in this tier
should assume no token, produce the file the user applies in the REDCap UI, and only take the API
shortcut if a token happens to be present. See [[project-no-super-token]].

## Tier 3 — one dedicated person, extra caution: QA write-back

- `redcap-qa/push_updates.py` — the one script in the suite that can overwrite live clinical/research
  data at scale.

Two requirements, both non-negotiable:

1. **Runs under a REDCap user account with restricted, form-level permissions** — not a general
   admin account. A REDCap token only ever carries the permissions of the account that generated
   it; there is no separate way to scope a token down, so the scoping must happen on the account.
2. **The dry-run diff is mandatory and shown, enforced in code** — not an optional flag someone is
   trusted to remember. A real push is refused unless the diff for that same input was produced and
   displayed first.

## Tier 0 — no API access at all, and it should stay that way

- `run-analysis` — works entirely from local exports
- The local-file half of `redcap-build`: `dd_builder.py`, `validate_dd.py`, `validate_import.py`,
  `setup_brief.py --from-json`
- `study-setup` — document drafting only

## Which pathway wins at each fork

Every fork below used to be documented as "here are two options." Each one is now **one
instruction**. Where a second path still exists, it exists for the specific named reason given —
it is not an equal alternative, and skills must not present it as a choice to the user.

| Fork | The one path | What happened to the other |
|---|---|---|
| **Marking build progress** | `sir_update.py --mark-step <field>`, one push per step | Ticking the box by hand in the Study Tracker UI is the fallback *only* when the SIR token is absent. Not offered as a choice. |
| **HTTP client** | `argo_redcap_client.py` in `argo-core`, imported by every script | No script writes its own `urlopen` or `curl` call again. Raw `curl` survives in docs only as copy-paste for a human debugging by hand. |
| **Confirming the right project** | `confirm_token()` inside the shared client, runs automatically before any write | The prose instruction "read [[token-confirmation]] before any write" is no longer the enforcement mechanism. The check is code, not convention. |
| **Creating a personnel record** | Resolves automatically on token presence: SPR token → API import; no token → SPR survey in the UI | Still a genuine two-path operation, but the skill decides and reports what it did. Never asks the user to pick. |
| **Closing out a build** | `sir_update.py --mark-built` | `--set field=value` is a documented escape hatch for one-off corrections only, never a routine close-out path. |

## Running in Cowork vs. Claude Code

These plugins run in both, and the two environments differ in ways that change what works. All of
the below was verified empirically, not assumed.

| | **Claude Code** (local) | **Cowork** (sandboxed VM) |
|---|---|---|
| Where plugins live | `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` | `/mnt/.remote-plugins/plugin_<opaque-id>/` — the plugin **name appears only inside `.claude-plugin/plugin.json`**, never in the directory name |
| `${CLAUDE_PLUGIN_ROOT}` | set | **not set** |
| Plugin files | writable | **read-only (mode 400)** |
| `~/.argo/.env` | the user's real file | **does not exist** — `$HOME` is ephemeral per session and is not the user's Mac home |
| Shell state between commands | does not persist | does not persist (identical) |

What follows from that, and is already implemented:

- **Never locate a sibling plugin by directory name, and never by a relative `../` path.** Search
  for the *marker file* `argo_redcap_client.py`. `find_argo_core()` in the shared client, and the
  `_add_argo_core_to_path()` block at the top of each script, both do this — checking
  `ARGO_CORE_SCRIPTS`, then `/mnt/.remote-plugins`, then the local plugin cache, then the repo.
- **Never write next to a script.** The plugin directory is read-only. All state goes to an
  external location: snapshots to `$ARGO_PM_ROOT` (falling back to `~/.argo/pm`), dry-run receipts
  to `~/.argo/qa-dry-run-receipts`.
- **Don't rely on `${CLAUDE_PLUGIN_ROOT}` in a command you tell the user to run.** It's empty in
  Cowork, so the path silently becomes relative and the command fails. Locate the script instead:

  ```bash
  ARGO=$(find /mnt/.remote-plugins ~/.claude/plugins -name portfolio.py 2>/dev/null | head -1)
  python3 "$ARGO" --check
  ```

- **Always combine sourcing and running into one command.** Shell state doesn't survive between
  commands in either environment, so `source ...` on its own line is always lost.

### Credentials in Cowork

`~/.argo/.env` doesn't exist there, and that's structural — `$HOME` is ephemeral per session and
isn't the user's Mac home. So the file has to be **created**, in a folder the user connects.
That's what `argo_setup.py` is for:

```bash
python3 argo_setup.py --dir /mnt/<connected-folder>/argo-work
```

**Decided layout: one working folder, with the keys inside it.** `argo-work/` holds `.env`
alongside `exports/`, `worklists/`, `builds/` and `pm/`. One folder to connect, and the shared
client discovers the settings on its own when run from inside it. The trade-off was considered
deliberately: a connected folder is readable in full, so the keys are visible whenever that folder
is connected. That's accepted because these are admin-tracker keys for ARGO's own
project-management records rather than patient data, and nothing ever prints more than a token's
last four characters. `--separate-credentials` splits keys into their own folder for anyone who
wants the smaller footprint.

Still true regardless of layout:

- **Assume token-free by default.** Tier 2 and Tier 3 work is CSV-via-UI anyway and `run-analysis`
  is Tier 0, so most Cowork sessions need no key at all.
- **Never put a token in a command.** `argo_setup.py` takes no token argument and never prompts
  for one; keys are pasted into the file in an editor. Commands end up in history and transcripts.
- **Lookup order:** `ARGO_ENV_FILE` → working directory and its parents → `/mnt/*` →
  `~/.argo/.env`. A token exported inline for a single command always wins over any file.
- The settings file is written `0600` and git-ignored on creation.

## Credential storage convention

One file: **`~/.argo/.env`**, loaded with `set -a; source ~/.argo/.env; set +a`.

- `REDCAP_URL` — the API endpoint, shared by every project on that REDCap instance
- One variable per project, named for the project (`STUDY_INITIATION_REQUEST`,
  `STUDY_PERSONELL_REQUEST`, `DATA_LINKING_REQUEST`, `DATA_REQUEST`,
  `SUPPORT_TICKET_REQUEST`)
- Tier 2/3 study tokens are **not** stored here. They are supplied for the one task that needs them.
- Never commit this file. Never log a full token — truncate to the last 4 characters.

## The trade-off that was considered and rejected

Moving `redcap-build` to Tier 0 (no token ever) was proposed, on the grounds that it would shrink
the credential footprint. It was **rejected**: `sir_update.py` writes to an admin tracker we already
hold a token for, so dropping it would remove the automatic build-progress marking — and with it
the portfolio's live progress column — without removing a single admin-support dependency. The
credential footprint would not actually shrink. Recorded here so this doesn't get re-proposed.

See also: [[token-optional]], [[token-confirmation]], [[project-no-super-token]],
[[redcap-api-gotchas]], [[decision-protocol]].
