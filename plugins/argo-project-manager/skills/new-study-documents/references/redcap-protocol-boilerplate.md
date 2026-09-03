---
name: redcap-protocol-boilerplate
description: The standard ARGO database/data-management text a study protocol needs — REDCap PHI approval, SSL, OAUTHC as database administrator, permission auditing, nightly backups, de-identified exports, source documentation, QA cadence, paper records. Drawn from ARGO's own final protocols; fill the [TODO]s and have the PI confirm before submission.
---

# ARGO REDCap protocol boilerplate (data management & quality assurance)

**Where this text comes from, and what you must do with it.** This is the standard
database-and-data-management language that ARGO's own **final** protocols carry and that study
*proposals* almost never have — in the programme's teaching case it was the single largest
proposal→final addition. It is offered so a drafting session writes real, house-standard prose
instead of emitting `[TODO: name the data platform]`.

**It is a starting draft, not an approved boilerplate.** Every paragraph below must be
**confirmed by the PI** (and the data manager) before the protocol goes to stakeholders or the
IRB — the facts are institutional and they change: administrators, backup schedules and who
receives exports are all study- and site-specific. Anything a session cannot confirm stays a
visible `**[TODO: …]**` rather than becoming an asserted regulatory fact.

Paste these sections into the protocol's data-management chapter, specialise every `[TODO]`, and
say in your hand-off that the text came from this reference and needs the PI's sign-off.

---

## Data management

**Database platform.** Study data will be collected and managed using **REDCap (Research
Electronic Data Capture)**, a secure, web-based application hosted at **[TODO: hosting
institution — e.g. Obafemi Awolowo University Teaching Hospitals Complex (OAUTHC)]**. The
instance has been **approved for the storage of protected health information (PHI)** by
**[TODO: the approving body and, if there is one, the approval reference]**. All traffic between
the user's browser and the database is encrypted in transit using **SSL/TLS**.

**Database administration.** **[TODO: OAUTHC / the named institution]** acts as the **database
administrator** for this study. Study-specific database configuration — instruments, data
dictionary, user accounts and roles — is carried out by **[TODO: the ARGO database manager /
named role]** at the PI's request.

**Access control and permission auditing.** Access is granted by named individual account only;
accounts are never shared. Each user is assigned the **minimum role** required for their task
(data entry, monitoring, export), and rights to export identifiable data are restricted to
**[TODO: named roles]**. **User permissions are audited [TODO: how often — the programme's
default is at least biannually and at every change of study staff]**, and accounts are revoked
when a team member leaves the study.

**Backups and continuity.** The database is **backed up nightly** by **[TODO: the hosting
institution's IT service]**, with restoration tested per that service's own schedule.
**[TODO: state the retention period agreed with the institution.]**

**Analysis exports.** Data released for analysis are **de-identified** before they leave the
database: direct identifiers are removed and a study identification number is used in their
place. **De-identified exports are provided to the study biostatistician** **[TODO: name /
role]** at agreed intervals **[TODO: how often]**. Identifiable data are not exported except
where the protocol and the ethical approval explicitly permit it.

## Source documentation

**Two participant identifiers.** Every source document and every database record carries **two
participant identifiers** — the **study identification number** and **[TODO: the second
identifier used at this site — e.g. the hospital number]** — so that a record can always be
traced back to, and reconciled with, its source.

**What is filed in the database.** **Signed informed consent forms and completed study
questionnaires are scanned and uploaded into REDCap** against the participant's record.
**[TODO: name any other source document that is scanned in — e.g. pathology reports,
eligibility checklists.]**

**Paper records.** Paper source documents — signed consents, completed paper questionnaires and
any printed case notes — are stored **under lock and key** in **[TODO: the named room / cabinet
and the site responsible]**, accessible only to authorised study personnel. Paper records are
retained for **[TODO: retention period per institutional policy]**.

## Quality assurance

**PI record audits.** The Principal Investigator (or a delegate named in the study's QA plan)
audits study records **biannually** — **[TODO: confirm the cadence and the sample size / fraction
of records audited]** — checking database entries against source documents for completeness,
accuracy and consent documentation.

**Monthly study meetings.** The study team meets **monthly** to review accrual, data quality
queries, protocol deviations and outstanding audit findings. **[TODO: name who attends — PI,
research managers, RAs, data manager, biostatistician.]**

**Corrective action.** Findings from an audit or a monthly meeting that indicate a systematic
problem result in a written **corrective action plan** — what will change, who owns it, and by
when — tracked to closure at the following meeting. **[TODO: name where corrective action plans
are filed.]**

---

## Using this reference in a draft

- Keep the section headings; a protocol reviewer looks for them.
- Where a `[TODO]` cannot be answered from the proposal or the PM's answers, **leave it visible**.
  Never invent an approval body, a backup schedule, an administrator or a retention period.
- If the study collects **no** paper records, or exports nothing to a biostatistician, say so
  explicitly rather than deleting the paragraph — a protocol that is silent on a question reads
  as an oversight.
- The study's own **QA plan** (`ARGO QA Plan.docx`, Gate 3) elaborates the QA cadence above; the
  protocol states it, the QA plan operationalises it. Keep the two consistent.
