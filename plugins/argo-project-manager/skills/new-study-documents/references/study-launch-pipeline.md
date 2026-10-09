---
name: study-launch-pipeline
description: Where each ARGO new-study template lives in the Study Tracker File Repository, gate by gate, plus the procedure's source and the teaching case its rules came from. The procedure itself — what to do at each gate — is new-study-documents' SKILL.md.
---

# The ARGO study-launch pipeline — sources and template locations

**Source:** the programme's own new-study procedure (Rivka, 2026-08-27), verified against the
live File Repository the same day and again on 2026-09-08 when the protocol template arrived.
How to work each gate is in [[new-study-documents]]; this page is the lookup it points to.

All templates live in the Study Tracker File Repository under **`ARGO Templates/`**, except the QA
plan and the Study Start-Up SOPs. `fetch_templates.py` brings all three folders into
`project-manager/templates-official/` (never committed — they carry staff contact details). Paths
below are relative to the File Repository root.

## Gate 1 — "The ARGO directors approved moving forward"

| Task | Template path | Note |
|---|---|---|
| Protocol | `ARGO Templates/ARGO Protocol Template/ARGO Protocol Template.docx` | 17 sections, each with its own italicised instruction; source map in [[protocol-fill-map]] |
| Consent (ICF) | `ARGO Templates/ARGO ICF Template/ARGO IPH Consent Form Template.doc` | The only legacy binary file in the repository; filling it in place needs `soffice` — the fallback ladder is in [[new-study-documents]] Gate 1 |
| Questionnaire | `ARGO Templates/ARGO Questionnaire Template/ARGO Questionnaire Template.docx` | A **design GUIDE, not a form to fill** — build the questionnaire to its rules |

## Gate 2 — "Ready for stakeholder review and IRB"

| Task | Template path | Note |
|---|---|---|
| Stakeholder review email | — | drafted |
| IRB submission form | `ARGO Templates/ARGO IPH HREC Application Form Template/ARGO IPH HREC Application Form Template.docx` | No OAUTHC submission template exists in the repository |
| DTA / MTA | `ARGO Templates/OAUTHC DTA Template/OAU Data Transfer Agreement_Template.docx` | Skipped when all sites are Nigerian federal hospitals |

## Gate 3 — "Ethical approval received"

| Task | Template path |
|---|---|
| CPL, one per site | `ARGO Templates/ARGO CPL Template/ARGO Consenting Professional List (CPL) Template.docx` |
| ECL, all sites | `ARGO Templates/ARGO ECL Template/ARGO Eligibility Checklist (ECL) Template.docx` |
| Study guide / SOP | `ARGO Templates/ARGO Study SOP Template/ARGO Study SOP Template.docx` |
| Lab manual (specimens only) | `ARGO Templates/ARGO Lab Templates/ARGO Biospecimen Laboratory Manual Template.docx` |
| Lab requisition (specimens only) | `ARGO Templates/ARGO Lab Templates/ARGO Lab Requisition Template.docx` |
| Study QA plan | `ARGO Quality Assurance (QA)/ARGO QA Plan.docx` |
| REDCap build request | the SIR survey in REDCap — no template |
| Monthly study meeting agenda | `ARGO Templates/ARGO Study Meeting Template/ARGO Study Meeting Template.docx` |
| Joint-call accrual table | `ARGO Templates/ARGO Joint Call Study Accrual Template/ARGO Joint Call Study Accrual Template.docx` |
| SIV scheduling | — drafted |
| SIV slides | `ARGO Templates/ARGO SIV Templates/ARGO SIV Template.pptx` |
| SIV attendance | `ARGO Templates/ARGO SIV Templates/Protocol Training Attendance Log Template.docx` |
| New Study / New Site checklist | `ARGO Templates/ARGO Checklists/New Study_New Site Checklist_NIH Funded Final.docx` and `ARGO Templates/ARGO Checklists/New Study_New Site Checklist_non-NIH Funded Final.docx` |
| Activation memo | `ARGO Templates/ARGO Activation Memo Template/ARGO Activation Memo Template.docx` (body is a floating text box) |
| Activation email | — drafted |

The two Study Start-Up SOPs (NIH / non-NIH) are under
`ARGO Standard Operating Procedures (SOPs)/Study Start-Up/`.

## Known gaps in the repository

- The ICF cites a companion *Consent Form Instructional Template* four times; it is not in the
  File Repository. Say so if a PM asks for it.
- No OAUTHC IRB submission form — only the IPH HREC application.
- Not built yet: amendment submission and collecting site amendment approvals.

## The teaching case

The Cervical cancer study — original protocol and proforma, and the final protocol, ICF and
proforma — shows the intended progression. Those files live in the PM's own materials, not this
repo. Gate 1 was drafted blind against that study and compared with the programme's real finals
(2026-09-03). Everything in [[new-study-documents]] attributed to *"the finals"* or *"the
editors"* comes from that comparison: the ICF conventions, the questionnaire edit policy and the
structural pre-flight; [[protocol-fill-map]]'s standing answers come from ARGO's approved
protocols and live REDCap practice.

**Open question (with Matteo and Rivka, unresolved):** whether ARGO studies present as
Nigerian-led with ARGO as the collaborator — the teaching case removed the foreign collaborator
from every document, but no rule is written. It is deliberately not settled here, so the skill
asks the collaborator question every time rather than assuming either answer.
