#!/usr/bin/env python3
"""Set up a folder to do ARGO work in, including the file that holds your REDCap access keys.

Run this once on a new machine, or once in a new Cowork session.

    python3 argo_setup.py --ensure                 # the usual first step: set up if not already
    python3 argo_setup.py --dir /mnt/my-folder     # set up a folder you've connected
    python3 argo_setup.py --separate-credentials   # keep keys in their own folder (see below)
    python3 argo_setup.py --check                  # see whether an existing setup works

It creates the folder structure, writes a settings file with blank spaces for your access keys,
and protects that file so only you can read it. **It never asks you to type an access key, and
you must never pass one on the command line** — anything typed as a command can end up saved in
logs and transcripts. You paste the keys into the file yourself, in a text editor.

Why a settings file at all: the ARGO tools need to know your REDCap web address and, for some
tasks, an access key. Keeping them in one file means you set them up once instead of retyping
them, and means they never appear in a command you run.
"""
from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

# The folders every ARGO workspace gets — one per ARGO role, so each person's work lands in
# their own folder. ONE list, used by scaffold, the README, and every message about it.
WORKSPACE_SUBDIRS = (
    ("project-manager",  "Portfolio snapshots, and documents for new studies"),
    ("qa-specialist",    "QA worklists sent to sites, and the ones they send back"),
    ("database-manager", "Builds, exports, user-rights files, linkage output"),
    ("data-analyst",     "Analysis scripts and their outputs, and the exports they read"),
)
WORKSPACE_DIR_NAMES = tuple(name for name, _ in WORKSPACE_SUBDIRS)

# The four ARGO roles, exactly as they may appear in ARGO_ROLES (comma-separated).
VALID_ROLES = ("project-manager", "qa-specialist", "database-manager", "data-analyst")

# The admin trackers ARGO holds keys for permanently (Tier 1 in access-tiers.md).
# Single source of truth: argo_trackers.py, next to this file.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from argo_trackers import ADMIN_TRACKERS, ARGO_REDCAP_URL, TOOLKIT_VERSION  # noqa: E402

TIER1 = [(env, f"{title}{'' if pid else ' (no key issued yet)'}")
         for env, title, pid, _marker in ADMIN_TRACKERS]

ENV_TEMPLATE = """\
# ARGO REDCap settings — private. Never share, email, or commit this file.
#
# Paste each access key after its = sign, in a text editor. Leave blank any
# you don't have — the tools say when one is needed. To load into a terminal:
#     set -a; source {env_path}; set +a

REDCAP_URL={redcap_url}
ARGO_PM_ROOT={pm_root}

# --- Your role or roles on ARGO. Set once; ARGO stops asking after that. ---
# Comma-separated, any of: project-manager, qa-specialist, database-manager, data-analyst
# e.g. ARGO_ROLES=qa-specialist,data-analyst
ARGO_ROLES=

# --- The five ARGO tracker keys — EVERYONE on the team should have these. ---
# They power the shared portfolio dashboard. Ask the ARGO REDCap administrator.
{tracker_lines}

# --- Study keys — add one for each study you are QAing. ---
# A study key lets QA pulls and exports for that study happen directly. It opens
# patient data, so keep this folder private, and ask the administrator for a key
# tied to an account that can only do what you need (export-only is often enough).
# Data analysts need no keys at all.
# Name it after the study, e.g.:
# CRC_TOKEN=
"""

README = """\
# ARGO working folder

This folder is where ARGO work happens. It was created by `argo_setup.py`.

## What's here

There's one folder per ARGO role. You'll mostly use your own — the others are there so a
folder shared with a colleague still makes sense, and so nothing lands in a surprising place.

| Path | What it's for |
|---|---|
| `.env` | Your role, your REDCap web address, and your access keys. **Private — never share or commit this.** |
| `Add keys here.command` | Double-click it: your settings file opens in a text editor. |
| `project-manager/` | Portfolio snapshots, and documents for new studies |
| `qa-specialist/` | QA worklists sent to sites, and the ones they send back |
| `database-manager/` | Builds, exports, user-rights files, linkage output |
| `data-analyst/` | Analysis scripts and their outputs, and the exports they read |

## Using it

You don't have to do anything special — the ARGO tools look for this folder's `.env` on their
own, as long as you run them from inside this folder (or a folder within it).

If you're working in a terminal and want to load the settings by hand, do it in **one command**
with whatever you're running — settings don't carry over between separate commands:

```bash
set -a; source .env; set +a; python3 /path/to/portfolio.py --check
```

## A note on privacy

Anything in a folder you connect to Claude can be read by it. That includes `.env`. The five
tracker keys are for ARGO's own project-management records, not patient data, so that trade is
usually fine. A **study key** is different — it opens patient data. If you'd rather your keys
lived somewhere on their own, run:

```bash
python3 argo_setup.py --separate-credentials
```

and connect only the working folder day to day, connecting the credentials folder only when a
task genuinely needs a key.
"""


def write_private(path: Path, content: str) -> None:
    """Write a file only the current user can read."""
    path.write_text(content)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600


def describe_mode(path: Path) -> str:
    return oct(path.stat().st_mode & 0o777)[2:]


def run_check(work_dir: Path) -> int:
    """Report on an existing setup, in plain language."""
    print(f"Looking at: {work_dir}\n" + "=" * 60)
    env_path = work_dir / ".env"
    if not env_path.exists():
        print(
            "There's no settings file here yet.\n"
            "\n"
            f"Create one by running:  python3 {Path(__file__).name} --dir {work_dir}"
        )
        return 1

    mode = describe_mode(env_path)
    print(f"Settings file: {env_path}  (permissions {mode})")
    if mode != "600":
        print("  ⚠ This file can be read by other people on this computer. Fix it with:")
        print(f"      chmod 600 {env_path}")

    filled, blank = [], []
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        (filled if value.strip() else blank).append(key.strip())

    print(f"\nFilled in ({len(filled)}): {', '.join(filled) if filled else 'nothing yet'}")
    print(f"Still blank ({len(blank)}): {', '.join(blank) if blank else 'none'}")

    tracker_vars = {env for env, _desc in TIER1}
    study_keys = [k for k in filled
                  if k not in tracker_vars
                  and k not in ("REDCAP_URL", "ARGO_PM_ROOT", "ARGO_ROLES")]
    if study_keys:
        print(f"\nStudy keys configured ({len(study_keys)}): {', '.join(study_keys)}")
        print("These open patient data — keep this folder private. The connection check\n"
              "(argo_redcap_client.py --check) verifies these too.")

    if "REDCAP_URL" in blank or "REDCAP_URL" not in filled:
        print(
            "\nThe REDCap web address is still blank, and nothing can talk to REDCap without it.\n"
            f"Open {env_path} in a text editor and put the address after 'REDCAP_URL='.\n"
            "Ask your ARGO REDCap administrator if you don't have it."
        )
        return 1

    print(
        "\nThe settings file looks reasonable. To check the keys actually work, run:\n"
        f"\n    set -a; source {env_path}; set +a; python3 argo_redcap_client.py --check"
    )
    return 0


def scaffold(work_dir: Path, creds_dir: "Path | None" = None, say=print) -> "Path | None":
    """Create the working folder and settings file. Never overwrites existing keys.

    Returns the settings file's path, or None if the folder couldn't be created.
    Safe to call repeatedly — everything that already exists is left alone.
    """
    creds_dir = creds_dir or work_dir
    env_path = creds_dir / ".env"
    try:
        for sub in WORKSPACE_DIR_NAMES:
            (work_dir / sub).mkdir(parents=True, exist_ok=True)
        creds_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        say(f"I couldn't create the folder {work_dir}:\n    {e}\n\n"
            "Pick somewhere you can write to with --dir, for example a folder you've connected.")
        return None

    if not env_path.exists():
        tracker_lines = "\n".join(f"{var}=" for var, _desc in TIER1)
        write_private(env_path, ENV_TEMPLATE.format(
            env_path=env_path, pm_root=work_dir / "project-manager",
            tracker_lines=tracker_lines, redcap_url=ARGO_REDCAP_URL))

    # A double-clickable way in for people who will never type a path: Finder -> double-click
    # "Add keys here" -> the settings file opens in TextEdit. Matters most for Cowork, whose
    # session runtime cannot open an editor on the user's screen but CAN write this file into
    # the real connected folder.
    opener = creds_dir / "Add keys here.command"
    if not opener.exists():
        opener.write_text(
            '#!/bin/bash\n'
            '# Double-click me to open your ARGO settings file in a text editor.\n'
            'open -t "$(dirname "$0")/.env" 2>/dev/null || xdg-open "$(dirname "$0")/.env"\n'
        )
        opener.chmod(0o755)

    readme = work_dir / "README.md"
    if not readme.exists():
        readme.write_text(README)
    gitignore = work_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            ".env\n*.env\nAdd keys here.command\n"
            "qa-specialist/\ndatabase-manager/\ndata-analyst/\n")
    return env_path


def find_existing_settings() -> "Path | None":
    """Whether a settings file already exists anywhere the tools look. Loads nothing.

    Delegates to the client's settings_candidates() — the one copy of the search list — so this
    can never again disagree with what load_env_file will actually find.
    """
    from argo_redcap_client import settings_candidates
    for path in settings_candidates():
        if path and path.is_file():
            return path
    return None


def open_settings_file(env_path: Path, connected: bool = False) -> None:
    """Put the freshly created settings file in front of the user so pasting keys is one step.

    On a local machine this opens the file in the default text editor. In a session runtime that
    can't reach the user's screen (Cowork, chat containers — detectable because opening fails or
    the environment is mounted), it prints exact instructions instead: the real path, how to open
    it on their computer, and to say when they've saved so the keys can be verified. It must
    never end silently — the user is holding a key with nowhere to put it. ARGO_SETUP_NO_OPEN=1
    disables entirely (test suites use it).
    """
    if os.environ.get("ARGO_SETUP_NO_OPEN"):
        return
    import shutil
    import subprocess

    def explain():
        print("\nTo add your access keys:")
        print(f"  1. On your computer, open the ARGO folder and double-click 'Add keys here' —")
        print(f"     the settings file opens in a text editor. (Or open it directly:")
        print(f"         {env_path} )")
        print("  2. Paste each key after its = sign and save the file.")
        print("  3. Tell your assistant you've saved it — it will check the keys work.")
        print("  Never paste a key into the chat itself; it would be saved in the transcript.")

    in_session_runtime = (Path("/mnt/skills").is_dir() or Path("/mnt/.remote-plugins").is_dir()
                          or (Path.home() / "mnt").is_dir() or str(Path.home()).startswith("/sessions"))
    try:
        if in_session_runtime:
            explain()
            return
        if sys.platform == "darwin":
            subprocess.run(["open", "-t", str(env_path)], check=False, timeout=10,
                           stderr=subprocess.DEVNULL)
            print(f"\nOpened {env_path.name} in your text editor — paste your keys in and save.")
        elif shutil.which("xdg-open"):
            subprocess.run(["xdg-open", str(env_path)], check=False, timeout=10,
                           stderr=subprocess.DEVNULL)
            print(f"\nOpened {env_path.name} — paste your keys in and save.")
        else:
            explain()
    except Exception:
        explain()


def set_roles(roles: str, work_dir: "Path | None" = None) -> int:
    """Record ARGO_ROLES in the settings file. Rewrites the line if it's already there."""
    env_path = (work_dir / ".env") if work_dir else find_existing_settings()
    if env_path is None or not env_path.is_file():
        print("There's no ARGO settings file yet — run this first:\n"
              f"    python3 {Path(__file__).name} --ensure")
        return 1
    wanted = [r.strip().lower() for r in roles.split(",") if r.strip()]
    unknown = [r for r in wanted if r not in VALID_ROLES]
    if unknown:
        print(f"I don't recognise these roles: {', '.join(unknown)}\n"
              f"Valid roles are: {', '.join(VALID_ROLES)}")
        return 1
    value = ",".join(dict.fromkeys(wanted))
    lines = env_path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("ARGO_ROLES="):
            lines[i] = f"ARGO_ROLES={value}"
            break
    else:
        lines.append(f"ARGO_ROLES={value}")
    write_private(env_path, "\n".join(lines) + "\n")
    print(f"Recorded your role: {value}")
    return 0


def find_connected_workspace(mnt: "Path | None" = None) -> "Path | None":
    if mnt is None:
        # Cloud sandboxes mount at /mnt; local agent mode mounts at ~/mnt.
        for root in (Path("/mnt"), Path.home() / "mnt"):
            found = find_connected_workspace(root)
            if found:
                return found
        return None
    return _find_connected_workspace_in(mnt)


def _find_connected_workspace_in(mnt: Path) -> "Path | None":
    """A folder the user connected for ARGO work, if one can be identified.

    Cowork's standing instruction to the team: create a folder on your computer for ARGO work
    and connect it to the session. Connected folders mount under /mnt and persist on the user's
    own computer — unlike the session home, which is thrown away. So setup must land there.

    Returns the folder to scaffold into, or None when nothing connected can be identified.
    Never guesses between multiple unrelated folders.
    """
    if not mnt.is_dir():
        return None
    SYSTEM = {"skills", "user-data", "knowledge", "outputs"}
    candidates = []
    for entry in sorted(mnt.iterdir()):
        if (not entry.is_dir() or entry.name.startswith(".")
                or entry.name in SYSTEM or not os.access(entry, os.W_OK)):
            continue
        candidates.append(entry)
    # A folder named for ARGO, or already holding an ARGO workspace, is unambiguous.
    for entry in candidates:
        if "argo" in entry.name.lower() or (entry / "argo-work").is_dir():
            return entry if "argo" in entry.name.lower() else entry / "argo-work"
    # Exactly one connected folder → that's the workspace they were told to connect.
    if len(candidates) == 1:
        return candidates[0] / "argo-work"
    return None


def ensure(work_dir: "Path | None" = None) -> int:
    """The default first step of any ARGO task: make sure a settings file exists.

    Already set up → one quiet line, nothing touched. Not set up → create the scaffold and say
    so LOUDLY, because the very next thing the user must do is paste their keys in.
    """
    existing = find_existing_settings()
    if existing:
        print(f"Settings found at {existing} — setup skipped. (ARGO toolkit {TOOLKIT_VERSION})")
        return 0

    connected = None
    if work_dir is None:
        override = os.environ.get("ARGO_WORK_DIR")
        if override:
            work_dir = Path(override).expanduser()
        else:
            connected = find_connected_workspace()
            work_dir = connected or Path("~/argo-work").expanduser()
    env_path = scaffold(work_dir)
    if env_path is None:
        return 1
    print("=" * 64)
    print(f" FIRST-TIME SETUP — one thing to do before ARGO tools can")
    print(f" talk to REDCap.  (ARGO toolkit {TOOLKIT_VERSION})")
    print()
    print(" I created your settings file:")
    print()
    print(f"     {env_path}")
    print()
    print(" The ARGO REDCap address is already filled in. Open the file in a")
    print(" text editor and paste your access keys after their = signs.")
    print(" Don't type keys as commands — commands get saved in transcripts.")
    print()
    print(" Everyone on the ARGO team should have the five tracker keys —")
    print(" they power the shared study dashboard. Your REDCap administrator")
    print(" issues them. Nothing is blocked without them: every ARGO task also")
    print(" works from files downloaded off the REDCap website.")
    print()
    if connected:
        print(" This is inside the folder you connected, so it lives on YOUR")
        print(" computer and keeps your keys between sessions.")
    else:
        print(" NOTE — this session may be temporary, and this file would then")
        print(" disappear when it ends. The ARGO way to keep your keys: create")
        print(" a folder on your computer for ARGO work, connect it to the")
        print(" session, and run setup again — it will move in there.")
    print("=" * 64)
    open_settings_file(env_path, connected=bool(connected))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Set up a folder for ARGO work, including your REDCap settings file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--dir", default=None,
                    help="The folder to set up. Suggested: ~/argo-work")
    ap.add_argument("--separate-credentials", action="store_true",
                    help="Put the settings file in its own folder, so you can connect the working "
                         "folder without exposing your access keys")
    ap.add_argument("--credentials-dir", default="~/argo-credentials",
                    help="Where the settings file goes when --separate-credentials is used")
    ap.add_argument("--check", action="store_true",
                    help="Report on an existing setup instead of creating one")
    ap.add_argument("--ensure", action="store_true",
                    help="The default first step of any ARGO task: if a settings file exists "
                         "anywhere the tools look, do nothing; otherwise create one and say so "
                         "loudly. Safe to run every time.")
    ap.add_argument("--set-roles", default=None, metavar="ROLES",
                    help="Record who this person is on ARGO, comma-separated: "
                         "project-manager, qa-specialist, database-manager, data-analyst. "
                         "Asked once by start-here; written into the settings file so nobody "
                         "is ever asked again.")
    args = ap.parse_args()

    if args.ensure:
        return ensure(Path(args.dir).expanduser() if args.dir else None)

    if args.set_roles is not None:
        return set_roles(args.set_roles,
                         Path(args.dir).expanduser() if args.dir else None)

    # --check must work without --dir: report on whatever settings the tools would find.
    if args.check and args.dir is None:
        found = find_existing_settings()
        if found:
            return run_check(found.parent)
        print("I couldn't find an ARGO settings file anywhere yet.\n"
              f"Run:  python3 {Path(__file__).name} --ensure")
        return 1

    # With no folder named, explain and create nothing. A setup tool should never make
    # directories on someone's computer just because it was run without arguments.
    if args.dir is None:
        suggested = "/mnt/<your-connected-folder>/argo-work" if Path("/mnt").is_dir() \
            else "~/argo-work"
        folder_lines = "\n".join(f"    {name + '/':<19}{desc}"
                                 for name, desc in WORKSPACE_SUBDIRS)
        print(
            "This sets up a folder to do ARGO work in, with a settings file for your REDCap\n"
            "details inside it.\n"
            "\n"
            "Tell me where to put it, and I'll create it:\n"
            "\n"
            f"    python3 {Path(__file__).name} --dir {suggested}\n"
            "\n"
            "It will create one folder per ARGO role, and change nothing that already exists:\n"
            f"{folder_lines}\n"
            "    .env               your REDCap web address and access keys (private to you)\n"
            "\n"
            "Nothing has been created yet — this was just an explanation."
        )
        return 0

    work_dir = Path(args.dir).expanduser()

    if args.check:
        return run_check(work_dir)

    creds_dir = Path(args.credentials_dir).expanduser() if args.separate_credentials else work_dir
    env_existed = (creds_dir / ".env").exists()
    env_path = scaffold(work_dir, creds_dir)
    if env_path is None:
        return 1

    print(f"Working folder: {work_dir}")
    for sub in WORKSPACE_DIR_NAMES:
        print(f"  created {sub}/")
    if env_existed:
        print(f"\nSettings file already exists, leaving it alone: {env_path}")
        print("(Nothing was overwritten — your existing keys are untouched.)")
    else:
        print(f"\nSettings file: {env_path}  (only you can read it)")
        open_settings_file(env_path)

    print("\n" + "=" * 60)
    print("Next step — put your REDCap details in, using a text editor:\n")
    print(f"    {env_path}\n")
    print("You need at least the REDCap web address (REDCAP_URL). Access keys are optional —")
    print("most ARGO work is done by downloading files from the REDCap website instead.")
    print("\nDon't type your keys as a command; open the file and paste them in. Then check it:\n")
    print(f"    python3 {Path(__file__).name} --check --dir {creds_dir}")
    if args.separate_credentials:
        print(
            f"\nYour keys are in {creds_dir}, separate from your work in {work_dir}.\n"
            "Connect only the working folder day to day; connect the credentials folder just for\n"
            "the tasks that genuinely need a key."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
