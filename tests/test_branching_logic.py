#!/usr/bin/env python3
"""Unit tests for the branching-logic evaluator — the business logic, not the plumbing.

This file exists because a silent-wrong-answer bug lived here undetected: the evaluator treated
any clause it couldn't parse as "field not applicable" and dropped it, while its docstring and
SKILL.md both claimed the opposite. It produced no crash, no traceback and no hang, so every
existing infrastructure test passed while 28% of branching-gated fields on one live cohort — and
70% on another — never appeared in a QA worklist.

Known input -> known output, no REDCap needed.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BW = REPO / "plugins/argo-qa-specialist/skills/qa-worklists/build_worklists.py"


def load():
    spec = importlib.util.spec_from_file_location("build_worklists", BW)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_worklists"] = module
    spec.loader.exec_module(module)
    return module


try:
    bw = load()
except ImportError as e:               # pandas/openpyxl/yaml not installed
    bw = None
    _REASON = f"build_worklists dependencies unavailable: {e}"


@unittest.skipIf(bw is None, "optional dependencies not installed")
class TestClauseParsing(unittest.TestCase):
    def test_quoted_value(self):
        self.assertEqual(bw._clause_parts("[status] = 'complete'"),
                         ("status", None, "=", "complete"))

    def test_unquoted_value(self):
        """The form REDCap's Designer emits for numeric codes — and the one that was broken."""
        self.assertEqual(bw._clause_parts("[oau_collection] = 0"),
                         ("oau_collection", None, "=", "0"))

    def test_checkbox_option(self):
        self.assertEqual(bw._clause_parts("[type_sample_crc(1)] = 1"),
                         ("type_sample_crc", "1", "=", "1"))

    def test_negative_checkbox_code(self):
        self.assertEqual(bw._clause_parts("[reason(-999)] = 1"),
                         ("reason", "-999", "=", "1"))

    def test_numeric_comparison(self):
        """dd-column-spec.md documents [age] >= 18 as valid ARGO branching syntax."""
        self.assertEqual(bw._clause_parts("[age] >= 18"), ("age", None, ">=", "18"))

    def test_double_quoted(self):
        self.assertEqual(bw._clause_parts('[site] <> "MSK"'), ("site", None, "<>", "MSK"))

    def test_genuinely_unparseable_returns_none(self):
        for clause in ("[checked(x)]", "datediff([a],[b],'d') > 30", "not a clause at all"):
            self.assertIsNone(bw._clause_parts(clause), clause)


@unittest.skipIf(bw is None, "optional dependencies not installed")
class TestEvaluateBranching(unittest.TestCase):
    def setUp(self):
        bw.UNPARSEABLE_LOGIC.clear()

    def test_no_logic_always_applies(self):
        self.assertEqual(bw.evaluate_branching("", {}), (True, True))
        self.assertEqual(bw.evaluate_branching("   ", {"a": "1"}), (True, True))

    def test_simple_match(self):
        self.assertEqual(bw.evaluate_branching("[sex] = '1'", {"sex": "1"}), (True, True))
        self.assertEqual(bw.evaluate_branching("[sex] = '1'", {"sex": "2"}), (False, True))

    def test_unquoted_match_is_the_regression_case(self):
        """Before the fix this returned False — the field was dropped from every worklist."""
        applies, certain = bw.evaluate_branching("[type_sample_crc(1)] = 1",
                                                 {"type_sample_crc___1": "1"})
        self.assertTrue(applies)
        self.assertTrue(certain)

    def test_unquoted_non_match(self):
        self.assertEqual(
            bw.evaluate_branching("[type_sample_crc(1)] = 1", {"type_sample_crc___1": "0"}),
            (False, True))

    def test_and_requires_both(self):
        logic = "[a] = 1 and [b] = 0"
        self.assertEqual(bw.evaluate_branching(logic, {"a": "1", "b": "0"}), (True, True))
        self.assertEqual(bw.evaluate_branching(logic, {"a": "1", "b": "9"}), (False, True))

    def test_or_requires_either(self):
        logic = "[a] = 1 OR [b] = 1"
        self.assertEqual(bw.evaluate_branching(logic, {"a": "0", "b": "1"}), (True, True))
        self.assertEqual(bw.evaluate_branching(logic, {"a": "0", "b": "0"}), (False, True))

    def test_lowercase_and_or_are_accepted(self):
        # REDCap writes lowercase 'and' in practice.
        self.assertEqual(bw.evaluate_branching("[a] = 1 and [b] = 1", {"a": "1", "b": "1"}),
                         (True, True))

    def test_not_equal_operators(self):
        self.assertEqual(bw.evaluate_branching("[s] <> '1'", {"s": "2"}), (True, True))
        self.assertEqual(bw.evaluate_branching("[s] != '1'", {"s": "1"}), (False, True))

    def test_numeric_comparisons(self):
        self.assertEqual(bw.evaluate_branching("[age] >= 18", {"age": "18"}), (True, True))
        self.assertEqual(bw.evaluate_branching("[age] >= 18", {"age": "17"}), (False, True))
        self.assertEqual(bw.evaluate_branching("[age] < 5", {"age": "3"}), (True, True))

    def test_blank_in_a_numeric_comparison_matches_redcap_and_is_certain(self):
        """REDCap evaluates [age] >= 18 with a blank age as false and hides the field.

        We match that exactly. Calling it "uncertain" instead would be defensible in the
        abstract but wrong in practice: on the Study Tracker it marked a quarter of all cells
        "please check", which is its own kind of useless.
        """
        self.assertEqual(bw.evaluate_branching("[age] >= 18", {"age": ""}), (False, True))

    def test_non_numeric_value_in_a_numeric_comparison_is_uncertain(self):
        """'unknown' is not blank and not a number — here we genuinely can't tell."""
        applies, certain = bw.evaluate_branching("[age] >= 18", {"age": "unknown"})
        self.assertTrue(applies, "an uncomparable value must not silently drop the field")
        self.assertFalse(certain)

    def test_unparseable_surfaces_but_is_marked_uncertain(self):
        applies, certain = bw.evaluate_branching("datediff([a],[b],'d') > 30", {})
        self.assertTrue(applies, "never drop a field because we couldn't read its condition")
        self.assertFalse(certain, "and never assert it as a confirmed gap either")

    def test_unparseable_logic_is_recorded_for_reporting(self):
        bw.evaluate_branching("checked([x], 1)", {})
        self.assertTrue(bw.UNPARSEABLE_LOGIC,
                        "unreadable conditions must be reported, not swallowed")

    def test_a_satisfied_branch_wins_over_an_unparseable_one(self):
        """If one OR-branch clearly matches, that's a certain answer regardless of the other."""
        applies, certain = bw.evaluate_branching("[a] = 1 OR datediff([x],[y],'d') > 3", {"a": "1"})
        self.assertEqual((applies, certain), (True, True))

    def test_missing_column_is_treated_as_blank_not_a_crash(self):
        self.assertEqual(bw.evaluate_branching("[nope] = '1'", {}), (False, True))


@unittest.skipIf(bw is None, "optional dependencies not installed")
class TestTriggerExtraction(unittest.TestCase):
    def test_extracts_gate_fields_from_unquoted_logic(self):
        """Gate fields were also being missed, so prerequisite columns went absent too."""
        self.assertEqual(
            bw.extract_branching_triggers("[type_sample_crc(1)] = 1 and [oau_collection] = 0"),
            ["type_sample_crc", "oau_collection"])

    def test_deduplicates(self):
        self.assertEqual(bw.extract_branching_triggers("[a] = 1 OR [a] = 2"), ["a"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
