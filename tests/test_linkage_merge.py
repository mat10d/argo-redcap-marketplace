#!/usr/bin/env python3
"""End-to-end test of the link-data READ SIDE across two synthetic studies.

The analyst task "merge more than one database for analysis" (PLAN.md Phase 1.5)
had no automated coverage: every linkage test to date compared one study against
a flat pathology sheet. This drives the real entry point —
`link-data/diff_payload.py`, which wraps `argo_diff.diff_records()` — over two
whole synthetic studies that share the `syn_id` space:

    testing/fixtures/synthetic-study/     200 records (the primary)
    testing/fixtures/synthetic-study-b/    60 records (the sub-study)

and asserts fills / conflicts / no-ops / unmatched rows against
synthetic-study-b/MANIFEST.json's engineered counts — numbers, not vibes.

It also drives `link_studies.py`, the step BEFORE the diff: deriving the join
key, checking the matched pairs by name, and producing the hard-link file the
user uploads to make the link permanent. That runs against the same fixture's
`parent_registry.csv` (the parent study's identity export) and its engineered
name discrepancies.

Stdlib only: no pandas, no network, no keys. Nothing to skip on.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PRIMARY = REPO / "testing" / "fixtures" / "synthetic-study"
STUDY_B = REPO / "testing" / "fixtures" / "synthetic-study-b"
LINK = REPO / "plugins" / "argo-database-manager" / "skills" / "link-data"
DIFF_PAYLOAD = LINK / "diff_payload.py"
MASTER = LINK / "build_master_linkage.py"
LINK_STUDIES = LINK / "link_studies.py"

FIELDS = "histology_grade,margin_status"


def read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def run_link(*args, parent_name="syn", child_name="synb"):
    """link_studies.py over the fixture pair: the SYN registry and the SYN-B sub-study."""
    return subprocess.run(
        [sys.executable, str(LINK_STUDIES),
         "--parent", str(STUDY_B / "parent_registry.csv"), "--parent-name", parent_name,
         "--child", str(STUDY_B / "records.csv"), "--child-name", child_name, *args],
        capture_output=True, text=True, timeout=300)


class TestTwoStudyLinkage(unittest.TestCase):
    """diff_payload.py with study B as COMPUTED and the primary as CURRENT."""

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp())
        cls.proc = subprocess.run(
            [sys.executable, str(DIFF_PAYLOAD),
             "--computed", str(STUDY_B / "records.csv"),
             "--current", str(PRIMARY / "records.csv"),
             "--id-field", "syn_id",
             "--fields", FIELDS,
             "--out-dir", str(cls.out),
             "--prefix", "merge"],
            capture_output=True, text=True, timeout=300,
        )
        cls.manifest = json.loads((STUDY_B / "MANIFEST.json").read_text())
        cls.expected = cls.manifest["expected_diff"]
        cls.overlap = cls.manifest["overlap"]
        if cls.proc.returncode == 0:
            cls.updates = read_csv(cls.out / "merge_update.csv")
            cls.conflicts = read_csv(cls.out / "merge_conflicts.csv")
            cls.overwrites = read_csv(cls.out / "merge_overwrite.csv")
            cls.unmatched = read_csv(cls.out / "merge_no_record_to_fill.csv")
            cls.missing_link = read_csv(cls.out / "merge_missing_link.csv")
        # The MANIFEST was written when orphans were (wrongly) counted as fills, so its
        # top-level fill_cells/update_csv_rows are fills PLUS orphans. The engineered
        # sub-counts it also records — fill_cells_shared_ids_only,
        # orphan_cells_classified_fill — are the fixed behaviour's numbers, and are what
        # the assertions below use. Both are checked against each other in
        # test_every_cell_is_accounted_for, so the fixture stays honest either way.

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    # -- it runs at all -----------------------------------------------------

    def test_diff_payload_completes_without_crashing(self):
        self.assertEqual(self.proc.returncode, 0,
                         f"diff_payload crashed:\n{self.proc.stderr[-1500:]}")
        self.assertNotIn("Traceback", self.proc.stdout + self.proc.stderr)

    def test_all_five_output_files_written(self):
        """Three payload files, plus the two halves of the gap report link-data promises."""
        for name in ("merge_update.csv", "merge_conflicts.csv", "merge_overwrite.csv",
                     "merge_no_record_to_fill.csv", "merge_missing_link.csv"):
            self.assertTrue((self.out / name).exists(), f"{name} not produced")

    # -- the headline numbers ----------------------------------------------

    def test_reported_cell_counts_match_the_manifest(self):
        """The counts printed by the tool are the ones the fixture engineered.

        Safe-fills are the SHARED-id fills only: an id with no record on the current side
        has nothing to fill, so it is reported as an orphan instead of inflating this number.
        """
        out = self.proc.stdout
        self.assertIn(f"safe-fills : {self.expected['fill_cells_shared_ids_only']} ", out)
        self.assertIn(f"conflicts  : {self.expected['conflict_cells']} ", out)
        self.assertIn(f"no-ops     : {self.expected['noop_cells']}", out)

    def test_reported_gap_counts_match_the_manifest(self):
        """Both gaps are named out loud, with counts, not just written to a file."""
        out = self.proc.stdout
        self.assertIn(f"no record  : {self.overlap['n_only_in_study_b']} rows", out)
        self.assertIn(f"no link    : {self.overlap['n_only_in_primary']} records", out)

    def test_payload_row_counts_match_the_manifest(self):
        # One filled field per filled record (the two fill classes are disjoint), so the
        # update file has exactly one row per shared fill id — and none for the orphans.
        shared_fill_rows = (self.overlap["n_shared_fill_histology_grade"]
                            + self.overlap["n_shared_fill_margin_status"])
        self.assertEqual(len(self.updates), shared_fill_rows)
        self.assertEqual(len(self.conflicts), self.expected["conflicts_csv_rows"])
        self.assertEqual(len(self.overwrites), self.expected["overwrite_csv_rows"])
        self.assertEqual(len(self.updates) + self.overlap["n_only_in_study_b"],
                         self.expected["update_csv_rows"],
                         "the MANIFEST's update_csv_rows counts the orphan rows that used to "
                         "be smuggled into the payload — fills + orphans should equal it")

    def test_every_cell_is_accounted_for(self):
        """Four classes now, and they still add up to every cell on the study-B side."""
        e = self.expected
        self.assertEqual(e["fill_cells_shared_ids_only"] + e["conflict_cells"]
                         + e["noop_cells"] + e["orphan_cells_classified_fill"],
                         e["cells_compared"])
        self.assertEqual(e["fill_cells_shared_ids_only"] + e["orphan_cells_classified_fill"],
                         e["fill_cells"],
                         "the MANIFEST's fill_cells is the pre-fix total (fills + orphans)")
        self.assertEqual(e["cells_compared"],
                         self.overlap["n_records_study_b"] * len(FIELDS.split(",")))

    # -- fills --------------------------------------------------------------

    def test_fills_on_shared_ids_are_exactly_the_engineered_blanks(self):
        """A shared id may only be filled where the PRIMARY was blank."""
        shared = set(self.overlap["ids_by_class"]["fill_grade"])
        shared_m = set(self.overlap["ids_by_class"]["fill_margin"])
        got_g = {r["syn_id"] for r in self.updates if r.get("histology_grade")}
        got_m = {r["syn_id"] for r in self.updates if r.get("margin_status")}
        self.assertEqual(got_g, shared)
        self.assertEqual(got_m, shared_m)
        self.assertEqual(len(shared) + len(shared_m),
                         self.expected["fill_cells_shared_ids_only"])

    def test_no_fill_ever_lands_on_a_populated_primary_cell(self):
        """The core write-back guarantee: fills only ever touch blanks."""
        primary = {r["syn_id"]: r for r in read_csv(PRIMARY / "records.csv")}
        for row in self.updates:
            cur = primary.get(row["syn_id"])
            self.assertIsNotNone(cur, f"{row['syn_id']} has no record in the current file — "
                                      f"it must never reach the update payload")
            for field in FIELDS.split(","):
                if row.get(field, ""):
                    self.assertEqual(cur[field], "",
                                     f"{row['syn_id']}.{field}: fill proposed over "
                                     f"an existing value {cur[field]!r}")

    # -- conflicts ----------------------------------------------------------

    def test_conflicts_are_exactly_the_engineered_conflict_ids(self):
        ids = {r["syn_id"] for r in self.conflicts}
        self.assertEqual(ids, set(self.overlap["ids_by_class"]["conflict"]))
        self.assertEqual(len(self.conflicts),
                         self.overlap["n_shared_conflicting"]
                         * self.overlap["n_shared_conflicting_fields"])

    def test_every_conflict_row_really_disagrees(self):
        for row in self.conflicts:
            self.assertNotEqual(row["existing"], row["computed"], row)
            self.assertNotEqual(row["existing"], "", row)
            self.assertNotEqual(row["computed"], "", row)

    def test_conflicts_are_never_in_the_update_payload(self):
        """Quarantine means quarantine: nothing conflicting may reach *_update.csv."""
        conflicted = {(r["syn_id"], r["field"]) for r in self.conflicts}
        for row in self.updates:
            for field in FIELDS.split(","):
                if row.get(field, ""):
                    self.assertNotIn((row["syn_id"], field), conflicted)

    # -- agreeing records ---------------------------------------------------

    def test_agreeing_ids_appear_in_no_payload_at_all(self):
        agree = set(self.overlap["ids_by_class"]["agree"])
        for name, rows in (("update", self.updates), ("conflicts", self.conflicts),
                           ("overwrite", self.overwrites)):
            self.assertFalse(agree & {r["syn_id"] for r in rows},
                             f"agreeing records leaked into {name}")

    # -- orphans (was a pinned defect; now the guarantee) --------------------

    def test_study_b_only_ids_are_reported_never_filled(self):
        """The fix for NITS #2.

        diff_records() used to iterate the computed side and read an id missing
        from the current side as an all-blank record, so all 15 study-B-only ids
        became safe-fill rows: importing merge_update.csv would have CREATED
        those records in REDCap. They now land in the no-record-to-fill report —
        reported, never payload.
        """
        b_only = set(self.overlap["ids_by_class"]["b_only"])
        self.assertEqual(len(b_only), 15)

        self.assertEqual({r["syn_id"] for r in self.unmatched}, b_only,
                         "the no-record report must be exactly the study-B-only ids")
        self.assertEqual(self.expected["orphan_cells_classified_fill"],
                         len(b_only) * len(FIELDS.split(",")))

        for name, rows in (("update", self.updates), ("conflicts", self.conflicts),
                           ("overwrite", self.overwrites)):
            self.assertFalse(b_only & {r["syn_id"] for r in rows},
                             f"an unmatched row reached {name}.csv — importing it would "
                             "create records")

    def test_no_fill_cell_anywhere_comes_from_an_unmatched_row(self):
        """Zero cells, not just zero rows: nothing of an unmatched row is pushable."""
        b_only = set(self.overlap["ids_by_class"]["b_only"])
        cells = sum(1 for row in self.updates if row["syn_id"] in b_only
                    for f in FIELDS.split(",") if row.get(f, ""))
        self.assertEqual(cells, 0)

    def test_unmatched_rows_carry_the_study_b_values(self):
        """A gap report nobody can act on is not a report — the values come with it."""
        study_b = {r["syn_id"]: r for r in read_csv(STUDY_B / "records.csv")}
        for row in self.unmatched:
            for field in FIELDS.split(","):
                self.assertEqual(row[field], study_b[row["syn_id"]][field])

    def test_primary_ids_absent_from_study_b_are_reported(self):
        """The other half of the gap: the 155 primary records the linkage found nothing for."""
        self.assertEqual(self.overlap["n_only_in_primary"], 155)
        self.assertEqual(len(self.missing_link), 155)
        primary_ids = {r["syn_id"] for r in read_csv(PRIMARY / "records.csv")}
        b_ids = {r["syn_id"] for r in read_csv(STUDY_B / "records.csv")}
        self.assertEqual({r["syn_id"] for r in self.missing_link}, primary_ids - b_ids)

    def test_nothing_outside_the_engineered_classes_reaches_any_payload_file(self):
        for row in self.updates + self.conflicts + self.overwrites:
            self.assertIn(row["syn_id"],
                          set(self.overlap["ids_by_class"]["fill_grade"])
                          | set(self.overlap["ids_by_class"]["fill_margin"])
                          | set(self.overlap["ids_by_class"]["conflict"]))


class TestDefaultFieldSelection(unittest.TestCase):
    """Without --fields, diff_payload compares every shared column EXCEPT REDCap's own.

    Two REDCap exports share `redcap_data_access_group`, and the default run used to treat
    the data access group as a linkable data field — a proposal to move records between
    sites, filed as a safe fill. Structural columns (`redcap_*`) and the per-form
    `*_complete` status columns are excluded by default, and the tool says which it skipped.
    """

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp())
        cls.proc = subprocess.run(
            [sys.executable, str(DIFF_PAYLOAD),
             "--computed", str(STUDY_B / "records.csv"),
             "--current", str(PRIMARY / "records.csv"),
             "--id-field", "syn_id", "--out-dir", str(cls.out), "--prefix", "auto"],
            capture_output=True, text=True, timeout=300)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_the_dag_column_is_not_compared_by_default(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-800:])
        rows = read_csv(self.out / "auto_update.csv")
        cols = list(rows[0].keys()) if rows else []
        self.assertNotIn("redcap_data_access_group", cols,
                         "the data access group is REDCap bookkeeping, not linkage data")
        self.assertIn("histology_grade", cols, "real data fields must still be compared")

    def test_the_skipped_columns_are_named_in_the_output(self):
        """Excluding silently would be its own bug — say what was left out."""
        self.assertIn("not compared", self.proc.stdout)
        self.assertIn("redcap_data_access_group", self.proc.stdout)

    def test_the_default_run_agrees_with_the_explicit_field_run(self):
        """The two comparable fields are the whole of the default comparison."""
        self.assertIn(f"safe-fills : {json.loads((STUDY_B / 'MANIFEST.json').read_text())['expected_diff']['fill_cells_shared_ids_only']} ",
                      self.proc.stdout)


class TestForAnalysisFraming(unittest.TestCase):
    """0.17.2 #33: the read side spoke in write-back language.

    Someone merging two studies for their own analysis got files called `*_update.csv` and
    `*_overwrite.csv` and a closing instruction to "push with overwriteBehavior=normal" — for a
    task where nothing is ever written to REDCap. `--for-analysis` renames the two files for
    what they mean and says nothing about pushing. The comparison itself is byte-identical.
    """

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp())
        cls.proc = subprocess.run(
            [sys.executable, str(DIFF_PAYLOAD), "--for-analysis",
             "--computed", str(STUDY_B / "records.csv"),
             "--current", str(PRIMARY / "records.csv"),
             "--id-field", "syn_id", "--fields", FIELDS,
             "--out-dir", str(cls.out), "--prefix", "merge"],
            capture_output=True, text=True, timeout=300)
        cls.expected = json.loads((STUDY_B / "MANIFEST.json").read_text())["expected_diff"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_it_runs(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-1500:])
        self.assertNotIn("Traceback", self.proc.stdout + self.proc.stderr)

    def test_the_two_payload_files_are_renamed(self):
        self.assertTrue((self.out / "merge_fills.csv").exists())
        self.assertTrue((self.out / "merge_disagreements.csv").exists())
        self.assertFalse((self.out / "merge_update.csv").exists(),
                         "an analysis merge produces nothing called an 'update'")
        self.assertFalse((self.out / "merge_overwrite.csv").exists())

    def test_the_three_reports_are_written_either_way(self):
        """Conflicts, orphans and missing-link are the gap report, not a payload."""
        for name in ("merge_conflicts.csv", "merge_no_record_to_fill.csv",
                     "merge_missing_link.csv"):
            self.assertTrue((self.out / name).exists(), f"{name} not produced")

    def test_nothing_is_said_about_pushing(self):
        out = self.proc.stdout
        for word in ("overwriteBehavior", "Push ", "push ", "Dry-run", "sign-off"):
            self.assertNotIn(word, out, f"{word!r} is write-back language on a read-only task")

    def test_the_numbers_are_the_same_comparison(self):
        self.assertIn(f"fills      : {self.expected['fill_cells_shared_ids_only']} ",
                      self.proc.stdout)
        self.assertIn(f"conflicts  : {self.expected['conflict_cells']} ", self.proc.stdout)
        rows = read_csv(self.out / "merge_fills.csv")
        self.assertEqual(len(rows), self.expected["fill_cells_shared_ids_only"])

    def test_both_gap_counts_are_still_named_out_loud(self):
        self.assertIn("no record  :", self.proc.stdout)
        self.assertIn("no link    :", self.proc.stdout)


class TestMasterLinkageTable(unittest.TestCase):
    """0.17.2 #34: link-data promised `master_linkage.csv` + `*_integrity.csv` and shipped no
    code that wrote either. A walkthrough had to hand-write the script; it is now the skill's
    own helper, generalised off the two study names it was born with.

    Driven over the same two synthetic studies as the diff test above: 200 cohort records, 60
    pathology records, 45 of them shared.
    """

    LEFT_NAME, RIGHT_NAME = "cohort", "pathology"

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp())
        cls.diff = subprocess.run(
            [sys.executable, str(DIFF_PAYLOAD), "--for-analysis",
             "--computed", str(STUDY_B / "records.csv"),
             "--current", str(PRIMARY / "records.csv"),
             "--id-field", "syn_id", "--fields", FIELDS,
             "--out-dir", str(cls.out), "--prefix", "path"],
            capture_output=True, text=True, timeout=300)
        cls.proc = subprocess.run(
            [sys.executable, str(MASTER),
             "--left", str(PRIMARY / "records.csv"), "--left-name", cls.LEFT_NAME,
             "--right", str(STUDY_B / "records.csv"), "--right-name", cls.RIGHT_NAME,
             "--diff-dir", str(cls.out), "--diff-prefix", "path",
             "--id-field", "syn_id", "--out", str(cls.out / "master_linkage.csv")],
            capture_output=True, text=True, timeout=300)
        cls.manifest = json.loads((STUDY_B / "MANIFEST.json").read_text())
        cls.overlap = cls.manifest["overlap"]
        if cls.proc.returncode == 0:
            cls.rows = read_csv(cls.out / "master_linkage.csv")
            cls.integrity = read_csv(cls.out / "path_integrity.csv")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    # -- it runs at all -----------------------------------------------------

    def test_both_steps_complete(self):
        self.assertEqual(self.diff.returncode, 0, self.diff.stderr[-1000:])
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-1500:])
        self.assertNotIn("Traceback", self.proc.stdout + self.proc.stderr)

    def test_both_promised_files_exist(self):
        self.assertTrue((self.out / "master_linkage.csv").exists())
        self.assertTrue((self.out / "path_integrity.csv").exists())

    # -- the headline numbers ----------------------------------------------

    def test_one_row_per_person_across_both_studies(self):
        self.assertEqual(len(self.rows), 215)
        self.assertEqual(len({r["syn_id"] for r in self.rows}), 215, "ids must be unique")

    def test_forty_five_are_linked_on_both_sides(self):
        linked = [r for r in self.rows
                  if r[f"{self.LEFT_NAME}_linked"] == "1"
                  and r[f"{self.RIGHT_NAME}_linked"] == "1"]
        self.assertEqual(len(linked), 45)
        self.assertEqual(len(linked), self.overlap["n_shared_ids"])

    def test_fifteen_are_right_side_only(self):
        right_only = [r for r in self.rows if r["link_class"] == f"{self.RIGHT_NAME}_only"]
        self.assertEqual(len(right_only), 15)
        self.assertEqual({r["syn_id"] for r in right_only},
                         set(self.overlap["ids_by_class"]["b_only"]))
        for row in right_only:
            self.assertEqual(row[f"{self.LEFT_NAME}_linked"], "0")

    def test_one_hundred_and_fifty_five_are_left_side_only(self):
        left_only = [r for r in self.rows if r["link_class"] == f"{self.LEFT_NAME}_only"]
        self.assertEqual(len(left_only), 155)
        self.assertEqual(len(left_only), self.overlap["n_only_in_primary"])
        for row in left_only:
            self.assertEqual(row[f"{self.RIGHT_NAME}_linked"], "0")

    def test_the_classes_partition_the_table(self):
        classes = {}
        for row in self.rows:
            classes[row["link_class"]] = classes.get(row["link_class"], 0) + 1
        self.assertEqual(sum(classes.values()), 215)
        self.assertEqual(classes["matched_conflict"], self.overlap["n_shared_conflicting"])
        self.assertEqual(classes["matched_agree"], self.overlap["n_shared_agreeing"])
        self.assertEqual(
            classes["matched_fill"],
            self.overlap["n_shared_fill_histology_grade"]
            + self.overlap["n_shared_fill_margin_status"])

    # -- the design that had to survive generalisation ----------------------

    def test_the_flag_columns_are_named_after_the_two_sources(self):
        header = list(self.rows[0].keys())
        self.assertIn("cohort_linked", header)
        self.assertIn("pathology_linked", header)
        self.assertNotIn("left_linked", header, "the columns take the names the user gave")
        self.assertIn("link_class", header)
        self.assertIn("conflict_fields", header)

    def test_a_column_on_both_sides_keeps_both_values_suffixed(self):
        """Never reconcile a disagreement automatically — carry both, flag the row."""
        header = list(self.rows[0].keys())
        for field in FIELDS.split(","):
            self.assertIn(field, header)
            self.assertIn(f"{field}_{self.RIGHT_NAME}", header,
                          "the right-hand source's value must survive under a suffix")
        left = {r["syn_id"]: r for r in read_csv(PRIMARY / "records.csv")}
        right = {r["syn_id"]: r for r in read_csv(STUDY_B / "records.csv")}
        for row in self.rows:
            rid = row["syn_id"]
            for field in FIELDS.split(","):
                self.assertEqual(row[field], left.get(rid, {}).get(field, ""))
                self.assertEqual(row[f"{field}_{self.RIGHT_NAME}"],
                                 right.get(rid, {}).get(field, ""))

    def test_conflicting_rows_name_the_fields_that_disagree(self):
        conflicted = [r for r in self.rows if r["link_class"] == "matched_conflict"]
        self.assertEqual({r["syn_id"] for r in conflicted},
                         set(self.overlap["ids_by_class"]["conflict"]))
        for row in conflicted:
            self.assertTrue(row["conflict_fields"].strip(),
                            f"{row['syn_id']} is flagged as a conflict but names no field")
            for field in row["conflict_fields"].split("; "):
                self.assertIn(field, FIELDS.split(","))
                self.assertNotEqual(row[field], row[f"{field}_{self.RIGHT_NAME}"])

    def test_rows_that_agree_carry_no_conflict_fields(self):
        for row in self.rows:
            if row["link_class"] != "matched_conflict":
                self.assertEqual(row["conflict_fields"], "", row["syn_id"])

    # -- the integrity report ----------------------------------------------

    def test_the_integrity_report_is_worst_first(self):
        order = ["high", "medium", "low", "info"]
        seen = [row["severity"] for row in self.integrity]
        self.assertEqual(seen, sorted(seen, key=order.index),
                         f"severities out of order: {seen}")
        self.assertEqual([row["rank"] for row in self.integrity],
                         [str(i) for i in range(1, len(self.integrity) + 1)])

    def test_the_worst_issue_is_the_unmatched_right_side_records(self):
        top = self.integrity[0]
        self.assertEqual(top["severity"], "high")
        self.assertEqual(int(top["n_records"]), 15)
        self.assertIn("pathology", top["issue"])

    def test_an_issue_with_nothing_in_it_drops_to_info(self):
        """A clean check must not sit at the top of the report shouting 'high'."""
        for row in self.integrity:
            if int(row["n_records"]) == 0:
                self.assertEqual(row["severity"], "info", row["issue"])

    def test_the_counts_in_the_report_match_the_table(self):
        by_issue = {row["issue"]: int(row["n_records"]) for row in self.integrity}
        classes = {}
        for row in self.rows:
            classes[row["link_class"]] = classes.get(row["link_class"], 0) + 1
        self.assertEqual(by_issue["pathology records with no matching cohort record"],
                         classes["pathology_only"])
        self.assertEqual(by_issue["cohort records with no matching pathology record"],
                         classes["cohort_only"])
        self.assertEqual(by_issue["Records where the two sources disagree on a value"],
                         classes["matched_conflict"])
        self.assertEqual(by_issue["Duplicate join IDs"], 0,
                         "syn_id is unique in both fixtures")

    # -- the mistake that would matter --------------------------------------

    def test_swapping_left_and_right_is_refused_not_silently_inverted(self):
        proc = subprocess.run(
            [sys.executable, str(MASTER),
             "--left", str(STUDY_B / "records.csv"), "--left-name", "b",
             "--right", str(PRIMARY / "records.csv"), "--right-name", "a",
             "--diff-dir", str(self.out), "--diff-prefix", "path",
             "--id-field", "syn_id", "--out", str(self.out / "wrong.csv")],
            capture_output=True, text=True, timeout=300)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("swapped", proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_it_also_reads_a_write_back_run(self):
        """The same merge after a normal (non---for-analysis) diff, whose files are named
        _update/_overwrite. One helper, either upstream framing."""
        out = Path(tempfile.mkdtemp())
        try:
            subprocess.run(
                [sys.executable, str(DIFF_PAYLOAD),
                 "--computed", str(STUDY_B / "records.csv"),
                 "--current", str(PRIMARY / "records.csv"),
                 "--id-field", "syn_id", "--fields", FIELDS,
                 "--out-dir", str(out), "--prefix", "wb"],
                capture_output=True, text=True, timeout=300, check=True)
            proc = subprocess.run(
                [sys.executable, str(MASTER),
                 "--left", str(PRIMARY / "records.csv"), "--left-name", "cohort",
                 "--right", str(STUDY_B / "records.csv"), "--right-name", "pathology",
                 "--diff-dir", str(out), "--diff-prefix", "wb",
                 "--id-field", "syn_id", "--out", str(out / "master_linkage.csv")],
                capture_output=True, text=True, timeout=300)
            self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
            self.assertEqual(len(read_csv(out / "master_linkage.csv")), 215)
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_a_missing_diff_output_explains_itself(self):
        proc = subprocess.run(
            [sys.executable, str(MASTER),
             "--left", str(PRIMARY / "records.csv"),
             "--right", str(STUDY_B / "records.csv"),
             "--diff-dir", str(self.out), "--diff-prefix", "nothing-here",
             "--id-field", "syn_id", "--out", str(self.out / "nope.csv")],
            capture_output=True, text=True, timeout=300)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("diff_payload.py", proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_a_wrong_id_field_names_the_columns_it_did_find(self):
        proc = subprocess.run(
            [sys.executable, str(MASTER),
             "--left", str(PRIMARY / "records.csv"),
             "--right", str(STUDY_B / "records.csv"),
             "--diff-dir", str(self.out), "--diff-prefix", "path",
             "--id-field", "not_a_column", "--out", str(self.out / "nope.csv")],
            capture_output=True, text=True, timeout=300)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--id-field", proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)


class TestJoinKeySurvey(unittest.TestCase):
    """0.19 #49, step one: the work is DERIVING the join key, and it has to be shown.

    `--suggest` surveys both files and ranks the columns that could join them, with the
    numbers behind each. It writes nothing: the key is confirmed with the user first.

    The fixture engineers exactly the comparison a real linkage turns on — the ported
    parent record ID matches all 45 shared people, the hospital number only 38 (five were
    never recorded, two are mistyped) — so the survey has to put syn_id first and say why.
    """

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp())
        cls.proc = run_link("--suggest", parent_name="syn", child_name="synb")
        cls.linking = json.loads((STUDY_B / "MANIFEST.json").read_text())["linking"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_it_runs(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-1500:])
        self.assertNotIn("Traceback", self.proc.stdout + self.proc.stderr)

    def test_the_shared_key_is_the_first_candidate(self):
        """syn_id is in both files and matches every shared person — it must rank first."""
        first = [ln for ln in self.proc.stdout.splitlines()
                 if re.match(r"\s*1\.\s", ln)]
        self.assertTrue(first, f"no ranked candidates printed:\n{self.proc.stdout}")
        self.assertRegex(first[0], r"^\s*1\.\s+syn_id\b",
                         "the survey must name syn_id as the shared key")

    def test_the_candidate_counts_are_the_engineered_ones(self):
        out = self.proc.stdout
        self.assertIn(f"matches {self.linking['n_matched']} of the "
                      f"{self.linking['n_child_records']} synb rows", out)
        self.assertIn(f"matches {self.linking['n_hospital_no_matches']} of the "
                      f"{self.linking['n_child_records']} synb rows", out,
                      "the hospital number is the weaker key and its count must be shown")

    def test_the_weaker_candidate_is_ranked_second_and_the_gap_named(self):
        second = [ln for ln in self.proc.stdout.splitlines() if re.match(r"\s*2\.\s", ln)]
        self.assertRegex(second[0], r"^\s*2\.\s+hospital_no\b")
        gap = self.linking["n_matched"] - self.linking["n_hospital_no_matches"]
        self.assertIn(f"{gap} fewer", self.proc.stdout,
                      "say how much better the best key is, not just that it is best")

    def test_a_coded_field_is_never_proposed_as_a_key(self):
        """A column with three possible values overlaps enormously and joins nobody.

        Run against the primary study's full 49-column export, which shares
        histology_grade, margin_status and the data access group with SYN-B: only the
        near-unique column may be offered as a key, or the survey is noise.
        """
        proc = subprocess.run(
            [sys.executable, str(LINK_STUDIES), "--suggest",
             "--parent", str(PRIMARY / "records.csv"), "--parent-name", "syn",
             "--child", str(STUDY_B / "records.csv"), "--child-name", "synb"],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        self.assertNotIn("histology_grade", proc.stdout)
        self.assertNotIn("margin_status", proc.stdout)
        self.assertNotIn("redcap_data_access_group", proc.stdout)
        candidates = [ln for ln in proc.stdout.splitlines() if re.match(r"\s*\d\.\s", ln)]
        self.assertEqual(len(candidates), 1, f"only syn_id should be offered: {candidates}")
        self.assertIn("syn_id", candidates[0])

    def test_it_says_so_when_only_one_side_carries_names(self):
        """The primary export has no name columns, so a matched pair can't be checked."""
        proc = subprocess.run(
            [sys.executable, str(LINK_STUDIES), "--suggest",
             "--parent", str(PRIMARY / "records.csv"), "--parent-name", "syn",
             "--child", str(STUDY_B / "records.csv"), "--child-name", "synb"],
            capture_output=True, text=True, timeout=300)
        self.assertIn("Only one of the two files carries names", proc.stdout)

    def test_it_reports_the_name_columns_it_will_check_against(self):
        self.assertIn("first_name", self.proc.stdout)
        self.assertIn("surname", self.proc.stdout)

    def test_it_writes_nothing_and_says_so(self):
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertIn("NOTHING HAS BEEN WRITTEN", self.proc.stdout)

    def test_a_ported_id_under_a_different_heading_is_still_found(self):
        """Matteo's other shape: the child carries the parent's number as `crc_redcap_number`.

        The survey compares columns by their VALUES, so a heading the two studies never
        agreed on is found exactly as well as one they did.
        """
        tmp = Path(tempfile.mkdtemp())
        try:
            rows = read_csv(STUDY_B / "records.csv")
            header = ["crc_redcap_number" if c == "syn_id" else c for c in rows[0]]
            renamed = tmp / "child_renamed.csv"
            with open(renamed, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=header)
                w.writeheader()
                for r in rows:
                    w.writerow({("crc_redcap_number" if k == "syn_id" else k): v
                                for k, v in r.items()})
            proc = subprocess.run(
                [sys.executable, str(LINK_STUDIES), "--suggest",
                 "--parent", str(STUDY_B / "parent_registry.csv"), "--parent-name", "syn",
                 "--child", str(renamed), "--child-name", "synb"],
                capture_output=True, text=True, timeout=300)
            self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
            first = [ln for ln in proc.stdout.splitlines() if re.match(r"\s*1\.\s", ln)][0]
            self.assertIn("crc_redcap_number", first)
            self.assertIn("syn_id", first, "name the parent's heading too, not just the child's")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestHardLinkRun(unittest.TestCase):
    """0.19 #49: the culminating deliverable of a linking request.

    45 of the 60 SYN-B participants exist in the SYN cohort. The run has to produce a
    two-column file for exactly those 45, the two missing-link reports (15 and 155) with
    names on them so a person can review them by eye, and the name-discrepancy table for
    the three engineered mismatches.
    """

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp())
        cls.proc = run_link("--key", "syn_id", "--out-dir", str(cls.out),
                            parent_name="syn", child_name="synb")
        cls.manifest = json.loads((STUDY_B / "MANIFEST.json").read_text())
        cls.linking = cls.manifest["linking"]
        cls.child = {r["syn_id"]: r for r in read_csv(STUDY_B / "records.csv")}
        cls.parent = {r["syn_id"]: r for r in read_csv(STUDY_B / "parent_registry.csv")}
        if cls.proc.returncode == 0:
            cls.hard = read_csv(cls.out / "synb_hard_link.csv")
            cls.child_missing = read_csv(cls.out / "synb_missing_link.csv")
            cls.parent_missing = read_csv(cls.out / "syn_missing_link.csv")
            cls.names = read_csv(cls.out / "synb_name_review.csv")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_it_runs(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-1500:])
        self.assertNotIn("Traceback", self.proc.stdout + self.proc.stderr)

    def test_the_four_files_are_written(self):
        for name in ("synb_hard_link.csv", "synb_missing_link.csv",
                     "syn_missing_link.csv", "synb_name_review.csv"):
            self.assertTrue((self.out / name).exists(), f"{name} not produced")

    # -- the hard link ------------------------------------------------------

    def test_the_hard_link_has_exactly_two_columns(self):
        """It is uploaded into REDCap; every extra column is a chance to overwrite something."""
        header = list(self.hard[0].keys())
        self.assertEqual(header, [self.linking["child_record_id_field"],
                                  self.linking["join_key"]])
        self.assertEqual(len(header), 2)

    def test_the_hard_link_holds_exactly_the_linked_people(self):
        self.assertEqual(len(self.hard), self.linking["n_matched"])
        self.assertEqual(len(self.hard), 45)
        linked = set(self.child) & set(self.parent)
        self.assertEqual({r["syn_id"] for r in self.hard}, linked)
        self.assertEqual(len({r["synb_id"] for r in self.hard}), 45,
                         "one row per child record — a repeated id would link twice")

    def test_every_hard_link_row_pairs_the_two_studies_own_numbers(self):
        for row in self.hard:
            self.assertEqual(row["synb_id"], self.child[row["syn_id"]]["synb_id"])
            self.assertEqual(row["syn_id"], self.parent[row["syn_id"]]["syn_id"],
                             "the parent's number must be written as the PARENT holds it")

    def test_no_unlinked_record_reaches_the_hard_link(self):
        """The 15 child records with no parent must never be uploaded as a link."""
        b_only = set(self.manifest["overlap"]["ids_by_class"]["b_only"])
        self.assertFalse(b_only & {r["syn_id"] for r in self.hard})

    def test_the_link_field_can_be_named_for_the_child_projects_own_field(self):
        """The file is imported into the child project, so the heading is that project's."""
        out = Path(tempfile.mkdtemp())
        try:
            proc = run_link("--key", "syn_id", "--link-field", "crc_redcap_number",
                            "--out-dir", str(out), parent_name="syn", child_name="synb")
            self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
            rows = read_csv(out / "synb_hard_link.csv")
            self.assertEqual(list(rows[0].keys()), ["synb_id", "crc_redcap_number"])
            self.assertEqual(len(rows), 45)
        finally:
            shutil.rmtree(out, ignore_errors=True)

    # -- the two missing-link reports ---------------------------------------

    def test_the_child_missing_link_file_is_the_engineered_fifteen(self):
        self.assertEqual(len(self.child_missing), self.linking["n_child_only"])
        self.assertEqual(len(self.child_missing), 15)
        self.assertEqual({r["syn_id"] for r in self.child_missing},
                         set(self.manifest["overlap"]["ids_by_class"]["b_only"]))

    def test_the_parent_missing_link_file_is_the_engineered_one_five_five(self):
        self.assertEqual(len(self.parent_missing), self.linking["n_parent_only"])
        self.assertEqual(len(self.parent_missing), 155)
        self.assertEqual({r["syn_id"] for r in self.parent_missing},
                         set(self.parent) - set(self.child))

    def test_both_missing_link_files_carry_name_and_surname(self):
        """These get resolved by a person reading down the list and recognising people."""
        for rows in (self.child_missing, self.parent_missing):
            header = list(rows[0].keys())
            self.assertIn("first_name", header)
            self.assertIn("surname", header)
            for row in rows:
                self.assertTrue(row["first_name"].strip(), row)
                self.assertTrue(row["surname"].strip(), row)

    def test_the_missing_link_rows_carry_the_names_the_files_hold(self):
        for row in self.child_missing:
            source = self.child[row["syn_id"]]
            self.assertEqual(row["first_name"], source["first_name"])
            self.assertEqual(row["surname"], source["surname"])

    def test_each_file_is_named_for_the_side_whose_records_are_in_it(self):
        self.assertTrue((self.out / "synb_missing_link.csv").exists())
        self.assertTrue((self.out / "syn_missing_link.csv").exists())

    # -- the name-discrepancy review table ----------------------------------

    def test_the_name_review_table_is_the_engineered_discrepancies(self):
        self.assertEqual(len(self.names), self.linking["n_name_discrepancies"])
        self.assertEqual({r["join_key"] for r in self.names},
                         set(self.linking["ids_name_discrepancy"]))

    def test_it_says_which_part_of_the_name_disagrees(self):
        counts = {}
        for row in self.names:
            counts[row["what_differs"]] = counts.get(row["what_differs"], 0) + 1
        self.assertEqual(counts, {"first name": 1, "surname": 2})
        self.assertEqual(sum(counts.values()),
                         sum(self.linking["n_name_discrepancies_by_field"].values()))

    def test_every_flagged_pair_really_disagrees(self):
        for row in self.names:
            sid = row["join_key"]
            differ = [f for f in ("first_name", "surname")
                      if self.child[sid][f] != self.parent[sid][f]]
            self.assertTrue(differ, f"{sid} is flagged but the two files agree")
            self.assertEqual(row["surname_synb"], self.child[sid]["surname"])
            self.assertEqual(row["surname_syn"], self.parent[sid]["surname"])

    def test_no_agreeing_pair_is_flagged(self):
        flagged = {r["join_key"] for r in self.names}
        for sid in set(self.child) & set(self.parent):
            agrees = all(self.child[sid][f] == self.parent[sid][f]
                         for f in ("first_name", "surname"))
            if agrees:
                self.assertNotIn(sid, flagged, f"{sid} agrees on both names")

    def test_the_review_table_is_worst_first(self):
        """Two unrelated names mean a wrong match; a near-miss is a spelling slip."""
        scores = [float(r["how_alike"]) for r in self.names]
        self.assertEqual(scores, sorted(scores), f"not worst-first: {scores}")
        self.assertLess(scores[0], 0.5, "a wholly different surname must sort to the top")
        self.assertGreater(scores[-1], 0.5, "a one-letter slip must sort to the bottom")

    # -- what it says out loud ----------------------------------------------

    def test_the_three_join_results_are_named_out_loud(self):
        """Plain left/inner/right, with no join vocabulary the user has to know."""
        out = self.proc.stdout
        self.assertRegex(out, r"matched\s+45\b")
        self.assertRegex(out, r"only in synb\s+15\b")
        self.assertRegex(out, r"only in syn\s+155\b")
        for word in ("inner join", "left join", "right join", "outer"):
            self.assertNotIn(word, out.lower(), f"{word!r} is vocabulary the user needn't learn")

    def test_it_hands_over_the_hard_link_with_the_instruction(self):
        out = self.proc.stdout
        self.assertIn("synb_hard_link.csv", out)
        self.assertIn("45 rows, two columns", out)
        self.assertIn("Data Import Tool", out)

    def test_the_name_discrepancies_are_named_out_loud(self):
        self.assertIn("3 of the 45 matched pairs disagree", self.proc.stdout)


class TestLinkStudiesRefusesRatherThanGuesses(unittest.TestCase):
    """Every refusal here is a wrong hard link that would have been uploaded to REDCap."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, header, rows):
        path = self.tmp / name
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        return path

    def test_a_repeated_join_value_stops_the_run(self):
        """A link has to point at ONE record per person — never pick one of two."""
        parent = self.write("parent.csv", ["record_id", "hosp"], [["1", "H1"], ["2", "H2"]])
        child = self.write("child.csv", ["child_id", "hosp"],
                           [["c1", "H1"], ["c2", "H1"], ["c3", "H2"]])
        proc = subprocess.run(
            [sys.executable, str(LINK_STUDIES), "--parent", str(parent), "--child", str(child),
             "--parent-name", "p", "--child-name", "c", "--key", "hosp",
             "--child-id", "child_id", "--link-field", "parent_no",
             "--out-dir", str(self.tmp / "out")],
            capture_output=True, text=True, timeout=300)
        self.assertNotEqual(proc.returncode, 0)
        out = proc.stdout + proc.stderr
        self.assertIn("more than one row", out)
        self.assertNotIn("Traceback", out)
        self.assertFalse((self.tmp / "out").exists(), "nothing may be written on a refusal")

    def test_nothing_matching_stops_the_run_and_points_back_at_the_survey(self):
        """An empty hard-link file is worse than none — it looks like a finished job."""
        parent = self.write("parent.csv", ["record_id"], [["1"], ["2"]])
        child = self.write("child.csv", ["child_id", "record_id"], [["c1", "77"], ["c2", "88"]])
        proc = subprocess.run(
            [sys.executable, str(LINK_STUDIES), "--parent", str(parent), "--child", str(child),
             "--parent-name", "p", "--child-name", "c", "--key", "record_id",
             "--child-id", "child_id", "--link-field", "parent_no",
             "--out-dir", str(self.tmp / "out")],
            capture_output=True, text=True, timeout=300)
        self.assertNotEqual(proc.returncode, 0)
        out = proc.stdout + proc.stderr
        self.assertIn("Nothing matched", out)
        self.assertIn("--suggest", out)
        self.assertNotIn("Traceback", out)

    def test_a_row_with_no_key_at_all_is_still_reported(self):
        """A record that vanishes from every report looks like one that was handled."""
        parent = self.write("parent.csv", ["record_id", "hosp", "first_name", "surname"],
                            [["1", "H1", "Ada", "Eze"], ["2", "H2", "Bode", "Kalu"]])
        child = self.write("child.csv", ["child_id", "hosp", "first_name", "surname"],
                           [["c1", "H1", "Ada", "Eze"], ["c2", "", "Chidi", "Nwosu"]])
        out = self.tmp / "out"
        proc = subprocess.run(
            [sys.executable, str(LINK_STUDIES), "--parent", str(parent), "--child", str(child),
             "--parent-name", "p", "--child-name", "c", "--key", "hosp",
             "--child-id", "child_id", "--link-field", "parent_no", "--out-dir", str(out)],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        hard = read_csv(out / "c_hard_link.csv")
        self.assertEqual([r["child_id"] for r in hard], ["c1"],
                         "a row with no key can never be hard-linked")
        missing = read_csv(out / "c_missing_link.csv")
        self.assertEqual({r["child_id"] for r in missing}, {"c2"})
        self.assertEqual(missing[0]["surname"], "Nwosu")
        self.assertIn("no hosp recorded at all", proc.stdout)

    def test_a_tab_separated_export_is_read_as_a_table_not_one_column(self):
        """cBioPortal ships TSV, and the skill advertises it — reading it as commas gives
        one column holding the whole header, which fails a long way from its cause."""
        parent = self.tmp / "parent.tsv"
        parent.write_text("record_id\thosp\n1\tH1\n2\tH2\n")
        child = self.write("child.csv", ["child_id", "hosp"], [["c1", "H1"]])
        proc = subprocess.run(
            [sys.executable, str(LINK_STUDIES), "--parent", str(parent), "--child", str(child),
             "--parent-name", "p", "--child-name", "c", "--key", "hosp",
             "--child-id", "child_id", "--link-field", "parent_no",
             "--out-dir", str(self.tmp / "out")],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, (proc.stdout + proc.stderr)[-800:])
        self.assertEqual(len(read_csv(self.tmp / "out" / "c_hard_link.csv")), 1)

    def test_a_key_that_is_not_a_column_names_the_columns_that_are(self):
        proc = run_link("--key", "not_a_column", "--out-dir", str(self.tmp / "out"),
                        parent_name="syn", child_name="synb")
        self.assertNotEqual(proc.returncode, 0)
        out = proc.stdout + proc.stderr
        self.assertIn("syn_id", out, "list the columns it did find")
        self.assertNotIn("Traceback", out)

    def test_it_refuses_a_hard_link_whose_two_columns_would_share_a_name(self):
        proc = run_link("--key", "syn_id", "--child-id", "syn_id",
                        "--out-dir", str(self.tmp / "out"),
                        parent_name="syn", child_name="synb")
        self.assertNotEqual(proc.returncode, 0)
        out = proc.stdout + proc.stderr
        # The refusal must name BOTH possible causes: a cut-down child export whose first
        # column is already the parent's number (→ ask for the full export), or a child that
        # genuinely stores the parent number under that name (→ point at --child-id).
        self.assertIn("full export", out)
        self.assertIn("--child-id", out)
        self.assertNotIn("Traceback", out)

    def test_it_asks_for_the_key_rather_than_guessing_one(self):
        proc = run_link("--out-dir", str(self.tmp / "out"),
                        parent_name="syn", child_name="synb")
        self.assertNotEqual(proc.returncode, 0)
        out = proc.stdout + proc.stderr
        self.assertIn("--suggest", out)
        self.assertNotIn("Traceback", out)


class TestOrphanVocabularyIsRetired(unittest.TestCase):
    """0.19 #49: "orphan" is jargon for "we found nobody to link this to".

    The word is gone from the skill and from everything the three tools print. It survives
    only inside argo_diff.py, the shared safety engine, where it is a constant in code and
    nobody reads it.
    """

    def test_the_skill_never_says_orphan(self):
        self.assertNotIn("orphan", (LINK / "SKILL.md").read_text().lower())

    def test_no_tool_prints_the_word(self):
        out = Path(tempfile.mkdtemp())
        try:
            runs = [
                run_link("--suggest", parent_name="syn", child_name="synb"),
                run_link("--key", "syn_id", "--out-dir", str(out),
                         parent_name="syn", child_name="synb"),
                subprocess.run(
                    [sys.executable, str(DIFF_PAYLOAD), "--for-analysis",
                     "--computed", str(STUDY_B / "records.csv"),
                     "--current", str(PRIMARY / "records.csv"),
                     "--id-field", "syn_id", "--fields", FIELDS,
                     "--out-dir", str(out), "--prefix", "v"],
                    capture_output=True, text=True, timeout=300),
                subprocess.run(
                    [sys.executable, str(MASTER),
                     "--left", str(PRIMARY / "records.csv"), "--left-name", "cohort",
                     "--right", str(STUDY_B / "records.csv"), "--right-name", "pathology",
                     "--diff-dir", str(out), "--diff-prefix", "v",
                     "--id-field", "syn_id", "--out", str(out / "master.csv")],
                    capture_output=True, text=True, timeout=300),
            ]
            for proc in runs:
                self.assertNotIn("orphan", (proc.stdout + proc.stderr).lower(),
                                 f"{proc.args[1]} still says orphan")
            self.assertFalse(any(p.name.startswith("v_orphans") for p in out.iterdir()))
            self.assertTrue((out / "v_no_record_to_fill.csv").exists())
        finally:
            shutil.rmtree(out, ignore_errors=True)


class TestLinkDataDocMatchesTheHelpers(unittest.TestCase):
    """The skill's promises, checked against the code that keeps them."""

    DOC = (LINK / "SKILL.md").read_text()

    def test_all_three_tools_are_documented_with_distinct_jobs(self):
        for tool in ("link_studies.py", "diff_payload.py", "build_master_linkage.py"):
            self.assertIn(tool, self.DOC, f"{tool} is undocumented")
        table = self.DOC.split("## The three tools", 1)[1].split("\n## ", 1)[0]
        for tool in ("link_studies.py", "diff_payload.py", "build_master_linkage.py"):
            self.assertIn(tool, table, f"{tool} is missing from the which-tool table")

    def test_the_hard_link_is_documented_as_the_deliverable(self):
        self.assertIn("_hard_link.csv", self.DOC)
        self.assertIn("two columns", self.DOC)
        self.assertIn("--suggest", self.DOC)

    def test_the_missing_link_naming_is_documented_per_side(self):
        self.assertIn("_missing_link.csv", self.DOC)
        self.assertIn("r01_missing_link.csv", self.DOC)
        self.assertIn("crc_missing_link.csv", self.DOC)

    def test_the_name_review_table_is_documented(self):
        self.assertIn("_name_review.csv", self.DOC)

    def test_the_master_table_helper_is_documented(self):
        self.assertIn("build_master_linkage.py", self.DOC,
                      "link-data promises master_linkage.csv — it must say what writes it")
        self.assertIn("--left-name", self.DOC)
        self.assertIn("--right-name", self.DOC)

    def test_the_analysis_framing_is_documented(self):
        self.assertIn("--for-analysis", self.DOC)
        self.assertIn("_fills.csv", self.DOC)
        self.assertIn("_disagreements.csv", self.DOC)

    def test_the_renamed_gap_report_is_documented(self):
        self.assertIn("_no_record_to_fill.csv", self.DOC)

    def test_every_flag_the_doc_shows_exists(self):
        for script, flags in ((MASTER, ["--left", "--right", "--left-name", "--right-name",
                                        "--diff-dir", "--diff-prefix", "--id-field", "--out"]),
                              (DIFF_PAYLOAD, ["--for-analysis", "--computed", "--current",
                                              "--prefix", "--out-dir"]),
                              (LINK_STUDIES, ["--suggest", "--parent", "--child",
                                              "--parent-name", "--child-name", "--key",
                                              "--parent-key", "--child-key", "--child-id",
                                              "--link-field", "--out-dir"])):
            text = script.read_text()
            for flag in flags:
                self.assertIn(f'"{flag}"', text, f"{script.name} has no {flag}")


class TestManifestIsSelfConsistent(unittest.TestCase):
    """Guard the fixture itself: the MANIFEST must describe the CSVs on disk."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((STUDY_B / "MANIFEST.json").read_text())
        cls.records = read_csv(STUDY_B / "records.csv")
        cls.dd = read_csv(STUDY_B / "datadictionary.csv")
        cls.primary = read_csv(PRIMARY / "records.csv")

    def test_record_and_field_counts(self):
        self.assertEqual(len(self.records), self.manifest["study"]["n_records"])
        self.assertEqual(len(self.dd), self.manifest["data_dictionary"]["n_fields"])
        self.assertEqual(self.manifest["study"]["record_id_field"], self.dd[0]["field_name"])

    def test_class_sizes_add_up_to_the_record_count(self):
        o = self.manifest["overlap"]
        classes = o["ids_by_class"]
        self.assertEqual(len(classes["agree"]), o["n_shared_agreeing"])
        self.assertEqual(len(classes["conflict"]), o["n_shared_conflicting"])
        self.assertEqual(len(classes["fill_grade"]), o["n_shared_fill_histology_grade"])
        self.assertEqual(len(classes["fill_margin"]), o["n_shared_fill_margin_status"])
        self.assertEqual(len(classes["b_only"]), o["n_only_in_study_b"])
        self.assertEqual(sum(len(v) for v in classes.values()), o["n_records_study_b"])
        self.assertEqual(o["n_shared_ids"] + o["n_only_in_study_b"],
                         o["n_records_study_b"])

    def test_classes_are_disjoint(self):
        classes = self.manifest["overlap"]["ids_by_class"]
        seen = set()
        for ids in classes.values():
            self.assertFalse(seen & set(ids), "engineered classes overlap")
            seen |= set(ids)

    def test_id_space_overlap_is_what_the_manifest_says(self):
        o = self.manifest["overlap"]
        pids = {r["syn_id"] for r in self.primary}
        bids = {r["syn_id"] for r in self.records}
        self.assertEqual(len(pids & bids), o["n_shared_ids"])
        self.assertEqual(len(bids - pids), o["n_only_in_study_b"])
        self.assertEqual(len(pids - bids), o["n_only_in_primary"])

    def test_the_parent_registry_describes_the_primary_study(self):
        """The parent side of the link: identity only, one row per SYN participant."""
        registry = read_csv(STUDY_B / "parent_registry.csv")
        linking = self.manifest["linking"]
        self.assertEqual(len(registry), linking["n_parent_records"])
        self.assertEqual(len(registry), len(self.primary))
        self.assertEqual({r["syn_id"] for r in registry},
                         {r["syn_id"] for r in self.primary},
                         "the registry must cover exactly the primary study's participants")
        for column in ("hospital_no", "first_name", "surname"):
            self.assertIn(column, registry[0], f"{column} is what the link is reasoned about")
        self.assertEqual(len({r["hospital_no"] for r in registry}), len(registry),
                         "a hospital number that repeats is not a candidate key")

    def test_the_linking_block_matches_the_two_csvs(self):
        linking = self.manifest["linking"]
        parent = {r["syn_id"] for r in read_csv(STUDY_B / "parent_registry.csv")}
        child = {r["syn_id"] for r in self.records}
        self.assertEqual(len(parent & child), linking["n_matched"])
        self.assertEqual(len(child - parent), linking["n_child_only"])
        self.assertEqual(len(parent - child), linking["n_parent_only"])
        self.assertEqual((linking["n_matched"], linking["n_child_only"],
                          linking["n_parent_only"]), (45, 15, 155),
                         "the engineered join results must not drift")

    def test_the_engineered_name_discrepancies_are_the_only_ones(self):
        linking = self.manifest["linking"]
        parent = {r["syn_id"]: r for r in read_csv(STUDY_B / "parent_registry.csv")}
        child = {r["syn_id"]: r for r in self.records}
        differ = {sid for sid in set(parent) & set(child)
                  if any(parent[sid][f] != child[sid][f] for f in ("first_name", "surname"))}
        self.assertEqual(differ, set(linking["ids_name_discrepancy"]))
        self.assertEqual(len(differ), linking["n_name_discrepancies"])

    def test_the_hospital_number_is_the_weaker_key_by_the_stated_margin(self):
        linking = self.manifest["linking"]
        parent = {r["syn_id"]: r for r in read_csv(STUDY_B / "parent_registry.csv")}
        child = {r["syn_id"]: r for r in self.records}
        agree = [sid for sid in set(parent) & set(child)
                 if child[sid]["hospital_no"]
                 and child[sid]["hospital_no"] == parent[sid]["hospital_no"]]
        self.assertEqual(len(agree), linking["n_hospital_no_matches"])
        self.assertLess(len(agree), linking["n_matched"],
                        "the fixture exists to show one candidate key beating another")

    def test_the_child_carries_its_own_id_and_the_parents(self):
        self.assertEqual(self.manifest["study"]["record_id_field"], "synb_id")
        self.assertEqual(self.manifest["study"]["parent_id_field"], "syn_id")
        self.assertEqual(len({r["synb_id"] for r in self.records}), len(self.records))

    def test_generator_is_byte_stable(self):
        """Regenerating into a scratch copy must reproduce the committed bytes."""
        tmp = Path(tempfile.mkdtemp())
        try:
            work = tmp / "synthetic-study-b"
            work.mkdir()
            shutil.copy(STUDY_B / "generate.py", work / "generate.py")
            # generate.py reads ../synthetic-study/records.csv
            shutil.copytree(PRIMARY, tmp / "synthetic-study")
            proc = subprocess.run([sys.executable, str(work / "generate.py")],
                                  capture_output=True, text=True, timeout=300)
            self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
            for name in ("records.csv", "datadictionary.csv", "parent_registry.csv",
                         "MANIFEST.json"):
                self.assertEqual((work / name).read_bytes(), (STUDY_B / name).read_bytes(),
                                 f"{name} is not byte-stable — regenerate and commit")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
