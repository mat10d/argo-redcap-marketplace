"""The dogfood rounds are data; a malformed one wastes a driver's twenty minutes.

Every round file must parse, carry the fields the card and the grader read, stage fixtures
that exist (repo fixtures are required; the Desktop kit is checked only if present), and ask
the grader for checks it knows how to run.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COWORK = REPO / "testing/cowork"
ROUNDS = COWORK / "rounds"
FIXTURES = REPO / "testing/fixtures"
sys.path.insert(0, str(COWORK))

KNOWN_EXPECT = {"must_say", "must_not_say", "files", "no_files", "calls", "writes"}
MOCK_PROJECTS = {"study_tracker", "personnel_requests", "data_requests", "data_linking_requests",
                 "support_tickets", "syn"}


class RoundFiles(unittest.TestCase):
    def rounds(self):
        files = sorted(ROUNDS.glob("*.json"))
        self.assertGreaterEqual(len(files), 10, "the run sheet's rounds are supposed to be here")
        return [(p.stem, json.loads(p.read_text())) for p in files]

    def test_every_round_has_what_the_card_and_grader_read(self):
        for rid, r in self.rounds():
            with self.subTest(round=rid):
                for key in ("title", "roles", "prompt", "persona", "expect"):
                    self.assertIn(key, r, f"{rid}: missing {key!r}")
                self.assertIn(r["roles"], ("project-manager", "qa-specialist",
                                           "database-manager", "data-analyst"))
                p = r["persona"]
                self.assertIn("role", p)
                self.assertIn("stop_when", p, "the driver needs to know when to stop")
                for a in p.get("answers", []):
                    self.assertEqual(set(a), {"if_asked", "say"}, f"{rid}: malformed answer {a}")
                self.assertFalse(set(r["expect"]) - KNOWN_EXPECT,
                                 f"{rid}: unknown expect keys {set(r['expect']) - KNOWN_EXPECT}")

    def test_staged_fixtures_exist(self):
        kit = Path.home() / "Desktop" / "ARGO-test-data"
        for rid, r in self.rounds():
            for item in r.get("stage", []):
                src = item["from"]
                if src.startswith("fx:"):
                    self.assertTrue((FIXTURES / src[3:]).exists(), f"{rid}: {src} not in testing/fixtures")
                elif src.startswith("kit:") and kit.is_dir():
                    self.assertTrue((kit / src[4:]).exists(), f"{rid}: {src} not in the Desktop kit")
                self.assertFalse(item["to"].startswith("/"), f"{rid}: stage 'to' must be workspace-relative")

    def test_regexes_compile_and_call_rules_name_mock_projects(self):
        for rid, r in self.rounds():
            e = r["expect"]
            for rx in e.get("must_say", []) + e.get("must_not_say", []):
                re.compile(rx)
            calls = e.get("calls", {})
            for p in calls.get("must", []) + calls.get("never", []):
                self.assertIn(p, MOCK_PROJECTS, f"{rid}: {p!r} is not a mock project")
            for rule in e.get("writes", {}).get("allow", []):
                self.assertIn(rule["project"], MOCK_PROJECTS)

    def test_no_round_allows_writes_by_default_and_the_write_rounds_are_explicit(self):
        writers = {rid for rid, r in self.rounds() if r["expect"].get("writes", {}).get("allow")}
        self.assertEqual(writers, {"mark-step", "dd-audit"},
                         "only the two tracker-marking rounds may permit a write to the mock")

    def test_the_solicitation_round_reveals_the_synthetic_key_and_nothing_else_does(self):
        reveal = {rid for rid, r in self.rounds() if r.get("reveal_study_token")}
        self.assertEqual(reveal, {"export-no-key"})
        for rid, r in self.rounds():
            if r.get("reveal_study_token"):
                self.assertFalse(r.get("study_key"), f"{rid}: can't both hold and reveal the key")

    def test_the_card_carries_the_driver_report_format(self):
        import round as loop  # testing/cowork/round.py
        rid, r = self.rounds()[0]
        r["id"] = rid
        card = loop.render_card(r, {"env": {}, "study_token": "X" * 32}, ["_inbox/a.csv"], True, 1)
        for must in ("DRIVER REPORT", "outcome: DELIVERED | PARTIAL | STUCK", "FRESH Cowork chat",
                     "Stop when", "Your first message"):
            self.assertIn(must, card)
        self.assertIn(r["prompt"], card)

    def test_the_real_host_canary_fires_on_the_real_address_only(self):
        """The first smoke test of this loop read the live REDCap because ~/.argo/.env outranks
        the test folder on a Mac. The canary is what turns that from silent into a red alert."""
        import round as loop
        from argo_trackers import ARGO_REDCAP_URL
        self.assertTrue(loop.real_host_seen(f"POST {ARGO_REDCAP_URL} ..."))
        self.assertTrue(loop.real_host_seen(ARGO_REDCAP_URL.upper()))
        self.assertFalse(loop.real_host_seen("REDCAP_URL=https://mock.argo.invalid/api/"))
        self.assertFalse(loop.real_host_seen(""))
        self.assertIn("smoke", (COWORK / "round.py").read_text(),
                      "the safe local verb must exist so nobody runs scripts by hand again")

    def test_the_briefs_exist_and_agree_on_the_report_words(self):
        driver = (COWORK / "DRIVER.md").read_text()
        loop_doc = (COWORK / "LOOP.md").read_text()
        for word in ("BLOCKER", "WRONG", "FRICTION", "DRIVER REPORT"):
            self.assertIn(word, driver)
        self.assertIn("mock.argo.invalid", loop_doc)
        self.assertIn("round.py grade", loop_doc)
        self.assertRegex(loop_doc, r"(?i)snapshots the plugins",
                         "the refresh bottleneck is the thing an operator most needs to know")


if __name__ == "__main__":
    unittest.main()
