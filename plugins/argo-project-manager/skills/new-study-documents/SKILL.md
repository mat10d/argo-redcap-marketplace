---
name: new-study-documents
description: Walk a new ARGO study through the launch pipeline — from the directors' approval to the REDCap build request. Asks one question first (where the study is: approved, ready for IRB, or ethical approval received), then works that gate's tasks one at a time, each producing one named ARGO document from its official template (or, where the template is a design guide rather than a form, built to its rules). Reads whatever you already have — proposal, concept note, questionnaire draft, an email thread — asks only about what's genuinely missing, and hands you real documents to review. Use for "the directors approved the study", "prepare the IRB submission", "we got ethical approval", "study activation", "set up a new study", "draft the questionnaire for this study", "prep the new-study documents".
allowed-tools: Read, Bash, Write, Edit, Glob, Grep, Skill
---

# new-study-documents — the study-launch pipeline

The project manager's real job, from *"the directors approved it"* to the REDCap build request.
**Three gates**, each a natural moment in a study's life, each with its own task list; every task
produces ONE named document, from its official template where one exists — but several templates
are not fill-in forms, and the protocol has no template at all; each gate says so where that
bites. The full procedure — the programme's own, with every template's real filename — is
[[study-launch-pipeline]]. Read it as you work the gate.

Today these documents are made from scratch every time, which makes the PM the serial chokepoint
for every new study. Here you review and finalize instead of starting from a blank page.

## Your first move: ask where the study is

**This is your whole first message.** One question, three options, nothing else — no summary of
the pipeline, no list of documents:

> **Where is the study right now?**
> 1. **The directors just approved it** — time to draft the study documents
> 2. **Ready for stakeholder review / IRB** — time to prepare the ethics submission
> 3. **Ethical approval received** — time to prepare for launch

Then work **that gate's** task list, one task at a time. **Never dump all three gates at once**,
and never start drafting before you know the gate — the same study needs different documents at
each. If they've already told you ("we got ethical approval last week"), don't ask: name the gate
you're taking them to and go.

## Before drafting anything: mine what they already have

1. **Supporting documents first.** Anything describing the study — the study proposal, concept
   note, grant aim, a prior or similar study's protocol, an email thread, a draft questionnaire.
   Ask where they are, READ them, and extract everything you can: title and moniker, PI, sites,
   cancer type, design, aims, accrual, timeline, inclusion/exclusion, variables, contacts,
   funding (NIH or not — it picks two documents later), whether specimens are collected.
2. **Interview for the gaps only.** After mining, ask *only* for what you still can't fill, and
   **never re-ask what the documents already answer.** One question at a time.
3. **Write the profile down once.** `project-manager/new-studies/<study>/STUDY_PROFILE.md` holds
   the study facts, so the next document reuses them instead of re-interviewing.

## Gate 1 — "the directors approved moving forward"

The study's founding documents, drafted from the proposal.

| Task | Official template (in `ARGO Templates/`) | Input |
|---|---|---|
| Protocol | **none yet** — three paths, see below | study proposal |
| Consent form (ICF) | `ARGO IPH Consent Form Template.doc` — legacy `.doc`, see the fill ladder | study proposal |
| Questionnaire | `ARGO Questionnaire Template.docx` — a **design guide**, not a form to fill | questionnaire draft |

**Outputs of this gate:** the protocol draft, the ICF draft, the questionnaire, and
`<MONIKER>_Questionnaire_changelog.md` — what you changed in the questionnaire and why, plus the
open questions for the PI. The changelog ships with the questionnaire; it is not optional.

### The protocol — say the gap, then take one of three paths

**Say this out loud when you reach the protocol:** ARGO has **no protocol template yet** — the
`ARGO Protocol Template/` folder in the File Repository is empty, one is being created.
**Never invent a house style** and never present an invented structure as ARGO's. Then:

1. **Ask the PM for an ARGO protocol that has already been approved** and draft on **that**
   document's structure.
2. **No ARGO protocol, but a comparable approved protocol from the same programme** → draft on
   that, and name which document you used.
3. **Neither — no template exists and the PM has no approved protocol to model.** This is not a
   dead end: you still deliver a protocol, rather than dropping the task and working only the
   consent and the questionnaire. **Draft on the PM's own proposal's structure**: keep its
   section order, add the sections a protocol needs that a proposal lacks,
   and **label it at the top of the document** — *"Drafted on the study proposal's own structure;
   no ARGO protocol template exists yet. To be reconciled against an approved ARGO protocol
   before submission."* This is what ARGO's own editors did.

**The data-management chapter comes from [[redcap-protocol-boilerplate]]** — the standard ARGO
text (REDCap PHI approval, SSL, OAUTHC as database administrator, permission auditing, nightly
backups, de-identified exports to the biostatistician, source documentation, QA cadence, paper
records under lock and key). It is the largest thing a proposal is missing. Carry it with its
`[TODO]`s visible, and say it needs the PI's confirmation — don't write `[TODO: name the
platform]` and move on.

### The consent (ICF) — filling a legacy `.doc`, and three checks

**The official ICF is a legacy binary `.doc`.** Filling it in place may need LibreOffice
(`soffice`) to convert it, and `soffice` is often **absent**. The ladder, and you must say which
rung you used:

1. **`soffice` available** → convert, fill in place, letterhead intact. Report:
   **"filled the official template."**
2. **`soffice` absent** → rebuild the template's structure in a new document and **copy its
   required language verbatim**. Report: **"rebuilt its structure and copied its required
   language verbatim (letterhead not preserved) — reconcile against the official file before
   use."**

**A PM must never be handed a reconstruction believing it is the official file.** Which rung
fired is part of the deliverable.

**Three checks on the consent — run all three, every time, and report what each found:**

1. **Ask about collaborators before you draft — don't assume.** At Gate 1, before drafting:
   *"Which institutions appear as collaborators on this study, and does participant data leave
   Nigeria?"* That one answer rewrites **the protocol title, the objectives, the analysis
   section and the ICF's data-sharing section**, and it **pre-decides Gate 2's DTA rule**. Then
   check the ICF: contact information present, and house practice is **one central PI contact
   block** — do **not** build a per-site contact table unless the PM asks for one. Missing
   contact block → a visible `**[TODO: …]**`, and tell the PM.
2. **IRB template language intact — removals *and* additions.** Compare against the ICF template:
   has any required IRB template text been **removed**, or has anything been **added** to the
   regulatory or signature blocks (a final ICF once gained a "Person Obtaining Consent" signature
   line)? Either way, **flag it and ask the site to edit the consent**. **Never silently restore,
   remove or rewrite it** — that edit is the site's to make, and a consent quietly patched by a
   tool is a consent nobody reviewed.
3. **Every template heading survives.** Keep all of them; where one doesn't apply, answer **"Not
   applicable"** rather than deleting the heading. ARGO's own finals answered exactly that for
   *Biological specimens*, *Payment of treatment costs*, *Clinical Trial Registration* and
   *Conflict of Interest*.

### The questionnaire — build to the guide, don't fill it

**`ARGO Questionnaire Template.docx` is a design GUIDE, not a fillable form.** Its Sections 1–5
are ARGO's drafting principles. **Build the questionnaire *to* its rules; never fill it in and
never emit its advice as the instrument.** The study's own questions come from the questionnaire
draft, the proposal and the PI.

**The three-class edit policy — what ARGO's editors actually did:**

- **(a) Mechanical defects — fix and log.** Wrong-cancer paste, triplicated blocks, hand-derived
  values, unanswerable items: the editors fixed exactly these. **Typos they left alone.**
- **(b) Clinical content — propose, never invent.** The finals went far deeper than the draft (an
  HIV block, HPV serotypes, FIGO and histology lists, structured exam grids, state of origin) —
  but that content came from clinicians. Propose it; the PI decides.
- **(c) Unstructured sections may be DELETED rather than repaired — ask before rebuilding.** One
  draft rebuilt a financial-toxicity section that the programme then cut entirely.

**Standing rule: never collapse co-occurring clinical events into select-one for tidiness**
(surgery procedures, recurrence sites — a patient can have more than one).

**Structural pre-flight before the questionnaire leaves this skill.** ARGO's own finals shipped
every one of these, so check all five:

- **Controlled vocabularies**, staging above all — a real final carried an invented FIGO stage
  (`IA3`) and roman/arabic corruption (`IB11`, `IB111`, `IIA11`, `IIIC11`).
- **Unit sanity** — `kg/m²` written where `mg/m²` was meant.
- **Duplicates** — repeated questions, repeated options, repeated blocks.
- **Consistent missing-value third columns** on every question of the same type, per
  [[mdc-rules]].
- **Cross-document check** — do the sites named in the protocol match the site field in the
  questionnaire? (One final protocol listed six sites while the proforma's hospital field was a
  single checkbox reading OAUTHC.)

Findings go in `<MONIKER>_Questionnaire_changelog.md` for the PI — **not** silent fixes.

## Gate 2 — "ready for stakeholder review and IRB"

| Task | Official template |
|---|---|
| Stakeholder review email | drafted — no template |
| IRB submission form | `ARGO IPH HREC Application Form Template.docx` — content map: `templates/irb-application.md` |
| DTA / MTA | `OAU Data Transfer Agreement_Template.docx` (in `OAUTHC DTA Template/`) |

**Stakeholder review comes BEFORE the IRB submission.** Circulate the protocol, consent and
questionnaire to the PI, Research Managers, Biostatisticians, RAs and Community Healthcare
Workers as needed; the submission goes out after that round comes back.

**Say this out loud if the site is OAUTHC:** there is **no OAUTHC submission template** in the
repository — the IPH HREC application form is what exists. Draft on the IPH form and tell the PM
that the OAUTHC-specific form has to come from the site.

`templates/irb-application.md` is the **content map for this form** — the questions the committee
asks, in its order. It is an IRB-application map, **not** a protocol skeleton: the protocol is
Gate 1's separate, earlier document. The map summarises the protocol; it never replaces it.

**The DTA skip rule — apply it, then say which rule fired.** List the participating sites first,
so the rule is applied to a written-down list rather than a memory (Gate 1's collaborator
question — *which institutions are collaborators, and does data leave Nigeria?* — has already
answered this; reuse the answer rather than re-asking). Then:

- **All sites are Nigerian federal hospitals** → **no DTA/MTA is required.** Skip the task and say
  so: *"all sites are Nigerian federal hospitals, so no DTA is needed."*
- **Anything else** (a non-Nigerian site, a non-federal institution, data leaving to a
  collaborator) → draft the DTA from the template, and name the site that triggered it.

Never skip silently, and never draft one silently: the sentence saying which rule fired is part
of the deliverable.

## Gate 3 — "ethical approval received"

**The precondition, first.** List **every** participating site and confirm, site by site, that
you have (a) that site's ICF and (b) that site's ethical clearance. A site missing either is not
ready to launch — name it, say what's missing, and carry on with the rest.

| Task | Official template |
|---|---|
| CPL — one per site | `ARGO Consenting Professional List (CPL) Template.docx` |
| ECL — one document covering all sites | `ARGO Eligibility Checklist (ECL) Template.docx` |
| Study guide / study SOP | `ARGO Study SOP Template.docx` |
| Lab manual — specimen studies only | `ARGO Biospecimen Laboratory Manual Template.docx` |
| Lab requisition — specimen studies only | `ARGO Lab Requisition Template.docx` |
| Study QA plan | `ARGO QA Plan.docx` (in `ARGO Quality Assurance (QA)/`, outside `ARGO Templates/`) |
| **REDCap build request** | the SIR survey — the hand-off, see below |
| Monthly study meeting agenda | `ARGO Study Meeting Template.docx` |
| Accrual table for the joint call, if needed | `ARGO Joint Call Study Accrual Template.docx` |
| SIV scheduling | zoom link + stakeholder email — drafted |
| SIV slides | `ARGO SIV Template.pptx` — see below |
| SIV attendance | `Protocol Training Attendance Log Template.docx` |
| New Study / New Site checklist | `New Study_New Site Checklist_NIH Funded Final.docx` or `New Study_New Site Checklist_non-NIH Funded Final.docx` — pick by funding |
| Activation memo | `ARGO Activation Memo Template.docx` — see below |
| Activation email to all stakeholders | drafted |

Inputs: the CPL needs the consenting professionals per site; the ECL needs the eligibility
criteria; the lab documents happen **only if the study collects specimens** — ask once, and skip
both without ceremony if it doesn't.

### The procedure's own reference text: the Study Start-Up SOP

Two of them, in `ARGO Standard Operating Procedures (SOPs)/Study Start-Up/` — one for **NIH-funded**
studies, one for **non-NIH**. Ask how the study is funded, read the matching one, and follow it.
The same funding answer picks the checklist variant in the table above; ask it once, use it twice.

### Say these out loud, at the task they belong to

- **Activation memo** — the official template is a **flattened image**, so it has no fields to
  fill. Draft the memo's *content* and hand it over for the PM to place on the official memo. Say
  that's what you did; never imply the template itself was filled.
- **SIV slides** — the deck is PowerPoint (`.pptx`), which the docx skill does not cover. If this
  session has a **pptx skill**, use it on the official template. If it doesn't, say so and draft
  the slide content as text, slide by slide, for the PM to paste into the official deck. The
  attendance log is a `.docx` and gets filled normally.

### Where the pipeline ends: the REDCap build request

**The PM submits the SIR survey** — the Study Initiation Request in REDCap — **with every document
above attached** for the study's File Repository. That submission is the hand-off: [[build-study]]
(argo-database-manager) triages the SIR and builds the database from the questionnaire.

Don't submit it for them and don't ask for a key to do it — the survey is filled in REDCap by the
PM. Your job is to make that one sitting: the package complete, every file named with the study
moniker, and a short list telling them which document goes in which SIR upload field.

## Rules that govern every task

1. **Fill, don't fabricate.** Populate the template from the mined documents and the PM's answers.
   Anything genuinely unknown becomes a visible `**[TODO: …]**` for the PM — **never** invent
   regulatory facts, IRB numbers, ethics statements, approval dates, PI details or site contacts.
2. **Real documents, not markdown.** Invoke the **docx** skill to produce the `.docx`; markdown
   skeletons are the working form, never the deliverable. (The SIV deck is the `.pptx` exception
   above; `<MONIKER>_Questionnaire_changelog.md` is a working note for the PI and stays markdown.)
3. **One folder per study, moniker naming.** Everything lands in
   `project-manager/new-studies/<study>/`, and every file is named with the study moniker
   (`<MONIKER>_ICF_draft.docx`, `<MONIKER>_CPL_<site>.docx`,
   `<MONIKER>_Questionnaire_changelog.md`) — the SIR attachments and the File Repository are
   named the same way, so a well-named draft is one drag rather than a rename.
4. **The questionnaire is analysis-driven.** It must be buildable: one question at a time, coded
   categoricals over free text, consistent scales, sectioned, validation-friendly — fields that map
   cleanly to a REDCap data dictionary ([[dd-column-spec]], [[mdc-rules]]). [[build-study]]'s
   Path A pulls the data dictionary straight out of it.
5. **Everything is a draft for the PM.** Say so, every time — especially the protocol, the consent
   and the IRB form, which are formal regulatory documents.
6. **Templates are never committed.** They carry internal contact details; they live in the user's
   workspace and nowhere else.

## The official Word templates — use them when you can

The real templates (official formatting, letterhead) live in the **Study Tracker's File
Repository**, not in this skill — the toolkit's repository is public and the templates contain
internal contact details, so they are fetched or downloaded, never bundled. Precedence:

1. **Already in the workspace?** Look before fetching:
   `find "<workspace>/project-manager/templates-official" -name "*.doc*" 2>/dev/null | head`
   — search the connected ARGO folder only, recursively (the fetch step writes a nested
   tree). Never search the whole home folder: a copy from an unrelated folder may be stale
   and carries staff contact details. A `FileRepository_*/ARGO Templates/` folder the user
   downloaded by hand and dropped into the workspace also counts.
2. **Not there, and the Study Tracker key is configured?** Fetch once into the workspace:
   `python3 fetch_templates.py --to <workspace>/project-manager/templates-official`
   (it brings the `ARGO Templates/` tree, the QA plan and the two Study Start-Up SOPs).
3. **Neither?** Use the markdown skeletons below and render via the docx skill — the content is
   identical; only the official styling is approximated. **Tell the user which path you took.**

When an official template exists, use it as the base document and fill its placeholders (docx
skill), keeping its formatting; the markdown skeleton then serves as the content map. **Two Gate-1
templates are exceptions:** `ARGO Questionnaire Template.docx` is a design guide and is never
filled at all (build to its rules), and `ARGO IPH Consent Form Template.doc` is a legacy `.doc`
whose in-place fill may need `soffice` — take Gate 1's ladder and **name the rung you used**.

| Skeleton in `templates/` | Official file it approximates |
|---|---|
| `questionnaire-proforma.md` | *(the study's instrument, built **to** the rules in `ARGO Questionnaire Template.docx` — that file is a design guide, so there is nothing to fill)* |
| `irb-application.md` | `ARGO IPH HREC Application Form Template.docx` — **Gate 2's** content map (it was mis-filed as a protocol skeleton; it never was one) |
| `study-guide.md` | `ARGO Study SOP Template.docx` |
| `activation-memo.md` | `ARGO Activation Memo Template.docx` (flattened image — content only) |
| `siv-outline.md` | `ARGO SIV Template.pptx` + `Protocol Training Attendance Log Template.docx` |
| `lab-requisition.md` | `ARGO Lab Requisition Template.docx` |
| `startup-checklist.md` | `New Study_New Site Checklist_NIH Funded Final.docx` / `New Study_New Site Checklist_non-NIH Funded Final.docx` |

Tasks with no skeleton (ICF, DTA, CPL, ECL, lab manual, QA plan, meeting agenda, accrual table)
are drafted from the **fetched template** itself. The **protocol** has no skeleton and no
official template — it takes Gate 1's three paths, with [[redcap-protocol-boilerplate]] for its
data-management chapter. If neither the template nor a skeleton is available, say so, draft the
content from [[study-launch-pipeline]]'s description of that document, and mark it clearly as an
approximation for the PM to reconcile against the official form.

Fetched templates stay in `project-manager/templates-official` in the user's workspace.
**Never commit or publish them.**

## What comes after launch

Amendment submission, and collecting each site's amendment approvals. That procedure isn't built
here yet — say so if asked, rather than improvising one.

## See also

- [[study-launch-pipeline]] — the full procedure: every gate, every task, every real filename
- [[redcap-protocol-boilerplate]] — the standard ARGO data-management text for the protocol
- [[build-study]] (argo-database-manager) — what happens after the PM submits the SIR
- [[dd-column-spec]], [[mdc-rules]] — keep the questionnaire buildable
- docx skill — used to render the Word deliverables
