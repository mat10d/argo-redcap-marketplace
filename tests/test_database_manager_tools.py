#!/usr/bin/env python3
"""Known-input / known-output tests for the database-manager fixes of 2026-10-09.

Each class is one defect or one decision from real sessions:

- sir_update.py: `--reopen` and `--set f=` wrote blanks that REDCap ignores under
  overwriteBehavior=normal; dd_uploaded could not be re-opened after a DD revision ("the tracker
  says done and the project isn't"); the build_tracking form stayed Incomplete after the 7th
  step; contains_phi was re-asked four times; "close out the build" needed seven questions.
- setup_brief.py: outstanding build items were unclear — now ONE table keyed to the 7 tracker
  steps plus the user's open requests; the build's hard-stop documents are one list.
- diff_payload.py: a repeated id let the last row win; `007` was written back as `7`.
- portfolio.py: an all-failed run became next week's baseline.
- close_request.py: closes a request without guessing `assigned_to`.
- dd_builder.py / validate_dd.py: self-completed surveys carry no MDC.
- make_roles_csv.py: Study Builder and PM export with identifier fields removed.

No network, no keys: everything runs on synthetic records.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "plugins/argo-database-manager/skills"
BUILD = SKILLS / "build-study"


def load(path: Path, name: str):
    sys.path.insert(0, str(path.parent / "scripts"))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SIR = load(BUILD / "sir_update.py", "sir_update_t")
STEPS = list(SIR.BUILD_STEPS)


def args(**kw):
    base = dict(rid="17", irb_number=None, irb_expires=None, close=False, close_out=False,
                mark_built=False, reopen=False, pid=None, status=None, mark_step=[],
                unmark_step=[], set_pairs=[], dd=None)
    base.update(kw)
    return argparse.Namespace(**base)


class TestSirUpdateWrites(unittest.TestCase):

    def test_a_blank_value_is_written_in_overwrite_mode(self):
        self.assertEqual(SIR.overwrite_mode([{"record_id": "1", "study_production": ""}]),
                         "overwrite")
        self.assertEqual(SIR.overwrite_mode([{"record_id": "1", "dd_uploaded": "1"}]), "normal")

    def test_reopen_blanks_study_production(self):
        payload, _diff, _ = SIR.plan({"study_production": "1", "study_status": "2"},
                                     args(reopen=True))
        self.assertEqual(payload["study_production"], "")
        self.assertEqual(SIR.overwrite_mode([payload]), "overwrite")

    def test_unmark_resets_dd_uploaded_to_zero(self):
        payload, diff, _ = SIR.plan({"dd_uploaded": "1"}, args(unmark_step=["dd_uploaded"]))
        self.assertEqual(payload, {"record_id": "17", "dd_uploaded": "0"})
        self.assertTrue(any("dd_uploaded" in d for d in diff), "the reset is shown in the diff")

    def test_unmark_of_a_step_not_done_writes_nothing(self):
        payload, _d, notes = SIR.plan({"dd_uploaded": ""}, args(unmark_step=["dd_uploaded"]))
        self.assertEqual(payload, {"record_id": "17"})
        self.assertTrue(any("already not done" in n for n in notes))

    def test_unmark_is_limited_to_the_build_steps(self):
        proc = subprocess.run([sys.executable, str(BUILD / "sir_update.py"), "17",
                               "--unmark-step", "contains_phi"],
                              capture_output=True, text=True, timeout=60)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("invalid choice", proc.stderr)

    def test_the_seventh_step_completes_the_form(self):
        rec = {s: "1" for s in STEPS[:-1]}
        payload, _d, _n = SIR.plan(rec, args(mark_step=["study_production"]))
        self.assertEqual(payload["study_production"], "1")
        self.assertEqual(payload["build_tracking_complete"], "2")

    def test_an_earlier_step_does_not_complete_the_form(self):
        payload, _d, _n = SIR.plan({}, args(mark_step=["dd_uploaded"]))
        self.assertNotIn("build_tracking_complete", payload)

    def test_close_out_ticks_every_remaining_step_in_one_push(self):
        rec = {"project_created": "1", "dd_uploaded": "1", "data_imported": "2"}
        payload, diff, _n = SIR.plan(rec, args(close_out=True))
        for step in ("user_rights_complete", "review_internal", "review_pi", "study_production"):
            self.assertEqual(payload[step], "1", step)
        self.assertNotIn("data_imported", payload, "a settled 'prospective' answer is kept")
        self.assertNotIn("project_created", payload)
        self.assertEqual(payload["build_tracking_complete"], "2")
        self.assertEqual(len(diff), 5, "one diff carrying every change")

    def test_a_dd_with_an_identifier_sets_contains_phi(self):
        with tempfile.TemporaryDirectory() as tmp:
            dd = Path(tmp) / "dd.csv"
            with open(dd, "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["Variable / Field Name", "Form Name", "Identifier?"])
                w.writerow(["record_id", "baseline", ""])
                w.writerow(["email", "baseline", "y"])
            ids = SIR.dd_identifier_fields(str(dd))
        self.assertEqual(ids, ["email"])
        payload, _d, _n = SIR.plan({"contains_phi": "0"}, args(mark_step=["dd_uploaded"]), ids)
        self.assertEqual(payload["contains_phi"], "1")
        payload, _d, _n = SIR.plan({}, args(mark_step=["dd_uploaded"]), [])
        self.assertNotIn("contains_phi", payload, "no identifiers says nothing — never sets 0")

    def test_production_with_blank_irb_fields_warns_and_proceeds(self):
        rec = {s: "1" for s in STEPS[:-1]}
        payload, _d, notes = SIR.plan(rec, args(mark_step=["study_production"]))
        self.assertEqual(payload["study_production"], "1", "a warning, not a stop")
        joined = " ".join(notes)
        self.assertIn("irb_number", joined)
        self.assertIn("irb_approval_expires", joined)
        self.assertIn("PM", joined, "the warning says who updates the field")
        _p, _d, notes = SIR.plan({**rec, "irb_number": "X/1", "irb_approval_expires": "2030-01-01"},
                                 args(mark_step=["study_production"]))
        self.assertFalse([n for n in notes if "blank" in n])


BRIEF = BUILD / "setup_brief.py"
REC = {"record_id": "17", "project_title": "Synthetic study", "pi_surname": "Testwell",
       "quest_univ_file": "q.docx", "irb_file_1": "irb.pdf", "data_collection": "2",
       "irb_number": "IRB/1", "irb_approval_expires": "2099-01-01",
       "project_created": "1", "dd_uploaded": "0", "data_imported": "2",
       "inst_name_1": "Korle Bu Teaching Hospital"}


def run_brief(rec, requests=None):
    tmp = Path(tempfile.mkdtemp())
    (tmp / "rec.json").write_text(json.dumps(rec))
    out = tmp / "study"
    out.mkdir()
    if requests:
        (out / "outstanding_requests.csv").write_text(requests)
    proc = subprocess.run([sys.executable, str(BRIEF), "17", "--from-json", str(tmp / "rec.json"),
                           "--out", str(out), "--moniker", "SYN"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return (out / "MANUAL_SETUP_BRIEF.md").read_text()


class TestSetupBriefOutstandingList(unittest.TestCase):

    def table(self, brief):
        section = brief.split("## Outstanding", 1)[1].split("\n## ", 1)[0]
        return [ln for ln in section.splitlines() if ln.startswith("| ") and "---" not in ln][1:]

    def test_one_row_per_tracker_step_in_tracker_order_with_who_and_status(self):
        rows = self.table(run_brief(REC))
        self.assertEqual(len(rows), 7)
        for row, step in zip(rows, STEPS):
            self.assertIn(f"`{step}`", row)
            cells = [c.strip() for c in row.strip("|").split("|")]
            self.assertEqual(len(cells), 4, row)
            self.assertIn(cells[3], ("Done", "Not done"))
            self.assertTrue(cells[1], "every item names who does it")
        status = {s: r.rstrip(" |").split("|")[-1].strip() for s, r in zip(STEPS, rows)}
        self.assertEqual(status["project_created"], "Done")
        self.assertEqual(status["dd_uploaded"], "Not done", "'0' is not done")
        self.assertEqual(status["data_imported"], "Done", "2 = prospective, settled")
        self.assertIn("2/7", run_brief(REC))

    def test_open_requests_join_the_same_list_and_closed_ones_leave_it(self):
        brief = run_brief(REC, "item,who,waiting_on,status\n"
                               "Mark identifiers so exports drop them,Database manager,,open\n"
                               "Rename the DAG,Database manager,,done\n")
        rows = self.table(brief)
        self.assertEqual(len(rows), 8)
        self.assertIn("Mark identifiers so exports drop them", rows[-1])
        self.assertNotIn("Rename the DAG", brief.split("## Details")[0].split("1 closed")[0])
        self.assertIn("1 open request", brief)

    def test_missing_hard_stop_documents_stop_the_build(self):
        rec = {k: v for k, v in REC.items() if k not in ("quest_univ_file", "irb_file_1")}
        brief = run_brief(rec)
        self.assertIn("The build can't start", brief)
        self.assertIn("questionnaire", brief.split("## Outstanding")[0])
        self.assertIn("ethics approval letter", brief.split("## Outstanding")[0])

    def test_complete_documents_do_not_raise_the_stop(self):
        self.assertNotIn("can't start", run_brief(REC))

    def test_blank_irb_fields_are_named_with_who_updates_them(self):
        rec = {**REC, "irb_number": "", "irb_approval_expires": ""}
        head = run_brief(rec).split("## Outstanding")[0]
        self.assertIn("`irb_number`", head)
        self.assertIn("`irb_approval_expires`", head)
        self.assertIn("PM / requester", head)


class TestHardStopIsOneList(unittest.TestCase):
    """Matteo, 2026-10-09: questionnaire, protocol, ethics approval letter. One list, guarded."""

    DOC = (BUILD / "SKILL.md").read_text()

    def test_the_skill_names_exactly_the_scripts_list(self):
        mod = load(BRIEF, "setup_brief_t")
        names = [n for n, _ in mod.HARD_STOP_DOCUMENTS]
        self.assertEqual(names, ["questionnaire", "protocol", "ethics approval letter"])
        stop = self.DOC.split("### Hard stop", 1)[1].split("\n## ", 1)[0]
        for name in names:
            self.assertIn(f"**the {name}**", stop)

    def test_the_stop_sits_before_any_dd_work(self):
        self.assertLess(self.DOC.index("### Hard stop"), self.DOC.index("## Step 2 —"))
        self.assertLess(self.DOC.index("### Hard stop"), self.DOC.index("## Step 3 —"))

    def test_the_stop_forbids_partial_builds_and_the_build_ahead_offer(self):
        stop = " ".join(self.DOC.split("### Hard stop", 1)[1].split("\n## ", 1)[0].split())
        self.assertRegex(stop, r"(?i)don't build the parts you can")
        self.assertRegex(stop, r"(?i)don't proceed on assumptions")
        self.assertRegex(stop, r"(?i)don't offer \"build ahead")
        self.assertRegex(stop, r"(?i)one or two plain sentences")
        self.assertRegex(stop, r"(?i)application.{0,60}is not an approval")

    def test_headway_is_scoped_to_ambiguity_inside_complete_documents(self):
        block = self.DOC.split("### The build always makes headway", 1)[1].split("\n> ### ", 1)[0]
        flat = " ".join(re.sub(r"^>\s?", "", block, flags=re.M).split())
        self.assertRegex(flat, r"(?i)never a way around the hard stop")

    def test_nothing_else_invites_building_on_missing_documents(self):
        flat = " ".join(self.DOC.split()).lower()
        for phrase in ("build around it", "proceed with assumptions", "todo the gaps"):
            self.assertNotIn(phrase, flat)


class TestDiffPayloadIds(unittest.TestCase):
    TOOL = SKILLS / "link-data/diff_payload.py"

    def run_tool(self, computed, current):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "comp.csv").write_text(computed)
        (tmp / "curr.csv").write_text(current)
        proc = subprocess.run([sys.executable, str(self.TOOL), "--computed", str(tmp / "comp.csv"),
                               "--current", str(tmp / "curr.csv"), "--id-field", "rid",
                               "--out-dir", str(tmp / "out"), "--prefix", "t"],
                              capture_output=True, text=True, timeout=60)
        return proc, tmp / "out"

    def test_a_repeated_id_stops_the_run(self):
        proc, _ = self.run_tool("rid,grade\n1,2\n", "rid,grade\n1,3\n1,\n")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("more than one row", proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_ids_are_written_back_as_the_current_file_spells_them(self):
        proc, out = self.run_tool("rid,grade\n7,2\n", "rid,grade\n007,\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = list(csv.DictReader((out / "t_update.csv").read_text().splitlines()))
        self.assertEqual(rows, [{"rid": "007", "grade": "2"}])


class TestPortfolioBaseline(unittest.TestCase):

    def test_an_all_failed_snapshot_is_skipped(self):
        import os
        os.environ.setdefault("ARGO_PM_ROOT", tempfile.mkdtemp())
        mod = load(SKILLS / "weekly-check/portfolio.py", "portfolio_t")
        state = Path(tempfile.mkdtemp())
        good = {"projects": {"A": {"open": [], "done": []}}}
        bad = {"projects": {"A": {"error": "x"}}}
        for stamp, snap in (("2026-01-01", good), ("2026-01-08", bad)):
            (state / f"snapshot-{stamp}").mkdir()
            (state / f"snapshot-{stamp}" / "summary.json").write_text(json.dumps(snap))
        self.assertEqual(mod.load_previous(state), good)


class TestCloseRequest(unittest.TestCase):
    mod = load(SKILLS / "weekly-check/close_request.py", "close_request_t")

    def test_it_ticks_completed_and_nothing_else(self):
        payload, diff = self.mod.plan_close({"completed": "0", "assigned_to": ""}, "record_id", "7")
        self.assertEqual(payload, {"record_id": "7", "completed": "1"})
        self.assertEqual(len(diff), 1)

    def test_assigned_to_only_when_a_username_is_named(self):
        payload, _ = self.mod.plan_close({"completed": ""}, "record_id", "7", "jdoe")
        self.assertEqual(payload["assigned_to"], "jdoe")

    def test_an_already_closed_request_writes_nothing(self):
        self.assertEqual(self.mod.plan_close({"completed": "1"}, "record_id", "7")[0], {})


class TestSurveysCarryNoMdc(unittest.TestCase):

    def test_builder_and_validator_agree(self):
        dd_mod = load(BUILD / "dd_builder.py", "dd_builder_t")
        val = load(BUILD / "validate_dd.py", "validate_dd_t")
        dd = dd_mod.DD(form="baseline", survey=True)
        dd.field("respondent_id", "text", "Record ID")
        dd.field("age", "text", "Age", valid="integer")
        dd.field("sex", "radio", "Sex", "1, Male | 2, Female")
        with tempfile.TemporaryDirectory() as tmp:
            path = dd.write(str(Path(tmp) / "dd.csv"))
            rows = list(csv.reader(Path(path).read_text().splitlines()))[1:]
            for row in rows:
                self.assertNotIn("-666", row[5] + row[6], "no MDC in a survey")
                self.assertNotIn("@MDC-EXEMPT", row[17], "nothing is being waived")
            errors, _ = val.validate(path, survey=True)
            self.assertEqual(errors, [])
            errors, _ = val.validate(path)
            self.assertTrue(errors, "without --survey the same DD fails MDC")


class TestRolesExportDefaults(unittest.TestCase):

    def test_builder_and_pm_export_without_identifier_fields(self):
        mod = load(BUILD / "make_roles_csv.py", "roles_t")
        with tempfile.TemporaryDirectory() as tmp:
            dd = Path(tmp) / "S_DataDictionary.csv"
            dd.write_text("Variable / Field Name,Form Name\nrid,baseline\nage,followup\n")
            text = mod.build_csv(dd)[0]
        rows = {r["role_label"]: r for r in csv.DictReader(text.splitlines())}
        self.assertEqual(rows["Study Builder"]["forms_export"], "baseline:3,followup:3")
        self.assertEqual(rows["Project Manager"]["forms_export"], "baseline:3,followup:3")
        self.assertEqual(rows["Principal Investigator"]["forms_export"], "baseline:2,followup:2")
        self.assertEqual(rows["Data Entry"]["forms_export"], "baseline:0,followup:0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
