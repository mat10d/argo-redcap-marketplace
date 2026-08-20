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

PRESENT = all(p.exists() for p in (DD_BUILDER, VALIDATE_DD,
                                   FIXTURE / "fields.json",
                                   FIXTURE / "dirty_datadictionary.csv",
                                   FIXTURE / "MANIFEST.json"))


def load_validate_dd():
    spec = importlib.util.spec_from_file_location("argo_validate_dd", VALIDATE_DD)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
