# Migration-only push workflow

**This is not part of a QA round.** In a QA round the RAs edit REDCap directly and you re-run
the worklist build to confirm — so REDCap's own branching, validation and audit trail apply. We
do not round-trip dirty Excel into REDCap.

This page exists only for a genuine one-off legacy migration: a bulk load of historical data
into a study. `push_updates.py` refuses to run without `--force-migration` plus a shown dry-run
([[access-tiers]] Tier 3). Read [[redcap-api-gotchas]] §0 (no programmatic writes to cohort
patient data) before using any of it.

`snapshot_project.py` (a read-only export) is fine to use at any time.

## Where things live

```
qa-specialist/<study>/
├── config/{fields.yaml, scope_ids.csv}
├── worklists/<round>/          # original worklists (build_worklists.py)
├── RA_response/                # files dropped here by RAs (flat — RA naming)
├── push_drafts/<round>/        # one CSV per (site, workbook) — staged updates
├── RA_summaries/<round>/       # per-RA markdown (summarize_for_ra.py)
├── RA_questions.md             # open items, RA-facing tone, single source
└── snapshots/                  # timestamped full project exports (snapshot_project.py)
```

`<round>` defaults to today's date (`YYYY-MM-DD`) — every script that writes derived artifacts
auto-appends this subdir so reruns within a round overwrite cleanly *within* the round folder,
and the next round (next day, or whatever you pass to `--round`) gets a fresh folder instead of
stomping the prior cycle. Pass `--round=` (empty) to disable the subdir (legacy flat layout).

## 1. Build per-site push CSVs

One CSV per (site, workbook), columns = record-ID + only the fields touched. Use REDCap's coded
values:
- Radio/dropdown: numeric code (e.g. `m_score = -888`)
- Checkbox: `field___N = 0|1` for positive codes, `field____N = 0|1` for negative codes (4
  underscores — REDCap strips the minus). To recode a checkbox from -999 to -888, write both
  `field____999=0` AND `field____888=1`.
- Blank cells = "leave alone" under `overwriteBehavior=normal`. So only the named fields get
  touched.

They go in `qa-specialist/<study>/push_drafts/<round>/`.

## 2. Snapshot before push

When all sites are resolved (push_drafts complete, RA_questions cleared), take a full project
snapshot as the rollback point:

```bash
python3 .../argo-qa-specialist/skills/qa-worklists/snapshot_project.py \
    --url "$REDCAP_URL" --token-env CRC_TOKEN \
    --out qa-specialist/<study>/snapshots/ --tag pre-qa-push
```

This writes `snapshot_<timestamp>_pre-qa-push.csv` — a raw flat export of every record, every
field, with DAGs. If a push goes wrong, restore via `overwriteBehavior=overwrite` against this
file.

## 3. Verify before push (handle RA direct edits)

RAs often update REDCap directly between when we stage `push_drafts/` and when we push. If we
push blindly with `overwriteBehavior=normal`, any cell we'd overwrite that the RA already filled
differently will be clobbered. To avoid that, re-pull and emit only the deltas that are still
needed:

```bash
python3 .../argo-qa-specialist/skills/qa-worklists/verify_push.py \
    --url "$REDCAP_URL" --token-env CRC_TOKEN \
    --push-drafts qa-specialist/<study>/push_drafts/<round>/
```

Writes:
- `push_drafts/<round>/_verified/<original>.csv` — safe-to-push deltas (cells still needed)
- `push_drafts/<round>/_conflicts.md` — REDCap is now non-blank and *differs* from our planned
  write; review each one

Push the `_verified/` copies, not the originals.

## 4. Push atomically

Push all sites in one merged call:

```bash
python3 .../argo-qa-specialist/skills/qa-worklists/push_updates.py \
    --url "$REDCAP_URL" --token-env CRC_TOKEN \
    qa-specialist/<study>/push_drafts/<round>/_verified/*.csv --dry-run   # preview merged payload
# then, without --dry-run, adding --force-migration, to actually push:
python3 .../argo-qa-specialist/skills/qa-worklists/push_updates.py \
    --url "$REDCAP_URL" --token-env CRC_TOKEN --force-migration \
    qa-specialist/<study>/push_drafts/<round>/_verified/*.csv
```

Uses `overwriteBehavior=normal` so blank cells in the payload don't clobber existing values.
Returns the count of records touched.

## 5. Re-run build_worklists.py to verify

After the push, regenerate the worklists. Cells that were resolved should drop out — anything
still yellow is either a push that didn't take or a new gap. Diff this against the prior run for
a clean "did the push do what we expected" check.
