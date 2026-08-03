#!/usr/bin/env python3
"""Set up a folder to do ARGO work in, including the file that holds your REDCap access keys.

Run this once on a new machine, or once in a new Cowork session.

    python3 argo_setup.py                          # set up ~/argo-work
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

# The admin trackers ARGO holds keys for permanently (Tier 1 in access-tiers.md).
# Single source of truth: argo_trackers.py, next to this file.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from argo_trackers import ADMIN_TRACKERS  # noqa: E402

TIER1 = [(env, f"{title}{'' if pid else ' (no key issued yet)'}")
         for env, title, pid, _marker in ADMIN_TRACKERS]

ENV_TEMPLATE = """\
# ARGO REDCap settings
#
# This file holds your REDCap access keys. Treat it like a password file:
# don't email it, don't put it in a shared folder, don't commit it to git.
#
# Fill in the values after each "=" sign. Leave any you don't have as they are —
# the ARGO tools work without them and will tell you when something needs one.
#
# After editing this file, load it into your terminal with:
#     set -a; source {env_path}; set +a

# The web address of your REDCap system. Ask your ARGO REDCap administrator.
# It usually ends in /api/ — for example: https://redcap.oauife.edu.ng/api/
REDCAP_URL=

# Where ARGO project-management files are kept on this computer.
ARGO_PM_ROOT={pm_root}

# ---------------------------------------------------------------------------
# Access keys for the ARGO admin trackers.
# Your REDCap administrator creates these — you can't generate them yourself.
# ---------------------------------------------------------------------------
{tracker_lines}

# ---------------------------------------------------------------------------
# Access keys for individual studies — THINK BEFORE ADDING ONE HERE.
#
# The keys above open ARGO's own project-management records. A study key is
# different: it opens patient data. Anything in a folder you share with Claude
# can be read in full, so a study key kept here is more exposed than a tracker
# key, for a much more sensitive project.
#
# Prefer either of these instead:
#   - supply it just for the one command that needs it, e.g.
#         CRC_TOKEN=... python3 export.py --token-env CRC_TOKEN --info
#   - or keep study keys in their own folder:
#         python3 argo_setup.py --separate-credentials
#
# If you do add one anyway, name it after the study (CRC_TOKEN=). The setup
# check will remind you it's here.
# ---------------------------------------------------------------------------
"""

README = """\
# ARGO working folder

This folder is where ARGO work happens. It was created by `argo_setup.py`.

## What's here

| Path | What it's for |
|---|---|
| `.env` | Your REDCap web address and access keys. **Private — never share or commit this.** |
| `exports/` | Data and data dictionaries downloaded from REDCap |
| `worklists/` | QA worklists sent to sites, and the ones they send back |
| `builds/` | Working files for studies being built |
| `pm/` | Portfolio snapshots and other project-management output |

## Using it

Load the settings and run a tool in **one command** — settings don't carry over between
separate commands:

```bash
set -a; source .env; set +a; python3 /path/to/portfolio.py --check
```

If you'd rather not do that each time, the ARGO tools also look for this `.env` on their own,
as long as you run them from inside this folder (or a folder within it).

## A note on privacy

Anything in a folder you connect to Claude can be read by it. That includes `.env`. If you'd
prefer your access keys to stay in a folder on their own, run:

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
                  if k not in tracker_vars and k not in ("REDCAP_URL", "ARGO_PM_ROOT")]
    if study_keys:
        print(
            f"\n⚠ This file also holds {len(study_keys)} access key(s) for individual studies:\n"
            f"    {', '.join(study_keys)}\n"
            "\n"
            "Those open patient data, unlike the tracker keys. If this folder is one you share\n"
            "with Claude, everything in it can be read — so consider supplying a study key only\n"
            "for the command that needs it, or moving study keys to their own folder:\n"
            "\n"
            f"    python3 {Path(__file__).name} --separate-credentials"
        )

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
    args = ap.parse_args()

    # With no folder named, explain and create nothing. A setup tool should never make
    # directories on someone's computer just because it was run without arguments.
    if args.dir is None:
        suggested = "/mnt/<your-connected-folder>/argo-work" if Path("/mnt").is_dir() \
            else "~/argo-work"
        print(
            "This sets up a folder to do ARGO work in, with a settings file for your REDCap\n"
            "details inside it.\n"
            "\n"
            "Tell me where to put it, and I'll create it:\n"
            "\n"
            f"    python3 {Path(__file__).name} --dir {suggested}\n"
            "\n"
            "It will create these, and change nothing that already exists:\n"
            "    exports/     data and data dictionaries downloaded from REDCap\n"
            "    worklists/   QA worklists sent to sites and returned by them\n"
            "    builds/      working files for studies being built\n"
            "    pm/          portfolio snapshots\n"
            "    .env         your REDCap web address and access keys (private to you)\n"
            "\n"
            "Nothing has been created yet — this was just an explanation."
        )
        return 0

    work_dir = Path(args.dir).expanduser()

    if args.check:
        return run_check(work_dir)

    creds_dir = Path(args.credentials_dir).expanduser() if args.separate_credentials else work_dir
    env_path = creds_dir / ".env"

    try:
        for sub in ("exports", "worklists", "builds", "pm"):
            (work_dir / sub).mkdir(parents=True, exist_ok=True)
        creds_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return int(bool(print(
            f"I couldn't create the folder {work_dir}:\n    {e}\n\n"
            "Pick somewhere you can write to with --dir, for example a folder you've connected."
        ))) or 1

    print(f"Working folder: {work_dir}")
    for sub in ("exports", "worklists", "builds", "pm"):
        print(f"  created {sub}/")

    if env_path.exists():
        print(f"\nSettings file already exists, leaving it alone: {env_path}")
        print("(Nothing was overwritten — your existing keys are untouched.)")
    else:
        tracker_lines = "\n".join(f"# {desc}\n{var}=" for var, desc in TIER1)
        write_private(env_path, ENV_TEMPLATE.format(
            env_path=env_path, pm_root=work_dir / "pm", tracker_lines=tracker_lines))
        print(f"\nSettings file: {env_path}  (only you can read it)")

    readme = work_dir / "README.md"
    if not readme.exists():
        readme.write_text(README)
        print(f"  created README.md")

    gitignore = work_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".env\n*.env\nexports/\nworklists/\n")
        print(f"  created .gitignore (so keys and patient data can't be committed by accident)")

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
