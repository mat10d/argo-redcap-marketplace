---
name: new-study-documents
description: Walk a new ARGO study through the launch pipeline — from the directors' approval to the REDCap build request. Asks one question first (where the study is: approved, ready for IRB, or ethical approval received), then works that gate's tasks one at a time, each filling its official ARGO template. Reads whatever you already have — proposal, concept note, questionnaire draft, an email thread — asks only about what's genuinely missing, and hands you real documents to review. Use for "the directors approved the study", "prepare the IRB submission", "we got ethical approval", "study activation", "set up a new study", "draft the questionnaire for this study", "prep the new-study documents".
allowed-tools: Read, Bash, Write, Edit, Glob, Grep, Skill
---

# new-study-documents — the study-launch pipeline

The project manager's real job, from *"the directors approved it"* to the REDCap build request.
**Three gates**, each a natural moment in a study's life, each with its own task list; every task
fills ONE named official template. The full procedure — the programme's own, with every
template's real filename — is [[study-launch-pipeline]]. Read it as you work the gate.

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
| Protocol | **none yet** — see below | study proposal |
| Consent form (ICF) | `ARGO IPH Consent Form Template.doc` | study proposal |
| Questionnaire | `ARGO Questionnaire Template.docx` | questionnaire draft |

**Say this out loud when you reach the protocol:** ARGO has **no protocol template yet** — the
`ARGO Protocol Template/` folder in the File Repository is empty, one is being created. So ask the
PM for an ARGO protocol that has already been approved, and draft on **that** document's
structure. **Never invent a house style** and never present an invented structure as ARGO's. If
they have no approved protocol to hand, say the gap plainly and stop at the other two tasks.

**Two checks on the consent — run both, every time, and report what each found:**

1. **Collaborating sites and contact information.** Every collaborating site that will see the
   data is named as needed — e.g. *"data will be shared with MSK for analysis"* — and site
   contact information is present in the ICF. Missing site or missing contact block → a visible
   `**[TODO: …]**`, and tell the PM.
2. **IRB template language intact.** Compare against the ICF template: has any required IRB
   template text been removed? If so, **flag it and ask the site to edit the consent** so all the
   required language is present again. **Never silently restore or rewrite it** — that edit is the
   site's to make, and a consent quietly patched by a tool is a consent nobody reviewed.

## Gate 2 — "ready for stakeholder review and IRB"

| Task | Official template |
|---|---|
| Stakeholder review email | drafted — no template |
| IRB submission form | `ARGO IPH HREC Application Form Template.docx` |
| DTA / MTA | `OAU Data Transfer Agreement_Template.docx` (in `OAUTHC DTA Template/`) |

**Stakeholder review comes BEFORE the IRB submission.** Circulate the protocol, consent and
questionnaire to the PI, Research Managers, Biostatisticians, RAs and Community Healthcare
Workers as needed; the submission goes out after that round comes back.

**Say this out loud if the site is OAUTHC:** there is **no OAUTHC submission template** in the
repository — the IPH HREC application form is what exists. Draft on the IPH form and tell the PM
that the OAUTHC-specific form has to come from the site.

**The DTA skip rule — apply it, then say which rule fired.** List the participating sites first,
so the rule is applied to a written-down list rather than a memory. Then:

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
   above.)
3. **One folder per study, moniker naming.** Everything lands in
   `project-manager/new-studies/<study>/`, and every file is named with the study moniker
   (`<MONIKER>_ICF_draft.docx`, `<MONIKER>_CPL_<site>.docx`) — the SIR attachments and the File
   Repository are named the same way, so a well-named draft is one drag rather than a rename.
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
skill), keeping its formatting; the markdown skeleton then serves as the content map.

| Skeleton in `templates/` | Official file it approximates |
|---|---|
| `questionnaire-proforma.md` | `ARGO Questionnaire Template.docx` |
| `protocol.md` | *(no official protocol template — Gate 1's gap; the skeleton is a content map only)* |
| `study-guide.md` | `ARGO Study SOP Template.docx` |
| `activation-memo.md` | `ARGO Activation Memo Template.docx` (flattened image — content only) |
| `siv-outline.md` | `ARGO SIV Template.pptx` + `Protocol Training Attendance Log Template.docx` |
| `lab-requisition.md` | `ARGO Lab Requisition Template.docx` |
| `startup-checklist.md` | `New Study_New Site Checklist_NIH Funded Final.docx` / `New Study_New Site Checklist_non-NIH Funded Final.docx` |

Tasks with no skeleton (ICF, IRB form, DTA, CPL, ECL, lab manual, QA plan, meeting agenda,
accrual table) are drafted from the **fetched template** itself. If neither the template nor a
skeleton is available, say so, draft the content from [[study-launch-pipeline]]'s description of
that document, and mark it clearly as an approximation for the PM to reconcile against the
official form.

Fetched templates stay in `project-manager/templates-official` in the user's workspace.
**Never commit or publish them.**

## What comes after launch

Amendment submission, and collecting each site's amendment approvals. That procedure isn't built
here yet — say so if asked, rather than improvising one.

## See also

- [[study-launch-pipeline]] — the full procedure: every gate, every task, every real filename
- [[build-study]] (argo-database-manager) — what happens after the PM submits the SIR
- [[dd-column-spec]], [[mdc-rules]] — keep the questionnaire buildable
- docx skill — used to render the Word deliverables
