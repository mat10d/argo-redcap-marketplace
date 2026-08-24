#!/usr/bin/env python3
"""Unit tests for the parts of the ARGO suite that need no REDCap connection.

Run them all:
    python3 -m pytest tests/ -q          (or, with no pytest installed)
    python3 tests/test_pure_logic.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGINS = REPO / "plugins"
os.environ.setdefault("ARGO_SETUP_NO_OPEN", "1")  # suites must not pop text editors


def load(path: Path, name: str, env: dict | None = None):
    """Import a script by file path, with any env vars it reads at import time set."""
    saved = {k: os.environ.get(k) for k in (env or {})}
    os.environ.update(env or {})
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


CLIENT = load(PLUGINS / "argo-core/skills/redcap-api/scripts/argo_redcap_client.py", "argo_redcap_client")
TRACKERS = load(PLUGINS / "argo-core/skills/redcap-api/scripts/argo_trackers.py",
                "argo_trackers_pure")
PORTFOLIO = load(
    PLUGINS / "argo-database-manager/skills/weekly-check/portfolio.py",
    "portfolio",
    {"ARGO_PM_ROOT": str(Path(os.environ.get("TMPDIR", "/tmp")) / "argo-test-pm")},
)
EXPORT = load(PLUGINS / "argo-database-manager/skills/export-data/export.py", "argo_export")


class TestUrlValidation(unittest.TestCase):
    def test_accepts_a_real_url(self):
        self.assertEqual(
            CLIENT.check_url("https://redcap.example.org/api/"),
            "https://redcap.example.org/api/",
        )

    def test_rejects_missing_url(self):
        with self.assertRaises(CLIENT.RedcapError):
            CLIENT.check_url(None)
        with self.assertRaises(CLIENT.RedcapError):
            CLIENT.check_url("")

    def test_rejects_url_without_a_scheme(self):
        # The exact case finding #7 called out: opaque urllib errors instead of a clear message.
        with self.assertRaises(CLIENT.RedcapError):
            CLIENT.check_url("redcap.example.org/api/")

    def test_rejects_nonsense(self):
        for bad in ("ftp://x/y", "just some words", "https://"):
            with self.assertRaises(CLIENT.RedcapError, msg=bad):
                CLIENT.check_url(bad)

    def test_message_is_actionable_not_jargon(self):
        try:
            CLIENT.check_url(None)
        except CLIENT.RedcapError as e:
            text = str(e)
        # Must point at the settings file in words a non-technical user can act on —
        # never at ~/.argo/.env, which doesn't exist in Cowork.
        self.assertIn("settings file", text)
        self.assertIn("Add keys here", text)
        self.assertIn("REDCAP_URL=", text)
        self.assertNotIn("~/.argo/.env", text)


class TestTokenMasking(unittest.TestCase):
    def test_shows_only_last_four(self):
        self.assertEqual(CLIENT.mask("ABCDEF0123456789"), "…6789")

    def test_never_leaks_the_whole_token(self):
        token = "S3CR3TT0K3NV4LU3"
        self.assertNotIn(token, CLIENT.mask(token))

    def test_handles_no_token(self):
        self.assertEqual(CLIENT.mask(None), "(none)")


class TestTitleNormalisation(unittest.TestCase):
    def test_ignores_case_spacing_and_punctuation(self):
        self.assertEqual(
            CLIENT._normalise_title("  Study   Tracker! "),
            CLIENT._normalise_title("study tracker"),
        )

    def test_distinguishes_genuinely_different_titles(self):
        self.assertNotEqual(
            CLIENT._normalise_title("Data Request"),
            CLIENT._normalise_title("Data Linking Request"),
        )


class TestSirProgress(unittest.TestCase):
    """The rendered 'N/7' the weekly check shows. The counting itself is the shared helper
    below — this class checks the rendering, and that it applies the same rule."""

    def test_counts_nothing_when_no_steps_set(self):
        self.assertEqual(PORTFOLIO.sir_progress({}), "0/7")

    def test_counts_yes_steps(self):
        rec = {"project_created": "Yes", "dd_uploaded": "Yes"}
        self.assertEqual(PORTFOLIO.sir_progress(rec), "2/7")

    def test_no_and_blank_and_zero_do_not_count(self):
        rec = {"project_created": "No", "dd_uploaded": "", "user_rights_complete": "0"}
        self.assertEqual(PORTFOLIO.sir_progress(rec), "0/7")

    def test_radio_label_counts_as_settled(self):
        # data_imported is a radio: "Prospective study, not required" is a settled answer.
        rec = {"data_imported": "Prospective study, not required"}
        self.assertEqual(PORTFOLIO.sir_progress(rec), "1/7")

    def test_all_seven(self):
        rec = {step: "Yes" for step in PORTFOLIO.SIR_BUILD_STEPS}
        self.assertEqual(PORTFOLIO.sir_progress(rec), "7/7")


class TestSharedProgressRule(unittest.TestCase):
    """One rule, in argo_trackers, imported by the weekly check AND the request queue.

    Two functions counted build steps differently until 0.17.2 — the same study read 3/7 to
    the database manager and 4/7 to the project manager. The helper returns counts, not a
    rendered string, so callers can format it however they like without re-implementing it.
    """

    def test_returns_done_and_total(self):
        self.assertEqual(TRACKERS.sir_progress({}), (0, 7))

    def test_total_is_the_canonical_step_count(self):
        _done, total = TRACKERS.sir_progress({})
        self.assertEqual(total, len(TRACKERS.SIR_BUILD_STEPS))

    def test_any_settled_answer_counts_not_just_yes(self):
        self.assertEqual(
            TRACKERS.sir_progress({"data_imported": "Prospective study, not required"}), (1, 7))
        self.assertEqual(TRACKERS.sir_progress({"project_created": "Yes"}), (1, 7))

    def test_no_blank_and_zero_never_count(self):
        for value in ("No", "no", "NO", "", "   ", "0", None):
            self.assertEqual(TRACKERS.sir_progress({"project_created": value})[0], 0,
                             f"{value!r} counted as a completed step")

    def test_fields_outside_the_seven_steps_are_ignored(self):
        self.assertEqual(TRACKERS.sir_progress({"study_status": "Building"}), (0, 7))

    def test_the_weekly_check_renders_the_shared_counts(self):
        rec = {"project_created": "Yes", "data_imported": "Prospective study, not required"}
        done, total = TRACKERS.sir_progress(rec)
        self.assertEqual(PORTFOLIO.sir_progress(rec), f"{done}/{total}")


class TestComputeDiff(unittest.TestCase):
    def snapshot(self, open_ids, done_ids):
        return {"projects": {"DATA_REQUEST": {
            "open": [{"record_id": i, "summary": ""} for i in open_ids],
            "done": [{"record_id": i, "summary": ""} for i in done_ids],
        }}}

    def test_spots_a_new_submission(self):
        diff = PORTFOLIO.compute_diff(self.snapshot(["1", "2"], []), self.snapshot(["1"], []))
        self.assertEqual(diff["DATA_REQUEST"]["new_open"], {"2"})

    def test_spots_something_finishing(self):
        diff = PORTFOLIO.compute_diff(self.snapshot([], ["1"]), self.snapshot(["1"], []))
        self.assertEqual(diff["DATA_REQUEST"]["newly_done"], {"1"})

    def test_carryover_is_not_reported_as_new(self):
        diff = PORTFOLIO.compute_diff(self.snapshot(["1"], []), self.snapshot(["1"], []))
        self.assertEqual(diff["DATA_REQUEST"]["new_open"], set())
        self.assertEqual(diff["DATA_REQUEST"]["still_open"], {"1"})

    def test_a_previously_done_item_reappearing_is_not_new(self):
        # Reopened, not newly submitted — must not inflate the "new this week" count.
        diff = PORTFOLIO.compute_diff(self.snapshot(["1"], []), self.snapshot([], ["1"]))
        self.assertEqual(diff["DATA_REQUEST"]["new_open"], set())

    def test_errored_projects_are_skipped_not_crashed(self):
        # A tracker that couldn't be read must be left out of the diff entirely — reporting it as
        # "everything disappeared this week" would be worse than saying nothing.
        curr = {"projects": {"DATA_REQUEST": {"error": "token not set"}}}
        prev = self.snapshot(["1"], [])
        diff = PORTFOLIO.compute_diff(curr, prev)
        self.assertNotIn("DATA_REQUEST", diff)

    def test_an_error_in_the_previous_snapshot_is_also_skipped(self):
        curr = self.snapshot(["1"], [])
        prev = {"projects": {"DATA_REQUEST": {"error": "connection refused"}}}
        self.assertNotIn("DATA_REQUEST", PORTFOLIO.compute_diff(curr, prev))


class TestRecordIdRangeParsing(unittest.TestCase):
    def setUp(self):
        self.backfill = load(
            PLUGINS / "argo-database-manager/skills/build-study/backfill_sir_from_csv.py",
            "backfill_sir_from_csv",
        )

    def test_parses_a_range(self):
        self.assertEqual(self.backfill.parse_record_id_range("1-108"), (1, 108))

    def test_tolerates_spaces(self):
        self.assertEqual(self.backfill.parse_record_id_range(" 5 - 9 "), (5, 9))

    def test_rejects_a_backwards_range(self):
        with self.assertRaises(SystemExit):
            self.backfill.parse_record_id_range("108-1")

    def test_rejects_nonsense(self):
        for bad in ("", "108", "a-b", "1..108", None):
            with self.assertRaises(SystemExit, msg=repr(bad)):
                self.backfill.parse_record_id_range(bad)


class TestQaDryRunReceipts(unittest.TestCase):
    """The Tier 3 safety gate: a real push requires a preview of this exact data."""

    def setUp(self):
        self.push = load(
            PLUGINS / "argo-qa-specialist/skills/qa-worklists/push_updates.py", "push_updates"
        )
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.push.RECEIPT_DIR = Path(self.tmp) / "receipts"

    def test_fingerprint_is_stable_for_identical_input(self):
        a = self.push._fingerprint("record_id,age\n1,42\n", "CRC_TOKEN")
        b = self.push._fingerprint("record_id,age\n1,42\n", "CRC_TOKEN")
        self.assertEqual(a, b)

    def test_one_edited_cell_changes_the_fingerprint(self):
        a = self.push._fingerprint("record_id,age\n1,42\n", "CRC_TOKEN")
        b = self.push._fingerprint("record_id,age\n1,43\n", "CRC_TOKEN")
        self.assertNotEqual(a, b)

    def test_same_data_to_a_different_project_is_a_different_fingerprint(self):
        a = self.push._fingerprint("record_id,age\n1,42\n", "CRC_TOKEN")
        b = self.push._fingerprint("record_id,age\n1,42\n", "OTHER_TOKEN")
        self.assertNotEqual(a, b)

    def test_no_preview_means_refusal(self):
        self.assertIsNotNone(self.push.check_receipt("nosuchfingerprint"))

    def test_a_fresh_preview_permits_the_push(self):
        fp = self.push._fingerprint("x", "T")
        self.push.write_receipt(fp, 1, [])
        self.assertIsNone(self.push.check_receipt(fp))

    def test_a_stale_preview_is_refused(self):
        import json, time
        fp = self.push._fingerprint("x", "T")
        self.push.write_receipt(fp, 1, [])
        receipt = self.push.RECEIPT_DIR / f"{fp}.json"
        data = json.loads(receipt.read_text())
        data["previewed_at"] = time.time() - (self.push.RECEIPT_MAX_AGE_SECONDS + 60)
        receipt.write_text(json.dumps(data))
        self.assertIsNotNone(self.push.check_receipt(fp))

    def test_a_corrupt_receipt_is_refused_not_crashed(self):
        fp = "deadbeefdeadbeef"
        self.push.RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
        (self.push.RECEIPT_DIR / f"{fp}.json").write_text("{not json")
        self.assertIsNotNone(self.push.check_receipt(fp))


class TestExportRowCounting(unittest.TestCase):
    """0.17.2 #23: export.py reported PHYSICAL LINES as "rows".

    A free-text answer containing a line break spans several lines of the CSV, so a 1,525-patient
    export announced itself as 2,143 — a number a researcher could have put in a paper. The count
    now comes from a real CSV parser, and "patients" is only claimed when the id column proves
    one row per patient.
    """

    HEADER = "syn_id,note,grade\n"

    def test_a_newline_inside_a_field_is_not_a_new_row(self):
        text = self.HEADER + '1,"line one\nline two\nline three",3\n2,plain,2\n'
        self.assertEqual(EXPORT.count_rows(text, "syn_id"), (2, 2))
        # The defect, stated as the number it used to produce.
        self.assertEqual(text.count("\n") - 1, 4)

    def test_a_trailing_blank_line_is_not_a_record(self):
        self.assertEqual(EXPORT.count_rows(self.HEADER + "1,a,3\n2,b,2\n\n", "syn_id"), (2, 2))

    def test_repeat_instrument_rows_outnumber_patients(self):
        text = self.HEADER + "1,a,3\n1,b,2\n2,c,1\n"
        rows, ids = EXPORT.count_rows(text, "syn_id")
        self.assertEqual((rows, ids), (3, 2))

    def test_header_only_is_zero_records(self):
        self.assertEqual(EXPORT.count_rows(self.HEADER, "syn_id"), (0, 0))

    def test_empty_text_does_not_crash(self):
        self.assertEqual(EXPORT.count_rows("", "syn_id"), (0, 0))

    def test_an_unknown_id_column_falls_back_to_the_row_count(self):
        rows, ids = EXPORT.count_rows(self.HEADER + "1,a,3\n", "not_a_column")
        self.assertEqual((rows, ids), (1, 1))


class TestExportSavedLineSaysWhatItSaved(unittest.TestCase):
    """0.17.2 #20/#23: the Saved line names the encoding and counts records, not lines."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _saved(self, **kwargs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            EXPORT.write_file(self.tmp / "x.csv", kwargs.pop("text"), kwargs.pop("label"), **kwargs)
        return buf.getvalue()

    def test_records_say_records_and_one_per_patient(self):
        line = self._saved(text="syn_id,a\n1,x\n2,y\n", label="records", unit="records",
                           id_column="syn_id", encoding_note="(raw codes)")
        self.assertIn("2 records", line)
        self.assertIn("one per patient", line)
        self.assertIn("(raw codes)", line)
        self.assertNotIn("rows", line)

    def test_repeat_rows_report_both_numbers(self):
        line = self._saved(text="syn_id,a\n1,x\n1,y\n2,z\n", label="records", unit="records",
                           id_column="syn_id")
        self.assertIn("3 records across 2 patients", line)

    def test_a_data_dictionary_counts_fields_not_patients(self):
        line = self._saved(text="field_name,form\na,f\nb,f\n", label="data dictionary",
                           unit="fields")
        self.assertIn("2 fields", line)
        self.assertNotIn("patient", line)


class TestExportOutIsAnchoredAtTheSettingsFile(unittest.TestCase):
    """0.17.2 #21: a relative --out was measured from the working directory.

    In a Cowork session that is nowhere the user can see. It is now measured from the folder
    holding their settings file — their ARGO folder — and absolute paths are left alone.
    """

    def test_a_relative_path_lands_beside_the_settings_file(self):
        settings = Path("/somewhere/ARGO-work/.env")
        self.assertEqual(EXPORT.resolve_out("database-manager/exports/crc", settings),
                         Path("/somewhere/ARGO-work/database-manager/exports/crc"))

    def test_an_absolute_path_is_untouched(self):
        self.assertEqual(EXPORT.resolve_out("/tmp/elsewhere", Path("/somewhere/ARGO-work/.env")),
                         Path("/tmp/elsewhere"))

    def test_a_home_relative_path_is_untouched(self):
        got = EXPORT.resolve_out("~/exports", Path("/somewhere/ARGO-work/.env"))
        self.assertEqual(got, Path.home() / "exports")

    def test_with_no_settings_file_the_working_directory_stands(self):
        self.assertEqual(EXPORT.resolve_out("exports/crc", None), Path("exports/crc"))


class TestExportIdentifierAndCheckboxHelpers(unittest.TestCase):
    """0.17.2 #40: the de-identified copy, derived from the dictionary's own Identifier? flag."""

    DD = ("field_name,form_name,field_type,field_label,select_choices_or_calculations,identifier\n"
          "syn_id,demo,text,ID,,\n"
          "name,demo,text,Name,,y\n"
          "mrn,demo,text,Hospital number,,Y\n"
          "sex,demo,radio,Sex,\"1, Male | 2, Female\",\n"
          "symptoms,demo,checkbox,Symptoms,\"1, Pain | 2, Bleeding\",\n"
          "contacts,demo,checkbox,Contacts,\"1, Phone | 2, Email\",y\n")

    def test_identifier_and_checkbox_fields_are_read_from_the_dictionary(self):
        identifiers, checkboxes = EXPORT.field_flags(self.DD)
        self.assertEqual(identifiers, ["name", "mrn", "contacts"])
        self.assertEqual(checkboxes, ["symptoms", "contacts"])

    def test_a_dictionary_with_no_identifiers_yields_none(self):
        clean = self.DD.replace(",y\n", ",\n").replace(",Y\n", ",\n")
        self.assertEqual(EXPORT.field_flags(clean)[0], [])

    def test_dropping_an_identifier_takes_its_checkbox_option_columns_too(self):
        """`contacts` is a checkbox identifier: leaving `contacts___1` behind is the whole bug."""
        raw = ("syn_id,name,mrn,sex,symptoms___1,contacts___1,contacts___2\n"
               "1,Ada,H1,1,1,1,0\n")
        got = EXPORT.drop_fields(raw, EXPORT.field_flags(self.DD)[0])
        self.assertEqual(got.splitlines()[0], "syn_id,sex,symptoms___1")
        self.assertNotIn("Ada", got)
        self.assertNotIn("H1", got)

    def test_dropping_nothing_returns_the_file_unchanged(self):
        raw = "syn_id,sex\n1,1\n"
        self.assertEqual(EXPORT.drop_fields(raw, []), raw)

    def test_a_multiline_value_survives_the_drop(self):
        raw = 'syn_id,name,note\n1,Ada,"two\nlines"\n'
        got = EXPORT.drop_fields(raw, ["name"])
        self.assertEqual(EXPORT.count_rows(got, "syn_id"), (1, 1))
        self.assertIn("two\nlines", got)

    def test_checkbox_columns_collapse_into_one_per_field(self):
        labelled = ("syn_id,sex,symptoms___1,symptoms___2\n"
                    "1,Male,Pain,\n"
                    "2,Female,Pain,Bleeding\n")
        tidy = EXPORT.collapse_checkboxes(labelled, ["symptoms"])
        self.assertEqual(tidy.splitlines(),
                         ["syn_id,sex,symptoms", "1,Male,Pain", "2,Female,Pain; Bleeding"])

    def test_no_checkbox_columns_means_no_pointless_duplicate(self):
        self.assertIsNone(EXPORT.collapse_checkboxes("syn_id,sex\n1,Male\n", ["symptoms"]))


class FakeRedcapProject:
    """The smallest thing export.py can download from. Not an HTTP mock — no transport at all."""

    DD = ("field_name,form_name,field_type,field_label,select_choices_or_calculations,identifier\n"
          "syn_id,demo,text,ID,,\n"
          "name,demo,text,Name,,y\n"
          "sex,demo,radio,Sex,\"1, Male | 2, Female\",\n"
          "symptoms,demo,checkbox,Symptoms,\"1, Pain | 2, Bleeding\",\n")
    RAW = ("syn_id,name,sex,symptoms___1,symptoms___2\n"
           "1,Ada,1,1,0\n"
           '2,"Bo\nLine",2,0,1\n')
    LABELLED = ("syn_id,name,sex,symptoms___1,symptoms___2\n"
                "1,Ada,Male,Pain,\n"
                '2,"Bo\nLine",Female,,Bleeding\n')

    def __init__(self):
        self.calls = []

    def project_info(self, refresh=False):
        return {"project_title": "Syn Cohort", "project_id": "77"}

    def record_id_field(self):
        return "syn_id"

    def export_metadata(self, **params):
        return [{"field_name": "syn_id", "form_name": "demo"}]

    def export_metadata_csv(self, **params):
        self.calls.append(("metadata", params))
        return self.DD

    def export_records_csv(self, **params):
        self.calls.append(("records", params))
        return self.LABELLED if params.get("rawOrLabel") == "label" else self.RAW

    def confirm_project(self, **kwargs):
        return self.project_info()


class TestExportSavesTheWholeSet(unittest.TestCase):
    """0.17.2 #40: one run, the whole set, and a README saying what each file is.

    Defaulting to one encoding meant someone had to choose between "raw" and "labelled" before
    they knew what they needed — and a live round chose wrong. Both are saved, plus a copy with
    the dictionary's flagged identifiers removed, and the folder explains itself.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.fake = FakeRedcapProject()
        saved = EXPORT.RedcapClient.from_env
        EXPORT.RedcapClient.from_env = staticmethod(lambda *a, **k: cls.fake)
        argv = sys.argv
        sys.argv = ["export.py", "--token-env", "SYN_TOKEN", "--out", str(cls.tmp / "syn")]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                cls.code = EXPORT.main()
        finally:
            EXPORT.RedcapClient.from_env = saved
            sys.argv = argv
        cls.stdout = buf.getvalue()
        cls.out = cls.tmp / "syn"
        cls.names = sorted(p.name for p in cls.out.iterdir()) if cls.out.is_dir() else []

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _one(self, fragment):
        hits = [n for n in self.names if fragment in n]
        self.assertEqual(len(hits), 1, f"expected exactly one {fragment!r} file in {self.names}")
        return self.out / hits[0]

    def test_it_completes(self):
        self.assertEqual(self.code, 0, self.stdout)

    def test_both_encodings_are_saved_without_being_asked_for(self):
        raw = self._one("_records_raw_")
        labelled = self._one("_records_labelled_2")   # not the _tidy_ one
        self.assertIn("1,Ada,1,1,0", raw.read_text())
        self.assertIn("1,Ada,Male,Pain,", labelled.read_text())

    def test_the_data_dictionary_comes_too(self):
        self.assertTrue(self._one("_datadictionary_").exists())

    def test_a_de_identified_copy_omits_the_identifier_columns(self):
        raw = self._one("_records_raw_").read_text()
        deid = self._one("_records_deidentified_raw_").read_text()
        self.assertIn("name", raw.splitlines()[0].split(","))
        self.assertNotIn("name", deid.splitlines()[0].split(","),
                         "the dictionary flags `name` as an identifier")
        self.assertNotIn("Ada", deid)
        # and it is still the same records, not a truncated file
        self.assertEqual(EXPORT.count_rows(deid, "syn_id"),
                         EXPORT.count_rows(raw, "syn_id"))

    def test_the_de_identified_copy_exists_in_both_encodings(self):
        self.assertTrue(self._one("_records_deidentified_labelled_").exists())

    def test_the_tidy_file_folds_checkbox_columns(self):
        tidy = self._one("_records_labelled_tidy_").read_text()
        header = tidy.splitlines()[0].split(",")
        self.assertIn("symptoms", header)
        self.assertNotIn("symptoms___1", header)

    def test_the_readme_lists_every_file_with_its_encoding_and_count(self):
        readme = (self.out / "README.md").read_text()
        for name in self.names:
            if name != "README.md":
                self.assertIn(name, readme, f"{name} is not described in the README")
        self.assertIn("raw codes", readme)
        self.assertIn("readable labels", readme)
        self.assertIn("2 records", readme, "counts must be CSV rows, not the 3 physical lines")
        self.assertNotIn("3 records", readme)

    def test_the_readme_says_which_file_the_tools_read_and_which_is_shareable(self):
        readme = (self.out / "README.md").read_text()
        self.assertIn("Which one do I use?", readme)
        self.assertIn("**The raw file**", readme)
        self.assertIn("Which one is safe to share?", readme)
        self.assertIn("`name`", readme, "the removed identifier fields must be listed by name")

    def test_the_saved_lines_say_the_same_things(self):
        self.assertIn("raw codes", self.stdout)
        self.assertIn("readable labels", self.stdout)
        self.assertIn("identifiers removed", self.stdout)
        self.assertIn("README.md", self.stdout)
        self.assertIn("2 records", self.stdout)

    def test_no_encoding_question_is_asked(self):
        """The point of saving both: there is nothing to decide up front."""
        help_text = subprocess.run(
            [sys.executable, str(PLUGINS / "argo-database-manager/skills/export-data/export.py"),
             "--help"], capture_output=True, text=True, timeout=60).stdout
        self.assertNotIn("--labels", help_text, "the raw-vs-labels choice is retired")
        self.assertIn("--only-raw", help_text)
        self.assertIn("--only-labelled", help_text)


class TestExportWithNoIdentifiersFlagged(unittest.TestCase):
    """A dictionary that flags nothing must not produce a file promising de-identification."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        fake = FakeRedcapProject()
        fake.DD = FakeRedcapProject.DD.replace(",y\n", ",\n")
        saved = EXPORT.RedcapClient.from_env
        EXPORT.RedcapClient.from_env = staticmethod(lambda *a, **k: fake)
        argv = sys.argv
        sys.argv = ["export.py", "--token-env", "SYN_TOKEN", "--out", str(cls.tmp / "syn")]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                cls.code = EXPORT.main()
        finally:
            EXPORT.RedcapClient.from_env = saved
            sys.argv = argv
        cls.stdout = buf.getvalue()
        cls.out = cls.tmp / "syn"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_no_deidentified_file_is_written(self):
        self.assertEqual(self.code, 0, self.stdout)
        self.assertEqual([p.name for p in self.out.glob("*deidentified*")], [])

    def test_the_readme_says_why_instead(self):
        readme = (self.out / "README.md").read_text()
        self.assertIn("marks no field as an identifier", readme)
        self.assertIn("Identifier?", readme,
                      "point at the Designer column someone needs to fix")


class TestExportEncodingIsDocumented(unittest.TestCase):
    """0.17.2 #20/#40: the skill must say which file is which, and never call the key path and
    the website path interchangeable without the raw/labelled caveat."""

    DOC = (PLUGINS / "argo-database-manager/skills/export-data/SKILL.md").read_text()

    def test_the_file_set_is_documented(self):
        for fragment in ("_records_raw_", "_records_labelled_", "_records_deidentified_raw_",
                         "README.md"):
            self.assertIn(fragment, self.DOC, f"the skill doesn't mention {fragment}")

    def test_the_doc_does_not_call_the_two_paths_identical(self):
        self.assertNotIn("Those two files are exactly what", self.DOC,
                         "the key path and the website path are only interchangeable when both "
                         "are raw — the doc must carry that caveat")

    def test_the_study_is_identified_by_the_key_not_by_a_tracker(self):
        """0.17.2 #40: a session went to the Study Tracker to work out which study 'CRC' meant.

        No tracker holds study keys, and none can say which project a key opens — only --info
        can, by asking REDCap.
        """
        self.assertIn("--info", self.DOC)
        self.assertIn("Do not open the Study Tracker", self.DOC)


TRACKER_VARS = [env for env, *_ in CLIENT.TIER1_PROJECTS]


class TestCheckOnlyTriesKeysFromTheSettingsFile(unittest.TestCase):
    """0.17.2 #19 (security): `--check` harvested every `*_TOKEN` in the environment.

    It POSTed whatever it found to REDCap as a study key — in one walkthrough that was the
    session harness's own CLAUDE_CODE_MESSAGING_TOKEN — and then told the user their setup was
    broken, because REDCap refused a secret that was never a REDCap key. Study keys now come
    from the settings file the client just loaded, and from nowhere else.

    No network: the two methods that would talk to REDCap are replaced for the duration.
    """

    def setUp(self):
        self.saved = dict(os.environ)
        self.tmp = Path(tempfile.mkdtemp())
        for var in list(os.environ):
            if var.endswith("_TOKEN") or var in TRACKER_VARS or var in ("REDCAP_URL",
                                                                        "ARGO_ENV_FILE"):
                os.environ.pop(var, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    URL_LINE = "REDCAP_URL=https://redcap.example.org/api/\n"

    def _run_check(self, settings_text):
        env_file = self.tmp / "argo.env"
        env_file.write_text(settings_text)
        os.environ["ARGO_ENV_FILE"] = str(env_file)
        known = {title: {"project_title": title, "project_id": pid}
                 for _e, title, pid in CLIENT.TIER1_PROJECTS}
        real_info = CLIENT.RedcapClient.project_info
        real_id = CLIENT.RedcapClient.record_id_field
        CLIENT.RedcapClient.project_info = lambda self, refresh=False: known.get(
            self.label, {"project_title": self.label, "project_id": "999"})
        CLIENT.RedcapClient.record_id_field = lambda self: "record_id"
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                code = CLIENT.run_check()
        finally:
            CLIENT.RedcapClient.project_info = real_info
            CLIENT.RedcapClient.record_id_field = real_id
        return code, buf.getvalue()

    def _trackers(self):
        return "".join(f"{env}=trackerkey{i}\n" for i, env in enumerate(TRACKER_VARS))

    def test_an_unrelated_token_in_the_environment_is_never_touched(self):
        os.environ["CLAUDE_CODE_MESSAGING_TOKEN"] = "harness-secret-value"
        os.environ["FOO_TOKEN"] = "someone-elses-secret"
        code, out = self._run_check(self.URL_LINE + self._trackers())
        self.assertNotIn("CLAUDE_CODE_MESSAGING_TOKEN", out)
        self.assertNotIn("FOO_TOKEN", out)
        self.assertNotIn("harness-secret-value", out)
        self.assertNotIn("someone-elses-secret", out)
        self.assertNotIn("Study keys:", out, "nothing in the settings file is a study key here")
        self.assertIn("0 not working", out, "no key may be reported broken because of these")
        self.assertEqual(code, 0, out)

    def test_a_study_key_written_in_the_settings_file_is_still_checked(self):
        """Scoping must not throw the baby out: a real study key still gets verified."""
        os.environ["FOO_TOKEN"] = "someone-elses-secret"
        code, out = self._run_check(self.URL_LINE + self._trackers() + "CRC_TOKEN=studykey\n")
        self.assertIn("Study keys:", out)
        self.assertIn("CRC_TOKEN", out)
        self.assertNotIn("FOO_TOKEN", out)
        self.assertEqual(code, 0, out)

    def test_a_workspace_with_no_keys_says_exactly_that_and_blames_nothing(self):
        os.environ["CLAUDE_CODE_MESSAGING_TOKEN"] = "harness-secret-value"
        code, out = self._run_check(self.URL_LINE)
        self.assertIn("No REDCap access keys are set up yet", out)
        self.assertIn("nothing here is broken", out)
        self.assertIn("0 not working", out)
        self.assertNotIn("✗", out, "nothing may be listed as broken when nothing is configured")
        self.assertNotIn("CLAUDE_CODE_MESSAGING_TOKEN", out)
        self.assertEqual(code, 1, "exit 1 is 'nothing configured', and the message says so")


class TestSettingsFileKeyParsing(unittest.TestCase):
    """What counts as a key written in a settings file. Deliberately narrow."""

    def keys(self, text):
        path = Path(tempfile.mkdtemp()) / ".env"
        path.write_text(text)
        try:
            return CLIENT.settings_file_keys(path)
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)

    def test_a_filled_line_counts(self):
        self.assertEqual(self.keys("CRC_TOKEN=abc123\n"), ["CRC_TOKEN"])

    def test_a_blank_placeholder_does_not(self):
        """The scaffolded settings file ships every tracker line empty — those aren't keys."""
        self.assertEqual(self.keys("CRC_TOKEN=\nOTHER_TOKEN=   \n"), [])

    def test_a_commented_line_does_not(self):
        self.assertEqual(self.keys("# CRC_TOKEN=abc123\n"), [])

    def test_export_prefix_and_quotes_are_understood(self):
        self.assertEqual(self.keys('export CRC_TOKEN="abc123"\n'), ["CRC_TOKEN"])

    def test_non_token_settings_are_not_keys(self):
        self.assertEqual(self.keys("REDCAP_URL=https://x/api/\nARGO_ROLES=qa\n"), [])

    def test_a_missing_or_unreadable_file_yields_nothing(self):
        self.assertEqual(CLIENT.settings_file_keys(None), [])
        self.assertEqual(CLIENT.settings_file_keys(Path("/no/such/file/.env")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
