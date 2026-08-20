---
name: link-data
description: Fulfil a linking request, or merge more than one database for analysis — match the same people or samples across studies and sources (REDCap to REDCap, or REDCap to a spreadsheet, cBioPortal export, CSV or TSV), build one linked table, and report the gaps, duplicates, orphans and conflicts. The matching side works entirely from downloaded files and needs no access key, which is the path when you are combining two studies for your own analysis. Writing the links back into REDCap is a separate, confirmed, fill-blanks-only step for the database manager. Use for join, link, match, reconcile, cross-reference or de-duplicate across two or more studies or sources.
allowed-tools: Read, Bash, Write, Edit, Glob, Grep
---

# link-data

Reconcile fragmented records across studies and sources into one linked view, and (optionally)
write the links back to REDCap **without ever clobbering existing data**.

**Two halves.** The read side (match, build the linked table, report gaps) works entirely from
files on disk and needs no access key — that's the path when you're merging two studies for
analysis. The write-back side pushes links into a live REDCap project and runs under the
guardrails below.

Pairs with [[export-data]] (also in argo-database-manager) for pulling the files, and with argo-core safety
references. The actual analysis of a linked cohort belongs to argo-data-analyst ([[run-analysis]]),
which works on the merged table this skill produces — no access key needed there.

## When to use

"Link the R01 and CRC cohorts," "match these pathology slides to the registry," "which cBioPortal
samples aren't in REDCap," "reconcile hospital numbers across sites," "push the linked MSI status
back into the pathology project." If they just want a plain export, use [[export-data]].

## Linkage scenarios this covers

Grounded in the team's real linkage work:
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
4. **Config-driven, not hardcoded.** Sources, access-key names, join keys, and field lists live in a config,
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

**Where they go, stated once.** Fulfilling a linking request as the database manager →
`database-manager/linkage/<name>/`. Merging studies for your own analysis →
`data-analyst/<study>/`. Everything below lands in whichever of those two applies.

- `master_linkage.csv` — one row per linked entity with the IDs from each source + link flags
  (`*_linked`) + carried-over key fields.
- Gap/orphan reports — unmatched rows on each side (e.g. `r01_not_in_cbioportal.csv`,
  `cbioportal_unlinked.csv`, `*_missing_link.csv`).
- `*_integrity.csv` — ranked structural issues (duplicate/orphan join IDs) and low-score fuzzy
  mismatches, worst first.
- The three payload CSVs above when writing back.

## Workflow

1. **Define the linkage** (config): the sources (REDCap access-key name + URL, or a local
   CSV/TSV/Excel path),
   the join key pair(s), primary vs fuzzy fallback, the target fields to carry/write.
2. **Pull each side** — via [[export-data]] for REDCap when a key exists, or use the CSV export and
   data dictionary downloaded from the REDCap website ([[getting-files-from-redcap]]) — the
   linkage never needs a key to run. Normalize keys (string, strip, drop `.0`); read the data
   dictionary for labels/branching if needed.
3. **Match** — exact join on primary keys; for leftovers, optional fuzzy fallback → candidate list.
4. **Build the master** — reconcile into `master_linkage.csv`; set link flags.
5. **Report gaps & integrity** — emit unmatched/orphan/duplicate reports and the ranked integrity CSV.
6. **(If writing back) build the diff-only payload** with `diff_payload.py`; show the user the
   update/conflict/overwrite counts. **Dry-run.**
7. **Confirm & push** — only after approval: confirm target project title, push `*_update.csv`
   (normal). Handle `*_overwrite.csv` separately, only with explicit sign-off.
8. **Close out the request** — when the linked table is delivered (or the write-back has landed),
   mark the request record complete in its tracker (tick `completed` in the REDCap UI). Skip this
   when you're merging studies for your own analysis — there's no request to close.

## Reusable helper: diff_payload.py

Generic implementation of the diff-only pattern — give it the computed and current states as CSVs
keyed by an ID field; it writes the three payload files:

```bash
D=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name diff_payload.py 2>/dev/null | head -1)
python3 "$D" --computed computed.csv --current current.csv \
    --id-field record_id --out-dir database-manager/linkage/<name>/ --prefix pathology_r01
```

## The original study-specific pipelines

The team's original linkage pipelines (P20, R01) live in the team's **private analysis repo**.
They are **not available in this session** — do not claim to have read them, and do not cite paths
into them as if they were on disk. Everything distilled from them that matters is already written
down above under "Match keys & logic" and "The diff-only payload pattern".

If a teammate does share one of those scripts with you, lift the *matching and scoring* logic
only. Do all REDCap I/O through `argo_redcap_client.py` from argo-core ([[redcap-api]],
[[access-tiers]]) — the old in-repo REDCap client is superseded and has no project confirmation,
no retry/backoff and no key masking. One HTTP path, no exceptions.

## See also

- [[export-data]] — pull/push the data this skill links
- [[run-analysis]] (argo-data-analyst) — analyse the linked cohort table (no access key needed)
- [[token-confirmation]], [[record-id-safety]], [[redcap-api-gotchas]] — write-back safety
