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
