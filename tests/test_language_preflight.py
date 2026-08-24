#!/usr/bin/env python3
"""The Python / R / Stata preflight (argo_tools.py) — NITS item 10.

The defect this pins: the Cowork session shell's PATH omits /usr/local/bin, so
`command -v Rscript` reported "R is not installed" on a machine whose
/usr/local/bin/Rscript works and passes tests/test_analysis_parity.py. So the
check must find programs that PATH does not mention, must never crash on a
machine where nothing is installed, and must name all three languages in words
a non-technical analyst can act on.

    python3 tests/test_language_preflight.py
"""
from __future__ import annotations

import importlib.util
import os
import platform
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS_PATH = REPO / "plugins/argo-core/skills/redcap-api/scripts/argo_tools.py"
SCAFFOLD = REPO / "plugins/argo-data-analyst/skills/run-analysis/scaffold.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TOOLS = load(TOOLS_PATH, "argo_tools_under_test")


def fake_bin(**programs) -> Path:
    """A directory of runnable stubs: fake_bin(Rscript="4.9.9") -> Path."""
    d = Path(tempfile.mkdtemp())
    for name, version in programs.items():
        exe = d / name
        exe.write_text(f'#!/bin/sh\necho "{name} (fake) version {version}"\n')
        exe.chmod(0o755)
    return d


class TestDetectNeverRaises(unittest.TestCase):
    """A check that crashes is worse than one that says 'not found'."""

    def test_empty_path_and_nonexistent_dirs(self):
        result = TOOLS.detect(path="", known_dirs=["/no/such/place", "/nope/*/bin"],
                              probe_versions=False)
        self.assertEqual(set(result), {"python", "r", "stata"})
        for entry in result.values():
            self.assertIn("found", entry)

    def test_a_computer_with_nothing_installed_reports_not_found(self):
        empty = Path(tempfile.mkdtemp())
        result = TOOLS.detect(path=str(empty), known_dirs=[str(empty)], system="Plan9",
                              probe_versions=False)
        self.assertFalse(result["r"]["found"])
        self.assertFalse(result["stata"]["found"])
        # Python is the exception: we are running on it, so it is never reported missing.
        self.assertTrue(result["python"]["found"])
        self.assertTrue(result["python"]["path"])

    def test_garbage_search_locations_do_not_raise(self):
        for junk in ("", "   ", "***", "/", "C:/nope/*/bin", str(Path.home())):
            TOOLS.detect(path=junk, known_dirs=[junk], probe_versions=False)

    def test_probing_a_program_that_is_not_one_returns_none_not_a_crash(self):
        d = Path(tempfile.mkdtemp())
        broken = d / "brokenscript"
        broken.write_text("this is not a program\n")
        broken.chmod(0o755)
        self.assertIsNone(TOOLS.probe_version(broken, timeout=2.0))
        self.assertIsNone(TOOLS.probe_version(d / "does-not-exist", timeout=2.0))


class TestKnownLocationsAreSearched(unittest.TestCase):
    """The whole point: find what PATH doesn't mention."""

    def test_an_rscript_that_is_not_on_path_is_still_found(self):
        elsewhere = fake_bin(Rscript="4.9.9")
        result = TOOLS.detect(path="", known_dirs=[str(elsewhere)], probe_versions=True)
        r = result["r"]
        self.assertTrue(r["found"], "an installed Rscript outside PATH was reported missing — "
                                    "this is exactly the bug (NITS 10)")
        self.assertEqual(r["path"], str(elsewhere / "Rscript"))
        self.assertFalse(r["on_path"], "it was found in a known location, not on PATH")
        self.assertEqual(r["version"], "4.9.9", "the version comes from asking the program")

    def test_a_stata_that_is_not_on_path_is_still_found(self):
        elsewhere = fake_bin(**{"stata-se": "18.0"})
        result = TOOLS.detect(path="", known_dirs=[str(elsewhere)], probe_versions=False)
        self.assertTrue(result["stata"]["found"])
        self.assertEqual(result["stata"]["path"], str(elsewhere / "stata-se"))

    def test_path_wins_when_a_program_is_in_both(self):
        on_path = fake_bin(Rscript="1.1.1")
        known = fake_bin(Rscript="2.2.2")
        result = TOOLS.detect(path=str(on_path), known_dirs=[str(known)], probe_versions=False)
        self.assertEqual(result["r"]["path"], str(on_path / "Rscript"),
                         "what the user's own shell would run must be reported first")
        self.assertTrue(result["r"]["on_path"])
        self.assertIn(str(known / "Rscript"), result["r"]["paths"], "both copies are reported")

    def test_the_locations_from_the_bug_report_are_in_the_search_list(self):
        """The places NITS 10 names, and the macOS R and Stata homes."""
        posix = list(TOOLS.known_locations("Darwin"))
        for needed in ("/usr/local/bin", "/opt/homebrew/bin", "/usr/bin"):
            self.assertIn(needed, posix, f"{needed} is not searched")
        self.assertTrue(any("Stata" in p for p in TOOLS.POSIX_GLOBS),
                        "/Applications/Stata* is not searched")
        self.assertTrue(any("R.framework" in p for p in TOOLS.POSIX_GLOBS),
                        "the macOS R framework (where Rscript really lives) is not searched")

    def test_windows_locations_are_only_searched_on_windows(self):
        win = [str(p) for p in TOOLS.WINDOWS_GLOBS]
        self.assertTrue(any("R-*" in p for p in win) and any("Stata" in p for p in win))
        # Guarded by platform: a Mac must not go looking down C:/ paths.
        dirs = [str(d) for d in TOOLS.search_dirs(path="", system="Darwin")]
        self.assertFalse([d for d in dirs if d.startswith("C:")])


class TestTheReportIsPlainLanguage(unittest.TestCase):
    """An analyst reads this. It must name all three and say what to do about a gap."""

    def setUp(self):
        empty = Path(tempfile.mkdtemp())
        self.nothing = TOOLS.detect(path=str(empty), known_dirs=[str(empty)],
                                    system="Plan9", probe_versions=False)
        self.everything = TOOLS.detect(
            path=str(fake_bin(python3="3.11.9", Rscript="4.3.1", stata="18.0")),
            known_dirs=[], probe_versions=True)

    def test_all_three_languages_are_named(self):
        for result in (self.nothing, self.everything):
            text = TOOLS.report(result, say=None)
            for name in ("Python", "R", "Stata"):
                self.assertIn(name, text, f"the report never mentions {name}")

    def test_a_missing_language_comes_with_how_to_get_it(self):
        text = TOOLS.report(self.nothing, say=None)
        self.assertIn("cran.r-project.org", text, "R is free — the report must say where from")
        self.assertIn("licensed", text.lower(), "Stata's licence is why it can't just be installed")
        self.assertNotIn("Traceback", text)

    def test_full_paths_are_shown_and_recommended(self):
        text = TOOLS.report(self.everything, say=None)
        self.assertIn(self.everything["r"]["path"], text, "the full path must be in the report")
        self.assertIn("full path", text.lower(),
                      "the report must tell the reader to invoke by full path")

    def test_the_one_line_summary_says_what_is_usable(self):
        line = TOOLS.summary_line(self.everything)
        self.assertIn("Python", line)
        self.assertIn("Stata", line)
        self.assertLess(len(line.splitlines()), 2, "the summary is one line")


class TestCommandLine(unittest.TestCase):
    """It runs as a program, for the skill's preflight step."""

    def test_plain_run_reports_and_exits_zero(self):
        proc = subprocess.run([sys.executable, str(TOOLS_PATH)],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        for name in ("Python", "R", "Stata"):
            self.assertIn(name, proc.stdout)

    def test_json_is_machine_readable(self):
        import json
        proc = subprocess.run([sys.executable, str(TOOLS_PATH), "--json", "--no-versions"],
                              capture_output=True, text=True, timeout=120)
        data = json.loads(proc.stdout)
        self.assertEqual(set(data), {"python", "r", "stata"})

    def test_the_setup_check_reports_analysis_tools(self):
        """--check must surface the languages, per NITS 10."""
        work = Path(tempfile.mkdtemp()) / "argo-work"
        setup = REPO / "plugins/argo-core/skills/redcap-api/scripts/argo_setup.py"
        env = dict(os.environ, ARGO_SETUP_NO_OPEN="1")
        subprocess.run([sys.executable, str(setup), "--dir", str(work)],
                       capture_output=True, timeout=120, env=env)
        proc = subprocess.run([sys.executable, str(setup), "--check", "--dir", str(work)],
                              capture_output=True, text=True, timeout=120, env=env)
        self.assertIn("Analysis tools:", proc.stdout)
        for name in ("Python", "R", "Stata"):
            self.assertIn(name, proc.stdout)


@unittest.skipIf(platform.system() == "Windows", "the fake programs are shell scripts")
class TestScaffoldRecordsTheDetectedPaths(unittest.TestCase):
    """The generated folder must carry the full paths, so re-runs work in any session."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        (cls.tmp / "export.csv").write_text("record_id,age\n1,40\n")
        (cls.tmp / "dd.csv").write_text("Variable / Field Name,Form Name,Field Type\n"
                                        "record_id,demo,text\n")
        cls.root = cls.tmp / "study"
        cls.proc = subprocess.run(
            [sys.executable, str(SCAFFOLD), str(cls.root),
             "--export", str(cls.tmp / "export.csv"),
             "--dictionary", str(cls.tmp / "dd.csv"),
             "--tools", str(TOOLS_PATH)],
            capture_output=True, text=True, timeout=180)

    def test_it_ran(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-800:])
        self.assertNotIn("Traceback", self.proc.stdout + self.proc.stderr)

    def test_readme_carries_the_full_paths(self):
        readme = (self.root / "README.md").read_text()
        found = TOOLS.detect(probe_versions=False)
        self.assertIn("Analysis tools on this computer", readme)
        self.assertIn(found["python"]["path"], readme,
                      "the README must name the full path to Python")
        self.assertIn("full path", readme.lower())
        for name in ("Python", "R", "Stata"):
            self.assertIn(name, readme)

    def test_the_log_opens_with_what_was_detected(self):
        log = (self.root / "ANALYSIS_LOG.md").read_text()
        self.assertIn("Tools:", log)
        self.assertIn("Python", log)

    def test_without_the_check_it_still_scaffolds_and_says_so(self):
        root = self.tmp / "study2"
        proc = subprocess.run(
            [sys.executable, str(SCAFFOLD), str(root),
             "--export", str(self.tmp / "export.csv"),
             "--dictionary", str(self.tmp / "dd.csv")],
            capture_output=True, text=True, timeout=180)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        readme = (root / "README.md").read_text()
        # Without --tools the scaffold uses the vendored scripts/argo_tools.py beside it
        # (release.py syncs it in); only with no copy at all does it say "Not checked".
        vendored = SCAFFOLD.parent / "scripts" / "argo_tools.py"
        if vendored.exists():
            self.assertIn("Analysis tools on this computer", readme)
        else:
            self.assertIn("Not checked", readme)
        self.assertNotIn("{TOOLS}", readme)
        self.assertNotIn("{PYTHON}", readme)


class TestTheSkillTellsAgentsToUseIt(unittest.TestCase):
    """Doc/code agreement: the preflight is worthless if the skill still says `command -v`."""

    SKILL = REPO / "plugins/argo-data-analyst/skills/run-analysis/SKILL.md"

    def test_the_skill_runs_the_preflight_and_bans_bare_command_v(self):
        text = self.SKILL.read_text()
        self.assertIn("argo_tools.py", text, "run-analysis never runs the language check")
        self.assertIn("--tools", text, "scaffold.py is called without the language check")
        self.assertNotIn("check availability first (`command -v`)", text,
                         "the skill still tells the agent to trust `command -v`")

    def test_setup_docs_cover_the_analysis_tools(self):
        setup_md = (REPO / "SETUP.md").read_text()
        self.assertIn("cran.r-project.org", setup_md)
        for name in ("Python", "R", "Stata"):
            self.assertIn(name, setup_md)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestExploreScriptReadsBothDictionaryStyles(unittest.TestCase):
    """The scaffolded 00_explore.py must label coded fields whether the data dictionary came
    from the website download ("Field Type" headers) or the API export (field_type headers).
    A walkthrough on the API-style fixture printed "Coded fields w/ map: 0" with no warning."""

    FIXTURE = REPO / "testing" / "fixtures" / "synthetic-study"

    def _run(self, dd_path):
        tmp = Path(tempfile.mkdtemp())
        root = tmp / "study"
        proc = subprocess.run(
            [sys.executable, str(SCAFFOLD), str(root),
             "--export", str(self.FIXTURE / "records.csv"),
             "--dictionary", str(dd_path)],
            capture_output=True, text=True, timeout=180)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        run = subprocess.run([sys.executable, "scripts/00_explore.py"], cwd=root,
                             capture_output=True, text=True, timeout=180)
        self.assertEqual(run.returncode, 0, run.stderr[-800:])
        return run.stdout

    def test_api_style_headers_yield_choice_maps(self):
        try:
            import pandas  # noqa: F401
        except ImportError:
            self.skipTest("pandas not installed")
        out = self._run(self.FIXTURE / "datadictionary.csv")
        m = re.search(r"Coded fields w/ map:\s*(\d+)", out)
        self.assertIsNotNone(m, out[-600:])
        self.assertGreater(int(m.group(1)), 0, "API-style dictionary yielded no choice maps")
        self.assertNotIn("WARNING", out)

    def test_website_style_headers_yield_choice_maps(self):
        try:
            import pandas  # noqa: F401
        except ImportError:
            self.skipTest("pandas not installed")
        import csv
        src = list(csv.reader(open(self.FIXTURE / "datadictionary.csv")))
        website = ["Variable / Field Name", "Form Name", "Section Header", "Field Type",
                   "Field Label", "Choices, Calculations, OR Slider Labels", "Field Note",
                   "Text Validation Type OR Show Slider Number", "Text Validation Min",
                   "Text Validation Max", "Identifier?", "Branching Logic (Show field only if...)",
                   "Required Field?", "Custom Alignment", "Question Number (surveys only)",
                   "Matrix Group Name", "Matrix Ranking?", "Field Annotation"]
        tmp = Path(tempfile.mkdtemp()) / "dd_web.csv"
        with open(tmp, "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(website[:len(src[0])]); w.writerows(src[1:])
        out = self._run(tmp)
        m = re.search(r"Coded fields w/ map:\s*(\d+)", out)
        self.assertIsNotNone(m, out[-600:])
        self.assertGreater(int(m.group(1)), 0)
