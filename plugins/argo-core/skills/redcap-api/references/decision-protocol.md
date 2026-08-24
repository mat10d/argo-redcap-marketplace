---
name: decision-protocol
description: Walk the user through every judgment call interactively, even in auto mode. Mechanical work proceeds; decisions wait.
---

# Decision protocol

In ARGO plugins, **walk the user through every judgment call** — even when auto mode is on. Auto mode applies to mechanical work (file ops, validation, reformatting), not to decisions.

## What counts as a decision

Any choice that affects:
- **Data semantics** — value translations between source and DD (especially inverted codings, lost categories)
- **DD structure** — adding/removing fields, changing required flags, modifying choice lists
- **Identifier conflicts** — duplicate IDs, missing IDs, ID generation rules
- **Irreversible actions** — API imports to live REDCaps, file overwrites of production data
- **Clinical meaning** — anything where getting it wrong silently propagates a misinterpretation across many records

## What counts as mechanical

- File reads, file writes to scratch folders
- Validator runs
- Format conversions (DOCX → TXT, XLSX → CSV)
- Per-record reformatting that has no semantic ambiguity (e.g., DD-MM-YYYY normalization where source format is unambiguous)
- Reporting and dashboard rendering

## How to walk a decision

1. **Triage by stakes.** Highest first: clinical semantics > identifier conflicts > category coverage > formatting.
2. **One at a time.** Don't batch — the user will skim and miss things.
3. **State the finding, the stakes, the options, and your recommendation (only if asked).**
4. **Wait for the call** before applying.
5. **Document the decision** in the relevant `mapping_report.md` or audit log so it's reproducible.

## Where this rule lives

This convention applies to:
- Importing external/historical data — every column→field translation that isn't 1:1
- `argo-database-manager/build-study` Path B — every audit finding with a non-obvious fix
- `argo-database-manager` — every write to a live project
- Any `argo-project-manager` skill that closes a ticket or modifies an admin REDCap

## See also
- [[record-id-safety]] — never modify the record ID field without confirmation
- [[token-confirmation]] — confirm target project before any API write
