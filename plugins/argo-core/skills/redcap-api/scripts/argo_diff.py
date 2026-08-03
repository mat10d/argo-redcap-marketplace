#!/usr/bin/env python3
"""The one write-back safety rule, in one place.

ARGO's core guardrail for writing anything back to REDCap: **computed values may only ever fill
blanks.** If a cell already holds a different value, that's a disagreement for a human to look at,
never something to overwrite automatically.

That rule was implemented twice — once in study-linkage's diff_payload.py against a static CSV of
current state, and once bespoke inside redcap-qa's push scripts against a live re-pull. Two
implementations of one safety guarantee means two things to verify and two ways to drift. This is
the shared engine; both should use it.

It deliberately knows nothing about REDCap: it takes plain dictionaries and returns a decision.
That's what makes it testable without a token, a network, or a project.
"""
from __future__ import annotations

FILL = "fill"          # current is blank, computed has a value — safe to write
CONFLICT = "conflict"  # both hold values and they differ — needs a human
NOOP = "noop"          # nothing to do (equal, or nothing to add)


def norm(value) -> str:
    """Normalise a value for comparison.

    Trims, treats 'nan' as blank, and collapses numeric tails so 1, '1', '1.0' and 1.0 all
    compare equal — REDCap and pandas disagree about these constantly, and a spurious difference
    would show up as a false conflict for someone to adjudicate.
    """
    s = ("" if value is None else str(value)).strip()
    if s.lower() == "nan":
        return ""
    try:
        f = float(s)
        return str(int(f)) if f == int(f) else repr(f)
    except (ValueError, TypeError):
        return s


def classify(current, computed) -> str:
    """Decide what to do about one cell. Returns FILL, CONFLICT or NOOP."""
    cur, new = norm(current), norm(computed)
    if cur == new:
        return NOOP
    if cur == "":
        return FILL if new != "" else NOOP
    if new == "":
        return NOOP        # never blank out an existing value
    return CONFLICT


def diff_records(computed: dict, current: dict, fields, id_field: str) -> dict:
    """Compare two {id: {field: value}} mappings.

    Returns {"updates": [...], "conflicts": [...], "overwrites": [...], "counts": {...}}:

      updates    rows of safe fills only — import these with overwriteBehavior=normal
      conflicts  long format (id, field, existing, computed) for human triage — never pushed
      overwrites the same conflicting cells in wide form, for use ONLY after explicit sign-off
    """
    updates, overwrites, conflicts = [], [], []
    counts = {FILL: 0, CONFLICT: 0, NOOP: 0}

    for rid, comp in computed.items():
        curr = current.get(rid, {})
        fill_row = {id_field: rid}
        over_row = {id_field: rid}
        for field in fields:
            verdict = classify(curr.get(field, ""), comp.get(field, ""))
            counts[verdict] += 1
            if verdict == FILL:
                fill_row[field] = norm(comp.get(field, ""))
            elif verdict == CONFLICT:
                conflicts.append({id_field: rid, "field": field,
                                  "existing": norm(curr.get(field, "")),
                                  "computed": norm(comp.get(field, ""))})
                over_row[field] = norm(comp.get(field, ""))
        if len(fill_row) > 1:
            updates.append(fill_row)
        if len(over_row) > 1:
            overwrites.append(over_row)

    return {"updates": updates, "conflicts": conflicts, "overwrites": overwrites,
            "counts": counts}
