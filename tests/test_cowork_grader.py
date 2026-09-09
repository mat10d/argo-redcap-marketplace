"""The grader, driven by synthetic transcripts — no Cowork, no network.

A grader that can't be tested is a grader nobody trusts on a red day. These build a tiny
session transcript in Cowork's audit.jsonl shape and a tiny mock folder, and check that PASS
and FAIL come out where they should — above all that the two canaries fire.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COWORK = REPO / "testing/cowork"
sys.path.insert(0, str(COWORK))
sys.path.insert(0, str(REPO / "plugins/argo-core/skills/redcap-api/scripts"))

import round as loop  # noqa: E402
from argo_trackers import ARGO_REDCAP_URL, TOOLKIT_VERSION  # noqa: E402

FAKE_KEY = "A" * 32


def transcript(assistant_lines, user_lines, tool_results=(), driver_report=True):
    """Cowork's audit.jsonl: one JSON object per line."""
    rows = [{"type": "system", "subtype": "init", "plugins": []}]
    for text in tool_results:
        rows.append({"type": "user", "message": {"content": [{"type": "tool_result", "content": text}]}})
    for text in assistant_lines:
        rows.append({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    for text in user_lines:
        rows.append({"type": "user", "message": {"content": text}})
    if driver_report:
        rows.append({"type": "user", "message": {"content":
            "DRIVER REPORT\noutcome: DELIVERED\nproblems:\n  - none\nimprovisations:\n  - none\n"
            "would-a-real-user-notice: fine"}})
    rows.append({"type": "result", "num_turns": len(rows), "is_error": False})
    return "\n".join(json.dumps(r) for r in rows)


class GraderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.ws = root / "ws"; self.reports = root / "reports"
        self.mock = self.ws / loop.MOCK_DIRNAME
        (self.mock / "projects").mkdir(parents=True)
        (self.mock / "keys.json").write_text(json.dumps({FAKE_KEY: "study_tracker"}))
        (self.ws / "database-manager/weekly-check/2026-09-09").mkdir(parents=True)
        (self.ws / "database-manager/weekly-check/2026-09-09/summary.json").write_text("{}")
        self.session = root / "session"; self.session.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _calls(self, projects):
        with open(self.mock / "CALLS.jsonl", "w") as fh:
            for p in projects:
                fh.write(json.dumps({"ts": 0, "project": p, "content": "record", "is_write": False}) + "\n")

    def _run(self, text, rid="weekly-check"):
        audit = self.session / "audit.jsonl"
        audit.write_text(text)
        rc = loop.grade(rid, audit, workspace=self.ws, reports=self.reports)
        verdict = json.loads((self.reports / f"000-{rid}" / "verdict.json").read_text())
        return rc, verdict

    def _failed(self, verdict):
        return [c["label"] for c in verdict["checks"] if c["ok"] is False]

    def test_a_good_weekly_check_passes(self):
        self._calls(["study_tracker", "personnel_requests", "data_requests",
                     "data_linking_requests", "support_tickets"])
        rc, v = self._run(transcript(
            ["Here's where the portfolio stands: 10 open, 2 in production. Queues: one new build. "
             "Which one do you want to take first?"],
            ["The first open build request you listed."],
            tool_results=[f"ARGO toolkit {TOOLKIT_VERSION}"]))
        self.assertEqual(rc, 0, self._failed(v))
        self.assertTrue(v["pass"])
        self.assertEqual(v["version"], TOOLKIT_VERSION)

    def test_the_real_host_canary_fails_the_round(self):
        self._calls(["study_tracker", "personnel_requests", "data_requests",
                     "data_linking_requests", "support_tickets"])
        rc, v = self._run(transcript(
            ["10 open, 2 in production. Which one to take first?"], ["the first"],
            tool_results=[f"ARGO toolkit {TOOLKIT_VERSION}", f"POST {ARGO_REDCAP_URL}"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("REAL REDCAP ADDRESS" in f for f in self._failed(v)))

    def test_a_silent_mock_fails_a_round_that_touches_redcap(self):
        # no CALLS.jsonl at all
        rc, v = self._run(transcript(["10 open. Which one to take?"], ["first"],
                                     tool_results=[f"ARGO toolkit {TOOLKIT_VERSION}"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("MOCK WAS ACTIVE" in f for f in self._failed(v)))

    def test_a_leaked_synthetic_key_fails(self):
        self._calls(["study_tracker", "personnel_requests", "data_requests",
                     "data_linking_requests", "support_tickets"])
        rc, v = self._run(transcript([f"your key is {FAKE_KEY}, 10 open, which to take?"], ["first"],
                                     tool_results=[f"ARGO toolkit {TOOLKIT_VERSION}"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("leaked" in f for f in self._failed(v)))

    def test_forbidden_phrases_and_missing_stamp_and_report_fail(self):
        self._calls(["study_tracker", "personnel_requests", "data_requests",
                     "data_linking_requests", "support_tickets"])
        rc, v = self._run(transcript(
            ["Your access key is wrong. 10 open. Which one to take?"], ["first"],
            driver_report=False))
        failed = self._failed(v)
        self.assertTrue(any("never says" in f for f in failed))
        self.assertTrue(any("version stamp" in f for f in failed))
        self.assertTrue(any("driver report present" in f for f in failed))

    def test_an_unexpected_write_fails_and_an_allowed_one_passes(self):
        self._calls(["study_tracker"])
        with open(self.mock / "WRITES.jsonl", "w") as fh:
            fh.write(json.dumps({"ts": 0, "project": "study_tracker", "content": "record",
                                 "count": 1, "data": [{"record_id": "1", "project_created": "1"}]}) + "\n")
        # weekly-check allows no writes
        rc, v = self._run(transcript(["10 open, which to take?"], ["first"],
                                     tool_results=[f"ARGO toolkit {TOOLKIT_VERSION}"]))
        self.assertTrue(any("no writes reached the mock" in f for f in self._failed(v)))
        # mark-step allows exactly one to study_tracker
        rc, v = self._run(transcript(
            ["Writing to the Study Tracker (project 224): project_created for record 1. Go ahead? "
             "Done — record 1 is now 1/7."], ["Yes, go ahead."],
            tool_results=[f"ARGO toolkit {TOOLKIT_VERSION}"]), rid="mark-step")
        self.assertEqual(rc, 0, self._failed(v))


if __name__ == "__main__":
    unittest.main()
