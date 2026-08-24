#!/usr/bin/env python3
"""Produce a paste-ready 'Create New REDCap Project' value sheet for a SIR record.

Ported from the prior ~/.claude/skills/study-intake/SKILL.md (Step 1).
Until a Super API Token is granted, project creation in REDCap is manual UI work.
This script prepares every field value so the human paste-step is trivial.

Usage (it finds your ARGO settings file by itself — there is nothing to load first):
    python3 fill_new_project.py 17 18 19 24      # one or more SIR record IDs
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# The shared ARGO scripts are vendored into this skill's own scripts/ folder by release.py,
# so imports never depend on where — or whether — other plugins are installed. The parents walk
# is only for running from a source checkout before the first sync.
_here = Path(__file__).resolve().parent
for _cand in (_here / "scripts",
              *(p / "plugins/argo-core/skills/redcap-api/scripts" for p in _here.parents)):
    if (_cand / "argo_redcap_client.py").exists():
        sys.path.insert(0, str(_cand))
        break
from argo_redcap_client import load_env_file  # noqa: E402

# Filled in by main(), from the settings file this script loads itself — never read at import.
REDCAP_URL = None
SIR_TOKEN = None

# Research sub-category derivation from project_description / project_title.
# Order matters — first match wins.
SUBCATEGORY_RULES = [
    (r"\b(biobank|repository|biorepository|specimen.collection|tissue.bank)\b", "Repository"),
    (r"\b(qualitative|interview|focus.group|survey|questionnaire|behavioral|psychosocial)\b", "Behavioral or psychosocial research study"),
    (r"\b(clinical.trial|randomi[sz]ed|rct|phase.[i1234])\b", "Clinical research study or trial"),
    (r"\b(deep.learning|machine.learning|ai|algorithm|diagnostic|imaging.classifier)\b", "Translational research 1"),
    (r"\b(implementation|dissemination|capacity.building|training.evaluation)\b", "Translational research 2"),
    (r"\b(epidemiolog|incidence|prevalence|cohort.study|case.control|retrospective.review|retroactive.review|outcomes.review)\b", "Epidemiology"),
    (r"\b(bench|molecular|single.cell|in.vitro|cell.line)\b", "Basic or bench research"),
]


def api_post(token, **params):
    data = urllib.parse.urlencode({"token": token, "format": "json", **params}).encode()
    req = urllib.request.Request(REDCAP_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_sir(rid):
    recs = api_post(SIR_TOKEN, content="record",
                    rawOrLabel="label", **{f"records[0]": str(rid)})
    if not recs:
        return None
    return recs[0]


def derive_subcategory(rec):
    haystack = (rec.get("project_title", "") + " " + rec.get("project_description", "")).lower()
    for pat, label in SUBCATEGORY_RULES:
        if re.search(pat, haystack):
            return label, pat
    return "(unclear — ask user)", None


HONORIFICS = {"dr", "dr.", "prof", "prof.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "miss"}


def pi_cited(rec):
    """Reformat to 'Surname Initial', e.g. 'Wuraola F'. Strips honorifics from first name."""
    surname = (rec.get("pi_surname") or "").strip()
    first = (rec.get("pi_first_name") or "").strip()
    if not surname:
        return rec.get("pi_name_cited", "")
    # Strip leading honorifics ("DR. FUNMILOLA" -> "FUNMILOLA")
    tokens = first.split()
    while tokens and tokens[0].lower() in HONORIFICS:
        tokens.pop(0)
    initial = tokens[0][:1].upper() if tokens else ""
    return f"{surname} {initial}".strip()


def format_irb_expires(s):
    """REDCap returns dates as YYYY-MM-DD; show as DD/MM/YYYY for the human."""
    if not s:
        return "(not provided)"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else s


def render(rec):
    rid = rec.get("record_id")
    title = rec.get("project_title", "").strip().strip('"')
    purpose = "Research" if rec.get("project_type", "").lower().startswith("research") else "Operational Support"
    subcat, matched = derive_subcategory(rec)
    pi_first_raw = rec.get("pi_first_name") or ""
    # Strip honorifics from the displayed first name too, not just the cited form
    pi_first_tokens = pi_first_raw.split()
    while pi_first_tokens and pi_first_tokens[0].lower() in HONORIFICS:
        pi_first_tokens.pop(0)
    pi_first = " ".join(pi_first_tokens).title() if pi_first_tokens else ""
    pi_mi = (rec.get("pi_middle_initial") or "").title()
    pi_surname = (rec.get("pi_surname") or "").title()
    pi_email = rec.get("pi_email") or ""
    pi_phone = rec.get("pi_whatsapp") or ""
    irb = rec.get("irb_number") or "(none)"
    irb_exp = format_irb_expires(rec.get("irb_approval_expires"))

    project_notes_lines = []
    if pi_phone:
        project_notes_lines.append(f"PI phone number: {pi_phone}")
    project_notes_lines.append(f"IRB approval expires: {irb_exp}.")
    project_notes = "\n                   ".join(project_notes_lines)

    folder = f"{pi_surname}" if pi_surname else "(decide manually)"

    out = []
    out.append("━" * 66)
    out.append(f" CREATE NEW PROJECT — SIR Record {rid} ({pi_surname or 'no PI'})")
    out.append("━" * 66)
    out.append("")
    out.append(f" Project title:    {title}")
    out.append("")
    out.append(f" Purpose:          {purpose}")
    out.append(f" Please specify:   {subcat}")
    if matched:
        out.append(f"                   (matched on pattern: {matched})")
    out.append("")
    if purpose == "Research":
        out.append(f" PI First Name:    {pi_first or '(leave blank)'}")
        out.append(f" PI MI:            {pi_mi or '(leave blank)'}")
        out.append(f" PI Last Name:     {pi_surname or '(leave blank)'}")
        out.append(f" PI Email:         {pi_email or '(leave blank)'}")
        out.append(f" PI Name (cited):  {pi_cited(rec) or '(leave blank)'}")
        out.append("")
        out.append(f" IRB Number:       {irb}")
        out.append("")
    out.append(f" Project Folder:   {folder}")
    out.append("")
    out.append(f" Project Notes:    {project_notes}")
    out.append("")
    out.append(" Creation option:  Empty project (blank slate)")
    out.append("━" * 66)
    return "\n".join(out)


def main():
    global REDCAP_URL, SIR_TOKEN
    settings = load_env_file()
    REDCAP_URL = os.environ.get("REDCAP_URL")
    SIR_TOKEN = os.environ.get("STUDY_INITIATION_REQUEST")

    if not REDCAP_URL or not SIR_TOKEN:
        where = (f"Your settings file is here:\n\n    {settings}\n"
                 if settings else
                 "Open your ARGO folder and double-click 'Add keys here' — that opens your\n"
                 "settings file in a text editor.\n")
        sys.exit(
        "This tool needs to know the web address of your REDCap system, and the access key for\n"
        "the Study Tracker, before it can do anything. One or both isn't set yet.\n"
        "\n"
        "Both live in your ARGO settings file, one per line (REDCAP_URL= and\n"
        "STUDY_INITIATION_REQUEST=).\n"
        "\n"
        + where +
        "\nIf you don't have the key yet, ask your ARGO REDCap administrator to set you up."
    )
    if len(sys.argv) < 2:
        sys.exit(
        "Tell me which study or studies to prepare, using their record numbers in the Study\n"
        "Tracker. For example:\n"
        "\n"
        "    python3 fill_new_project.py 109\n"
        "    python3 fill_new_project.py 109 110 111"
    )

    for rid in sys.argv[1:]:
        rec = fetch_sir(rid)
        if not rec:
            print(f"\n  RID {rid}: not found.\n")
            continue
        print()
        print(render(rec))
        print()


if __name__ == "__main__":
    main()
