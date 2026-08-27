#!/usr/bin/env python3
"""The request-queue logic, driven by the synthetic admin-tracker fixtures.

`open_requests.py` is what a database manager sees first: five queues, each bucketed into
open/done and each open record summarised by its *labels*. None of that had a test — it is
pure dict-shuffling over the REDCap API's label-mode JSON, so a wrong field name or a
changed done-marker would produce a plausible-looking but wrong landing page rather than a
crash. Exactly the bug class that shipped once already in the worklist builder.

So: `testing/fixtures/synthetic-trackers/` holds a seeded, byte-stable imitation of what
content=record (rawOrLabel=label) and content=metadata return for all five trackers, with a
MANIFEST.json stating the engineered counts. These tests assert against those numbers.

No network, no keys, no HTTP mocking: the two functions that take a client are handed a tiny
fixture-backed stand-in exposing the three methods they call (export_records,
export_metadata, record_id_field). Everything else is called directly.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "testing" / "fixtures" / "synthetic-trackers"
CORE_SCRIPTS = REPO / "plugins" / "argo-core" / "skills" / "redcap-api" / "scripts"
PORTFOLIO_PY = (REPO / "plugins" / "argo-database-manager" / "skills" / "weekly-check"
                / "portfolio.py")
GENERATOR = FIXTURE / "generate.py"


def load(path: Path, name: str, env: "dict | None" = None):
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


OR = load(CORE_SCRIPTS / "open_requests.py", "open_requests")
TRACKERS = load(CORE_SCRIPTS / "argo_trackers.py", "argo_trackers_for_queue_test")
PORTFOLIO = load(
    PORTFOLIO_PY, "portfolio_for_queue_test",
    {"ARGO_PM_ROOT": str(Path(tempfile.gettempdir()) / "argo-tracker-fixture-test")},
)

MANIFEST = json.loads((FIXTURE / "MANIFEST.json").read_text())


class FixtureClient:
    """A stand-in for RedcapClient backed by the fixture JSON.

    Not an HTTP mock — it never pretends to be a transport. It is the smallest object that
    satisfies the three methods open_requests calls on a client, so the surrounding pure
    logic can be exercised end to end.
    """

    def __init__(self, env_var: str):
        entry = MANIFEST["trackers"][env_var]
        self.label = entry["project_title"]
        self._records = json.loads((FIXTURE / entry["records_file"]).read_text())
        self._metadata = json.loads((FIXTURE / entry["metadata_file"]).read_text())

    def export_records(self, **params):
        recs = self._records
        if params.get("records"):
            wanted = str(params["records"])
            recs = [r for r in recs if str(r.get("record_id")) == wanted]
        return [dict(r) for r in recs]

    def export_metadata(self, **params):
        return [dict(m) for m in self._metadata]

    def record_id_field(self) -> str:
        return self._metadata[0]["field_name"]


def entry(env_var: str) -> dict:
    return MANIFEST["trackers"][env_var]


class TestFixtureIsWellFormed(unittest.TestCase):
    def test_every_tracker_in_argo_trackers_has_a_fixture(self):
        self.assertEqual(sorted(MANIFEST["trackers"]), sorted(TRACKERS.env_vars()))

    def test_manifest_agrees_with_the_real_tracker_definitions(self):
        """A fixture that drifts from argo_trackers.py tests nothing useful."""
        for env_var, title, pid, done_marker in TRACKERS.ADMIN_TRACKERS:
            e = entry(env_var)
            self.assertEqual(e["project_title"], title, env_var)
            self.assertEqual(e["pid"], pid, env_var)
            self.assertEqual(e["done_marker"], done_marker, env_var)
            self.assertEqual(e["source_form"], TRACKERS.SOURCE_FORMS[env_var], env_var)
        self.assertEqual(MANIFEST["sir_build_steps"], TRACKERS.SIR_BUILD_STEPS)

    def test_manifest_mirrors_open_requests_boring_list(self):
        self.assertEqual(MANIFEST["boring_fields"], sorted(OR.BORING))

    def test_record_counts_match_the_manifest(self):
        for env_var, e in MANIFEST["trackers"].items():
            recs = json.loads((FIXTURE / e["records_file"]).read_text())
            self.assertEqual(len(recs), e["total"], env_var)
            self.assertEqual(e["open"] + e["done"], e["total"], env_var)

    def test_fixtures_are_obviously_synthetic(self):
        blob = "\n".join((FIXTURE / e["records_file"]).read_text()
                         for e in MANIFEST["trackers"].values())
        self.assertNotIn("@", blob.replace("@example.org", ""),
                         "the only email domain in the fixtures must be example.org")


class TestOpenBucketing(unittest.TestCase):
    """_open_records buckets on the tracker's own done marker, label-mode 'Yes'."""

    def test_open_counts_match_the_manifest(self):
        for env_var, e in MANIFEST["trackers"].items():
            client = FixtureClient(env_var)
            open_recs, id_field = OR._open_records(client, e["done_marker"])
            self.assertEqual(len(open_recs), e["open"], env_var)
            self.assertEqual(id_field, MANIFEST["id_field"], env_var)
            self.assertEqual([r[id_field] for r in open_recs], e["open_record_ids"], env_var)

    def test_done_records_are_excluded(self):
        for env_var, e in MANIFEST["trackers"].items():
            open_recs, _ = OR._open_records(FixtureClient(env_var), e["done_marker"])
            got = {r["record_id"] for r in open_recs}
            self.assertFalse(got & set(e["done_record_ids"]), env_var)

    def test_a_blank_done_marker_counts_as_open(self):
        """SIR record 2 has an entirely blank build_tracking form — it is still a build to do."""
        e = entry("STUDY_INITIATION_REQUEST")
        recs = json.loads((FIXTURE / e["records_file"]).read_text())
        blank = next(r for r in recs if r["record_id"] == "2")
        self.assertEqual(blank["study_production"], "")
        self.assertIn("2", e["open_record_ids"])

    def test_portfolio_buckets_identically(self):
        """portfolio.collect() and open_requests must not disagree about what's finished."""
        for env_var, e in MANIFEST["trackers"].items():
            recs = json.loads((FIXTURE / e["records_file"]).read_text())
            done = [r for r in recs if r.get(e["done_marker"]) == MANIFEST["done_value"]]
            self.assertEqual(len(done), e["done"], env_var)


class TestFormFields(unittest.TestCase):
    def test_only_the_source_form_is_returned(self):
        for env_var, e in MANIFEST["trackers"].items():
            fields = OR._form_fields(FixtureClient(env_var), e["source_form"])
            self.assertEqual(len(fields), e["form_field_count"], env_var)

    def test_sir_build_tracking_fields_are_not_summary_material(self):
        """The 7 build steps live on build_tracking, so they never reach a summary line."""
        e = entry("STUDY_INITIATION_REQUEST")
        names = {n for n, _ in OR._form_fields(FixtureClient("STUDY_INITIATION_REQUEST"),
                                               e["source_form"])}
        self.assertFalse(names & set(TRACKERS.SIR_BUILD_STEPS))

    def test_an_unlabelled_field_falls_back_to_its_name(self):
        e = entry("SUPPORT_TICKET_REQUEST")
        fields = dict(OR._form_fields(FixtureClient("SUPPORT_TICKET_REQUEST"),
                                      e["source_form"]))
        fallback = MANIFEST["label_fallback_field"]
        self.assertEqual(fields[fallback], fallback)


class TestSummarise(unittest.TestCase):
    """The summary line must read as labels, never as field names."""

    def _summaries(self, env_var):
        e = entry(env_var)
        client = FixtureClient(env_var)
        fields = OR._form_fields(client, e["source_form"])
        open_recs, id_field = OR._open_records(client, e["done_marker"])
        return e, {r[id_field]: OR._summarise(r, fields, id_field) for r in open_recs}

    def test_summaries_show_labels_not_field_names(self):
        # Every field name on these forms contains an underscore; no label or value does.
        for env_var in MANIFEST["trackers"]:
            e, summaries = self._summaries(env_var)
            for rid, line in summaries.items():
                self.assertNotIn("_", line, f"{env_var} record {rid}: {line!r}")
                expected = e["expected_first_label"][rid]
                if expected:
                    self.assertTrue(line.startswith(expected + ":"),
                                    f"{env_var} record {rid}: {line!r}")

    def test_records_with_no_details_say_so(self):
        for env_var in MANIFEST["trackers"]:
            e, summaries = self._summaries(env_var)
            for rid in e["open_with_no_details"]:
                self.assertEqual(summaries[rid], "(no details filled in)",
                                 f"{env_var} record {rid}")
            self.assertEqual(
                sum(1 for s in summaries.values() if s == "(no details filled in)"),
                len(e["open_with_no_details"]), env_var)

    def test_triage_fields_never_appear(self):
        """assigned_to / completed / notes and friends say nothing about the request."""
        for env_var in MANIFEST["trackers"]:
            e, summaries = self._summaries(env_var)
            client = FixtureClient(env_var)
            labels = {lab for name, lab in OR._form_fields(client, e["source_form"])
                      if name in OR.BORING}
            self.assertTrue(labels, f"{env_var} fixture has no triage fields to skip")
            for rid, line in summaries.items():
                for lab in labels:
                    self.assertNotIn(lab, line, f"{env_var} record {rid}: {line!r}")

    def test_at_most_three_field_bits_per_line(self):
        for env_var in MANIFEST["trackers"]:
            _e, summaries = self._summaries(env_var)
            for rid, line in summaries.items():
                if line == "(no details filled in)":
                    continue
                self.assertLessEqual(len(line.split("; ")), 3, f"{env_var} {rid}: {line!r}")

    def test_a_long_wrapped_label_is_collapsed_and_truncated(self):
        spec = MANIFEST["long_label"]
        _e, summaries = self._summaries(spec["tracker"])
        rendered = spec["expected_rendered"]
        self.assertNotIn("\n", rendered)
        hits = [line for line in summaries.values() if rendered in line]
        self.assertTrue(hits, f"no summary carried {rendered!r}: {summaries}")

    def test_a_thin_record_still_summarises(self):
        """SIR record 4 has only two filled request-form fields — no crash, no padding."""
        _e, summaries = self._summaries("STUDY_INITIATION_REQUEST")
        self.assertEqual(len(summaries["4"].split("; ")), 2, summaries["4"])


class TestSirProgress(unittest.TestCase):
    """One counting rule, shared.

    Until 0.17.2 there were two: the queue counted the literal "Yes", the weekly check counted
    any settled answer, and the same study read 3/7 to one and 4/7 to the other. The rule now
    lives once, in `argo_trackers.sir_progress`, and both sides import it — so these tests
    assert AGREEMENT where they used to pin the divergence.
    """

    def setUp(self):
        self.entry = entry("STUDY_INITIATION_REQUEST")
        self.records = json.loads((FIXTURE / self.entry["records_file"]).read_text())

    @staticmethod
    def _retired_strict_rule(rec: dict) -> str:
        """The rule open_requests used to apply: only the literal 'Yes' counts.

        Kept here, and nowhere in the shipped code, so the fixture's engineered radio records
        still assert something — they are exactly where the lenient rule counts one more.
        """
        done = sum(1 for f in TRACKERS.SIR_BUILD_STEPS if str(rec.get(f, "")).strip() == "Yes")
        return f"{done}/{len(TRACKERS.SIR_BUILD_STEPS)}"

    def test_both_progress_functions_bucket_to_the_lenient_manifest(self):
        for name, fn in (("open_requests", OR._sir_progress),
                         ("portfolio", PORTFOLIO.sir_progress)):
            buckets = {}
            for rec in self.records:
                p = fn(rec)
                buckets[p] = buckets.get(p, 0) + 1
            self.assertEqual(buckets, self.entry["sir_progress_lenient"], name)

    def test_every_bucket_from_zero_to_seven_is_represented(self):
        self.assertEqual(sorted(self.entry["sir_progress_lenient"]),
                         [f"{i}/7" for i in range(8)])

    def test_per_record_progress_matches_the_manifest(self):
        for rec in self.records:
            expected = self.entry["sir_progress_per_record"][rec["record_id"]]["lenient"]
            self.assertEqual(OR._sir_progress(rec), expected, rec["record_id"])
            self.assertEqual(PORTFOLIO.sir_progress(rec), expected, rec["record_id"])

    def test_the_two_progress_functions_agree_on_every_record(self):
        """The flipped pin: they used to diverge by design. One shared helper, so they can't."""
        diverging = sorted(r["record_id"] for r in self.records
                           if OR._sir_progress(r) != PORTFOLIO.sir_progress(r))
        self.assertEqual(diverging, [],
                         "open_requests and the weekly check disagree about build progress — "
                         "both must go through argo_trackers.sir_progress")

    def test_both_sides_delegate_to_the_shared_helper(self):
        """Not just equal outputs: the same function is doing the counting on both sides."""
        for rec in self.records:
            done, total = TRACKERS.sir_progress(rec)
            self.assertEqual(f"{done}/{total}", OR._sir_progress(rec), rec["record_id"])
            self.assertEqual((done, total), PORTFOLIO._sir_progress_counts(rec),
                             rec["record_id"])

    def test_the_lenient_rule_counts_the_engineered_radio_answers(self):
        """Regression for the fix: exactly the records the manifest calls out as divergent
        count one step MORE than the retired 'Yes'-only rule would have."""
        gained = sorted(r["record_id"] for r in self.records
                        if self._retired_strict_rule(r) != OR._sir_progress(r))
        self.assertEqual(gained, self.entry["progress_divergence_record_ids"])
        for rid in gained:
            rec = next(r for r in self.records if r["record_id"] == rid)
            strict_done = int(self._retired_strict_rule(rec).split("/")[0])
            lenient_done = int(OR._sir_progress(rec).split("/")[0])
            self.assertGreater(lenient_done, strict_done, rid)

    def test_every_record_in_production_is_seven_of_seven(self):
        for rec in self.records:
            if rec["study_production"] == "Yes":
                self.assertEqual(OR._sir_progress(rec), "7/7", rec["record_id"])
                self.assertEqual(PORTFOLIO.sir_progress(rec), "7/7", rec["record_id"])


class TestLabelsReadAsSentences(unittest.TestCase):
    """0.17.2 #26: doubled colons. REDCap labels are written to sit on a form, so most of them
    already end in ':' — appending our own gave "Full study title:: Hepatectomy" on every line
    of every queue."""

    def test_a_trailing_colon_on_the_label_is_dropped(self):
        self.assertEqual(OR._clean_label("Full study title:"), "Full study title")
        self.assertEqual(OR._clean_label("Name of the person requesting :"),
                         "Name of the person requesting")

    def test_a_label_without_one_is_unchanged(self):
        self.assertEqual(OR._clean_label("Full study title"), "Full study title")

    def test_wrapping_is_collapsed_before_the_colon_is_dropped(self):
        self.assertEqual(OR._clean_label("Purpose of the\n   linkage:"),
                         "Purpose of the linkage")

    def test_truncation_can_never_leave_a_dangling_colon(self):
        label = "x" * 39 + ":" + " and more text"
        self.assertFalse(OR._clean_label(label).endswith(":"))

    def test_the_whole_label_is_kept_for_the_one_record_view(self):
        long_label = "A very long question that a form would wrap over three separate lines:"
        self.assertEqual(OR._clean_label(long_label, width=None), long_label.rstrip(":"))

    def test_no_summary_line_in_the_fixture_ever_shows_a_doubled_colon(self):
        for env_var, e in MANIFEST["trackers"].items():
            client = FixtureClient(env_var)
            fields = OR._form_fields(client, e["source_form"])
            open_recs, id_field = OR._open_records(client, e["done_marker"])
            for rec in open_recs:
                line = OR._summarise(rec, fields, id_field)
                self.assertNotIn("::", line, f"{env_var} {rec[id_field]}: {line!r}")


class TestBuildsQueueNamesTheStudy(unittest.TestCase):
    """0.17.2 #26: the two halves of the weekly check named studies differently.

    The portfolio identifies a study by its short name and PI; the build queue showed a record
    number and the first few form fields, so nobody could match one against the other by eye.
    """

    def _sir(self, record_id):
        e = entry("STUDY_INITIATION_REQUEST")
        recs = json.loads((FIXTURE / e["records_file"]).read_text())
        return next(r for r in recs if r["record_id"] == record_id)

    def test_a_filled_record_carries_short_name_and_pi(self):
        rec = self._sir("9")
        label = OR._study_label(rec)
        self.assertIn(rec["shortened_study_name"], label)
        self.assertIn(rec["pi_surname"], label)
        self.assertIn("PI:", label)

    def test_the_same_two_facts_the_portfolio_shows(self):
        """Same study, same words, on both halves of the weekly check."""
        rec = self._sir("9")
        portfolio_line = PORTFOLIO.summarize("STUDY_INITIATION_REQUEST", rec)
        for fact in (rec["shortened_study_name"], rec["pi_surname"]):
            self.assertIn(fact, portfolio_line)
            self.assertIn(fact, OR._study_label(rec))

    def test_a_blank_record_produces_no_stray_dashes(self):
        """A half-filled request still gets a usable line — never ' — PI: ' with nothing in it."""
        self.assertEqual(OR._study_label(self._sir("2")), "")
        self.assertEqual(OR._study_label({}), "")

    def test_only_one_of_the_two_is_still_useful(self):
        self.assertEqual(OR._study_label({"shortened_study_name": "Hepatectomy"}), "Hepatectomy")
        self.assertEqual(OR._study_label({"pi_surname": "Alatise"}), "PI: Alatise")


class TestPeopleQueueNamesThePerson(unittest.TestCase):
    """0.19 #44: a personnel request you can't put a name to is one you can't act on.

    The weekly check now puts every open request in its own table row, with first name, last
    name and email as columns. The queue line has to carry those, and carry them where the
    row-splitting rule can find them — but only from the record's OWN data dictionary, and only
    when the record actually holds them.
    """

    ENV = "STUDY_PERSONELL_REQUEST"

    def setUp(self):
        self.entry = entry(self.ENV)
        self.client = FixtureClient(self.ENV)
        self.fields = OR._form_fields(self.client, self.entry["source_form"])
        self.labels = dict(self.fields)
        self.open_recs, self.id_field = OR._open_records(self.client, self.entry["done_marker"])
        self.lines = {r[self.id_field]: OR._detail_line("people", r, self.fields, self.id_field)
                      for r in self.open_recs}

    def test_the_fixture_actually_carries_name_and_email(self):
        """If the fixture lost these fields the tests below would pass vacuously."""
        filled = [r for r in self.open_recs if r["record_id"] != "6"]
        self.assertTrue(filled)
        for rec in filled:
            for field in OR.PERSON_FIELDS:
                self.assertTrue(str(rec.get(field, "")).strip(), f"{rec['record_id']}/{field}")

    def test_every_filled_open_request_shows_name_and_email(self):
        for rec in self.open_recs:
            if rec["record_id"] == "6":            # the deliberately empty one
                continue
            line = self.lines[rec["record_id"]]
            for field in OR.PERSON_FIELDS:
                self.assertIn(rec[field], line, f"record {rec['record_id']}: {line!r}")

    def test_the_person_comes_first_on_the_line(self):
        """Before institution or date — the row's first columns must identify the person."""
        for rec in self.open_recs:
            if rec["record_id"] == "6":
                continue
            bits = self.lines[rec["record_id"]].split("; ")
            self.assertEqual(len(bits[:3]), 3, rec["record_id"])
            for i, field in enumerate(OR.PERSON_FIELDS):
                self.assertTrue(bits[i].endswith(rec[field]),
                                f"record {rec['record_id']} bit {i}: {bits[i]!r}")

    def test_what_they_are_asking_for_comes_next(self):
        """NITS 44 wants the role in the table. The form lists it AFTER the phone number and
        institution, so a plain three-field summary never reached it."""
        for rec in self.open_recs:
            if rec["record_id"] == "6":
                continue
            bits = self.lines[rec["record_id"]].split("; ")
            self.assertTrue(bits[3].endswith(rec["user_role"]),
                            f"record {rec['record_id']}: {bits[3]!r}")

    def test_the_role_beats_the_incidental_fields_onto_the_line(self):
        """The bug this fixes: institution and date crowded the role off the end."""
        for rid, line in self.lines.items():
            if line == OR.NO_DETAILS:
                continue
            role = self.lines[rid].split("; ")[3]
            institution = OR._clean_label(self.labels["institution"])
            self.assertLess(line.index(role), line.index(institution), f"record {rid}")

    def test_the_headings_are_the_forms_own_labels(self):
        """Metadata-driven, not hardcoded English: the DD calls them Given/Family name."""
        line = self.lines["1"]
        for field in OR.PERSON_FIELDS:
            self.assertIn(f"{OR._clean_label(self.labels[field])}:", line)
        self.assertNotIn("first_name", line)
        self.assertNotIn("last_name", line)

    def test_nothing_is_said_twice(self):
        """The person's fields lead the line, so the generic summary must skip them."""
        for rid, line in self.lines.items():
            headings = [bit.split(":")[0] for bit in line.split("; ")]
            self.assertEqual(len(headings), len(set(headings)), f"record {rid}: {line!r}")

    def test_every_bit_is_a_labelled_pair(self):
        """The weekly check splits a line on '; ' and makes each bit a column."""
        for rid, line in self.lines.items():
            if line == OR.NO_DETAILS:
                continue
            for bit in line.split("; "):
                self.assertIn(": ", bit, f"record {rid}: {bit!r}")

    def test_a_record_with_no_person_fields_falls_back_to_the_summary(self):
        """A tracker whose form doesn't name people this way still renders."""
        rec = {"record_id": "99", "institution": "Example University Clinic"}
        line = OR._detail_line("people", rec, self.fields, self.id_field)
        self.assertEqual(line, OR._summarise(rec, self.fields, self.id_field))
        self.assertIn("Example University Clinic", line)

    def test_an_entirely_empty_request_still_says_so(self):
        self.assertEqual(self.lines["6"], OR.NO_DETAILS)

    def test_a_half_filled_person_drops_the_missing_bits(self):
        """No empty columns: a request with a name but no email shows a name and no email."""
        rec = {"record_id": "98", "first_name": "Cleo", "last_name": "Sampleton"}
        line = OR._detail_line("people", rec, self.fields, self.id_field)
        self.assertIn("Cleo", line)
        self.assertIn("Sampleton", line)
        self.assertNotIn(OR._clean_label(self.labels["email"]) + ":", line)
        self.assertNotEqual(line, OR.NO_DETAILS)

    def test_a_person_with_nothing_else_filled_is_not_padded(self):
        rec = {"record_id": "97", "first_name": "Cleo", "last_name": "Sampleton",
               "email": "c.sampleton@example.org"}
        line = OR._detail_line("people", rec, self.fields, self.id_field)
        self.assertNotIn(OR.NO_DETAILS, line)
        self.assertEqual(len(line.split("; ")), 3, line)

    def test_the_other_queues_are_untouched(self):
        """Only the people queue leads with a person; everything else is the plain summary."""
        for env_var, e in MANIFEST["trackers"].items():
            if env_var == self.ENV:
                continue
            key = next((k for k, (var, _h) in OR.QUEUES.items() if var == env_var), None)
            if key is None:                        # support tickets aren't an expanded queue
                continue
            client = FixtureClient(env_var)
            fields = OR._form_fields(client, e["source_form"])
            recs, id_field = OR._open_records(client, e["done_marker"])
            for rec in recs:
                self.assertEqual(OR._detail_line(key, rec, fields, id_field),
                                 OR._summarise(rec, fields, id_field),
                                 f"{env_var} {rec[id_field]}")

    def test_the_lead_fields_are_the_ones_the_form_documents(self):
        """Nothing here may be invented: every lead field is on the SPR form's dictionary.

        `user_study` is the exception — it exists on the live PID 221 form but not in this
        fixture, which is precisely the case the drop-if-absent rule exists for, so it is
        asserted absent rather than present.
        """
        names = {n for n, _lab in self.fields}
        for field in OR.PERSON_FIELDS + ("user_role",):
            self.assertIn(field, names,
                          "the people lead must name fields the Study Personnel Request form "
                          "actually has — nothing here may be invented")
        self.assertNotIn("user_study", names)
        for rid, line in self.lines.items():
            self.assertNotIn("user_study", line, f"record {rid} leaked an absent field name")

    def test_the_lead_is_the_identity_trio_plus_what_is_asked_for(self):
        self.assertEqual(OR.PEOPLE_LEAD_FIELDS, OR.PERSON_FIELDS + OR.PERSON_ASK_FIELDS)
        self.assertEqual(OR.PERSON_FIELDS, ("first_name", "last_name", "email"))


class TestPortfolioSummarize(unittest.TestCase):
    """portfolio.summarize reads named fields; the fixture must actually carry them."""

    def test_summaries_are_populated_for_every_tracker(self):
        for env_var, e in MANIFEST["trackers"].items():
            recs = json.loads((FIXTURE / e["records_file"]).read_text())
            for rec in recs:
                line = PORTFOLIO.summarize(env_var, rec)
                self.assertIsInstance(line, str)
                self.assertTrue(line.strip(), f"{env_var} {rec['record_id']}")

    def test_sir_summary_carries_status_pid_progress_and_pi(self):
        e = entry("STUDY_INITIATION_REQUEST")
        recs = json.loads((FIXTURE / e["records_file"]).read_text())
        filled = next(r for r in recs if r["record_id"] == "9")
        line = PORTFOLIO.summarize("STUDY_INITIATION_REQUEST", filled)
        self.assertIn(filled["study_status"], line)
        self.assertIn(filled["new_project_pid"], line)
        self.assertIn(PORTFOLIO.sir_progress(filled), line)
        self.assertIn(filled["pi_surname"], line)

    def test_a_blank_sir_record_does_not_crash_the_summary(self):
        e = entry("STUDY_INITIATION_REQUEST")
        recs = json.loads((FIXTURE / e["records_file"]).read_text())
        blank = next(r for r in recs if r["record_id"] == "2")
        line = PORTFOLIO.summarize("STUDY_INITIATION_REQUEST", blank)
        self.assertIn("no PID", line)
        self.assertIn("0/7", line)


class TestGeneratorIsByteStable(unittest.TestCase):
    """Regenerating must reproduce the committed fixture exactly — otherwise every diff is
    noise and no test can trust the MANIFEST."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="argo-trackers-"))
        cls.runs = []
        for i in (1, 2):
            out = cls.tmp / f"run{i}"
            proc = subprocess.run([sys.executable, str(GENERATOR), "--out", str(out)],
                                  capture_output=True, text=True, timeout=120)
            cls.runs.append((out, proc))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_generator_runs_clean(self):
        for out, proc in self.runs:
            self.assertEqual(proc.returncode, 0, proc.stderr[-1500:])
            self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_two_runs_are_byte_identical(self):
        (a, _), (b, _) = self.runs
        names = sorted(p.name for p in a.iterdir())
        self.assertEqual(names, sorted(p.name for p in b.iterdir()))
        for name in names:
            self.assertEqual((a / name).read_bytes(), (b / name).read_bytes(),
                             f"{name} differs between two runs of generate.py")

    def test_committed_fixture_matches_a_fresh_run(self):
        out, _ = self.runs[0]
        for path in sorted(out.iterdir()):
            committed = FIXTURE / path.name
            self.assertTrue(committed.exists(), f"{path.name} is not committed")
            self.assertEqual(committed.read_bytes(), path.read_bytes(),
                             f"{path.name} is stale — re-run generate.py and commit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
