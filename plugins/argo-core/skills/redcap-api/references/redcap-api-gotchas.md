---
name: redcap-api-gotchas
description: REDCap REST API write-side gotchas — dates, overwrite modes, choice fields. Read before any bulk import.
---

# REDCap API gotchas

Compiled from real ARGO bulk imports. Each item below was discovered the hard way; the failure mode is silent or misleading, so verify explicitly.

## 0. POLICY: no programmatic writes to cohort patient data

**Default: the QA/analysis loop does not write patient data** — with one narrow exception, below. Cohort patient records are entered and corrected by RAs *directly in REDCap*, against the worklists — not by pushing CSVs. Programmatic record import bypasses the three things REDCap does for you:

- **branching logic** — writes land in fields that are hidden/not-applicable (orphan data),
- **field validation** — out-of-range / wrong-coded values land silently,
- **audit trail** — edits show as "API import," not as the RA who is accountable for them.

Every silent-failure mode in this document was hit during the 2026-06 CRC push: a verify step that reported "0 conflicts" while staging 19 real overwrites, orphan writes into gated-off fields, and the REDCap UI Data Import Tool dropping **all** checkbox columns without error.

**Scope.** This restricts *cohort patient-data record imports* (`content=record` writes to a study/cohort project). It does NOT restrict admin-REDCap writes (e.g. `build-study` lifecycle tracking) or project-structure writes (data dictionary / user rights) — those are a separate, lower-risk class.

**The one QA exception (decided 2026-10-09, [[access-tiers]] Tier 3):** `qa-worklists/upload_mdc.py` may upload a missing-data code the RA returned (-666/-777/-888/-999; date form `8888-08-08` for dates; the code's own option column for a checkbox), only into a worklist cell that is blank in REDCap now, only where the field lists the code and the RA's note / field comment fit it. Every other returned value is entered by the RA in REDCap; QA checks it landed with `reconcile_return.py` (read-only).

**Cohort record import is otherwise migration-only.** If legacy data genuinely must be bulk-loaded, treat it as a separate, deliberate one-off migration — REDCap-native import with validation ON, a decode-and-categorize preview (FILL / RECODE / OVERWRITE / HIDDEN-orphan / ALREADY) reviewed by a human, and a fresh `snapshot_project.py` first — never a step in the routine cycle. The `qa-worklists` write-back scripts (`push_updates.py`, `verify_push.py`) are **deprecated** under this policy; `snapshot_project.py` (read-only export) is retained.

## 1. Dates must be YYYY-MM-DD on import

Whatever a field's display format (`date_dmy` shows DD-MM-YYYY), import every date as
`YYYY-MM-DD` — a DD-MM-YYYY value is rejected, and a DD/MM value can be misread as M/D. The full
rule, the normalizer, and the MDC date codes in import form are in [[redcap-date-import]].

## 2. `overwriteBehavior=normal` silently drops cross-form fields on NEW records

When creating a new record with fields spanning multiple forms (e.g. `study_initiation_request_complete` form 1 + `build_tracking` form 2 + `study_metadata` form 3), `overwriteBehavior=normal` will commit ONLY the first form's fields. The other forms' fields disappear without error — the API response is still `{"count": 1}`.

**Rule of thumb:**
- **Creating a new record** (record_id doesn't yet exist) → use `overwriteBehavior=overwrite`
- **Updating an existing record** where a blank in the payload must not erase a stored value → use `overwriteBehavior=normal` (blank cells are ignored; non-blank cells still replace)

After any bulk import, spot-check 2-3 records by exporting them and confirming cross-form fields landed. Don't trust the `{count: N}` response alone.

## 3. Choice fields require numeric codes, not labels

For dropdown / radio / checkbox fields, the API expects the underlying code (e.g. `"1"` for "Colorectal"), not the display label (`"CRC"` or `"Colorectal"`). Sending a label returns HTTP 400 with `"The value is not a valid category for <field>"`.

Build an explicit map from your source data's labels to the DD's codes. The DD CSV's `select_choices_or_calculations` column is the source of truth — split on `|`, then on `,` to extract `code, label` pairs.

## 4. record_id is not API-renameable

There is no API endpoint to rename a record's `record_id`. The UI has a per-record "Rename Record" feature but it's not bulk-callable. To re-sequence records, you must:

1. Export the old record(s) (including any file uploads via `content=file action=export`)
2. Delete the old record(s) (`content=record action=delete`)
3. Re-create with new explicit `record_id` in the payload (and `overwriteBehavior=overwrite`)
4. Re-upload any files via `content=file action=import`

For large bulk reorganizations, this is high-risk (file uploads especially). Prefer a manual UI rename pass when feasible.

## 5. `forceAutoNumber=true` overrides explicit record_id

If your project has auto-numbering enabled and you want to specify exact record_ids on import, do NOT pass `forceAutoNumber=true` — that flag tells REDCap to ignore your `record_id` value and assign the next number. Omit it (or set to false) when you want explicit IDs.

## 6. Verify, don't trust

Always pull a sample record after an import and inspect all expected fields. The combination of (1) `normal`-mode silent drops, (2) date format rejections, (3) choice code rejections all surface as either no error at all or single-field 400s; you can easily miss them across hundreds of records. A 30-second post-import sanity check (`curl ... content=record format=json records[0]=<rid>`) catches most of these.

## Related
- [[redcap-date-import]] — display format vs import format mismatch
- [[token-confirmation]] — always confirm project_title before any write
