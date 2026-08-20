#!/usr/bin/env python3
"""End-to-end test of the QA worklist builder against the synthetic study.

This test exists because of a bug that every other kind of test missed: after the 0.9.0
refactor, missing_and_certainty_for returned bare bools on four paths into a tuple-unpacking
caller — so the builder crashed the moment any applicable-but-blank cell existed, meaning the
shipped plugin could not produce a nonempty worklist AT ALL. Unit tests of the branching logic
all passed; nothing ran the builder on data with flaggable cells until the synthetic fixture
did, on first contact.

Asserts against MANIFEST.json's engineered counts — numbers, not vibes.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "testing" / "fixtures" / "synthetic-study"
BUILDER = REPO / "plugins" / "argo-qa-specialist" / "skills" / "qa-worklists" / "build_worklists.py"

try:
    import openpyxl  # noqa: F401
    import pandas  # noqa: F401
    import yaml  # noqa: F401
    DEPS = True
except ImportError:
    DEPS = False


@unittest.skipIf(not DEPS, "pandas/openpyxl/yaml not installed")
class TestWorklistBuilderEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp())
        cls.proc = subprocess.run(
            [sys.executable, str(BUILDER),
             "--records-csv", str(FIXTURE / "records.csv"),
             "--metadata-csv", str(FIXTURE / "datadictionary.csv"),
             "--fields", str(FIXTURE / "qa_fields.yaml"),
             "--out", str(cls.out), "--id-field", "syn_id"],
            capture_output=True, text=True, timeout=300,
        )
        cls.manifest = json.loads((FIXTURE / "MANIFEST.json").read_text())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_builder_completes_without_crashing(self):
        self.assertEqual(self.proc.returncode, 0,
                         f"builder crashed on the fixture:\n{self.proc.stderr[-1500:]}")
        self.assertNotIn("Traceback", self.proc.stdout + self.proc.stderr)

    def test_all_eight_workbooks_written(self):
        # 2 workbooks x 2 DAGs x (with_MDC + no_MDC)
        books = list(self.out.rglob("*.xlsx"))
        self.assertEqual(len(books), 8, f"expected 8 workbooks, got {[b.name for b in books]}")

    def test_unparseable_datediff_reported_exactly_once(self):
        combined = self.proc.stdout + self.proc.stderr
        self.assertEqual(combined.count("datediff"), 1,
                         "the one engineered unreadable condition must be reported once")

    def test_row_counts_match_the_manifest(self):
        """The fixture's MANIFEST states exact expected rows per workbook — assert them."""
        expected = self.manifest.get("qa", {}).get("expected_worklists", {})
        self.assertTrue(expected, "MANIFEST lost its qa.expected_worklists block")
        for workbook, variants in expected.items():
            for key, spec in variants.items():
                site, variant = key.split("/")
                matches = [p for p in self.out.rglob(f"{workbook}_{site}.xlsx")
                           if p.parent.name == variant]
                self.assertTrue(matches, f"{variant}/{workbook}_{site}.xlsx not produced")
                wb = openpyxl.load_workbook(matches[0])
                ws = wb.active
                data_rows = ws.max_row - 2  # header + prereq rows
                self.assertEqual(
                    data_rows, spec["rows_with_work"],
                    f"{workbook} {key}: {data_rows} data rows, "
                    f"MANIFEST says {spec['rows_with_work']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
