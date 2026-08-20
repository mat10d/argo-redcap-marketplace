#!/usr/bin/env python3
"""Seeded generator for the SYN synthetic study fixture.

SYNTHETIC TEST STUDY — "SYN — Synthetic Colorectal Cohort". Every value in every
file this script writes is fabricated. No real people, sites, or data.

Regenerates, byte-identically on every run (stdlib only, no timestamps):

    datadictionary.csv   REDCap API-format metadata (45 fields, 3 forms)
    records.csv          200 flat raw-code records, 2 DAGs, engineered missingness
    linkage-source.csv   fake pathology sheet with engineered overlaps/conflicts
    qa_fields.yaml       build_worklists config (2 workbooks, 6 QA target fields)
    concept-note.md      half-page synthetic concept note
    intake.json          fake SIR-style intake record
    MANIFEST.json        every engineered count, for tests to assert exactly

Run:  python3 generate.py     (writes into its own directory)
"""

from __future__ import annotations

import csv
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20260820

SENTINELS = ["-666", "-777", "-888", "-999"]
MDC_CHOICES = "-666, Not applicable (MDC) | -777, Not asked (MDC) | -888, Don't know (MDC) | -999, Refused (MDC)"

DD_COLUMNS = [
    "field_name", "form_name", "section_header", "field_type", "field_label",
    "select_choices_or_calculations", "field_note",
    "text_validation_type_or_show_slider_number", "text_validation_min",
    "text_validation_max", "identifier", "branching_logic", "required_field",
    "custom_alignment", "question_number", "matrix_group_name", "matrix_ranking",
    "field_annotation",
]

AMBER_LOGIC = "datediff([dx_date],[surgery_date],'d') > 30"

# The six QA target fields (mixed forms) that qa_fields.yaml points at.
QA_FIELDS = ["pregnancy_status", "bleeding_severity", "histology_grade",
             "margin_status", "adjuvant_therapy", "recurrence_site"]


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


def build_data_dictionary():
    d = []
    # ---- demographics (14 fields) ------------------------------------------
    d.append(dd_row("syn_id", "demographics", "text",
                    "Synthetic participant ID (TEST DATA)",
                    section="SYNTHETIC TEST STUDY — no real data"))
    d.append(dd_row("consented", "demographics", "yesno", "Consented to synthetic study?"))
    d.append(dd_row("enrol_date", "demographics", "text", "Enrolment date",
                    val="date_dmy"))
    d.append(dd_row("age", "demographics", "text", "Age at enrolment (years)",
                    val="integer", vmin="18", vmax="95"))
    d.append(dd_row("sex", "demographics", "radio", "Sex",
                    choices="1, Male | 2, Female"))
    d.append(dd_row("education", "demographics", "dropdown", "Highest education level",
                    choices="1, None | 2, Primary | 3, Secondary | 4, Tertiary"))
    d.append(dd_row("marital_status", "demographics", "radio", "Marital status",
                    choices="1, Single | 2, Married | 3, Widowed | 4, Divorced"))
    d.append(dd_row("district", "demographics", "dropdown", "District of residence",
                    choices="1, North | 2, South | 3, East | 4, West | 5, Central"))
    d.append(dd_row("occupation", "demographics", "text", "Occupation",
                    note="Free text. If missing with a reason, enter an MDC code: "
                         "-666 not applicable, -777 not asked, -888 don't know, -999 refused."))
    d.append(dd_row("pregnancy_status", "demographics", "radio",
                    "Pregnancy status at enrolment",
                    choices="1, Not pregnant | 2, Pregnant | 3, Unsure",
                    branch="[sex] = '2'"))
    d.append(dd_row("alcohol_use", "demographics", "radio", "Alcohol use",
                    choices="1, Never | 2, Former | 3, Current",
                    branch="[age] >= 18"))
    d.append(dd_row("tobacco_use", "demographics", "yesno", "Ever used tobacco?"))
    d.append(dd_row("phone_available", "demographics", "yesno", "Phone contact available?"))
    d.append(dd_row("contact_notes", "demographics", "notes", "Contact notes"))
    # ---- clinical (20 fields) ----------------------------------------------
    d.append(dd_row("dx_date", "clinical", "text", "Date of diagnosis",
                    val="date_dmy", branch="[consented] = 1"))
    d.append(dd_row("dx_confirmed", "clinical", "yesno", "Diagnosis histologically confirmed?"))
    d.append(dd_row("tumor_site", "clinical", "radio", "Primary tumour site",
                    choices="1, Caecum/ascending | 2, Transverse | 3, Descending/sigmoid | 4, Rectum"))
    d.append(dd_row("symptoms", "clinical", "checkbox", "Presenting symptoms",
                    choices="1, Abdominal pain | 2, Weight loss | 3, Rectal bleeding | 4, Fatigue"))
    d.append(dd_row("symptom_onset", "clinical", "text", "Symptom onset date",
                    val="date_dmy"))
    d.append(dd_row("bleeding_severity", "clinical", "radio", "Rectal bleeding severity",
                    choices="1, Mild | 2, Moderate | 3, Severe",
                    branch="[symptoms(3)] = 1"))
    d.append(dd_row("weight_kg", "clinical", "text", "Weight (kg)",
                    val="number", vmin="30", vmax="150"))
    d.append(dd_row("height_cm", "clinical", "text", "Height (cm)",
                    val="integer", vmin="100", vmax="220"))
    d.append(dd_row("tnm_t", "clinical", "dropdown", "TNM: T stage",
                    choices="1, T1 | 2, T2 | 3, T3 | 4, T4"))
    d.append(dd_row("tnm_n", "clinical", "dropdown", "TNM: N stage",
                    choices="0, N0 | 1, N1 | 2, N2"))
    d.append(dd_row("tnm_m", "clinical", "dropdown", "TNM: M stage",
                    choices="0, M0 | 1, M1"))
    d.append(dd_row("histology_grade", "clinical", "dropdown", "Histology grade",
                    choices="1, Well differentiated | 2, Moderately differentiated | "
                            "3, Poorly differentiated | " + MDC_CHOICES))
    d.append(dd_row("margin_status", "clinical", "radio", "Resection margin status",
                    choices="1, Negative | 2, Positive | 3, Not assessed"))
    d.append(dd_row("cea_level", "clinical", "text", "CEA level (ng/mL)",
                    val="number"))
    d.append(dd_row("surgery_done", "clinical", "yesno", "Surgery performed?"))
    d.append(dd_row("surgery_date", "clinical", "text", "Date of surgery",
                    val="date_dmy", branch="[surgery_done] = 1"))
    d.append(dd_row("surgery_type", "clinical", "radio", "Type of surgery",
                    choices="1, Hemicolectomy | 2, Anterior resection | 3, APR",
                    branch="[surgery_done] = 1"))
    d.append(dd_row("adjuvant_therapy", "clinical", "radio", "Adjuvant therapy given",
                    choices="1, Chemotherapy | 2, Radiotherapy | 3, None | " + MDC_CHOICES,
                    branch=AMBER_LOGIC))
    d.append(dd_row("chemo_cycles", "clinical", "text", "Number of chemotherapy cycles",
                    val="integer", vmin="1", vmax="12",
                    branch="[adjuvant_therapy] = '1' AND [surgery_done] = 1"))
    d.append(dd_row("clinical_notes", "clinical", "notes", "Clinical notes"))
    # ---- follow_up (11 fields) ---------------------------------------------
    d.append(dd_row("fu_date", "follow_up", "text", "Follow-up date", val="date_dmy"))
    d.append(dd_row("follow_status", "follow_up", "radio", "Status at follow-up",
                    choices="1, Alive, no recurrence | 2, Recurrence | 3, Deceased | 4, Lost to follow-up"))
    d.append(dd_row("recurrence_date", "follow_up", "text", "Date of recurrence",
                    val="date_dmy", branch="[follow_status] = '2'"))
    d.append(dd_row("recurrence_site", "follow_up", "radio", "Site of recurrence",
                    choices="1, Local | 2, Liver | 3, Other distant",
                    branch="[follow_status] = '2'"))
    d.append(dd_row("death_date", "follow_up", "text", "Date of death",
                    val="date_dmy", branch="[follow_status] = '3'"))
    d.append(dd_row("qol_score", "follow_up", "text", "Quality-of-life score (0-100)",
                    val="integer", vmin="0", vmax="100"))
    d.append(dd_row("support_needed", "follow_up", "yesno", "Support services needed?",
                    branch="[follow_status] = '2' OR [follow_status] = '4'"))
    d.append(dd_row("fu_contact_method", "follow_up", "radio", "Follow-up contact method",
                    choices="1, In person | 2, Phone | 3, Relative"))
    d.append(dd_row("next_fu_date", "follow_up", "text", "Next follow-up date",
                    val="date_dmy"))
    d.append(dd_row("lost_reason", "follow_up", "radio", "Reason lost to follow-up",
                    choices="1, Moved away | 2, Declined | 3, Unreachable",
                    branch="[follow_status] = '4'"))
    d.append(dd_row("fu_notes", "follow_up", "notes", "Follow-up notes"))
    return d


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

N_ALPHA, N_BETA = 120, 80
NONCONSENT_IDS = ["SYN-0110", "SYN-0111", "SYN-0195", "SYN-0196"]

# Engineered counts: applicable-but-blank per QA field per DAG.
BLANKS = {
    "pregnancy_status":  {"site_alpha": 8,  "site_beta": 5},
    "bleeding_severity": {"site_alpha": 7,  "site_beta": 4},
    "histology_grade":   {"site_alpha": 10, "site_beta": 6},
    "margin_status":     {"site_alpha": 6,  "site_beta": 4},
    "recurrence_site":   {"site_alpha": 5,  "site_beta": 3},
}
# Sentinel (MDC) cells per field per DAG. adjuvant_therapy is the amber field:
# filled for ALL 200 records; its sentinel cells surface amber in with_MDC mode
# because its branching logic is unparseable.
SENTINEL_CELLS = {
    "histology_grade": {"site_alpha": 5, "site_beta": 3},
    "adjuvant_therapy": {"site_alpha": 9, "site_beta": 6},
}
OCCUPATIONS = ["Farmer", "Trader", "Teacher", "Driver", "Tailor", "Civil servant",
               "Fisher", "Retired", "Student", "Artisan"]


def rand_date(y0=2023, y1=2025):
    y = random.randint(y0, y1)
    m = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{y:04d}-{m:02d}-{day:02d}"


def make_record(i):
    sid = f"SYN-{i:04d}"
    dag = "site_alpha" if i <= N_ALPHA else "site_beta"
    r = {"syn_id": sid, "redcap_data_access_group": dag}
    consented = "0" if sid in NONCONSENT_IDS else "1"
    r["consented"] = consented
    r["enrol_date"] = rand_date(2023, 2024)
    r["age"] = str(random.randint(18, 95))
    r["sex"] = str(random.choices([1, 2], [45, 55])[0])
    r["education"] = str(random.randint(1, 4))
    r["marital_status"] = str(random.randint(1, 4))
    r["district"] = str(random.randint(1, 5))
    r["occupation"] = random.choice(OCCUPATIONS)
    r["pregnancy_status"] = str(random.choices([1, 2, 3], [70, 15, 15])[0]) if r["sex"] == "2" else ""
    r["alcohol_use"] = str(random.randint(1, 3))
    r["tobacco_use"] = str(random.randint(0, 1))
    r["phone_available"] = str(random.choices([1, 0], [80, 20])[0])
    r["contact_notes"] = ""
    r["dx_date"] = rand_date(2023, 2024) if consented == "1" else ""
    r["dx_confirmed"] = str(random.choices([1, 0], [85, 15])[0])
    r["tumor_site"] = str(random.randint(1, 4))
    ticks = [1 if random.random() < 0.4 else 0 for _ in range(4)]
    if sum(ticks) == 0:
        ticks[random.randint(0, 3)] = 1
    for k in range(4):
        r[f"symptoms___{k + 1}"] = str(ticks[k])
    r["symptom_onset"] = rand_date(2023, 2024)
    r["bleeding_severity"] = str(random.randint(1, 3)) if r["symptoms___3"] == "1" else ""
    r["weight_kg"] = f"{random.uniform(35, 120):.1f}"
    r["height_cm"] = str(random.randint(140, 200))
    r["tnm_t"] = str(random.randint(1, 4))
    r["tnm_n"] = str(random.randint(0, 2))
    r["tnm_m"] = str(random.choices([0, 1], [75, 25])[0])
    r["histology_grade"] = str(random.randint(1, 3))
    r["margin_status"] = str(random.choices([1, 2, 3], [60, 25, 15])[0])
    r["cea_level"] = f"{random.uniform(0.5, 60):.1f}"
    r["surgery_done"] = str(random.choices([1, 0], [80, 20])[0])
    if r["surgery_done"] == "1":
        r["surgery_date"] = rand_date(2024, 2025)
        r["surgery_type"] = str(random.randint(1, 3))
    else:
        r["surgery_date"] = ""
        r["surgery_type"] = ""
    r["adjuvant_therapy"] = str(random.choices([1, 2, 3], [40, 20, 40])[0])
    if r["adjuvant_therapy"] == "1" and r["surgery_done"] == "1":
        r["chemo_cycles"] = str(random.randint(1, 12))
    else:
        r["chemo_cycles"] = ""
    r["clinical_notes"] = ""
    r["fu_date"] = rand_date(2025, 2025)
    r["follow_status"] = str(random.choices([1, 2, 3, 4], [45, 30, 15, 10])[0])
    if r["follow_status"] == "2":
        r["recurrence_date"] = rand_date(2025, 2025)
        r["recurrence_site"] = str(random.randint(1, 3))
    else:
        r["recurrence_date"] = ""
        r["recurrence_site"] = ""
    r["death_date"] = rand_date(2025, 2025) if r["follow_status"] == "3" else ""
    r["qol_score"] = str(random.randint(20, 100))
    r["support_needed"] = str(random.randint(0, 1)) if r["follow_status"] in ("2", "4") else ""
    r["fu_contact_method"] = str(random.randint(1, 3))
    r["next_fu_date"] = rand_date(2025, 2025)
    r["lost_reason"] = str(random.randint(1, 3)) if r["follow_status"] == "4" else ""
    r["fu_notes"] = ""
    return r


def first_n(records, dag, n, eligible, skip=0):
    """First n record dicts (id order) in `dag` passing `eligible`, after skipping `skip`."""
    out, skipped = [], 0
    for r in records:
        if r["redcap_data_access_group"] != dag or not eligible(r):
            continue
        if skipped < skip:
            skipped += 1
            continue
        out.append(r)
        if len(out) == n:
            return out
    raise RuntimeError(f"pool exhausted: wanted {n} in {dag}, got {len(out)}")


def engineer(records):
    """Apply engineered blanks/sentinels. Returns {field: {dag: [ids]}}."""
    picks = {}

    def apply(field, dag_counts, eligible, value_fn, skip=0):
        picks.setdefault(field, {})
        for dag, n in dag_counts.items():
            chosen = first_n(records, dag, n, eligible, skip=skip)
            for j, r in enumerate(chosen):
                r[field] = value_fn(j)
            picks[field][dag] = [r["syn_id"] for r in chosen]

    blank = lambda j: ""
    # Applicable-but-blank (yellow) cells.
    apply("pregnancy_status", BLANKS["pregnancy_status"], lambda r: r["sex"] == "2", blank)
    apply("bleeding_severity", BLANKS["bleeding_severity"], lambda r: r["symptoms___3"] == "1", blank)
    apply("histology_grade", BLANKS["histology_grade"], lambda r: True, blank)
    apply("margin_status", BLANKS["margin_status"], lambda r: True, blank, skip=12)
    apply("recurrence_site", BLANKS["recurrence_site"], lambda r: r["follow_status"] == "2", blank)
    # Sentinel (MDC) cells — cycle through the four codes.
    picks["histology_grade_sentinel"] = {}
    picks["adjuvant_therapy_sentinel"] = {}
    for dag, n in SENTINEL_CELLS["histology_grade"].items():
        chosen = first_n(records, dag, n, lambda r: r["histology_grade"] != "", skip=20)
        for j, r in enumerate(chosen):
            r["histology_grade"] = SENTINELS[j % 4]
        picks["histology_grade_sentinel"][dag] = [r["syn_id"] for r in chosen]
    for dag, n in SENTINEL_CELLS["adjuvant_therapy"].items():
        chosen = first_n(records, dag, n, lambda r: True, skip=40)
        for j, r in enumerate(chosen):
            r["adjuvant_therapy"] = SENTINELS[j % 4]
            r["chemo_cycles"] = ""  # gate ([adjuvant_therapy]='1') now false
        picks["adjuvant_therapy_sentinel"][dag] = [r["syn_id"] for r in chosen]
    return picks


# ---------------------------------------------------------------------------
# Expected QA-worklist behaviour (mirrors build_worklists.py semantics)
# ---------------------------------------------------------------------------

def field_applicability(field, r):
    """(applies, certain) for the six QA fields, per build_worklists semantics."""
    if field == "pregnancy_status":
        return r["sex"] == "2", True
    if field == "bleeding_severity":
        return r["symptoms___3"] == "1", True
    if field == "recurrence_site":
        return r["follow_status"] == "2", True
    if field == "adjuvant_therapy":
        return True, False        # unparseable datediff gate -> uncertain (amber)
    return True, True             # histology_grade, margin_status: no branching


def expected_worklists(records, workbooks):
    out = {}
    for wb_name, fields in workbooks.items():
        out[wb_name] = {}
        for dag in ("site_alpha", "site_beta"):
            subset = [r for r in records if r["redcap_data_access_group"] == dag]
            for mode, flag_sentinels in (("with_MDC", True), ("no_MDC", False)):
                per_field_yellow = {f: 0 for f in fields}
                per_field_amber = {f: 0 for f in fields}
                rows = 0
                for r in subset:
                    row_flagged = False
                    for f in fields:
                        applies, certain = field_applicability(f, r)
                        if not applies:
                            continue
                        v = r[f].strip()
                        flagged = v == "" or (flag_sentinels and v in SENTINELS)
                        if flagged:
                            row_flagged = True
                            if certain:
                                per_field_yellow[f] += 1
                            else:
                                per_field_amber[f] += 1
                    if row_flagged:
                        rows += 1
                out[wb_name][f"{dag}/{mode}"] = {
                    "rows_with_work": rows,
                    "yellow_cells_per_field": per_field_yellow,
                    "amber_cells_per_field": per_field_amber,
                    "yellow_cells_total": sum(per_field_yellow.values()),
                    "amber_cells_total": sum(per_field_amber.values()),
                }
    return out


# ---------------------------------------------------------------------------
# Linkage source
# ---------------------------------------------------------------------------

LINKAGE_PLAN = {  # per shared field: engineered row classes
    "histology_grade": {"safe_fill": 12, "conflict": 7},
    "margin_status": {"safe_fill": 8, "conflict": 5},
}
N_ORPHANS = 5
N_MISSING_FROM_SOURCE = 5


def build_linkage(records):
    """Rows + exact class counts. Deterministic; derived from final record values."""
    valid = {"histology_grade": ["1", "2", "3"], "margin_status": ["1", "2", "3"]}
    classes = {f: {} for f in LINKAGE_PLAN}      # field -> id -> class
    for field, plan in LINKAGE_PLAN.items():
        blank_ids = [r["syn_id"] for r in records if r[field] == ""]
        filled_ids = [r["syn_id"] for r in records
                      if r[field] != "" and r[field] not in SENTINELS]
        sentinel_ids = [r["syn_id"] for r in records if r[field] in SENTINELS]
        for sid in blank_ids[:plan["safe_fill"]]:
            classes[field][sid] = "safe_fill"
        for sid in blank_ids[plan["safe_fill"]:]:
            classes[field][sid] = "both_blank"
        for sid in filled_ids[:plan["conflict"]]:
            classes[field][sid] = "conflict"
        for sid in filled_ids[plan["conflict"]:]:
            classes[field][sid] = "no_op"
        for sid in sentinel_ids:
            classes[field][sid] = "sentinel_redcap_source_blank"

    # Records missing from source: plain no-op on BOTH fields, taken from the end.
    plain = [r["syn_id"] for r in records
             if classes["histology_grade"].get(r["syn_id"]) == "no_op"
             and classes["margin_status"].get(r["syn_id"]) == "no_op"]
    missing_from_source = plain[-N_MISSING_FROM_SOURCE:]
    missing_set = set(missing_from_source)

    by_id = {r["syn_id"]: r for r in records}
    rows = []
    lab_no = 5000
    for r in records:
        sid = r["syn_id"]
        if sid in missing_set:
            continue
        lab_no += 1
        row = {"syn_id": sid, "path_lab_no": f"PL-{lab_no}"}
        for field in ("histology_grade", "margin_status"):
            cls = classes[field][sid]
            rv = by_id[sid][field]
            if cls == "safe_fill":
                row[field] = valid[field][(lab_no + len(field)) % 3]
            elif cls == "conflict":
                others = [c for c in valid[field] if c != rv]
                row[field] = others[lab_no % len(others)]
            elif cls == "no_op":
                row[field] = rv
            else:  # both_blank, sentinel_redcap_source_blank
                row[field] = ""
        rows.append(row)
    for k in range(1, N_ORPHANS + 1):
        lab_no += 1
        rows.append({"syn_id": f"SYN-{9000 + k:04d}", "path_lab_no": f"PL-{lab_no}",
                     "histology_grade": str((k % 3) + 1),
                     "margin_status": str(((k + 1) % 3) + 1)})

    counts = {}
    for field in LINKAGE_PLAN:
        c = {}
        for sid, cls in classes[field].items():
            if sid in missing_set:
                cls = "missing_from_source"
            c[cls] = c.get(cls, 0) + 1
        counts[field] = dict(sorted(c.items()))
    counts["orphan_rows"] = N_ORPHANS
    counts["missing_from_source_ids"] = missing_from_source
    counts["source_rows_total"] = len(rows)
    return rows, counts


# ---------------------------------------------------------------------------
# Static text files
# ---------------------------------------------------------------------------

CONCEPT_NOTE = """# Concept Note — SYN: Synthetic Colorectal Cohort

> **SYNTHETIC TEST STUDY — not real.** Every name, site, number, and record in
> this study is computer-generated fixture data for testing the ARGO REDCap
> plugin suite. There are no real participants and no real institutions.

**Principal Investigator:** Dr. Ada Synthetic (fictional)
**Sites:** Alpha Teaching Hospital (`site_alpha`), Beta General Hospital (`site_beta`) — both fictional
**Design:** Prospective observational cohort (simulated)
**Sample size:** n = 200 synthetic records (120 Alpha, 80 Beta)

## Background

Colorectal cancer outcomes data are commonly fragmented across clinical and
pathology systems. This synthetic cohort imitates that shape: a three-form
REDCap project (demographics, clinical, follow-up) plus a separate pathology
sheet that overlaps on histology grade and margin status.

## Objectives

1. Exercise QA worklist generation: engineered applicable-but-blank cells,
   branching logic in every shape the parser supports, one deliberately
   unparseable condition, and MDC sentinel codes (-666/-777/-888/-999).
2. Exercise record linkage: engineered safe-fills, conflicts, no-ops, orphan
   pathology rows, and REDCap records absent from the pathology sheet.
3. Provide a stable, seeded dataset for automated feasibility tests.

## Data

Record ID field is `syn_id` (deliberately not `record_id`). All counts of
engineered missingness are stated exactly in `MANIFEST.json`; tests assert
those numbers rather than approximations.
"""

QA_FIELDS_YAML = """# SYNTHETIC TEST STUDY fixture — build_worklists config for the SYN cohort.
# Two workbooks over the six QA target fields (mixed forms).
workbooks:
  - name: clinical_core
    title: Clinical Core
    fields: [bleeding_severity, histology_grade, margin_status, adjuvant_therapy]
  - name: demo_followup
    title: Demographics and Follow-up
    fields: [pregnancy_status, recurrence_site]
"""

INTAKE = {
    "record_id": "SYN-TEST-001",
    "project_title": "SYN — Synthetic Colorectal Cohort (SYNTHETIC TEST STUDY)",
    "pi_surname": "Synthetic",
    "study_status": "1",
    "project_created": "1",
    "dd_uploaded": "1",
    "user_rights_complete": "1",
    "data_imported": "1",
    "review_internal": "0",
    "review_pi": "0",
    "study_production": "0",
    "note": "Fake SIR-style intake record for the synthetic test study. Not a real study.",
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

    dd = build_data_dictionary()
    write_csv(os.path.join(HERE, "datadictionary.csv"), DD_COLUMNS, dd)

    records = [make_record(i) for i in range(1, N_ALPHA + N_BETA + 1)]
    picks = engineer(records)
    rec_columns = ["syn_id", "redcap_data_access_group"] + [
        c for f in dd for c in
        ([f"symptoms___{k}" for k in range(1, 5)] if f["field_name"] == "symptoms"
         else [f["field_name"]])
        if c != "syn_id"
    ]
    write_csv(os.path.join(HERE, "records.csv"), rec_columns, records)

    linkage_rows, linkage_counts = build_linkage(records)
    write_csv(os.path.join(HERE, "linkage-source.csv"),
              ["syn_id", "path_lab_no", "histology_grade", "margin_status"], linkage_rows)

    with open(os.path.join(HERE, "qa_fields.yaml"), "w") as fh:
        fh.write(QA_FIELDS_YAML)
    with open(os.path.join(HERE, "concept-note.md"), "w") as fh:
        fh.write(CONCEPT_NOTE)
    with open(os.path.join(HERE, "intake.json"), "w") as fh:
        json.dump(INTAKE, fh, indent=2, sort_keys=True)
        fh.write("\n")

    # Not-applicable blanks (branching false — must NOT be flagged), computed
    # from the final data.
    def na_counts(field, applicable):
        out = {}
        for dag in ("site_alpha", "site_beta"):
            out[dag] = sum(1 for r in records
                           if r["redcap_data_access_group"] == dag
                           and not applicable(r) and r[field] == "")
        return out

    not_applicable_blanks = {
        "pregnancy_status": na_counts("pregnancy_status", lambda r: r["sex"] == "2"),
        "bleeding_severity": na_counts("bleeding_severity", lambda r: r["symptoms___3"] == "1"),
        "recurrence_site": na_counts("recurrence_site", lambda r: r["follow_status"] == "2"),
        "dx_date": na_counts("dx_date", lambda r: r["consented"] == "1"),
        "surgery_date": na_counts("surgery_date", lambda r: r["surgery_done"] == "1"),
    }

    workbooks = {"clinical_core": ["bleeding_severity", "histology_grade",
                                   "margin_status", "adjuvant_therapy"],
                 "demo_followup": ["pregnancy_status", "recurrence_site"]}

    manifest = {
        "contract_version": 1,
        "synthetic": True,
        "study": {
            "title": "SYN — Synthetic Colorectal Cohort (SYNTHETIC TEST STUDY)",
            "record_id_field": "syn_id",
            "n_records": len(records),
            "dags": {"site_alpha": N_ALPHA, "site_beta": N_BETA},
            "nonconsented_ids": NONCONSENT_IDS,
        },
        "data_dictionary": {
            "n_fields": len(dd),
            "forms": {form: sum(1 for f in dd if f["form_name"] == form)
                      for form in ("demographics", "clinical", "follow_up")},
            "checkbox_field": "symptoms",
            "amber_field": "adjuvant_therapy",
            "amber_logic": AMBER_LOGIC,
            "mdc_select_fields": ["histology_grade", "adjuvant_therapy"],
            "mdc_field_note_field": "occupation",
            "branching_shapes": {
                "quoted": {"field": "pregnancy_status", "logic": "[sex] = '2'"},
                "unquoted": {"field": "dx_date", "logic": "[consented] = 1"},
                "checkbox": {"field": "bleeding_severity", "logic": "[symptoms(3)] = 1"},
                "numeric_comparison": {"field": "alcohol_use", "logic": "[age] >= 18"},
                "and_combo": {"field": "chemo_cycles",
                              "logic": "[adjuvant_therapy] = '1' AND [surgery_done] = 1"},
                "or_combo": {"field": "support_needed",
                             "logic": "[follow_status] = '2' OR [follow_status] = '4'"},
                "unparseable": {"field": "adjuvant_therapy", "logic": AMBER_LOGIC},
            },
        },
        "qa": {
            "target_fields": QA_FIELDS,
            "sentinel_codes": SENTINELS,
            "applicable_but_blank": BLANKS,
            "sentinel_cells": SENTINEL_CELLS,
            "engineered_cell_ids": picks,
            "not_applicable_blanks": not_applicable_blanks,
            "expected_worklists": expected_worklists(records, workbooks),
        },
        "linkage": linkage_counts,
    }
    with open(os.path.join(HERE, "MANIFEST.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("Wrote synthetic-study fixture files to", HERE)


if __name__ == "__main__":
    main()
