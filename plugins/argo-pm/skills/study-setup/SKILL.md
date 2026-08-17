---
name: study-setup
description: Draft the document package for a NEW ARGO study so the program manager isn't the bottleneck for every new study initiation. Reads any supporting documents the user provides (concept note, grant aim, prior study, emails) to pre-fill, interviews only for what's missing, fills the canonical ARGO templates, and renders real Word documents via the docx skill. Use when starting a new study / preparing a study initiation — e.g. "set up a new study," "draft the questionnaire/protocol/study guide for this study," "prep the new-study documents."
allowed-tools: Read, Bash, Write, Edit, Glob, Grep, Skill
---

# study-setup

Compress the program manager's repetitive new-study work. Today the PM hand-makes the
questionnaire and supporting documents, then fills out the Study Initiation Request (SIR)
survey, and only then can the builder build. The PM is the serial chokepoint for every new
study. This skill drafts the document package fast — from whatever the user already has — so
the PM reviews and finalizes instead of starting from scratch each time.

**Scope: documents only.** This skill does not submit the SIR for you (the PM still does the
initiation survey today). It produces the Word package that feeds it. After the PM submits the
SIR, [[redcap-build]] (argo-build) triages the SIR and builds the database from the questionnaire.

## Pipeline position

```
study-setup  → (PM submits SIR survey) → redcap-build
draft docs       initiate on REDCap        triage SIR     build the DD
```

## In scope (the docs the PM generates to initiate)

- **questionnaire-proforma** — the data-collection instrument. The linchpin: redcap-build's
  Path A pulls the data dictionary from this.
- **protocol** — HREC/IRB research-plan application (IPH template).
- **study-guide** — operational study guide / SOP (aims, design, accrual, data-collection plan,
  contacts, weekly accrual reporting).
- **activation-memo** — site activation letter.
- **siv** — Site Initiation Visit deck outline + protocol-training attendance log.
- **lab-requisition** — research lab requisition form (specimen studies).
- **startup-checklist** — New Study / New Site checklist (NIH or non-NIH variant).

## Out of scope (deliberately)

**Consent / regulatory documents — ICF, CPL, ECL, DTA — are NOT generated here.** Per the
official New Study checklist these are *site-provided* ("Has the site provided the consent
forms / CPL?") and IRB-controlled. Do not draft or alter them. If asked, point the user to the
site and the File Repository.

## Inputs

1. **Supporting documents (preferred):** anything describing the study — concept note, grant
   aim, a prior/similar study's protocol or study guide, an email thread, a draft questionnaire.
   READ these first and extract everything you can (title, PI, sites, cancer type, design, aims,
   accrual, timeline, inclusion/exclusion, variables, contacts). Ask the user where they are.
2. **Interview for the gaps only:** after mining the documents, ask the user *only* for the
   fields you still can't fill. Don't re-ask what the documents already answer.

## The contract

1. **Render to Word via the docx skill.** Markdown skeletons (in `templates/`) are the working
   form, but the deliverable is real `.docx`. Invoke the **docx** skill to create the Word
   documents — do not hand the user raw markdown as the final product. (The SIV deck stays on
   the official `.pptx`; produce its content outline.)
2. **Fill, don't fabricate.** Populate placeholders from the supporting docs + interview. For
   anything genuinely unknown, leave a clearly-marked `**[TODO: …]**` for the PM — never invent
   regulatory facts, IRB numbers, ethics statements, or PI details.
3. **The questionnaire is analysis-driven.** When drafting the questionnaire-proforma, follow
   its own design principles (one question at a time, coded/categorical over free text,
   consistent scales, sectioned, validation-friendly) — it must be buildable by redcap-build,
   so favor fields that map cleanly to a REDCap data dictionary ([[dd-column-spec]],
   [[mdc-rules]]).
4. **Organized output.** One folder per study: `outputs/<study-slug>/` with the rendered `.docx`
   files + a `STUDY_PROFILE.md` capturing the study facts you gathered (so the package is
   reproducible and the next doc reuses the same facts).
5. **PM reviews before use.** Everything is a draft for the PM to verify — especially the
   protocol (a formal HREC application). Say so.

## Workflow

1. **Gather** — ask for / read the supporting documents. Extract the study profile; write it to
   `outputs/<study-slug>/STUDY_PROFILE.md`. Ask only for missing fields.
2. **Pick the set** — confirm which documents the user needs now (default: questionnaire +
   study-guide + activation-memo; add protocol/SIV/lab-req/checklist on request).
3. **Fill** — for each, copy the matching skeleton from `templates/`, substitute the study
   profile into its placeholders, and flag remaining `[TODO]`s.
4. **Render** — drive the **docx** skill to produce each `.docx` in `outputs/<study-slug>/`.
5. **Hand off** — tell the PM the package is drafted; next step is the SIR survey on REDCap,
   then [[redcap-build]].

## Templates

## The official Word templates — use them when you can

The real templates (official formatting, letterhead) live in the **Study Tracker's File
Repository**, not in this skill — the toolkit's repository is public and the templates contain
internal contact details, so they are fetched or downloaded, never bundled. Precedence:

1. **Already in the workspace?** Look before fetching:
   `find /mnt ~/argo-work ~ -maxdepth 4 -iname "ARGO*Template*" -name "*.docx" 2>/dev/null | head`
   (a folder named `templates-official/` or a downloaded `FileRepository_*/ARGO Templates/` both count)
2. **Not there, and the Study Tracker key is configured?** Fetch once into the workspace:
   `python3 fetch_templates.py --to <workspace>/templates-official`
3. **Neither?** Use the markdown skeletons below and render via the docx skill — the content is
   identical; only the official styling is approximated. Tell the user which path you took.

When an official template exists, use it as the base document and fill its placeholders (docx
skill), keeping its formatting; the markdown skeleton then serves as the content map.

| Skeleton | Official file (File Repository → ARGO Templates) |
|---|---|
| `questionnaire-proforma.md` | ARGO Questionnaire Template.docx |
| `protocol.md` | ARGO IPH Protocol Template.docx |
| `study-guide.md` | ARGO Study SOP Template.docx |
| `activation-memo.md` | ARGO Activation Memo Template.docx |
| `siv-outline.md` | ARGO SIV Template.pptx + Protocol Training Attendance Log Template.docx |
| `lab-requisition.md` | ARGO Lab Requisition Template.docx |
| `startup-checklist.md` | New Study_New Site Checklist (NIH / non-NIH variants) |

Fetched templates stay in the user's workspace. **Never commit or publish them.**

Markdown skeletons live in `templates/` (faithful to the official ARGO File Repository
templates), each with `[PLACEHOLDER]` slots:
`questionnaire-proforma.md`, `protocol.md`, `study-guide.md`, `activation-memo.md`,
`siv-outline.md`, `lab-requisition.md`, `startup-checklist.md`.

## See also

- [[redcap-build]] (argo-build) — the next step: triages the submitted SIR and builds the database from the questionnaire
- [[dd-column-spec]], [[mdc-rules]] — keep the questionnaire buildable
- docx skill — used to render the Word deliverables
