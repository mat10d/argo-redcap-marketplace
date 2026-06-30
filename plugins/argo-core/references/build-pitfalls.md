---
name: build-pitfalls
description: Consolidated gotchas from real ARGO builds. Every entry here is something we got wrong at least once. Read before starting a new build or ingest.
---

# Build pitfalls

This is the running list of mistakes we've made on real ARGO builds and the rules we now follow to avoid repeating them. Reference from `redcap-build` and `redcap-admin`.

## DD construction

### 1. `yesno` field type — never use it
`yesno` cannot hold MDC codes. Always use `radio` with `1, Yes | 0, No | -666, ... | -777, ... | -888, ... | -999, ...`. Validator enforces this.

### 2. `hospital_number` is required for patient-level DDs
Even if the Word proforma omits it. ARGO standard: text field, Identifier=`y`, position 2 (right after the record-id field). The validator can be run with `--patient-level` to enforce. Non-patient studies (training, capacity-building surveys, biobank specimen tracking with no patient link) may skip — document the deviation in the Active Databases sheet.

### 3. DD column 11 is `Identifier?`, column 13 is `Required?`
A `y` in column 11 means the field holds PII (and gets de-identified on export based on role permissions). A `y` in column 13 means data entry blocks until populated. Agents reading the DD via index have confused the two — count commas carefully or use a DictReader.

### 4. Missing Data Codes live entirely in the DD
- **Choice fields (radio/dropdown/checkbox):** MDCs appended to choices
- **Text/notes/date fields:** MDCs in Field Note column as a comment

That's it. **No separate project-level MDC configuration step** in REDCap. See [[mdc-rules]].

### 5. "Other + branched free-text" is the clean DD extension pattern
When source data has categories the DD doesn't anticipate (e.g., morbidity values like "Liver failure" not in `morbidity_major_types`):
- Add `99, Other` to the checkbox/radio choices
- Add a sibling text field `<parent>_other` branched on `[<parent>(99)] = '1'`
- Route the orphan source values to the `___99` bit + verbatim text in `_other`

Cleaner than nearest-match nudging or losing the data.

## Dates

### 6. Display format ≠ import format
REDCap's `content=record action=import` API and Data Import Tool both require dates in **YYYY-MM-DD** or M/D/Y format, regardless of the field's `date_dmy` display validation. Always normalize import CSV dates to YYYY-MM-DD. See [[redcap-date-import]] for full rules.

### 6b. Checkbox MDC bits don't survive import naming
When a checkbox field's DD has MDC codes as choices (`-666, ... | -999, ...`), naïvely expanding them to checkbox bit columns produces `field___-666` etc. **REDCap rejects this** ("not found in the project as real data fields"). Two fixes:
- **Preferred:** omit MDC bit columns from the import CSV when no record actually has MDC for that checkbox (common for retrospective data — all bits are 0 anyway).
- **Alternative:** rename to `field___666` (no hyphen) — REDCap's internal column naming strips negative signs from checkbox codes.

Radio/dropdown fields are not affected; they take the raw `-666` as a cell value.

### 7. MDC date codes reverse for import
Display form (`06-06-6666`) goes in the Field Note. Import form (`6666-06-06`) goes in the data CSV. REDCap converts on display.

## Ingest

### 8. DD is canonical — reshape source data to fit
The DD is canonical. Source typos (`Haemagioma` → `Haemangioma`), inverted codings, missing categories — reshape source. Don't expand the DD just to absorb source quirks unless the user approves the extension.

### 9. Inverted codings need PI confirmation — but don't over-escalate when obvious
HepB / HepC source columns labeled `1=Yes, 2=No` vs DD using `1=Negative, 2=Positive` is a real semantic question. **But** when the column header itself spells out the meaning, don't bury the user in confirmation requests — make the obvious call and flag in the mapping report.

### 10. "Nil" / NaN / missing-source handling depends on field type
**Default rule:** blank source data stays blank in the import CSV. MDC codes are reserved for the rare case where the source explicitly documents "patient does not know" / "missing in case notes" — almost never the case in retrospective ingests.

- **Checkbox bit:** `Nil` / `NaN` / blank → `0` (not selected)
- **Radio with a "No" option:** `Nil` → `0` only if column-name semantics support it (e.g., `morbidity_popf`). Otherwise **blank**, not MDC.
- **Text/notes:** blank → blank
- **Date:** blank or "none"/"n/a"/"nil"/"-" → blank
- **Column missing from source entirely:** blank for all records, note in mapping_report as "(no source column — left blank for backfill)"

Document every "Nil" decision in the mapping report.

### 11. Duplicate source IDs → re-ID + document
Sometimes the source has `id=41` twice for distinct patients. Re-ID the later occurrence to the next free integer, note both in the mapping report, and surface to the study coordinator. Don't merge or drop.

## Project creation & ARGO-internal admin

### 12. No Super API Token at OAU — UI path is primary
Per-project API tokens are admin-controlled at OAU. The marketplace defaults to CSV-upload-via-UI; API path is an enhancement available once a token is obtained. See [[project-no-super-token]].

### 13. Admin REDCaps (SIR/SPR/etc.) are PIDs 221-225 — DO NOT confuse with new project PIDs
The Hepatectomy build had a moment where PID 242 (new study) was confused with PID 224 (SIR admin). Token confirmation always shows `project_title` — verify before any write.

### 13b. Push SIR build_tracking + study_metadata as each step lands
Do not batch the per-step writes at the end of a build. Immediately after each canonical step completes (project creation, DD upload, user rights, data import, internal review, PI review, production), call `sir_update.py` with the right `--mark-step` / `--set` / `--status` flags. The portfolio dashboard reads these in real time.

The 7 build_tracking flags: `project_created`, `dd_uploaded`, `user_rights_complete`, `data_imported` (radio: 1=Yes/2=Prospective-not-required), `review_internal`, `review_pi`, `study_production`.

### 14. SIR records can have stale data after submission
PIs often submit before IRB approval lands ("Pending" `irb_number`, blank `irb_approval_expires`). Backfill the SIR record once the cert is received — see `sir_update.py` in redcap-build. Future analyses pulling the SIR for tracker context need the corrected values.

## Decision protocol

### 15. Walk every non-mechanical decision through the user
Auto mode applies to file ops and validation. Decisions about data semantics, DD structure, identifier conflicts, or live-project writes always go through a user check, one at a time, sorted by stakes. See [[decision-protocol]].

### 16. Don't over-escalate
The flip side of #15: when the data tells you the answer (column headers, clinical literature, distribution of values), make the call and document it. Don't bury the user in confirmations.

## Cross-cutting

### 16b. Sister-study instrument structure must match
Parallel build agents on sister SIRs (same PI, same HREC, different procedures/arms) can produce divergent instrument structures (e.g., RID 17 = 1 instrument with sections; RID 18 = 6 instruments). Audit time should catch this and reconcile. Run `make_roles_csv.py` on both DDs and compare the `Forms detected` lists.

### 17. Two studies with the same title aren't necessarily duplicates
RIDs 17 and 18 both titled "Clinical Outcomes and Lessons Learned from Hepatobiliary Surgery in Nigeria…" — they're sister studies for Hepatectomy and Whipple respectively. Treat duplicate-looking SIR titles as warnings, not facts; check the attached questionnaire to confirm.

### 18. Honorifics in PI name fields
SIR's `pi_first_name` may contain "DR." or "PROF." — strip before deriving the "PI Name (cited)" Surname-Initial format. `fill_new_project.py` does this.

### 19. Sub-category derivation needs the right keyword pool
"Retrospective" / "retroactive review" → Epidemiology. "Database" alone → ambiguous. Patterns in `fill_new_project.py` evolve as new studies surface words we haven't seen.

## Where this doc lives in the workflow

| Skill | When to consult |
|---|---|
| `argo-build/redcap-build` Path A | Before starting a new DD construction — items 1, 2, 3, 4, 5 |
| `argo-build/redcap-build` Path B | Before auditing an existing DD — items 1-5 plus 8, 11 |
| Importing external/historical data | Before designing an import pass — items 6-11 |
| `argo-build/redcap-build` (triage) | Before generating a paste box / triaging a SIR — items 12, 13, 14, 17, 18, 19 |
| `argo-build/redcap-admin` | Before any live-project write — items 12, 13, 14 |
| All skills | Item 15 + 16 (decision protocol) always applies |
