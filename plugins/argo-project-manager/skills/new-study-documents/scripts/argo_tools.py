#!/usr/bin/env python3
"""Which analysis languages this computer can run: Python, R and Stata.

Why this exists: the shell a Cowork session runs commands in has a thin PATH —
/usr/local/bin is often missing from it — so `command -v Rscript` answers "not
installed" on a machine where R is installed, works, and passes ARGO's own
three-language parity test. An analyst was told R was missing while
/usr/local/bin/Rscript sat right there.

So this doesn't ask PATH. It looks in the places these programs actually get
installed, reports what it found in plain words, and hands back FULL paths —
a full path runs no matter what PATH happens to contain.

    python3 argo_tools.py          # the plain-language report
    python3 argo_tools.py --json   # the same facts as JSON, for scripts

Stdlib only, and it never raises: a computer with nothing installed gets a
report that says so, not an error.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Each language: key, the name people use, the program names to look for (best
# first), and what to tell someone who hasn't got it. The install advice is
# written for someone who has never installed software from a terminal.
LANGUAGES = (
    (
        "python",
        "Python",
        ("python3", "python"),
        "Python is what ARGO's own tools are written in, so it is normally already here. "
        "If it really is missing, ask whoever manages your computer to install Python 3.",
    ),
    (
        "r",
        "R",
        ("Rscript",),
        "R is free: install it from https://cran.r-project.org (pick your computer's "
        "download), then run this check again.",
    ),
    (
        "stata",
        "Stata",
        ("stata-mp", "stata-se", "stata-be", "stata", "stata-ic",
         "StataMP", "StataSE", "StataBE", "StataIC", "Stata"),
        "Stata is licensed software, so it can't be downloaded for free — ask whoever "
        "manages your computer (IT) to install it, then run this check again.",
    ),
)

# Folders every Unix-ish machine keeps programs in. Checked IN ADDITION to PATH,
# because the session shell's PATH is not the user's login PATH.
COMMON_DIRS = (
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/usr/bin",
    "/bin",
    "/opt/local/bin",
    "/usr/local/sbin",
)

# Where R and Stata put themselves on macOS/Linux when they are NOT on PATH.
POSIX_GLOBS = (
    "/opt/R/*/bin",                                        # Posit/RStudio builds
    "/Library/Frameworks/R.framework/Resources/bin",       # macOS R (the real Rscript)
    "/Library/Frameworks/R.framework/Versions/*/Resources/bin",
    "/Applications/R.app/Contents/MacOS",                  # the R GUI's own folder
    "/Applications/Stata*/*.app/Contents/MacOS",           # StataSE.app etc.
    "/Applications/Stata*",
    "/usr/local/stata*",
    "/opt/stata*",
)

# The Windows equivalents. Only searched on Windows.
WINDOWS_GLOBS = (
    "C:/Program Files/R/R-*/bin",
    "C:/Program Files/R/R-*/bin/x64",
    "C:/Program Files (x86)/R/R-*/bin",
    "C:/Program Files/Stata*",
    "C:/Program Files (x86)/Stata*",
)

# Windows program names carry an extension, and Stata's varies by edition/bitness.
WINDOWS_SUFFIXES = (".exe", ".bat", ".cmd")
WINDOWS_NAME_GLOBS = {"r": ("Rscript.exe",), "stata": ("Stata*.exe",)}

# Version strings all look like 4.3.1 / 3.12 somewhere in the first line of output.
VERSION_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?)")

VERSION_TIMEOUT = 2.0  # seconds; a program that won't answer quickly is reported without a version


def _glob_dirs(pattern: str) -> "list[Path]":
    """Every existing directory matching one absolute pattern. Never raises.

    Plain paths ("/usr/local/bin") and patterns ("/Applications/Stata*/*.app/Contents/MacOS")
    go through here alike, so there is one code path and one place for it to be wrong.
    """
    try:
        pat = str(pattern).replace("\\", "/")
        anchor = Path(pat).anchor or "/"
        rest = pat[len(anchor):] if pat.startswith(anchor) else pat.lstrip("/")
        if not rest:
            here = Path(pat)
            return [here] if here.is_dir() else []
        return [d for d in Path(anchor).glob(rest) if d.is_dir()]
    except Exception:
        return []


def known_locations(system: "str | None" = None) -> "list[str]":
    """The install locations to check on top of PATH, for this kind of computer."""
    system = system or platform.system()
    return list(COMMON_DIRS) + list(WINDOWS_GLOBS if system == "Windows" else POSIX_GLOBS)


def search_dirs(path: "str | None" = None, known_dirs=None, system: "str | None" = None) -> "list[Path]":
    """The folders to look in, in order: PATH first, then the known install locations.

    PATH comes first so that what ARGO reports is what the user's own shell would run.
    `known_dirs` replaces the built-in install locations — it exists so the check can be
    tested against a made-up computer instead of the one the tests happen to run on.
    """
    system = system or platform.system()
    if path is None:
        path = os.environ.get("PATH", "")

    dirs: "list[Path]" = []
    for entry in (path or "").split(os.pathsep):
        entry = entry.strip()
        if entry:
            dirs.extend(_glob_dirs(entry))

    for pattern in (known_locations(system) if known_dirs is None else known_dirs):
        dirs.extend(_glob_dirs(str(pattern)))

    if known_dirs is None:
        # The interpreter running this check is, by definition, a working Python.
        try:
            dirs.extend(_glob_dirs(str(Path(sys.executable).resolve().parent)))
        except Exception:
            pass

    seen, ordered = set(), []
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            ordered.append(d)
    return ordered


def _is_runnable(candidate: Path) -> bool:
    try:
        return candidate.is_file() and os.access(str(candidate), os.X_OK)
    except Exception:
        return False


def _find_all(names, dirs, key, system) -> "list[Path]":
    """Every runnable program with one of these names, in search order. Never raises."""
    hits: "list[Path]" = []
    seen = set()

    def keep(candidate: Path) -> None:
        try:
            resolved = str(candidate)
        except Exception:
            return
        if resolved not in seen and _is_runnable(candidate):
            seen.add(resolved)
            hits.append(candidate)

    for directory in dirs:
        for name in names:
            keep(directory / name)
            if system == "Windows":
                for suffix in WINDOWS_SUFFIXES:
                    keep(directory / (name + suffix))
        if system == "Windows":
            for pattern in WINDOWS_NAME_GLOBS.get(key, ()):
                try:
                    for match in sorted(directory.glob(pattern)):
                        keep(match)
                except Exception:
                    pass
    return hits


def probe_version(program, timeout: float = VERSION_TIMEOUT) -> "str | None":
    """Ask a program its version. Returns None rather than ever failing.

    Runs with no keyboard attached (stdin closed) and from a scratch folder, so a
    program that would otherwise sit waiting for input, or write a log file into
    whatever folder we happen to be in, can't do either.
    """
    if os.environ.get("ARGO_TOOLS_NO_VERSION"):
        return None
    try:
        proc = subprocess.run(
            [str(program), "--version"],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL, cwd=tempfile.gettempdir(),
        )
    except Exception:
        return None
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    match = VERSION_RE.search(text)
    return match.group(1) if match else None


def detect(path: "str | None" = None, known_dirs=None, system: "str | None" = None,
           probe_versions: bool = True, timeout: float = VERSION_TIMEOUT) -> dict:
    """Find python3, Rscript and Stata. Returns plain data; never raises.

    {"python": {"name": "Python", "found": True, "path": "/usr/bin/python3",
                "version": "3.12.4", "on_path": True, "paths": [...], "advice": "..."} , ...}

    `path`, `known_dirs` and `system` exist so this can be run against a made-up computer
    in the tests; real callers pass nothing.
    """
    system = system or platform.system()
    dirs = search_dirs(path=path, known_dirs=known_dirs, system=system)
    path_dirs = {str(d) for entry in ((path if path is not None
                                       else os.environ.get("PATH", "")) or "").split(os.pathsep)
                 if entry.strip() for d in _glob_dirs(entry.strip())}

    versions: dict = {}
    result: dict = {}
    for key, name, names, advice in LANGUAGES:
        hits = _find_all(names, dirs, key, system)
        entry = {
            "name": name,
            "found": bool(hits),
            "path": str(hits[0]) if hits else None,
            "version": None,
            "on_path": bool(hits) and str(hits[0].parent) in path_dirs,
            "paths": [str(h) for h in hits],
            "advice": advice,
        }
        if key == "python" and not hits:
            # We are running on Python right now, so it exists whatever the folders say.
            entry.update(found=True, path=sys.executable, on_path=False,
                         paths=[sys.executable],
                         version="%d.%d.%d" % sys.version_info[:3])
        elif hits and probe_versions:
            first = entry["path"]
            if first not in versions:
                versions[first] = probe_version(first, timeout=timeout)
            entry["version"] = versions[first]
        result[key] = entry
    return result


def summary_line(result: "dict | None" = None) -> str:
    """One sentence an assistant can say out loud about this computer."""
    result = result if result is not None else detect()
    usable = [e["name"] for e in result.values() if e["found"]]
    missing = [e["name"] for e in result.values() if not e["found"]]
    if not usable:                                    # not reachable in practice
        return "No analysis language could be found on this computer."
    if not missing:
        return "Python, R and Stata are all usable on this computer."
    return (f"{' and '.join(usable) if len(usable) < 3 else ', '.join(usable)} "
            f"{'is' if len(usable) == 1 else 'are'} usable on this computer; "
            f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not installed.")


def format_report(result: "dict | None" = None, indent: str = "  ") -> str:
    """The plain-language report, as text. Full paths included — they always work."""
    result = result if result is not None else detect()
    lines = []
    for key, name, _names, _advice in LANGUAGES:
        entry = result.get(key) or {"name": name, "found": False, "advice": ""}
        if entry.get("found"):
            version = f" {entry['version']}" if entry.get("version") else ""
            lines.append(f"{indent}{entry['name']}{version} ✓  {entry.get('path')}")
        else:
            lines.append(f"{indent}{entry['name']} ✗ not found")
            advice = entry.get("advice") or ""
            for chunk in _wrap(advice, 72):
                lines.append(f"{indent}    {chunk}")
    lines.append(f"{indent}{summary_line(result)}")
    lines.append(f"{indent}Run scripts with the full path shown above — a session's PATH "
                 f"often leaves these out.")
    return "\n".join(lines)


def _wrap(text: str, width: int) -> "list[str]":
    words, line, out = text.split(), "", []
    for word in words:
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def report(result: "dict | None" = None, say=print) -> str:
    """Print the plain-language report (and return it, for callers that want the text)."""
    text = format_report(result)
    if say:
        say(text)
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Report which analysis languages (Python, R, Stata) this computer can run.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--json", action="store_true",
                    help="Print the same facts as JSON, for another script to read")
    ap.add_argument("--no-versions", action="store_true",
                    help="Skip asking each program its version number (faster)")
    args = ap.parse_args(argv)

    found = detect(probe_versions=not args.no_versions)
    if args.json:
        print(json.dumps(found, indent=2))
    else:
        print("Analysis tools on this computer:")
        report(found)
    return 0


if __name__ == "__main__":
    sys.exit(main())
