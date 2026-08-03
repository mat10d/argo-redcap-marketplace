#!/usr/bin/env python3
"""Unit tests for the parts of the ARGO suite that need no REDCap connection.

Run them all:
    python3 -m pytest tests/ -q          (or, with no pytest installed)
    python3 tests/test_pure_logic.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGINS = REPO / "plugins"


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
PORTFOLIO = load(
    PLUGINS / "argo-pm/skills/study-portfolio/portfolio.py",
    "portfolio",
    {"ARGO_PM_ROOT": str(Path(os.environ.get("TMPDIR", "/tmp")) / "argo-test-pm")},
)


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
        self.assertIn("~/.argo/.env", text)
        self.assertIn("REDCAP_URL=", text)


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
            PLUGINS / "argo-build/skills/redcap-build/backfill_sir_from_csv.py",
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
            PLUGINS / "argo-qa/skills/redcap-qa/push_updates.py", "push_updates"
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
