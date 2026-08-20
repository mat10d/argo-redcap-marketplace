#!/usr/bin/env python3
"""End-to-end test of the QA specialist's TASK 2 — auditing RA-returned worklists.

Task 1 (build the worklists) has had a test since the synthetic fixture landed. Task 2 had
none at all: `review_responses.py` had never once been run against a workbook with RA edits in
it by anything automated. This closes that hole.

The round trip:

    records.csv + datadictionary.csv + qa_fields.yaml
        -> build_worklists.py                     (the worklists we'd send the sites)
        -> generate_returns.py                    (seeded, engineered RA edits)
        -> review_responses.py                    (the audit)
        -> counts asserted against MANIFEST.json's `returned` block

Nothing binary is committed: the workbooks are generated into a temp directory on every run
from the seeded generator, and thrown away afterwards.

Four of the assertions below record KNOWN DEFECTS rather than correct behaviour — three in
`review_responses.py`, one in `build_worklists.py`. They are named `test_known_defect_*` and
each docstring says what is wrong, what the consequence is, and what to do when it is fixed.
They exist so the gaps are visible in the suite instead of being discovered by an RA whose
answers were silently dropped.
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
FIXTURE = REPO / "testing" / "fixtures" / "synthetic-study"
GENERATOR = FIXTURE / "generate_returns.py"
QA_SKILL = REPO / "plugins" / "argo-qa-specialist" / "skills" / "qa-worklists"
REVIEWER = QA_SKILL / "review_responses.py"
BUILDER = QA_SKILL / "build_worklists.py"

try:
    import openpyxl  # noqa: F401
    import pandas  # noqa: F401
    import yaml  # noqa: F401
    DEPS = True
except ImportError:
    DEPS = False


def _load_reviewer():
    """Import review_responses.py by path — the plugin folder never goes on sys.path."""
    spec = importlib.util.spec_from_file_location("_argo_review_responses", REVIEWER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipIf(not DEPS, "pandas/openpyxl/yaml not installed")
class TestQAAuditRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp())
        cls.proc = subprocess.run(
            [sys.executable, str(GENERATOR), "--out", str(cls.out)],
            capture_output=True, text=True, timeout=600,
        )
        cls.manifest = json.loads((FIXTURE / "MANIFEST.json").read_text())
        cls.block = cls.manifest.get("returned", {})
        cls.rr = _load_reviewer()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    # -- helpers ----------------------------------------------------------

    def pair(self, name):
        return (self.out / "build" / "with_MDC" / f"{name}.xlsx",
                self.out / "returned" / f"{name}_RETURNED.xlsx")

    def expectations(self):
        exp = self.block.get("expected_review_responses")
        self.assertTrue(exp, "MANIFEST.json has no `returned.expected_review_responses` block — "
                             "run: python3 testing/fixtures/synthetic-study/generate_returns.py "
                             "--out /tmp/x --update-manifest")
        return exp

    # -- the generator ----------------------------------------------------

    def test_generator_completes_without_crashing(self):
        self.assertEqual(self.proc.returncode, 0,
                         f"generate_returns.py failed:\n{self.proc.stdout[-1500:]}"
                         f"\n{self.proc.stderr[-1500:]}")
        self.assertNotIn("Traceback", self.proc.stdout + self.proc.stderr)

    def test_four_returned_workbooks_written(self):
        books = sorted(p.name for p in (self.out / "returned").glob("*.xlsx"))
        self.assertEqual(len(books), 4, f"expected 4 returned workbooks, got {books}")

    def test_manifest_block_matches_what_the_generator_just_produced(self):
        """MANIFEST's stated counts must be the counts the seeded generator actually makes.

        If this fails, the fixture or the builder changed: rerun generate_returns.py with
        --update-manifest and check the diff is what you intended.
        """
        fresh = json.loads((self.out / "returned" / "returned_counts.json").read_text())
        self.assertTrue(self.block, "MANIFEST.json has no `returned` block")
        self.assertEqual(self.block.get("per_file"), fresh["per_file"])
        self.assertEqual(self.block.get("totals"), fresh["totals"])

    # -- the audit script -------------------------------------------------

    def test_reviewer_runs_on_every_returned_workbook(self):
        for name in self.expectations():
            orig, resp = self.pair(name)
            with self.subTest(name):
                proc = subprocess.run([sys.executable, str(REVIEWER), str(orig), str(resp)],
                                      capture_output=True, text=True, timeout=300)
                self.assertEqual(proc.returncode, 0,
                                 f"review_responses.py failed on {name}:\n{proc.stderr[-1500:]}")
                self.assertNotIn("Traceback", proc.stdout + proc.stderr)
                self.assertIn("RESPONSE column present: True", proc.stdout)

    def test_triage_counts_match_the_manifest(self):
        """The four-bucket triage inputs, per returned workbook, as exact numbers.

        READY / QUESTION_FOR_RA are both sourced from the changed-cell list (the specialist
        splits them by whether the value maps to the DD); NO_ACTION / VERIFY are both sourced
        from the note-only list. Those two lists are what review_responses.py produces, and
        they are what is asserted here.
        """
        for name, spec in self.expectations().items():
            orig, resp = self.pair(name)
            with self.subTest(name):
                by_record, notes, id_field, had_resp = self.rr.diff(str(orig), str(resp))
                changed_cells = sum(len(v) for v in by_record.values())
                note_only = [rid for rid, n in notes.items() if n and rid not in by_record]
                self.assertEqual(had_resp, spec["response_column_present"])
                self.assertEqual(id_field, "syn_id")
                self.assertEqual(len(by_record), spec["records_with_proposed_updates"],
                                 f"{name}: records with proposed updates")
                self.assertEqual(changed_cells, spec["changed_cells"],
                                 f"{name}: changed cells")
                self.assertEqual(len(note_only), spec["note_only_records"],
                                 f"{name}: records with a note but no cell change")

    def test_note_only_records_are_the_engineered_ones(self):
        """The VERIFY/NO_ACTION bucket must name the right patients, not just the right count."""
        for name, counts in self.block["per_file"].items():
            orig, resp = self.pair(name)
            with self.subTest(name):
                by_record, notes, _id, _had = self.rr.diff(str(orig), str(resp))
                note_only = sorted(rid for rid, n in notes.items() if n and rid not in by_record)
                self.assertEqual(note_only, counts["note_only_record_ids"])

    def test_mdc_answers_survive_the_audit_as_changed_cells(self):
        """An RA answering with an MDC sentinel is an answer, not a blank — it must show up."""
        for name, counts in self.block["per_file"].items():
            if not counts["filled_with_mdc"]:
                continue
            orig, resp = self.pair(name)
            with self.subTest(name):
                by_record, _n, _i, _h = self.rr.diff(str(orig), str(resp))
                seen = [nv for cells in by_record.values() for _f, _ov, nv in cells]
                mdc_seen = sum(1 for v in seen if v in self.manifest["qa"]["sentinel_codes"])
                self.assertEqual(mdc_seen, counts["filled_with_mdc"],
                                 f"{name}: MDC answers reported")

    # -- known defects ----------------------------------------------------

    def test_known_defect_out_of_scope_edits_are_not_reported(self):
        """DEFECT: review_responses.py cannot see an RA edit to a cell that wasn't flagged.

        `_yellow_keys` only records yellow cells, and `diff` only looks up response values for
        those keys, so a value the RA overwrote in a gate-context column (e.g. changing
        'Sex' from Female to Male) passes the audit completely silently. The fixture engineers
        9 such edits across the four workbooks; the audit reports 0 of them.

        Asserted as 0 because that is today's behaviour. If this test starts failing because
        the script now reports them, that is the fix landing — update MANIFEST's
        `out_of_scope_edits_detected` and this test together.
        """
        total_engineered = total_detected = 0
        for name, counts in self.block["per_file"].items():
            orig, resp = self.pair(name)
            by_record, _n, _i, _h = self.rr.diff(str(orig), str(resp))
            for edit in counts["out_of_scope_detail"]:
                total_engineered += 1
                reported = [f for f, _ov, _nv in by_record.get(edit["record"], [])]
                if edit["column"] in reported:
                    total_detected += 1
        self.assertEqual(total_engineered, 9, "fixture should engineer 9 out-of-scope edits")
        self.assertEqual(total_detected, 0,
                         "out-of-scope edits are now detected — the defect is fixed, "
                         "update MANIFEST and this test")

    def test_known_defect_amber_cell_answers_are_not_reported(self):
        """DEFECT: answers in AMBER cells are dropped by the audit.

        Amber means 'we could not read this field's condition — please check'. It is a genuine
        RA task, documented as such in SKILL.md. But `review_responses.YELLOW_HEX` matches only
        the yellow fill, so when the RA answers an amber cell the audit never mentions it. The
        fixture fills 5 amber cells; 0 are reported.
        """
        engineered = detected = 0
        for name, counts in self.block["per_file"].items():
            if not counts["amber_cells_filled"]:
                continue
            orig, resp = self.pair(name)
            by_record, _n, _i, _h = self.rr.diff(str(orig), str(resp))
            for rid in counts["amber_filled_record_ids"]:
                engineered += 1
                if any(f == "Adjuvant therapy given" for f, _o, _n2 in by_record.get(rid, [])):
                    detected += 1
        self.assertEqual(engineered, 5, "fixture should fill 5 amber cells")
        self.assertEqual(detected, 0,
                         "amber answers are now reported — the defect is fixed, "
                         "update MANIFEST and this test")

    def test_known_defect_gate_context_column_order_is_not_stable(self):
        """DEFECT (build_worklists.py): the gate-context columns come out in a random order.

        `build_workbook` collects them into a set and then inserts them at the front:

            context_set = {g for f in fields_with_work for g in prereq_map.get(f, []) ...}
            for gate in context_set: display_fields.insert(0, gate)

        Set iteration order over strings depends on PYTHONHASHSEED, so a workbook with two or
        more gate-context columns lays them out differently on different runs of the same
        command against the same data. `demo_followup` (gates: Sex, Status at follow-up) is
        such a workbook. Consequences: round-to-round worklists aren't diffable, RAs see the
        columns move, and no fixture built through it can be byte-reproducible.

        Pinning PYTHONHASHSEED to 0 and 2 makes the demonstration itself deterministic.
        """
        orders = {}
        for seed in ("0", "2"):
            out = self.out / f"hashseed_{seed}"
            env = dict(os.environ, PYTHONHASHSEED=seed)
            proc = subprocess.run(
                [sys.executable, str(BUILDER),
                 "--records-csv", str(FIXTURE / "records.csv"),
                 "--metadata-csv", str(FIXTURE / "datadictionary.csv"),
                 "--fields", str(FIXTURE / "qa_fields.yaml"),
                 "--out", str(out), "--id-field", "syn_id", "--round="],
                capture_output=True, text=True, timeout=300, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
            ws = openpyxl.load_workbook(
                out / "with_MDC" / "demo_followup_site_alpha.xlsx").active
            orders[seed] = [c.value for c in ws[1]]
        self.assertEqual(set(orders["0"]), set(orders["2"]),
                         "the same columns should appear either way")
        self.assertNotEqual(orders["0"], orders["2"],
                            "column order is now stable — the defect is fixed, delete this test")

    def test_known_defect_first_data_column_ignored_with_a_single_id_column(self):
        """DEFECT: `_yellow_keys(orig_ws, id_col_count=2)` hardcodes TWO id columns.

        `build_worklists.py` writes `--id-field` plus whatever `--extra-id-cols` says: one id
        column by default. When there is one, the first DATA column is column 2 — and the
        audit's scan starts at column 3, so every yellow cell in that column, and every RA
        answer in it, is invisible.

        The SYN fixture's two workbooks happen to dodge this: gate-context columns are inserted
        at the front, so column 2 is never flagged in either. This test reproduces it directly
        on a one-field workbook: 15 answered cells in, 0 records out.
        """
        cfg = self.out / "one_field.yaml"
        cfg.write_text("workbooks:\n  - name: onefield\n    title: One Field\n"
                       "    fields: [histology_grade]\n")
        build = self.out / "defect_build"
        proc = subprocess.run(
            [sys.executable, str(BUILDER),
             "--records-csv", str(FIXTURE / "records.csv"),
             "--metadata-csv", str(FIXTURE / "datadictionary.csv"),
             "--fields", str(cfg), "--out", str(build), "--id-field", "syn_id", "--round="],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1000:])
        src = build / "with_MDC" / "onefield_site_alpha.xlsx"
        wb = openpyxl.load_workbook(src)
        ws = wb.active
        self.assertEqual([c.value for c in ws[1]], ["syn_id", "Histology grade", "RESPONSE"])
        answered = 0
        for r in range(3, ws.max_row + 1):
            cell = ws.cell(row=r, column=2)
            if str(cell.fill.fgColor.rgb or "").upper().endswith("FFC7CE"):
                cell.value = "Poorly differentiated"
                answered += 1
        dst = build / "onefield_site_alpha_RETURNED.xlsx"
        wb.save(dst)
        self.assertEqual(answered, 15, "fixture should give 15 yellow cells in this workbook")
        by_record, _n, _i, _h = self.rr.diff(str(src), str(dst))
        self.assertEqual(len(by_record), 0,
                         "the first-data-column blind spot is fixed — delete this test")


if __name__ == "__main__":
    unittest.main(verbosity=2)
