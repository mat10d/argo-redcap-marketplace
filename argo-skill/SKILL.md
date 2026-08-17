---
name: argo
description: ARGO team bootstrap and front door. Use for ANY ARGO or REDCap-related request when no more specific ARGO skill has already been loaded — "help with ARGO", "our REDCap studies", "I'm new", "set me up", study/QA/data/build questions. Sets up the working folder and settings file, verifies access keys, finds the full ARGO plugin suite in this environment, and routes into it. Self-contained: works even when it is the only ARGO skill installed.
---

# argo — standalone bootstrap and front door

This skill exists because sessions can load *skills* before (or without) the ARGO *plugins*. It
ships its own copies of the setup scripts, so the first three steps of any ARGO session work no
matter what else is installed. The person you're helping may have never used a terminal, an API,
or a tool like this — plain words, one thing at a time, no menus of options.

## Step 0 — make sure setup exists (always, first)

The scripts are bundled in this skill's own `scripts/` folder. Locate and run them by search —
never by a hardcoded path, because every environment lays skills out differently:

```bash
SETUP=$(find /mnt/.remote-plugins /mnt/skills ~/.claude/plugins ~/skills -name argo_setup.py 2>/dev/null | head -1)
python3 "$SETUP" --ensure
```

- `Settings found at <path> — setup skipped.` → move on.
- The FIRST-TIME SETUP banner → relay it in your own words: a settings file was created at the
  path shown, with the ARGO REDCap address already filled in; they paste their access keys
  into it **in a text editor** when they have them; and most ARGO work needs no keys at all, so they can also just
  carry on.

**Never let anyone paste an access key into the chat** — it would be saved in the transcript.
In Cowork, keys persist only via a connected folder holding the settings file; anything created
in the session's own home disappears when the session ends. Say so if they ask about keys.

## Step 1 — verify any keys that are configured

If the settings file exists and this task will touch REDCap directly, check the keys work before
building anything on them:

```bash
CLIENT=$(find /mnt/.remote-plugins /mnt/skills ~/.claude/plugins ~/skills -name argo_redcap_client.py 2>/dev/null | head -1)
python3 "$CLIENT" --check
```

One line per tracker key — title, project number, whether it works — never a full key. Relay
failures in plain language; they're already written for it.

## Step 2 — find the full ARGO suite and route into it

This bootstrap doesn't do the work itself. Look for the plugin suite:

```bash
find /mnt/.remote-plugins /mnt/skills ~/.claude/plugins -path "*start-here/SKILL.md" 2>/dev/null | head -1
```

- **Found** → read that file and follow its routing table: it matches what the user said to the
  right skill (portfolio, study-setup, redcap-build, redcap-qa, data-export, study-linkage,
  run-analysis, redcap-admin) and hands off. Do what it says; your job here is done.
- **Not found** → the ARGO plugins aren't installed in this session. Say so plainly:

  > The ARGO setup and key-checking tools are here and working, but the full toolkit (study
  > dashboards, database building, QA worklists, exports, analysis) isn't installed in this
  > session. Whoever manages your ARGO tools can add it — it's the `argo-redcap` plugin
  > marketplace at github.com/mat10d/argo-redcap-marketplace.

  Then still help with what needs no toolkit: general REDCap questions, planning, and reading
  any files they share. Don't attempt to recreate a plugin skill's job from memory.

## Notes for you, the agent

- Shell state does not persist between commands in any ARGO environment. Combine any `source`
  with the command that uses it, in one line.
- The bundled `scripts/` here are exact copies of the plugin suite's shared scripts, kept in
  sync by the release process. If both are present, either copy works — they're identical.
- Don't make autonomous calls on data semantics or data-dictionary changes — surface decisions
  to the user, one at a time.
