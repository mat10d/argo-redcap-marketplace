#!/usr/bin/env python3
"""The R half of the ARGO analysis library, checked against the golden Table 1.

`plugins/argo-data-analyst/skills/run-analysis/lib/R/argo_analysis/` is a
SOURCED library (not a package): core.R, table1.R, excel.R, figures.R,
survival.R, plus a one-command runner, run_table1.R. It is the mirror of the
Python library in lib/python/argo_analysis/ -- same function names, same table
shape, same rounding.

What is checked here, all against the committed synthetic fixture:

    * the runner reproduces testing/fixtures/synthetic-study/analysis/
      expected_table1.csv -- every number in the golden, to within 0.01
    * the applicable denominator: pregnancy_status is out of 111 women, not
      out of 200 participants
    * branching logic we cannot read WARNS and counts everyone, never silently
      drops the field
    * the survival module stops with the planned message
    * write_workbook() produces a workbook that opens, with the sheets and the
      Notes sheet the house style requires
    * the figures are real PNGs

R is found through the toolkit's own preflight (argo_tools.detect), which probes
the folders a Cowork shell's thin PATH misses, and which reports whether Rscript
can actually RUN something rather than only whether the file exists. Where R is
not installed, or is installed but broken, every R test here skips cleanly --
the suite must pass on a machine with no R at all.

No network, no keys, no patient data.
"""
from __future__ import annotations

import csv
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "testing" / "fixtures" / "synthetic-study"
GOLDEN = FIXTURE / "analysis" / "expected_table1.csv"
LIB = (REPO / "plugins" / "argo-data-analyst" / "skills" / "run-analysis"
       / "lib" / "R" / "argo_analysis")
RUNNER = LIB / "run_table1.R"

# The variables the golden describes, in the golden's order.
GOLDEN_VARIABLES = "age,sex,education,marital_status,tobacco_use,histology_grade"

# R and Python both round through C's printf, so in practice they agree to the
# last printed digit. The tolerance is there so a platform whose printf breaks a
# rounding tie the other way fails on the tie alone, not on the whole table.
TOL = 0.01

KEY = ("variable", "level", "statistic")


def _find_rscript():
    """R via the toolkit's preflight: is it there, and can it actually run?"""
    tools = REPO / "plugins/argo-core/skills/redcap-api/scripts/argo_tools.py"
    try:
        spec = importlib.util.spec_from_file_location("argo_tools", tools)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        info = mod.detect(probe_versions=False, verify_run=True).get("r") or {}
    except Exception:
        path = shutil.which("Rscript")
        return path, ("Rscript is not on PATH" if path is None else None)
    if not info.get("found"):
        return None, "R is not installed on this computer"
    if info.get("runs") is False:
        return None, f"R is installed but will not run: {info.get('run_error')}"
    return info.get("path") or shutil.which("Rscript"), None


RSCRIPT, R_SKIP_REASON = _find_rscript()
SKIP = R_SKIP_REASON or "R not available"


def read_table(path):
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames, list(reader)


def run_r(script_source, cwd):
    """Run a snippet of R that has already sourced whatever it needs."""
    script = Path(cwd) / "snippet.R"
    script.write_text(script_source)
    return subprocess.run([RSCRIPT, str(script)], capture_output=True, text=True,
                          timeout=300, cwd=str(cwd))


def source_lines():
    """The `source()` calls that put the whole library in scope."""
    return "\n".join(f'source({str(LIB / name)!r})'
                     for name in ("core.R", "table1.R", "excel.R", "figures.R",
                                  "survival.R")) + "\n"


def load_fixture_lines():
    return (f'study <- apply_missing(load_study({str(FIXTURE / "records.csv")!r}, '
            f'{str(FIXTURE / "datadictionary.csv")!r}))\n')


class TestTheLibraryIsPresent(unittest.TestCase):
    """Runs everywhere, R or no R: the files have to exist to be shipped."""

    def test_every_module_of_the_contract_is_there(self):
        for name in ("core.R", "table1.R", "excel.R", "figures.R", "survival.R",
                     "run_table1.R"):
            self.assertTrue((LIB / name).is_file(), f"lib/R/argo_analysis/{name} is missing")

    def test_the_contract_functions_are_defined(self):
        expected = {
            "core.R": ("load_study", "apply_missing", "labels", "applicable", "denominator"),
            "table1.R": ("table1",),
            "excel.R": ("write_workbook",),
            "figures.R": ("bar_by_group", "hist"),
            "survival.R": ("survival",),
        }
        for module, functions in expected.items():
            text = (LIB / module).read_text()
            for fn in functions:
                self.assertIn(f"{fn} <- function", text,
                              f"{module} does not define {fn}()")

    def test_survival_is_marked_planned_in_the_source(self):
        text = (LIB / "survival.R").read_text()
        self.assertIn("Survival analysis is planned but not built yet", text)

    def test_the_only_package_dependency_is_guarded(self):
        """openxlsx is the one add-on the library uses, and a missing add-on must
        produce an install line a non-programmer can copy, not a stack trace."""
        text = (LIB / "excel.R").read_text()
        self.assertIn('requireNamespace("openxlsx"', text.replace("ARGO_EXCEL_PACKAGE", '"openxlsx"'))
        self.assertIn('install.packages("openxlsx")', text)
        for module in ("core.R", "table1.R", "figures.R", "survival.R"):
            body = (LIB / module).read_text()
            self.assertNotIn("library(", body,
                             f"{module} must be base R only -- no library() calls")


@unittest.skipIf(RSCRIPT is None, SKIP)
class TestRunnerReproducesTheGolden(unittest.TestCase):
    """run_table1.R, one command, against the committed golden Table 1."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "table1.csv"
        cls.proc = subprocess.run(
            [RSCRIPT, str(RUNNER),
             "--export", str(FIXTURE / "records.csv"),
             "--dictionary", str(FIXTURE / "datadictionary.csv"),
             "--group-by", "redcap_data_access_group",
             "--variables", GOLDEN_VARIABLES,
             "--out", str(cls.out)],
            capture_output=True, text=True, timeout=300, cwd=str(cls.tmp))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_the_runner_runs(self):
        self.assertEqual(self.proc.returncode, 0,
                         f"run_table1.R failed:\n{self.proc.stderr[-2000:]}")
        self.assertTrue(self.out.exists(), "run_table1.R wrote no table")

    def test_the_columns_are_the_goldens_columns(self):
        header, _ = read_table(self.out)
        g_header, _ = read_table(GOLDEN)
        self.assertEqual(header, g_header)

    def test_every_number_in_the_golden_is_reproduced(self):
        g_header, g_rows = read_table(GOLDEN)
        _, r_rows = read_table(self.out)
        produced = {tuple(r[k] for k in KEY): r for r in r_rows}
        value_columns = g_header[3:]
        for g in g_rows:
            key = tuple(g[k] for k in KEY)
            self.assertIn(key, produced, f"the R table is missing the row {key}")
            r = produced[key]
            for col in value_columns:
                gv, rv = g[col].strip(), r[col].strip()
                if gv == "" or rv == "":
                    self.assertEqual(gv, rv, f"{key}/{col}: one side blank")
                    continue
                self.assertAlmostEqual(float(gv), float(rv), delta=TOL,
                                       msg=f"{key}/{col}: golden={gv} R={rv}")

    def test_the_golden_rows_keep_the_goldens_order(self):
        """Level order comes from the codebook, so the shared rows must appear in
        the same order -- an alphabetised Table 1 is a different table."""
        _, g_rows = read_table(GOLDEN)
        _, r_rows = read_table(self.out)
        wanted = [tuple(r[k] for k in KEY) for r in g_rows]
        got = [tuple(r[k] for k in KEY) for r in r_rows]
        self.assertEqual([k for k in got if k in set(wanted)], wanted)

    def test_the_contracts_extra_continuous_statistics_are_there(self):
        """The golden predates median/q1/q3; the contract requires them, so they
        are extra rows rather than changed ones."""
        _, r_rows = read_table(self.out)
        stats = {r["statistic"] for r in r_rows if r["variable"] == "age"}
        self.assertEqual(stats, {"n", "missing", "mean", "sd", "median", "q1", "q3"})


@unittest.skipIf(RSCRIPT is None, SKIP)
class TestApplicableDenominator(unittest.TestCase):
    """The rule the whole library turns on: describe a field against the records
    it was actually asked of."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def r(self, body):
        proc = run_r(source_lines() + load_fixture_lines() + body, self.tmp)
        self.assertEqual(proc.returncode, 0, f"R failed:\n{proc.stderr[-2000:]}")
        return proc

    def test_pregnancy_status_is_out_of_the_111_women(self):
        """[sex] = '2'. 200 records, 111 of them female. The naive denominator,
        200, is the bug this rule exists to prevent."""
        out = self.r('cat(denominator(study, "pregnancy_status"))').stdout.strip()
        self.assertEqual(out, "111")

    def test_a_field_with_no_branching_applies_to_everyone(self):
        self.assertEqual(self.r('cat(denominator(study, "sex"))').stdout.strip(), "200")

    def test_the_supported_branching_grammar(self):
        """One denominator per shape the fixture's MANIFEST engineers: quoted,
        unquoted, checkbox, numeric comparison, AND, OR."""
        body = ('for (f in c("pregnancy_status", "dx_date", "bleeding_severity", '
                '"alcohol_use", "chemo_cycles", "support_needed")) '
                'cat(f, denominator(study, f), "\\n")')
        counts = dict(line.split() for line in self.r(body).stdout.strip().splitlines())
        self.assertEqual(counts["pregnancy_status"], "111")   # [sex] = '2'      quoted
        self.assertEqual(counts["alcohol_use"], "200")        # [age] >= 18      numeric
        for field in ("dx_date", "bleeding_severity", "chemo_cycles", "support_needed"):
            n = int(counts[field])
            self.assertTrue(0 < n < 200,
                            f"{field}: branching logic did not narrow anything ({n})")

    def test_a_branching_field_is_described_against_its_own_denominator(self):
        """The pregnancy percentages must add to 100 over the women, and the
        counts must add to the applicable denominator -- not to 200."""
        body = ('t <- table1(study, group_by = "redcap_data_access_group", '
                'variables = "pregnancy_status")\n'
                'p <- t[t$variable == "pregnancy_status", ]\n'
                'cat(sum(as.numeric(p$overall[p$statistic == "n"])), '
                'as.numeric(p$overall[p$statistic == "missing"]), '
                'sum(as.numeric(p$overall[p$statistic == "pct"])))')
        counted, missing, pct_total = self.r(body).stdout.strip().split()
        self.assertEqual(int(counted) + int(missing), 111,
                         "pregnancy_status was not described against the 111 women")
        self.assertAlmostEqual(float(pct_total), 100.0, delta=0.05)

    def test_unreadable_branching_warns_and_keeps_every_record(self):
        """datediff(...) is outside the grammar. The field must be counted for
        everyone AND say so -- silently dropping it is the failure this replaced."""
        proc = self.r('cat("N=", denominator(study, "adjuvant_therapy"), "\\n", sep = "")')
        self.assertIn("N=200", proc.stdout)
        warned = proc.stderr + proc.stdout
        self.assertIn("could not fully read the branching condition", warned.lower(),
                      "an unreadable condition was used without warning anyone")
        self.assertIn("datediff", warned,
                      "the warning must quote the condition it could not read")


@unittest.skipIf(RSCRIPT is None, SKIP)
class TestSurvivalIsPlanned(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_calling_it_stops_with_the_planned_message(self):
        for name in ("survival", "survival_analysis"):
            proc = run_r(f'source({str(LIB / "survival.R")!r})\n{name}()\n', self.tmp)
            self.assertNotEqual(proc.returncode, 0, f"{name}() did not stop")
            self.assertIn("Survival analysis is planned but not built yet", proc.stderr)

    def test_the_status_the_registry_reads_says_planned(self):
        proc = run_r(f'source({str(LIB / "survival.R")!r})\ncat(ARGO_SURVIVAL_STATUS)\n',
                     self.tmp)
        self.assertEqual(proc.stdout.strip(), "planned")

    def test_it_says_what_does_work(self):
        """A dead end that does not point anywhere is a dead end someone reports
        as a bug."""
        proc = run_r(f'source({str(LIB / "survival.R")!r})\nsurvival()\n', self.tmp)
        self.assertIn("Table 1", proc.stderr)


@unittest.skipIf(RSCRIPT is None, SKIP)
class TestTable1RefusesToGuess(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_group_by_is_required(self):
        proc = run_r(source_lines() + load_fixture_lines()
                     + 'table1(study, variables = "sex")\n', self.tmp)
        self.assertNotEqual(proc.returncode, 0,
                            "table1() grouped by something it was never told")
        self.assertIn("group", proc.stderr.lower())

    def test_an_unknown_grouping_variable_is_named_plainly(self):
        proc = run_r(source_lines() + load_fixture_lines()
                     + 'table1(study, group_by = "site", variables = "sex")\n', self.tmp)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("site", proc.stderr)
        self.assertNotIn("Error in", proc.stderr.split("\n")[0])


@unittest.skipIf(RSCRIPT is None, SKIP)
class TestWorkbookAndFigures(unittest.TestCase):
    """The house style, checked from the outside: a workbook another tool can
    open, and figures that are really PNGs."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.xlsx = cls.tmp / "analysis.xlsx"
        cls.bar = cls.tmp / "figs" / "education.png"
        cls.histogram = cls.tmp / "figs" / "age.png"
        body = (
            't1 <- table1(study, group_by = "redcap_data_access_group",\n'
            '             variables = c("age", "sex", "education"))\n'
            f'write_workbook(list("Table 1" = t1), {str(cls.xlsx)!r},\n'
            '               notes = "Cohort: the whole synthetic export.")\n'
            f'bar_by_group(study, "education", "redcap_data_access_group", {str(cls.bar)!r})\n'
            f'hist(study, "age", {str(cls.histogram)!r})\n'
        )
        cls.proc = run_r(source_lines() + load_fixture_lines() + body, cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _skip_if_openxlsx_missing(self):
        if "install.packages" in self.proc.stderr and not self.xlsx.exists():
            self.skipTest("the openxlsx add-on is not installed in this R")

    def test_the_workbook_was_written(self):
        self._skip_if_openxlsx_missing()
        self.assertEqual(self.proc.returncode, 0,
                         f"the R script failed:\n{self.proc.stderr[-2000:]}")
        self.assertTrue(self.xlsx.exists() and self.xlsx.stat().st_size > 0)

    def test_the_workbook_opens_and_carries_a_notes_sheet(self):
        self._skip_if_openxlsx_missing()
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl is not installed, so the workbook cannot be opened here")
        wb = openpyxl.load_workbook(self.xlsx)
        self.assertIn("Table 1", wb.sheetnames)
        self.assertEqual(wb.sheetnames[-1], "Notes", "the Notes sheet must come last")
        notes = " ".join(str(row[0]) for row in wb["Notes"].iter_rows(values_only=True)
                         if row[0])
        self.assertIn("N = 200", notes, "the Notes sheet must state N")
        self.assertIn("-666", notes, "the Notes sheet must state the missing-data rule")
        self.assertIn("applicable denominator", notes,
                      "the Notes sheet must state the denominator rule")
        self.assertIn("Generated by", notes,
                      "the Notes sheet must name the script and the date")
        sheet = wb["Table 1"]
        self.assertTrue(sheet["A1"].font.bold, "the header row must be bold")
        self.assertEqual(sheet.freeze_panes, "A2", "the header row must be frozen")

    def test_the_figures_are_real_pngs(self):
        if self.proc.returncode != 0 and not self.bar.exists():
            self._skip_if_openxlsx_missing()
        for path in (self.bar, self.histogram):
            self.assertTrue(path.exists(), f"{path.name} was not written")
            self.assertGreater(path.stat().st_size, 1000, f"{path.name} is suspiciously small")
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n",
                                 f"{path.name} is not a PNG")


if __name__ == "__main__":
    unittest.main(verbosity=2)
