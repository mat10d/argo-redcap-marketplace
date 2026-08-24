#!/usr/bin/env python3
"""Unit tests for ARGO's core write-back guarantee: computed values only ever fill blanks.

This is the rule that stands between a linkage run and overwriting real clinical data. It used to
be implemented twice — once in link-data, once bespoke inside qa-worklists's push scripts — so it
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


D = load("plugins/argo-core/skills/redcap-api/scripts/argo_diff.py", "argo_diff")


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

    def test_a_record_missing_from_current_is_an_orphan_not_a_row_of_fills(self):
        """The second guardrail: a missing record is not a blank record.

        Read as blanks, every value on an unmatched id became a "safe fill" — and importing
        that payload would CREATE records in the project instead of filling gaps in it.
        """
        r = D.diff_records({"9": {"a": "X", "b": "Y"}}, {}, self.fields, "record_id")
        self.assertEqual(r["updates"], [], "an orphan must never reach the pushable file")
        self.assertEqual(r["counts"][D.FILL], 0)
        self.assertEqual(r["counts"][D.ORPHAN], 2, "both cells belong to the orphan class")
        self.assertEqual(r["orphans"], [{"record_id": "9", "a": "X", "b": "Y"}],
                         "the orphan is reported, with its values, so a human can act on it")

    def test_an_orphan_never_produces_a_conflict_or_an_overwrite_row_either(self):
        r = D.diff_records({"9": {"a": "X", "b": "Y"}}, {}, self.fields, "record_id")
        self.assertEqual(r["conflicts"], [])
        self.assertEqual(r["overwrites"], [])

    def test_an_orphan_row_carries_every_compared_field_even_when_blank(self):
        """A uniform row keeps the report a table, not a ragged edge."""
        r = D.diff_records({"9": {"a": "X"}}, {}, self.fields, "record_id")
        self.assertEqual(r["orphans"], [{"record_id": "9", "a": "X", "b": ""}])
        self.assertEqual(r["counts"][D.ORPHAN], 2, "orphan cells are counted, blank or not")

    def test_a_present_record_is_still_compared_normally(self):
        """Only ABSENCE makes an orphan — an existing but wholly blank record still fills."""
        r = D.diff_records({"9": {"a": "X", "b": "Y"}}, {"9": {"a": "", "b": ""}},
                           self.fields, "record_id")
        self.assertEqual(r["orphans"], [])
        self.assertEqual(r["counts"][D.FILL], 2)
        self.assertEqual(r["updates"], [{"record_id": "9", "a": "X", "b": "Y"}])

    def test_current_ids_with_no_computed_counterpart_are_reported(self):
        """The other half of the gap report: records the linkage found nothing for."""
        r = D.diff_records({"1": {"a": "X", "b": ""}},
                           {"1": {"a": "", "b": ""}, "2": {"a": "q", "b": "r"}},
                           self.fields, "record_id")
        self.assertEqual(r["missing_link"], [{"record_id": "2"}])

    def test_missing_link_is_empty_when_every_current_id_was_computed(self):
        r = D.diff_records({"1": {"a": "X"}}, {"1": {"a": ""}}, self.fields, "record_id")
        self.assertEqual(r["missing_link"], [])

    def test_orphans_and_missing_link_are_the_two_directions_of_the_same_gap(self):
        r = D.diff_records({"1": {"a": "X"}, "9": {"a": "Y"}}, {"1": {"a": ""}, "7": {"a": "z"}},
                           self.fields, "record_id")
        self.assertEqual([o["record_id"] for o in r["orphans"]], ["9"])
        self.assertEqual([m["record_id"] for m in r["missing_link"]], ["7"])

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

    def test_counts_still_add_up_when_some_records_are_orphans(self):
        """Four classes, one accounting: every cell on the computed side lands in exactly one."""
        computed = {"1": {"a": "X", "b": "NEW"}, "9": {"a": "P", "b": "Q"}}
        current = {"1": {"a": "", "b": "OLD"}}
        r = D.diff_records(computed, current, self.fields, "record_id")
        self.assertEqual(sum(r["counts"].values()), 4)
        self.assertEqual(r["counts"][D.ORPHAN], 2)

    def test_overwrite_file_holds_only_the_conflicting_cells(self):
        computed = {"1": {"a": "X", "b": "NEW"}}
        current = {"1": {"a": "", "b": "OLD"}}
        r = D.diff_records(computed, current, self.fields, "record_id")
        self.assertEqual(r["overwrites"], [{"record_id": "1", "b": "NEW"}],
                         "the sign-off file must not smuggle in cells that weren't conflicts")


if __name__ == "__main__":
    unittest.main(verbosity=2)
