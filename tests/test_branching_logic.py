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


@unittest.skipIf(bw is None, "optional dependencies not installed")
class TestPrerequisiteRowWording(unittest.TestCase):
    """0.17.2 #30: the prerequisite header row printed unreadable conditions after "only if".

    An RA opening an amber column saw `only if datediff([dx_date],[surgery_date],"d") > 30` —
    an instruction in a language they don't speak, presented as though we had understood it. We
    hadn't: the cells below are amber for precisely that reason. The row now says so, and still
    shows the raw expression, because that is honestly all there is to show.
    """

    META = {
        "sex": {"field_name": "sex", "select_choices_or_calculations": "1, Male | 2, Female"},
        "treatment": {"field_name": "treatment",
                      "select_choices_or_calculations": "1, Surgery | 2, Chemo"},
    }

    def test_a_readable_condition_still_reads_only_if(self):
        self.assertEqual(bw.prereq_text("[sex] = '2'", self.META), "only if sex = Female")

    def test_a_checkbox_condition_still_reads_only_if(self):
        self.assertEqual(bw.prereq_text("[treatment(1)] = '1'", self.META),
                         "only if treatment includes Surgery")

    def test_no_condition_is_an_empty_cell(self):
        self.assertEqual(bw.prereq_text("", self.META), "")
        self.assertEqual(bw.prereq_text("   ", self.META), "")

    def test_an_unreadable_condition_says_so_and_shows_the_expression(self):
        expr = 'datediff([dx_date],[surgery_date],"d") > 30'
        got = bw.prereq_text(expr, self.META)
        self.assertEqual(got, f"couldn't read this condition: {expr}")
        self.assertNotIn("only if", got)

    def test_a_partly_unreadable_condition_is_treated_as_unreadable(self):
        """One clause we can't parse makes the whole row a guess — don't half-claim it."""
        expr = "[sex] = '2' AND datediff([a],[b],'d') > 5"
        self.assertTrue(bw.prereq_text(expr, self.META).startswith("couldn't read this condition:"))

    def test_readability_matches_what_makes_a_cell_amber(self):
        """The wording and the fill must be driven by the same judgement, or they disagree."""
        for expr in ("[sex] = '2'", "[treatment(1)] = '1'", "[age] >= 18"):
            self.assertTrue(bw.logic_is_readable(expr), expr)
            _applies, certain = bw.evaluate_branching(expr, {"sex": "2", "treatment___1": "1",
                                                             "age": "40"})
            self.assertTrue(certain, expr)
        for expr in ('datediff([a],[b],"d") > 30', "[a] = '1' AND rounddown([x]) = 2"):
            self.assertFalse(bw.logic_is_readable(expr), expr)
            _applies, certain = bw.evaluate_branching(expr, {"a": "1"})
            self.assertFalse(certain, expr)


@unittest.skipIf(bw is None, "optional dependencies not installed")
class TestLabelsAreDisplayOnly(unittest.TestCase):
    """0.19 #41: a field's LABEL is what the RA reads; its NAME is what identifies it.

    `labelize` used to be paired with a `df.rename(columns=label_map)` in the caller, which made
    the label the row's key. REDCap only requires field NAMES to be unique — a live 160-field
    dictionary had 44 labels shared by more than one field — so two columns then carried the
    same name, pandas returned a Series where a value was expected, and the build died with
    `ValueError: Cannot convert ... to Excel`.

    The invariant the fix rests on, pinned here at unit level: labelize translates VALUES and
    never column names.
    """

    METADATA = [
        {"field_name": "record_id", "field_type": "text", "field_label": "Record ID",
         "select_choices_or_calculations": ""},
        {"field_name": "first_date", "field_type": "text", "field_label": "Date of procedure",
         "select_choices_or_calculations": ""},
        {"field_name": "second_date", "field_type": "text", "field_label": "Date of procedure",
         "select_choices_or_calculations": ""},
        {"field_name": "sex", "field_type": "radio", "field_label": "Sex ",
         "select_choices_or_calculations": "1, Male | 2, Female"},
    ]

    def frame(self):
        import pandas as pd
        return pd.DataFrame([{"record_id": "1", "first_date": "2024-01-01",
                              "second_date": "2024-02-02", "sex": "2"}], dtype=str)

    def test_column_names_stay_field_names(self):
        out, label_map = bw.labelize(self.frame(), self.METADATA,
                                     ["first_date", "second_date", "sex"])
        self.assertEqual(list(out.columns), ["record_id", "first_date", "second_date", "sex"])
        self.assertEqual(len(out.columns), len(set(out.columns)))

    def test_the_label_map_is_keyed_by_field_name(self):
        _out, label_map = bw.labelize(self.frame(), self.METADATA,
                                      ["first_date", "second_date", "sex"])
        self.assertEqual(label_map["first_date"], "Date of procedure")
        self.assertEqual(label_map["second_date"], "Date of procedure")
        self.assertEqual(label_map["sex"], "Sex", "labels are cleaned for display")

    def test_values_are_still_turned_into_labels(self):
        """Translating the values is the whole job — only the headers were the problem."""
        out, _label_map = bw.labelize(self.frame(), self.METADATA, ["sex"])
        self.assertEqual(out.iloc[0]["sex"], "Female")

    def test_two_fields_sharing_a_label_keep_their_own_values(self):
        out, label_map = bw.labelize(self.frame(), self.METADATA,
                                     ["first_date", "second_date"])
        row = out.iloc[0]
        self.assertEqual(row["first_date"], "2024-01-01")
        self.assertEqual(row["second_date"], "2024-02-02")
        headers = bw.display_headers(["first_date", "second_date"], label_map)
        self.assertEqual(headers, ["Date of procedure", "Date of procedure (second_date)"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
