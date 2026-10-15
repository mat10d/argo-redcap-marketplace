"""link_patients.py against the synthetic-linkage fixture (target 1 of the linkage plan).

The fixture plants every case the engine must handle and records the answer: MANIFEST.json holds
the counts, truth.csv says which made-up person each record is. Two kinds of check:
  - the counts match the planted cases exactly;
  - against the truth, no accepted link ever joins two different people, no planted typo is
    missed, and every conflict really is two different people.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "plugins/argo-database-manager/skills/link-patients"
FIXTURE = REPO / "testing/fixtures/synthetic-linkage"
sys.path.insert(0, str(SKILL))

import link_patients as lp  # noqa: E402


class LinkPatientsOnTheFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((FIXTURE / "MANIFEST.json").read_text())
        studies = lp.read_studies(FIXTURE / "studies.csv")
        cls.records = [r for s in studies for r in lp.read_records(s, FIXTURE)]
        cls.out = lp.link(studies, cls.records)
        with open(FIXTURE / "truth.csv", newline="") as f:
            cls.truth = {(r["study"], r["record_id"]): r["person"] for r in csv.DictReader(f)}

    def same_person(self, row):
        return self.truth[(row["study_a"], row["record_a"])] == \
            self.truth[(row["study_b"], row["record_b"])]

    def test_counts_match_the_planted_cases(self):
        s, want = self.out["summary"], self.manifest["expect"]
        for k in ("hard_links", "hard_confirmed", "hard_with_typo", "hard_disagrees", "strong",
                  "probable", "near_miss", "conflict", "duplicate", "names_to_judge"):
            self.assertEqual(s[k], want[k], k)
        for study, n in want["blank_key"].items():
            self.assertEqual(s["per_study"][study].get("blank_key", 0), n, study)
        for study, n in want["unlinked"].items():
            self.assertEqual(s["per_study"][study].get("unlinked", 0), n, study)
        for study, n in want["expected_but_not_linked"].items():
            self.assertEqual(s["per_study"][study].get("expected_but_not_linked", 0), n, study)

    def test_a_condition_decides_which_records_should_have_a_parent(self):
        r01 = [r for r in self.records if r.study == "r01"]
        self.assertEqual(sum(1 for r in r01 if not r.expects), 2, "cohort 2 expects no CRC parent")
        fin = {r.rid: r for r in self.records if r.study == "fintox"}
        self.assertEqual(sorted({tuple(r.expects) for r in fin.values()}), [("breast",), ("crc",)])

    def test_a_coded_site_is_decoded(self):
        sites = {r.site for r in self.records if r.study == "crc"}
        self.assertEqual(sites, {"OAUTHC", "LUTH"})

    def test_no_accepted_link_joins_two_different_people(self):
        wrong = [l for l in self.out["links"] if not self.same_person(l)]
        self.assertEqual(wrong, [])

    def test_a_person_id_never_spans_two_real_people(self):
        by_id = {}
        for p in self.out["persons"]:
            by_id.setdefault(p["argo_person_id"], set()).add(
                self.truth[(p["study"], p["record_id"])])
        self.assertEqual([k for k, v in by_id.items() if len(v) > 1], [])

    def test_every_near_miss_is_the_same_person_with_a_typo(self):
        self.assertTrue(all(self.same_person(n) for n in self.out["near_misses"]))

    def test_every_conflict_is_two_different_people(self):
        conflicts = [r for r in self.out["review"] if r["kind"] == "conflict"]
        self.assertTrue(conflicts)
        self.assertFalse(any(self.same_person(r) for r in conflicts))

    def test_a_wrong_stored_parent_id_is_held_not_linked(self):
        held = [r for r in self.out["review"] if r["kind"] == "hard_link_disagrees"]
        self.assertEqual(len(held), 1)
        self.assertIn("instead", held[0]["explain"], "the review names where the numbers point")
        ref = (held[0]["study_a"], held[0]["record_a"])
        linked = {(l["study_a"], l["record_a"]) for l in self.out["links"]} | \
                 {(l["study_b"], l["record_b"]) for l in self.out["links"]}
        self.assertNotIn(ref, linked)

    def test_names_to_judge_carry_names_only(self):
        for row in self.out["names_to_judge"]:
            self.assertEqual(set(row), {"pair", "name_a", "name_b"})
            self.assertFalse(any(ch.isdigit() for ch in row["name_a"] + row["name_b"]))


class RealExportShapes(unittest.TestCase):
    def write(self, tmp, header, rows):
        path = Path(tmp) / "x.csv"
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        return {"study": "x", "name": "X", "file": "x.csv", "record_id_field": "record_id",
                "site_field": "", "single_site": "OAUTHC", "hosp_field": "hospital_number",
                "histology_fields": "histology_number", "first_name_field": "",
                "last_name_field": "", "parent_links": "", "site_choices": ""}

    def test_repeating_rows_become_one_record_with_every_histology_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = self.write(tmp, ["record_id", "redcap_repeat_instrument", "hospital_number",
                                    "histology_number"],
                              [["1", "", "123456", ""], ["1", "pathology", "", "H100/21"],
                               ["1", "pathology", "", "H200/22"]])
            recs = lp.read_records(spec, tmp)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].raw["hospital_number"], "123456")
        self.assertEqual(recs[0].raw["histology"], ["H100/21", "H200/22"])

    def test_a_label_export_is_refused_in_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = self.write(tmp, ["Record ID", "Hospital number"], [["1", "123456"]])
            with self.assertRaises(SystemExit) as e:
                lp.read_records(spec, tmp)
        self.assertIn("raw data", str(e.exception))

    def test_a_malformed_parent_link_is_refused_in_words(self):
        with self.assertRaises(SystemExit):
            lp.parse_parent_links("colorectal_record_id")
        self.assertEqual(lp.parse_parent_links("a_record_id=crc[cohort=1|2]"),
                         [("a_record_id", "crc", "cohort", {"1", "2"})])


class TheCommandLine(unittest.TestCase):
    def test_it_writes_every_output_and_per_site_worklists(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run([sys.executable, str(SKILL / "link_patients.py"),
                                   "--studies", str(FIXTURE / "studies.csv"),
                                   "--exports", str(FIXTURE), "--out", tmp],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for name in ("links.csv", "persons.csv", "hard_link_check.csv", "review.csv",
                         "near_misses.csv", "names_to_judge.csv", "summary.json"):
                self.assertTrue((Path(tmp) / name).exists(), name)
            sheets = list((Path(tmp) / "worklists").glob("near_misses_*.csv"))
            self.assertTrue(sheets)
            with open(sheets[0], newline="") as f:
                self.assertIn("RESPONSE", next(csv.reader(f)))

    def test_no_arguments_explains_instead_of_crashing(self):
        proc = subprocess.run([sys.executable, str(SKILL / "link_patients.py")],
                              capture_output=True, text=True)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("Nothing is written to REDCap", proc.stdout)


if __name__ == "__main__":
    unittest.main()
