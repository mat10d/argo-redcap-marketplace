---
name: record-id-safety
description: The record ID field in REDCap is not always literally `record_id`. Always read metadata before importing.
---

# Record ID safety

REDCap names the record ID field whatever the project creator chose. Common ARGO values: `record_id`, `study_id`, `participant_id`, `mrn`.

**Before any import:**
1. Export project metadata
2. Read `field_name` of the first field — that is the record ID column
3. Use that exact name as the header in your import CSV

Import CSVs with the wrong record ID column header silently create new records instead of updating existing ones. This has burned us before. See [[token-confirmation]] for the parallel write-safety rule.
