#!/usr/bin/env python3
"""pathology.py — the ARGO standard for a study with slides in PathPresenter, and its tools.

A pathology study is two systems joined only by a file name: REDCap holds identity and the slide
tracker, PathPresenter holds the images, their metadata and the readers' eCRF. The standard below
was settled across three live builds (P20 aim 1 PID 197 and aim 2 PID 190, retrospective; the
PD-1 trial PID 272, prospective) and the first PathPresenter requests (decided 2026-11-17):

  - Every pathology build starts from a PathPresenter request (PID 233). No request, no build.
  - The case key is the histology number, flagged as an identifier, so it never downloads.
  - The slide file name is the link: histology number, then stain (H661-26-CD8.svs; a second
    slide of the same stain H661-26-CD8-2.svs). PathPresenter carries the Pathology REDCap ID in
    its metadata, never a name or hospital number.
  - REDCap has the PD-1 slide block: one name field per slide, per stain, up to 3.
  - Readers' results (counts, grades, labels) live in the PathPresenter eCRF and are exported;
    REDCap holds the slide tracker, not the scores.
  - New studies go on the OAU PathPresenter (argo-ccr) unless the request says MSK.

    python3 pathology.py plan <SIR record> [--out DIR]          # which path, what's missing
    python3 pathology.py setup <PathPresenter request> --out DIR [--study-code CODE]
                                                                 # the PathPresenter side
    python3 pathology.py check-slide-list <file.csv|xlsx>        # analysis requests (path D)
    python3 pathology.py audit <dd.csv>                          # an existing study vs the standard

Add `--from-json sir.json --pp-json pp.json` to `plan` / `setup` to work without access keys
(label exports of the two records). Nothing here writes to REDCap or PathPresenter.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
for _cand in (_here / "scripts",
              *(p / "plugins/argo-core/skills/redcap-api/scripts" for p in _here.parents)):
    if (_cand / "argo_redcap_client.py").exists():
        sys.path.insert(0, str(_cand))
        break

# --------------------------------------------------------------------------------------
# The REDCap side
# --------------------------------------------------------------------------------------

CASE_KEY = "histology_number"   # flagged Identifier = y on every pathology build
MAX_SLIDES_PER_STAIN = 3        # PD-1: up to 3 per stain; a 4th is reported, never stored
SITES = "1, OAUTHC | 2, LUTH | 3, MSK | 98, Other"

# The slide tracker: what the RA records about the glass and the upload. Not patient-reported,
# so no missing-data codes on these (dd_builder and validate_dd both read this set); the
# staining and imaging sites are ordinary fields and keep theirs, as on PD-1.
SLIDE_TRACKER_FIELDS = ("slide_found", "slide_type", "slide_rounds_imaged", "slide_retrieved",
                        "slide_pathpresenter", "qa_pathpresenter")
SLIDE_NAME_PREFIX = "slide_name_"
# Every pathology dictionary must have these, by these names.
REQUIRED_FIELDS = SLIDE_TRACKER_FIELDS + ("slide_staining_site", "slide_imaging_site")


def is_slide_tracker(var: str) -> bool:
    return var in SLIDE_TRACKER_FIELDS or var.startswith(SLIDE_NAME_PREFIX)


def stain_var(stain: str) -> str:
    """'H&E' -> 'he', 'CD8' -> 'cd8', 'Ki-67' -> 'ki67', 'PD-L1' -> 'pdl1'."""
    v = re.sub(r"[^a-z0-9]", "", stain.lower())
    if not v:
        raise ValueError(f"'{stain}' is not a stain name")
    return v


def slide_block(dd, stains, form=None):
    """Write the PD-1 slide block into a dd_builder.DD, for these stains, in this order."""
    stains = [s.strip() for s in stains if s.strip()]
    if not stains:
        raise ValueError("a pathology study needs at least one stain (H&E counts)")
    vars_ = [stain_var(s) for s in stains]
    if len(set(vars_)) != len(vars_):
        raise ValueError(f"two stains share a field name: {stains}")
    kw = {"form": form} if form else {}
    dd.field("slide_found", "radio", "Slide found", "1, Yes | 0, No", **kw)
    dd.field("slide_type", "checkbox", "Slides found for this case",
             " | ".join(f"{n}, {s}" for n, s in enumerate(stains, 1)),
             branching="[slide_found]='1'", required="y", **kw)
    dd.field("slide_rounds_imaged", "radio", "Slides per stain (blocks / re-scans)",
             " | ".join(f"{n}, {n}" for n in range(1, MAX_SLIDES_PER_STAIN + 1)),
             note="Repeat stains, extra blocks/levels or re-uploads of the same stain",
             branching="[slide_found]='1'", **kw)
    for code, (stain, v) in enumerate(zip(stains, vars_), 1):
        for n in range(1, MAX_SLIDES_PER_STAIN + 1):
            show = f"[slide_type({code})]='1'"
            if n > 1:
                more = " or ".join(f"[slide_rounds_imaged]='{k}'"
                                   for k in range(n, MAX_SLIDES_PER_STAIN + 1))
                show += f" and ({more})" if n < MAX_SLIDES_PER_STAIN else f" and {more}"
            dd.field(f"{SLIDE_NAME_PREFIX}{v}_{n}", "text", f"Slide name {stain} ({n})",
                     note=f"Exact PathPresenter file name, e.g. {example_name(stain, n)}",
                     branching=show, **kw)
    dd.field("slide_retrieved", "text", "Slide comments (why it was not found)",
             branching="[slide_found]='0'", required="y", **kw)
    dd.field("slide_staining_site", "radio", "Slide staining site", SITES, **kw)
    dd.field("slide_imaging_site", "radio", "Slide imaging site", SITES, **kw)
    dd.field("slide_pathpresenter", "radio",
             "Slide uploaded into PathPresenter database (to be completed by RA)",
             "1, Yes | 0, No", **kw)
    dd.field("qa_pathpresenter", "radio",
             "Slide confirmed in PathPresenter database (to be completed by QA manager)",
             "1, Yes | 0, No", branching="[slide_pathpresenter]='1'", **kw)


def case_key(dd, form=None):
    """The retrospective case key: the histology number, flagged, required."""
    kw = {"form": form} if form else {}
    dd.field(CASE_KEY, "text", "Histology number", identifier="y", required="y",
             note="As written on the glass and the pathology report, e.g. H661/26", **kw)


def example_name(stain: str, n: int = 1, histology: str = "H661/26") -> str:
    """The standard file name: histology number with '/' as '-', the stain, then -n from 2 on."""
    base = re.sub(r"[\s/_]+", "-", histology.strip().upper())
    tag = re.sub(r"[^A-Za-z0-9&]", "", stain).upper()
    return f"{base}-{tag}{'' if n == 1 else f'-{n}'}.svs"


def check_rows(rows, stains=None) -> list:
    """Errors for a pathology dictionary (rows as dicts keyed by REDCap's metadata names)."""
    by = {r["field_name"]: r for r in rows}
    errors = []
    if CASE_KEY not in by:
        errors.append(f"pathology: '{CASE_KEY}' is missing — it is the case key that finds the glass")
    elif by[CASE_KEY]["identifier"].lower() != "y":
        errors.append(f"pathology: '{CASE_KEY}' must have Identifier? = y, so it never downloads")
    for f in REQUIRED_FIELDS:
        if f not in by:
            errors.append(f"pathology: slide-tracker field '{f}' is missing (pathology.slide_block writes it)")
    if "slide_type" in by:
        choices = [c.split(",", 1)[1].strip() for c in by["slide_type"]["select_choices_or_calculations"].split("|")
                   if "," in c and not c.strip().startswith("-")]
        for stain in choices:
            v = stain_var(stain)
            for n in range(1, MAX_SLIDES_PER_STAIN + 1):
                if f"{SLIDE_NAME_PREFIX}{v}_{n}" not in by:
                    errors.append(f"pathology: stain '{stain}' has no '{SLIDE_NAME_PREFIX}{v}_{n}'")
        if stains:
            want = [s.strip() for s in stains]
            if [stain_var(s) for s in choices] != [stain_var(s) for s in want]:
                errors.append(f"pathology: slide_type lists {choices}, the PathPresenter request {want}")
    return errors


# --------------------------------------------------------------------------------------
# The request: which path a PathPresenter request takes
# --------------------------------------------------------------------------------------

PATHS = {
    "A": "New PathPresenter database, with a new REDCap build",
    "B": "New PathPresenter database for a REDCap that already exists: amend it, don't rebuild",
    "C": "New PathPresenter database with no REDCap request: nothing to build yet",
    "D": "Analysis study on slides already in PathPresenter: PathPresenter side only",
    "E": "Both a new database and an analysis study: path A or B, then D",
}


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


def ticked(rec: dict, field: str, code: str) -> bool:
    v = str(rec.get(f"{field}___{code}", "")).strip()
    return v not in ("", "0", "Unchecked")


def classify(pp: dict, sir: "dict | None") -> str:
    """The path for one PathPresenter request, given the Study Tracker record it links to."""
    new_db, analysis = ticked(pp, "request_type", "1"), ticked(pp, "request_type", "2")
    if not new_db and not analysis:
        new_db = True                     # filed before the request-type question existed
    if analysis and not new_db:
        return "D"
    submitted = str(pp.get("redcap_request_submitted", "")).strip().lower() in ("1", "yes")
    if not submitted or sir is None:
        return "C"
    built = str(sir.get("study_production", "")).strip().lower() in ("1", "yes") \
        or str(sir.get("new_project_pid", "")).strip() != ""
    db_path = "B" if built else "A"
    return "E" if analysis else db_path


def match_sir(pp: dict, sirs: list) -> "dict | None":
    """The Study Tracker record a PathPresenter request links to, by title."""
    want = {norm_title(pp.get("linked_redcap_title")), norm_title(pp.get("project_title"))} - {""}
    hits = [s for s in sirs if norm_title(s.get("project_title")) in want]
    return hits[0] if len(hits) == 1 else None


def request_stains(pp: dict) -> list:
    """Stains the request names. The form asks only which metadata to enable, so the stain list
    usually comes from the deliverable text; anything unclear goes to OPEN_QUESTIONS."""
    text = " ".join(str(pp.get(k, "")) for k in ("expected_deliverable", "labeling_requirements",
                                                  "an_question", "project_description"))
    found = []
    for s in ("H&E", "CD3", "CD4", "CD8", "CD20", "FOXP3", "PD-L1", "PD-1", "Ki-67", "HER2",
              "ER", "PR", "MLH1", "PMS2", "MSH2", "MSH6", "EBER"):
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(s).replace('-', '-?')}(?![A-Za-z0-9])",
                     text, re.I) or (s == "CD8" and re.search(r"\bCD\s*8\b", text)) \
                or (s == "CD3" and re.search(r"\bCD\s*3\b", text)):
            found.append(s)
    return found


def instance(pp: dict) -> "tuple[str, bool]":
    """(instance, stated). Unstated means the default, OAU (argo-ccr), and a question."""
    v = str(pp.get("pp_instance", "")).strip().upper()
    if "MSK" in v:
        return "MSK (argo-research)", True
    if "OAU" in v:
        return "OAU (argo-ccr)", True
    return "OAU (argo-ccr)", False


# --------------------------------------------------------------------------------------
# Reading the two trackers
# --------------------------------------------------------------------------------------

def load(env_var: str, path: "str | None") -> list:
    if path:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, list) else [data]
    from argo_redcap_client import RedcapClient  # noqa: E402
    from argo_trackers import ADMIN_TRACKERS     # noqa: E402
    client = RedcapClient.from_env(env_var)
    if client is None:
        sys.exit(f"The {env_var} access key isn't in your ARGO settings file. Export the record "
                 "as JSON (labels) from REDCap and pass it with --from-json / --pp-json instead.")
    _e, title, pid, _m = next(t for t in ADMIN_TRACKERS if t[0] == env_var)
    client.confirm_project(expect_title=title, expect_pid=pid)
    return client.export_records(rawOrLabel="label", exportCheckboxLabel="true")


def find(records: list, rid: str) -> dict:
    rec = next((r for r in records if str(r.get("record_id")) == str(rid)), None)
    if rec is None:
        sys.exit(f"There's no record {rid} there.")
    return rec


# --------------------------------------------------------------------------------------
# plan — what this build is and what it still needs
# --------------------------------------------------------------------------------------

def plan_for(sir: dict, pps: list) -> dict:
    linked = [p for p in pps if match_sir(p, [sir]) is sir]
    todo, steps = [], []
    if not linked:
        return {"path": None, "requests": [], "todo": [
            "No PathPresenter request (PID 233) links to this study. A pathology build doesn't "
            "start without one: the requester submits the PathPresenter Initiation Request, "
            "naming this study's title as the linked REDCap project."]}
    paths = {p["record_id"]: classify(p, sir) for p in linked}
    for p in linked:
        inst, stated = instance(p)
        if not stated:
            todo.append(f"PathPresenter request {p['record_id']}: no instance chosen — planned "
                        f"on {inst}; confirm with the requester.")
        stains = request_stains(p)
        if paths[p["record_id"]] in ("A", "B", "E"):
            if not stains:
                todo.append(f"PathPresenter request {p['record_id']}: no stain list — ask which "
                            "stains are scanned (H&E plus any IHC).")
            elif "H&E" not in stains:
                todo.append(f"PathPresenter request {p['record_id']}: stains {', '.join(stains)} "
                            "named; is there an H&E per case too? (planned: yes)")
        if str(p.get("labeling_requirements", "")).strip() or str(p.get("an_question", "")).strip():
            todo.append(f"PathPresenter request {p['record_id']}: the eCRF and labeling spec "
                        "needs the reader protocol (e.g. hotspots per slide, scoring scale) — "
                        "ECRF_SPEC.md has the draft.")
    design = str(sir.get("study_design") or sir.get("data_collection") or "").lower()
    retrospective = "retro" in design or "database" in design
    steps.append("Prospective: --patient-level (eligibility_consent, patient, specimen with the "
                 "slide block)" if not retrospective else
                 "Retrospective: a case form keyed on histology_number (identifier), then the "
                 "slide block; a clinical form only from an abstraction proforma")
    return {"path": sorted(set(paths.values())), "requests": list(paths.items()),
            "retrospective": retrospective, "todo": todo, "shape": steps}


def write_plan(sir: dict, plan: dict, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    lines = [f"# Pathology plan — SIR {sir.get('record_id')}: {str(sir.get('project_title', ''))[:90]}",
             "", "Generated by `pathology.py plan`; rewritten each run.", ""]
    if plan["path"] is None:
        lines += ["**Stop: no PathPresenter request.**", ""] + [f"- {t}" for t in plan["todo"]]
    else:
        lines += ["| PathPresenter request | Path |", "|---|---|"]
        lines += [f"| {rid} | {p} — {PATHS[p]} |" for rid, p in plan["requests"]]
        lines += ["", "## REDCap shape", ""] + [f"- {s}" for s in plan["shape"]]
        lines += ["", "## Open before the build", ""]
        lines += [f"- {t}" for t in plan["todo"]] or ["- Nothing open."]
    path = out / "PATHOLOGY_PLAN.md"
    path.write_text("\n".join(lines) + "\n")
    return path


# --------------------------------------------------------------------------------------
# setup — the PathPresenter side of a build
# --------------------------------------------------------------------------------------

METADATA_COLUMNS = ["Name", "Pathology REDCap ID", "Slide type", "Slide comment 1",
                    "Slide comment 2", "Slide stain", "Scanner used", "Cut location",
                    "Stain location"]


def study_code(pp: dict, sir: "dict | None" = None) -> str:
    """A PROPOSED dataset code — the administrator assigns the real one (slide-bank
    architecture). From the tracker's short name when it has one, else the title."""
    short = str((sir or {}).get("shortened_study_name", "")).strip()
    if short:
        return re.sub(r"[^A-Za-z0-9]", "", short.title())[:10].upper() or "STUDY"
    words = [w for w in re.findall(r"[A-Za-z0-9]+", str(pp.get("project_title", "")))
             if w.lower() not in {"of", "the", "in", "and", "for", "a", "an", "seen", "with", "to"}]
    caps = [w for w in words if w.isupper() and len(w) <= 6 and not w.isdigit()]
    return (caps[0] if caps else "".join(w[0] for w in words[:4])).upper()[:8] or "STUDY"


# PathPresenter permissions (decided 2026-11-17, from the vendor's role table and sharing
# workflows; pathpresenter-roles.md). Two layers: an ACCOUNT role per person, and per-DATASET
# sharing. Only the ARGO admin can create anything — every role that could manage access can
# also create datasets — so everyone else is a Guest and the per-study jobs live on the dataset.
# Nothing is shared organisation-wide; downloads and the slide-label photo are off; readers see
# only stain and slide type, and never each other's annotations (that switch lives on the
# annotation project, not the dataset). Copying slides between datasets needs the dataset's
# owner or its Dataset Access Manager — no other dataset job, whatever the account role
# (PathPresenter, 2026-11-19) — so the ARGO admin, who owns every dataset, copies them.
DATASET_SWITCHES = [
    ("Grant access to all users within your organization", "OFF"),
    ("Allow access to External User", "OFF"),
    ("General permissions for all External Institute User", "OFF"),
    ("Access", "specific users only, each Read-Only or Approved as below"),
    ("Download permission", "OFF for everyone; the ARGO admin grants it per request"),
    ("Can View Label", "OFF for everyone: the photo of the glass slide's label can carry identifiers"),
    ("Metadata fields visible (readers, viewers)", "stain and slide type only"),
    ("Metadata fields visible (PM, RA)", "all"),
]
# Set on the annotation project, not the dataset.
PROJECT_SWITCHES = [
    ("Annotation review permission (readers)",
     "OFF, so double reads stay independent; the PI may turn it on for a consensus read"),
    ("Additional Project Owner", "none by default; the ARGO admin owns and builds the project"),
]
COPY_SLIDES = ("Copying slides between datasets: only the source dataset's owner or its Dataset "
               "Access Manager can, so the ARGO admin does it. If someone else owns the source "
               "dataset, they first make the ARGO admin its Dataset Access Manager.")
# Account roles: Guest is the default (pathpresenter-roles.md). A person from another
# institution than the instance's is also an external-institute user of that institution.
GUEST = "Guest (external-institute user if from another site)"


def permissions(pp: dict) -> list:
    """(who, from the request; account role; on the dataset) for everyone the request names."""
    def val(k):
        return str(pp.get(k, "")).strip()
    rows = [("ARGO PathPresenter admin", "Admin",
             "Owner + Dataset Access Manager; builds the annotation project and eCRF")]
    pi = val("pi_user_name") or " ".join(x for x in (val("pi_first_name"), val("pi_surname")) if x)
    if pi:
        rows.append((f"{pi} (PI)", GUEST, "Approved; gets results as the admin's export"))
    if val("pm_name"):
        rows.append((f"{val('pm_name')} (PM)", GUEST, "Approved + Metadata Entry Specialist + Data Contributor"))
    if val("ra_name"):
        rows.append((f"{val('ra_name')} (RA)", GUEST,
                     "Data Contributor (uploads slides only)"))
    readers = [val(f"contributor_{n}") for n in range(1, 5)] + [val("an_labelers")]
    for r in [r for r in readers if r]:
        rows.append((f"{r} (reader)", GUEST,
                     "Approved; assigned to the annotation project; sees stain and slide type "
                     "only; no annotation review"))
    for v in [val(f"viewer_{n}") for n in range(1, 5)]:
        if v:
            rows.append((f"{v} (viewer)", "Guest", "Read-Only"))
    return rows


def setup(pp: dict, sir: "dict | None", out: Path, code: "str | None") -> list:
    out.mkdir(parents=True, exist_ok=True)
    path = classify(pp, sir)
    inst, stated = instance(pp)
    proposed = not code
    code = code or study_code(pp, sir)
    stains = request_stains(pp) or ["H&E"]
    if "H&E" not in stains and path != "D":
        stains = ["H&E"] + stains
    written = []

    # 1. the metadata import template: one example row per stain
    meta = out / f"{code}_PathPresenter_metadata_TEMPLATE.csv"
    with open(meta, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(METADATA_COLUMNS)
        for s in stains:
            w.writerow([example_name(s), "<Pathology REDCap ID>", "", "", "", s, "", "", ""])
    written.append(meta)

    # 2. the eCRF / labeling spec, drafted from the request
    readers = [str(pp.get(f"contributor_{n}", "")).strip() for n in range(1, 5)]
    readers = [r for r in readers if r] or ([str(pp.get("an_labelers", "")).strip()]
                                            if str(pp.get("an_labelers", "")).strip() else [])
    ecrf = out / "ECRF_SPEC.md"
    ecrf.write_text("\n".join([
        f"# eCRF and labeling — {code}", "",
        "Draft from the PathPresenter request. Readers score in PathPresenter; the eCRF export "
        "is the results file. REDCap does not hold the scores.", "",
        "## Every slide (the ARGO slide QC, as on P20 aim 2)", "",
        "- Slide in focus: Yes / No", "- Stain visible: Yes / No", "- Tumour present: Yes / No",
        "- Comment (free text)", "",
        "## The study's own questions", "",
        f"- What is labeled or measured: {pp.get('an_question') or pp.get('expected_deliverable') or '[TODO]'}",
        f"- Annotation tools: {pp.get('labeling_requirements') or pp.get('an_annotation_types') or '[TODO]'}",
        f"- Label classes: {pp.get('an_label_classes') or '[TODO — ask the PI]'}",
        "- Scoring protocol (e.g. hotspots per slide, fields per hotspot, scale): [TODO — ask the PI]",
        "", "## Readers", "",
        *([f"- {r}" for r in readers] or ["- [TODO] who labels, and whether they are blinded"]),
        "", f"Deliverable: {pp.get('expected_deliverable') or pp.get('an_question') or '[TODO]'}",
        ""]))
    written.append(ecrf)

    # 3. the setup checklist
    checklist = out / "PATHPRESENTER_SETUP.md"
    lines = [f"# PathPresenter setup — {code} (request {pp.get('record_id')}, path {path})", "",
             f"Instance: **{inst}**" + ("" if stated else " — not chosen on the request; confirm"),
             f"Dataset code: **{code}**" + (" — proposed; confirm or pass --study-code"
                                             if proposed else ""),
             f"Study: {str(pp.get('project_title', ''))[:90]}", "",
             "File names: histology number, then stain — "
             f"`{example_name(stains[0])}`; a second slide of the same stain "
             f"`{example_name(stains[0], 2)}`. Never a patient name or hospital number. The "
             "label image must not show a name.", "",
             "| # | Step | Who | Done |", "|---|---|---|---|"]
    rows = [("Create the dataset and folder on the instance above", "PathPresenter admin")]
    if path == "D":
        rows += [("Check the slide list holds Pathology REDCap IDs / file names only "
                  "(`pathology.py check-slide-list`)", "database manager"),
                 (f"Copy the listed slides from {pp.get('an_source_db') or '[source dataset]'} "
                  "into the new dataset (owner or Dataset Access Manager of the source only)",
                  "PathPresenter admin"),
                 ("Check the new dataset holds exactly the listed slides: download its file names "
                  "and compare them with the slide list", "database manager")]
    else:
        rows += [("Scanner staging folder D:\\ARGO_SCANS\\" + code +
                  " with 01_TO_CHECK / 02_TO_UPLOAD / 03_UPLOADED", "scanning site"),
                 ("Upload one test slide end to end, named by the rule above", "scanning site"),
                 ("Import the metadata template (Pathology REDCap ID, stain, scanner, locations)",
                  "RA")]
    rows += [("Build the eCRF and labels from ECRF_SPEC.md", "PathPresenter admin"),
             ("Accounts, dataset and project permissions exactly as the tables below", "PathPresenter admin"),
             ("Weekly: export the dataset and reconcile it against the REDCap slide names",
              "database manager")]
    lines += [f"| {n} | {s} | {w} | ☐ |" for n, (s, w) in enumerate(rows, 1)]
    lines += ["", "## Dataset sharing settings", "", "| Setting | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in DATASET_SWITCHES]
    lines += ["", "## Annotation project settings", "", "| Setting | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in PROJECT_SWITCHES]
    lines += ["", COPY_SLIDES]
    lines += ["", "## People", "",
              "Names as the request gives them. A person with no PathPresenter account is "
              "requested on the Study Personnel Request (platform: PathPresenter).", "",
              "| Who | Account role | On this dataset |", "|---|---|---|"]
    lines += [f"| {w} | {r} | {d} |" for w, r, d in permissions(pp)]
    checklist.write_text("\n".join(lines) + "\n")
    written.append(checklist)
    return written


# --------------------------------------------------------------------------------------
# check-slide-list — path D: the list must carry no identifiers
# --------------------------------------------------------------------------------------

IDENTIFIER_COLUMNS = re.compile(r"name|surname|hospital|dob|birth|phone|address|email|mrn|"
                                r"patient_?id|nhs|nin\b", re.I)
SLIDE_COLUMNS = re.compile(r"slide|file|pathology redcap id|redcap_id|record", re.I)


def read_table(path: Path) -> "tuple[list, list]":
    if path.suffix.lower() in (".xlsx", ".xls"):
        import openpyxl  # noqa: E402
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
        rows = [[("" if c is None else str(c)) for c in r] for r in ws.iter_rows(values_only=True)]
    else:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    rows = [r for r in rows if any(c.strip() for c in r)]
    return (rows[0], rows[1:]) if rows else ([], [])


def check_slide_list(path: Path) -> "tuple[list, list]":
    """(problems, the columns that look like identifiers). Reports column names only, never
    a cell value."""
    header, body = read_table(path)
    flagged = [h for h in header if IDENTIFIER_COLUMNS.search(h) and not SLIDE_COLUMNS.search(h)]
    problems = []
    if flagged:
        problems.append(f"columns that look like identifiers: {', '.join(flagged)} — remove "
                        "them before the list goes anywhere near PathPresenter")
    if not any(SLIDE_COLUMNS.search(h) for h in header):
        problems.append("no column names a slide, file or Pathology REDCap ID")
    if not body:
        problems.append("the list has no rows")
    return problems, flagged


# --------------------------------------------------------------------------------------
# audit — an existing study against the standard; reports, never restructures
# --------------------------------------------------------------------------------------

DD_TO_META = {"Variable / Field Name": "field_name", "Form Name": "form_name",
              "Field Type": "field_type", "Identifier?": "identifier",
              "Choices, Calculations, OR Slider Labels": "select_choices_or_calculations"}


def read_dd(path: Path) -> list:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if rows and "field_name" not in rows[0]:
        rows = [{DD_TO_META.get(k, k): v for k, v in r.items()} for r in rows]
    return rows


def audit(rows: list) -> list:
    names = {r["field_name"] for r in rows}
    out = []
    numbered = sorted(n for n in names if re.fullmatch(r"slide_name_\d+", n))
    per_stain = sorted(n for n in names if re.fullmatch(r"slide_name_[a-z0-9]+_\d", n))
    single = sorted(n for n in names if re.fullmatch(r"slide_name_[a-z][a-z0-9]*", n))
    if numbered:
        out.append(f"slide names are numbered slots ({len(numbered)}, aim 2 style), not per stain "
                   "— differs from the standard; leave as built")
    elif single and not per_stain:
        out.append(f"one slide name per stain ({len(single)}, aim 1 style), no room for a second "
                   "slide of a stain — differs from the standard; leave as built")
    out += [f"{e} — leave as built unless the study is being restructured" for e in check_rows(rows)
            if not (numbered or single) or "has no 'slide_name_" not in e]
    return out or ["Matches the standard."]


# --------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="ARGO pathology builds: the PathPresenter standard.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="which path a study's PathPresenter request takes")
    p.add_argument("sir")
    p.add_argument("--out", default=".")
    p.add_argument("--from-json")
    p.add_argument("--pp-json")
    s = sub.add_parser("setup", help="write the PathPresenter side for one request")
    s.add_argument("pp")
    s.add_argument("--out", required=True)
    s.add_argument("--study-code")
    s.add_argument("--from-json")
    s.add_argument("--pp-json")
    c = sub.add_parser("check-slide-list", help="an analysis request's slide list (path D)")
    c.add_argument("file")
    a = sub.add_parser("audit", help="an existing study's dictionary against the standard")
    a.add_argument("dd")
    args = ap.parse_args()

    if args.cmd == "check-slide-list":
        problems, _ = check_slide_list(Path(args.file))
        print("\n".join(f"✗ {p}" for p in problems) or "✓ The list names slides and carries no "
              "identifier columns.")
        return 1 if problems else 0
    if args.cmd == "audit":
        for line in audit(read_dd(Path(args.dd))):
            print(f"- {line}")
        return 0

    from argo_trackers import ADMIN_TRACKERS  # noqa: E402
    sirs = load(ADMIN_TRACKERS[0][0], args.from_json)
    pps = load("PATHPRESENTER_REQUEST", args.pp_json)
    if args.cmd == "plan":
        sir = find(sirs, args.sir)
        plan = plan_for(sir, pps)
        print(f"Wrote {write_plan(sir, plan, Path(args.out))}")
        if plan["path"] is None:
            print("Stop: no PathPresenter request links to this study.")
            return 1
        for rid, path in plan["requests"]:
            print(f"  PathPresenter request {rid}: path {path} — {PATHS[path]}")
        return 0
    pp = find(pps, args.pp)
    sir = match_sir(pp, sirs)
    if classify(pp, sir) == "C":
        print("Path C: this request has no REDCap Study Initiation request behind it, so there is "
              "nothing to set up yet. Ask the requester to submit one, naming the same title.")
        return 1
    for path in setup(pp, sir, Path(args.out), args.study_code):
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
