#!/usr/bin/env python3
"""Unit tests for ARGO's core write-back guarantee: computed values only ever fill blanks.

This is the rule that stands between a linkage run and overwriting real clinical data. It used to
be implemented twice — once in study-linkage, once bespoke inside redcap-qa's push scripts — so it
was verified twice, differently, and could drift. It now lives in argo-core/argo_diff.py, and
this is where it's proven.

Known input -> known output. No REDCap, no network, no token.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


D = load("plugins/argo-core/scripts/argo_diff.py", "argo_diff")


class TestNormalisation(unittest.TestCase):
    """Spurious differences become false conflicts for a human to adjudicate — so don't create any."""

    def test_numeric_forms_compare_equal(self):
        for a, b in [("1", "1.0"), (1, "1"), ("1.0", 1.0), (" 2 ", "2")]:
            self.assertEqual(D.norm(a), D.norm(b), f"{a!r} vs {b!r}")

    def test_nan_is_blank(self):
        for value in ("nan", "NaN", "NAN"):
            self.assertEqual(D.norm(value), "")

    def test_none_is_blank(self):
        self.assertEqual(D.norm(None), "")

    def test_whitespace_only_is_blank(self):
        self.assertEqual(D.norm("   "), "")

    def test_text_is_preserved_exactly(self):
        self.assertEqual(D.norm("  Ibadan  "), "Ibadan")

    def test_non_equal_numbers_stay_different(self):
        self.assertNotEqual(D.norm("1"), D.norm("2"))


class TestClassify(unittest.TestCase):
    def test_blank_to_value_is_a_safe_fill(self):
        self.assertEqual(D.classify("", "X"), D.FILL)

    def test_value_to_different_value_is_a_conflict(self):
        self.assertEqual(D.classify("EXISTING", "NEW"), D.CONFLICT)

    def test_identical_values_are_a_noop(self):
        self.assertEqual(D.classify("same", "same"), D.NOOP)

    def test_value_to_blank_never_erases(self):
        """The most dangerous case: a blank computed value must never clear real data."""
        self.assertEqual(D.classify("REAL DATA", ""), D.NOOP)

    def test_blank_to_blank_is_a_noop(self):
        self.assertEqual(D.classify("", ""), D.NOOP)

    def test_numeric_equivalence_is_not_a_conflict(self):
        self.assertEqual(D.classify("1", "1.0"), D.NOOP)

    def test_nan_current_counts_as_blank_so_it_fills(self):
        self.assertEqual(D.classify("nan", "X"), D.FILL)


class TestDiffRecords(unittest.TestCase):
    def setUp(self):
        self.fields = ["a", "b"]

    def test_fills_and_conflicts_are_separated(self):
        computed = {"1": {"a": "X", "b": "NEW"}}
        current = {"1": {"a": "", "b": "EXISTING"}}
        r = D.diff_records(computed, current, self.fields, "record_id")

        self.assertEqual(r["updates"], [{"record_id": "1", "a": "X"}],
                         "only the safe fill may appear in the pushable file")
        self.assertEqual(len(r["conflicts"]), 1)
        self.assertEqual(r["conflicts"][0]["existing"], "EXISTING")

    def test_a_conflicting_value_never_reaches_the_update_file(self):
        computed = {"1": {"a": "NEW", "b": "NEW"}}
        current = {"1": {"a": "OLD", "b": "OLD"}}
        r = D.diff_records(computed, current, self.fields, "record_id")
        self.assertEqual(r["updates"], [], "nothing may be auto-pushed when everything conflicts")
        self.assertEqual(r["counts"][D.CONFLICT], 2)

    def test_a_record_missing_from_current_is_all_fills(self):
        r = D.diff_records({"9": {"a": "X", "b": "Y"}}, {}, self.fields, "record_id")
        self.assertEqual(r["counts"][D.FILL], 2)

    def test_rows_with_nothing_to_do_are_omitted_entirely(self):
        computed = {"1": {"a": "same", "b": "same"}}
        current = {"1": {"a": "same", "b": "same"}}
        r = D.diff_records(computed, current, self.fields, "record_id")
        self.assertEqual(r["updates"], [])
        self.assertEqual(r["overwrites"], [])
        self.assertEqual(r["counts"][D.NOOP], 2)

    def test_counts_add_up_to_every_cell_examined(self):
        computed = {"1": {"a": "X", "b": "NEW"}, "2": {"a": "same", "b": ""}}
        current = {"1": {"a": "", "b": "OLD"}, "2": {"a": "same", "b": "keep"}}
        r = D.diff_records(computed, current, self.fields, "record_id")
        self.assertEqual(sum(r["counts"].values()), 4)

    def test_overwrite_file_holds_only_the_conflicting_cells(self):
        computed = {"1": {"a": "X", "b": "NEW"}}
        current = {"1": {"a": "", "b": "OLD"}}
        r = D.diff_records(computed, current, self.fields, "record_id")
        self.assertEqual(r["overwrites"], [{"record_id": "1", "b": "NEW"}],
                         "the sign-off file must not smuggle in cells that weren't conflicts")


if __name__ == "__main__":
    unittest.main(verbosity=2)
