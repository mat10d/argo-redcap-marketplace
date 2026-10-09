---
name: new-study-documents
description: Walk a new ARGO study through the launch pipeline — from the directors' approval to the REDCap build request. Asks one question first (where the study is: approved, ready for IRB, or ethical approval received), then works that gate's tasks one at a time, each producing one named ARGO document from its official template (or, where the template is a design guide rather than a form, built to its rules). Reads whatever you already have — proposal, concept note, questionnaire draft, an email thread — asks only about what's genuinely missing, and hands you real documents to review. Use for "the directors approved the study", "prepare the IRB submission", "we got ethical approval", "study activation", "set up a new study", "draft the questionnaire for this study", "prep the new-study documents".
allowed-tools: Read, Bash, Write, Edit, Glob, Grep, Skill
---

# new-study-documents — the study-launch pipeline

The project manager's job from *"the directors approved it"* to the REDCap build request:
**three gates**, each with its own task list, each task producing one named document from its
official ARGO template. Where each template lives in the File Repository, and where this
procedure came from, is in [[study-launch-pipeline]]. The PM reviews and finalizes; you draft.

## Your first move: ask where the study is

**This is your whole first message.** One question, three options, nothing else — no summary of
the pipeline, no list of documents:

> **Where is the study right now?**
> 1. **The directors just approved it** — time to draft the study documents
> 2. **Ready for stakeholder review / IRB** — time to prepare the ethics submission
> 3. **Ethical approval received** — time to prepare for launch

Then work **that gate's** tasks, one task at a time. **Never dump all three gates at once** — the
same study needs different documents at each gate. If they've already told you ("we got ethical
approval last week"), don't ask: name the gate and go.

## Before drafting anything: mine what they already have

1. **Read their documents first** — proposal, concept note, a prior study's protocol, an email
   thread, a draft questionnaire. Extract title and moniker, PI, sites, cancer type, design, aims,
   accrual, timeline, eligibility, variables, contacts — and the **seven facts** below.
2. **Interview for the gaps only**, one question at a time, and **never re-ask what the documents
   already answer.** One role per question — ask for the PI and the biostatistician separately.
   If someone answers a combined question with one name ("PI and biostatistician: Prof. X"), that
   person holds **both** roles: record both, and say so back in one line ("Prof. X is PI and
   biostatistician"). Never mark a role missing that the answer filled.
3. **Write the profile down once** in `project-manager/new-studies/<study>/STUDY_PROFILE.md`, so
   the next document reuses it instead of re-interviewing.

## The seven facts that branch everything

Almost every task is the same for every study. **Seven answers make one study's document set
differ from another's**, and each decides several documents, across gates:

| # | The fact | What it decides |
|---|---|---|
| 1 | **Which gate** the study is at | Which task list you work at all — the first question, always |
| 2 | **Collaborators, and whether participant data leaves Nigeria** | Protocol title, objectives and analysis; protocol 14.1 and 14.6; the ICF's data-sharing section; **Gate 2's DTA rule** |
| 3 | **Funding: NIH or not** | Which Study Start-Up SOP you read; which New Study / New Site checklist you fill |
| 4 | **Specimens: collected or not** | Protocol 5.6 and 8.4; the lab manual and lab requisition at Gate 3 — kept or removed together |
| 5 | **Design: prospective, retrospective, or both** | The consent scenario; eligibility; whether **two** consent scenarios are kept |
| 6 | **Consent scenario** (written / verbal / read-and-sign / waived) | Protocol 7.x and 4.1's consent criterion; the ICF; the HREC application |
| 7 | **Sites: one or many, and are all of them Nigerian federal hospitals** | Protocol 5.2, 6.1, Appendix I, and whether 17.0 stays; one CPL **per site** at Gate 3; the DTA rule; the questionnaire's site field |

- **Mine before you ask.** Most are in the proposal.
- **Ask each one once, at the first task that needs it** — not as an interrogation up front. Fact 2
  is the exception: ask it **at Gate 1 before drafting anything**, because it rewrites the
  protocol's title and objectives; noticed at Gate 2, the drafts are already wrong.
- **Write each answer down the moment you have it, and never re-ask across gates.** A PM asked
  twice for the same fact has been asked once too often.
- **An unanswered fact is stated, not guessed.** Say which one is open and what it blocks, and
  work everything that doesn't depend on it.

## Gate 1 — "the directors approved moving forward"

| Task | Official template (in `ARGO Templates/`) | Input |
|---|---|---|
| Protocol | `ARGO Protocol Template.docx` — fill it against [[protocol-fill-map]] | study proposal |
| Consent form (ICF) | `ARGO IPH Consent Form Template.doc` — legacy `.doc`, see the fill ladder | study proposal |
| Questionnaire | `ARGO Questionnaire Template.docx` — a **design guide**, not a form to fill | questionnaire draft |

**Outputs:** the protocol draft, the ICF draft, the questionnaire, and
`<MONIKER>_Questionnaire_changelog.md` — what you changed in the questionnaire and why, plus the
open questions for the PI. The changelog ships with the questionnaire.

### The protocol — fill the official template

**One question comes before a word is drafted** (fact 2):

> *"Which institutions appear as collaborators on this study, and does participant data leave Nigeria?"*

Ask — don't assume, and never infer it from what a previous study did. The answer rewrites **the
protocol title, the objectives, the analysis section and the ICF's data-sharing section**, writes
14.6, and **pre-decides Gate 2's DTA rule**. Whether ARGO studies are presented as Nigerian-led
with ARGO as the collaborator is an open policy question: the programme's teaching case removed
the foreign collaborator from every document, but no rule is written.

**`ARGO Protocol Template.docx` is the protocol** — seventeen sections, with an italicised
instruction under almost every heading saying what that section must contain. Read each
instruction before drafting its section and follow it. Don't substitute a structure of your own
and **never invent a house style** — the template is ARGO's house style.

[[protocol-fill-map]] says where each section's answer comes from — the proposal (most of it), the
PI, the named biostatistician, or one of ARGO's standing answers (propose them; the PI confirms;
an unconfirmed one stays a visible `**[TODO: …]**`) — and collects the template's own rules
(answer every placeholder or write "Not applicable", keep only the consent scenario(s) that apply,
don't renumber until the end). The template requires a **named biostatistician** on the cover
sheet before the protocol is circulated for review; if there isn't one, say so — it blocks.
The biostatistician is a person to bring in, not a gap to draft around: never fill 12.1–12.4
with plausible statistics.
Before the draft leaves you, run the map's **cross-document checks**.

### The consent (ICF) — a legacy `.doc`, and three checks

**The official ICF is a legacy binary `.doc`.** Filling it in place needs LibreOffice (`soffice`)
to convert it, and `soffice` is often absent (the failure is a bare `FileNotFoundError`, easy to
paper over). Use the first rung that works, and say which:

1. **`soffice` available** → convert, fill in place, letterhead intact. Report:
   **"filled the official template."**
2. **`soffice` absent** → rebuild the template's structure in a new document and **copy its
   required language verbatim**. Report: **"rebuilt its structure and copied its required
   language verbatim (letterhead not preserved) — reconcile against the official file before
   use."**

**A PM must never be handed a reconstruction believing it is the official file.**

**Three checks — run all three and report what each found:**

1. **One contact block, with contact information present.** Reuse the collaborator answer for the
   data-sharing section; don't re-ask. House practice is **one central PI contact block** — do
   **not** build a per-site contact table unless the PM asks. Missing → a visible
   `**[TODO: …]**`, and tell the PM.
2. **IRB template language intact — removals *and* additions.** Has required IRB template text been
   **removed**, or anything **added** to the regulatory or signature blocks (a final ICF once
   gained a "Person Obtaining Consent" signature line)? Flag it and ask the site to edit the
   consent. **Never silently restore, remove or rewrite it** — a consent quietly patched by a
   tool is a consent nobody reviewed.
3. **Every template heading survives.** Where one doesn't apply, answer **"Not applicable"** rather
   than deleting it — as ARGO's finals did for *Biological specimens*, *Payment of treatment
   costs*, *Clinical Trial Registration* and *Conflict of Interest*.

### The questionnaire — build to the guide, don't fill it

**`ARGO Questionnaire Template.docx` is a design GUIDE, not a fillable form** — its Sections 1–5
are ARGO's drafting principles. **Build the questionnaire *to* its rules**; never emit its advice
as the instrument. The study's questions come from the questionnaire draft, the proposal and the
PI. It must be buildable — one question at a time, coded categoricals over free text, consistent
scales, sectioned — because [[build-study]]'s Path A pulls the data dictionary straight out of it
([[dd-column-spec]], [[mdc-rules]]).

**The three-class edit policy — what ARGO's editors actually did:**

- **(a) Mechanical defects — fix and log.** Wrong-cancer paste, triplicated blocks, hand-derived
  values, unanswerable items. **Typos they left alone.**
- **(b) Clinical content — propose, never invent.** The finals went far deeper than the draft (an
  HIV block, HPV serotypes, FIGO and histology lists, structured exam grids, state of origin) —
  but that content came from clinicians. Propose it; the PI decides.
- **(c) Unstructured sections may be DELETED rather than repaired — ask before rebuilding.** One
  draft rebuilt a financial-toxicity section that the programme then cut entirely.

**Standing rule: never collapse co-occurring clinical events into select-one for tidiness**
(surgery procedures, recurrence sites — a patient can have more than one).

**Structural pre-flight** — ARGO's own finals shipped every one of these defects:

- **Controlled vocabularies**, staging above all — a real final carried an invented FIGO stage
  (`IA3`) and roman/arabic corruption (`IB11`, `IB111`, `IIA11`, `IIIC11`).
- **Unit sanity** — `kg/m²` written where `mg/m²` was meant.
- **Duplicates** — repeated questions, options or blocks.
- **Consistent missing-value third columns** on every question of the same type, per
  [[mdc-rules]].
- **Cross-document check** — do the sites named in the protocol match the site field in the
  questionnaire? (One final protocol listed six sites; the proforma's hospital field was a single
  checkbox reading OAUTHC.)

Findings go in `<MONIKER>_Questionnaire_changelog.md` for the PI — **not** silent fixes.

## Gate 2 — "ready for stakeholder review and IRB"

| Task | Official template |
|---|---|
| Stakeholder review email | drafted — no template |
| IRB submission form | `ARGO IPH HREC Application Form Template.docx` — content map: `templates/irb-application.md` |
| DTA / MTA | `OAU Data Transfer Agreement_Template.docx` |

**Stakeholder review comes first.** Circulate the protocol, consent and questionnaire to the PI,
Research Managers, Biostatisticians, RAs and Community Healthcare Workers as needed; the IRB
submission goes out after that round comes back.

**If the site is OAUTHC, say so:** there is **no OAUTHC submission template** in the repository —
draft on the IPH HREC form and tell the PM the OAUTHC-specific form has to come from the site.

`templates/irb-application.md` maps the questions the committee asks, in its order. The form is
**populated from the Gate-1 protocol**, never re-interviewed; where the two disagree, the protocol
is right.

**The DTA skip rule — apply it, then say which rule fired.** Write the participating sites down
first, and reuse the Gate-1 collaborator answer rather than re-asking. Then:

- **All sites are Nigerian federal hospitals** → **no DTA/MTA is required.** Skip the task and say
  so: *"all sites are Nigerian federal hospitals, so no DTA is needed."*
- **Anything else** (a non-Nigerian site, a non-federal institution, data leaving to a
  collaborator) → draft the DTA from the template, and name the site that triggered it.

Never skip silently, and never draft one silently.

## Gate 3 — "ethical approval received"

**The precondition, first.** List **every** participating site and confirm, site by site, that you
have its ICF and its ethical clearance. A site missing either is not ready — name it, say what's
missing, and carry on with the rest.

| Task | Official template |
|---|---|
| CPL — one per site | `ARGO Consenting Professional List (CPL) Template.docx` |
| ECL — one document covering all sites | `ARGO Eligibility Checklist (ECL) Template.docx` |
| Study guide / study SOP | `ARGO Study SOP Template.docx` |
| Lab manual — specimen studies only | `ARGO Biospecimen Laboratory Manual Template.docx` |
| Lab requisition — specimen studies only | `ARGO Lab Requisition Template.docx` |
| Study QA plan | `ARGO QA Plan.docx` (outside `ARGO Templates/`) |
| **REDCap build request** | the SIR survey — the hand-off, see below |
| Monthly study meeting agenda | `ARGO Study Meeting Template.docx` |
| Accrual table for the joint call, if needed | `ARGO Joint Call Study Accrual Template.docx` |
| SIV scheduling | zoom link + stakeholder email — drafted |
| SIV slides | `ARGO SIV Template.pptx` — see below |
| SIV attendance | `Protocol Training Attendance Log Template.docx` |
| New Study / New Site checklist | `New Study_New Site Checklist_NIH Funded Final.docx` or `New Study_New Site Checklist_non-NIH Funded Final.docx` — pick by funding |
| Activation memo | `ARGO Activation Memo Template.docx` — see below |
| Activation email to all stakeholders | drafted |

The CPL needs the consenting professionals per site; the ECL needs the eligibility criteria; the
lab documents exist **only if the study collects specimens** (fact 4).

### The Study Start-Up SOP

There are two, in `ARGO Standard Operating Procedures (SOPs)/Study Start-Up/` — one for
**NIH-funded** studies, one for **non-NIH**. Ask how the study is funded (fact 3), read the
matching SOP and follow it; the same answer picks the checklist variant.

### Say these out loud, at the task they belong to

- **Activation memo** — its whole body is a **floating text box over the letterhead image**.
  Editable in Word, but invisible to docx tooling, so a fill attempt reports success and changes
  nothing. Draft the memo's *content* (date, PI, study title, site names, signatory) for the PM to
  type into the official memo, and say that's what you did. Its standing instruction is worth
  repeating: registration paperwork (signed ICF, eligibility checklist, source documentation) goes
  into OAU REDCap **within 24 hours** of the consent being signed.
- **SIV slides** — the deck is PowerPoint, which the docx skill doesn't cover. With a **pptx
  skill**, fill the official template; without one, say so and draft the slide content as text,
  slide by slide, for the PM to paste. The attendance log is a `.docx`, filled normally.

### Where the pipeline ends: the REDCap build request

**The PM submits the SIR survey** — the Study Initiation Request in REDCap — **with every document
above attached** for the study's File Repository. That is the hand-off: [[build-study]]
(argo-database-manager) builds the database from the questionnaire.

Don't submit it for them and don't ask for a key to do it. Make it one sitting: the package
complete, every file named with the study moniker, and a short list of which document goes in
which SIR upload field.

## Rules for every task

1. **Fill, don't fabricate.** Anything genuinely unknown becomes a visible `**[TODO: …]**` —
   **never** invent regulatory facts, IRB numbers, ethics statements, approval dates, PI details
   or site contacts.
2. **Real documents.** Use the **docx** skill for the `.docx`; markdown skeletons are a working
   form, never the deliverable. (Exceptions: the SIV deck above, and the questionnaire changelog,
   which stays markdown.)
3. **One folder per study, moniker naming.** Everything lands in
   `project-manager/new-studies/<study>/`, each file named with the study moniker
   (`<MONIKER>_ICF_draft.docx`, `<MONIKER>_CPL_<site>.docx`) — the same names the SIR and the File
   Repository use, so a draft is one drag, not a rename.
4. **Everything is a draft for the PM.** Say so — especially for the protocol, the consent and the
   IRB form.
5. **Keep messages to the PM short and plain.** Name the document you made, where it is, and the
   open `[TODO]`s or questions — not a recap of what the template says.

## The official Word templates

The real templates (official formatting, letterhead) live in the **Study Tracker's File
Repository**, not in this skill: this repository is public and the templates carry internal
contact details. In order:

1. **Already in the workspace?**
   `find "<workspace>/project-manager/templates-official" -name "*.doc*" 2>/dev/null | head`
   Search only there, recursively (the fetch writes a nested tree) — never the whole home folder,
   where a copy may be stale. A `FileRepository_*/ARGO Templates/` folder the user downloaded by
   hand into the workspace also counts.
2. **Not there, and the Study Tracker key is configured?** Fetch once:
   `python3 fetch_templates.py --to <workspace>/project-manager/templates-official`
   (it brings the `ARGO Templates/` tree, the QA plan and the two Study Start-Up SOPs).
3. **Neither?** Use the markdown skeletons below, rendered via the docx skill — same content,
   approximate styling. **Tell the user which path you took.**

With a template in hand, it is the base document: fill its placeholders and keep its formatting.
The three that can't be filled that way — the questionnaire guide, the legacy `.doc` ICF and the
text-box activation memo — are handled at their own tasks above.

| Skeleton in `templates/` | Official file it approximates |
|---|---|
| `questionnaire-proforma.md` | *(the study's instrument, built **to** the rules in `ARGO Questionnaire Template.docx` — a design guide, so nothing to fill)* |
| `irb-application.md` | `ARGO IPH HREC Application Form Template.docx` — Gate 2's content map, not a protocol skeleton |
| `study-guide.md` | `ARGO Study SOP Template.docx` |
| `activation-memo.md` | `ARGO Activation Memo Template.docx` (content only) |
| `siv-outline.md` | `ARGO SIV Template.pptx` + `Protocol Training Attendance Log Template.docx` |
| `lab-requisition.md` | `ARGO Lab Requisition Template.docx` |
| `startup-checklist.md` | `New Study_New Site Checklist_NIH Funded Final.docx` / `New Study_New Site Checklist_non-NIH Funded Final.docx` |

Tasks with no skeleton (protocol, ICF, DTA, CPL, ECL, lab manual, QA plan, meeting agenda, accrual
table) are drafted from the fetched template. If it isn't available, say so, draft the content,
and mark it clearly as an approximation to reconcile against the official form.

Fetched templates stay in `project-manager/templates-official` in the user's workspace.
**Never commit or publish them.**

## After launch

Amendment submission and collecting each site's amendment approval aren't built here yet — say so
if asked, rather than improvising a procedure.

## See also

- [[study-launch-pipeline]] — where each template lives, the procedure's source, the teaching case
- [[protocol-fill-map]] — where each protocol section gets its answer
- [[build-study]] (argo-database-manager) — what happens after the PM submits the SIR
- [[dd-column-spec]], [[mdc-rules]] — keep the questionnaire buildable
