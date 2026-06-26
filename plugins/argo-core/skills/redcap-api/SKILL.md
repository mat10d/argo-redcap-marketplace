---
name: redcap-api
description: Base conventions for talking to REDCap APIs across ARGO projects — token handling, record-ID safety, common curl/python patterns. Loaded transitively by other ARGO skills; rarely invoked directly.
---

# redcap-api

Shared API conventions used by every other ARGO plugin. If you are reading this directly you probably want a more specific skill (`redcap-build`, `data-export`, `study-portfolio`, etc.) — but the rules below apply universally.

## Tokens are optional — never block on one

REDCap tokens are scarce and admin-gated; requesting one per study doesn't scale. **No skill may
hard-require a token.** Check whether a token for the target project is present — if it is, use the
API; if not, take the no-token path (work from an on-disk export/download and produce files the
user applies in the REDCap UI) and say so. Never error out demanding a token. This is the single
most important cross-cutting rule — see **[[token-optional]]** for the per-operation fallback table.

## Critical safety rules

### 1. Confirm the target project token before any write
Multiple ARGO projects (admin REDCaps, cohort REDCaps, dev copies) use the same API endpoint. Before any call that imports, modifies, or deletes data: read back the project's `project_info` and confirm the title/PID matches what the user intended. See [[token-confirmation]].

### 2. Do not assume the record ID field is named `record_id`
Some ARGO projects use `study_id`, `participant_id`, `mrn`, etc. Always export metadata and read the first field name before constructing imports. See [[record-id-safety]].

### 3. Never log full API tokens
Truncate to last 4 chars when echoing. Never write tokens to files committed to git.

## Reference tables

These live in `references/` and are linked from skills in `argo-build`, `argo-pm`, etc. Update them here, not in the downstream skills:

- [[token-optional]] — **cross-cutting:** use the API only when a token is present; else fall back to files + UI
- [[mdc-rules]] — Missing Data Codes by field type
- [[standard-roles]] — ARGO's four standard REDCap roles
- [[dd-column-spec]] — Data dictionary CSV column reference

## Common patterns

### Export metadata
```bash
curl -X POST "$REDCAP_URL" \
  -d "token=$TOKEN" -d "content=metadata" -d "format=json" -d "returnFormat=json"
```

### Export project info (for token confirmation)
```bash
curl -X POST "$REDCAP_URL" \
  -d "token=$TOKEN" -d "content=project" -d "format=json"
```

## TODO during pilot
- [ ] Decide on a shared Python wrapper vs. raw curl. Currently both are in use across existing skills.
- [ ] Document the credential storage convention (env var, keychain, `.env` per project).
- [ ] Add a `/argo-token-check` slash command that runs project_info and prints title + record-ID field.
