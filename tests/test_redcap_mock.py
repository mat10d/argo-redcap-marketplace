"""The mock REDCap — the thing that makes a test workspace unable to reach a real one.

Two properties matter more than any feature: it is INERT unless the settings file asks for it,
and it REFUSES to run against a real address. Everything else — reads served from fixtures,
writes logged and not applied, the File Repository — exists so a live Cowork session can run
the real skills end to end against synthetic projects and be graded afterwards.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "plugins/argo-core/skills/redcap-api/scripts"
sys.path.insert(0, str(SCRIPTS))

import argo_redcap_mock as mock  # noqa: E402
from argo_redcap_client import RedcapClient, RedcapError, load_env_file  # noqa: E402

MOCK_URL = "https://mock.argo.invalid/api/"


def _post(url, **params):
    """Raw POST the way the four non-client scripts do it — the mock must catch these too."""
    data = urllib.parse.urlencode({"format": "json", **params}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode()


class MockFolder:
    """A tiny mock folder with one tracker-shaped project and one study-shaped project."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "mock"
        (self.root / "projects/tracker/files/ARGO Templates/ARGO Protocol Template").mkdir(parents=True)
        (self.root / "projects/study").mkdir(parents=True)
        self.tracker_token = mock.fake_token("tracker")
        self.study_token = mock.fake_token("study")
        (self.root / "keys.json").write_text(json.dumps(
            {self.tracker_token: "tracker", self.study_token: "study"}))
        (self.root / "config.json").write_text(json.dumps({"apply_writes": False}))

        t = self.root / "projects/tracker"
        (t / "project.json").write_text(json.dumps(
            {"project_id": "224", "project_title": "Study Tracker", "_stored_mode": "label"}))
        (t / "metadata.json").write_text(json.dumps([
            {"field_name": "record_id", "form_name": "sir", "field_type": "text", "field_label": "ID"},
            {"field_name": "project_title", "form_name": "sir", "field_type": "text", "field_label": "Title"},
            {"field_name": "project_created", "form_name": "build_tracking", "field_type": "yesno",
             "field_label": "Created?", "select_choices_or_calculations": ""},
        ]))
        (t / "records.json").write_text(json.dumps([
            {"record_id": "1", "project_title": "Alpha", "project_created": "Yes"},
            {"record_id": "2", "project_title": "Beta", "project_created": "No"},
        ]))
        (t / "files/ARGO Templates/ARGO Protocol Template/ARGO Protocol Template.docx").write_bytes(b"PK-fake-docx")

        s = self.root / "projects/study"
        (s / "project.json").write_text(json.dumps(
            {"project_id": "9077", "project_title": "SYN — Synthetic Cohort", "_stored_mode": "raw"}))
        (s / "metadata.json").write_text(json.dumps([
            {"field_name": "syn_id", "form_name": "demo", "field_type": "text", "field_label": "ID"},
            {"field_name": "sex", "form_name": "demo", "field_type": "radio", "field_label": "Sex",
             "select_choices_or_calculations": "1, Male | 2, Female"},
            {"field_name": "symptoms", "form_name": "clinical", "field_type": "checkbox",
             "field_label": "Symptoms", "select_choices_or_calculations": "1, Pain | 2, Bleeding"},
        ]))
        (s / "records.json").write_text(json.dumps([
            {"syn_id": "SYN-0001", "redcap_data_access_group": "site_alpha", "sex": "1",
             "symptoms___1": "1", "symptoms___2": "0"},
            {"syn_id": "SYN-0002", "redcap_data_access_group": "site_beta", "sex": "2",
             "symptoms___1": "0", "symptoms___2": "1"},
        ]))

    def settings(self, url=MOCK_URL, flag=".mock", extra="") -> Path:
        env = Path(self.tmp.name) / ".env"
        env.write_text(f"REDCAP_URL={url}\nARGO_REDCAP_MOCK={flag}\n"
                       f"STUDY_INITIATION_REQUEST={self.tracker_token}\nCRC_TOKEN={self.study_token}\n{extra}")
        return env

    def cleanup(self):
        self.tmp.cleanup()


class MockRedcapTests(unittest.TestCase):
    def setUp(self):
        self.f = MockFolder()
        self._env = dict(os.environ)
        for k in ("REDCAP_URL", "ARGO_REDCAP_MOCK", "STUDY_INITIATION_REQUEST", "CRC_TOKEN"):
            os.environ.pop(k, None)
        mock.uninstall()

    def tearDown(self):
        mock.uninstall()
        os.environ.clear(); os.environ.update(self._env)
        self.f.cleanup()

    def _install(self, **kw):
        env = self.f.settings(**kw)
        self.assertEqual(load_env_file(str(env)), env)
        return env

    # -- the two properties that matter ---------------------------------------------

    def test_inert_without_the_flag(self):
        (Path(self.f.tmp.name) / ".env").write_text(f"REDCAP_URL={MOCK_URL}\n")
        load_env_file(str(Path(self.f.tmp.name) / ".env"))
        self.assertFalse(mock.is_active())
        self.assertIs(urllib.request.urlopen, mock._real_urlopen,
                      "without ARGO_REDCAP_MOCK the real urlopen must be untouched")

    def test_refuses_a_real_redcap_address(self):
        env = self.f.settings(url="https://redcap.oauife.edu.ng/api/")
        with self.assertRaises(mock.MockConfigError) as cm:
            load_env_file(str(env))
        self.assertIn(".invalid", str(cm.exception))
        self.assertFalse(mock.is_active())

    def test_the_mock_flag_resolves_relative_to_the_settings_file(self):
        # The folder is named ".mock" in the settings file; it lives beside that file.
        os.rename(self.f.root, Path(self.f.tmp.name) / ".mock")
        self._install()
        self.assertTrue(mock.is_active())
        self.assertEqual(mock._installed.folder, (Path(self.f.tmp.name) / ".mock").resolve())

    def test_other_hosts_are_unreachable_in_mock_mode(self):
        os.rename(self.f.root, Path(self.f.tmp.name) / ".mock")
        self._install()
        with self.assertRaises(urllib.error.URLError) as cm:
            _post("https://example.com/anything", content="project")
        self.assertIn("network is disabled", str(cm.exception.reason))

    # -- reads ----------------------------------------------------------------------

    def _active(self):
        os.rename(self.f.root, Path(self.f.tmp.name) / ".mock")
        self._install()
        return Path(self.f.tmp.name) / ".mock"

    def test_project_info_and_confirm_project_work_through_the_client(self):
        self._active()
        client = RedcapClient.from_env("STUDY_INITIATION_REQUEST", label="Study Tracker")
        self.assertEqual(client.project_title(), "Study Tracker")
        client.confirm_project(expect_title="Study Tracker", expect_pid="224")
        with self.assertRaises(RedcapError):
            client.confirm_project(expect_pid="999")

    def test_unknown_token_is_a_403_the_client_explains(self):
        self._active()
        os.environ["BOGUS_TOKEN"] = "0" * 32
        client = RedcapClient.from_env("BOGUS_TOKEN")
        with self.assertRaises(RedcapError) as cm:
            client.project_info()
        self.assertIn("refused", str(cm.exception))

    def test_records_label_and_raw_from_label_stored_fixtures(self):
        self._active()
        client = RedcapClient.from_env("STUDY_INITIATION_REQUEST")
        label = client.export_records(rawOrLabel="label")
        self.assertEqual(label[0]["project_created"], "Yes")
        raw = client.export_records()
        self.assertEqual(raw[0]["project_created"], "1", "label-stored yesno maps back to a code")
        one = client.export_records(records="2")
        self.assertEqual([r["record_id"] for r in one], ["2"])

    def test_records_filters_the_way_the_scripts_ask(self):
        self._active()
        # sir_update / setup_brief spell it records[0]=; open_requests spells it records=.
        body = _post(MOCK_URL, token=self.f.tracker_token, content="record", **{"records[0]": "1"})
        self.assertEqual([r["record_id"] for r in json.loads(body)], ["1"])
        body = _post(MOCK_URL, token=self.f.tracker_token, content="record",
                     **{"fields[0]": "record_id", "fields[1]": "project_title"})
        self.assertEqual(set(json.loads(body)[0]), {"record_id", "project_title"})

    def test_study_export_csv_with_labels_checkboxes_and_dags(self):
        self._active()
        client = RedcapClient.from_env("CRC_TOKEN")
        text = client.export_records_csv(exportDataAccessGroups="true")   # label + checkbox labels
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(rows[0]["sex"], "Male")
        self.assertEqual(rows[0]["symptoms___1"], "Pain")
        self.assertEqual(rows[0]["symptoms___2"], "")
        self.assertEqual(rows[1]["redcap_data_access_group"], "site_beta")
        raw = client.export_records_csv(rawOrLabel="raw", exportCheckboxLabel="false",
                                        exportDataAccessGroups="false")
        rows = list(csv.DictReader(io.StringIO(raw)))
        self.assertEqual(rows[0]["sex"], "1")
        self.assertNotIn("redcap_data_access_group", rows[0])

    def test_metadata_json_csv_and_forms_filter(self):
        self._active()
        client = RedcapClient.from_env("CRC_TOKEN")
        self.assertEqual(client.record_id_field(), "syn_id")
        dd = client.export_metadata_csv()
        header = dd.splitlines()[0].split(",")
        self.assertEqual(header[0], "field_name")
        self.assertEqual(len(header), 18, "the standard 18-column data dictionary")
        clinical = client.export_metadata(forms="clinical")
        self.assertEqual([m["field_name"] for m in clinical], ["symptoms"])

    def test_file_repository_list_and_export(self):
        self._active()
        client = RedcapClient.from_env("STUDY_INITIATION_REQUEST")
        root = client.list_file_repository()
        self.assertEqual([i["name"] for i in root], ["ARGO Templates"])
        templates = client.list_file_repository(root[0]["folder_id"])
        self.assertEqual(templates[0]["name"], "ARGO Protocol Template")
        inner = client.list_file_repository(templates[0]["folder_id"])
        self.assertEqual(inner[0]["name"], "ARGO Protocol Template.docx")
        self.assertEqual(client.export_file_repository(inner[0]["doc_id"]), b"PK-fake-docx")

    def test_user_export_is_refused_like_a_properly_scoped_key(self):
        self._active()
        client = RedcapClient.from_env("CRC_TOKEN")
        self.assertEqual(client.warn_if_over_permissioned(), [])

    # -- writes ---------------------------------------------------------------------

    def test_writes_are_logged_with_their_payload_and_not_applied(self):
        folder = self._active()
        client = RedcapClient.from_env("STUDY_INITIATION_REQUEST", label="Study Tracker")
        result = client.import_records([{"record_id": "2", "project_created": "1"}],
                                       expect_title="Study Tracker", expect_pid="224",
                                       overwrite="normal")
        self.assertEqual(result, {"count": 1})
        writes = [json.loads(l) for l in (folder / "WRITES.jsonl").read_text().splitlines()]
        self.assertEqual(len(writes), 1)
        w = writes[0]
        self.assertEqual((w["project"], w["content"], w["count"], w["applied"]),
                         ("tracker", "record", 1, False))
        self.assertEqual(w["data"], [{"record_id": "2", "project_created": "1"}])
        self.assertEqual(w["overwriteBehavior"], "normal")
        # and the fixture is untouched
        after = client.export_records(records="2")
        self.assertEqual(after[0]["project_created"], "0")

    def test_writes_apply_only_when_config_says_so(self):
        folder = self._active()
        (folder / "config.json").write_text(json.dumps({"apply_writes": True}))
        mock.uninstall(); self._install()
        client = RedcapClient.from_env("STUDY_INITIATION_REQUEST", label="Study Tracker")
        client.import_records([{"record_id": "2", "project_created": "1"}], expect_pid="224")
        self.assertEqual(client.export_records(records="2")[0]["project_created"], "1")

    def test_csv_import_and_metadata_upload_are_writes_too(self):
        folder = self._active()
        client = RedcapClient.from_env("CRC_TOKEN")
        n = client.import_records_csv("syn_id,sex\nSYN-0001,2\n", expect_pid="9077")
        self.assertEqual(n, "1")
        client.import_metadata("field_name,form_name\nx,demo\n", expect_pid="9077")
        kinds = [(json.loads(l)["content"], json.loads(l)["count"])
                 for l in (folder / "WRITES.jsonl").read_text().splitlines()]
        self.assertEqual(kinds, [("record", 1), ("metadata", 1)])

    def test_every_call_is_logged_with_its_project(self):
        folder = self._active()
        RedcapClient.from_env("CRC_TOKEN").project_info()
        RedcapClient.from_env("STUDY_INITIATION_REQUEST").export_records()
        calls = [json.loads(l) for l in (folder / "CALLS.jsonl").read_text().splitlines()]
        self.assertEqual([(c["project"], c["content"]) for c in calls],
                         [("study", "project"), ("tracker", "record")])
        self.assertTrue(all(not c["is_write"] for c in calls))
        self.assertTrue(all("token" not in c.get("params", {}) for c in calls),
                        "the call log never carries the token itself")

    def test_egress_block_can_be_simulated(self):
        folder = self._active()
        (folder / "config.json").write_text(json.dumps({"simulate_egress_block": True}))
        mock.uninstall(); self._install()
        client = RedcapClient.from_env("STUDY_INITIATION_REQUEST")
        with self.assertRaises(RedcapError) as cm:
            client.project_info()
        self.assertIn("restricted by your organisation", str(cm.exception))
        self.assertNotIn("access key is wrong", str(cm.exception))


class MockIsVendoredAndGuarded(unittest.TestCase):
    def test_the_client_installs_the_mock_on_the_settings_path_every_script_takes(self):
        text = (SCRIPTS / "argo_redcap_client.py").read_text()
        self.assertIn("_maybe_install_mock(path)", text)
        self.assertIn("argo_redcap_mock.install(settings_path)", text)

    def test_the_four_raw_urllib_scripts_still_load_settings_through_the_client(self):
        """These bypass RedcapClient, so the hook in load_env_file is the only thing that
        routes them to the mock. If one of them stops calling it, it reaches the real URL."""
        for rel in ("argo-database-manager/skills/weekly-check/portfolio.py",
                    "argo-database-manager/skills/build-study/setup_brief.py",
                    "argo-database-manager/skills/build-study/fill_new_project.py",
                    "argo-database-manager/skills/build-study/sir_update.py"):
            text = (REPO / "plugins" / rel).read_text()
            self.assertIn("load_env_file", text, f"{rel} must load settings via the client")

    def test_the_mock_module_is_vendored_into_every_skill(self):
        missing = [p for p in (REPO / "plugins").glob("*/skills/*/scripts/argo_redcap_client.py")
                   if not (p.parent / "argo_redcap_mock.py").exists()]
        self.assertFalse(missing, f"release.py has not vendored the mock into: {missing}")


if __name__ == "__main__":
    unittest.main()
