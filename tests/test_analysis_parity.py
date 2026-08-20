#!/usr/bin/env python3
"""Three-language parity for the analyst's Table 1.

PLAN.md Phase 1.5 lists "Analyst / Stata-R-Python parity: same data, three
reference scripts" as an input to define. This is that check.

`testing/fixtures/synthetic-study/analysis/` holds three scripts that must all
produce the SAME Table 1 (demographics by site: counts, percentages, mean/SD of
age) from the same two committed inputs:

    table1.py   the golden implementation (stdlib only -- never skips)
    table1.R    checked whenever Rscript is on PATH, numerically, with tolerance
    table1.do   REFERENCE ONLY -- no headless Stata licence, so only its
                existence is asserted here

`expected_table1.csv` is table1.py's committed output. Python is compared to it
byte for byte, so a change in the analysis silently changing the golden numbers
cannot pass.

No network, no keys, no pandas.
"""
from __future__ import annotations

import csv
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "testing" / "fixtures" / "synthetic-study"
ANALYSIS = FIXTURE / "analysis"
GOLDEN = ANALYSIS / "expected_table1.csv"

RSCRIPT = shutil.which("Rscript")

# R and Python both round through C's printf, so in practice they agree to the
# last printed digit. The tolerance exists so a future platform whose printf
# breaks a rounding tie the other way fails loudly on the tie alone, rather
# than on the whole table.
TOL = 0.011

KEY_COLUMNS = ("variable", "level", "statistic")


def read_table(path):
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames, list(reader)


def run(cmd, out_dir):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                          cwd=str(ANALYSIS))


class TestPythonMatchesGolden(unittest.TestCase):
    """Always runs: table1.py is stdlib-only by design."""

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp())
        cls.proc = run([sys.executable, str(ANALYSIS / "table1.py"),
                        "--out", str(cls.out)], cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_script_runs(self):
        self.assertEqual(self.proc.returncode, 0,
                         f"table1.py failed:\n{self.proc.stderr[-1500:]}")
        self.assertNotIn("Traceback", self.proc.stdout + self.proc.stderr)

    def test_output_is_byte_identical_to_the_committed_golden(self):
        produced = (self.out / "table1.csv").read_bytes()
        self.assertEqual(produced, GOLDEN.read_bytes(),
                         "table1.py no longer reproduces expected_table1.csv — if the "
                         "change is intended, regenerate the golden and commit it")

    def test_golden_has_the_expected_shape(self):
        header, rows = read_table(GOLDEN)
        self.assertEqual(header[:3], list(KEY_COLUMNS))
        self.assertEqual(header[3:], ["site_alpha", "site_beta", "overall"])
        self.assertTrue(rows)
        keys = [tuple(r[k] for k in KEY_COLUMNS) for r in rows]
        self.assertEqual(len(keys), len(set(keys)), "duplicate (variable, level, statistic)")

    def test_site_counts_and_percentages_are_internally_consistent(self):
        """A Table 1 that does not add up is worse than no Table 1."""
        header, rows = read_table(GOLDEN)
        idx = {tuple(r[k] for k in KEY_COLUMNS): r for r in rows}
        totals = idx[("records", "", "n")]
        self.assertEqual(int(totals["site_alpha"]) + int(totals["site_beta"]),
                         int(totals["overall"]))

        # Per variable: the level counts plus the missing count must equal the
        # record total, and the percentages must sum to 100.
        variables = {r["variable"] for r in rows} - {"records", "age"}
        for var in sorted(variables):
            for col in ("site_alpha", "site_beta", "overall"):
                n_sum = sum(int(r[col]) for r in rows
                            if r["variable"] == var and r["statistic"] == "n")
                missing = next(int(r[col]) for r in rows
                               if r["variable"] == var and r["statistic"] == "missing")
                self.assertEqual(n_sum + missing, int(totals[col]),
                                 f"{var}/{col}: levels + missing != N")
                pcts = [float(r[col]) for r in rows
                        if r["variable"] == var and r["statistic"] == "pct"]
                self.assertAlmostEqual(sum(pcts), 100.0, delta=0.05,
                                       msg=f"{var}/{col}: percentages sum to {sum(pcts)}")

    def test_mdc_sentinels_are_counted_as_missing_not_as_a_level(self):
        """histology_grade carries the fixture's engineered MDC codes: 16 blanks
        plus 8 sentinels = 24 missing, and no -666/-777/-888/-999 level row."""
        header, rows = read_table(GOLDEN)
        grade = [r for r in rows if r["variable"] == "histology_grade"]
        self.assertTrue(grade, "histology_grade missing from the table")
        self.assertFalse([r for r in grade if r["level"].startswith("-")],
                         "an MDC code became a category of the variable")
        missing = next(r for r in grade if r["statistic"] == "missing")
        self.assertEqual(int(missing["overall"]), 24)


@unittest.skipIf(RSCRIPT is None, "Rscript not on PATH — R parity not checked")
class TestRMatchesGolden(unittest.TestCase):
    """Runs only where R is installed. Compares NUMERICALLY, with tolerance."""

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp())
        cls.proc = run([RSCRIPT, str(ANALYSIS / "table1.R"), "--out", str(cls.out)],
                       cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_script_runs(self):
        self.assertEqual(self.proc.returncode, 0,
                         f"table1.R failed:\n{self.proc.stderr[-1500:]}")

    def test_same_rows_in_the_same_order(self):
        g_header, g_rows = read_table(GOLDEN)
        r_header, r_rows = read_table(self.out / "table1.csv")
        self.assertEqual(r_header, g_header, "R produced different columns")
        self.assertEqual([tuple(r[k] for k in KEY_COLUMNS) for r in r_rows],
                         [tuple(r[k] for k in KEY_COLUMNS) for r in g_rows],
                         "R produced different rows, or a different row order")

    def test_every_number_agrees_within_tolerance(self):
        g_header, g_rows = read_table(GOLDEN)
        r_header, r_rows = read_table(self.out / "table1.csv")
        value_columns = g_header[3:]
        for g, r in zip(g_rows, r_rows):
            key = tuple(g[k] for k in KEY_COLUMNS)
            for col in value_columns:
                gv, rv = g[col].strip(), r[col].strip()
                if gv == "" or rv == "":
                    self.assertEqual(gv, rv, f"{key}/{col}: one side blank")
                    continue
                self.assertAlmostEqual(float(gv), float(rv), delta=TOL,
                                       msg=f"{key}/{col}: python={gv} R={rv}")


class TestStataReferenceExists(unittest.TestCase):
    """Stata gets no automated run: there is no headless licence available, so
    table1.do is a hand-checked reference. Assert it is present and that it is
    honest about not being tested."""

    def test_do_file_is_present(self):
        do_file = ANALYSIS / "table1.do"
        self.assertTrue(do_file.exists(), "table1.do is missing")
        text = do_file.read_text()
        self.assertIn("REFERENCE ONLY", text,
                      "table1.do must state that it is not automatically tested")
        self.assertIn("table1.csv", text)

    def test_all_three_languages_are_present(self):
        for name in ("table1.py", "table1.R", "table1.do", "expected_table1.csv"):
            self.assertTrue((ANALYSIS / name).exists(), f"{name} is missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
