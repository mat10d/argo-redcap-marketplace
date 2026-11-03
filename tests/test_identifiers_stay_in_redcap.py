"""Identifiers never leave REDCap (decided 2026-11-03, access-tiers.md).

Every record download asks only for fields the data dictionary does not flag as identifiers.
Asking for identifiers needs two keys — the call asks for them AND the private settings file holds
ARGO_ALLOW_IDENTIFIERS=linkage — and warns hard when both are there. These tests capture what the
client would send to REDCap; nothing reaches a server.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "plugins/argo-core/skills/redcap-api/scripts"))

import argo_redcap_client as c  # noqa: E402

META = [
    {"field_name": "record_id", "form_name": "consent", "field_type": "text", "identifier": "y"},
    {"field_name": "hospital_number", "form_name": "consent", "field_type": "text", "identifier": "y"},
    {"field_name": "intro", "form_name": "consent", "field_type": "descriptive", "identifier": ""},
    {"field_name": "surname", "form_name": "demographics", "field_type": "text", "identifier": "y"},
    {"field_name": "age", "form_name": "demographics", "field_type": "text", "identifier": ""},
    {"field_name": "stage", "form_name": "clinical", "field_type": "radio", "identifier": ""},
]


class TheFieldList(unittest.TestCase):
    def test_everything_means_every_non_identifier_field_plus_form_status(self):
        params, dropped = c.allowed_record_params(META, {"rawOrLabel": "raw"})
        self.assertEqual(params["fields"], ["record_id", "consent_complete", "age",
                                            "demographics_complete", "stage", "clinical_complete"])
        self.assertEqual(sorted(dropped), ["hospital_number", "surname"])
        self.assertEqual(params["rawOrLabel"], "raw")

    def test_the_record_id_always_comes_even_when_flagged(self):
        params, _ = c.allowed_record_params(META, {"fields": ["stage"]})
        self.assertEqual(params["fields"], ["record_id", "stage"])

    def test_forms_become_fields_so_redcap_cannot_add_the_whole_form_back(self):
        params, dropped = c.allowed_record_params(META, {"forms": "demographics"})
        self.assertNotIn("forms", params)
        self.assertEqual(params["fields"], ["record_id", "age", "demographics_complete"])
        self.assertEqual(dropped, ["surname"])

    def test_an_explicit_request_for_an_identifier_is_quietly_left_out(self):
        params, dropped = c.allowed_record_params(META, {"fields": "hospital_number,age"})
        self.assertEqual(params["fields"], ["record_id", "age"])
        self.assertEqual(dropped, ["hospital_number"])


class TheClient(unittest.TestCase):
    def client(self, env_var="CRC_TOKEN"):
        cl = c.RedcapClient("0" * 32, url="https://redcap.example.org/api/")
        cl.env_var = env_var
        cl._metadata = META
        return cl

    def sent(self, cl, **kw):
        with mock.patch.object(c.RedcapClient, "_post", return_value=[]) as post:
            cl.export_records(**kw)
        return post.call_args.kwargs

    def test_a_study_download_never_asks_for_identifiers(self):
        cl = self.client()
        sent = self.sent(cl)
        self.assertNotIn("hospital_number", sent["fields"])
        self.assertNotIn("surname", sent["fields"])
        self.assertEqual(sorted(cl.dropped_identifiers), ["hospital_number", "surname"])

    def test_the_csv_download_obeys_the_same_rule(self):
        cl = self.client()
        with mock.patch.object(c.RedcapClient, "_post", return_value="") as post:
            cl.export_records_csv(forms="consent")
        self.assertEqual(post.call_args.kwargs["fields"], ["record_id", "consent_complete"])

    def test_identifiers_are_refused_without_the_settings_line(self):
        cl = self.client()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(c.ALLOW_IDENTIFIERS_SETTING, None)
            with mock.patch.object(c.RedcapClient, "_post", return_value=[]) as post:
                with self.assertRaises(c.RedcapError) as e:
                    cl.export_records(include_identifiers=True)
        post.assert_not_called()
        self.assertIn("stay in REDCap", str(e.exception))

    def test_with_both_keys_identifiers_come_and_the_warning_is_loud(self):
        cl = self.client()
        err = io.StringIO()
        with mock.patch.dict(os.environ, {c.ALLOW_IDENTIFIERS_SETTING: "linkage"}), \
                redirect_stderr(err):
            sent = self.sent(cl, include_identifiers=True)
        self.assertNotIn("fields", sent, "an unfiltered download")
        self.assertIn("IDENTIFIERS INCLUDED", err.getvalue())
        self.assertIn("linkage", err.getvalue())

    def test_any_other_value_of_the_setting_is_not_an_opt_in(self):
        with mock.patch.dict(os.environ, {c.ALLOW_IDENTIFIERS_SETTING: "yes"}):
            with self.assertRaises(c.RedcapError):
                c.identifiers_allowed()

    def test_admin_trackers_are_exempt(self):
        cl = self.client(env_var="STUDY_INITIATION_REQUEST")
        sent = self.sent(cl)
        self.assertNotIn("fields", sent, "trackers hold no patient data")


class EveryPatientDownloadGoesThroughTheRule(unittest.TestCase):
    """A guard: a skill script that asks REDCap for records must use the client or record_payload,
    unless it only ever reads the admin trackers."""
    TRACKER_ONLY = {"portfolio.py", "sir_update.py", "fill_new_project.py",
                    "backfill_sir_from_csv.py", "close_request.py"}

    def test_no_raw_record_download_outside_the_rule(self):
        offenders = []
        for path in (REPO / "plugins").glob("*/skills/*/*.py"):
            if path.name in self.TRACKER_ONLY:
                continue
            text = path.read_text()
            raw = ('content="record"' in text or "'content': 'record'" in text
                   or '"content": "record"' in text)
            if raw and "record_payload" not in text:
                offenders.append(str(path.relative_to(REPO)))
        self.assertEqual(offenders, [], "these download records around the identifier rule")


if __name__ == "__main__":
    unittest.main()
