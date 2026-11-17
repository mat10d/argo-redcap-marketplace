"""Pathology builds: the PathPresenter standard in build-study (pathology.py, decided 2026-11-17).

Every request below is synthetic. They mirror the shapes the real PathPresenter Initiation
Request (PID 233) produces in a label export: a new database with its REDCap request in, one for
a study already built, one with no REDCap request, an analysis study on existing slides, and an
old request filed before the form asked for the request type or the instance.
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
BUILD_STUDY = REPO / "plugins/argo-database-manager/skills/build-study"
sys.path.insert(0, str(BUILD_STUDY))

import pathology as P  # noqa: E402
from dd_builder import DD  # noqa: E402
import validate_dd  # noqa: E402

TITLE = "Synthetic Tumour Infiltrating Lymphocytes in Testville Breast Cancer"
SIR_NEW = {"record_id": "901", "project_title": TITLE, "study_design": "Retrospective",
           "new_project_pid": "", "study_production": ""}
SIR_BUILT = {"record_id": "902", "project_title": "Synthetic Methylation Cohort",
             "new_project_pid": "9999", "study_production": "Yes"}


def pp(rid, **kw):
    rec = {"record_id": str(rid), "request_type___1": "", "request_type___2": "",
           "redcap_request_submitted": "", "pp_instance": "", "project_title": "",
           "linked_redcap_title": ""}
    rec.update(kw)
    return rec


NEW_DB = pp(1, request_type___1="A new PathPresenter database", redcap_request_submitted="Yes",
            project_title=TITLE, linked_redcap_title=TITLE,
            expected_deliverable="CD 8 lymphocyte count\nCD3 lymphocyte count",
            labeling_requirements="annotation, region scoring", contributor_1="Reader One")
OLD_FORM = pp(2, redcap_request_submitted="Yes", project_title=TITLE, linked_redcap_title=TITLE)
NO_REDCAP = pp(3, request_type___1="A new PathPresenter database", redcap_request_submitted="No")
FOR_BUILT = pp(4, request_type___1="A new PathPresenter database", redcap_request_submitted="Yes",
               pp_instance="MSKCC", project_title="Synthetic Methylation Cohort")
ANALYSIS = pp(6, request_type___2="An analysis study on slides already in PathPresenter",
              pp_instance="MSKCC", project_title="Synthetic Methylation Cohort",
              an_source_db="SYNTH", an_question="No labels; just checking malignancy")
BOTH = pp(7, request_type___1="A new PathPresenter database",
          request_type___2="An analysis study on slides already in PathPresenter",
          redcap_request_submitted="Yes", project_title=TITLE)


class ThePaths(unittest.TestCase):
    def test_a_new_database_with_its_redcap_request_is_path_a(self):
        self.assertEqual(P.classify(NEW_DB, SIR_NEW), "A")

    def test_a_request_from_before_the_type_question_is_a_new_database(self):
        self.assertEqual(P.classify(OLD_FORM, SIR_NEW), "A")

    def test_a_built_study_is_amended_not_rebuilt(self):
        self.assertEqual(P.classify(FOR_BUILT, SIR_BUILT), "B")

    def test_no_redcap_request_means_nothing_to_build(self):
        self.assertEqual(P.classify(NO_REDCAP, None), "C")
        self.assertEqual(P.classify(NO_REDCAP, SIR_NEW), "C")

    def test_an_analysis_study_has_no_redcap_build(self):
        self.assertEqual(P.classify(ANALYSIS, SIR_BUILT), "D")
        self.assertEqual(P.classify(ANALYSIS, None), "D")

    def test_both_boxes_is_path_e(self):
        self.assertEqual(P.classify(BOTH, SIR_NEW), "E")

    def test_the_request_links_to_its_tracker_record_by_title(self):
        self.assertIs(P.match_sir(NEW_DB, [SIR_BUILT, SIR_NEW]), SIR_NEW)
        self.assertIsNone(P.match_sir(NO_REDCAP, [SIR_BUILT, SIR_NEW]))

    def test_an_unstated_instance_is_oau_and_a_question(self):
        self.assertEqual(P.instance(NEW_DB), ("OAU (argo-ccr)", False))
        self.assertEqual(P.instance(FOR_BUILT), ("MSK (argo-research)", True))

    def test_stains_come_from_the_request_text(self):
        self.assertEqual(P.request_stains(NEW_DB), ["CD3", "CD8"])

    def test_the_plan_stops_without_a_request(self):
        plan = P.plan_for(SIR_NEW, [NO_REDCAP])
        self.assertIsNone(plan["path"])
        self.assertIn("doesn't start without one", plan["todo"][0])

    def test_the_plan_names_every_gap_instead_of_guessing(self):
        plan = P.plan_for(SIR_NEW, [NEW_DB])
        self.assertEqual(plan["path"], ["A"])
        text = " ".join(plan["todo"])
        self.assertIn("no instance chosen", text)
        self.assertIn("H&E", text)
        self.assertTrue(plan["retrospective"])


class TheRedcapSide(unittest.TestCase):
    def build(self, stains=("H&E", "CD3", "CD8")):
        dd = DD(form="case")
        dd.field("case_id", "text", "Case ID")
        dd.case_key()
        dd.slide_block(list(stains))
        return dd

    def write(self, dd):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        tmp.close()
        dd.write(tmp.name)
        return tmp.name

    def test_the_slide_block_has_the_pd1_fields_up_to_three_per_stain(self):
        names = [r[0] for r in self.build().rows]
        for f in P.REQUIRED_FIELDS:
            self.assertIn(f, names)
        for v in ("he", "cd3", "cd8"):
            for n in (1, 2, 3):
                self.assertIn(f"slide_name_{v}_{n}", names)
        self.assertNotIn("slide_name_cd8_4", names)

    def test_the_case_key_is_a_flagged_identifier(self):
        row = next(r for r in self.build().rows if r[0] == "histology_number")
        self.assertEqual(row[10], "y")

    def test_the_slide_tracker_carries_no_missing_data_codes(self):
        rows = {r[0]: r for r in self.build().rows}
        self.assertEqual(rows["slide_found"][5], "1, Yes | 0, No")
        self.assertNotIn("-666", rows["slide_name_he_1"][6])
        self.assertIn("-666", rows["slide_staining_site"][5], "the sites are ordinary fields")

    def test_extra_slides_of_a_stain_show_only_when_asked_for(self):
        rows = {r[0]: r for r in self.build().rows}
        self.assertEqual(rows["slide_name_cd3_1"][11], "[slide_type(2)]='1'")
        self.assertIn("[slide_rounds_imaged]='2'", rows["slide_name_cd3_2"][11])
        self.assertIn("[slide_rounds_imaged]='3'", rows["slide_name_cd3_3"][11])

    def test_a_built_pathology_dictionary_validates(self):
        errors, _ = validate_dd.validate(self.write(self.build()), pathology_study=True,
                                         stains=["H&E", "CD3", "CD8"])
        self.assertEqual(errors, [])

    def test_the_validator_refuses_a_stain_list_that_differs_from_the_request(self):
        errors, _ = validate_dd.validate(self.write(self.build()), pathology_study=True,
                                         stains=["H&E", "CD8"])
        self.assertTrue(any("slide_type lists" in e for e in errors))

    def test_the_validator_refuses_a_dictionary_without_the_slide_block(self):
        dd = DD(form="case")
        dd.field("case_id", "text", "Case ID")
        dd.field("histology_number", "text", "Histology number")
        errors, _ = validate_dd.validate(self.write(dd), pathology_study=True)
        self.assertTrue(any("must have Identifier? = y" in e for e in errors))
        self.assertTrue(any("'slide_found' is missing" in e for e in errors))

    def test_the_json_spec_takes_a_slide_block_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "f.json"
            spec.write_text(json.dumps([{"var": "case_id", "type": "text", "label": "Case ID"},
                                        {"slide_block": ["H&E"]}]))
            out = Path(tmp) / "dd.csv"
            proc = subprocess.run([sys.executable, str(BUILD_STUDY / "dd_builder.py"),
                                   str(spec), str(out)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, newline="") as f:
                names = [r[0] for r in csv.reader(f)][1:]
        self.assertIn("slide_name_he_3", names)

    def test_a_stain_name_becomes_a_field_name(self):
        self.assertEqual([P.stain_var(s) for s in ("H&E", "PD-L1", "Ki-67")],
                         ["he", "pdl1", "ki67"])
        with self.assertRaises(ValueError):
            P.slide_block(DD(), ["CD-8", "CD8"])


class ThePathPresenterSide(unittest.TestCase):
    def test_file_names_are_histology_number_then_stain(self):
        self.assertEqual(P.example_name("CD8", 1, "H661/26"), "H661-26-CD8.svs")
        self.assertEqual(P.example_name("CD8", 2, "H661/26"), "H661-26-CD8-2.svs")

    def test_setup_writes_the_checklist_the_spec_and_the_metadata_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = P.setup(NEW_DB, SIR_NEW, Path(tmp), None)
            names = sorted(f.name for f in files)
            self.assertIn("PATHPRESENTER_SETUP.md", names)
            self.assertIn("ECRF_SPEC.md", names)
            meta = next(f for f in files if f.name.endswith("_TEMPLATE.csv"))
            with open(meta, newline="") as f:
                rows = list(csv.reader(f))
            checklist = (Path(tmp) / "PATHPRESENTER_SETUP.md").read_text()
            ecrf = (Path(tmp) / "ECRF_SPEC.md").read_text()
        self.assertEqual(rows[0], P.METADATA_COLUMNS)
        self.assertEqual([r[5] for r in rows[1:]], ["H&E", "CD3", "CD8"], "H&E always added")
        self.assertIn("OAU (argo-ccr)", checklist)
        self.assertIn("proposed", checklist)
        self.assertIn("Reader One", ecrf)

    def test_an_analysis_setup_copies_slides_instead_of_scanning(self):
        with tempfile.TemporaryDirectory() as tmp:
            P.setup(ANALYSIS, None, Path(tmp), "SYN")
            checklist = (Path(tmp) / "PATHPRESENTER_SETUP.md").read_text()
        self.assertIn("Copy the listed slides from SYNTH", checklist)
        self.assertIn("check-slide-list", checklist)
        self.assertNotIn("ARGO_SCANS", checklist)
        self.assertIn("MSK (argo-research)", checklist)


class TheSlideListCheck(unittest.TestCase):
    def check(self, header, rows):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "list.csv"
            with open(path, "w", newline="") as f:
                csv.writer(f).writerows([header] + rows)
            return P.check_slide_list(path)

    def test_a_clean_list_passes(self):
        problems, _ = self.check(["Pathology REDCap ID", "Slide name"], [["7", "H661-26-HE.svs"]])
        self.assertEqual(problems, [])

    def test_identifier_columns_are_named_never_their_values(self):
        problems, flagged = self.check(["Slide name", "Patient name", "Hospital number"],
                                       [["H661-26-HE.svs", "Ada Testwell", "123456"]])
        self.assertEqual(flagged, ["Patient name", "Hospital number"])
        self.assertNotIn("Ada", " ".join(problems))
        self.assertNotIn("123456", " ".join(problems))

    def test_a_list_that_names_no_slide_is_refused(self):
        problems, _ = self.check(["foo"], [["bar"]])
        self.assertTrue(any("no column names a slide" in p for p in problems))


class TheAudit(unittest.TestCase):
    def meta(self, names, identifier=""):
        return [{"field_name": n, "identifier": identifier if n == "histology_number" else "",
                 "select_choices_or_calculations": ""} for n in names]

    def test_numbered_slots_are_reported_and_left_alone(self):
        out = P.audit(self.meta(["record_id", "slide_found", "slide_name_1", "slide_name_2"]))
        self.assertTrue(any("numbered slots" in o and "leave as built" in o for o in out))

    def test_a_study_built_to_the_standard_matches(self):
        dd = DD(form="case")
        dd.field("case_id", "text", "Case ID")
        dd.case_key()
        dd.slide_block(["H&E"])
        rows = [{"field_name": r[0], "identifier": r[10], "select_choices_or_calculations": r[5]}
                for r in dd.rows]
        self.assertEqual(P.audit(rows), ["Matches the standard."])


class TheSkillDocumentsIt(unittest.TestCase):
    def test_the_skill_names_every_path_and_the_gate(self):
        text = (BUILD_STUDY / "SKILL.md").read_text()
        self.assertIn("No request, no pathology build", text)
        for path in P.PATHS:
            self.assertIn(f"| **{path}** |", text)
        for cmd in ("pathology.py plan", "pathology.py setup", "check-slide-list",
                    "pathology.py audit", "validate_dd.py --pathology"):
            self.assertIn(cmd, text)


if __name__ == "__main__":
    unittest.main()
