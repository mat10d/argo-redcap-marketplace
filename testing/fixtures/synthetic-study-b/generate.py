#!/usr/bin/env python3
"""Seeded generator for the SYN-B synthetic study fixture (the SECOND study).

SYNTHETIC TEST STUDY — "SYN-B — Synthetic Pathology & Biobank Sub-study".
Every value in every file this script writes is fabricated. No real people,
sites, or data.

WHY A SECOND STUDY
------------------
The analyst role has a task the single-study fixture cannot exercise: *merging
more than one database for analysis* (PLAN.md Phase 1.5, "Analyst /
multi-database merge-analysis"). That needs two studies that share an
identifier space, with the overlap ENGINEERED — some records agreeing, some
disagreeing, some present on only one side — so a test can assert exact
numbers instead of eyeballing a join.

SYN-B is a pathology/biobank sub-study recruiting *from* the SYN colorectal
cohort. It therefore:

  * has its OWN record ID, `synb_id` (SYNB-####), and CARRIES the parent
    cohort's record ID in a `syn_id` column — the ported-ID shape that real
    sub-studies have, and the thing that makes the two exports joinable with
    no crosswalk. `syn_id` is what every linkage here joins on;
  * repeats two of the parent study's field names verbatim —
    `histology_grade` and `margin_status` — because both studies record them
    off the same pathology report. These are the two COMPARABLE FIELDS the
    linkage diff runs on;
  * carries the identifying columns a real linkage is reasoned about:
    `hospital_no`, `first_name`, `surname`.

DEPENDS ON the primary fixture: the engineered agree/conflict/fill classes are
computed from `../synthetic-study/records.csv`, which is committed. If that
file is regenerated, regenerate this one too and re-commit both.

WHY THE PARENT REGISTRY LIVES HERE
----------------------------------
Establishing a link is done on IDENTITY columns — hospital number, name,
surname — and the primary fixture predates them: it holds no names, and it is
byte-frozen because four other suites assert against it. So this generator also
writes `parent_registry.csv`: the SYN cohort's identity-only export, derived
deterministically from `../synthetic-study/records.csv` (one row per SYN
participant; no clinical data copied). It is the PARENT side of every
hard-link test, and it is regenerated here rather than hand-maintained, so it
can never drift from the primary it comes from.

Regenerates byte-identically on every run (stdlib only, no timestamps):

    datadictionary.csv   REDCap API-format metadata (19 fields, 2 forms)
    records.csv          60 flat raw-code records, 2 DAGs (the CHILD side)
    parent_registry.csv  200 identity rows for the SYN cohort (the PARENT side)
    MANIFEST.json        every engineered count, for tests to assert exactly

Run:  python3 generate.py     (writes into its own directory)
"""

from __future__ import annotations

import csv
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
PRIMARY = os.path.join(os.path.dirname(HERE), "synthetic-study")
SEED = 20260821

SENTINELS = ["-666", "-777", "-888", "-999"]
MDC_CHOICES = ("-666, Not applicable (MDC) | -777, Not asked (MDC) | "
               "-888, Don't know (MDC) | -999, Refused (MDC)")

DD_COLUMNS = [
    "field_name", "form_name", "section_header", "field_type", "field_label",
    "select_choices_or_calculations", "field_note",
    "text_validation_type_or_show_slider_number", "text_validation_min",
    "text_validation_max", "identifier", "branching_logic", "required_field",
    "custom_alignment", "question_number", "matrix_group_name", "matrix_ranking",
    "field_annotation",
]

# The two fields SYN-B shares, by name and by coding, with the primary study.
# Everything about the engineered overlap is expressed in terms of these.
COMPARABLE_FIELDS = ["histology_grade", "margin_status"]
VALID = {"histology_grade": ["1", "2", "3"], "margin_status": ["1", "2", "3"]}

# ---------------------------------------------------------------------------
# Engineered overlap sizes. These are THE numbers the tests assert; MANIFEST.json
# restates them (plus everything derived from them) for the tests to read.
# ---------------------------------------------------------------------------
N_AGREE = 20        # shared ids, SYN-B agrees with the primary on BOTH fields
N_CONFLICT = 12     # shared ids, SYN-B disagrees with the primary on BOTH fields
N_FILL_GRADE = 8    # shared ids, primary histology_grade blank, SYN-B has a value
N_FILL_MARGIN = 5   # shared ids, primary margin_status  blank, SYN-B has a value
N_B_ONLY = 15       # ids in SYN-B that do not exist in the primary study at all
# shared total = 45; SYN-B total = 60; primary-only = 200 - 45 = 155

B_ONLY_ID_BASE = 8000   # SYN-8001 .. SYN-8015 (the primary study stops at SYN-0200,
                        # and its pathology fixture's unmatched rows use SYN-90xx)

# ---------------------------------------------------------------------------
# Engineered IDENTITY truth — what the hard-link flow is tested against.
#
# The link is established on identity, so the fixture has to carry identity that
# is mostly consistent and deliberately, countably, not always. All of it is
# derived from the record ID with no randomness, so adding it left every
# pre-existing value in records.csv byte-identical.
# ---------------------------------------------------------------------------

# Fabricated name pools. No real person is intended; the two lists are prime-ish
# lengths so index arithmetic spreads them without repeating in lockstep.
GIVEN_NAMES = [
    "Adaeze", "Bankole", "Chidinma", "Damilola", "Ebele", "Folasade", "Gbenga",
    "Halima", "Ifeoma", "Jumoke", "Kelechi", "Lanre", "Maryam", "Nkechi",
    "Obiageli", "Patience", "Rukayat", "Segun", "Temitope", "Uchenna",
    "Victoria", "Wale", "Yewande", "Zainab", "Amaka", "Bode", "Chinedu",
    "Dayo", "Emeka",
]
SURNAMES = [
    "Abiodun", "Balogun", "Chukwu", "Danjuma", "Eze", "Fashola", "Garba",
    "Hassan", "Ibrahim", "Jibril", "Kalu", "Lawal", "Mbeki", "Nwosu",
    "Okonkwo", "Popoola", "Quadri", "Rotimi", "Sanusi", "Tijani", "Umeh",
    "Vaughan", "Williams", "Yusuf", "Zubairu", "Adeleke", "Bassey",
]

# Which shared records the CHILD study spells differently from the PARENT.
# Positions into sorted(shared_ids); disjoint from the hospital-number wrinkles
# below so each engineered defect can be counted on its own.
NAME_MISMATCH_POSITIONS = {0: "surname_typo", 10: "surname_swap", 20: "first_name"}

# Hospital number is the OTHER plausible join key, and it is deliberately the
# weaker one: five shared child records never had it recorded and two carry a
# transposed digit. 45 - 5 - 2 = 38 shared records match on hospital_no against
# 45 on syn_id — which is exactly the reasoning the key survey has to surface.
HOSPITAL_BLANK_POSITIONS = [3, 8, 13, 18, 23]
HOSPITAL_TYPO_POSITIONS = [5, 15]

# The parent side of the link: identity only. No clinical column is copied out
# of the primary fixture — this file exists to be joined against, not analysed.
PARENT_REGISTRY_COLUMNS = ["syn_id", "redcap_data_access_group",
                           "hospital_no", "first_name", "surname"]


def dd_row(name, form, ftype, label, choices="", note="", val="", vmin="", vmax="",
           branch="", section=""):
    return {
        "field_name": name, "form_name": form, "section_header": section,
        "field_type": ftype, "field_label": label,
        "select_choices_or_calculations": choices, "field_note": note,
        "text_validation_type_or_show_slider_number": val,
        "text_validation_min": vmin, "text_validation_max": vmax,
        "identifier": "", "branching_logic": branch, "required_field": "",
        "custom_alignment": "", "question_number": "", "matrix_group_name": "",
        "matrix_ranking": "", "field_annotation": "",
    }


# ---------------------------------------------------------------------------
# Identity: names and hospital numbers, derived from the ID with no randomness
# ---------------------------------------------------------------------------

def id_number(sid: str) -> int:
    """The numeric part of SYN-0007 / SYNB-0007 — the seed for everything below."""
    return int(sid.rsplit("-", 1)[1])


def given_name_for(sid: str) -> str:
    return GIVEN_NAMES[(id_number(sid) * 7) % len(GIVEN_NAMES)]


def surname_for(sid: str) -> str:
    return SURNAMES[(id_number(sid) * 11) % len(SURNAMES)]


def hospital_no_for(sid: str) -> str:
    """A hospital number that looks nothing like the record ID but is unique per person."""
    return f"HOSP-{100000 + id_number(sid) * 37:06d}"


def misspell(word: str) -> str:
    """Swap the last two letters — a transcription slip, not a different person."""
    if len(word) < 2 or word[-1] == word[-2]:
        return word[:-1] + ("a" if word[-1] != "a" else "e")
    return word[:-2] + word[-1] + word[-2]


def transpose_digits(value: str) -> str:
    """The same slip on a hospital number: last two digits swapped."""
    if len(value) < 2 or value[-1] == value[-2]:
        return value[:-1] + ("0" if value[-1] != "0" else "1")
    return value[:-2] + value[-1] + value[-2]


def build_data_dictionary():
    """19 fields over 2 forms. Two of them deliberately match the primary study."""
    d = []
    # ---- pathology (13 fields) ---------------------------------------------
    d.append(dd_row("synb_id", "pathology", "text",
                    "SYN-B record ID (TEST DATA)",
                    note="This study's OWN record ID. The linkage writes this back "
                         "alongside the parent cohort's number.",
                    section="SYNTHETIC TEST STUDY — no real data"))
    d.append(dd_row("syn_id", "pathology", "text",
                    "Parent cohort record ID — this participant's ID in the SYN cohort",
                    note="Ported from the SYN colorectal cohort. This is what makes the "
                         "two studies linkable."))
    d.append(dd_row("hospital_no", "pathology", "text", "Hospital number"))
    d.append(dd_row("first_name", "pathology", "text", "First name"))
    d[-1]["identifier"] = "y"
    d.append(dd_row("surname", "pathology", "text", "Surname"))
    d[-1]["identifier"] = "y"
    d.append(dd_row("path_lab_no", "pathology", "text", "Pathology laboratory number"))
    d.append(dd_row("accession_date", "pathology", "text", "Specimen accession date",
                    val="date_dmy"))
    d.append(dd_row("specimen_type", "pathology", "radio", "Specimen type",
                    choices="1, Biopsy | 2, Resection | 3, Polypectomy"))
    # --- comparable field 1 (same name + same codes as the primary study) ---
    d.append(dd_row("histology_grade", "pathology", "dropdown", "Histology grade",
                    choices="1, Well differentiated | 2, Moderately differentiated | "
                            "3, Poorly differentiated | " + MDC_CHOICES,
                    note="Recorded in both studies off the same pathology report."))
    # --- comparable field 2 -------------------------------------------------
    d.append(dd_row("margin_status", "pathology", "radio", "Resection margin status",
                    choices="1, Negative | 2, Positive | 3, Not assessed",
                    note="Recorded in both studies off the same pathology report.",
                    branch="[specimen_type] = '2'"))
    d.append(dd_row("tumor_size_mm", "pathology", "text", "Largest tumour dimension (mm)",
                    val="integer", vmin="1", vmax="200"))
    d.append(dd_row("nodes_examined", "pathology", "text", "Lymph nodes examined",
                    val="integer", vmin="0", vmax="60"))
    d.append(dd_row("nodes_positive", "pathology", "text", "Lymph nodes positive",
                    val="integer", vmin="0", vmax="60",
                    branch="[nodes_examined] > 0"))
    # ---- biobank (6 fields) ------------------------------------------------
    d.append(dd_row("msi_status", "biobank", "radio", "Microsatellite instability status",
                    choices="1, MSS | 2, MSI-low | 3, MSI-high | " + MDC_CHOICES))
    d.append(dd_row("kras_result", "biobank", "radio", "KRAS mutation result",
                    choices="1, Wild type | 2, Mutant | " + MDC_CHOICES))
    d.append(dd_row("biobank_consent", "biobank", "yesno",
                    "Consented to biobank storage?"))
    d.append(dd_row("sample_stored", "biobank", "yesno", "Sample stored in biobank?",
                    branch="[biobank_consent] = 1"))
    d.append(dd_row("storage_site", "biobank", "radio", "Storage location",
                    choices="1, Alpha freezer | 2, Beta freezer | 3, Central repository",
                    branch="[sample_stored] = 1"))
    d.append(dd_row("path_notes", "biobank", "notes", "Pathology notes"))
    return d


# ---------------------------------------------------------------------------
# Read the primary study
# ---------------------------------------------------------------------------

def load_primary():
    with open(os.path.join(PRIMARY, "records.csv"), newline="") as fh:
        return list(csv.DictReader(fh))


def pick_shared(primary):
    """Choose which primary ids land in which engineered class.

    Selection is by ID ORDER, not randomly, so it is stable and easy to read
    back out of the MANIFEST. Classes are disjoint by construction.
    """
    used = set()

    def take(n, predicate):
        out = []
        for r in primary:
            sid = r["syn_id"]
            if sid in used or not predicate(r):
                continue
            used.add(sid)
            out.append(sid)
            if len(out) == n:
                return out
        raise RuntimeError(f"pool exhausted: wanted {n}, got {len(out)}")

    def solid(r):
        """Primary holds a real (non-blank, non-MDC) value in BOTH fields."""
        return all(r[f] != "" and r[f] not in SENTINELS for f in COMPARABLE_FIELDS)

    groups = {
        # Order matters only in that the fill groups must claim the blank ids
        # before the "solid" groups walk the same list; they cannot collide
        # anyway (a blank id is not solid), but taking them first keeps the
        # chosen ids at the low end of the ID range for both classes.
        "fill_grade": take(N_FILL_GRADE, lambda r: r["histology_grade"] == ""),
        "fill_margin": take(N_FILL_MARGIN, lambda r: r["margin_status"] == ""),
        "conflict": take(N_CONFLICT, solid),
        "agree": take(N_AGREE, solid),
    }
    return groups


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def rand_date(y0=2024, y1=2025):
    y = random.randint(y0, y1)
    m = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{y:04d}-{m:02d}-{day:02d}"


def other_value(field, current):
    """A valid code for `field` that is deliberately NOT `current` — the engineered
    disagreement. Chosen deterministically so the fixture is byte-stable."""
    options = [v for v in VALID[field] if v != current]
    return options[len(current) % len(options)]


def make_record(sid, dag, grade, margin, lab_seq, synb_id, identity):
    """One SYN-B record. The two comparable fields and the identity columns are
    passed in (they carry the engineered classes); everything else is seeded filler.

    The identity columns are assigned WITHOUT touching `random`, so adding them
    left every pre-existing value in records.csv byte-identical.
    """
    r = {"synb_id": synb_id, "syn_id": sid, "redcap_data_access_group": dag}
    r["hospital_no"] = identity["hospital_no"]
    r["first_name"] = identity["first_name"]
    r["surname"] = identity["surname"]
    r["path_lab_no"] = f"BX-{7000 + lab_seq}"
    r["accession_date"] = rand_date(2024, 2025)
    # specimen_type drives margin_status's branching logic. Keep it '2'
    # (resection) whenever SYN-B actually carries a margin value, so the
    # fixture never contains a value under a false branch.
    r["specimen_type"] = "2" if margin != "" else str(random.choice([1, 3]))
    r["histology_grade"] = grade
    r["margin_status"] = margin
    r["tumor_size_mm"] = str(random.randint(5, 120))
    examined = random.randint(0, 30)
    r["nodes_examined"] = str(examined)
    r["nodes_positive"] = str(random.randint(0, examined)) if examined > 0 else ""
    r["msi_status"] = str(random.choices([1, 2, 3], [70, 10, 20])[0])
    r["kras_result"] = str(random.choices([1, 2], [60, 40])[0])
    consent = random.choices([1, 0], [85, 15])[0]
    r["biobank_consent"] = str(consent)
    if consent == 1:
        stored = random.choices([1, 0], [80, 20])[0]
        r["sample_stored"] = str(stored)
        r["storage_site"] = str(random.randint(1, 3)) if stored == 1 else ""
    else:
        r["sample_stored"] = ""
        r["storage_site"] = ""
    r["path_notes"] = ""
    return r


def build_records(primary, groups):
    by_id = {r["syn_id"]: r for r in primary}
    classes = {}          # syn_id -> class name
    plan = []             # (syn_id, dag, grade, margin) in output order

    for sid in groups["fill_grade"]:
        p = by_id[sid]
        # Primary is blank here; SYN-B supplies a value -> a safe FILL.
        # SYN-B leaves margin blank so this class contributes exactly one
        # fill cell and one no-op cell.
        plan.append((sid, p["redcap_data_access_group"],
                     VALID["histology_grade"][len(sid) % 3], ""))
        classes[sid] = "fill_grade"
    for sid in groups["fill_margin"]:
        p = by_id[sid]
        plan.append((sid, p["redcap_data_access_group"],
                     "", VALID["margin_status"][(len(sid) + 1) % 3]))
        classes[sid] = "fill_margin"
    for sid in groups["conflict"]:
        p = by_id[sid]
        plan.append((sid, p["redcap_data_access_group"],
                     other_value("histology_grade", p["histology_grade"]),
                     other_value("margin_status", p["margin_status"])))
        classes[sid] = "conflict"
    for sid in groups["agree"]:
        p = by_id[sid]
        plan.append((sid, p["redcap_data_access_group"],
                     p["histology_grade"], p["margin_status"]))
        classes[sid] = "agree"
    # Records that exist only in SYN-B: no counterpart in the primary study at
    # all. On the linkage read side these are the records with NO PARENT MATCH.
    for k in range(1, N_B_ONLY + 1):
        sid = f"SYN-{B_ONLY_ID_BASE + k:04d}"
        plan.append((sid, "site_gamma",
                     VALID["histology_grade"][k % 3],
                     VALID["margin_status"][(k + 2) % 3]))
        classes[sid] = "b_only"

    plan.sort(key=lambda t: t[0])          # emit in ID order
    parent_identity, child_identity, engineered = engineer_identity(
        [r["syn_id"] for r in primary], [t[0] for t in plan])
    records = [make_record(sid, dag, grade, margin, i + 1,
                           f"SYNB-{i + 1:04d}", child_identity[sid])
               for i, (sid, dag, grade, margin) in enumerate(plan)]
    return records, classes, parent_identity, engineered


def engineer_identity(primary_ids, child_ids):
    """Who each record says it is, on both sides, and where the two disagree.

    Identity is derived from the participant's parent-cohort ID, so a shared
    record is the SAME person on both sides by construction. Then three
    engineered discrepancies are introduced on the CHILD side (a mistyped
    surname, a wholly different surname, a mistyped first name) and seven
    engineered hospital-number gaps (five never recorded, two transposed), so
    the tests can assert exact numbers for the name-review table and for why
    the hospital number is the WEAKER of the two candidate join keys.

    Returns (parent_identity, child_identity, engineered_counts).
    """
    shared = sorted(set(child_ids) & set(primary_ids))

    def identity(sid):
        return {"hospital_no": hospital_no_for(sid),
                "first_name": given_name_for(sid),
                "surname": surname_for(sid)}

    parent = {sid: identity(sid) for sid in sorted(set(primary_ids))}
    child = {sid: identity(sid) for sid in sorted(set(child_ids))}

    name_mismatch = {}
    for pos, kind in sorted(NAME_MISMATCH_POSITIONS.items()):
        sid = shared[pos]
        if kind == "surname_typo":
            child[sid]["surname"] = misspell(parent[sid]["surname"])
        elif kind == "surname_swap":
            child[sid]["surname"] = SURNAMES[
                (SURNAMES.index(parent[sid]["surname"]) + 5) % len(SURNAMES)]
        elif kind == "first_name":
            child[sid]["first_name"] = misspell(parent[sid]["first_name"])
        else:                                     # pragma: no cover - guard
            raise RuntimeError(f"unknown name-mismatch kind {kind!r}")
        differs = [f for f in ("first_name", "surname")
                   if child[sid][f] != parent[sid][f]]
        if len(differs) != 1:
            raise RuntimeError(f"{sid}: {kind} changed {differs}, wanted exactly one field")
        name_mismatch[sid] = differs[0]

    parent_hospital_numbers = {v["hospital_no"] for v in parent.values()}
    blanked, mistyped = [], []
    for pos in HOSPITAL_BLANK_POSITIONS:
        sid = shared[pos]
        child[sid]["hospital_no"] = ""
        blanked.append(sid)
    for pos in HOSPITAL_TYPO_POSITIONS:
        sid = shared[pos]
        child[sid]["hospital_no"] = transpose_digits(parent[sid]["hospital_no"])
        if child[sid]["hospital_no"] in parent_hospital_numbers:
            raise RuntimeError(f"{sid}: the mistyped hospital number collides with a real one")
        mistyped.append(sid)

    matching_hospital = [sid for sid in shared
                         if child[sid]["hospital_no"]
                         and child[sid]["hospital_no"] == parent[sid]["hospital_no"]]
    engineered = {
        "name_mismatch": name_mismatch,
        "hospital_blank": sorted(blanked),
        "hospital_typo": sorted(mistyped),
        "hospital_matching": matching_hospital,
        "shared": shared,
    }
    return parent, child, engineered


# ---------------------------------------------------------------------------
# Expected linkage-diff outcome (mirrors argo_diff.classify semantics)
# ---------------------------------------------------------------------------

def expected_diff(primary, records):
    """What diff_payload.py must report with
        --computed <SYN-B records>  --current <primary records>
        --id-field syn_id  --fields histology_grade,margin_status

    Computed here from the finished data rather than asserted from the plan, so
    the MANIFEST can never drift from the CSVs sitting next to it.

    NOTE the orphan row: diff_records() iterates the COMPUTED side and treats a
    missing current record as all-blank, so every SYN-B-only id is classified
    FILL. That is recorded separately below (`orphan_cells_classified_fill`)
    because a test asserts the current behaviour AND flags it.
    """
    by_id = {r["syn_id"]: r for r in primary}
    counts = {"fill": 0, "conflict": 0, "noop": 0}
    shared = {"fill": 0, "conflict": 0, "noop": 0}
    orphan_fill = 0
    update_rows = conflict_rows = overwrite_rows = 0

    for r in records:
        cur = by_id.get(r["syn_id"])
        row_fill = row_conf = 0
        for f in COMPARABLE_FIELDS:
            new = r[f].strip()
            old = (cur[f].strip() if cur else "")
            if old == new:
                verdict = "noop"
            elif old == "":
                verdict = "fill" if new != "" else "noop"
            elif new == "":
                verdict = "noop"
            else:
                verdict = "conflict"
            counts[verdict] += 1
            if cur is None:
                if verdict == "fill":
                    orphan_fill += 1
            else:
                shared[verdict] += 1
            row_fill += verdict == "fill"
            row_conf += verdict == "conflict"
        update_rows += row_fill > 0
        conflict_rows += row_conf
        overwrite_rows += row_conf > 0

    return {
        "id_field": "syn_id",
        "compared_fields": COMPARABLE_FIELDS,
        "cells_compared": len(records) * len(COMPARABLE_FIELDS),
        "fill_cells": counts["fill"],
        "conflict_cells": counts["conflict"],
        "noop_cells": counts["noop"],
        "fill_cells_shared_ids_only": shared["fill"],
        "conflict_cells_shared_ids_only": shared["conflict"],
        "noop_cells_shared_ids_only": shared["noop"],
        "orphan_cells_classified_fill": orphan_fill,
        "update_csv_rows": update_rows,
        "conflicts_csv_rows": conflict_rows,
        "overwrite_csv_rows": overwrite_rows,
    }


# ---------------------------------------------------------------------------
# Expected HARD-LINK outcome (what link_studies.py must produce)
# ---------------------------------------------------------------------------

def linking_manifest(records, registry, engineered):
    """Every number the hard-link flow is asserted against.

    Computed from the finished CSVs rather than restated from the plan, so the
    MANIFEST can never drift from the files sitting next to it.
    """
    child_ids = {r["syn_id"] for r in records}
    parent_ids = {r["syn_id"] for r in registry}
    matched = sorted(child_ids & parent_ids)
    name_mismatch = engineered["name_mismatch"]
    by_field = {}
    for sid, field in name_mismatch.items():
        by_field[field] = by_field.get(field, 0) + 1
    return {
        "parent_file": "parent_registry.csv",
        "child_file": "records.csv",
        "parent_name": "syn",
        "child_name": "synb",
        "join_key": "syn_id",
        "child_record_id_field": "synb_id",
        "n_parent_records": len(registry),
        "n_child_records": len(records),
        # The three join results, in the plain words the skill uses for them.
        "n_matched": len(matched),
        "n_child_only": len(child_ids - parent_ids),
        "n_parent_only": len(parent_ids - child_ids),
        # The name-review table: matched pairs whose names disagree.
        "name_columns": ["first_name", "surname"],
        "n_name_discrepancies": len(name_mismatch),
        "n_name_discrepancies_by_field": dict(sorted(by_field.items())),
        "ids_name_discrepancy": sorted(name_mismatch),
        # Why hospital_no is the WEAKER candidate key: 38 of the 45 matched
        # records agree on it, against 45 on syn_id.
        "n_hospital_no_matches": len(engineered["hospital_matching"]),
        "ids_hospital_no_blank": engineered["hospital_blank"],
        "ids_hospital_no_mistyped": engineered["hospital_typo"],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_csv(path, columns, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    random.seed(SEED)

    primary = load_primary()
    dd = build_data_dictionary()
    write_csv(os.path.join(HERE, "datadictionary.csv"), DD_COLUMNS, dd)

    groups = pick_shared(primary)
    records, classes, parent_identity, engineered = build_records(primary, groups)
    rec_columns = (["synb_id", "redcap_data_access_group"]
                   + [f["field_name"] for f in dd if f["field_name"] != "synb_id"])
    write_csv(os.path.join(HERE, "records.csv"), rec_columns, records)

    # The PARENT side of the link: identity only, one row per SYN participant,
    # derived from the primary fixture (see the module docstring for why it is
    # written here rather than in synthetic-study/).
    registry = [{"syn_id": r["syn_id"],
                 "redcap_data_access_group": r["redcap_data_access_group"],
                 **parent_identity[r["syn_id"]]}
                for r in primary]
    write_csv(os.path.join(HERE, "parent_registry.csv"), PARENT_REGISTRY_COLUMNS, registry)

    primary_ids = {r["syn_id"] for r in primary}
    b_ids = {r["syn_id"] for r in records}
    shared_ids = sorted(primary_ids & b_ids)
    dags = {}
    for r in records:
        dags[r["redcap_data_access_group"]] = dags.get(r["redcap_data_access_group"], 0) + 1

    manifest = {
        "contract_version": 1,
        "synthetic": True,
        "study": {
            "title": "SYN-B — Synthetic Pathology & Biobank Sub-study (SYNTHETIC TEST STUDY)",
            "record_id_field": "synb_id",
            "parent_id_field": "syn_id",
            "n_records": len(records),
            "dags": dict(sorted(dags.items())),
            "shares_id_space_with": "testing/fixtures/synthetic-study",
        },
        "data_dictionary": {
            "n_fields": len(dd),
            "forms": {form: sum(1 for f in dd if f["form_name"] == form)
                      for form in ("pathology", "biobank")},
            "comparable_fields": COMPARABLE_FIELDS,
            "comparable_fields_note":
                "Same field names and same coded values as the primary study, so the "
                "two exports join with no crosswalk.",
        },
        "overlap": {
            # ---- the engineered numbers, stated exactly -------------------
            "n_records_study_b": len(records),
            "n_records_primary": len(primary),
            "n_shared_ids": len(shared_ids),
            "n_shared_agreeing": N_AGREE,
            "n_shared_conflicting": N_CONFLICT,
            "n_shared_conflicting_fields": len(COMPARABLE_FIELDS),
            "n_shared_fill_histology_grade": N_FILL_GRADE,
            "n_shared_fill_margin_status": N_FILL_MARGIN,
            "n_only_in_study_b": N_B_ONLY,
            "n_only_in_primary": len(primary_ids - b_ids),
            "ids_by_class": {
                cls: sorted(sid for sid, c in classes.items() if c == cls)
                for cls in ("agree", "conflict", "fill_grade", "fill_margin", "b_only")
            },
        },
        "expected_diff": expected_diff(primary, records),
        "linking": linking_manifest(records, registry, engineered),
    }
    with open(os.path.join(HERE, "MANIFEST.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("Wrote synthetic-study-b fixture files to", HERE)


if __name__ == "__main__":
    main()
