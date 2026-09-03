---
name: study-launch-pipeline
description: The ARGO new-study procedure — study idea to study launch, three gates, every task mapped to its real template in the Study Tracker File Repository. Source — the programme's own procedure (Rivka, 2026-08-27), verified against the live File Repository the same day.
---

# The ARGO study-launch pipeline (the PM's real job)

Three gates. Each gate is a natural prompt from the PM; each task produces ONE named document.
Most fill a named template — but not all: the protocol has **no** template, and the questionnaire
template is a **design guide** rather than a form (both flagged at Gate 1).
All templates live in the Study Tracker File Repository under **ARGO Templates/** (fetched by
`fetch_templates.py` into `project-manager/templates-official/` — never committed). The two
Study Start-Up SOPs (NIH / non-NIH, under `ARGO Standard Operating Procedures (SOPs)/Study
Start-Up/`) are the procedure's own reference text — read the one matching the study's funding.

## Gate 1 — "The ARGO directors approved moving forward"

| Task | Template (real filename) | Input |
|---|---|---|
| Draft protocol | **NONE YET** — `ARGO Protocol Template/` is empty (being created). Say so plainly; then take one of the three paths below — never invent a house style | study proposal |
| Draft consent (ICF) | `ARGO ICF Template/ARGO IPH Consent Form Template.doc` — a **legacy `.doc`**; see the fill ladder below | study proposal |
| Draft questionnaire | `ARGO Questionnaire Template/ARGO Questionnaire Template.docx` — a **design GUIDE, not a fillable form** (Sections 1–5 are drafting principles). Build the questionnaire **to** its rules; never emit its advice as the instrument | questionnaire draft |

### The protocol's three paths (in order of preference)

1. **An approved ARGO protocol the PM supplies** → draft on that document's structure.
2. **A closely comparable approved protocol from the same programme** → same, and say which one.
3. **Neither — no ARGO protocol template exists and the PM has no approved protocol to model**
   → **draft on the PM's OWN proposal's structure**, keeping its section order and adding the
   sections a protocol needs that a proposal lacks, and **label it at the top of the document**:
   *"Drafted on the study proposal's own structure — no ARGO protocol template exists yet; to be
   reconciled against an approved ARGO protocol before submission."* This is what ARGO's own
   editors did on the teaching case. It replaces the old dead-end ("stop at the other two
   tasks"), which the finals disprove.

The largest proposal→final addition is the standard database/data-management text — REDCap PHI
approval, SSL, OAUTHC as database administrator, permission auditing, nightly backups,
de-identified exports to the biostatistician, source documentation, QA cadence, paper records
under lock and key. Carry it from [[redcap-protocol-boilerplate]] with its `[TODO]`s visible and
say it needs the PI's confirmation; never emit `[TODO: name the platform]` instead.

### Filling the ICF — the fallback ladder, and say which rung you used

The official ICF is a legacy binary `.doc`. Filling it **in place** (letterhead intact) may need
LibreOffice (`soffice`) to convert it, and `soffice` is often **absent** — the failure is a bare
`FileNotFoundError`, which is easy to paper over.

1. `soffice` present → convert to `.docx`, fill in place, keep the letterhead. Report:
   **"filled the official template."**
2. `soffice` absent → rebuild the template's structure in a new document and **copy its required
   language verbatim**. Report: **"rebuilt its structure and copied its required language
   verbatim (letterhead not preserved) — reconcile against the official file before use."**

Never let a PM believe a reconstruction is the official file. Which rung fired is part of the
deliverable, not a footnote.

**Keep-notes (checks on the consent, every time):**
- **Ask, don't assume, at Gate 1 before drafting:** *"Which institutions appear as collaborators
  on this study, and does participant data leave Nigeria?"* The answer rewrites the protocol
  title, the objectives, the analysis section and the ICF's data-sharing section — and it
  pre-decides Gate 2's DTA rule. Site contact information must be present in the ICF; house
  practice is **one central PI contact block**, not a per-site contact table (don't build one
  unless asked).
  *Open question (with Matteo and Rivka, unresolved):* whether ARGO studies are presented as
  Nigerian-led with ARGO as the collaborator is a **policy question**, not settled here — the
  teaching case removed the foreign collaborator from every document, but no rule is written.
- Has any IRB template text been **removed** — or **added**? Both count: the check covers
  additions to the regulatory and signature blocks as well as deletions. Flag it and ask the site
  to edit the consent so all required template language is present and nothing unreviewed has
  been inserted. (A check, not a silent fix.)
- Keep **every** template heading. Where a heading doesn't apply, answer **"Not applicable"**
  rather than deleting it — the finals answered exactly this way for *Biological specimens*,
  *Payment of treatment costs*, *Clinical Trial Registration* and *Conflict of Interest*.

### The questionnaire — three-class edit policy

What ARGO's editors actually did to the draft proforma, as three classes:

- **(a) Mechanical defects — fix and log.** Wrong-cancer paste, triplicated blocks, hand-derived
  values, unanswerable items: the editors fixed exactly these. Typos they left alone.
- **(b) Clinical content — propose, never invent.** The finals went far deeper than the draft (an
  HIV block, HPV serotypes, FIGO + histology lists, structured exam grids, state of origin) — but
  that content came from clinicians. Propose it; let the PI decide.
- **(c) Unstructured sections may be DELETED rather than repaired — ask before rebuilding.** The
  draft rebuilt the financial-toxicity section; the programme cut it entirely.

**Standing rule:** never collapse co-occurring clinical events into select-one for tidiness
(surgery procedures, recurrence sites).

### Gate-1 structural pre-flight on the questionnaire

Before the questionnaire leaves this skill — the finals shipped all of these:

- **Controlled vocabularies**, staging especially. FIGO: an invented `IA3` and roman/arabic
  corruption (`IB11`, `IB111`, `IIA11`, `IIIC11`) both shipped. Check every stage, grade and
  histology list against the real vocabulary.
- **Unit sanity** — `kg/m²` written for `mg/m²` (chemotherapy dosing) shipped.
- **Duplicates** — repeated questions, repeated option lists, repeated blocks.
- **Consistent missing-value third columns**, per [[mdc-rules]] — the same MDC set on every
  question of the same type, not some.
- **Cross-document check** — do the sites named in the protocol match the site field in the
  questionnaire? (The final protocol listed six sites; the final proforma's hospital field was a
  single checkbox reading OAUTHC.)

Findings go in the changelog for the PI, **not** silent fixes.

**The drafting artifact:** `<MONIKER>_Questionnaire_changelog.md` — what changed and why, plus
the PI's open questions. It ships with the questionnaire.

## Gate 2 — "Ready for stakeholder review and IRB"

| Task | Template | Notes |
|---|---|---|
| Stakeholder review email | (drafted, no template) | protocol + consent + questionnaire to PI, Research Managers, Biostatisticians, RAs, Community Healthcare Workers as needed — BEFORE IRB submission |
| IRB submission form | `ARGO IPH HREC Application Form Template/ARGO IPH HREC Application Form Template.docx` | the OAUTHC submission template does **not** exist in the repository yet — say so if the site is OAUTHC. Content map: `templates/irb-application.md` (an IRB-application map, **not** a protocol skeleton — the protocol is Gate 1's own document) |
| DTA/MTA | `OAUTHC DTA Template/OAU Data Transfer Agreement_Template.docx` | **Skip if all sites are Nigerian federal hospitals** — no DTA/MTA required then. Say which rule applied. Gate 1's collaborator question already answered this; reuse the answer. |

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
  the study moniker. Where filling in place was not possible (the legacy `.doc` ICF, the
  flattened activation memo, the `.pptx` deck), **say which rung of the fallback you used** —
  a reconstruction must never be handed over as the official file.
- Facts come from the proposal/protocol and the PM's answers; unknowns are visible [TODO]s.
- Ask which gate the study is at ("where are we — approval just in, IRB submitted, or ethical
  approval received?") and do that gate's tasks; never dump all three gates at once.
- Known gaps to say out loud when relevant: no protocol template yet (three paths above); the
  questionnaire template is a design guide, not a form; the ICF template is a legacy `.doc` that
  may not be fillable in place; no OAUTHC IRB form (IPH HREC only); the activation memo template
  is a flattened image (fill limitations — draft content + hand over).
- Next procedure after launch (not built yet): amendment submission + collecting site
  amendment approvals.

## The teaching case

The Cervical cancer study: original protocol + proforma, and the final protocol / ICF /
proforma, show the intended progression. They live in the PM's own materials (not this repo).

Gate 1 was drafted blind against that study and the drafts compared with the programme's real
finals (2026-09-03). Everything above marked *"the finals"*, *"the editors"* or *"the teaching
case"* comes from that comparison: the protocol's third path, the REDCap boilerplate, the ICF
conventions, the questionnaire edit policy and the structural pre-flight. One question the
comparison raised is **not** settled and is deliberately not answered here — whether foreign
collaborators appear in ARGO study documents at all (see the first keep-note).
