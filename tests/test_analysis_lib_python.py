#!/usr/bin/env python3
"""The Python analysis library (argo_analysis) — known input, known output.

The worst bug this repo has shipped produced no crash, only a wrong Excel file.
An analysis library is the easiest place in the toolkit for that to happen
again: every function here returns a number that looks plausible whether or not
it is right. So the numbers are pinned, against a golden table that was computed
independently (testing/fixtures/synthetic-study/analysis/table1.py, stdlib only,
committed as expected_table1.csv), and against the fixture MANIFEST's engineered
counts.

What is checked here:

  * table1 reproduces every statistic in expected_table1.csv — mean, SD, and
    every count and percentage of sex, education, marital status, tobacco use
    and histology grade, split by site and overall
  * the applicable denominator: pregnancy status is out of the 111 women, not
    the 200 records, and the same rule holds for checkbox-gated, AND-gated and
    OR-gated fields
  * a branching condition we cannot read counts EVERYONE and says so out loud —
    never silently drops a field
  * missing-data codes are missing, never a category, never averaged
  * levels come out in codebook order, not alphabetical order
  * the Excel house style: sheets, bold frozen header, a Notes sheet carrying N,
    the missing-data rule, the denominator rule, the script and the date
  * the figures: real PNGs, and a plain-language degrade when matplotlib is not
    installed rather than a crash
  * the survival stub stops with "planned but not built yet"
  * nothing in the package imports anything outside the package or from another
    plugin — the rule four separate locator bugs were paid for

No network, no tokens, no patient data.

    python3 tests/test_analysis_lib_python.py
"""

from __future__ import annotations

import ast
import contextlib
import csv
import datetime
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "plugins/argo-data-analyst/skills/run-analysis"
LIB = SKILL / "lib/python"
PACKAGE = LIB / "argo_analysis"
FIXTURE = REPO / "testing/fixtures/synthetic-study"
RECORDS = FIXTURE / "records.csv"
DICTIONARY = FIXTURE / "datadictionary.csv"
GOLDEN = FIXTURE / "analysis/expected_table1.csv"

sys.path.insert(0, str(LIB))

from argo_analysis import core, excel, figures, survival, table1  # noqa: E402

#: The variables the golden table covers, in the golden's own order.
GOLDEN_VARIABLES = ["age", "sex", "education", "marital_status", "tobacco_use",
                    "histology_grade"]

GROUP_BY = "redcap_data_access_group"
KEY = ("variable", "level", "statistic")


@contextlib.contextmanager
def quiet():
    """Swallow the library's progress messages so the test run stays readable."""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def load_study():
    core.reset_warnings()
    return core.apply_missing(core.load_study(RECORDS, DICTIONARY))


def golden_rows():
    with open(GOLDEN, newline="") as fh:
        return list(csv.DictReader(fh))


def as_dict(table):
    """{(variable, level, statistic): row} for a table1 DataFrame."""
    out = {}
    for _, row in table.iterrows():
        out[(str(row["variable"]), str(row["level"]), str(row["statistic"]))] = row
    return out


class TestTable1MatchesTheGolden(unittest.TestCase):
    """Every number the golden holds, reproduced by the library.

    The golden was produced by a separate stdlib-only script that shares no code
    with this library, so agreement is evidence and not a tautology.
    """

    @classmethod
    def setUpClass(cls):
        cls.study = load_study()
        cls.table = table1.table1(cls.study, GROUP_BY, GOLDEN_VARIABLES)
        cls.rows = as_dict(cls.table)
        cls.golden = golden_rows()

    def test_the_columns_are_the_contracted_ones(self):
        self.assertEqual(list(self.table.columns),
                         ["variable", "level", "statistic",
                          "site_alpha", "site_beta", "overall"])

    def test_no_p_value_column_unless_it_was_asked_for(self):
        self.assertNotIn("p_value", self.table.columns)

    def test_every_statistic_in_the_golden_is_reproduced(self):
        checked = 0
        for want in self.golden:
            key = (want["variable"], want["level"], want["statistic"])
            self.assertIn(key, self.rows, f"{key} is missing from the library's table")
            got = self.rows[key]
            for column in ("site_alpha", "site_beta", "overall"):
                expected = want[column].strip()
                actual = got[column]
                self.assertIsNotNone(actual, f"{key}/{column} came out blank")
                self.assertEqual(
                    float(f"{float(actual):.2f}"), float(expected),
                    f"{key}/{column}: golden says {expected}, library says {actual}")
                checked += 1
        self.assertGreaterEqual(len(self.golden), 40, "the golden itself looks truncated")
        self.assertEqual(checked, 3 * len(self.golden),
                         "every cell of the golden must have been compared")

    def test_the_golden_rows_come_out_in_the_golden_order(self):
        """Row order is part of the output: a Table 1 is read top to bottom."""
        wanted = [(r["variable"], r["level"], r["statistic"]) for r in self.golden]
        produced = [k for k in as_dict(self.table)]
        positions = [produced.index(k) for k in wanted]
        self.assertEqual(positions, sorted(positions),
                         "the library's rows are in a different order from the golden's")

    def test_the_contracted_extra_statistics_are_present(self):
        """The contract adds median/q1/q3 to what the golden happens to record."""
        for statistic in ("n", "missing", "mean", "sd", "median", "q1", "q3"):
            self.assertIn(("age", "", statistic), self.rows)
        # 200 ages, so the median sits between the 100th and 101st value.
        ages = sorted(float(v) for v in self.study.data["age"])
        self.assertAlmostEqual(float(self.rows[("age", "", "median")]["overall"]),
                               (ages[99] + ages[100]) / 2, places=2)

    def test_levels_and_missing_add_up_to_the_records_in_the_column(self):
        total = self.rows[("records", "", "n")]
        for variable in ("sex", "education", "marital_status", "tobacco_use",
                         "histology_grade"):
            for column in ("site_alpha", "site_beta", "overall"):
                counted = sum(int(r[column]) for k, r in self.rows.items()
                              if k[0] == variable and k[2] == "n")
                missing = int(self.rows[(variable, "", "missing")][column])
                self.assertEqual(counted + missing, int(total[column]),
                                 f"{variable}/{column}: levels + missing != N")

    def test_percentages_sum_to_a_hundred(self):
        for variable in ("sex", "education", "marital_status", "tobacco_use",
                         "histology_grade"):
            for column in ("site_alpha", "site_beta", "overall"):
                pcts = [float(r[column]) for k, r in self.rows.items()
                        if k[0] == variable and k[2] == "pct"]
                self.assertAlmostEqual(sum(pcts), 100.0, delta=0.05,
                                       msg=f"{variable}/{column} sums to {sum(pcts)}")


class TestApplicableDenominator(unittest.TestCase):
    """Who was actually asked — the rule that separates a right table from a
    plausible one.

    pregnancy_status is shown only when `[sex] = '2'`. The fixture has 111 women
    among 200 records, of whom 13 were left blank (MANIFEST: 8 at site_alpha,
    5 at site_beta). So the denominator is 111 records asked, 98 answered — and
    a percentage out of 200 would understate every level by nearly half.
    """

    @classmethod
    def setUpClass(cls):
        cls.study = load_study()

    def test_pregnancy_status_is_out_of_the_women_not_the_cohort(self):
        self.assertEqual(core.denominator(self.study, "pregnancy_status"), 111)
        self.assertEqual(len(self.study.data), 200, "the naive denominator")

    def test_the_denominator_matches_the_gate_field_itself(self):
        women = int((self.study.data["sex"].astype(str).str.strip() == "2").sum())
        self.assertEqual(core.denominator(self.study, "pregnancy_status"), women)

    def test_the_table_uses_111_and_not_200(self):
        table = table1.table1(self.study, GROUP_BY, ["pregnancy_status"])
        rows = as_dict(table)
        counted = sum(int(r["overall"]) for k, r in rows.items()
                      if k[0] == "pregnancy_status" and k[2] == "n")
        missing = int(rows[("pregnancy_status", "", "missing")]["overall"])
        self.assertEqual(counted + missing, 111,
                         "the table counted people who were never asked")
        self.assertEqual(missing, 13, "MANIFEST: 8 blank at site_alpha, 5 at site_beta")
        answered = counted
        for key, row in rows.items():
            if key[0] == "pregnancy_status" and key[2] == "pct":
                level_n = int(rows[(key[0], key[1], "n")]["overall"])
                self.assertAlmostEqual(float(row["overall"]),
                                       round(100.0 * level_n / answered, 2), places=2)
                self.assertNotAlmostEqual(float(row["overall"]),
                                          round(100.0 * level_n / 200, 2), places=2,
                                          msg="this percentage is out of 200, not out of "
                                              "the people who were asked")

    def test_a_checkbox_gate_is_read(self):
        """bleeding_severity is shown only if `[symptoms(3)] = 1` — column symptoms___3."""
        ticked = int((self.study.data["symptoms___3"].astype(str).str.strip() == "1").sum())
        self.assertEqual(core.denominator(self.study, "bleeding_severity"), ticked)
        self.assertLess(ticked, 200)

    def test_an_and_gate_and_an_or_gate_are_read(self):
        data = self.study.data
        chemo = ((data["adjuvant_therapy"].astype(str).str.strip() == "1")
                 & (data["surgery_done"].astype(str).str.strip() == "1")).sum()
        self.assertEqual(core.denominator(self.study, "chemo_cycles"), int(chemo))
        support = data["follow_status"].astype(str).str.strip().isin(["2", "4"]).sum()
        self.assertEqual(core.denominator(self.study, "support_needed"), int(support))

    def test_a_numeric_comparison_gate_is_read(self):
        adults = int((self.study.data["age"].astype(float) >= 18).sum())
        self.assertEqual(core.denominator(self.study, "alcohol_use"), adults)

    def test_an_unreadable_condition_counts_everyone_and_says_so(self):
        """`datediff([dx_date],[surgery_date],'d') > 30` is outside the grammar.

        The failure this replaces treated unreadable as "not applicable" and
        silently dropped 28% of branching fields on one live cohort.
        """
        core.reset_warnings()
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            self.assertEqual(core.denominator(self.study, "adjuvant_therapy"), 200)
        said = buffer.getvalue()
        self.assertIn("could not be read", said)
        self.assertIn("datediff", said)
        self.assertIn("datediff([dx_date],[surgery_date],'d') > 30",
                      " ".join(core.UNPARSEABLE_LOGIC))

    def test_a_field_with_no_condition_applies_to_everyone(self):
        self.assertEqual(core.denominator(self.study, "sex"), 200)


class TestMissingData(unittest.TestCase):
    """Missing-data codes are missing. Everywhere, in every field, always."""

    def test_apply_missing_clears_every_sentinel_in_every_field(self):
        raw = core.load_study(RECORDS, DICTIONARY)
        before = sum(int(raw.data[c].astype(str).str.strip().isin(core.MDC_CODES).sum())
                     for c in raw.data.columns)
        self.assertGreater(before, 0, "the fixture should carry engineered sentinels")
        cleaned = core.apply_missing(raw)
        after = sum(int(cleaned.data[c].astype(str).str.strip().isin(core.MDC_CODES).sum())
                    for c in cleaned.data.columns)
        self.assertEqual(after, 0)
        self.assertGreater(len(raw.data.loc[
            raw.data["histology_grade"].astype(str).str.strip().isin(core.MDC_CODES)]), 0)

    def test_apply_missing_leaves_the_original_alone_and_repeats_safely(self):
        raw = core.load_study(RECORDS, DICTIONARY)
        once = core.apply_missing(raw)
        twice = core.apply_missing(once)
        self.assertTrue((once.data == twice.data).all().all())
        self.assertGreater(
            int(raw.data["histology_grade"].astype(str).str.strip()
                .isin(core.MDC_CODES).sum()), 0, "the original was modified in place")

    def test_a_missing_code_offered_as_a_choice_never_becomes_a_level(self):
        """histology_grade offers -666/-777/-888/-999 so an RA can say WHY a value
        is absent. They are reasons, not grades: 16 blanks + 8 codes = 24 missing."""
        study = load_study()
        self.assertEqual(list(core.labels(study, "histology_grade").keys()),
                         ["1", "2", "3"])
        table = table1.table1(study, GROUP_BY, ["histology_grade"])
        levels = {str(r["level"]) for _, r in table.iterrows()}
        self.assertFalse([l for l in levels if l.startswith("-")],
                         "a missing-data code became a category of the variable")
        rows = as_dict(table)
        self.assertEqual(int(rows[("histology_grade", "", "missing")]["overall"]), 24)

    def test_the_table_is_right_even_if_apply_missing_was_forgotten(self):
        """A script that skips the step still must not average a -999."""
        raw = core.load_study(RECORDS, DICTIONARY)
        careless = table1.table1(raw, GROUP_BY, ["histology_grade"])
        careful = table1.table1(core.apply_missing(raw), GROUP_BY, ["histology_grade"])
        self.assertEqual(as_dict(careless).keys(), as_dict(careful).keys())
        for key, row in as_dict(careless).items():
            self.assertEqual(row["overall"], as_dict(careful)[key]["overall"])


class TestCodebookOrder(unittest.TestCase):
    """Levels in the order the questionnaire asks them, not in the order the
    alphabet happens to put them."""

    def test_labels_follow_the_choice_list(self):
        study = load_study()
        self.assertEqual(list(core.labels(study, "education").values()),
                         ["None", "Primary", "Secondary", "Tertiary"])
        self.assertEqual(list(core.labels(study, "marital_status").values()),
                         ["Single", "Married", "Widowed", "Divorced"])

    def test_yes_no_fields_get_the_map_redcap_keeps_to_itself(self):
        study = load_study()
        self.assertEqual(core.labels(study, "tobacco_use"), {"0": "No", "1": "Yes"})

    def test_the_table_is_not_alphabetical(self):
        study = load_study()
        table = table1.table1(study, GROUP_BY, ["marital_status"])
        levels = [str(r["level"]) for _, r in table.iterrows()
                  if str(r["statistic"]) == "n" and str(r["level"])]
        self.assertEqual(levels, ["Single", "Married", "Widowed", "Divorced"])
        self.assertNotEqual(levels, sorted(levels))


class TestGroupingIsRequired(unittest.TestCase):
    def test_no_grouping_variable_is_an_error_a_person_can_read(self):
        study = load_study()
        with self.assertRaises(ValueError) as caught:
            table1.table1(study, "", ["age"])
        self.assertIn("grouping variable", str(caught.exception))

    def test_a_grouping_variable_that_is_not_there_says_so(self):
        study = load_study()
        with self.assertRaises(ValueError) as caught:
            table1.table1(study, "not_a_column", ["age"])
        self.assertIn("not a column", str(caught.exception))


class TestPValues(unittest.TestCase):
    """Only when asked for, and from tests whose critical values are known."""

    def test_the_distributions_agree_with_published_critical_values(self):
        self.assertAlmostEqual(table1.chi_square_p(3.841459, 1), 0.05, places=4)
        self.assertAlmostEqual(table1.chi_square_p(5.991465, 2), 0.05, places=4)
        self.assertAlmostEqual(table1.student_t_p(2.228139, 10), 0.05, places=4)
        self.assertAlmostEqual(table1.normal_p(1.959964), 0.05, places=4)
        # Fisher's tea-tasting table: the textbook answer is 0.4857.
        self.assertAlmostEqual(table1.fisher_exact_2x2([[3, 1], [1, 3]]), 0.4857, places=4)

    def test_a_p_value_column_appears_only_on_request(self):
        study = load_study()
        with quiet():
            table = table1.table1(study, GROUP_BY, ["age", "sex"], p_values=True)
        self.assertIn("p_value", table.columns)
        values = [r["p_value"] for _, r in table.iterrows() if r["p_value"] is not None]
        self.assertEqual(len(values), 2, "one p-value per variable, on its first row")
        for p in values:
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)
        self.assertEqual(table.attrs["p_value_tests"]["sex"], "chi-square test")
        self.assertEqual(table.attrs["p_value_tests"]["age"], "Welch's t test")

    def test_the_continuous_test_can_be_switched(self):
        study = load_study()
        with quiet():
            table = table1.table1(study, GROUP_BY, ["age"], p_values=True,
                                  continuous_test="mannwhitney")
        self.assertEqual(table.attrs["p_value_tests"]["age"], "Mann-Whitney U test")

    def test_a_simulated_p_value_is_seeded_and_repeatable(self):
        """pregnancy_status has an expected count under 5, so the chi-square
        approximation is replaced by simulation — which must not wobble."""
        study = load_study()
        with quiet():
            first = table1.table1(study, GROUP_BY, ["pregnancy_status"], p_values=True)
            second = table1.table1(study, GROUP_BY, ["pregnancy_status"], p_values=True)
        p1 = [r["p_value"] for _, r in first.iterrows() if r["p_value"] is not None]
        p2 = [r["p_value"] for _, r in second.iterrows() if r["p_value"] is not None]
        self.assertEqual(p1, p2)
        self.assertIn("seed", first.attrs["p_value_tests"]["pregnancy_status"])


class TestExcelHouseStyle(unittest.TestCase):
    """One workbook per analysis, and always the same one."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        study = load_study()
        cls.table = table1.table1(study, GROUP_BY, ["age", "sex"])
        core.denominator(study, "adjuvant_therapy")     # provokes an unreadable condition
        cls.path = excel.write_workbook(
            {"Table 1": cls.table, "Sex only": cls.table},
            cls.dir / "analysis.xlsx",
            notes=["Grouped by site. Synthetic test data."])
        openpyxl = core.require("openpyxl", "openpyxl", "reads the workbook back")
        cls.book = openpyxl.load_workbook(cls.path)

    def test_a_sheet_per_table_then_notes_last(self):
        self.assertEqual(self.book.sheetnames, ["Table 1", "Sex only", "Notes"])

    def test_the_header_row_is_bold_and_frozen(self):
        sheet = self.book["Table 1"]
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertTrue(all(cell.font.bold for cell in sheet[1]))
        self.assertEqual([c.value for c in sheet[1]], list(self.table.columns))

    def test_columns_are_wide_enough_to_read(self):
        sheet = self.book["Table 1"]
        widths = [dim.width for dim in sheet.column_dimensions.values()]
        self.assertTrue(widths, "no column widths were set")
        self.assertTrue(all(w and w >= 9 for w in widths))

    def test_numbers_are_written_as_numbers(self):
        """A count stored as text cannot be summed, sorted or charted."""
        sheet = self.book["Table 1"]
        row = next(r for r in sheet.iter_rows(min_row=2, values_only=True)
                   if r[0] == "records")
        self.assertEqual(row[3:6], (120, 80, 200))
        for value in row[3:6]:
            self.assertIsInstance(value, int)

    def test_the_notes_sheet_carries_what_a_reader_needs(self):
        lines = [c.value for c in self.book["Notes"]["A"] if c.value]
        joined = "\n".join(lines)
        self.assertIn("Records in this analysis (N): 200", joined)
        self.assertIn("Produced by:", joined)
        self.assertIn(datetime.date.today().isoformat(), joined)
        self.assertIn("Grouped by site. Synthetic test data.", lines)
        self.assertIn("-666", joined)                    # the missing-data rule
        self.assertIn("branching logic fired", joined)   # the denominator rule
        self.assertIn("2 decimal places", joined)        # the rounding rule
        self.assertIn("datediff", joined,
                      "an unreadable condition must be listed for the reader")

    def test_an_empty_workbook_is_refused_in_words(self):
        with self.assertRaises(ValueError) as caught:
            excel.write_workbook({}, self.dir / "nothing.xlsx")
        self.assertIn("no tables", str(caught.exception))

    def test_sheet_names_are_made_legal_and_unique(self):
        self.assertEqual(excel.sheet_name("Table 1: by site/DAG"), "Table 1- by site-DAG")
        self.assertEqual(excel.sheet_name("A" * 40), "A" * 31)
        self.assertEqual(excel.sheet_name("Notes", taken=["Notes"]), "Notes 2")


class TestFigures(unittest.TestCase):
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.study = load_study()

    def test_a_grouped_bar_chart_is_a_real_png(self):
        with quiet():
            path = figures.bar_by_group(self.study, "education", GROUP_BY,
                                        self.dir / "education.png")
        self.assertIsNotNone(path, "matplotlib is installed here, so this must draw")
        blob = Path(path).read_bytes()
        self.assertTrue(blob.startswith(self.PNG_MAGIC))
        self.assertGreater(len(blob), 5000, "the file is too small to be a real chart")

    def test_a_histogram_is_a_real_png(self):
        with quiet():
            path = figures.hist(self.study, "age", self.dir / "age.png")
        blob = Path(path).read_bytes()
        self.assertTrue(blob.startswith(self.PNG_MAGIC))
        self.assertGreater(len(blob), 5000)

    def test_the_palette_is_the_colourblind_safe_one(self):
        self.assertEqual(figures.PALETTE[:3], ["#0072B2", "#E69F00", "#009E73"])
        self.assertEqual(figures.DPI, 300)

    def test_the_legend_is_drawn_outside_the_plot_area(self):
        """The legend used to sit at 'upper right' — on top of the tallest bar, which
        is the bar the reader came for. Measured rather than read off the source: the
        legend's box has to begin at or past the right-hand edge of the axes."""
        measured = {}
        original = figures._save

        def spy(fig, path, plt):
            fig.canvas.draw()               # a renderer, so the boxes can be measured
            axes = fig.axes[0]
            legend = axes.get_legend()
            measured["legend"] = None if legend is None else legend.get_window_extent()
            measured["axes"] = axes.get_window_extent()
            return original(fig, path, plt)

        figures._save = spy
        try:
            with quiet():
                figures.bar_by_group(self.study, "education", GROUP_BY,
                                     self.dir / "legend.png")
        finally:
            figures._save = original
        self.assertIsNotNone(measured["legend"], "a chart of two groups must have a legend")
        self.assertGreaterEqual(
            round(measured["legend"].x0, 3), round(measured["axes"].x1, 3),
            "the legend starts inside the plot area — it must sit clear of the bars")

    def test_the_legend_geometry_is_stated_once(self):
        """Both halves of the fix live in named constants, so neither can be undone
        by editing one line of drawing code."""
        self.assertGreater(figures.LEGEND_ANCHOR[0], 1.0,
                           "the anchor must be past the right edge of the axes")
        self.assertLess(figures.LEGEND_RIGHT, 1.0,
                        "the axes must give up width for the legend to sit in")

    def test_a_chart_of_something_uncountable_says_why(self):
        with self.assertRaises(ValueError) as caught:
            figures.bar_by_group(self.study, "age", GROUP_BY, self.dir / "no.png")
        self.assertIn("no choice list", str(caught.exception))

    def test_no_matplotlib_degrades_with_one_plain_paragraph(self):
        """A laptop without matplotlib still gets the tables. It must not crash."""
        saved = {name: module for name, module in sys.modules.items()
                 if name == "matplotlib" or name.startswith("matplotlib.")}
        for name in saved:
            del sys.modules[name]
        sys.modules["matplotlib"] = None
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stderr(buffer), quiet():
                bar = figures.bar_by_group(self.study, "education", GROUP_BY,
                                           self.dir / "never.png")
                histogram = figures.hist(self.study, "age", self.dir / "never2.png")
        finally:
            sys.modules.pop("matplotlib", None)
            sys.modules.update(saved)
        self.assertIsNone(bar)
        self.assertIsNone(histogram)
        said = buffer.getvalue()
        self.assertIn("python3 -m pip install matplotlib", said)
        self.assertIn("the chart was skipped", said)
        self.assertFalse((self.dir / "never.png").exists())


class TestSurvivalIsHonestlyAStub(unittest.TestCase):
    def test_calling_it_stops_with_the_agreed_sentence(self):
        with self.assertRaises(NotImplementedError) as caught:
            survival.survival(None, "enrol_date", "death_date")
        self.assertIn("Survival analysis is planned but not built yet",
                      str(caught.exception))

    def test_it_is_marked_planned_so_the_registry_can_read_it(self):
        self.assertEqual(survival.STATUS, "planned")

    def test_it_is_the_only_function_in_the_module(self):
        public = [name for name in dir(survival)
                  if callable(getattr(survival, name)) and not name.startswith("_")]
        self.assertEqual(public, ["survival"])

    def test_running_the_file_explains_itself_instead_of_crashing(self):
        proc = subprocess.run([sys.executable, str(PACKAGE / "survival.py")],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("planned but not built yet", proc.stdout)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)


class TestTheLibraryStaysInsideItsOwnFolder(unittest.TestCase):
    """Imports are same-package, full stop.

    Four separate locator bugs came from scripts hunting for code in other
    plugins across four environment layouts; a fifth cannot. The branching
    grammar in core.py is a deliberate COPY of the QA worklist builder's, not an
    import of it — this is the test that keeps it a copy.
    """

    MODULES = ["__init__", "core", "table1", "excel", "figures", "survival"]

    #: Everything the library is allowed to import: the standard library subset
    #: it actually uses, plus the three add-ons the contract permits.
    ALLOWED = {
        "__future__", "argparse", "ast", "collections", "contextlib", "csv",
        "dataclasses", "datetime", "importlib", "io", "json", "math", "os",
        "pathlib", "random", "re", "statistics", "string", "sys", "textwrap",
        "typing", "warnings",
        "pandas", "openpyxl", "matplotlib",
    }

    def files(self):
        for name in self.MODULES:
            path = PACKAGE / f"{name}.py"
            self.assertTrue(path.exists(), f"{path.relative_to(REPO)} is missing")
            yield path, path.read_text()

    def test_all_six_modules_are_where_the_layout_says(self):
        self.assertEqual(sorted(p.name for p in PACKAGE.glob("*.py")),
                         sorted(f"{m}.py" for m in self.MODULES))

    def test_every_import_is_the_package_itself_or_an_allowed_add_on(self):
        offenders = []
        for path, text in self.files():
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        # A bare `import core` is the fallback that lets a module be
                        # run as a loose file from its own folder — still the package.
                        if top not in self.ALLOWED and top not in self.MODULES:
                            offenders.append(f"{path.name}:{node.lineno} import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.level:                       # from . import x / from .core import y
                        inside = node.module or ""
                        if inside:
                            if inside.split(".")[0] not in self.MODULES:
                                offenders.append(
                                    f"{path.name}:{node.lineno} from .{inside}")
                        else:
                            for alias in node.names:
                                if alias.name not in self.MODULES:
                                    offenders.append(
                                        f"{path.name}:{node.lineno} from . import {alias.name}")
                        continue
                    top = (node.module or "").split(".")[0]
                    if top in self.MODULES:
                        continue                         # the standalone-run fallback
                    if top not in self.ALLOWED:
                        offenders.append(f"{path.name}:{node.lineno} from {node.module}")
        self.assertFalse(offenders,
                         "the analysis library may only import itself, the standard library, "
                         f"pandas, openpyxl and matplotlib: {offenders}")

    def test_nothing_reaches_for_another_plugin_or_edits_the_search_path(self):
        for path, text in self.files():
            for forbidden in ("plugins/", "argo-qa-specialist", "argo-core",
                              "build_worklists", "CLAUDE_PLUGIN_ROOT",
                              "sys.path.insert", "sys.path.append"):
                self.assertNotIn(forbidden, text,
                                 f"{path.name} reaches outside its own package ({forbidden})")

    def test_nothing_talks_to_redcap_or_the_network(self):
        """This library reads two CSV files. That is the whole of its input."""
        for path, text in self.files():
            for forbidden in ("REDCAP_URL", "urllib", "requests", "http://", "https://"):
                self.assertNotIn(forbidden, text,
                                 f"{path.name} looks like it goes online ({forbidden})")

    def test_the_optional_add_ons_are_imported_only_when_they_are_needed(self):
        """Importing the library on a bare machine must work; only the step that
        needs pandas may complain about pandas."""
        for path, text in self.files():
            for node in ast.parse(text).body:            # module level only
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [(node.module or "").split(".")[0]]
                for name in names:
                    self.assertNotIn(name, ("pandas", "openpyxl", "matplotlib"),
                                     f"{path.name} imports {name} at the top of the file; "
                                     "import it inside the function that needs it, with a "
                                     "message naming the pip install line")

    def test_every_module_runs_on_its_own_without_a_traceback(self):
        for path, _ in self.files():
            if path.name == "__init__.py":
                continue
            proc = subprocess.run([sys.executable, str(path)],
                                  capture_output=True, text=True, timeout=60, cwd=str(REPO))
            self.assertEqual(proc.returncode, 0, f"{path.name}: {proc.stderr[-500:]}")
            self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_the_missing_add_on_message_names_the_command_that_fixes_it(self):
        with self.assertRaises(core.MissingToolkit) as caught:
            core.require("a_package_that_does_not_exist", "notreal",
                         "does something useful")
        self.assertIn("python3 -m pip install notreal", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
