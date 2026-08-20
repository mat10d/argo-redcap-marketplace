<!-- ARGO Questionnaire / Proforma — skeleton. THE LINCHPIN: build-study's Path A pulls the data
dictionary from this, so design it to map cleanly to a REDCap DD. Fill [PLACEHOLDERS]; render to
.docx via the docx skill. -->

# [STUDY_NAME] — Data Collection Proforma

> Design principles (keep the instrument analysis-driven and buildable):
> - One question at a time; no double-barreled questions.
> - Prefer **coded categorical** options over free text (e.g. Mild / Moderate / Severe).
> - Consistent rating scales throughout; specify units.
> - Group related questions; move general → specific; use clear section headers.
> - Validation-friendly (numeric ranges, dates as dd/mm/yyyy), required where appropriate.
> - Every field should map to a REDCap field type (radio / dropdown / checkbox / text / date).
> - Reserve missing-data codes per ARGO SOP: -666 doesn't know, -777 refused, -888 missing in
>   case notes, -999 other (see [[mdc-rules]]).

**Record ID:** [study]_id (auto) · **Hospital Number:** required, identifier (PII).

## Section 1: Demographics
- Age at diagnosis (years): [____]  (numeric)
- Sex: ☐ Male ☐ Female
- Site / hospital: [dropdown of sites]
- [add fields…]

## Section 2: History of Present Illness
- [coded fields…]

## Section 3: Diagnosis & Staging
- Date of diagnosis (dd/mm/yyyy): [____]
- Stage: ☐ I ☐ II ☐ III ☐ IV
- Tumor location: [coded options…]
- [add fields…]

## Section 4: Treatment
- Treatment received (select all): ☐ Surgery ☐ Chemotherapy ☐ Radiotherapy ☐ … [checkbox]
- [branching follow-ups: "if Surgery → procedure type"…]

## Section 5: Follow-up & Outcomes
- Follow-up interval: [____]
- Vital status / recurrence / dates: [coded + date fields]

**[TODO: replace example sections with the study's actual variables — derive from the supporting
documents the PM provided where possible; confirm coding schemes and units with the PI.]**
