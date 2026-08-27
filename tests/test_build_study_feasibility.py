#!/usr/bin/env python3
"""Feasibility test of the database manager's build task against the synthetic-build fixture.

Two halves, mirroring the two things a build actually does:

  (a) CONSTRUCT — dd_builder.py turns testing/fixtures/synthetic-build/fields.json into a
      data dictionary; it must exit 0 and the result must pass validate_dd.py with zero
      errors AND zero warnings (MDC applied by construction, per the SKILL's Path A claim).
  (b) AUDIT — validate_dd.py on dirty_datadictionary.csv must report exactly the violation
      set MANIFEST.json declares: same checks, same counts, same fields, same rows. Message
      wording is not asserted; each check carries a tolerant regex in the manifest.

Asserts against MANIFEST.json's engineered counts — numbers, not vibes. Both scripts are
stdlib-only, so this test skips only if the scripts or the fixture are missing.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "testing" / "fixtures" / "synthetic-build"
BUILD_STUDY = REPO / "plugins" / "argo-database-manager" / "skills" / "build-study"
DD_BUILDER = BUILD_STUDY / "dd_builder.py"
VALIDATE_DD = BUILD_STUDY / "validate_dd.py"
SETUP_BRIEF = BUILD_STUDY / "setup_brief.py"

PRESENT = all(p.exists() for p in (DD_BUILDER, VALIDATE_DD,
                                   FIXTURE / "fields.json",
                                   FIXTURE / "dirty_datadictionary.csv",
                                   FIXTURE / "MANIFEST.json"))


def load_validate_dd():
    spec = importlib.util.spec_from_file_location("argo_validate_dd", VALIDATE_DD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_dd_builder():
    spec = importlib.util.spec_from_file_location("argo_dd_builder", DD_BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_setup_brief():
    spec = importlib.util.spec_from_file_location("argo_setup_brief", SETUP_BRIEF)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipIf(not PRESENT, "build-study scripts or synthetic-build fixture not present")
class TestDdBuilderProducesACleanDictionary(unittest.TestCase):
    """(a) fields.json -> dd_builder -> a dictionary validate_dd passes clean."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "SYNBUILD_DataDictionary.csv"
        cls.proc = subprocess.run(
            [sys.executable, str(DD_BUILDER), str(FIXTURE / "fields.json"), str(cls.out)],
            capture_output=True, text=True, timeout=120,
        )
        cls.manifest = json.loads((FIXTURE / "MANIFEST.json").read_text())
        cls.validate_dd = load_validate_dd()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_dd_builder_exits_zero(self):
        self.assertEqual(self.proc.returncode, 0,
                         f"dd_builder failed on fields.json:\n{self.proc.stderr[-1500:]}")
        self.assertNotIn("Traceback", self.proc.stdout + self.proc.stderr)

    def test_dd_has_the_manifest_field_count_and_18_columns(self):
        import csv
        with self.out.open(newline="") as fh:
            rows = list(csv.reader(fh))
        inv = self.manifest["fields_json"]
        self.assertEqual(len(rows) - 1, inv["n_fields"])
        for n, row in enumerate(rows, 1):
            self.assertEqual(len(row), 18, f"row {n} has {len(row)} columns, expected 18")
        self.assertEqual(rows[1][0], inv["record_id_field"])

    def test_built_dd_validates_clean(self):
        errors, warnings = self.validate_dd.validate(str(self.out))
        self.assertEqual(errors, [], "dd_builder output must validate with zero errors")
        self.assertEqual(warnings, [], "dd_builder output must validate with zero warnings")

    def test_built_dd_validates_clean_at_patient_level(self):
        errors, _ = self.validate_dd.validate(str(self.out), patient_level=True)
        self.assertEqual(errors, [], "fixture carries hospital_number (Identifier? = y)")

    def test_mdc_applied_to_every_non_exempt_field(self):
        """dd_builder's headline promise: MDC by construction. Assert it field by field."""
        import csv
        with self.out.open(newline="") as fh:
            rows = {r[0]: r for r in list(csv.reader(fh))[1:]}
        inv = self.manifest["fields_json"]
        for var in inv["mdc_applied_fields"]:
            row = rows[var]
            blob = row[5] + row[6]  # choices + field note
            self.assertIn("-666", blob, f"{var} has no MDC in choices or field note")
        for var in inv["mdc_exempt_fields"]:
            row = rows[var]
            self.assertNotIn("-666", row[5] + row[6], f"{var} is MDC-exempt but carries MDC")

    def test_the_validated_scale_is_exempt_by_visible_annotation(self):
        """NITS 7: a validated Likert scale belongs in a CLEAN dictionary — via @MDC-EXEMPT."""
        import csv
        with self.out.open(newline="") as fh:
            rows = {r[0]: r for r in list(csv.reader(fh))[1:]}
        inv = self.manifest["fields_json"]
        annotated = inv["mdc_exempt_annotated_fields"]
        self.assertTrue(annotated, "fixture must carry at least one MDC-exempt scale")
        for var in annotated:
            self.assertIn(inv["mdc_exempt_annotation"], rows[var][17],
                          f"{var} opted out of MDC but the dictionary doesn't say so")
            self.assertNotIn("-666", rows[var][5] + rows[var][6])
        for group in inv["mdc_exempt_matrix_groups"]:
            members = inv["matrix_groups"][group]
            self.assertTrue(set(members) <= set(annotated))
        # and the whole dictionary — validated scale included — is still clean
        errors, warnings = self.validate_dd.validate(str(self.out))
        self.assertEqual((errors, warnings), ([], []))


@unittest.skipIf(not PRESENT, "build-study scripts or synthetic-build fixture not present")
class TestValidateDdOnTheDirtyDictionary(unittest.TestCase):
    """(b) the dirty DD raises exactly the manifest's violations — counts, fields, rows."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((FIXTURE / "MANIFEST.json").read_text())
        cls.spec = cls.manifest["dirty_dd"]
        cls.dirty = FIXTURE / "dirty_datadictionary.csv"
        vd = load_validate_dd()
        cls.errors, cls.warnings = vd.validate(str(cls.dirty))
        cls.pl_errors, _ = vd.validate(str(cls.dirty), patient_level=True)

    # -- helpers ----------------------------------------------------------
    def _bucket(self, checks, messages, severity):
        """{check: [messages]} plus the messages nothing claimed / several claimed."""
        wanted = {n: c for n, c in checks.items() if c["severity"] == severity}
        buckets = {n: [] for n in wanted}
        unclaimed, multi = [], []
        for msg in messages:
            low = msg.lower()
            hits = [n for n, c in wanted.items() if re.search(c["match_regex"], low)]
            if not hits:
                unclaimed.append(msg)
            elif len(hits) > 1:
                multi.append((msg, hits))
            else:
                buckets[hits[0]].append(msg)
        return buckets, unclaimed, multi

    def _assert_matches_manifest(self, severity, messages):
        checks = self.spec["checks"]
        buckets, unclaimed, multi = self._bucket(checks, messages, severity)
        self.assertEqual(multi, [], f"manifest regexes are ambiguous for these {severity}s")
        self.assertEqual(unclaimed, [],
                         f"validator produced {severity}s the MANIFEST does not declare")
        for name, spec in ((n, c) for n, c in checks.items() if c["severity"] == severity):
            got = buckets[name]
            self.assertEqual(len(got), spec["count"],
                             f"{name}: expected {spec['count']} {severity}(s), got {len(got)}:\n"
                             + "\n".join(got))
            blob = " || ".join(got)
            if spec.get("field_named_in_message", True):
                for field in spec["fields"]:
                    if field:  # the empty-variable-name row has no name to match on
                        self.assertIn(field, blob, f"{name}: no message mentions '{field}'")
            for row_no in spec["rows"]:
                self.assertIn(f"Row {row_no}", blob, f"{name}: no message points at row {row_no}")

    # -- tests ------------------------------------------------------------
    def test_error_total_matches_manifest(self):
        self.assertEqual(len(self.errors), self.spec["expected_errors_total"],
                         "\n".join(self.errors))

    def test_warning_total_matches_manifest(self):
        self.assertEqual(len(self.warnings), self.spec["expected_warnings_total"],
                         "\n".join(self.warnings))

    def test_every_engineered_error_is_detected_exactly_once(self):
        self._assert_matches_manifest("error", self.errors)

    def test_every_engineered_warning_is_detected_exactly_once(self):
        self._assert_matches_manifest("warning", self.warnings)

    def test_patient_level_flag_adds_exactly_the_manifest_extras(self):
        extra = self.spec["patient_level_only"]["checks"]
        expected_n = sum(c["count"] for c in extra.values() if c["severity"] == "error")
        self.assertEqual(len(self.pl_errors), len(self.errors) + expected_n)
        added = [e for e in self.pl_errors if e not in self.errors]
        for name, c in extra.items():
            hits = [m for m in added if re.search(c["match_regex"], m.lower())]
            self.assertEqual(len(hits), c["count"], f"{name}: got {hits}")

    def test_mdc_waiver_silences_annotated_rows_but_not_their_controls(self):
        """NITS 7 both halves: @MDC-EXEMPT rows raise nothing; the same shape un-annotated does."""
        waiver = self.spec["mdc_waiver"]
        for var, row_no in waiver["waived_rows"].items():
            hits = [m for m in self.errors + self.warnings
                    if f"Row {row_no} " in m + " " or f"({var})" in m]
            self.assertEqual(hits, [], f"{var} is MDC-waived but the validator flagged it")
        for var, row_no in waiver["flagged_rows"].items():
            hits = [m for m in self.errors if f"({var})" in m and "MDC" in m]
            self.assertEqual(len(hits), 1,
                             f"{var} carries no waiver — it must still be flagged: {hits}")

    def test_validator_cli_exits_nonzero_on_the_dirty_dictionary(self):
        proc = subprocess.run([sys.executable, str(VALIDATE_DD), str(self.dirty)],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)


@unittest.skipIf(not PRESENT, "build-study scripts or synthetic-build fixture not present")
class TestFixtureIsReproducible(unittest.TestCase):
    """The generator is committed and seeded — rerunning it must not change a byte."""

    def test_generator_is_byte_stable(self):
        gen = FIXTURE / "generate.py"
        before = {p.name: p.read_bytes() for p in FIXTURE.iterdir()
                  if p.suffix in (".json", ".csv")}
        proc = subprocess.run([sys.executable, str(gen)], capture_output=True, text=True,
                              timeout=120, cwd=str(FIXTURE))
        self.assertEqual(proc.returncode, 0, proc.stderr[-1500:])
        after = {p.name: p.read_bytes() for p in FIXTURE.iterdir()
                 if p.suffix in (".json", ".csv")}
        self.assertEqual(sorted(before), sorted(after))
        for name in before:
            self.assertEqual(before[name], after[name], f"{name} changed on regeneration")


@unittest.skipIf(not PRESENT, "build-study scripts or synthetic-build fixture not present")
class TestDdBuilderMdcRules(unittest.TestCase):
    """Regressions for the dd_builder defects in NITS item 5 (a-d) and the item-7 waiver.

    Each one is checked twice: the cell dd_builder wrote, and validate_dd's verdict on the
    dictionary containing it — the defects were all cases of the builder failing its own
    validator.
    """

    @classmethod
    def setUpClass(cls):
        cls.builder = load_dd_builder()
        cls.validate_dd = load_validate_dd()
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # -- helpers ----------------------------------------------------------
    def _build(self, fields):
        """fields = [kwargs, ...] appended after a record-id field. -> (rows_by_var, path)."""
        import csv
        dd = self.builder.DD(form="clinical")
        dd.field("study_id", "text", "Study ID")
        for f in fields:
            dd.field(**f)
        path = Path(self.tmp.name) / f"dd_{abs(hash(repr(fields)))}.csv"
        dd.write(str(path))
        with path.open(newline="") as fh:
            rows = {r[0]: r for r in list(csv.reader(fh))[1:]}
        return rows, path

    def _validate(self, path):
        return self.validate_dd.validate(str(path))

    # -- (a) date-format MDC on every date validation ----------------------
    def test_every_date_validation_gets_date_format_mdc(self):
        """NITS 5a: only date_dmy/datetime_dmy got the date note — the other 7 failed the validator."""
        date_types = sorted(v for v in self.validate_dd.VALID_VALIDATION_TYPES
                            if v.startswith("date"))
        self.assertEqual(len(date_types), 9, date_types)  # 3 date_* + 3 datetime_* + 3 seconds
        fields = [{"var": f"d{n}", "type": "text", "label": f"Date {n}", "valid": v}
                  for n, v in enumerate(date_types)]
        rows, path = self._build(fields)
        for n, v in enumerate(date_types):
            note = rows[f"d{n}"][6]
            self.assertIn(self.validate_dd.DATE_MDC_MARKER, note,
                          f"{v} did not get date-format MDC (note={note!r})")
            self.assertNotIn("[-666", note, f"{v} got text-format MDC")
        errors, warnings = self._validate(path)
        self.assertEqual((errors, warnings), ([], []))

    def test_non_date_validations_still_get_text_format_mdc(self):
        fields = [{"var": f"v{n}", "type": "text", "label": f"Value {n}", "valid": v}
                  for n, v in enumerate(["", "integer", "number", "email", "phone", "time"])]
        rows, path = self._build(fields)
        for n in range(6):
            note = rows[f"v{n}"][6]
            self.assertNotIn(self.validate_dd.DATE_MDC_MARKER, note)
            self.assertTrue(self.validate_dd.TEXT_MDC_RE.search(note), note)
        self.assertEqual(self._validate(path), ([], []))

    # -- (b) a custom Field Note must survive ------------------------------
    def test_a_custom_field_note_is_kept_and_the_mdc_note_appended(self):
        """NITS 5b: a Field Note used to suppress MDC silently. Both must be present now."""
        custom_text, custom_date = "Record exactly as printed.", "Use the date on the card."
        rows, path = self._build([
            {"var": "occupation", "type": "text", "label": "Occupation", "note": custom_text},
            {"var": "referral", "type": "notes", "label": "Referral detail", "note": custom_text},
            {"var": "dob", "type": "text", "label": "Date of birth", "valid": "date_dmy",
             "note": custom_date},
        ])
        for var, custom in (("occupation", custom_text), ("referral", custom_text),
                            ("dob", custom_date)):
            note = rows[var][6]
            self.assertIn(custom, note, f"{var} lost the note the builder was given")
            self.assertIn("-666", note, f"{var} has a custom note and no MDC (the old defect)")
        self.assertIn(self.validate_dd.DATE_MDC_MARKER, rows["dob"][6])
        self.assertEqual(self._validate(path), ([], []))

    def test_mdc_is_not_appended_twice_to_a_note_that_already_has_it(self):
        rows, _ = self._build([{"var": "occupation", "type": "text", "label": "Occupation",
                                "note": self.builder.TEXT_MDC}])
        self.assertEqual(rows["occupation"][6].count("-666"), 1)

    # -- (c) Matrix Ranking? is never emitted ------------------------------
    def test_matrix_ranking_column_is_always_blank(self):
        """NITS 5c: the column was dead code (`and False`). It is now honestly always blank."""
        rows, path = self._build([
            {"var": "sev_a", "type": "radio", "label": "Item A", "choices": "0, No | 1, Yes",
             "matrix": "sev_grid"},
            {"var": "sev_b", "type": "radio", "label": "Item B", "choices": "0, No | 1, Yes",
             "matrix": "sev_grid"},
        ])
        self.assertEqual([rows["sev_a"][16], rows["sev_b"][16]], ["", ""])
        self.assertEqual(self._validate(path), ([], []))

    # -- (d) yesno is refused at build time --------------------------------
    def test_yesno_is_refused_by_the_builder(self):
        """NITS 5d: yesno used to pass through and only fail downstream."""
        dd = self.builder.DD(form="clinical")
        dd.field("study_id", "text", "Study ID")
        with self.assertRaises(ValueError) as ctx:
            dd.field("surgery_done", "yesno", "Surgery performed?")
        msg = str(ctx.exception)
        self.assertIn("surgery_done", msg)
        self.assertIn("radio", msg)
        self.assertIn("1, Yes | 0, No", msg)
        self.assertEqual(len(dd.rows), 1, "the rejected field must not reach the dictionary")

    def test_yesno_in_a_json_spec_fails_the_cli_plainly(self):
        spec = Path(self.tmp.name) / "yesno_fields.json"
        spec.write_text(json.dumps([
            {"var": "study_id", "type": "text", "label": "Study ID", "form": "clinical"},
            {"var": "surgery_done", "type": "yesno", "label": "Surgery performed?"},
        ]))
        out = Path(self.tmp.name) / "yesno_out.csv"
        proc = subprocess.run([sys.executable, str(DD_BUILDER), str(spec), str(out)],
                              capture_output=True, text=True, timeout=120)
        self.assertNotEqual(proc.returncode, 0, "yesno must not build")
        blob = proc.stdout + proc.stderr
        self.assertNotIn("Traceback", blob)
        self.assertIn("radio", blob)
        self.assertFalse(out.exists(), "a refused build must not leave a dictionary behind")

    # -- item 7: the MDC waiver -------------------------------------------
    def test_mdc_false_writes_the_exemption_annotation_and_validates_clean(self):
        scale = "0, Not at all | 1, Sometimes | 2, Often | 3, Always"
        rows, path = self._build([
            {"var": f"scale_q{n}", "type": "radio", "label": f"Scale item {n}",
             "choices": scale, "matrix": "val_scale", "mdc": False} for n in (1, 2, 3)
        ])
        for n in (1, 2, 3):
            row = rows[f"scale_q{n}"]
            self.assertIn("@MDC-EXEMPT", row[17], "mdc=False must be visible in the dictionary")
            self.assertNotIn("-666", row[5])
        self.assertEqual(self._validate(path), ([], []))

    def test_the_same_scale_without_the_annotation_is_still_flagged(self):
        """The waiver must not weaken the check — only an explicit annotation waives it."""
        import csv
        scale = "0, Not at all | 1, Sometimes | 2, Often | 3, Always"
        _, path = self._build([
            {"var": f"scale_q{n}", "type": "radio", "label": f"Scale item {n}",
             "choices": scale, "matrix": "val_scale", "mdc": False} for n in (1, 2, 3)
        ])
        with path.open(newline="") as fh:
            rows = list(csv.reader(fh))
        for row in rows[1:]:
            row[17] = ""  # strip the waiver, change nothing else
        stripped = Path(self.tmp.name) / "scale_unannotated.csv"
        with stripped.open("w", newline="") as fh:
            csv.writer(fh).writerows(rows)
        errors, _ = self._validate(stripped)
        self.assertEqual(len(errors), 3, errors)
        for n in (1, 2, 3):
            self.assertTrue(any(f"scale_q{n}" in e and "MDC" in e for e in errors), errors)

    def test_one_annotated_field_waives_its_whole_matrix_group(self):
        import csv
        scale = "0, Not at all | 1, Sometimes | 2, Often | 3, Always"
        _, path = self._build([
            {"var": f"scale_q{n}", "type": "radio", "label": f"Scale item {n}",
             "choices": scale, "matrix": "val_scale", "mdc": False} for n in (1, 2, 3)
        ])
        with path.open(newline="") as fh:
            rows = list(csv.reader(fh))
        seen = False
        for row in rows[1:]:  # leave the annotation on the FIRST scale field only
            if row[15] == "val_scale":
                if seen:
                    row[17] = ""
                seen = True
        group = Path(self.tmp.name) / "scale_group_waiver.csv"
        with group.open("w", newline="") as fh:
            csv.writer(fh).writerows(rows)
        self.assertEqual(self._validate(group), ([], []))

    def test_the_two_scripts_agree_on_the_annotation_spelling(self):
        self.assertEqual(self.builder.MDC_EXEMPT_ANNOTATION,
                         self.validate_dd.MDC_EXEMPT_ANNOTATION)


# A fabricated SIR record — three institutions in three countries, one of them unnamed.
# Nothing here resembles any real study; the point is that NO site name may come from
# anywhere except this record.
SYNTHETIC_SIR = {
    "record_id": "1", "project_title": "SYNTHETIC MULTI-SITE STUDY (TEST FIXTURE)",
    "pi_first_name": "Ada", "pi_surname": "Synth", "irb_number": "IRB/SYN/1",
    "inst_name_1": "Korle Bu Teaching Hospital",
    "inst_name_2": "Muhimbili National Hospital (MNH)",
    "inst_name_3": "",
    "quest_univ_file": "universal.docx", "quest_site_1": "s1.docx",
    "quest_site_2": "s2.docx", "quest_site_3": "s3.docx",
    "irb_file_1": "irb1.pdf", "consent_file_2": "consent2.pdf",
    "sop": "sop.docx", "eligibility_checklist": "ecl.docx",
}


@unittest.skipIf(not SETUP_BRIEF.exists(), "setup_brief.py not present")
class TestSetupBriefDerivesSitesFromTheRecord(unittest.TestCase):
    """NITS 11: the brief once named a previous study's sites. Site names come from the SIR."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_setup_brief()
        cls.tmp = tempfile.TemporaryDirectory()
        rec = Path(cls.tmp.name) / "rec.json"
        rec.write_text(json.dumps(SYNTHETIC_SIR))
        out = Path(cls.tmp.name) / "study"
        cls.proc = subprocess.run(
            [sys.executable, str(SETUP_BRIEF), "1", "--from-json", str(rec),
             "--out", str(out), "--moniker", "SYNMULTI"],
            capture_output=True, text=True, timeout=120)
        cls.brief = (out / "MANUAL_SETUP_BRIEF.md").read_text() if cls.proc.returncode == 0 else ""

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_brief_generates(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-1500:])
        self.assertNotIn("Traceback", self.proc.stdout + self.proc.stderr)

    def test_site_names_come_from_the_institution_fields(self):
        got = self.mod.site_names(SYNTHETIC_SIR)
        self.assertEqual(got, {"1": "Korle Bu Teaching Hospital",
                               "2": "Muhimbili National Hospital (MNH)"})

    def test_site_token_is_derived_from_the_institutions_own_name(self):
        self.assertEqual(self.mod.site_token("Muhimbili National Hospital (MNH)"), "MNH")
        self.assertEqual(self.mod.site_token("Korle Bu Teaching Hospital"), "KBTH")
        self.assertEqual(self.mod.site_token("University of Ghana Medical Centre"), "UGMC")
        self.assertEqual(self.mod.site_token("Bugando"), "Bugando")

    def test_a_missing_institution_becomes_a_todo_not_a_guess(self):
        sites = self.mod.site_names(SYNTHETIC_SIR)
        label, site = self.mod.repo_label("quest_site_3", sites)
        self.assertIn("TODO", label)
        self.assertIn("TODO", site)
        self.assertIn("inst_name_3", site)

    def test_the_rename_table_uses_this_records_sites_only(self):
        self.assertIn("SYNMULTI_Questionnaire_KBTH", self.brief)
        self.assertIn("SYNMULTI_IRB_KBTH", self.brief)
        self.assertIn("SYNMULTI_Consent_MNH", self.brief)
        self.assertIn("[TODO site 3]", self.brief)
        # the shipped defect: site names carried over from an unrelated study
        for stale in ("UCH", "UNIOSUN", "SiteUch", "SiteUniosun"):
            self.assertNotIn(stale, self.brief, f"'{stale}' is not one of this study's sites")

    def test_dags_are_the_named_institutions_in_number_order(self):
        dag_line = next(l for l in self.brief.splitlines() if "DAGs — create" in l)
        self.assertIn("Korle Bu Teaching Hospital", dag_line)
        self.assertLess(dag_line.index("Korle Bu"), dag_line.index("Muhimbili"))

    def test_brief_names_both_questionnaire_deliverables(self):
        """NITS 48: the single changelog split into two deliverables by KIND — assumptions the
        build made (`OPEN_QUESTIONS.md`) vs changes the questionnaire itself needs (the original
        with tracked changes). The brief promises both, and no longer the retired name."""
        self.assertIn("OPEN_QUESTIONS.md", self.brief)
        self.assertIn("_redcap_changes.docx", self.brief)
        self.assertIn("_redcap_changes.md", self.brief, "the PDF fallback has to be named too")
        self.assertNotIn("QUESTIONNAIRE_CHANGELOG", self.brief)

    def test_brief_keeps_typos_out_of_both_deliverables(self):
        """NITS 48 + the IRB minimal-change rule: cosmetic quirks are built as printed and go in
        neither deliverable. The brief must not read as an invitation to raise them."""
        self.assertRegex(self.brief, r"(?i)typos[^\n]*neither|neither[^\n]*typos")


if __name__ == "__main__":
    unittest.main(verbosity=2)
