#!/usr/bin/env python3
"""argo_analysis.survival — planned, not built.

Survival analysis (Kaplan-Meier curves, log-rank tests, Cox models) is on the
list for this library and is not in it yet. This file exists so that the answer
to "can ARGO do survival?" is a straight *not yet*, in one place, rather than a
half-finished function that produces a number nobody should trust.

    from argo_analysis import survival
    survival.survival(study, "enrol_date", "death_date")
    -> stops with: Survival analysis is planned but not built yet.

The registry entry (analyses/survival.md) marks it planned, so it shows up in
"what I can do" as something coming rather than something missing. If you need
it now, say so — knowing it is wanted is what moves it up the list.
"""

from __future__ import annotations

import sys

#: Read by the registry and by "what I can do". "ready" when this is built.
STATUS = "planned"

MESSAGE = (
    "Survival analysis is planned but not built yet.\n"
    "Kaplan-Meier curves, log-rank tests and Cox models are on the list for the ARGO\n"
    "analysis library, but nothing here computes them today, and a wrong survival\n"
    "curve is worse than none. Table 1 is ready and works now (argo_analysis.table1).\n"
    "If survival is what you need, say so — that is what moves it up the list."
)


def survival(*args, **kwargs):
    """Stop, with an explanation. This is the whole module, on purpose."""
    raise NotImplementedError(MESSAGE)


def _main() -> int:
    print(__doc__.strip())
    print()
    print(MESSAGE)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
