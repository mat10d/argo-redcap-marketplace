#!/usr/bin/env python3
"""The analysis registry, the scaffolded library, and the docs that describe them.

0.20 turns run-analysis from "write the statistics into every study script" into
"call the library" — and the thing that makes that safe is the registry: one file
per analysis in `run-analysis/analyses/`, saying whether it is READY or PLANNED.
Three failures this pins:

* claiming a planned analysis exists (the old SKILL.md roadmap read like a feature
  list; survival is the one that must never be offered as if it were built),
* a study script that re-derives its own statistics instead of calling the library
  (two studies, two different Table 1s, from the same export),
* guessing the grouping variable. "By site" and "by district" are different tables
  and both look right. It is asked once, explicitly, and passed to --group-by.

The library modules themselves are built alongside this; where a check needs them,
it SKIPS with a plain message rather than failing, so the registry and the scaffold
can be tested before lib/ lands.

    python3 tests/test_analysis_registry.py
"""
from __future__ import annotations

import ast
import datetime
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO / "plugins/argo-data-analyst/skills/run-analysis"
SKILL_MD = SKILL_DIR / "SKILL.md"
SCAFFOLD = SKILL_DIR / "scaffold.py"
ANALYSES = SKILL_DIR / "analyses"
LIB = SKILL_DIR / "lib"
FIXTURE = REPO / "testing" / "fixtures" / "synthetic-study"
TOOLS = REPO / "plugins/argo-core/skills/redcap-api/scripts/argo_tools.py"


def load_scaffold():
    spec = importlib.util.spec_from_file_location("scaffold_registry_under_test", SCAFFOLD)
    module = importlib.util.module_from_spec(spec)
    sys.modules["scaffold_registry_under_test"] = module
    spec.loader.exec_module(module)
    return module


SCAFFOLD_MOD = load_scaffold()


def statements(text: str) -> list:
    """Top-level statements in a script, ignoring its docstring and its imports.

    Counted as statements rather than lines so that wrapping a long call, or a
    variable list that runs to three lines, can't make a short script look long.
    """
    tree = ast.parse(text)
    out = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            continue  # the module docstring
        out.append(ast.get_source_segment(text, node) or type(node).__name__)
    return out


# ---------------------------------------------------------------- the registry itself

class TestTheRegistryFilesParse(unittest.TestCase):
    """One file per analysis, each with a machine-readable front matter block."""

    REQUIRED = ("name", "status", "summary", "python_module", "r_module")

    def test_the_registry_folder_exists_with_both_analyses(self):
        self.assertTrue(ANALYSES.is_dir(), f"no analysis registry at {ANALYSES}")
        names = {p.stem for p in ANALYSES.glob("*.md")}
        self.assertIn("table1", names)
        self.assertIn("survival", names)

    def test_every_entry_has_the_required_front_matter(self):
        for path in sorted(ANALYSES.glob("*.md")):
            with self.subTest(analysis=path.stem):
                fields = SCAFFOLD_MOD.parse_front_matter(path)
                self.assertTrue(fields, f"{path.name} has no `---` front matter block")
                for key in self.REQUIRED:
                    self.assertIn(key, fields, f"{path.name} is missing `{key}:`")
                self.assertIn(fields["status"], ("ready", "planned"),
                              f"{path.name}: status must be ready or planned")
                self.assertEqual(fields["name"], path.stem,
                                 "the file name and the `name:` field must agree")

    def test_read_registry_sorts_ready_before_planned(self):
        entries = SCAFFOLD_MOD.read_registry(ANALYSES)
        self.assertTrue(entries, "read_registry() found nothing")
        statuses = [e["status"] for e in entries]
        self.assertEqual(statuses, sorted(statuses, key=lambda s: s != "ready"),
                         "ready analyses must be listed before planned ones")
        by_name = {e["name"]: e for e in entries}
        self.assertEqual(by_name["table1"]["status"], "ready")
        self.assertEqual(by_name["survival"]["status"], "planned")

    def test_survival_is_planned_and_says_so_in_one_line(self):
        text = (ANALYSES / "survival.md").read_text()
        self.assertIn("planned", text.lower())
        self.assertIn("Kaplan", text, "the scope note must name Kaplan–Meier")
        self.assertIn("Cox", text, "the scope note must name Cox")
        self.assertIn("not built yet", text.lower(),
                      "a planned analysis must say, in words, that it does not exist")
        self.assertIn("Survival analysis is planned but not built yet", text,
                      "the registry must carry the exact message the stub raises")

    def test_table1_states_what_it_needs_from_the_user(self):
        text = (ANALYSES / "table1.md").read_text()
        self.assertIn("REQUIRED", text, "the grouping variable must be marked REQUIRED")
        lowered = text.lower()
        self.assertIn("asked once", lowered, "table1 must say the grouping variable is asked once")
        self.assertIn("--group-by", text, "table1 must say how the answer reaches the scaffold")
        self.assertIn("demographics", lowered,
                      "the variable list must state its default (the demographics form)")

    def test_table1_states_the_files_it_produces(self):
        text = (ANALYSES / "table1.md").read_text()
        self.assertIn("outputs/tables/table1.xlsx", text)
        self.assertIn(".png", text)
        self.assertIn("Notes", text, "the workbook's Notes sheet is part of what it produces")

    def test_table1_gives_the_exact_lib_calls_in_both_languages(self):
        text = (ANALYSES / "table1.md").read_text()
        self.assertIn("```python", text, "no Python call block")
        self.assertIn("```r", text.lower(), "no R call block")
        for call in ("load_study", "apply_missing", "table1(", "write_workbook", "bar_by_group"):
            self.assertIn(call, text, f"the registry never shows the {call} call")
        self.assertIn("argo_analysis.core", text, "the Python import path is not shown")
        self.assertIn("argo_analysis", text.replace("argo_analysis.core", ""),
                      "the R source path is not shown")


class TestTheRegistryPointsAtRealModules(unittest.TestCase):
    """Every registry entry names a module that exists — once the library is built."""

    def _check(self, root: Path, language: str, rel_for):
        """Every registry entry names a module file that is really there.

        A READY analysis whose module is missing is a broken registry and fails. A
        PLANNED one may not have been stubbed yet, so it skips with a plain message
        instead — the library and the registry are built in parallel.
        """
        if not root.is_dir():
            self.skipTest(f"the {language} library isn't built yet ({root} does not exist) — "
                          f"this check runs once {root.name}/argo_analysis/ lands")
        for entry in SCAFFOLD_MOD.read_registry(ANALYSES):
            with self.subTest(analysis=entry["name"]):
                target = root / rel_for(entry)
                if target.is_file():
                    continue
                message = (f"{entry['name']}.md names a {language} module that does not "
                           f"exist: {target}")
                if entry.get("status") == "ready":
                    self.fail(message)
                self.skipTest(message + " (planned — not stubbed yet)")

    def test_python_modules_exist(self):
        self._check(LIB / "python", "Python",
                    lambda e: Path(*e["python_module"].split(".")).with_suffix(".py"))

    def test_r_modules_exist(self):
        self._check(LIB / "R", "R", lambda e: Path(e["r_module"]))


# ---------------------------------------------------------------- the scaffold

class TestScaffoldCopiesTheLibraryIn(unittest.TestCase):
    """A study folder must stand alone: the library is COPIED, not referenced."""

    def test_copy_library_copies_both_languages_and_skips_pycache(self):
        src = Path(tempfile.mkdtemp()) / "lib"
        (src / "python" / "argo_analysis").mkdir(parents=True)
        (src / "R" / "argo_analysis").mkdir(parents=True)
        (src / "python" / "argo_analysis" / "core.py").write_text("# python side\n")
        (src / "R" / "argo_analysis" / "core.R").write_text("# R side\n")
        (src / "python" / "argo_analysis" / "__pycache__").mkdir()
        (src / "python" / "argo_analysis" / "__pycache__" / "core.pyc").write_text("junk")

        root = Path(tempfile.mkdtemp()) / "study"
        root.mkdir()
        original = SCAFFOLD_MOD.LIB_SOURCE
        try:
            SCAFFOLD_MOD.LIB_SOURCE = src
            self.assertTrue(SCAFFOLD_MOD.copy_library(root))
        finally:
            SCAFFOLD_MOD.LIB_SOURCE = original
        self.assertTrue((root / "lib" / "python" / "argo_analysis" / "core.py").is_file())
        self.assertTrue((root / "lib" / "R" / "argo_analysis" / "core.R").is_file())
        self.assertFalse((root / "lib" / "python" / "argo_analysis" / "__pycache__").exists(),
                         "compiled junk must not be copied into a study folder")

    def test_copy_library_says_no_rather_than_crashing_when_there_is_no_library(self):
        root = Path(tempfile.mkdtemp()) / "study"
        root.mkdir()
        original = SCAFFOLD_MOD.LIB_SOURCE
        try:
            SCAFFOLD_MOD.LIB_SOURCE = Path(tempfile.mkdtemp()) / "nothing-here"
            self.assertFalse(SCAFFOLD_MOD.copy_library(root))
        finally:
            SCAFFOLD_MOD.LIB_SOURCE = original


class TestTheDefaultVariableListReadsBothDictionaryStyles(unittest.TestCase):
    """A REDCap data dictionary comes with website headers OR API headers. The
    default variable list must be found either way — the same defect that once made
    00_explore.py report "Coded fields w/ map: 0" on an API-style dictionary."""

    # The website header for the choices column contains commas, so REDCap quotes
    # it — the fixture must too, or the columns shift and nothing lines up.
    WEBSITE = ("Variable / Field Name,Form Name,Field Type,"
               "\"Choices, Calculations, OR Slider Labels\","
               "Text Validation Type OR Show Slider Number\n"
               "pid,demographics,text,,\n"
               "age,demographics,text,,integer\n"
               "sex,demographics,radio,\"1, Male | 2, Female\",\n"
               "notes,demographics,notes,,\n"
               "site,demographics,text,,\n"
               "stage,clinical,radio,\"1, I | 2, II\",\n")

    API = ("field_name,form_name,field_type,select_choices_or_calculations,"
           "text_validation_type_or_show_slider_number\n"
           "pid,demographics,text,,\n"
           "age,demographics,text,,integer\n"
           "sex,demographics,radio,\"1, Male | 2, Female\",\n"
           "notes,demographics,notes,,\n"
           "site,demographics,text,,\n"
           "stage,clinical,radio,\"1, I | 2, II\",\n")

    def _resolve(self, text):
        path = Path(tempfile.mkdtemp()) / "dd.csv"
        path.write_text(text)
        return path, SCAFFOLD_MOD.demographics_variables(path, "site")

    def test_both_header_styles_give_the_same_list(self):
        _, website = self._resolve(self.WEBSITE)
        _, api = self._resolve(self.API)
        self.assertEqual(website, api)
        self.assertEqual(website, ["age", "sex"],
                         "the record ID, the grouping variable, free text and notes are "
                         "not Table 1 rows")

    def test_only_the_demographics_form_is_taken(self):
        _, fields = self._resolve(self.API)
        self.assertNotIn("stage", fields, "a field from another form leaked into the default")

    def test_the_figure_field_prefers_a_real_choice_list(self):
        path, fields = self._resolve(self.API)
        self.assertEqual(SCAFFOLD_MOD.figure_field(path, fields), "sex")

    def test_an_unreadable_dictionary_yields_nothing_rather_than_a_guess(self):
        missing = Path(tempfile.mkdtemp()) / "nope.csv"
        self.assertEqual(SCAFFOLD_MOD.demographics_variables(missing), [])
        self.assertEqual(SCAFFOLD_MOD.figure_field(missing, ["age"]), "")


class TestScaffoldedStudyFolder(unittest.TestCase):
    """One real scaffold run, with a grouping variable, inspected."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = cls.tmp / "study"
        cls.proc = subprocess.run(
            [sys.executable, str(SCAFFOLD), str(cls.root),
             "--export", str(FIXTURE / "records.csv"),
             "--dictionary", str(FIXTURE / "datadictionary.csv"),
             "--group-by", "redcap_data_access_group"],
            capture_output=True, text=True, timeout=180)

    def test_it_ran(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-800:])
        self.assertNotIn("Traceback", self.proc.stdout + self.proc.stderr)

    def test_the_library_lands_in_the_study_folder(self):
        if not LIB.is_dir():
            self.skipTest(f"the library isn't built yet ({LIB} does not exist) — this check "
                          "runs once run-analysis/lib/ lands")
        self.assertTrue((self.root / "lib").is_dir(),
                        "scaffold.py did not copy lib/ into the study folder")
        for language in ("python", "R"):
            if (LIB / language).is_dir():
                self.assertTrue((self.root / "lib" / language).is_dir(),
                                f"lib/{language} was not copied into the study folder")

    def test_it_writes_a_short_table1_script_of_library_calls(self):
        script = self.root / "scripts" / "01_table1.py"
        self.assertTrue(script.is_file(), "no scripts/01_table1.py was generated")
        text = script.read_text()
        compile(text, str(script), "exec")  # it must at least be valid Python

        self.assertIn('sys.path.insert(0, str(HERE / "lib" / "python"))', text,
                      "the generated script must import from the study's own ./lib")
        self.assertIn("from argo_analysis", text)

        body = statements(text)
        self.assertLessEqual(len(body), 15,
                             "01_table1.py must be ~15 statements of library calls, not an "
                             "analysis in itself:\n" + "\n---\n".join(body))
        for call in ("load_study", "apply_missing", "table1(", "write_workbook", "bar_by_group"):
            self.assertIn(call, text, f"the generated script never calls {call}")

    def test_the_generated_script_computes_nothing_itself(self):
        text = (self.root / "scripts" / "01_table1.py").read_text()
        for banned in ("import pandas", "import numpy", ".mean(", ".std(", "scipy"):
            self.assertNotIn(banned, text,
                             f"01_table1.py does its own statistics ({banned}) — that belongs "
                             "in the library, tested once")

    def test_the_grouping_variable_is_written_in(self):
        text = (self.root / "scripts" / "01_table1.py").read_text()
        self.assertIn('GROUP_BY = "redcap_data_access_group"', text)

    def test_the_variable_list_is_written_out_in_full(self):
        """The default is the demographics form, resolved here and made explicit — a
        table must say which variables it counted, not defer to a library default."""
        text = (self.root / "scripts" / "01_table1.py").read_text()
        self.assertIn("VARIABLES = [", text, "the Table 1 variables are not listed")
        self.assertIn("variables=VARIABLES", text,
                      "the generated script must pass its own explicit list")
        listed = SCAFFOLD_MOD.demographics_variables(
            FIXTURE / "datadictionary.csv", "redcap_data_access_group")
        self.assertTrue(listed, "no demographics fields were resolved from the fixture")
        for field in ("age", "sex", "education"):
            self.assertIn(field, listed)
        for skipped in ("syn_id", "contact_notes", "redcap_data_access_group"):
            self.assertNotIn(skipped, listed,
                             f"{skipped} cannot be a Table 1 row and must not be listed")

    def test_a_chartable_field_is_chosen_for_the_figure(self):
        text = (self.root / "scripts" / "01_table1.py").read_text()
        self.assertIn("FIGURE_FIELD =", text)
        chosen = SCAFFOLD_MOD.figure_field(
            FIXTURE / "datadictionary.csv",
            SCAFFOLD_MOD.demographics_variables(FIXTURE / "datadictionary.csv",
                                                "redcap_data_access_group"))
        self.assertTrue(chosen, "no chartable variable was found on the demographics form")
        self.assertIn(f'FIGURE_FIELD = "{chosen}"', text)

    def test_it_runs_end_to_end_and_writes_a_workbook_and_a_figure(self):
        """The generated script must actually work against the real library."""
        if not (self.root / "lib" / "python" / "argo_analysis").is_dir():
            self.skipTest("the Python library isn't built yet — nothing to run against")
        try:
            import pandas  # noqa: F401
            import openpyxl  # noqa: F401
            import matplotlib  # noqa: F401
        except ImportError as exc:
            self.skipTest(f"the analysis stack isn't installed here ({exc})")
        run = subprocess.run([sys.executable, "scripts/01_table1.py"], cwd=self.root,
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(run.returncode, 0, (run.stdout + run.stderr)[-1500:])
        workbook = self.root / "outputs" / "tables" / "table1.xlsx"
        self.assertTrue(workbook.is_file(), "no workbook was written")
        figures = list((self.root / "outputs" / "figures").glob("*.png"))
        self.assertTrue(figures, "no figure was written")
        self.assertGreater(figures[0].stat().st_size, 0)

    def test_the_readme_lists_ready_and_planned(self):
        readme = (self.root / "README.md").read_text()
        self.assertIn("What this toolkit can do", readme)
        section = readme.split("What this toolkit can do", 1)[1].split("## Analysis plan")[0]
        self.assertIn("table1", section)
        self.assertIn("ready", section)
        self.assertIn("survival", section)
        self.assertIn("planned", section)
        self.assertIn("not built yet", section,
                      "a planned analysis must be marked as not existing, in words")
        self.assertNotIn("{REGISTRY}", readme, "the registry placeholder was never filled in")

    def test_the_run_prints_the_registry(self):
        self.assertIn("What this toolkit can do", self.proc.stdout)
        self.assertIn("table1 — ready", self.proc.stdout)
        self.assertIn("survival — planned", self.proc.stdout)

    # ------------------------------------------------- the R twin (NITS 57)

    def test_an_r_twin_of_the_table1_script_is_written_too(self):
        """The R analyst must not have to translate a Python script to get a table.
        Hand-writing the R half is where the two libraries quietly drift apart."""
        script = self.root / "scripts" / "01_table1.R"
        self.assertTrue(script.is_file(), "no scripts/01_table1.R was generated")
        text = script.read_text()
        for module in ("core", "table1", "excel", "figures"):
            self.assertIn(f'"{module}"', text,
                          f"the R twin never sources lib/R/argo_analysis/{module}.R")
        self.assertIn('file.path(HERE, "lib", "R", "argo_analysis"', text,
                      "the R twin must source the study's OWN copied library")
        for call in ("load_study", "apply_missing", "table1(", "write_workbook",
                     "bar_by_group"):
            self.assertIn(call, text, f"the R twin never calls {call}")

    def test_the_two_table1_scripts_are_twins(self):
        """Same answers in, same files out — or they are not twins."""
        py = (self.root / "scripts" / "01_table1.py").read_text()
        r = (self.root / "scripts" / "01_table1.R").read_text()

        def value(text, name, arrow):
            match = re.search(rf'^{name} {arrow} "([^"]*)"', text, re.M)
            return match.group(1) if match else None

        self.assertEqual(value(py, "GROUP_BY", "="), value(r, "GROUP_BY", "<-"))
        self.assertEqual(value(py, "FIGURE_FIELD", "="), value(r, "FIGURE_FIELD", "<-"))
        variables = re.compile(r'"([a-z0-9_]+)"')
        py_vars = variables.findall(py.split("VARIABLES = ", 1)[1].split("\n\n", 1)[0])
        r_vars = variables.findall(r.split("VARIABLES <- ", 1)[1].split("\n\n", 1)[0])
        self.assertTrue(py_vars, "no variables were written into the Python script")
        self.assertEqual(py_vars, r_vars, "the twins describe different variables")
        for text, language in ((py, "Python"), (r, "R")):
            self.assertIn("table1.xlsx", text, f"the {language} script writes no workbook")
            self.assertIn('"outputs"', text, f"the {language} script writes outside outputs/")
            self.assertIn("_by_", text, f"the {language} script names no figure")

    def test_the_r_twin_is_valid_r_that_the_shipped_library_can_be_read_by(self):
        """Parsed, not run: this check has to pass on a machine with no R at all."""
        text = (self.root / "scripts" / "01_table1.R").read_text()
        self.assertEqual(text.count("{"), text.count("}"), "unbalanced braces in the R twin")
        self.assertEqual(text.count("("), text.count(")"), "unbalanced brackets in the R twin")
        self.assertNotIn("{GROUP_BY}", text, "a placeholder was never filled in")
        self.assertNotIn("{VARIABLES_R}", text, "a placeholder was never filled in")
        self.assertNotIn("{STUDY}", text)
        self.assertNotIn("{DATE}", text)

    # ------------------------------- the headers say which study, and when (NITS 56)

    def test_every_generated_header_carries_the_study_folder_and_today(self):
        """`<fill in>` in a header is a blank nobody ever goes back to fill — and both
        facts are known at scaffold time."""
        today = datetime.date.today().isoformat()
        for name in ("00_explore.py", "01_table1.py", "01_table1.R"):
            with self.subTest(script=name):
                header = (self.root / "scripts" / name).read_text()[:1200]
                self.assertIn(f"Study   : {self.root.name}", header,
                              f"{name} does not name the study folder")
                self.assertIn(f"Date: {today}", header, f"{name} carries no date")
                self.assertNotIn("Date: <fill in>", header)

    # ------------------------------------------- README carries the answers (NITS 56)

    def test_the_readme_study_block_records_the_grouping_variable(self):
        """The answer to the one question that makes a Table 1 right or wrong belongs
        where a reader looks first, not only inside a script."""
        readme = (self.root / "README.md").read_text()
        study = readme.split("## Study", 1)[1].split("\n## ", 1)[0]
        self.assertIn("redcap_data_access_group", study,
                      "the grouping answer never reached README.md's Study block")
        self.assertIn("Table 1 variables", study)
        for field in ("age", "sex", "education"):
            self.assertIn(f"`{field}`", study,
                          f"{field} is in the generated script but not in README.md")

    def test_the_readme_reproduces_both_twins_by_interpreter_path(self):
        readme = (self.root / "README.md").read_text()
        how = readme.split("## How to reproduce", 1)[1]
        self.assertIn("scripts/01_table1.py", how)
        self.assertIn("scripts/01_table1.R", how,
                      "README.md never says how to run the R twin")
        self.assertIn("scripts/00_explore.py", how)


class TestReadmeRecordsTheAnswersItWasGiven(unittest.TestCase):
    """One scaffold run WITH the language check: README.md must carry the answers the
    scaffold was given (grouping variable, variable list) and a runnable command for
    each script, by full interpreter path — the bare name is what fails in a session
    with a thin PATH."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = cls.tmp / "crc-cohort"
        cls.proc = subprocess.run(
            [sys.executable, str(SCAFFOLD), str(cls.root),
             "--export", str(FIXTURE / "records.csv"),
             "--dictionary", str(FIXTURE / "datadictionary.csv"),
             "--group-by", "district",
             "--variables", "age,sex",
             "--tools", str(TOOLS)],
            capture_output=True, text=True, timeout=300)
        cls.readme = (cls.root / "README.md").read_text()
        cls.found = SCAFFOLD_MOD.detect_tools(SCAFFOLD_MOD.load_tools(str(TOOLS)))

    def test_it_ran(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-800:])

    def test_the_given_grouping_variable_is_in_the_study_block(self):
        study = self.readme.split("## Study", 1)[1].split("\n## ", 1)[0]
        self.assertIn("`district`", study)
        self.assertNotIn("fill in — the variable Table 1 is grouped by", study)

    def test_the_given_variable_list_is_in_the_study_block(self):
        study = self.readme.split("## Study", 1)[1].split("\n## ", 1)[0]
        self.assertIn("`age`", study)
        self.assertIn("`sex`", study)
        self.assertIn("--variables", study,
                      "README should say the list was given, not defaulted")
        self.assertNotIn("`education`", study,
                         "the demographics default overrode the list that was asked for")

    def test_each_script_has_a_command_with_a_full_interpreter_path(self):
        if self.found is None:
            self.skipTest("the language check could not run here")
        how = self.readme.split("## How to reproduce", 1)[1]
        python = SCAFFOLD_MOD.tools_python(self.found)
        self.assertTrue(os.path.isabs(python), f"the check returned a bare name: {python}")
        self.assertIn(f"`{python} scripts/00_explore.py`", how)
        self.assertIn(f"`{python} scripts/01_table1.py`", how)
        rscript = SCAFFOLD_MOD.tools_rscript(self.found)
        if rscript:
            self.assertIn(f"`{rscript} scripts/01_table1.R`", how)
        else:
            self.assertIn("scripts/01_table1.R", how,
                          "the R twin must still be listed, with where to run it")
            self.assertIn("no working R", how,
                          "a machine without R must be told so, not given a path that fails")

    def test_no_placeholder_survives_anywhere_in_the_readme(self):
        for placeholder in ("{TOOLS}", "{REGISTRY}", "{REPRODUCE}", "{GROUP_BY}",
                            "{VARIABLES}", "{PYTHON}"):
            self.assertNotIn(placeholder, self.readme,
                             f"{placeholder} was never filled in")


class TestScaffoldWithoutAGroupingVariable(unittest.TestCase):
    """No --group-by: a marked placeholder that stops plainly — never a wrong table."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = cls.tmp / "study"
        cls.proc = subprocess.run(
            [sys.executable, str(SCAFFOLD), str(cls.root),
             "--export", str(FIXTURE / "records.csv"),
             "--dictionary", str(FIXTURE / "datadictionary.csv")],
            capture_output=True, text=True, timeout=180)

    def test_it_still_scaffolds(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-800:])

    def test_the_placeholder_is_clearly_marked(self):
        text = (self.root / "scripts" / "01_table1.py").read_text()
        self.assertIn("FILL IN", text, "the placeholder must be unmistakable")
        self.assertNotIn('GROUP_BY = "record_id"', text)
        self.assertNotIn('GROUP_BY = "site"', text,
                         "an unasked grouping variable must never be invented")

    def test_running_it_stops_with_a_plain_message_not_a_traceback(self):
        proc = subprocess.run([sys.executable, "scripts/01_table1.py"], cwd=self.root,
                              capture_output=True, text=True, timeout=180)
        self.assertNotEqual(proc.returncode, 0, "the placeholder script must not 'succeed'")
        message = proc.stdout + proc.stderr
        self.assertNotIn("Traceback", message,
                         "a non-technical user must not be shown a Python traceback")
        self.assertIn("group Table 1 by", message)
        self.assertIn("01_table1.py", message, "the message must say which file to edit")

    def test_the_run_says_the_script_is_waiting_on_an_answer(self):
        self.assertIn("group", self.proc.stdout.lower())

    def test_the_r_twin_carries_the_same_placeholder_and_the_same_refusal(self):
        """Both twins have to refuse — a filled-in Python script beside a guessing R
        one is exactly the wrong-table-nobody-caught defect, in the other language."""
        text = (self.root / "scripts" / "01_table1.R").read_text()
        self.assertIn("FILL IN", text, "the placeholder must be unmistakable")
        self.assertIn('substr(GROUP_BY, 1, 1) == "<"', text,
                      "the R twin never checks for the placeholder")
        self.assertIn("group Table 1 by", text)
        self.assertIn("01_table1.R", text, "the message must say which file to edit")
        self.assertNotIn('GROUP_BY <- "site"',
                         text, "an unasked grouping variable must never be invented")

    def test_the_readme_marks_the_grouping_variable_as_unanswered(self):
        study = (self.root / "README.md").read_text().split("## Study", 1)[1]
        study = study.split("\n## ", 1)[0]
        self.assertIn("fill in", study.lower())
        self.assertIn("never guessed", study.lower(),
                      "README must say the answer is asked for, not inferred")


# ---------------------------------------------------------------- doc guards

class TestSkillDescribesTheRegistry(unittest.TestCase):
    """Doc/code agreement. The registry is the source; SKILL.md must not drift from it."""

    @classmethod
    def setUpClass(cls):
        cls.text = SKILL_MD.read_text()
        cls.entries = SCAFFOLD_MOD.read_registry(ANALYSES)

    def _what_i_can_do(self) -> str:
        self.assertIn("## What I can do", self.text, "the skill has no registry section")
        return self.text.split("## What I can do", 1)[1].split("\n## ", 1)[0]

    def test_the_skill_has_a_what_i_can_do_section_naming_every_analysis(self):
        section = self._what_i_can_do()
        self.assertIn("analyses/", section, "the skill must point at the registry folder")
        for entry in self.entries:
            with self.subTest(analysis=entry["name"]):
                self.assertIn(entry["name"], section)
                self.assertIn(entry["status"], section,
                              f"{entry['name']} is not marked {entry['status']}")

    def test_each_analysis_carries_its_registry_status_in_the_skill(self):
        """The drift guard: a status changed in analyses/ must be changed here too."""
        section = self._what_i_can_do()
        for entry in self.entries:
            row = [ln for ln in section.splitlines() if f"`{entry['name']}`" in ln]
            self.assertTrue(row, f"no table row for {entry['name']} in 'What I can do'")
            self.assertIn(entry["status"], row[0],
                          f"the row for {entry['name']} does not say {entry['status']}")

    def test_planned_analyses_are_never_claimed_to_exist(self):
        section = self._what_i_can_do()
        for entry in self.entries:
            if entry["status"] == "planned":
                row = [ln for ln in section.splitlines() if f"`{entry['name']}`" in ln][0]
                self.assertIn("not built yet", row.lower(),
                              f"{entry['name']} is planned but the skill doesn't say so")
        self.assertIn("never import the module", section.lower())

    def test_the_old_roadmap_is_gone(self):
        self.assertNotIn("None of this exists yet", self.text,
                         "the library exists now — the not-yet-built roadmap must be replaced")
        self.assertNotIn("## Where this is heading", self.text)

    def test_survival_stays_planned_everywhere_in_the_skill(self):
        self.assertIn("Survival analysis is planned but not built yet", self.text,
                      "the skill must carry the exact message the survival stub raises")


class TestSkillStatesTheAskOnceRule(unittest.TestCase):
    """The 'by site' vs 'by district' defect: guessed grouping, invisible wrong answer."""

    @classmethod
    def setUpClass(cls):
        cls.text = SKILL_MD.read_text()

    def test_the_grouping_variable_is_asked_once_and_explicitly(self):
        lowered = self.text.lower()
        self.assertIn("asked once", lowered, "the ask-once rule is not stated")
        self.assertIn("never guessed", lowered,
                      "the skill must forbid guessing the grouping variable")

    def test_the_skill_records_why(self):
        self.assertIn("by district", self.text,
                      "the site/district confusion — the reason for the rule — is not recorded")
        self.assertIn("by site", self.text)

    def test_the_answer_is_passed_to_the_scaffold(self):
        self.assertIn("--group-by", self.text,
                      "the skill never says how the answer reaches scaffold.py")


class TestSkillStatesTheHouseStyle(unittest.TestCase):
    """One look for every ARGO output, applied by the library, not by hand."""

    @classmethod
    def setUpClass(cls):
        cls.text = SKILL_MD.read_text()
        cls.lowered = cls.text.lower()

    def test_one_workbook_per_analysis_one_sheet_per_table(self):
        self.assertIn("one workbook per analysis", self.lowered)
        self.assertIn("one sheet per table", self.lowered)

    def test_every_workbook_ends_with_a_notes_sheet(self):
        self.assertIn("`notes` sheet", self.lowered)
        for rule in ("missing-data rule", "denominator"):
            self.assertIn(rule, self.lowered, f"the Notes sheet must carry the {rule}")

    def test_figures_are_png_with_the_script_as_provenance(self):
        self.assertIn("300 dpi", self.lowered)
        self.assertIn("png", self.lowered)
        self.assertIn("provenance", self.lowered,
                      "the skill must say the generating script is a figure's provenance")


class TestSkillSaysScriptsAreLibraryCalls(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = SKILL_MD.read_text()

    def test_study_scripts_are_library_calls_not_hand_written_statistics(self):
        lowered = self.text.lower()
        self.assertIn("library calls", lowered)
        self.assertIn("not hand-written statistics", lowered,
                      "the skill must say a registry analysis is not hand-written statistics")
        self.assertIn("never re-derive a mean", lowered)

    def test_the_template_shows_the_lib_import_path(self):
        self.assertIn('sys.path.insert(0, str(HERE / "lib" / "python"))', self.text,
                      "the skill's template must show how a script reaches the copied library")
        for call in ("load_study", "apply_missing", "write_workbook", "bar_by_group"):
            self.assertIn(call, self.text)


class TestSkillKeepsTheRSectionAndTheSandboxFact(unittest.TestCase):
    """Slice C rewrote sections around these; they are load-bearing and must survive."""

    @classmethod
    def setUpClass(cls):
        cls.text = SKILL_MD.read_text()

    def test_the_r_handoff_survives(self):
        for fact in ("Never try to install R itself", "Exec format error", "base R",
                     "requireNamespace", "install.packages("):
            self.assertIn(fact, self.text, f"the R hand-off lost: {fact}")

    def test_the_cowork_sandbox_fact_survives(self):
        self.assertIn("Linux sandbox", self.text)
        self.assertIn("cannot run there", self.text,
                      "the fact that a Mac R can't execute in Cowork's Linux VM is gone")

    def test_the_language_preflight_survives(self):
        self.assertIn("argo_tools.py", self.text)
        self.assertIn("--tools", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
