---
name: link-data
description: Fulfil a linking request, or merge more than one database for analysis — work out which column identifies the same person in two studies, join them, and produce the hard-link file that records each participant's number from the other study. Also builds one merged table for analysis and reports the gaps, duplicates and conflicts. Works entirely from downloaded files and needs no access key. Writing values back into REDCap is a separate, confirmed, fill-blanks-only step for the database manager. Use for link, join, match, reconcile, cross-reference or de-duplicate across two or more studies or sources (REDCap to REDCap, or REDCap to a spreadsheet saved as CSV, cBioPortal export, CSV or TSV).
allowed-tools: Read, Bash, Write, Edit, Glob, Grep
---

# link-data

Two studies hold the same people under different numbers. This skill works out which column
says so, joins on it, and produces the file that makes the link permanent.

**A linking request** asks for that permanence. Somebody in the CRC cohort is also in the R01
study, and nothing in either project says so. The deliverable is a two-column file — each R01
record's ID next to that participant's CRC number — that the user uploads into the R01 project.
After that the link is *in* REDCap and every later export carries it. That file is the **hard
link**; it is what finishes a linking request.

**The analyst's job** is the other use: two studies, one merged table, nothing written anywhere.
Same first step (establish the link), different second step (merge and compare). Both run from
downloaded files — no access key anywhere on the read side.

Talk to the user in short sentences and plain words. Pull the files with [[export-data]];
analyse the linked cohort in [[run-analysis]].

## The three tools, and which job each one has

| Tool | Question it answers | Produces |
|---|---|---|
| `link_studies.py` | **Which people are the same people?** | the hard link, the two missing-link reports, the name-review table |
| `diff_payload.py` | Once linked, **where do the two studies disagree, field by field?** | fills, conflicts, the gap reports |
| `build_master_linkage.py` | **What does one table with both studies in it look like?** | `master_linkage.csv` + the integrity report |

Run them in that order. `link_studies.py` comes first every time: the other two take the link as
given, and neither will tell you it was wrong.

```bash
L="$(dirname "$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name link_studies.py 2>/dev/null | head -1)")"
```

`$L` is this skill's folder. Shell variables don't survive between commands, so put that line in
front of every block below.

## First: which two files, and which is the parent

A linkage is only as good as its two files, and the folder usually holds several plausible
exports. **If the user hasn't named both sides, ask — one question.** If you found likely
candidates, name them and confirm in that same question:

> I can see `crc_records_2026-08-12.csv` and `r01_export.csv` — is that the pair, and is the R01
> the study that should end up holding the CRC number?

**Parent and child.** The *parent* is the study whose number gets carried (cohort, registry,
older study). The *child* holds the link — the hard link is uploaded into the child. Say which is
which in plain words; backwards means a file uploaded to the wrong project. Never treat a
synthetic or test export as the study.

Either side can be a website download ([[getting-files-from-redcap]]) or an [[export-data]] pull.
**Both must be CSV or TSV** (a cBioPortal export reads as-is); an Excel workbook has to be saved
as CSV first — say so up front.

## Step 1 — derive the join key, out loud

This is the judgement step; think in the open. In this team's data the join is almost always:

- a **hospital number** both studies recorded, or
- **one study's record number carried inside the other** — an `r01_number` column in the CRC
  export, a `crc_redcap_number` in the R01 export — the usual shape of a sub-study.

`--suggest` surveys both files and prints the candidates with their numbers: rows matched, one row
per value on each side or not, hospital-number-like or record-number-like. It compares VALUES, so
a column carrying the other study's numbers under a different heading is found too. It writes
nothing.

```bash
python3 "$L/link_studies.py" --suggest \
    --parent crc_records.csv --parent-name crc \
    --child  r01_export.csv  --child-name  r01
```

Then **propose one key with the evidence and ask a yes/no** — not a menu:

> The R01 export's `crc_redcap_number` matches 312 of 340 R01 records; the hospital number
> matches 289. I'd join on `crc_redcap_number` and check names afterwards. Shall I?

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

`--key` replaces the two `--*-key` flags when both files use the same heading. `--child-id` is the
child's own record-ID column (default: its first column, as REDCap exports it). `--link-field` is
the heading the parent's number gets in the hard-link file — **the name of the field in the child
project that will hold it**, because REDCap matches an upload on column headings.

Four files come out.

### `<child>_hard_link.csv` — the deliverable

Exactly two columns: the child's record ID and the parent's number, one row per linked person.
Nothing else — every extra column in an import is a chance to overwrite something. Hand it over
with the instruction:

> `r01_hard_link.csv` has 312 rows. In the R01 project: Data Import Tool → upload it → review
> the changes before saving. It only fills `crc_redcap_number`. After that the link is in REDCap.

Uploading is the user's own act on the website; this skill never writes it.

### `<child>_missing_link.csv` and `<parent>_missing_link.csv`

What the link could NOT do, one file per side, named for the side whose records are in it:
`r01_missing_link.csv` is R01 records with no CRC match, `crc_missing_link.csv` the reverse. Both
carry **name and surname** (and hospital number when there is one), because these get resolved
by someone reading the list and recognising people. A record with a blank key lands in its own
side's file too — a record missing from every report looks like one that was handled.

Say both counts, always: "312 linked, 28 R01 records with no CRC match, 604 CRC records with no
R01 record" — "312 linked" alone isn't the truth about a linkage.

### `<child>_name_review.csv`

Matched pairs whose names disagree, worst first — how you find out the key matched the wrong
people. A near-miss (`Lawla` / `Lawal`) is a transcription slip; two unrelated names on one number
mean a reused or mistyped ID, and that pair needs a human before the hard link goes up. If the run
reports discrepancies, show this table before handing over the hard link. Missing names on one
side or both are reported, not skipped. Unusual name headings: `--parent-names "first_name,surname"`
/ `--child-names …`.

### When the run refuses

- **A repeated key value.** A link must point at one record per person. Usually the export has one
  row per visit or sample; export one row per person.
- **Nothing matched.** An empty hard link is worse than none. Back to `--suggest`.

## Step 3 — once linked: comparing fields, and the merged table

### `diff_payload.py` — where the two studies disagree

Give it both sides keyed by the linking ID; it classifies every shared cell under ARGO's core
guardrail — a computed value may only **fill a blank**, never replace a value:

| current | computed | action |
|---|---|---|
| equal | — | skip |
| **blank** | non-blank | **fill** |
| non-blank | blank | skip |
| non-blank, **differs** | non-blank | **conflict** → for a human |
| **no such record** | anything | report only |

**An id missing from the current side is not a blank record.** Treating it as one would make every
value a "fill", and importing that would CREATE records. Whether those people belong in the study
is the user's decision, made on `<prefix>_no_record_to_fill.csv`.

It refuses an id that appears twice on either side (the last row would silently win, and a field
filled on an earlier row would read as blank — a "fill" that overwrites). Ids are matched loosely
(`1` = `1.0`) but written back exactly as the current file spells them, so `007` stays `007`.

```bash
python3 "$L/diff_payload.py" --computed computed.csv --current current.csv \
    --id-field record_id --out-dir database-manager/linkage/r01-crc/ --prefix pathology
```

Use a `--prefix` that isn't one of the study names you gave `link_studies.py`: both write
`<name>_missing_link.csv`, and a shared name overwrites the other's file.

Files: `<prefix>_update.csv` (fills, on existing records only), `<prefix>_conflicts.csv` (long:
`id, field, existing, computed`), `<prefix>_overwrite.csv` (the conflicts, wide),
`<prefix>_no_record_to_fill.csv` (computed rows with no record), `<prefix>_missing_link.csv`
(current ids nothing was computed for).

Without `--fields` it compares every shared column **except** the ID, REDCap's structural columns
(`redcap_data_access_group`, `redcap_event_name`, `redcap_repeat_instrument`,
`redcap_repeat_instance`) and `*_complete` — they describe storage, not content, and comparing the
data access group proposes moving people between sites. Pass `--fields` for an exact list.

**Merging for analysis? Add `--for-analysis`.** Same comparison; the two files become
`<prefix>_fills.csv` and `<prefix>_disagreements.csv`, and nothing mentions writing back.

### `build_master_linkage.py` — one table with both studies

```bash
python3 "$L/build_master_linkage.py" \
    --left  cohort_records.csv --left-name  cohort \
    --right pathology.csv      --right-name pathology \
    --diff-dir database-manager/linkage/r01-crc/ --diff-prefix pathology \
    --id-field syn_id --out database-manager/linkage/r01-crc/master_linkage.csv
```

`--left` is what you gave `--current`, `--right` what you gave `--computed`; it checks this against
the diff's reports and stops if they look swapped. `--left-name` / `--right-name` name the sources
in the output columns. It reads the diff's verdicts rather than re-comparing — the fill/conflict
rule lives in one place. It accepts either file naming (`--for-analysis` or not). Outputs:

- **`master_linkage.csv`** — one row per id across both sources: `<left>_linked` /
  `<right>_linked`, a `link_class` (`matched_agree`, `matched_fill`, `matched_conflict`,
  `<left>_only`, `<right>_only`), `conflict_fields`, and every column from both sides. A column on
  both sides keeps **both values** (the right one suffixed `_<right-name>`); a disagreement is for
  a human.
- **`<prefix>_integrity.csv`** — structural problems, worst first, each with a count and a sentence
  on what it means; a zero count drops to `info`.

## Where the files go

Linking request → `database-manager/linkage/<name>/`. Merge for your own analysis →
`data-analyst/<study>/`.

## Writing values back into REDCap

Rarely the right move, and never part of a linking request — the hard link is a two-column upload
the user does, which is why a linking request needs no key end to end. Cohort patient records are
corrected by RAs in REDCap; a bulk write is a one-off migration ([[redcap-api-gotchas]] §0), and
ARGO has no script that pushes a link-data payload. If the database manager decides a fill is
genuinely needed:

1. **Fill blanks only.** `<prefix>_update.csv`, nothing else, shown with its counts.
2. **The user applies it**, in the Data Import Tool on the confirmed project, reviewing the
   changes, with blank cells **not** overwriting existing values. Check checkbox columns
   survived — the import tool has dropped them silently before.
3. **`<prefix>_overwrite.csv` only with explicit sign-off** on each row of `_conflicts.csv`.
4. **Traceable:** every value written maps to a row in the master table.

## Matching when there is no clean key

- **Primary: the exact join** on the confirmed key — what `link_studies.py` does, and what almost
  every real linkage needs.
- **Fallback: fuzzy matching**, done in the session (no script): token-wise `SequenceMatcher` on
  names (a token pair at ratio ≥0.85 counts) plus a normalized hospital-number comparison
  (lowercase, strip non-alphanumerics, drop leading zeros; `NYR` / `-999` / blank are neutral).
  Score = (name + hospital) / 2; show the top candidates for a human to confirm one at a time.
  **Never auto-accept a fuzzy match into a hard link** — a hard link is permanent.
- **Ties:** rank by score; never pick silently.

## Closing a linking request

When the hard link is delivered, close the request: `close_request.py linking <record>` from
[[weekly-check]] (shows the change, asks first), or tick `completed` in the REDCap UI. A merge for
your own analysis has no request to close.

## The original study-specific pipelines

The team's original linkage pipelines (P20, R01) live in a private analysis repo and are **not
available in this session** — don't claim to have read them or cite paths into them. If a teammate
shares one, lift only the matching and scoring logic; all REDCap I/O goes through
`argo_redcap_client.py` ([[redcap-api]], [[access-tiers]]) — the old in-repo client had no project
confirmation, retry or key masking.

## See also

- [[export-data]] — pull the files this skill links
- [[run-analysis]] (argo-data-analyst) — analyse the linked table (no access key)
- [[token-confirmation]], [[record-id-safety]], [[redcap-api-gotchas]] — write-back safety
