---
name: study-linkage
description: Link records across ARGO studies and external sources (REDCap ↔ REDCap, REDCap ↔ cBioPortal/Excel/TSV), then write the result back to REDCap safely with a diff-only payload. Builds a master linkage table, separates safe-fills from conflicts, and reports gaps/orphans/integrity issues. Use when the user wants to join, link, reconcile, match, cross-reference, or de-duplicate records between two or more studies/sources, or push linked values back into REDCap.
allowed-tools: Read, Bash, Write, Edit, Glob, Grep
---

# study-linkage

Reconcile fragmented records across studies and sources into one linked view, and (optionally)
write the links back to REDCap **without ever clobbering existing data**. This is data-management
work: it holds API tokens and touches live projects, so it runs under strict write-back guardrails.

Pairs with [[data-export]] (also in argo-data) for pulling/pushing, and with argo-core safety
references. The actual analysis of a linked cohort belongs to argo-analysis ([[run-analysis]]),
which works on the export this skill can produce — no token needed there.

## When to use

"Link the R01 and CRC cohorts," "match these pathology slides to the registry," "which cBioPortal
samples aren't in REDCap," "reconcile hospital numbers across sites," "push the linked MSI status
back into the pathology project." If they just want a plain export, use [[data-export]].

## Linkage scenarios this covers

Grounded in real ARGO linkage pipelines:
- **REDCap ↔ REDCap** — two cohort/clinical projects (e.g. R01 ↔ Nigeria CRC).
- **REDCap ↔ external** — a project against cBioPortal TSV, PathPresenter Excel, or an eCRF CSV.
- **Multi-way** — 3–4 sources reconciled into one master (e.g. R01 ↔ cBioPortal ↔ CRC).

## The contract (non-negotiable)

1. **Diff-only write-back.** Never overwrite a non-blank REDCap value implicitly. Computed values
   only ever FILL blanks. Disagreements are quarantined as conflicts for human decision. (See the
   payload pattern below — this is the core safety rule, consistent with [[redcap-api-gotchas]] §0:
   cohort patient-data writes are migration/one-off only, and confirmed before running.)
2. **Dry-run first.** Compute and emit the payload + reports; show counts; do not push until the
   user reviews and approves.
3. **Confirm the target project** before any write ([[token-confirmation]]) and read the record-ID
   field from metadata, don't assume `record_id` ([[record-id-safety]]).
4. **Config-driven, not hardcoded.** Sources, tokens, join keys, and field lists live in a config,
   not buried in code, so a linkage is reproducible and reviewable.
5. **Everything traceable.** Emit a master table + gap/conflict reports; every pushed value is
   attributable to a row in the master.

## Match keys & logic

- **Primary: exact join** on a declared key pair per source (e.g. R01 `colorectal_record_id` ↔
  CRC `research_number`; or `collaboration_identifier` for cBioPortal; or `record_id` + a
  categorical like `slide_type`/`batch`).
- **Fallback: fuzzy match** when exact fails — token-wise `SequenceMatcher` on names (a token pair
  at ratio ≥0.85 counts as a hit) plus a normalized hospital-number comparison (lowercase, strip
  non-alphanumerics, drop leading zeros; sentinels like `NYR`/`-999`/blank are neutral). Composite
  score = (name + hospital) / 2; surface the top-N candidates for a human to confirm. Never
  auto-accept a fuzzy match for write-back.
- **Ties/ambiguity:** rank by score, never silently pick; report duplicates and orphans.

## The diff-only payload pattern (core)

For each linked record and each target field, compare the **computed** value to the **current**
REDCap value (both normalized — trim, treat `nan`/blank as empty, drop numeric `.0` tails):

| current | computed | action |
|---|---|---|
| equal to computed | — | skip (no-op) |
| **blank** | non-blank | **safe-fill** → goes in the update payload |
| non-blank | blank | skip (nothing to add) |
| non-blank, **differs** | non-blank | **conflict** → quarantined, NOT pushed |

Emit three files:
- `*_update.csv` — safe-fills only; push with `overwriteBehavior=normal`.
- `*_conflicts.csv` — long format (`id, field, existing, computed`) for human triage.
- `*_overwrite.csv` — the conflict rows in wide form; push only after explicit human approval
  with `overwriteBehavior=overwrite`.

The reusable helper `diff_payload.py` implements exactly this (see below).

## Outputs

- `master_linkage.csv` — one row per linked entity with the IDs from each source + link flags
  (`*_linked`) + carried-over key fields.
- Gap/orphan reports — unmatched rows on each side (e.g. `r01_not_in_cbioportal.csv`,
  `cbioportal_unlinked.csv`, `*_missing_link.csv`).
- `*_integrity.csv` — ranked structural issues (duplicate/orphan join IDs) and low-score fuzzy
  mismatches, worst first.
- The three payload CSVs above when writing back.

## Workflow

1. **Define the linkage** (config): the sources (REDCap token/URL or local CSV/TSV/Excel path),
   the join key pair(s), primary vs fuzzy fallback, the target fields to carry/write.
2. **Pull each side** — via [[data-export]]/`redcap_client` for REDCap, or load the local file.
   Normalize keys (string, strip, drop `.0`); read metadata for labels/branching if needed.
3. **Match** — exact join on primary keys; for leftovers, optional fuzzy fallback → candidate list.
4. **Build the master** — reconcile into `master_linkage.csv`; set link flags.
5. **Report gaps & integrity** — emit unmatched/orphan/duplicate reports and the ranked integrity CSV.
6. **(If writing back) build the diff-only payload** with `diff_payload.py`; show the user the
   update/conflict/overwrite counts. **Dry-run.**
7. **Confirm & push** — only after approval: confirm target project title, push `*_update.csv`
   (normal). Handle `*_overwrite.csv` separately, only with explicit sign-off.

## Reusable helper: diff_payload.py

Generic implementation of the diff-only pattern — give it the computed and current states as CSVs
keyed by an ID field; it writes the three payload files:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/study-linkage/diff_payload.py \
    --computed computed.csv --current current.csv \
    --id-field record_id --out-dir outputs/ --prefix pathology_r01
```

## Reference implementations (adapt, don't reinvent)

The team's real linkage pipelines are the canonical patterns; read and adapt them per study:
- `Analysis/linkages/P20_linkages/aim1/pipeline.py` — clean 2-way (REDCap ↔ PathPresenter).
- `Analysis/linkages/R01_linkages/linkage.py` — multi-way resolution + gap taxonomy.
- `Analysis/linkages/R01_linkages/pipeline.py` (`build_*_payload`) — the diff-only payload in situ.
- `Analysis/linkages/R01_linkages/audit.py` — integrity checks + fuzzy name/hospital scoring.
- `Analysis/linkages/R01_linkages/redcap_client.py` — pull/push/metadata wrapper.

## See also

- [[data-export]] — pull/push the data this skill links
- [[run-analysis]] (argo-analysis) — analyze the linked cohort export (no token needed)
- [[token-confirmation]], [[record-id-safety]], [[redcap-api-gotchas]] — write-back safety
