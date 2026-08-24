# Getting started with ARGO's Claude tools

For ARGO team members. No coding needed — you make a folder, connect it, and talk to Claude.

## 1. What you need

- **Claude desktop app** (Cowork), signed in with your ARGO account. The ARGO plugins are
  already loaded for everyone in the organization — there is nothing to install.
- That's it. (Claude Code in a terminal also works, for those who use it — same steps.)

## 2. Make a folder and connect it

1. Make a folder on your computer called **ARGO** (Desktop or Documents, wherever you like).
2. In the Claude app, connect that folder to your conversation.
3. Say: **"help me get started with ARGO"**.

Claude asks who you are on the team — project manager, QA specialist, database manager,
data analyst, or several of those — and sets the folder up for your role(s). It creates one
subfolder per role you hold, and everything you produce lands in your role's folder:

```
ARGO/
  project-manager/     new-study documents, and the templates fetched to build them
  qa-specialist/       RA worklists, audit results
  database-manager/    weekly-check snapshots, builds, exports, linkage outputs
  data-analyst/        scripts, tables, figures
  Settings (ARGO).env  your access keys (see below)
```

Your roles are remembered, so next time you just say "help me with ARGO" and continue.

## 3. Access keys

An access key is a personal password that lets Claude read a REDCap project on your behalf.
Keys are secrets: **they go into the settings file, never into the chat.**

- **Everyone on the core team** adds the **5 tracker keys** (Study Tracker and the four
  request trackers). They power the weekly check — where every study stands and what's
  waiting. Request them from the OAU REDCap administrator; setup walks you through where
  each one goes.
- **QA specialists** also add one key **for the study they are assigned to QA** — just that
  study, requested when the assignment starts.
- **Data analysts need no key at all.** You work from files downloaded from the REDCap
  website; Claude handles everything from the download.

During setup, Claude opens the settings file for you (or gives you a double-clickable
"Add keys here" shortcut). Paste each key after its `=` sign, save, and tell Claude "done" —
it verifies every key and tells you in plain words which ones work.

## 4. Check it worked

Say **"help me with ARGO"** in a fresh conversation. You should see one line confirming your
keys connect (with a version number like `ARGO toolkit 0.17.0`), then a question about what
you'd like to do. If a key fails, say "fix my key" and Claude walks you through it.

## Analysis tools (R and Stata)

Only for **data analysts** — everyone else can skip this.

- **Python** is required, and it is already on your computer: it is what the ARGO tools
  themselves run on. Nothing to install.
- **R** is optional and free. If you want your analyses written in R, install it from
  <https://cran.r-project.org> (pick the download for your computer).
- **Stata** is optional and **licensed software**, so it can't just be downloaded — ask whoever
  manages your computer to install it.

Ask **"which analysis tools do I have?"** — or just start an analysis — and Claude reports which
of the three it found, and where. It runs your scripts by the full path it found, so an analysis
never fails with "R is not installed" on a computer that has R.

## If something goes wrong

- **"I can't find your settings"** — make sure the ARGO folder is connected to the
  conversation, then say "set up ARGO" again. Setup never erases keys you already entered.
- **A key stops working** — keys expire when the administrator resets them. Request a fresh
  one and say "fix my key".
- Anything else: copy what Claude said and send it to Matteo.

---

## For the org owner (one-time, technical)

The plugins are distributed through the org marketplace. To (re)load them, push this repo via
**claude.ai → Admin Settings → Claude Code → Managed settings**:

```json
{
  "extraKnownMarketplaces": {
    "argo-redcap": { "source": { "source": "github", "repo": "mat10d/argo-redcap-marketplace" } }
  },
  "enabledPlugins": {
    "argo-core@argo-redcap": true,
    "argo-project-manager@argo-redcap": true,
    "argo-database-manager@argo-redcap": true,
    "argo-qa-specialist@argo-redcap": true,
    "argo-data-analyst@argo-redcap": true
  }
}
```

All five plugins version in lockstep; refresh the org marketplace after every release, and
verify inside a session by the `ARGO toolkit X.Y.Z` stamp in the first setup output.
Developers: see `CLAUDE.md` and `README.md` for how this repo is built and released.
