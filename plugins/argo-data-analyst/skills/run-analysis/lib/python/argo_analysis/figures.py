#!/usr/bin/env python3
"""argo_analysis.figures — two charts, one look, print-ready.

    from argo_analysis import figures
    figures.bar_by_group(study, "education", "redcap_data_access_group",
                         "outputs/education_by_site.png")
    figures.hist(study, "age", "outputs/age.png")

THE LOOK, AND WHY IT IS FIXED
-----------------------------
Both charts come out the same way, because a figure in a paper is read at 8 cm
wide by someone who is not looking for it:

  * PNG at 300 dpi — the resolution journals ask for, big enough to crop
  * the Okabe-Ito palette, which stays distinguishable for readers with any of
    the common forms of colour blindness, and still separates in greyscale print
  * the title is the field's question, in the words the participant was asked
  * the subtitle is always `n = … ; missing = …`, because a chart whose
    denominator you cannot see is a chart you cannot check
  * a footnote naming the script and the date — the provenance of a figure is
    the script that made it, and a figure that has drifted from the file it came
    from is how the wrong version ends up in a submission
  * no chartjunk: no top or right frame, a faint horizontal grid, nothing else

Percentages here obey the same rule as everywhere in this library: they are out
of the records the field was actually asked of and that answered it.

If matplotlib is not installed, nothing crashes. Both functions say so in one
sentence, name the one command that fixes it, and return None — the table part
of an analysis is worth having even on a laptop that cannot draw.
"""

from __future__ import annotations

import datetime
import importlib
import sys
from pathlib import Path

try:
    from . import core, table1 as _table1
except ImportError:                   # run as a loose file from its own folder
    import core                       # type: ignore
    import table1 as _table1          # type: ignore


#: Okabe-Ito: eight colours chosen to stay apart for colour-blind readers.
#: Ordered so the first two — blue and orange — are the pair used most often.
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7",
           "#56B4E9", "#D55E00", "#F0E442", "#000000"]

DPI = 300
FIGSIZE = (7.5, 4.5)
GRID_COLOUR = "#D9D9D9"
INK = "#222222"
QUIET_INK = "#666666"

MATPLOTLIB_MISSING = (
    "This chart needs matplotlib, a free add-on for Python that draws graphs.\n"
    "It is not installed on this computer yet, so the chart was skipped — the rest\n"
    "of the analysis is unaffected. To draw it, open a terminal window, type the\n"
    "line below, press Enter, wait for it to finish, then run this again:\n\n"
    "    python3 -m pip install matplotlib\n"
)


def _pyplot():
    """matplotlib's drawing surface, or None with one plain paragraph of explanation.

    Imported fresh each time rather than cached at the top of the file: this
    module has to be importable, and its docstring readable, on a machine where
    matplotlib was never installed.
    """
    try:
        matplotlib = importlib.import_module("matplotlib")
        matplotlib.use("Agg")             # no screen needed; write straight to a file
        return importlib.import_module("matplotlib.pyplot")
    except ImportError:
        print(MATPLOTLIB_MISSING, file=sys.stderr)
        return None


def _dress(fig, ax, title, subtitle):
    """The house look, applied in one place so both charts cannot drift apart."""
    ax.set_title("")
    fig.suptitle(title, x=0.01, y=0.98, ha="left", fontsize=13,
                 fontweight="bold", color=INK)
    fig.text(0.01, 0.90, subtitle, ha="left", fontsize=9.5, color=QUIET_INK)
    fig.text(0.01, 0.015, f"{_generating_script()} — {datetime.date.today().isoformat()}",
             ha="left", fontsize=7, color=QUIET_INK)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID_COLOUR)
    ax.yaxis.grid(True, color=GRID_COLOUR, linewidth=0.8)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)
    ax.tick_params(colors=QUIET_INK, labelsize=9.5, length=0)


def _generating_script() -> str:
    argv0 = sys.argv[0] if sys.argv else ""
    if not argv0 or argv0 in ("-c", "-"):
        return "an interactive session"
    return Path(argv0).name


def _save(fig, path, plt):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Chart written to {path}")
    return path


def _counts(study, field, mask):
    """{level label: count} for one column of records, in codebook order, and the
    number of records that were asked the field and answered it."""
    mapping = core.labels(study, field)
    applies = core.applicable(study, field)
    usable = core.usable(study, field)
    answered = mask & applies & usable
    out = {}
    if core.field_type(study, field) == "checkbox":
        for code, label in mapping.items():
            column = f"{field}___{code}"
            if column in study.data.columns:
                ticked = study.data[column].astype(str).str.strip() == "1"
                out[label] = int((mask & applies & ticked).sum())
            else:
                out[label] = 0
    else:
        values = study.data[field].astype(str).str.strip()
        for code, label in mapping.items():
            out[label] = int((answered & (values == code)).sum())
    return out, int(answered.sum()), int((mask & applies).sum()) - int(answered.sum())


def bar_by_group(study, field, group_by, path):
    """A grouped bar chart: one cluster per level of `field`, one bar per group.

    Bars are percentages within each group — the honest comparison when the
    groups are different sizes — out of the records that group was asked the
    field and answered it. The counts are printed above the bars so nothing is
    hidden behind a percentage.

    Returns the path written, or None if matplotlib is not installed.
    """
    plt = _pyplot()
    if plt is None:
        return None
    if group_by not in study.data.columns:
        raise ValueError(f"'{group_by}' is not a column in this export, so the chart "
                         "cannot be grouped by it.")
    mapping = core.labels(study, field)
    if not mapping:
        raise ValueError(f"'{field}' has no choice list in the codebook, so it has no bars "
                         "to draw. Use hist() for a number.")

    masks = _table1.group_masks(study, group_by)
    groups = [g for g in masks if g != "overall"]
    levels = list(mapping.values())

    per_group = {}
    for group in groups:
        counts, answered, _ = _counts(study, field, masks[group])
        per_group[group] = (counts, answered)
    _, answered_total, missing_total = _counts(study, field, masks["overall"])

    fig, ax = plt.subplots(figsize=FIGSIZE)
    width = 0.8 / max(len(groups), 1)
    for i, group in enumerate(groups):
        counts, answered = per_group[group]
        heights = [(100.0 * counts[l] / answered if answered else 0.0) for l in levels]
        positions = [x + i * width - 0.4 + width / 2 for x in range(len(levels))]
        bars = ax.bar(positions, heights, width=width * 0.92,
                      color=PALETTE[i % len(PALETTE)],
                      label=f"{group} (n = {answered})")
        for bar, level in zip(bars, levels):
            ax.annotate(str(counts[level]),
                        (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                        ha="center", va="bottom", fontsize=7.5, color=QUIET_INK)

    ax.set_xticks(range(len(levels)))
    ax.set_xticklabels(levels, fontsize=9.5)
    ax.set_ylabel("% of those asked and answered", fontsize=9.5, color=QUIET_INK)
    if len(groups) > 1:
        ax.legend(frameon=False, fontsize=9, loc="upper right")
    _dress(fig, ax, core.field_label(study, field),
           f"n = {answered_total} ; missing = {missing_total}")
    fig.subplots_adjust(top=0.80)
    return _save(fig, path, plt)


def hist(study, field, path, bins: int = 20):
    """A histogram of one number, over everyone the field was asked of.

    Returns the path written, or None if matplotlib is not installed.
    """
    plt = _pyplot()
    if plt is None:
        return None
    applies = core.applicable(study, field)
    usable = core.usable(study, field)
    keep = applies & usable
    values = []
    for raw in study.data.loc[keep, field].astype(str).str.strip().tolist():
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            pass
    missing = int(applies.sum()) - len(values)
    if not values:
        raise ValueError(f"'{field}' has no numbers in it to chart — every value is blank, "
                         "a missing-data code, or not a number.")

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.hist(values, bins=bins, color=PALETTE[0], edgecolor="white", linewidth=0.6)
    ax.set_xlabel(core.field_label(study, field), fontsize=9.5, color=QUIET_INK)
    ax.set_ylabel("Number of records", fontsize=9.5, color=QUIET_INK)
    _dress(fig, ax, core.field_label(study, field),
           f"n = {len(values)} ; missing = {missing}")
    fig.subplots_adjust(top=0.80)
    return _save(fig, path, plt)


def _main() -> int:
    print(__doc__.strip())
    print("\nThis file is part of the ARGO analysis library. It is not run on its own —")
    print("an analysis script imports it. See the run-analysis skill for how to start one.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
