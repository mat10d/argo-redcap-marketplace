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

## First: ask which two things you're linking

A linkage is only as good as the two files that went into it, and the folder usually holds
several exports that all look plausible. **If the user hasn't attached or named both sides, ask
where they are — one question.** If you have looked and found likely candidates, don't assume:
name what you found and confirm in the same one question.

> I can see `crc_records_2026-08-12.csv` and `pathology_export.xlsx` in your folder — is that the
> pair you want linked, or is one of them somewhere else?

Never pick a file because it was the only one matching a guess, and never treat a synthetic or
test export as the study. Ask once, then get on with it.

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
| **no such record** | anything | **orphan** → gap report only, NEVER payload |

**An id that isn't in the REDCap side is not a blank record.** Treating it as one turns every
value on it into a "safe fill", and importing that file would CREATE records in the project
instead of filling gaps in it. Whether those people or samples belong in the study at all is a
decision for the user, made on the orphan report — never a side effect of a write-back.

Emit five files — the three-file payload, plus the two halves of the gap report:
- `*_update.csv` — safe-fills only, on records that already exist; push with
  `overwriteBehavior=normal`.
- `*_conflicts.csv` — long format (`id, field, existing, computed`) for human triage.
- `*_overwrite.csv` — the conflict rows in wide form; push only after explicit human approval
  with `overwriteBehavior=overwrite`.
- `*_orphans.csv` — ids found only on the computed side, with their values. A report, not a
  payload.
- `*_missing_link.csv` — ids found only on the current/REDCap side: the records the linkage
  found nothing for.

The reusable helper `diff_payload.py` implements exactly this (see below). Those file names are
the write-back ones; on an analysis merge (`--for-analysis`) the same two files are called
`*_fills.csv` and `*_disagreements.csv`, because there is nothing to update or overwrite.

## Outputs

**Where they go, stated once.** Fulfilling a linking request as the database manager →
`database-manager/linkage/<name>/`. Merging studies for your own analysis →
`data-analyst/<study>/`. Everything below lands in whichever of those two applies.

- `master_linkage.csv` — one row per linked entity with the IDs from each source + link flags
  (`<left>_linked` / `<right>_linked`) + a `link_class` + every field from both sides. Written by
  `build_master_linkage.py` (below), not by hand.
- **Gap/orphan reports — unmatched rows on each side.** `diff_payload.py` writes these two for
  every run, alongside the payload, and prints both counts:
  - `*_orphans.csv` — ids only on the computed/right side (no record to fill; never pushed).
  - `*_missing_link.csv` — ids only on the current/left side (nothing was computed for them).

  A multi-source linkage adds its own per-source versions of the same idea (e.g.
  `r01_not_in_cbioportal.csv`, `cbioportal_unlinked.csv`).
- `*_integrity.csv` — ranked structural issues (duplicate/orphan join IDs, sites that disagree
  between sources) worst first, each with a count and a sentence on what it means for the
  analysis. Also written by `build_master_linkage.py`.
- The two comparison CSVs, named for what the run is for:
  - writing back — `*_update.csv` (safe fills) and `*_overwrite.csv` (the conflict rows);
  - merging for analysis (`--for-analysis`) — `*_fills.csv` and `*_disagreements.csv`.
  `*_conflicts.csv` (long format, for triage) is written either way.

Always show the user both gap counts, not just the fill count — "13 fills, 24 conflicts, 15
records only in the new file, 155 with nothing to link to" is the honest summary of a linkage.

## Workflow

1. **Define the linkage** (config): the sources (REDCap access-key name + URL, or a local
   CSV/TSV/Excel path),
   the join key pair(s), primary vs fuzzy fallback, the target fields to carry/write.
2. **Pull each side** — via [[export-data]] for REDCap when a key exists, or use the CSV export and
   data dictionary downloaded from the REDCap website ([[getting-files-from-redcap]]) — the
   linkage never needs a key to run. Normalize keys (string, strip, drop `.0`); read the data
   dictionary for labels/branching if needed.
3. **Match** — run `diff_payload.py` (add `--for-analysis` when there is no write-back in
   prospect); it does the exact join on the id and classifies every shared cell.
4. **Build the master** — run `build_master_linkage.py` on the same two files plus step 3's
   output. It writes both of this skill's promised deliverables in one go: `master_linkage.csv`
   (link flags, `link_class`, both sources' columns) and the ranked `*_integrity.csv`.
5. **Report gaps & integrity** — read the integrity report back, worst first, and give both gap
   counts (see "Always show the user both gap counts", above).
6. **(If writing back) re-run `diff_payload.py` without `--for-analysis`**, so the two files
   carry the write-back names and the run prints the push instructions. Show the user all five
   counts — fills, conflicts, no-ops, orphans, and records with nothing to link to. **Dry-run.**
   If there are orphans, say what they are before anything else: those ids have no record in the
   project, and nothing will be written for them unless the user decides the records should be
   created (a separate, deliberate step).
7. **Confirm & push** — only after approval: confirm target project title, push `*_update.csv`
   (normal). Handle `*_overwrite.csv` separately, only with explicit sign-off.
8. **Close out the request** — when the linked table is delivered (or the write-back has landed),
   mark the request record complete in its tracker (tick `completed` in the REDCap UI). Skip this
   when you're merging studies for your own analysis — there's no request to close.

## Reusable helper: diff_payload.py

Generic implementation of the diff-only pattern — give it the computed and current states as CSVs
keyed by an ID field; it writes the three payload files and the two gap reports, and prints the
counts for all five:

```bash
D=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name diff_payload.py 2>/dev/null | head -1)
python3 "$D" --computed computed.csv --current current.csv \
    --id-field record_id --out-dir database-manager/linkage/<name>/ --prefix pathology_r01
```

Without `--fields` it compares every column the two files share, **except** the ID, REDCap's
structural columns (`redcap_data_access_group`, `redcap_event_name`, `redcap_repeat_instrument`,
`redcap_repeat_instance`) and the per-form `*_complete` columns. Those describe how REDCap stores
a record, not what the record says — comparing the data access group proposes moving records
between sites. The run prints which columns it skipped; pass `--fields` to compare an exact list
(including one of those, if you really mean to).

## Merging two sources for analysis — the read side, end to end

This is the common case: two studies, one merged table, nothing written anywhere. Say so with
`--for-analysis` and the whole run speaks the right language — the two files come out as
`*_fills.csv` (one source has a value, the other doesn't) and `*_disagreements.csv` (they
contradict each other), and nothing is printed about pushing or `overwriteBehavior`, because
nobody is pushing anything. The gap reports are written exactly as before.

```bash
L=$(dirname "$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name diff_payload.py 2>/dev/null | head -1)")

# 1. compare the two sources
python3 "$L/diff_payload.py" --for-analysis \
    --current cohort_records.csv --computed pathology.csv \
    --id-field syn_id --out-dir data-analyst/<study>/ --prefix pathology

# 2. build the merged table + the integrity report
python3 "$L/build_master_linkage.py" \
    --left cohort_records.csv --left-name cohort \
    --right pathology.csv     --right-name pathology \
    --diff-dir data-analyst/<study>/ --diff-prefix pathology \
    --id-field syn_id --out data-analyst/<study>/master_linkage.csv
```

`--left` is whatever you gave `--current`, `--right` whatever you gave `--computed`; the script
checks that against the diff's own reports and stops if they look swapped. `--left-name` and
`--right-name` name the two sources in the output columns (`cohort_linked`,
`pathology_linked`), so the table reads as itself rather than as "left" and "right".

`build_master_linkage.py` reads the diff engine's verdicts rather than comparing the two files a
second time — the fill/conflict/orphan rule is a safety rule and lives in exactly one place. It
writes:

- **`master_linkage.csv`** — one row per id across both sources, with `<left>_linked` /
  `<right>_linked` flags, a `link_class` (`matched_agree`, `matched_fill`, `matched_conflict`,
  `<left>_only`, `<right>_only`), a `conflict_fields` list, and every column from both sides.
  Where a column name exists on both sides, **both values are kept** — the right-hand one is
  suffixed `_<right-name>`. Nothing is reconciled automatically: a disagreement is for a human.
- **`<prefix>_integrity.csv`** — the structural problems, ranked worst first, each with a count
  and a sentence saying what it means. An issue with a count of zero drops to `info`, so the
  top of the file is always this run's real problems.

It accepts either naming for the comparison files, so it works after a `--for-analysis` run or
a write-back one.

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
