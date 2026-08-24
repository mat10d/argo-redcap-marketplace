#!/usr/bin/env python3
"""End-to-end test of the link-data READ SIDE across two synthetic studies.

The analyst task "merge more than one database for analysis" (PLAN.md Phase 1.5)
had no automated coverage: every linkage test to date compared one study against
a flat pathology sheet. This drives the real entry point —
`link-data/diff_payload.py`, which wraps `argo_diff.diff_records()` — over two
whole synthetic studies that share the `syn_id` space:

    testing/fixtures/synthetic-study/     200 records (the primary)
    testing/fixtures/synthetic-study-b/    60 records (the sub-study)

and asserts fills / conflicts / no-ops / orphans against
synthetic-study-b/MANIFEST.json's engineered counts — numbers, not vibes.

Stdlib only: no pandas, no network, no keys. Nothing to skip on.
"""
from __future__ import annotations

import csv
import json
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

FIELDS = "histology_grade,margin_status"


def read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


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
            cls.orphans = read_csv(cls.out / "merge_orphans.csv")
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
                     "merge_orphans.csv", "merge_missing_link.csv"):
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
        self.assertIn(f"orphans    : {self.overlap['n_only_in_study_b']} records", out)
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
                                      f"an orphan must never reach the update payload")
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

    def test_study_b_only_ids_are_orphans_never_fills(self):
        """The fix for NITS #2.

        diff_records() used to iterate the computed side and read an id missing
        from the current side as an all-blank record, so all 15 study-B-only ids
        became safe-fill rows: importing merge_update.csv would have CREATED
        those records in REDCap. They are now ORPHANS — reported, never payload.
        """
        b_only = set(self.overlap["ids_by_class"]["b_only"])
        self.assertEqual(len(b_only), 15)

        self.assertEqual({r["syn_id"] for r in self.orphans}, b_only,
                         "the orphan report must be exactly the study-B-only ids")
        self.assertEqual(self.expected["orphan_cells_classified_fill"],
                         len(b_only) * len(FIELDS.split(",")))

        for name, rows in (("update", self.updates), ("conflicts", self.conflicts),
                           ("overwrite", self.overwrites)):
            self.assertFalse(b_only & {r["syn_id"] for r in rows},
                             f"an orphan reached {name}.csv — importing it would create records")

    def test_no_fill_cell_anywhere_comes_from_an_orphan(self):
        """Zero cells, not just zero rows: nothing of an orphan's data is pushable."""
        b_only = set(self.overlap["ids_by_class"]["b_only"])
        cells = sum(1 for row in self.updates if row["syn_id"] in b_only
                    for f in FIELDS.split(",") if row.get(f, ""))
        self.assertEqual(cells, 0)

    def test_orphan_rows_carry_the_study_b_values(self):
        """A gap report nobody can act on is not a report — the values come with it."""
        study_b = {r["syn_id"]: r for r in read_csv(STUDY_B / "records.csv")}
        for row in self.orphans:
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
        for name in ("merge_conflicts.csv", "merge_orphans.csv", "merge_missing_link.csv"):
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
        self.assertIn("orphans    :", self.proc.stdout)
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

    def test_the_worst_issue_is_the_orphans(self):
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


class TestLinkDataDocMatchesTheHelpers(unittest.TestCase):
    """The skill's promises, checked against the code that keeps them."""

    DOC = (LINK / "SKILL.md").read_text()

    def test_the_master_table_helper_is_documented(self):
        self.assertIn("build_master_linkage.py", self.DOC,
                      "link-data promises master_linkage.csv — it must say what writes it")
        self.assertIn("--left-name", self.DOC)
        self.assertIn("--right-name", self.DOC)

    def test_the_analysis_framing_is_documented(self):
        self.assertIn("--for-analysis", self.DOC)
        self.assertIn("_fills.csv", self.DOC)
        self.assertIn("_disagreements.csv", self.DOC)

    def test_every_flag_the_doc_shows_exists(self):
        for script, flags in ((MASTER, ["--left", "--right", "--left-name", "--right-name",
                                        "--diff-dir", "--diff-prefix", "--id-field", "--out"]),
                              (DIFF_PAYLOAD, ["--for-analysis", "--computed", "--current",
                                              "--prefix", "--out-dir"])):
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
            for name in ("records.csv", "datadictionary.csv", "MANIFEST.json"):
                self.assertEqual((work / name).read_bytes(), (STUDY_B / name).read_bytes(),
                                 f"{name} is not byte-stable — regenerate and commit")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
