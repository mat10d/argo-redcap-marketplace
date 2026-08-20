#!/usr/bin/env python3
"""Set the version of every ARGO plugin and the marketplace, together.

All six plugins carry the SAME version as the marketplace. They are released as one unit
because they behave as one unit: argo-core ships the shared REDCap client that argo-build,
argo-data, argo-pm and argo-qa all import. A mix of old and new plugins is not a supported
combination, so giving them separate version numbers would describe an independence that
doesn't exist.

There is a second, practical reason. Marketplace update-detection keys off the version field,
and a session's plugin copies are an immutable snapshot taken when the conversation starts. A
plugin whose version didn't move may not register as changed, so an edit can silently fail to
reach anyone. Bumping everything, every release, makes that impossible.

    python3 release.py                 # show the current version
    python3 release.py --set 0.9.0     # set every plugin and the marketplace to 0.9.0
    python3 release.py --bump patch    # 0.8.0 -> 0.8.1
    python3 release.py --bump minor    # 0.8.0 -> 0.9.0
    python3 release.py --bump major    # 0.8.0 -> 1.0.0

Nothing is committed for you — check `git diff`, then commit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def plugin_manifests() -> list[Path]:
    return sorted(REPO.glob("plugins/*/.claude-plugin/plugin.json"))


def read_versions() -> dict[str, str]:
    versions = {}
    for manifest in plugin_manifests():
        name = manifest.parents[1].name
        versions[name] = json.loads(manifest.read_text()).get("version", "?")
    versions["(marketplace)"] = json.loads(MARKETPLACE.read_text())["metadata"].get("version", "?")
    return versions


def show() -> int:
    versions = read_versions()
    distinct = set(versions.values())
    width = max(len(n) for n in versions)
    for name, version in versions.items():
        print(f"  {name:<{width}}  {version}")
    if len(distinct) == 1:
        print(f"\nAll in step at {distinct.pop()}.")
        return 0
    print(
        f"\nThese have drifted apart ({len(distinct)} different versions).\n"
        "They're released as one unit, so they should all match. Fix with:\n"
        f"\n    python3 {Path(__file__).name} --set <version>"
    )
    return 1


SCRIPTS_SOURCE = REPO / "plugins/argo-core/skills/redcap-api/scripts"

# Every skill that runs the shared scripts carries its OWN synced copy in <skill>/scripts/.
# This is the simplification that killed cross-plugin discovery: imports are always
# "the folder I'm standing in", identical in every environment, and the four locator bugs
# (name-globbing, lexical version sort, /mnt/skills, ~/mnt) become structurally impossible.
VENDOR_TARGETS = [
    REPO / "plugins/argo-build/skills/redcap-build/scripts",
    REPO / "plugins/argo-data/skills/data-export/scripts",
    REPO / "plugins/argo-data/skills/study-linkage/scripts",
    REPO / "plugins/argo-pm/skills/study-portfolio/scripts",
    REPO / "plugins/argo-pm/skills/study-setup/scripts",
    REPO / "plugins/argo-qa/skills/redcap-qa/scripts",
]


def sync_standalone() -> None:
    """Mirror argo-core's shared scripts into every vendored copy. Drift dies at release time."""
    for target in VENDOR_TARGETS:
        target.mkdir(parents=True, exist_ok=True)
        for src in sorted(SCRIPTS_SOURCE.glob("*.py")):
            dest = target / src.name
            if not dest.exists() or dest.read_bytes() != src.read_bytes():
                dest.write_bytes(src.read_bytes())
                print(f"  synced {dest.relative_to(REPO)}")
        for dest in target.glob("*.py"):
            if not (SCRIPTS_SOURCE / dest.name).exists():
                dest.unlink()
                print(f"  removed stale {dest.relative_to(REPO)}")


def write_version(new: str) -> None:
    for manifest in plugin_manifests():
        data = json.loads(manifest.read_text())
        data["version"] = new
        manifest.write_text(json.dumps(data, indent=2) + "\n")
        print(f"  {manifest.parents[1].name} -> {new}")

    data = json.loads(MARKETPLACE.read_text())
    data["metadata"]["version"] = new
    MARKETPLACE.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  (marketplace) -> {new}")

    trackers = SCRIPTS_SOURCE / "argo_trackers.py"
    t = trackers.read_text()
    t = re.sub(r'TOOLKIT_VERSION = "[^"]*"', f'TOOLKIT_VERSION = "{new}"', t, count=1)
    trackers.write_text(t)
    print(f"  (runtime stamp) -> {new}")


def bump(current: str, part: str) -> str:
    major, minor, patch = (int(x) for x in current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Set every ARGO plugin and the marketplace to one version.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--set", metavar="X.Y.Z", help="Set an exact version everywhere")
    ap.add_argument("--bump", choices=["major", "minor", "patch"],
                    help="Raise the current version by one step")
    args = ap.parse_args()

    if not args.set and not args.bump:
        return show()

    current = json.loads(MARKETPLACE.read_text())["metadata"]["version"]

    if args.set:
        new = args.set.strip().lstrip("v")
        if not SEMVER.match(new):
            print(
                f"{args.set!r} isn't a version number I understand.\n"
                "\n"
                "Use three numbers separated by dots, like 0.9.0 — the first for big changes\n"
                "that break how things work, the second for new features, the third for fixes."
            )
            return 1
    else:
        if not SEMVER.match(current):
            print(f"The current version {current!r} isn't a plain X.Y.Z number, so I can't step "
                  f"it up. Set one explicitly with --set instead.")
            return 1
        new = bump(current, args.bump)

    print(f"Setting everything to {new} (was {current})\n")
    write_version(new)
    sync_standalone()
    print(
        "\nDone. Nothing has been committed — check `git diff`, then commit.\n"
        "Remember to refresh the installed copies afterwards, or a running session will keep\n"
        "using the versions it snapshotted when it started."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
