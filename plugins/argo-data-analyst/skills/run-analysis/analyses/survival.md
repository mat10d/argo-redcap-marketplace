---
name: survival
status: planned
summary: Time-to-event survival — Kaplan–Meier curves and Cox models.
python_module: argo_analysis.survival
r_module: argo_analysis/survival.R
outputs: none yet
---

# survival — planned

**Time-to-event with Kaplan–Meier + Cox — not built yet.**

Nothing here exists as a working analysis. The module is present so that the
registry has one entry per analysis and so calling it fails loudly rather than
silently doing something else: every function in it stops with

> Survival analysis is planned but not built yet.

## What to say when someone asks for it

Say it plainly — "survival analysis isn't built into the toolkit yet" — and then
either write it as an ordinary hand-written script under the skill's normal
script contract (saved, commented, reproducible), or note the request. Never
tell a user the toolkit does survival analysis, and never generate a study
script that imports it.

## What it needs from the user (when it is built)

The time variable, the event indicator (and which code means the event), and the
grouping variable for the curves — the same ask-once rule as `table1`.

## What it will produce

A Kaplan–Meier table and figure, median survival with confidence intervals, a
log-rank test, and a Cox model summary — one workbook, one sheet per table, PNG
figures, exactly the house style `table1` uses.
