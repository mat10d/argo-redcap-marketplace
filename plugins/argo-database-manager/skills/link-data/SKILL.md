---
name: link-data
description: Fulfil a linking request, or merge more than one database for analysis — work out which column identifies the same person in two studies, join them, and produce the hard-link file that records each participant's number from the other study. Also builds one merged table for analysis and reports the gaps, duplicates and conflicts. Works entirely from downloaded files and needs no access key. Writing values back into REDCap is a separate, confirmed, fill-blanks-only step for the database manager. Use for link, join, match, reconcile, cross-reference or de-duplicate across two or more studies or sources (REDCap to REDCap, or REDCap to a spreadsheet, cBioPortal export, CSV or TSV).
allowed-tools: Read, Bash, Write, Edit, Glob, Grep
---

# link-data

Two studies hold the same people under different numbers. This skill works out which column
says so, joins on it, and produces the file that makes the link permanent.

**What a linking request is actually asking for.** Somebody enrolled in the CRC cohort is also
in the R01 study, and today nothing in either project says so. The deliverable is a two-column
file — each R01 record's own ID next to that participant's CRC number — that the user uploads
into the R01 project. After that upload the link is *in* REDCap, and every later export carries
it. That file is the **hard link**, and it is what a linking request is finished by.

**The other job this skill does** is the analyst's: two studies, one merged table, nothing
written anywhere. Same first step (establish the link), then a different second step (merge and
compare). Both run entirely from files downloaded from the REDCap website — no access key
anywhere on the read side.

Pairs with [[export-data]] (also in argo-database-manager) for pulling the files. The actual
analysis of a linked cohort belongs to argo-data-analyst ([[run-analysis]]), which works on the
merged table this skill produces.

## The three tools, and which job each one has

| Tool | Question it answers | Produces |
|---|---|---|
| `link_studies.py` | **Which people are the same people?** | the hard link, the two missing-link reports, the name-review table |
| `diff_payload.py` | Once linked, **where do the two studies disagree, field by field?** | fills, conflicts, and the write-back payload |
| `build_master_linkage.py` | **What does one table with both studies in it look like?** | `master_linkage.csv` + the integrity report |

Run them in that order. `link_studies.py` comes first every time: the other two take the link as
given, and neither of them will tell you the link was wrong.

## First: ask which two files, and which one is the parent

A linkage is only as good as the two files that went into it, and the folder usually holds
several exports that all look plausible. **If the user hasn't attached or named both sides, ask
where they are — one question.** If you have looked and found likely candidates, don't assume:
name what you found and confirm in the same one question.

> I can see `crc_records_2026-08-12.csv` and `r01_export.xlsx` in your folder — is that the pair
> you want linked, and is the R01 the study that should end up holding the CRC number?

**Parent and child.** The *parent* is the study whose number gets carried (the cohort, the
registry, the older study). The *child* is the study that will hold the link — the hard link is
uploaded into the child. Say which is which in plain words and let the user correct you; getting
it backwards produces a file that would be uploaded to the wrong project.

Never pick a file because it was the only one matching a guess, and never treat a synthetic or
test export as the study.

**Where the files come from.** Either side can be a CSV downloaded from the REDCap website
([[getting-files-from-redcap]]) or pulled with a key via [[export-data]]. The whole read side
works the same either way — a linkage never needs a key.

## Step 1 — derive the join key, out loud

This is the part that takes judgment, and it is the part to think about in the open. Two studies
join on something that identifies the same person in both. In this team's data that is almost
always one of:

- a **hospital number** both studies recorded, or
- **one study's record number carried inside the other** — the CRC export holding an `r01_number`
  column, or the R01 export holding a `crc_redcap_number` — which is the shape a sub-study
  usually has.

`link_studies.py --suggest` surveys both files and prints the candidates with the numbers behind
them: how many rows each one matches, whether it has one row per value on each side, and whether
it looks like a hospital number or like the other study's number. It compares columns by their
VALUES, so a column that carries the other study's numbers under a different heading is found
too. It writes nothing.

```bash
L="$(dirname "$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name link_studies.py 2>/dev/null | head -1)")"

python3 "$L/link_studies.py" --suggest \
    --parent crc_records.csv --parent-name crc \
    --child  r01_export.csv  --child-name  r01
```

`$L` is the folder this skill's scripts are in. Shell variables don't survive between commands,
so keep that first line in front of every block below, or set it once in the same command.

Then **reason about it in front of the user and ask ONE question.** Not a menu — a proposal with
the evidence and a yes/no:

> Both files carry a hospital number, and the R01 export also has a `crc_redcap_number` column
> holding CRC-style numbers. The `crc_redcap_number` matches 312 of the 340 R01 records against
> the CRC file; the hospital number matches 289. The ported CRC number is the more likely unique
> ID, so I'd join on that and check the names afterwards to be sure it matched the right people.
> Shall I?

Nothing is built until they answer. If they name a different column, use it.

## Step 2 — the run

```bash
python3 "$L/link_studies.py" \
    --parent crc_records.csv --parent-name crc \
    --child  r01_export.csv  --child-name  r01 \
    --parent-key record_id --child-key crc_redcap_number \
    --child-id record_id --link-field crc_redcap_number \
    --out-dir database-manager/linkage/r01-crc/
```

Use `--key` instead of the two `--*-key` flags when both files use the same heading. `--child-id`
is the child study's own record-ID column (it defaults to the first column of the child file, the
way REDCap exports it). `--link-field` is the heading the parent's number gets in the hard-link
file — **the name of the field in the child project that will hold it**, because that file is
uploaded into the child project and REDCap matches on column headings.

Four files come out.

### `<child>_hard_link.csv` — the deliverable

Exactly two columns: the child's record ID and the parent's number. One row per person the link
was established for. Nothing else — every extra column in a REDCap import is a chance to
overwrite something.

Hand it over with the instruction, not just the file:

> `r01_hard_link.csv` has 312 rows. In the R01 project, go to Data Import Tool, upload this file
> and choose to review the changes before saving — it only fills `crc_redcap_number`, and it
> leaves every other field alone. After that the link is in REDCap for good.

Uploading is the user's own act, on the website. This skill never writes it for them.

### `<child>_missing_link.csv` and `<parent>_missing_link.csv`

The two halves of what the link could NOT do, one file per side, each named for the side whose
records are in it: `r01_missing_link.csv` is R01 records with no CRC match; `crc_missing_link.csv`
is the reverse. Both carry the patient's **name and surname** (and the hospital number when there
is one), because the way these get resolved is somebody reading down the list and recognising
people.

Say both counts out loud, always. "312 linked" on its own is not the truth about a linkage;
"312 linked, 28 R01 records with no CRC match, 604 CRC records with no R01 record" is.

### `<child>_name_review.csv`

The matched pairs whose names disagree between the two studies, worst first. This is how you find
out the key matched the wrong people. A near-miss (`Lawla` / `Lawal`) is a transcription slip and
the link is fine; two unrelated names on the same number mean the ID was reused or mistyped, and
that pair needs a human before the hard link is uploaded. If the run reports discrepancies, show
this table before handing over the hard link.

If only one of the two files carries names, the run says so rather than skipping quietly.

### When the run refuses

- **A repeated key value.** A link has to point at one record per person, so a repeated join
  value stops the run rather than picking one. Usually the export has one row per visit or per
  sample and needs to be exported one row per person.
- **Nothing matched at all.** An empty hard-link file is worse than none. Go back to `--suggest`.

## Step 3 — once linked: comparing fields, and the merged table

The link is established; these two are what you do with it.

### `diff_payload.py` — where the two studies disagree, field by field

Give it the two sides keyed by the linking ID and it classifies every shared cell. It enforces
the core ARGO guardrail: a computed value may only ever **fill a blank**, never replace a value.

| current | computed | action |
|---|---|---|
| equal to computed | — | skip (no-op) |
| **blank** | non-blank | **safe-fill** → goes in the update payload |
| non-blank | blank | skip (nothing to add) |
| non-blank, **differs** | non-blank | **conflict** → quarantined, NOT pushed |
| **no such record** | anything | report only, NEVER payload |

**An id that isn't on the current side is not a blank record.** Treating it as one turns every
value on it into a "safe fill", and importing that file would CREATE records in the project
instead of filling gaps in it. Whether those people belong in the study at all is a decision for
the user, made on `<prefix>_no_record_to_fill.csv` — never a side effect of a write-back.

It writes five files:

- `<prefix>_update.csv` — safe-fills only, on records that already exist; push with
  `overwriteBehavior=normal`.
- `<prefix>_conflicts.csv` — long format (`id, field, existing, computed`) for human triage.
- `<prefix>_overwrite.csv` — the conflict rows in wide form; push only after explicit human
  approval, with `overwriteBehavior=overwrite`.
- `<prefix>_no_record_to_fill.csv` — rows on the computed side with no record to fill. A report.
- `<prefix>_missing_link.csv` — ids only on the current side: nothing was computed for them.

```bash
python3 "$L/diff_payload.py" --computed computed.csv --current current.csv \
    --id-field record_id --out-dir database-manager/linkage/r01-crc/ --prefix pathology
```

Without `--fields` it compares every column the two files share, **except** the ID, REDCap's
structural columns (`redcap_data_access_group`, `redcap_event_name`, `redcap_repeat_instrument`,
`redcap_repeat_instance`) and the per-form `*_complete` columns. Those describe how REDCap stores
a record, not what the record says — comparing the data access group proposes moving records
between sites. The run prints which columns it skipped; pass `--fields` to compare an exact list.

**Merging for analysis, with no write-back in prospect? Add `--for-analysis`.** The same
comparison runs, but the two files come out as `<prefix>_fills.csv` (one source has a value, the
other doesn't) and `<prefix>_disagreements.csv` (they contradict each other), and nothing is
printed about pushing — because nobody is pushing anything.

### `build_master_linkage.py` — one table with both studies in it

```bash
python3 "$L/build_master_linkage.py" \
    --left  cohort_records.csv --left-name  cohort \
    --right pathology.csv      --right-name pathology \
    --diff-dir data-analyst/<study>/ --diff-prefix pathology \
    --id-field syn_id --out data-analyst/<study>/master_linkage.csv
```

`--left` is whatever you gave `--current`, `--right` whatever you gave `--computed`; the script
checks that against the diff's own reports and stops if they look swapped. `--left-name` and
`--right-name` name the two sources in the output columns (`cohort_linked`, `pathology_linked`),
so the table reads as itself rather than as "left" and "right".

It reads the diff engine's verdicts rather than comparing the two files a second time — the
fill/conflict rule is a safety rule and lives in exactly one place. It writes:

- **`master_linkage.csv`** — one row per id across both sources, with `<left>_linked` /
  `<right>_linked` flags, a `link_class` (`matched_agree`, `matched_fill`, `matched_conflict`,
  `<left>_only`, `<right>_only`), a `conflict_fields` list, and every column from both sides.
  Where a column name exists on both sides, **both values are kept** — the right-hand one is
  suffixed `_<right-name>`. Nothing is reconciled automatically: a disagreement is for a human.
- **`<prefix>_integrity.csv`** — the structural problems, ranked worst first, each with a count
  and a sentence saying what it means. An issue with a count of zero drops to `info`, so the top
  of the file is always this run's real problems.

It accepts either naming for the comparison files, so it works after a `--for-analysis` run or a
write-back one.

## Where the files go, stated once

Fulfilling a linking request as the database manager → `database-manager/linkage/<name>/`.
Merging studies for your own analysis → `data-analyst/<study>/`. Everything above lands in
whichever of those two applies.

## Writing back to REDCap (database manager only)

The read side never needs an access key. Pushing values back does, and it runs under these rules:

1. **Diff-only.** Never overwrite a non-blank REDCap value implicitly. Computed values only ever
   fill blanks; disagreements are quarantined for human decision. (Consistent with
   [[redcap-api-gotchas]] §0: cohort patient-data writes are migration/one-off only, and
   confirmed before running.)
2. **Dry-run first.** Emit the payload and the reports, show the counts, push nothing until the
   user reviews and approves.
3. **Confirm the target project** before any write ([[token-confirmation]]) and read the
   record-ID field from metadata, don't assume `record_id` ([[record-id-safety]]).
4. **Everything traceable.** Every pushed value is attributable to a row in the master table.

Then: confirm the project title, push `<prefix>_update.csv` with `overwriteBehavior=normal`, and
handle `<prefix>_overwrite.csv` separately, only with explicit sign-off.

The hard link itself is not this path — it is a two-column file the user uploads on the website,
which is why a linking request needs no key from end to end.

## Matching when there is no clean key

- **Primary: the exact join** on the confirmed key. This is what `link_studies.py` does, and it
  is what almost every real linkage needs.
- **Fallback: fuzzy matching**, when no column joins enough rows — token-wise `SequenceMatcher`
  on names (a token pair at ratio ≥0.85 counts as a hit) plus a normalized hospital-number
  comparison (lowercase, strip non-alphanumerics, drop leading zeros; sentinels like `NYR`/`-999`
  /blank are neutral). Composite score = (name + hospital) / 2; surface the top candidates for a
  human to confirm one at a time. No script implements this — it is work you do in the session,
  one candidate at a time. **Never auto-accept a fuzzy match into a hard link:** the whole point
  of a hard link is that it is permanent.
- **Ties and ambiguity:** rank by score, never silently pick.

## Closing out a linking request

When the hard link is delivered (or the write-back has landed), mark the request record complete
in its tracker — tick `completed` in the REDCap UI. Skip this when you're merging studies for
your own analysis: there's no request to close.

## The original study-specific pipelines

The team's original linkage pipelines (P20, R01) live in the team's **private analysis repo**.
They are **not available in this session** — do not claim to have read them, and do not cite paths
into them as if they were on disk. Everything distilled from them that matters is written down
above.

If a teammate does share one of those scripts with you, lift the *matching and scoring* logic
only. Do all REDCap I/O through `argo_redcap_client.py` from argo-core ([[redcap-api]],
[[access-tiers]]) — the old in-repo REDCap client is superseded and has no project confirmation,
no retry/backoff and no key masking. One HTTP path, no exceptions.

## See also

- [[export-data]] — pull the files this skill links
- [[run-analysis]] (argo-data-analyst) — analyse the linked cohort table (no access key needed)
- [[token-confirmation]], [[record-id-safety]], [[redcap-api-gotchas]] — write-back safety
