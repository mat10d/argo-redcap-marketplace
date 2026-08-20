# Concept Note — SYN: Synthetic Colorectal Cohort

> **SYNTHETIC TEST STUDY — not real.** Every name, site, number, and record in
> this study is computer-generated fixture data for testing the ARGO REDCap
> plugin suite. There are no real participants and no real institutions.

**Principal Investigator:** Dr. Ada Synthetic (fictional)
**Sites:** Alpha Teaching Hospital (`site_alpha`), Beta General Hospital (`site_beta`) — both fictional
**Design:** Prospective observational cohort (simulated)
**Sample size:** n = 200 synthetic records (120 Alpha, 80 Beta)

## Background

Colorectal cancer outcomes data are commonly fragmented across clinical and
pathology systems. This synthetic cohort imitates that shape: a three-form
REDCap project (demographics, clinical, follow-up) plus a separate pathology
sheet that overlaps on histology grade and margin status.

## Objectives

1. Exercise QA worklist generation: engineered applicable-but-blank cells,
   branching logic in every shape the parser supports, one deliberately
   unparseable condition, and MDC sentinel codes (-666/-777/-888/-999).
2. Exercise record linkage: engineered safe-fills, conflicts, no-ops, orphan
   pathology rows, and REDCap records absent from the pathology sheet.
3. Provide a stable, seeded dataset for automated feasibility tests.

## Data

Record ID field is `syn_id` (deliberately not `record_id`). All counts of
engineered missingness are stated exactly in `MANIFEST.json`; tests assert
those numbers rather than approximations.
