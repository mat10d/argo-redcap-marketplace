#!/usr/bin/env python3
"""Guards against documentation drifting away from the code it describes.

Every check here corresponds to a real drift found in the suite: a SKILL.md table that had
diverged from the Python it documented, and scripts that crashed instead of explaining themselves.
These are cheap to keep passing and expensive to notice by hand.

    python3 tests/test_docs_match_code.py
"""
from __future__ import annotations

import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGINS = REPO / "plugins"
os.environ.setdefault("ARGO_SETUP_NO_OPEN", "1")  # suites must not pop text editors
PORTFOLIO_DIR = PLUGINS / "argo-database-manager/skills/weekly-check"


def load_portfolio():
    os.environ.setdefault("ARGO_PM_ROOT", str(Path(os.environ.get("TMPDIR", "/tmp")) / "argo-test-pm"))
    spec = importlib.util.spec_from_file_location("portfolio_doc", PORTFOLIO_DIR / "portfolio.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPortfolioDocMatchesCode(unittest.TestCase):
    """The three drifts in finding #5, plus the build-step count drift found alongside them."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_portfolio()
        cls.doc = (PORTFOLIO_DIR / "SKILL.md").read_text()

    def test_every_tracker_in_the_code_is_documented(self):
        for env_var, *_ in self.mod.ADMIN_REDCAPS:
            self.assertIn(env_var, self.doc,
                          f"{env_var} is in ADMIN_REDCAPS but missing from SKILL.md")

    def test_the_doc_does_not_invent_trackers(self):
        known = {e for e, *_ in self.mod.ADMIN_REDCAPS}
        documented = set(re.findall(r"`([A-Z][A-Z_]{6,})`", self.doc))
        # Env vars that aren't tracker names are fine; only flag *_REQUEST/-ish tracker lookalikes.
        suspicious = {d for d in documented
                      if d.endswith(("_REQUEST", "_INITIATION")) and d not in known}
        self.assertFalse(suspicious, f"SKILL.md documents trackers the code doesn't have: {suspicious}")

    def test_done_marker_fields_match(self):
        for env_var, _label, _form, status_field, _done in self.mod.ADMIN_REDCAPS:
            row = [ln for ln in self.doc.splitlines() if f"`{env_var}`" in ln]
            self.assertTrue(row, f"no table row for {env_var}")
            self.assertIn(status_field, row[0],
                          f"SKILL.md's row for {env_var} doesn't name its real done-marker "
                          f"field {status_field!r}")

    def test_project_titles_match(self):
        for env_var, label, *_ in self.mod.ADMIN_REDCAPS:
            row = [ln for ln in self.doc.splitlines() if f"`{env_var}`" in ln]
            self.assertIn(label, row[0],
                          f"SKILL.md's row for {env_var} doesn't use the project title the code "
                          f"confirms against ({label!r})")

    def test_build_step_count_matches(self):
        n = len(self.mod.SIR_BUILD_STEPS)
        self.assertIn(f"/{n}", self.doc,
                      f"code counts {n} build steps; SKILL.md doesn't mention N/{n}")
        # The old, wrong count must not still be presented as current.
        self.assertNotIn("9 canonical build flags", self.doc)

    def test_snapshot_path_is_described_as_a_directory(self):
        # The code writes snapshot-<stamp>/summary.json, not a flat snapshot-<stamp>.json.
        self.assertIn("summary.json", self.doc,
                      "SKILL.md must document that a snapshot is a directory containing "
                      "summary.json, not a single flat file")


class TestScriptsSelfLoadTheSettingsFile(unittest.TestCase):
    """0.17.2 #24: portfolio.py read `REDCAP_URL` from os.environ AT IMPORT and never loaded
    the settings file, so the weekly check failed exactly as documented unless the user had
    sourced their settings by hand first — the one chore every other ARGO script does for them.

    Two rules, both mechanical:

    1. **Nothing reads REDCAP_URL at module level.** An import-time read happens before any
       script can load anything, so the value is whatever the shell happened to export. It also
       makes the variable untestable and unfixable: by the time `main()` runs it is already
       decided.
    2. **A script that reads REDCAP_URL calls `load_env_file` (or goes through
       `RedcapClient.from_env`, which calls it).** Reading the variable is what "talks to
       REDCap" means here; a script that mentions it only in a usage example or an error
       message isn't reading anything, so it isn't in scope.
    """

    # os.environ.get("REDCAP_URL") / os.environ["REDCAP_URL"] — in code, not in a docstring.
    READ = re.compile(r"""os\.environ(?:\.get\(|\[)\s*['"]REDCAP_URL['"]""")

    def scripts(self):
        for py in sorted(PLUGINS.rglob("*.py")):
            yield py, py.read_text()

    def test_no_script_reads_redcap_url_at_module_level(self):
        offenders = []
        for py, text in self.scripts():
            try:
                tree = ast.parse(text)
            except SyntaxError:                       # a broken file is another test's problem
                continue
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    continue                          # module docstring
                if self.READ.search(ast.unparse(node)):
                    offenders.append(f"{py.relative_to(REPO)}:{node.lineno}")
        self.assertFalse(
            offenders,
            "These read REDCAP_URL when the module is imported, before anything has had a "
            "chance to load the settings file. Read it inside main(), after calling "
            f"load_env_file(): {offenders}",
        )

    def test_every_script_that_reads_redcap_url_loads_the_settings_file(self):
        offenders = []
        for py, text in self.scripts():
            if not self.READ.search(text):
                continue
            if "load_env_file" in text or "from_env" in text:
                continue
            offenders.append(str(py.relative_to(REPO)))
        self.assertFalse(
            offenders,
            "These read REDCAP_URL but never load the ARGO settings file, so they only work for "
            "someone who sourced it by hand. Call load_env_file() (or use "
            f"RedcapClient.from_env): {offenders}",
        )

    def test_the_weekly_check_is_one_of_them(self):
        """Belt and braces: the script the finding was about, named."""
        text = (PORTFOLIO_DIR / "portfolio.py").read_text()
        self.assertIn("load_env_file", text)
        self.assertIn("REDCAP_URL = None", text,
                      "portfolio.py must declare REDCAP_URL empty and fill it in main()")


class TestWeeklyCheckSelfLoadsAndExplainsItself(unittest.TestCase):
    """The behaviour behind the guard above, driven end to end with no network.

    No tracker keys are configured, so every REDCap call is skipped before any socket is
    opened — the run reports five unreadable trackers and exits 1, which is exactly the shape
    needed to observe everything that happens BEFORE the fetch.
    """

    PORTFOLIO = PORTFOLIO_DIR / "portfolio.py"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = dict(os.environ)
        for var in list(self.env):
            if var.endswith(("_TOKEN", "_REQUEST", "_INITIATION")) or var == "REDCAP_URL":
                self.env.pop(var)
        self.env["ARGO_PM_ROOT"] = str(self.tmp / "database-manager")
        self.env["ARGO_SETUP_NO_OPEN"] = "1"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_portfolio(self, settings: str, *args):
        env_file = self.tmp / "argo.env"
        env_file.write_text(settings)
        env = dict(self.env, ARGO_ENV_FILE=str(env_file))
        return subprocess.run([sys.executable, str(self.PORTFOLIO), *args],
                              capture_output=True, text=True, timeout=120,
                              env=env, cwd=str(self.tmp))

    def test_the_address_is_read_from_the_settings_file_without_sourcing_it(self):
        proc = self.run_portfolio("REDCAP_URL=https://redcap.example.org/api/\n", "--diff")
        out = proc.stdout + proc.stderr
        self.assertNotIn("address isn't set", out,
                         "the settings file holds REDCAP_URL — it must be found and used")
        self.assertIn("COULD NOT READ ANY OF THE ARGO TRACKERS", out,
                      "it should get past the address check and fail on the missing keys")
        self.assertNotIn("Traceback", out)

    def test_a_missing_address_points_at_the_argo_settings_file(self):
        proc = self.run_portfolio("# nothing configured yet\n")
        out = proc.stdout + proc.stderr
        self.assertIn("address isn't set", out)
        self.assertIn("ARGO settings file", out)
        self.assertNotIn("~/.argo/.env", out,
                         "that path doesn't exist in Cowork — name the settings file instead")
        self.assertNotIn("set -a; source", out,
                         "the script loads the settings file itself; don't ask the user to")

    def test_a_first_diff_says_it_is_the_baseline(self):
        """0.17.2 #25: silence on the first --diff reads as 'nothing changed this week'."""
        proc = self.run_portfolio("REDCAP_URL=https://redcap.example.org/api/\n", "--diff")
        self.assertIn("First snapshot — nothing to compare against yet; next run will show "
                      "what changed.", proc.stdout)

    def test_a_run_without_diff_does_not_claim_to_be_a_baseline(self):
        proc = self.run_portfolio("REDCAP_URL=https://redcap.example.org/api/\n")
        self.assertNotIn("First snapshot", proc.stdout)


class TestWeeklyCheckQueuePresentationRules(unittest.TestCase):
    """0.19 #44: the queues came back as prose — empty ones got tables, open ones got collapsed
    into "the rest are untouched", and personnel requests arrived with no name on them.

    The rules are the deliverable here (a SKILL.md tells an agent how to present), so this
    guards that they are still stated, still specific, and still agree with what the script
    actually emits.
    """

    @classmethod
    def setUpClass(cls):
        cls.doc = (PORTFOLIO_DIR / "SKILL.md").read_text()
        cls.rules = cls.doc.split("### How to present the queues")[1].split("\n## ")[0]

    def test_the_rules_section_exists(self):
        self.assertIn("### How to present the queues", self.doc)

    def test_an_empty_queue_gets_one_line_and_no_table(self):
        self.assertIn("never a table", self.rules)
        self.assertIn("No data requests.", self.rules,
                      "show the one-line form, don't just describe it")

    def test_open_items_are_never_collapsed(self):
        self.assertIn("One record, one row", self.rules)
        for banned in ("Never collapse", "Never drop a row"):
            self.assertIn(banned, self.rules)

    def test_the_rows_are_an_inline_markdown_table(self):
        self.assertIn("inline markdown table", self.rules)
        self.assertIn("not a file", self.rules)

    def test_there_is_an_example_table(self):
        rows = [ln for ln in self.rules.splitlines() if ln.strip().startswith("|")]
        self.assertGreaterEqual(len(rows), 8, "the rules need a worked example, not just prose")
        self.assertTrue(any("| Record |" in ln for ln in rows),
                        "the example table must start from the record number")

    def test_the_builds_columns_are_named(self):
        for column in ("short name", "PI", "progress", "next step"):
            self.assertIn(column, self.rules, f"builds table is missing {column!r}")

    def test_the_people_columns_are_named(self):
        for column in ("first name", "last name", "email", "role"):
            self.assertIn(column, self.rules, f"people table is missing {column!r}")

    def test_the_people_columns_are_the_fields_the_script_emits(self):
        """The doc promises name and email; open_requests must actually put them on the line."""
        spec = importlib.util.spec_from_file_location(
            "open_requests_doc",
            PLUGINS / "argo-core/skills/redcap-api/scripts/open_requests.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(tuple(module.PERSON_FIELDS), ("first_name", "last_name", "email"))
        # The doc's people table also promises the role being asked for; the form lists that
        # AFTER the phone number, so it only reaches the line by being led with.
        self.assertIn("user_role", module.PEOPLE_LEAD_FIELDS)
        self.assertEqual(module.PEOPLE_LEAD_FIELDS,
                         module.PERSON_FIELDS + module.PERSON_ASK_FIELDS)
        # And the vendored copy the skill actually runs says the same thing.
        vendored = (PORTFOLIO_DIR / "scripts" / "open_requests.py").read_text()
        self.assertIn("PEOPLE_LEAD_FIELDS", vendored)

    def test_the_support_ticket_exception_is_stated_where_the_rules_are(self):
        """Rule 2 says never a count; the routing table says support tickets ARE a count."""
        self.assertIn("Support tickets are the one exception", self.rules)
        self.assertIn("count only", self.doc)


class TestStartHerePushesTheSettingsFile(unittest.TestCase):
    """0.19 #43: setup used to end by declaring itself done and ASKING whether they'd like to
    add keys. The completing act of setup is the file being on screen."""

    DOC = PLUGINS / "argo-core/skills/start-here/SKILL.md"

    @classmethod
    def setUpClass(cls):
        cls.doc = cls.DOC.read_text()
        # The doc is hard-wrapped at 98 columns, so every phrase check reads the unwrapped
        # text — otherwise a reflow breaks a test that has nothing to do with the wording.
        cls.flat = " ".join(cls.doc.replace("*", "").split())

    def test_it_no_longer_asks_permission_to_show_the_file(self):
        self.assertNotIn("Want me to put the file on screen", self.flat,
                         "the file goes on screen; the question is whether they've saved it")

    def test_the_file_is_presented_unprompted(self):
        self.assertIn("your next message is the file itself", self.flat)
        self.assertIn("Present it unprompted", self.flat)
        self.assertIn("present_files", self.flat, "the file card is still the first rung")

    def test_the_instruction_line_is_the_one_the_scaffold_prints(self):
        """Same words in the SKILL.md and in argo_setup.py, so the two don't drift apart."""
        phrase = "paste each key after its = sign, save"
        self.assertIn(phrase, self.flat.lower())
        setup = (PLUGINS / "argo-core/skills/redcap-api/scripts/argo_setup.py").read_text()
        self.assertIn(phrase, " ".join(setup.split()).lower())

    def test_declining_moves_on_without_nagging(self):
        self.assertIn('"later"', self.flat)
        self.assertIn("Don't raise it again this session", self.flat)
        self.assertIn("Nothing is blocked without keys", self.flat)

    def test_analysts_are_still_exempt_from_key_talk(self):
        self.assertIn("Data analysts are the exception", self.flat)


class TestNewStudyPipelineDocMatchesTheProcedure(unittest.TestCase):
    """new-study-documents is gate-first, and its gates are the programme's own procedure.

    The procedure lives once, in `references/study-launch-pipeline.md` (verified against the live
    File Repository). SKILL.md is what a session actually reads while working a gate, so the two
    drift silently and expensively: the version before this one told sessions to fill an
    `ARGO IPH Protocol Template.docx` that does not exist, and to refuse to draft the ICF, CPL,
    ECL and DTA that the procedure puts squarely in the PM's hands.

    So: every template the reference names must be named in SKILL.md, SKILL.md may not invent
    one, and each gate must still carry the checks and the known gaps it has to say out loud.
    """

    SKILL_DIR = PLUGINS / "argo-project-manager/skills/new-study-documents"
    REFERENCE = SKILL_DIR / "references/study-launch-pipeline.md"

    # A template filename as either document writes it — bounded by a backtick, a slash, a
    # newline or a bold marker, so `ARGO ICF Template/ARGO IPH Consent Form Template.doc` yields
    # the basename. `docx` must come before `doc` in the alternation, or every .docx truncates to
    # a .doc filename that exists nowhere.
    FILENAME = re.compile(r"[^`/\n*]+\.(?:docx|pptx|doc)\b")

    @staticmethod
    def flatten(text):
        """Both docs are hard-wrapped, so phrase checks read the unwrapped text."""
        return " ".join(text.replace("*", "").split())

    @classmethod
    def setUpClass(cls):
        cls.ref = cls.REFERENCE.read_text()
        cls.doc = (cls.SKILL_DIR / "SKILL.md").read_text()
        cls.flat = cls.flatten(cls.doc)
        cls.gate = {n: cls.flatten(cls.doc.split(f"## Gate {n} ", 1)[1].split("\n## ", 1)[0])
                    for n in (1, 2, 3)}

    def names(self, text):
        return {m.group(0).strip() for m in self.FILENAME.finditer(text)}

    def test_skill_names_every_template_the_procedure_names(self):
        missing = []
        for name in sorted(self.names(self.ref)):
            # The reference abbreviates the second checklist variant as "..._non-NIH Funded
            # Final.docx"; the ellipsis stands for the shared prefix, not for filename text.
            if name.lstrip(".") not in self.doc:
                missing.append(name)
        self.assertFalse(
            missing,
            "study-launch-pipeline.md names these templates and SKILL.md doesn't, so a session "
            f"working the gate has no filename to fetch or fill: {missing}")

    def test_the_skill_invents_no_template(self):
        """The drift that shipped: SKILL.md promised a protocol template that doesn't exist."""
        stray = [n for n in sorted(self.names(self.doc))
                 if "template" in n.lower() and n not in self.ref]
        self.assertFalse(
            stray,
            "SKILL.md names template files the procedure doesn't have — a session will hunt the "
            f"File Repository for something that isn't there: {stray}")
        self.assertNotIn("ARGO IPH Protocol Template", self.doc,
                         "there is no ARGO protocol template yet; that is Gate 1's stated gap")

    def test_the_first_move_is_the_gate_question(self):
        opener = self.flatten(self.doc.split("## Your first move", 1)[1].split("\n## ", 1)[0])
        self.assertIn("This is your whole first message", opener)
        self.assertIn("Where is the study right now?", opener)
        for option in ("directors just approved it", "stakeholder review / IRB",
                       "Ethical approval received"):
            self.assertIn(option, opener, f"the gate question is missing its {option!r} option")
        self.assertIn("Never dump all three gates at once", opener)
        self.assertIn("one task at a time", opener)

    def test_gate_1_says_the_protocol_template_gap_out_loud(self):
        self.assertIn("no protocol template yet", self.gate[1])
        self.assertIn("Never invent a house style", self.gate[1])
        self.assertRegex(self.gate[1], r"(?i)approved.{0,60}protocol",
                         "the fallback is drafting on an approved protocol the PM supplies")

    def test_gate_1_carries_both_consent_checks(self):
        self.assertIn("contact information", self.gate[1])
        self.assertRegex(self.gate[1], r"(?i)collaborating site")
        self.assertIn("shared with MSK for analysis", self.gate[1],
                      "the worked example of a collaborating site belongs in the check")
        self.assertRegex(self.gate[1], r"(?i)IRB template",
                         "the second check is that required IRB template language is intact")
        self.assertRegex(self.gate[1], r"(?i)never silently",
                         "removed IRB language is flagged for the site to fix, never patched here")

    def test_gate_2_says_the_oauthc_form_gap_out_loud(self):
        self.assertIn("no OAUTHC submission template", self.gate[2])
        self.assertIn("IPH HREC", self.gate[2], "the IPH HREC form is what actually exists")

    def test_gate_2_carries_the_dta_skip_rule(self):
        self.assertIn("Nigerian federal hospitals", self.gate[2])
        self.assertRegex(self.gate[2], r"(?i)no DTA/MTA is required")
        self.assertIn("which rule fired", self.gate[2],
                      "applying the rule silently is the failure mode; it must be said")
        self.assertIn("Never skip silently", self.gate[2])

    def test_gate_3_checks_every_site_before_anything_else(self):
        self.assertRegex(self.gate[3], r"(?i)every.{0,30}participating site")
        self.assertIn("ethical clearance", self.gate[3])

    def test_gate_3_names_the_two_study_start_up_sops(self):
        self.assertIn("Study Start-Up", self.gate[3])
        self.assertIn("NIH-funded", self.gate[3])
        self.assertIn("non-NIH", self.gate[3])
        self.assertRegex(self.gate[3], r"(?i)how the study is funded",
                         "funding is what picks the SOP and the checklist variant")

    def test_gate_3_says_the_unfillable_templates_out_loud(self):
        self.assertIn("flattened image", self.gate[3])
        self.assertRegex(self.gate[3], r"(?i)pptx skill",
                         "the SIV deck is PowerPoint: use a pptx skill or hand the content over")
        self.assertRegex(self.gate[3], r"(?i)slide content as text")

    def test_gate_3_ends_at_the_redcap_build_request(self):
        self.assertIn("SIR survey", self.gate[3])
        self.assertIn("with every document above attached", self.gate[3])
        self.assertIn("[[build-study]]", self.gate[3], "the hand-off names where it hands off to")
        self.assertLess(self.gate[3].index("Say these out loud"),
                        self.gate[3].index("Where the pipeline ends"),
                        "the build request is the end of the pipeline, so it comes last")

    def test_the_pm_submits_the_request_not_this_skill(self):
        self.assertRegex(self.flat, r"(?i)PM submits the SIR survey")
        self.assertRegex(self.flat, r"(?i)Don't submit it for them")

    def test_the_template_fetch_ladder_survives(self):
        ladder = self.flatten(self.doc.split("## The official Word templates", 1)[1]
                                      .split("\n## ", 1)[0])
        self.assertIn("project-manager/templates-official", ladder)
        self.assertIn("fetch_templates.py --to", ladder)
        self.assertRegex(ladder, r"(?i)markdown skeletons")
        self.assertIn("Tell the user which path you took", ladder)
        self.assertIn("Never commit or publish them", ladder)

    def test_the_ladder_promises_what_the_fetcher_actually_downloads(self):
        """The fetch reaches past ARGO Templates for the QA plan and the Study Start-Up SOPs."""
        code = (self.SKILL_DIR / "fetch_templates.py").read_text()
        for folder in ("ARGO Templates", "ARGO Quality Assurance (QA)",
                       "ARGO Standard Operating Procedures (SOPs)", "Study Start-Up"):
            self.assertIn(folder, code,
                          f"fetch_templates.py must fetch {folder!r} — the pipeline needs it")
        ladder = self.doc.split("## The official Word templates", 1)[1].split("\n## ", 1)[0]
        self.assertRegex(self.flatten(ladder), r"(?i)QA plan and the two Study Start-Up SOPs",
                         "the ladder must say what one fetch brings back")

    def test_outputs_are_moniker_named_in_one_folder_per_study(self):
        self.assertIn("project-manager/new-studies/<study>/", self.flat)
        self.assertIn("study moniker", self.flat)
        self.assertIn("STUDY_PROFILE.md", self.flat)

    def test_it_mines_before_it_asks_and_never_invents(self):
        self.assertRegex(self.flat, r"(?i)never re-ask what the documents already answer")
        self.assertRegex(self.flat, r"(?i)\[TODO")
        self.assertRegex(self.flat, r"(?i)never.{0,20}invent regulatory facts")

    def test_the_retired_refusal_is_gone(self):
        """The old skill refused to touch ICF/CPL/ECL/DTA; the procedure assigns them to the PM."""
        self.assertNotIn("are NOT generated here", self.doc)
        for owned in ("ARGO IPH Consent Form Template.doc",
                      "ARGO Consenting Professional List (CPL) Template.docx",
                      "ARGO Eligibility Checklist (ECL) Template.docx"):
            self.assertIn(owned, self.doc)

    def test_start_here_lands_the_pm_on_the_gate_question(self):
        landing = (PLUGINS / "argo-core/skills/start-here/SKILL.md").read_text()
        section = self.flatten(landing.split("### Project manager", 1)[1].split("\n### ", 1)[0])
        self.assertIn("[[new-study-documents]]", section)
        for option in ("directors just approved", "IRB", "ethical approval received"):
            self.assertRegex(section, f"(?i){re.escape(option)}",
                             f"the PM landing must ask the gate question ({option})")
        row = [ln for ln in landing.splitlines()
               if ln.startswith("| `project-manager`")]
        self.assertTrue(row, "start-here has no project-manager greeting row")
        self.assertRegex(row[0], r"(?i)ethical approval",
                         "the greeting row asks the same gate question the skill opens with")


class TestQaWorklistsDocMatchesCode(unittest.TestCase):
    """The three qa-worklists doc gaps the Tier 1.5 walkthroughs found (0.17.2 #28/#30/#31).

    Each of them is a question the skill left a live session to answer on its own — which
    variant to send, whether to source a settings file, when a round is finished — and each
    time it answered differently.
    """

    SKILL = PLUGINS / "argo-qa-specialist/skills/qa-worklists"
    DOC = (SKILL / "SKILL.md").read_text()

    def test_it_says_which_variant_the_ras_get(self):
        """#28: the builder writes with_MDC/ and no_MDC/ and the doc never said which to send."""
        hand_over = self.DOC.split("### Hand it to the RAs", 1)[1].split("\n## ", 1)[0]
        self.assertIn("with_MDC", hand_over)
        self.assertIn("no_MDC", hand_over)
        self.assertRegex(hand_over, r"(?s)with_MDC.{0,400}default|default.{0,400}with_MDC")
        self.assertIn("QA specialist", hand_over,
                      "no_MDC is a decision someone makes, and the doc must say whose")

    def test_the_run_block_does_not_ask_the_user_to_source_anything(self):
        """#30: the scripts self-load; telling the user to source is both noise and, in Cowork,
        an instruction they cannot follow (there is no ~/.argo/.env there)."""
        self.assertNotIn("set -a; source", self.DOC)
        self.assertNotIn("~/.argo/.env", self.DOC)
        for script in ("build_worklists.py", "summarize_for_ra.py"):
            self.assertIn("load_env_file", (self.SKILL / script).read_text(),
                          f"the doc stops telling people to source, so {script} must self-load")

    def test_the_amber_prerequisite_wording_is_the_one_the_code_writes(self):
        """#30: the header row said 'only if <unreadable expression>'."""
        self.assertIn("couldn't read this condition", self.DOC)
        code = (self.SKILL / "build_worklists.py").read_text()
        self.assertIn('"couldn\'t read this condition: "', code,
                      "SKILL.md and build_worklists.py must use the same words")

    def test_task_2_defines_where_to_stop_without_a_post_ra_export(self):
        """#31: 'confirm the gaps closed' and VERIFY both assume a fresh export exists."""
        task2 = self.DOC.split("## Task 2", 1)[1]
        self.assertIn("no post-ra export", task2.lower())
        self.assertIn("fresh export", task2)
        self.assertIn("closes on the next pull", task2)


class TestBuildStudyPromisedDeliverables(unittest.TestCase):
    """NITS 47 + 48 (0.19): the build's document handling.

    47 — the documents attached to the request get ported into the build folder as the first act
    after triage, before any analysis. 48 — the one QUESTIONNAIRE_CHANGELOG.md deliverable split
    in two BY KIND: assumptions the build made go in `OPEN_QUESTIONS.md` as questions; changes the
    questionnaire itself needs come back as the original document with tracked changes. Typos and
    numbering quirks appear in neither. These guards exist because SKILL.md and the brief generator
    each promise deliverables by name to a live session, and a stray old name sends it to write a
    file nothing else in the pipeline knows about.
    """

    SKILL_DIR = PLUGINS / "argo-database-manager/skills/build-study"
    DOC = (SKILL_DIR / "SKILL.md").read_text()
    BRIEF_CODE = (SKILL_DIR / "setup_brief.py").read_text()
    RETIRED = "QUESTIONNAIRE_CHANGELOG"

    def test_the_retired_changelog_name_is_gone_everywhere(self):
        self.assertNotIn(self.RETIRED, self.DOC)
        self.assertNotIn(self.RETIRED, self.BRIEF_CODE)

    def test_both_deliverables_are_named_in_the_skill(self):
        for name in ("OPEN_QUESTIONS.md", "_redcap_changes.docx", "_redcap_changes.md"):
            self.assertIn(name, self.DOC, f"SKILL.md must name the {name} deliverable")

    def test_the_skill_and_the_brief_promise_the_same_deliverables(self):
        """Both are read by the same session; they cannot name different files."""
        for name in ("OPEN_QUESTIONS.md", "_redcap_changes.docx", "_redcap_changes.md"):
            self.assertIn(name, self.BRIEF_CODE,
                          f"setup_brief.py's deliverables list must name {name} too")

    def test_the_handoff_list_names_both_deliverables(self):
        """The 'self-contained for handoff' list is what a session checks itself against."""
        handoff = self.DOC.split("self-contained for handoff", 1)[1].split("\n## ", 1)[0]
        self.assertIn("OPEN_QUESTIONS.md", handoff)
        self.assertIn("_redcap_changes", handoff)

    def test_the_changes_deliverable_says_tracked_changes_on_the_original(self):
        """A rewritten-from-scratch questionnaire is not a review vehicle; the point is redlines
        the questionnaire's owner can accept or reject in their own document."""
        section = self.DOC.split("### Changes the QUESTIONNAIRE itself needs", 1)[1] \
                          .split("\n**Path A workflow", 1)[0]
        self.assertIn("tracked changes", section.lower())
        self.assertIn("docx skill", section.lower(),
                      "the doc must point at the skill that can actually write tracked changes")
        self.assertRegex(section, r"(?i)pdf")

    def test_the_build_always_makes_headway(self):
        """The decided design: never stall on an ambiguity — best guess in the DD, question out."""
        section = self.DOC.split("### The build always makes headway", 1)[1] \
                          .split("\n> ### ", 1)[0]
        self.assertIn("best guess", section.lower())
        self.assertIn("OPEN_QUESTIONS.md", section)

    def test_cosmetic_quirks_go_in_neither_deliverable(self):
        """The IRB minimal-change rule survives the split — and must not read as contradicting it:
        the mirror-it block has to say those quirks reach neither deliverable."""
        mirror = self.DOC.split("### The questionnaire is IRB-approved", 1)[1] \
                         .split("\n> ### ", 1)[0]
        self.assertIn("neither", mirror.lower())
        self.assertRegex(mirror, r"(?i)numbering")

    def test_open_questions_are_questions_not_edits(self):
        self.assertRegex(self.DOC, r"(?i)never proposed edits to the form")

    def test_documents_are_ported_before_any_analysis(self):
        """NITS 47: a numbered first step — make the folder, pull the documents in, read them."""
        self.assertIn("## Step 1b", self.DOC, "the porting step needs its own numbered step")
        step = self.DOC.split("## Step 1b", 1)[1].split("\n## ", 1)[0]
        self.assertIn("mkdir -p", step, "it has to say how to make the folder")
        self.assertIn("questionnaires", step)
        for order in ("1. **Make the folder", "2. **Pull the documents in", "3. **Then read them"):
            self.assertIn(order, step, f"the step is ordered; missing: {order}")
        # and it is placed before the create-project step, not after the DD is designed
        self.assertLess(self.DOC.index("## Step 1b"), self.DOC.index("## Step 2 —"))
        self.assertLess(self.DOC.index("## Step 1b"), self.DOC.index("## Step 3 —"))

    def test_the_pipeline_table_carries_the_porting_step(self):
        row = [ln for ln in self.DOC.splitlines() if ln.startswith("| 1b ")]
        self.assertTrue(row, "the pipeline table must show the document-porting step")
        self.assertIn("no flag", row[0], "porting is not a build_tracking flag")


class TestNoBracketEnvAccess(unittest.TestCase):
    """Finding #1: os.environ['X'] raises a bare KeyError instead of explaining itself."""

    # os.environ["X"] = value is an assignment and can't raise KeyError — only reads are a problem.
    READ = re.compile(r"os\.environ\[[^\]]+\]\s*(?!=[^=])")
    ASSIGNMENT = re.compile(r"os\.environ\[[^\]]+\]\s*=[^=]")

    def test_no_script_uses_bracket_env_access(self):
        offenders = []
        for py in PLUGINS.rglob("*.py"):
            for i, line in enumerate(py.read_text().splitlines(), 1):
                if self.READ.search(line) and not self.ASSIGNMENT.search(line):
                    offenders.append(f"{py.relative_to(REPO)}:{i}")
        self.assertFalse(
            offenders,
            "These read environment variables with [], which crashes with a bare KeyError "
            "instead of a message the user can act on. Use os.environ.get() or "
            f"RedcapClient.from_env(): {offenders}",
        )


class TestHeadlessSafe(unittest.TestCase):
    """Nothing may block on typed input where there's no keyboard.

    These scripts run in agent sessions, scheduled jobs and cloud runners as well as terminals.
    A bare input() there waits forever, which looks like a hang with no explanation.
    """

    def test_every_input_call_is_guarded_by_a_tty_check(self):
        unguarded = []
        for py in PLUGINS.rglob("*.py"):
            text = py.read_text()
            if not re.search(r"(?<![\w.])input\s*\(", text):
                continue
            if "isatty" not in text:
                unguarded.append(str(py.relative_to(REPO)))
        self.assertFalse(
            unguarded,
            "These prompt for typed input without checking a keyboard is attached, so they hang "
            f"forever in a headless run: {unguarded}",
        )

    def test_no_script_globs_plugin_roots_anymore(self):
        """Cross-plugin discovery is retired: every skill vendors its own scripts/ copy.

        Four separate locator bugs (directory-name globbing, lexical version sort, the
        /mnt/skills layout, the ~/mnt layout) came from scripts hunting for argo-core across
        environments. Imports are now same-folder. The shared client's find_argo_core keeps a
        roots list for standalone --check use; no other script may grow one back.
        """
        for py in PLUGINS.rglob("*.py"):
            if py.parent.name == "scripts":
                continue  # vendored copies of the client itself
            text = py.read_text()
            self.assertNotIn("/mnt/.remote-plugins", text,
                             f"{py.relative_to(REPO)} greps plugin roots — import from the "
                             "skill's vendored scripts/ folder instead")
            self.assertNotIn("hits[-1]", text,
                             f"{py.relative_to(REPO)} picks glob hits by name order")

    def test_no_relative_cross_plugin_paths_in_docs(self):
        """Plugins install into separate versioned dirs — '../other-plugin' never resolves."""
        offenders = []
        for md in PLUGINS.rglob("*.md"):
            for i, line in enumerate(md.read_text().splitlines(), 1):
                if "CLAUDE_PLUGIN_ROOT}/.." in line:
                    offenders.append(f"{md.relative_to(REPO)}:{i}")
        self.assertFalse(
            offenders,
            "A path like ${CLAUDE_PLUGIN_ROOT}/../argo-core resolves inside the current plugin's "
            f"own directory, not next to it, so it never exists: {offenders}",
        )


class TestVersionsAreInStep(unittest.TestCase):
    """All five plugins and the marketplace share one version — they release as one unit.

    argo-core ships the shared REDCap client that every role plugin vendors, so a mix of old and
    new plugins isn't a supported combination. Separate numbers would imply an independence that
    doesn't exist. Bumping everything each release also guarantees update-detection fires, which
    keys off the version field.
    """

    SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

    def versions(self):
        import json
        found = {}
        for manifest in sorted(REPO.glob("plugins/*/.claude-plugin/plugin.json")):
            found[manifest.parents[1].name] = json.loads(manifest.read_text()).get("version")
        found["(marketplace)"] = json.loads(
            (REPO / ".claude-plugin" / "marketplace.json").read_text())["metadata"].get("version")
        return found

    def test_every_version_matches(self):
        found = self.versions()
        distinct = set(found.values())
        self.assertEqual(
            len(distinct), 1,
            "Plugin versions have drifted apart. They ship as one unit — run "
            f"`python3 release.py --set <version>`. Found: {found}",
        )

    def test_marketplace_descriptions_mirror_plugin_json(self):
        """The marketplace's per-plugin descriptions are a copy of each plugin.json's
        description, synced by release.py — a hand-edited third copy would silently drift."""
        import json
        plugin_desc = {}
        for manifest in sorted(REPO.glob("plugins/*/.claude-plugin/plugin.json")):
            data = json.loads(manifest.read_text())
            plugin_desc[data.get("name", manifest.parents[1].name)] = data.get("description", "")
        market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
        for entry in market.get("plugins", []):
            name = entry.get("name")
            if name in plugin_desc:
                self.assertEqual(
                    entry.get("description", ""), plugin_desc[name],
                    f"marketplace.json's description for {name} drifted from its plugin.json — "
                    "edit plugin.json and run release.py; never hand-edit marketplace.json")

    def test_runtime_stamp_matches(self):
        import re as _re
        trackers = (REPO / "plugins/argo-core/skills/redcap-api/scripts/argo_trackers.py").read_text()
        stamp = _re.search(r'TOOLKIT_VERSION = "([^"]+)"', trackers).group(1)
        marketplace = self.versions()["(marketplace)"]
        self.assertEqual(stamp, marketplace,
                         "argo_trackers.TOOLKIT_VERSION drifted from the release version — "
                         "release.py stamps it; don't edit by hand")

    def test_versions_are_plain_semver(self):
        for name, version in self.versions().items():
            self.assertIsNotNone(version, f"{name} has no version")
            self.assertRegex(str(version), self.SEMVER,
                             f"{name}'s version {version!r} isn't a plain X.Y.Z number")

    def test_every_plugin_is_listed_in_the_marketplace(self):
        import json
        listed = {p["name"] for p in json.loads(
            (REPO / ".claude-plugin" / "marketplace.json").read_text())["plugins"]}
        on_disk = {p.parents[1].name for p in REPO.glob("plugins/*/.claude-plugin/plugin.json")}
        self.assertEqual(listed, on_disk,
                         "the marketplace listing and the plugins on disk disagree")


class TestEverythingShipsInsideASkill(unittest.TestCase):
    """No plugin asset may live outside a skills/<name>/ folder.

    Chat-surface distribution mounts each SKILL folder, not the plugin root. scripts/ and
    references/ used to sit at argo-core's root — so a chat session received bare SKILL.mds
    with no executable layer and no reference docs, while everything worked locally. Anything
    a skill needs must live inside the skill folder to travel.
    """

    ALLOWED_AT_ROOT = {"plugin.json"}  # .claude-plugin/plugin.json is plugin metadata

    def test_no_scripts_or_references_outside_skills(self):
        offenders = []
        for plugin in sorted(PLUGINS.iterdir()):
            if not plugin.is_dir():
                continue
            for path in plugin.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(plugin)
                if rel.parts[0] in ("skills", ".claude-plugin"):
                    continue
                offenders.append(str(path.relative_to(REPO)))
        self.assertFalse(
            offenders,
            "These files sit outside every skills/<name>/ folder, so chat-surface installs "
            f"will not include them: {offenders}",
        )


class TestStandaloneBundleInSync(unittest.TestCase):
    """Every skill's vendored scripts/ must be byte-identical to argo-core's source.

    Vendored copies are what killed cross-plugin discovery (each skill is self-contained), and
    many copies is normally the disease this repo kills on sight — so it's mechanised instead:
    release.py syncs every target on every release, and this test fails the moment any differs.
    """

    SOURCE = REPO / "plugins/argo-core/skills/redcap-api/scripts"

    def test_every_vendored_copy_matches_source_exactly(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("release_mod", REPO / "release.py")
        release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)
        src = {p.name: p.read_bytes() for p in self.SOURCE.glob("*.py")}
        self.assertTrue(src, "argo-core has no shared scripts?")
        for target in release.VENDOR_TARGETS:
            self.assertTrue(target.is_dir(), f"{target} missing — run release.py")
            dst = {p.name: p.read_bytes() for p in target.glob("*.py")}
            self.assertEqual(sorted(src), sorted(dst),
                             f"{target.relative_to(REPO)} has different files than argo-core — "
                             "run `python3 release.py --bump patch` to re-sync")
            for name in src:
                self.assertEqual(src[name], dst[name],
                                 f"{target.relative_to(REPO)}/{name} differs from argo-core — "
                                 "run `python3 release.py --bump patch` to re-sync")


class TestWikilinksResolve(unittest.TestCase):
    """Every [[name]] link must point at a real skill or reference doc.

    The start-here front door is almost entirely links — a dangling one sends a brand-new user
    to a skill that doesn't exist, which is the worst possible first experience. Applies
    repo-wide: a rename that orphans links elsewhere fails here too.
    """

    def test_every_wikilink_has_a_target(self):
        targets = set()
        for path in PLUGINS.rglob("*"):
            if path.is_dir() and path.parent.name == "skills":
                targets.add(path.name)
            if path.suffix == ".md" and path.parent.name == "references":
                targets.add(path.stem)
        dangling = []
        for md in PLUGINS.rglob("*.md"):
            for link in re.findall(r"\[\[([a-z0-9-]+)\]\]", md.read_text()):
                if link not in targets:
                    dangling.append(f"{md.relative_to(REPO)} -> [[{link}]]")
        self.assertFalse(dangling,
                         f"These links point at skills or reference docs that don't exist: {dangling}")


class TestSetupIsSafe(unittest.TestCase):
    """argo_setup.py creates folders — so it must never do that just for being run."""

    SETUP = PLUGINS / "argo-core/skills/redcap-api/scripts/argo_setup.py"

    def test_no_args_creates_nothing(self):
        import tempfile
        home = tempfile.mkdtemp()
        env = dict(os.environ, HOME=home)
        before = set(os.listdir(home))
        proc = subprocess.run([sys.executable, str(self.SETUP)],
                              capture_output=True, text=True, timeout=60, env=env)
        after = set(os.listdir(home))
        self.assertEqual(before, after,
                         "running argo_setup.py with no arguments created something")
        self.assertIn("Nothing has been created yet", proc.stdout)

    def test_setup_writes_a_private_env_file(self):
        import tempfile
        work = Path(tempfile.mkdtemp()) / "argo-work"
        subprocess.run([sys.executable, str(self.SETUP), "--dir", str(work)],
                       capture_output=True, text=True, timeout=60)
        env_file = work / ".env"
        self.assertTrue(env_file.exists(), "no .env was created")
        self.assertEqual(oct(env_file.stat().st_mode & 0o777)[2:], "600",
                         "the settings file must be readable only by its owner")
        self.assertIn(".env", (work / ".gitignore").read_text(),
                      "the settings file must be git-ignored so keys can't be committed")
        for sub in ("project-manager", "qa-specialist", "database-manager", "data-analyst"):
            self.assertTrue((work / sub).is_dir(), f"workspace is missing {sub}/")

    def test_setup_never_overwrites_existing_keys(self):
        import tempfile
        work = Path(tempfile.mkdtemp()) / "argo-work"
        subprocess.run([sys.executable, str(self.SETUP), "--dir", str(work)],
                       capture_output=True, timeout=60)
        env_file = work / ".env"
        env_file.write_text(env_file.read_text().replace("DATA_REQUEST=", "DATA_REQUEST=keepme"))
        subprocess.run([sys.executable, str(self.SETUP), "--dir", str(work)],
                       capture_output=True, timeout=60)
        self.assertIn("DATA_REQUEST=keepme", env_file.read_text(),
                      "re-running setup destroyed a key the user had filled in")

    def test_returning_user_in_local_agent_mode_is_recognised(self):
        """Round 7's bug: a staged .env in a ~/mnt connected folder got the FIRST-TIME banner."""
        import tempfile
        home = Path(tempfile.mkdtemp())
        (home / "mnt" / "ARGO-work").mkdir(parents=True)
        (home / "mnt" / "ARGO-work" / ".env").write_text("REDCAP_URL=https://x.org/api/\n")
        proc = subprocess.run([sys.executable, str(self.SETUP), "--ensure"],
                              capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, HOME=str(home), ARGO_SETUP_NO_OPEN="1"),
                              cwd=str(home))
        self.assertIn("setup skipped", proc.stdout,
                      "a settings file in a local-agent-mode mount must be recognised")
        self.assertNotIn("FIRST-TIME", proc.stdout)

    def test_setup_has_no_private_search_list(self):
        """The search list lives once, in the client. Setup must delegate, never copy."""
        text = (PLUGINS / "argo-core/skills/redcap-api/scripts/argo_setup.py").read_text()
        self.assertIn("settings_candidates", text)
        self.assertNotIn('candidates.append(Path.home() / ".argo" / ".env")', text,
                         "argo_setup grew its own copy of the search paths again")

    def test_ensure_skips_when_settings_exist(self):
        import tempfile
        home = Path(tempfile.mkdtemp())
        (home / ".argo").mkdir()
        (home / ".argo" / ".env").write_text("REDCAP_URL=https://x.org/api/\n")
        proc = subprocess.run([sys.executable, str(self.SETUP), "--ensure"],
                              capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, HOME=str(home)), cwd=str(home))
        self.assertIn("setup skipped", proc.stdout)
        self.assertFalse((home / "argo-work").exists(),
                         "--ensure must not scaffold when settings already exist")

    def test_ensure_scaffolds_loudly_when_nothing_exists(self):
        import tempfile
        home = Path(tempfile.mkdtemp())
        env = dict(os.environ, HOME=str(home))
        env.pop("ARGO_ENV_FILE", None)
        proc = subprocess.run([sys.executable, str(self.SETUP), "--ensure"],
                              capture_output=True, text=True, timeout=60,
                              env=env, cwd=str(home))
        self.assertIn("FIRST-TIME SETUP", proc.stdout, "the scaffold must announce itself loudly")
        env_file = home / "argo-work" / ".env"
        self.assertTrue(env_file.exists(), "--ensure must create the settings file")
        self.assertEqual(oct(env_file.stat().st_mode & 0o777)[2:], "600")
        # And running it again must now skip.
        proc2 = subprocess.run([sys.executable, str(self.SETUP), "--ensure"],
                               capture_output=True, text=True, timeout=60,
                               env=env, cwd=str(home))
        self.assertIn("setup skipped", proc2.stdout)

    def test_ensure_survives_an_unwritable_home(self):
        proc = subprocess.run([sys.executable, str(self.SETUP), "--ensure"],
                              capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, HOME="/nonexistent-home"), cwd="/tmp")
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_connected_workspace_detection(self):
        """Cowork rule: setup lands in the user's connected folder, and never guesses."""
        import importlib.util, tempfile
        spec = importlib.util.spec_from_file_location("argo_setup_ws", self.SETUP)
        s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
        base = Path(tempfile.mkdtemp())
        (base / "skills").mkdir()          # system mount — always ignored
        # ARGO-named folder wins outright.
        (base / "My ARGO Files").mkdir()
        self.assertEqual(s.find_connected_workspace(base), base / "My ARGO Files")
        # A lone generic folder gets an argo-work subfolder.
        import shutil; shutil.rmtree(base / "My ARGO Files")
        (base / "projects").mkdir()
        self.assertEqual(s.find_connected_workspace(base), base / "projects" / "argo-work")
        # Two unrelated folders: refuse to guess.
        (base / "photos").mkdir()
        self.assertIsNone(s.find_connected_workspace(base))

    def test_client_searches_the_scaffolded_locations(self):
        """The file --ensure creates must be findable by the client — this was a real gap."""
        client_text = (PLUGINS / "argo-core/skills/redcap-api/scripts/argo_redcap_client.py").read_text()
        self.assertIn('"argo-work" / ".env"', client_text,
                      "load_env_file must search argo-work/.env under home and connected folders")

    def test_template_never_asks_for_a_token_on_the_command_line(self):
        text = self.SETUP.read_text()
        self.assertNotIn('"--token"', text)
        self.assertNotIn("'--token'", text)
        self.assertIn("never pass one on the command line", text.lower().replace("**", ""))


class TestScriptsDegradeGracefully(unittest.TestCase):
    """Finding #3's smoke test: no script may traceback when run with no arguments."""

    SKIP = {"__init__.py"}

    def test_no_args_never_tracebacks(self):
        env = dict(os.environ)
        # Simulate a machine with nothing configured — the hardest case.
        for var in list(env):
            if var.endswith(("_TOKEN", "_REQUEST", "_INITIATION")) or var == "REDCAP_URL":
                env.pop(var)
        env["ARGO_PM_ROOT"] = str(Path(os.environ.get("TMPDIR", "/tmp")) / "argo-test-pm")

        failures = []
        for py in sorted(PLUGINS.rglob("*.py")):
            if py.name in self.SKIP:
                continue
            proc = subprocess.run(
                [sys.executable, str(py)],
                capture_output=True, text=True, timeout=60, env=env, cwd=str(REPO),
            )
            combined = proc.stdout + proc.stderr
            if "Traceback (most recent call last)" in combined:
                last = combined.strip().splitlines()[-1]
                failures.append(f"{py.relative_to(REPO)} → {last}")

        self.assertFalse(
            failures,
            "Run with no arguments and nothing configured, these crashed with a raw traceback "
            f"instead of explaining what was missing:\n  " + "\n  ".join(failures),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
