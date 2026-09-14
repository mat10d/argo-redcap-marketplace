"""The session miner — it decides what gets read, so a bad filter costs real findings.

These drive it with synthetic transcripts in Cowork's audit.jsonl shape. The two that matter:
a skill's own SKILL.md arriving as a user turn must never be flagged (it matched four labels at
once on the first run), and the sentences that became NITS 78-86 must still be caught.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / ".claude/skills/mine-sessions"
sys.path.insert(0, str(SKILL))

import mine_sessions as miner  # noqa: E402


def session_file(root: Path, rows: list) -> Path:
    d = root / "1f7" / "cce" / "local_test000"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "audit.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return p


def user(text):
    return {"type": "user", "message": {"content": text}}


def assistant(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def tool_error(text):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True,
                                                     "content": text}]}}


class MinerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def mine(self, rows):
        s = miner.read_session(session_file(self.root, rows))
        return s, miner.candidates(s)

    # -- the real sentences ---------------------------------------------------------

    def test_it_catches_the_sentences_that_became_nits_78_86(self):
        """Every one of these is a verbatim turn from the Synoptic build."""
        real = [
            ("Hmmm, the final set of documents that get uploaded into the file repository aren't "
             "present, with accepted changes, in the right places", "MISSING"),
            # "isn't just a X" is the whole signal here — the real turn went on to say
            # "That's not in the 4/7", but the correction is complete before that clause.
            ("Survey mode isn't just a checkbox — 261 and 262 still need Project Setup", "CORRECTION"),
            ("Survey mode isn't just a checkbox — 261 and 262 still need Project Setup → "
             "\"Use surveys\" enabled, each instrument enabled as a survey, and survey settings "
             "written. That's not in the 4/7.", "CORRECTION"),
            ("Wait did you modify the proformas?", "CORRECTION"),
            ("Wait a second, per the SOP, a lot of these questions are already resolved.",
             "CORRECTION"),
            ("You can remove the MDC exempt tag... not sure what that is, that isn't relevant ever",
             "CONFUSED"),
            ("I don't understand 3 and 4", "CONFUSED"),
            ("Sorry--I don't understand... what documents exist for each of the 4 studies",
             "CONFUSED"),
        ]
        for text, want in real:
            _, (pushback, _) = self.mine([assistant("..."), user(text)])
            self.assertTrue(pushback, f"missed entirely: {text[:60]!r}")
            self.assertIn(want, pushback[0]["labels"], f"{text[:60]!r} -> {pushback[0]['labels']}")

    def test_a_stated_rule_and_a_repeat_are_caught(self):
        _, (pushback, _) = self.mine([user("come on, we can do better. we always name the "
                                           "biostatistician before circulating")])
        self.assertTrue({"REPEAT", "RULE"} & set(pushback[0]["labels"]))

    # -- the false positives that cost a run ---------------------------------------

    def test_a_skill_md_arriving_as_a_user_turn_is_never_flagged(self):
        """The loudest candidate on the first run was the toolkit quoting its own SKILL.md."""
        skill_text = ("Base directory for this skill: /var/folders/zr/x/plugin_01/skills/build-study\n\n"
                      "# build-study\n\nNever fabricate extra instruments. Don't stall on an "
                      "ambiguity. Stop at anything that is a judgement call. That's not how we "
                      "do it. I don't understand is not an option.\n")
        _, (pushback, _) = self.mine([user(skill_text)])
        self.assertEqual(pushback, [], "a skill's own doctrine is not a user complaint")

    def test_long_documentation_pasted_in_is_not_flagged(self):
        doc = "Some intro\n" + ("\n# Section\nWe always do it this way. Never the other.\n" * 60)
        self.assertGreater(len(doc), 2500)
        _, (pushback, _) = self.mine([user(doc)])
        self.assertEqual(pushback, [])

    def test_bare_acknowledgements_are_not_flagged(self):
        for word in ("no", "No.", "yes", "ok", "sure", "go ahead", "continue", "done"):
            _, (pushback, _) = self.mine([assistant("Shall I?"), user(word)])
            self.assertEqual(pushback, [], f"{word!r} is an answer, not push-back")

    def test_assistant_text_is_never_a_candidate(self):
        _, (pushback, _) = self.mine([assistant("Wait — actually I don't understand that; "
                                                "you should never do this again")])
        self.assertEqual(pushback, [], "only the user's words count as friction")

    # -- errors, versions, ARGO detection ------------------------------------------

    def test_toolkit_errors_are_separated_from_environmental_ones(self):
        _, (_, errors) = self.mine([
            tool_error("Traceback ... validate_dd.py line 40 KeyError"),
            tool_error("`/tmp/a.jpg` is outside this session's connected folders"),
        ])
        self.assertEqual([e["own"] for e in errors], [True, False])
        self.assertIn("TOOL-ERROR/ARGO", errors[0]["labels"])

    def test_argo_detection_and_version_stamp(self):
        s, _ = self.mine([user("hello"), assistant("hi")])
        self.assertFalse(s["argo"], "a chat that never ran the toolkit is not an ARGO session")
        s, _ = self.mine([user("run it"), tool_error("python3 sir_update.py failed"),
                          assistant("ARGO toolkit 0.24.0 loaded")])
        self.assertTrue(s["argo"])
        self.assertEqual(s["version"], "0.24.0")

    def test_cowork_echoed_user_turns_are_collapsed(self):
        """Cowork writes each user message twice; without deduping every finding appears twice."""
        text = "Wait did you modify the proformas?"
        s, (pushback, _) = self.mine([user(text), user(text), assistant("checking")])
        self.assertEqual(len(pushback), 1)

    def test_the_watermark_round_trips(self):
        original = miner.WATERMARK
        try:
            miner.WATERMARK = self.root / "mined.json"
            self.assertEqual(miner.load_watermark(), {})
            miner.save_watermark({"local_x": {"mined_at": "2026-09-14T10:00:00", "nits": "78-86"}})
            self.assertEqual(miner.load_watermark()["local_x"]["nits"], "78-86")
        finally:
            miner.WATERMARK = original


class SkillDocMatchesTheScript(unittest.TestCase):
    DOC = (SKILL / "SKILL.md").read_text()

    def test_every_label_the_script_emits_is_explained(self):
        for name, _ in miner.SIGNALS:
            self.assertIn(name, self.DOC, f"SKILL.md never mentions the {name} label")
        self.assertIn("TOOL-ERROR", self.DOC)

    def test_the_commands_in_the_doc_are_the_script_s_real_flags(self):
        for flag in ("--all", "--show", "--turn", "--context", "--mark", "--nits"):
            self.assertIn(flag, self.DOC, f"SKILL.md never shows {flag}")
            self.assertIn(flag, (SKILL / "mine_sessions.py").read_text())

    def test_it_says_candidates_are_not_findings(self):
        self.assertRegex(self.DOC, r"(?i)candidate, not a finding")
        self.assertRegex(self.DOC, r"(?i)version stamp",
                         "a finding on a stale version is not a finding")
        self.assertRegex(self.DOC, r"(?i)what went right",
                         "without this note a later pass 'fixes' the behaviour that worked")

    def test_it_warns_against_rebuilding_the_removed_loop(self):
        self.assertRegex(self.DOC, r"(?i)don'?t rebuild it")


if __name__ == "__main__":
    unittest.main()
