#!/usr/bin/env python3
"""Guards against documentation drifting away from the code it describes.

Every check here corresponds to a real drift found in the suite: a SKILL.md table that had
diverged from the Python it documented, and scripts that crashed instead of explaining themselves.
These are cheap to keep passing and expensive to notice by hand.

    python3 tests/test_docs_match_code.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGINS = REPO / "plugins"
PORTFOLIO_DIR = PLUGINS / "argo-pm/skills/study-portfolio"


def load_portfolio():
    os.environ.setdefault("ARGO_PM_ROOT", str(Path(os.environ.get("TMPDIR", "/tmp")) / "argo-test-pm"))
    spec = importlib.util.spec_from_file_location("portfolio_doc", PORTFOLIO_DIR / "portfolio.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPortfolioDocMatchesCode(unittest.TestCase):
    """The three drifts in finding #5, plus the build-step count drift found alongside them."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_portfolio()
        cls.doc = (PORTFOLIO_DIR / "SKILL.md").read_text()

    def test_every_tracker_in_the_code_is_documented(self):
        for env_var, *_ in self.mod.ADMIN_REDCAPS:
            self.assertIn(env_var, self.doc,
                          f"{env_var} is in ADMIN_REDCAPS but missing from SKILL.md")

    def test_the_doc_does_not_invent_trackers(self):
        known = {e for e, *_ in self.mod.ADMIN_REDCAPS}
        documented = set(re.findall(r"`([A-Z][A-Z_]{6,})`", self.doc))
        # Env vars that aren't tracker names are fine; only flag *_REQUEST/-ish tracker lookalikes.
        suspicious = {d for d in documented
                      if d.endswith(("_REQUEST", "_INITIATION")) and d not in known}
        self.assertFalse(suspicious, f"SKILL.md documents trackers the code doesn't have: {suspicious}")

    def test_done_marker_fields_match(self):
        for env_var, _label, _form, status_field, _done in self.mod.ADMIN_REDCAPS:
            row = [ln for ln in self.doc.splitlines() if f"`{env_var}`" in ln]
            self.assertTrue(row, f"no table row for {env_var}")
            self.assertIn(status_field, row[0],
                          f"SKILL.md's row for {env_var} doesn't name its real done-marker "
                          f"field {status_field!r}")

    def test_project_titles_match(self):
        for env_var, label, *_ in self.mod.ADMIN_REDCAPS:
            row = [ln for ln in self.doc.splitlines() if f"`{env_var}`" in ln]
            self.assertIn(label, row[0],
                          f"SKILL.md's row for {env_var} doesn't use the project title the code "
                          f"confirms against ({label!r})")

    def test_build_step_count_matches(self):
        n = len(self.mod.SIR_BUILD_STEPS)
        self.assertIn(f"/{n}", self.doc,
                      f"code counts {n} build steps; SKILL.md doesn't mention N/{n}")
        # The old, wrong count must not still be presented as current.
        self.assertNotIn("9 canonical build flags", self.doc)

    def test_snapshot_path_is_described_as_a_directory(self):
        # The code writes snapshot-<stamp>/summary.json, not a flat snapshot-<stamp>.json.
        self.assertIn("summary.json", self.doc,
                      "SKILL.md must document that a snapshot is a directory containing "
                      "summary.json, not a single flat file")


class TestNoBracketEnvAccess(unittest.TestCase):
    """Finding #1: os.environ['X'] raises a bare KeyError instead of explaining itself."""

    # os.environ["X"] = value is an assignment and can't raise KeyError — only reads are a problem.
    READ = re.compile(r"os\.environ\[[^\]]+\]\s*(?!=[^=])")
    ASSIGNMENT = re.compile(r"os\.environ\[[^\]]+\]\s*=[^=]")

    def test_no_script_uses_bracket_env_access(self):
        offenders = []
        for py in PLUGINS.rglob("*.py"):
            for i, line in enumerate(py.read_text().splitlines(), 1):
                if self.READ.search(line) and not self.ASSIGNMENT.search(line):
                    offenders.append(f"{py.relative_to(REPO)}:{i}")
        self.assertFalse(
            offenders,
            "These read environment variables with [], which crashes with a bare KeyError "
            "instead of a message the user can act on. Use os.environ.get() or "
            f"RedcapClient.from_env(): {offenders}",
        )


class TestHeadlessSafe(unittest.TestCase):
    """Nothing may block on typed input where there's no keyboard.

    These scripts run in agent sessions, scheduled jobs and cloud runners as well as terminals.
    A bare input() there waits forever, which looks like a hang with no explanation.
    """

    def test_every_input_call_is_guarded_by_a_tty_check(self):
        unguarded = []
        for py in PLUGINS.rglob("*.py"):
            text = py.read_text()
            if not re.search(r"(?<![\w.])input\s*\(", text):
                continue
            if "isatty" not in text:
                unguarded.append(str(py.relative_to(REPO)))
        self.assertFalse(
            unguarded,
            "These prompt for typed input without checking a keyboard is attached, so they hang "
            f"forever in a headless run: {unguarded}",
        )

    def test_cross_plugin_lookup_is_by_marker_file_not_directory_name(self):
        """Cowork names plugin dirs plugin_<opaque-id>; only the manifest holds the name.

        So any search for a directory literally called "argo-core" under a plugin root finds
        nothing there. Searching for the file argo_redcap_client.py works in every environment.
        """
        # Walking up from __file__ to find the marketplace repo layout is fine — that really is a
        # directory called argo-core. What breaks is assuming that name inside an *installed*
        # plugin tree, where Cowork uses opaque IDs and the marketplace name may differ too.
        forbidden = (
            'argo-redcap/argo-core',                     # hardcoded marketplace + plugin name
            '"argo-redcap", "argo-core"',
            '"cache" / "argo-redcap"',
            'cache/argo-redcap',
        )
        offenders = []
        for py in PLUGINS.rglob("*.py"):
            text = py.read_text()
            for i, line in enumerate(text.splitlines(), 1):
                if any(f in line for f in forbidden):
                    offenders.append(f"{py.relative_to(REPO)}:{i}")
        self.assertFalse(
            offenders,
            "These hardcode a marketplace/plugin directory name inside an installed plugin tree. "
            "Cowork's plugin directories are opaque IDs, so this finds nothing there — search for "
            f"the marker file argo_redcap_client.py instead: {offenders}",
        )

    def test_every_locator_checks_the_sandbox_plugin_root(self):
        locators = [p for p in PLUGINS.rglob("*.py")
                    if "_add_argo_core_to_path" in p.read_text() or "def find_argo_core" in p.read_text()]
        self.assertTrue(locators, "expected at least one argo-core locator")
        for py in locators:
            text = py.read_text()
            self.assertIn("/mnt/.remote-plugins", text,
                          f"{py.relative_to(REPO)} doesn't look in the sandboxed plugin root")
            self.assertIn("argo_redcap_client.py", text,
                          f"{py.relative_to(REPO)} doesn't search by marker file")

    def test_no_relative_cross_plugin_paths_in_docs(self):
        """Plugins install into separate versioned dirs — '../other-plugin' never resolves."""
        offenders = []
        for md in PLUGINS.rglob("*.md"):
            for i, line in enumerate(md.read_text().splitlines(), 1):
                if "CLAUDE_PLUGIN_ROOT}/.." in line:
                    offenders.append(f"{md.relative_to(REPO)}:{i}")
        self.assertFalse(
            offenders,
            "A path like ${CLAUDE_PLUGIN_ROOT}/../argo-core resolves inside the current plugin's "
            f"own directory, not next to it, so it never exists: {offenders}",
        )


class TestScriptsDegradeGracefully(unittest.TestCase):
    """Finding #3's smoke test: no script may traceback when run with no arguments."""

    SKIP = {"__init__.py"}

    def test_no_args_never_tracebacks(self):
        env = dict(os.environ)
        # Simulate a machine with nothing configured — the hardest case.
        for var in list(env):
            if var.endswith(("_TOKEN", "_REQUEST", "_INITIATION")) or var == "REDCAP_URL":
                env.pop(var)
        env["ARGO_PM_ROOT"] = str(Path(os.environ.get("TMPDIR", "/tmp")) / "argo-test-pm")

        failures = []
        for py in sorted(PLUGINS.rglob("*.py")):
            if py.name in self.SKIP:
                continue
            proc = subprocess.run(
                [sys.executable, str(py)],
                capture_output=True, text=True, timeout=60, env=env, cwd=str(REPO),
            )
            combined = proc.stdout + proc.stderr
            if "Traceback (most recent call last)" in combined:
                last = combined.strip().splitlines()[-1]
                failures.append(f"{py.relative_to(REPO)} → {last}")

        self.assertFalse(
            failures,
            "Run with no arguments and nothing configured, these crashed with a raw traceback "
            f"instead of explaining what was missing:\n  " + "\n  ".join(failures),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
