# Token confirmation

Many ARGO projects share one API endpoint. The only thing distinguishing them is the access
key. A wrong key can silently write to the wrong project.

**This is enforced in code, not by convention.** Every write method on the shared client
(`import_records`, `import_records_csv`, `import_metadata`) calls `confirm_project()` before
posting. Your job as a script author is one thing:

**Pass `expect_pid=` (preferred — a project number is unambiguous) or `expect_title=` to every
write call.** Omit it and the write is unguarded.

```python
client.import_records(payload, expect_pid="224")             # best
client.import_records(payload, expect_title="Study Tracker")  # acceptable
```

On mismatch the client raises `ProjectMismatch` with "Stopping before making any changes" and
nothing is posted. An exact title match passes silently; a partial match passes with a warning.

Do not re-implement this check per script, and do not substitute a prose "confirm with the
user" step for it.

See [[record-id-safety]] for the parallel field-name rule, [[access-tiers]] for the decision
record.
