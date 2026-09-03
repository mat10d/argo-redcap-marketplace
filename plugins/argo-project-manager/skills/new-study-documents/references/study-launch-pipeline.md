---
name: study-launch-pipeline
description: The ARGO new-study procedure — study idea to study launch, three gates, every task mapped to its real template in the Study Tracker File Repository. Source — the programme's own procedure (Rivka, 2026-08-27), verified against the live File Repository the same day.
---

# The ARGO study-launch pipeline (the PM's real job)

Three gates. Each gate is a natural prompt from the PM; each task fills ONE named template.
All templates live in the Study Tracker File Repository under **ARGO Templates/** (fetched by
`fetch_templates.py` into `project-manager/templates-official/` — never committed). The two
Study Start-Up SOPs (NIH / non-NIH, under `ARGO Standard Operating Procedures (SOPs)/Study
Start-Up/`) are the procedure's own reference text — read the one matching the study's funding.

## Gate 1 — "The ARGO directors approved moving forward"

| Task | Template (real filename) | Input |
|---|---|---|
| Draft protocol | **NONE YET** — `ARGO Protocol Template/` is empty (being created). Say so plainly; draft on the structure of an approved ARGO protocol the user supplies — never invent a house style | study proposal |
| Draft consent (ICF) | `ARGO ICF Template/ARGO IPH Consent Form Template.doc` | study proposal |
| Draft questionnaire | `ARGO Questionnaire Template/ARGO Questionnaire Template.docx` | questionnaire draft |

**Keep-notes (checks on the consent, every time):**
- Collaborating sites listed as needed — e.g. "data will be shared with MSK for analysis";
  site contact information present in the ICF.
- Has any IRB template text been removed? If so, flag it and ask the site to edit the consent
  so all required template language is present. (A check, not a silent fix.)

## Gate 2 — "Ready for stakeholder review and IRB"

| Task | Template | Notes |
|---|---|---|
| Stakeholder review email | (drafted, no template) | protocol + consent + questionnaire to PI, Research Managers, Biostatisticians, RAs, Community Healthcare Workers as needed — BEFORE IRB submission |
| IRB submission form | `ARGO IPH HREC Application Form Template/ARGO IPH HREC Application Form Template.docx` | the OAUTHC submission template does **not** exist in the repository yet — say so if the site is OAUTHC |
| DTA/MTA | `OAUTHC DTA Template/OAU Data Transfer Agreement_Template.docx` | **Skip if all sites are Nigerian federal hospitals** — no DTA/MTA required then. Say which rule applied. |

## Gate 3 — "Ethical approval received"

First: confirm ICF + ethical clearance from **every** participating site (list them; check each).

| Task | Template |
|---|---|
| CPL, one per site | `ARGO CPL Template/ARGO Consenting Professional List (CPL) Template.docx` (input: consenting professionals + sites) |
| ECL (all sites, one doc) | `ARGO ECL Template/ARGO Eligibility Checklist (ECL) Template.docx` (input: eligibility criteria) |
| Study Guide / SOP | `ARGO Study SOP Template/ARGO Study SOP Template.docx` |
| Lab Manual — only if specimens | `ARGO Lab Templates/ARGO Biospecimen Laboratory Manual Template.docx` |
| Lab Requisition — only if specimens | `ARGO Lab Templates/ARGO Lab Requisition Template.docx` |
| Study QA plan | `ARGO Quality Assurance (QA)/ARGO QA Plan.docx` |
| **Submit the REDCap build request** | the SIR survey, with ALL documents above attached for the File Repository — this is where the PM pipeline hands off to the database manager's build |
| Monthly study meeting agenda | `ARGO Study Meeting Template/ARGO Study Meeting Template.docx` |
| Accrual table for the joint call (if needed) | `ARGO Joint Call Study Accrual Template/ARGO Joint Call Study Accrual Template.docx` |
| Schedule the SIV | (zoom link + stakeholder email — drafted) |
| SIV slides | `ARGO SIV Templates/ARGO SIV Template.pptx` (PowerPoint — fill with the pptx tooling where available; otherwise draft the content and hand it over) |
| SIV attendance | `ARGO SIV Templates/Protocol Training Attendance Log Template.docx` |
| New Study / New Site checklist | `ARGO Checklists/New Study_New Site Checklist_NIH Funded Final.docx` or `..._non-NIH Funded Final.docx` — pick by funding |
| Activation memo | `ARGO Activation Memo Template/ARGO Activation Memo Template.docx` |
| Activation email to all stakeholders | (drafted) |

## Rules that govern every task here

- Templates are FETCHED from the File Repository, filled in place (letterhead intact), never
  committed to any repo, and outputs land in `project-manager/new-studies/<study>/` named with
  the study moniker.
- Facts come from the proposal/protocol and the PM's answers; unknowns are visible [TODO]s.
- Ask which gate the study is at ("where are we — approval just in, IRB submitted, or ethical
  approval received?") and do that gate's tasks; never dump all three gates at once.
- Known gaps to say out loud when relevant: no protocol template yet; no OAUTHC IRB form (IPH
  HREC only); the activation memo template is a flattened image (fill limitations — draft
  content + hand over).
- Next procedure after launch (not built yet): amendment submission + collecting site
  amendment approvals.

## The teaching case

The Cervical cancer study: original protocol + proforma, and the final protocol / ICF /
proforma, show the intended progression. They live in the PM's own materials (not this repo).
