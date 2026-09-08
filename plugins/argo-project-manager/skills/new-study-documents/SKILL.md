---
name: new-study-documents
description: Walk a new ARGO study through the launch pipeline — from the directors' approval to the REDCap build request. Asks one question first (where the study is: approved, ready for IRB, or ethical approval received), then works that gate's tasks one at a time, each producing one named ARGO document from its official template (or, where the template is a design guide rather than a form, built to its rules). Reads whatever you already have — proposal, concept note, questionnaire draft, an email thread — asks only about what's genuinely missing, and hands you real documents to review. Use for "the directors approved the study", "prepare the IRB submission", "we got ethical approval", "study activation", "set up a new study", "draft the questionnaire for this study", "prep the new-study documents".
allowed-tools: Read, Bash, Write, Edit, Glob, Grep, Skill
---

# new-study-documents — the study-launch pipeline

The project manager's real job, from *"the directors approved it"* to the REDCap build request.
**Three gates**, each a natural moment in a study's life, each with its own task list; every task
produces ONE named document from its official ARGO template — with three exceptions that each
gate flags where it bites. The full procedure — the programme's own, with every template's real
filename — is [[study-launch-pipeline]]. Read it as you work the gate.

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
   cancer type, design, aims, accrual, timeline, inclusion/exclusion, variables, contacts — and
   above all the **seven branching facts** in the next section, most of which a proposal answers.
2. **Interview for the gaps only.** After mining, ask *only* for what you still can't fill, and
   **never re-ask what the documents already answer.** One question at a time.
3. **Write the profile down once.** `project-manager/new-studies/<study>/STUDY_PROFILE.md` holds
   the study facts, so the next document reuses them instead of re-interviewing.

## The seven facts that branch everything

Almost every task below is the same for every study. **Seven answers are what make one study's
document set differ from another's** — and each one decides several documents at once, across
gates. Get them into `STUDY_PROFILE.md` and the rest is filling.

| # | The fact | What it decides |
|---|---|---|
| 1 | **Which gate** the study is at | Which task list you work at all — the first question, always |
| 2 | **Collaborators, and whether participant data leaves Nigeria** | Protocol title, objectives, 14.6 and 17.0; the ICF's data-sharing section; **Gate 2's DTA rule** |
| 3 | **Funding: NIH or not** | Which Study Start-Up SOP you read; which New Study / New Site checklist you fill |
| 4 | **Specimens: collected or not** | Protocol 5.6 and 8.4; the lab manual and lab requisition at Gate 3 — kept or removed together |
| 5 | **Design: prospective, retrospective, or both** | The consent scenario; eligibility; whether **two** consent scenarios are kept |
| 6 | **Consent scenario** (written / verbal / read-and-sign / waived) | Protocol 7.x; the ICF; the HREC application; protocol 4.1's consent criterion |
| 7 | **Sites: one or many, and are all of them Nigerian federal hospitals** | Protocol 5.2, 6.1, 17.0 and Appendix I; one CPL **per site** at Gate 3; the DTA rule; the questionnaire's site field |

**How to get them — this is the part that goes wrong.**

- **Mine before you ask.** Most are in the proposal. Never ask for something the documents you
  were given already answer.
- **Ask each one once, at the first task that needs it**, not as an interrogation up front. Fact 2
  is the exception: ask it **at Gate 1 before drafting anything**, because it rewrites the
  protocol's title and objectives, and by the time you notice it at Gate 2 the drafts are wrong.
- **Write the answer down the moment you have it**, and **never re-ask across gates.** Fact 3
  picks two documents; fact 7 picks four. A PM asked twice for the same fact has been asked once
  too often.
- **An unanswered fact is stated, not guessed.** Say which one is open and what it blocks, and
  work everything that doesn't depend on it.

## Gate 1 — "the directors approved moving forward"

The study's founding documents, drafted from the proposal.

| Task | Official template (in `ARGO Templates/`) | Input |
|---|---|---|
| Protocol | `ARGO Protocol Template.docx` — fill it; map in [[protocol-fill-map]] | study proposal |
| Consent form (ICF) | `ARGO IPH Consent Form Template.doc` — legacy `.doc`, see the fill ladder | study proposal |
| Questionnaire | `ARGO Questionnaire Template.docx` — a **design guide**, not a form to fill | questionnaire draft |

**Outputs of this gate:** the protocol draft, the ICF draft, the questionnaire, and
`<MONIKER>_Questionnaire_changelog.md` — what you changed in the questionnaire and why, plus the
open questions for the PI. The changelog ships with the questionnaire; it is not optional.

### The protocol — fill the official template

**One question comes first, before a word is drafted** (branching fact 2 — ask it here, at the
gate's first task, not later at the consent):

> *"Which institutions appear as collaborators on this study, and does participant data leave Nigeria?"*

**Ask about collaborators — don't assume.** That one answer rewrites **the protocol title, the
objectives, the analysis section and the ICF's data-sharing section**, decides whether 14.6 and
17.0 stay, and it **pre-decides Gate 2's DTA rule**. Asked after the protocol is drafted, it
invalidates the draft.

*Open policy question, unresolved:* whether ARGO studies are presented as Nigerian-led with ARGO
as the collaborator is not settled — the programme's teaching case removed the foreign
collaborator from every document, but no rule is written. **So ask; never infer it from what a
previous study did.**

**`ARGO Protocol Template.docx` is the protocol.** Seventeen sections, and an italicised
instruction under almost every heading saying what that section must contain. **Read those
instructions and follow them.** Never draft a section whose instruction you haven't read, never
substitute a structure of your own, and **never invent a house style** — the template is ARGO's
house style now.

Fill it against [[protocol-fill-map]], which says where each section's answer comes from:

- **From the proposal** — summary, objectives, background, eligibility, design, sites, duration,
  accrual, references. This is most of the document, and it is why the proposal is the input.
- **From the PI** — screening, procedures, follow-up, withdrawal, outcome definitions, risks,
  the institutional facts in 14.x.
- **From the named biostatistician** — 12.1–12.4. The template requires one on the cover sheet
  **before the protocol is circulated for review**. If there isn't one, say so: it blocks.
- **ARGO's standing answers** — 14.2's REDCap chapter, 14.3's source documentation, 14.4's QA
  cadence. [[protocol-fill-map]] carries them. **Propose, PI confirms**; an unconfirmed
  institutional fact stays a visible `**[TODO: …]**`, never an asserted regulatory claim.

**Three things the template asks of you that are easy to miss:**

1. **Answer every bracketed placeholder, or write "Not applicable"** — never delete the row or
   leave it blank. The template says a silent protocol reads as an oversight.
2. **Delete the italicised instructions and the version line** before the draft goes out — but
   only sections marked *(remove if not applicable)* may be removed, and **don't renumber** until
   the whole document is drafted.
3. **Keep only the consent scenario(s) that apply** (7.1–7.4) — and a study that is *both*
   prospective and retrospective keeps two. It must match the ICF and the HREC application.

Before the draft leaves you, run [[protocol-fill-map]]'s **cross-document checks** — objectives
against outcomes against the analysis plan; 8.2's data items against the questionnaire; the site
list in its four places; withdrawal handling against the ICF word for word.

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

1. **Contact block present, and only one.** The collaborator answer you already have from the
   protocol task writes the ICF's data-sharing section — reuse it, don't re-ask. Then check the
   ICF's own convention: contact information must be present, and house practice is **one central
   PI contact block** — do **not** build a per-site contact table unless the PM asks for one.
   Missing contact block → a visible `**[TODO: …]**`, and tell the PM.
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

- **Activation memo** — the template's whole body sits in a **floating text box over the
  letterhead image**. It is perfectly editable in Word, but text in a text box is invisible to
  docx tooling, so a fill attempt will report success and change nothing. Draft the memo's
  *content* — date, PI name, study title, site names, signatory — and hand it over for the PM to
  type into the official memo. Say that's what you did; never imply the template itself was
  filled. Its standing instruction is worth repeating to the PM: registration paperwork (signed
  ICF, completed eligibility checklist, supporting source documentation) goes into OAU REDCap
  **within 24 hours** of the consent being signed.
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

Every task that has a template now has one — including the protocol — so the default is always:
**use it as the base document and fill its placeholders** (docx skill), keeping its formatting; a
markdown skeleton is then only the content map. (Four tasks have no template and never did: the
stakeholder review email, the SIV scheduling email, the activation email, and the SIR submission
itself.) **Three templates are exceptions, and each says so at its own task:**

| Exception | Why | What you do instead |
|---|---|---|
| `ARGO Questionnaire Template.docx` | It is a **design guide**, not a form — Sections 1–5 are drafting principles | Build the questionnaire **to** its rules; never fill it, never emit its advice as the instrument |
| `ARGO IPH Consent Form Template.doc` | Legacy binary `.doc`; in-place fill may need `soffice`, which is often absent | Gate 1's ladder — and **name the rung you used** |
| `ARGO Activation Memo Template.docx` | The body is a floating **text box**, invisible to docx tooling | Draft the content; the PM types it into the official memo |

The `.pptx` SIV deck is a fourth case, handled at its Gate 3 task.

| Skeleton in `templates/` | Official file it approximates |
|---|---|
| `questionnaire-proforma.md` | *(the study's instrument, built **to** the rules in `ARGO Questionnaire Template.docx` — that file is a design guide, so there is nothing to fill)* |
| `irb-application.md` | `ARGO IPH HREC Application Form Template.docx` — **Gate 2's** content map (it was mis-filed as a protocol skeleton; it never was one) |
| `study-guide.md` | `ARGO Study SOP Template.docx` |
| `activation-memo.md` | `ARGO Activation Memo Template.docx` (body is a text box — content only) |
| `siv-outline.md` | `ARGO SIV Template.pptx` + `Protocol Training Attendance Log Template.docx` |
| `lab-requisition.md` | `ARGO Lab Requisition Template.docx` |
| `startup-checklist.md` | `New Study_New Site Checklist_NIH Funded Final.docx` / `New Study_New Site Checklist_non-NIH Funded Final.docx` |

Tasks with no skeleton (protocol, ICF, DTA, CPL, ECL, lab manual, QA plan, meeting agenda,
accrual table) are drafted from the **fetched template** itself — the protocol against
[[protocol-fill-map]]. If neither the template nor a skeleton is available, say so, draft the
content from [[study-launch-pipeline]]'s description of that document, and mark it clearly as an
approximation for the PM to reconcile against the official form.

Fetched templates stay in `project-manager/templates-official` in the user's workspace.
**Never commit or publish them.**

## What comes after launch

Amendment submission, and collecting each site's amendment approvals. That procedure isn't built
here yet — say so if asked, rather than improvising one.

## See also

- [[study-launch-pipeline]] — the full procedure: every gate, every task, every real filename
- [[protocol-fill-map]] — where each of the protocol template's 17 sections gets its answer
- [[build-study]] (argo-database-manager) — what happens after the PM submits the SIR
- [[dd-column-spec]], [[mdc-rules]] — keep the questionnaire buildable
- docx skill — used to render the Word deliverables
