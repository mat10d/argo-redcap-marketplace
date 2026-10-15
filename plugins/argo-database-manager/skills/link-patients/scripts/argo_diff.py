#!/usr/bin/env python3
"""The one write-back safety rule, in one place.

ARGO's core guardrail for writing anything back to REDCap: **computed values may only ever fill
blanks.** If a cell already holds a different value, that's a disagreement for a human to look at,
never something to overwrite automatically.

That rule was implemented twice — once in link-data's diff_payload.py against a static CSV of
current state, and once bespoke inside qa-worklists's push scripts against a live re-pull. Two
implementations of one safety guarantee means two things to verify and two ways to drift. This is
the shared engine; both should use it.

There is a second guardrail here, learned the hard way: **an id that isn't on the current side is
not a blank record.** Reading it as one turned every value on an unmatched record into a "safe
fill", and importing that payload would CREATE records in the project rather than fill gaps in it.
Those ids are ORPHANS: reported, never payload.

It deliberately knows nothing about REDCap: it takes plain dictionaries and returns a decision.
That's what makes it testable without a token, a network, or a project.
"""
from __future__ import annotations

FILL = "fill"          # current is blank, computed has a value — safe to write
CONFLICT = "conflict"  # both hold values and they differ — needs a human
NOOP = "noop"          # nothing to do (equal, or nothing to add)
ORPHAN = "orphan"      # the record itself is absent from current — nothing to fill INTO


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
    """Decide what to do about one cell of an EXISTING record. Returns FILL, CONFLICT or NOOP.

    Only ever call this for a record that exists on both sides — a missing record is an ORPHAN,
    decided one level up in diff_records(), not a row of blanks.
    """
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

    Returns {"updates", "conflicts", "overwrites", "orphans", "missing_link", "counts"}:

      updates      rows of safe fills only — import these with overwriteBehavior=normal
      conflicts    long format (id, field, existing, computed) for human triage — never pushed
      overwrites   the same conflicting cells in wide form, for use ONLY after explicit sign-off
      orphans      computed rows whose id is absent from current — a gap report, NEVER payload.
                   Writing these would create new records, which is a decision for a human, not
                   a side effect of a fill.
      missing_link current ids with no computed counterpart — the other half of the gap report

    counts is per CELL on the computed side: FILL/CONFLICT/NOOP for records present on both
    sides, plus ORPHAN for every cell of an orphan record (which is compared to nothing). The
    four together account for every cell examined.
    """
    updates, overwrites, conflicts, orphans = [], [], [], []
    counts = {FILL: 0, CONFLICT: 0, NOOP: 0, ORPHAN: 0}
    fields = list(fields)

    for rid, comp in computed.items():
        if rid not in current:
            # No record to fill INTO. Report it; never let it reach a payload file.
            orphans.append({id_field: rid,
                            **{f: norm(comp.get(f, "")) for f in fields}})
            counts[ORPHAN] += len(fields)
            continue
        curr = current[rid]
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

    missing_link = [{id_field: rid} for rid in current if rid not in computed]

    return {"updates": updates, "conflicts": conflicts, "overwrites": overwrites,
            "orphans": orphans, "missing_link": missing_link, "counts": counts}
