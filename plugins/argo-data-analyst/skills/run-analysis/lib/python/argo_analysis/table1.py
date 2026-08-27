#!/usr/bin/env python3
"""argo_analysis.table1 — the table every clinical paper opens with.

One call, one tidy table:

    from argo_analysis import core, table1
    study = core.apply_missing(core.load_study("records.csv", "datadictionary.csv"))
    t1 = table1.table1(study, "redcap_data_access_group",
                       ["age", "sex", "education", "tobacco_use"])

THE SHAPE
---------
Long, one row per (variable, level, statistic), one column per group level plus
an `overall` column:

    variable, level, statistic, <group level 1>, <group level 2>, …, overall

  continuous variables get   n, missing, mean, sd, median, q1, q3
  categorical variables get  n and pct for each level, then missing

Every cell is a number, never a pre-formatted "12 (34.5%)" string. That is what
lets the R port be compared to this one for equality, and lets a user paste the
table into a manuscript, a plot or a spreadsheet without unpicking it first.

THE FOUR RULES BEHIND THE NUMBERS
---------------------------------
1. **Missing means missing.** Blanks and REDCap's missing-data codes
   (-666, -777, -888, -999, 666) are counted under `missing` and never averaged,
   and a code offered as a choice never becomes a row of the table.
2. **Percentages are of the people who were asked.** The denominator is the
   records the field *applies to* — its branching logic fired — and that have a
   usable value. Pregnancy status behind `[sex] = '2'` is out of the women, not
   out of the cohort. See `core.denominator`.
3. **Levels come from the codebook, in codebook order.** Never alphabetical,
   never "whatever the data happened to contain". A level nobody chose still
   appears, as a zero.
4. **Two decimal places, everywhere.** `core.DECIMALS`, one constant, so the
   Python and R tables agree to the last digit.

The grouping variable is REQUIRED. There is no sensible default — a Table 1
without a comparison is a list — so the skill asks for it once and passes it in.
"""

from __future__ import annotations

import math
import random
import sys

try:                                  # inside the package, the normal case
    from . import core
except ImportError:                   # run as a loose file from its own folder
    import core                       # type: ignore


#: A p-value is computed only when asked for. This is the default seed used for
#: the one test that needs randomness (a Monte Carlo chi-square on a sparse
#: table), so the same data always gives the same p-value.
DEFAULT_SEED = 20260827

#: How many shuffles the Monte Carlo chi-square uses. R's chisq.test default.
MONTE_CARLO_DRAWS = 2000


def _round(value):
    """Round to `core.DECIMALS` the way a printed number rounds.

    Formatting and then reading back looks roundabout, but it is what makes
    Python, R and Stata print the same last digit on a tie — which is the whole
    point of having a golden copy of the table.
    """
    if value is None:
        return None
    return float(format(float(value), f".{core.DECIMALS}f"))


# --------------------------------------------------------------------------
# Which kind of variable is this?
# --------------------------------------------------------------------------

def variable_kind(study, field: str) -> str:
    """"categorical", "continuous", or "" if this field cannot be summarised.

    Decided from the codebook, not from the data: a field with a choice list is
    categorical even if only one level was ever used, and a number is a number
    even if this particular export happens to hold whole values only.
    """
    ftype = core.field_type(study, field)
    if ftype in core.CHOICE_TYPES:
        return "categorical"
    validation = core.meta(study, field).get(
        "text_validation_type_or_show_slider_number", "").strip()
    if ftype in ("text", "calc", "slider") and (
            validation in core.NUMERIC_VALIDATIONS or ftype in ("calc", "slider")):
        return "continuous"
    if ftype == "" and field in study.data.columns:
        return ""                       # not in the codebook — we will not guess
    return ""


# --------------------------------------------------------------------------
# Columns: the group levels, in codebook order
# --------------------------------------------------------------------------

def group_levels(study, group_by: str) -> list:
    """The group column headings, in codebook order where there is a codebook.

    The site column (`redcap_data_access_group`) has no codebook entry — REDCap
    manages it outside the dictionary — so its levels come from the data, sorted,
    which is stable and reproducible.
    """
    mapping = core.labels(study, group_by)
    present = study.data[group_by].astype(str).str.strip()
    seen = set(present) - {""}
    if mapping:
        levels = [mapping[code] for code in mapping if code in seen]
        unknown = sorted(seen - set(mapping))
        if unknown:
            core.warn(
                f"'{group_by}' holds {len(unknown)} value(s) that are not in the codebook "
                f"({', '.join(unknown)}); they are shown as their raw codes."
            )
            levels += unknown
        return levels
    return sorted(seen)


def group_masks(study, group_by: str) -> dict:
    """{column heading: True/False column}. `overall` is everybody."""
    pd = core._pandas()
    values = study.data[group_by].astype(str).str.strip()
    mapping = core.labels(study, group_by)
    reverse = {label: code for code, label in mapping.items()}
    masks = {}
    for level in group_levels(study, group_by):
        code = reverse.get(level, level)
        masks[level] = values == code
    blank = int((values == "").sum())
    if blank:
        core.warn(
            f"{blank} record(s) have no value for the grouping variable '{group_by}'. "
            "They are counted in the overall column and in no group column."
        )
    masks["overall"] = pd.Series([True] * len(study.data), index=study.data.index)
    return masks


# --------------------------------------------------------------------------
# The table
# --------------------------------------------------------------------------

def table1(study, group_by, variables, p_values: bool = False,
           continuous_test: str = "welch", seed: int = DEFAULT_SEED):
    """Build a Table 1.

    study            a Study from core.load_study (run core.apply_missing first)
    group_by         the field to compare across — REQUIRED, no default
    variables        the fields to summarise, in the order you want them shown.
                     A list of field names, or {field: "continuous"|"categorical"}
                     when you want to overrule what the codebook implies.
    p_values         add a p-value column (off by default: a p-value nobody asked
                     for is a p-value nobody chose the test for)
    continuous_test  "welch" (default) or "mannwhitney"
    seed             fixes the one randomised test, so the table is reproducible

    Returns a pandas DataFrame. Which test produced each p-value is recorded in
    `result.attrs["p_value_tests"]` and printed when the table is built.
    """
    pd = core._pandas()
    if not group_by:
        raise ValueError(
            "A Table 1 needs a grouping variable — the thing the columns compare.\n"
            "Pass the field name, for example table1(study, 'redcap_data_access_group', …)."
        )
    if group_by not in study.data.columns:
        raise ValueError(
            f"'{group_by}' is not a column in this export, so the table cannot be grouped "
            f"by it. The export has: {', '.join(list(study.data.columns)[:12])}…"
        )

    kinds = dict(variables) if isinstance(variables, dict) else {}
    names = list(variables)
    masks = group_masks(study, group_by)
    columns = list(masks)                       # group levels, then "overall"

    rows = []
    tests_used = {}

    def add(variable, level, statistic, values, p=None):
        rows.append({"variable": variable, "level": level, "statistic": statistic,
                     **{c: values.get(c) for c in columns}, "p_value": p})

    # How many records are in each column. Everything below is read against this.
    add("records", "", "n", {c: int(masks[c].sum()) for c in columns})

    for field in names:
        kind = kinds.get(field) or variable_kind(study, field)
        if kind not in ("continuous", "categorical"):
            core.warn(
                f"'{field}' is not something this table knows how to summarise "
                f"(REDCap type '{core.field_type(study, field)}'). It was left out. If it is "
                "a number, pass it as {'" + field + "': 'continuous'}."
            )
            continue
        applies = core.applicable(study, field)
        first_row = len(rows)
        if kind == "continuous":
            p, test = _continuous_rows(study, field, masks, columns, applies, add,
                                       p_values, continuous_test)
        else:
            p, test = _categorical_rows(study, field, masks, columns, applies, add,
                                        p_values, seed)
        # One variable, one test, one p-value — put it on the variable's first row
        # rather than repeating it down every level, where it would read as though
        # each level had been tested separately.
        if p is not None and len(rows) > first_row:
            rows[first_row]["p_value"] = p
        if test:
            tests_used[field] = test

    order = ["variable", "level", "statistic"] + columns
    if p_values:
        order.append("p_value")
    # Built column by column with dtype=object so a count stays an int and a
    # percentage stays a two-decimal float in the same column — pandas would
    # otherwise turn every 44 into 44.0.
    table = pd.DataFrame({name: pd.Series([r.get(name) for r in rows], dtype=object)
                          for name in order})
    table.attrs["p_value_tests"] = tests_used
    table.attrs["group_by"] = group_by
    if p_values and tests_used:
        print("p-values: " + "; ".join(f"{f} — {t}" for f, t in tests_used.items()))
    return table


def _values_for(study, field, mask, applies):
    """The usable values of `field` for the records in this column, as strings."""
    keep = mask & applies & core.usable(study, field)
    return study.data.loc[keep, field].astype(str).str.strip().tolist()


def _continuous_rows(study, field, masks, columns, applies, add,
                     p_values, continuous_test):
    numbers, counted, missing = {}, {}, {}
    for c in columns:
        raw = _values_for(study, field, masks[c], applies)
        vals = []
        for v in raw:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
        if len(vals) != len(raw):
            core.warn(f"{len(raw) - len(vals)} value(s) of '{field}' are not numbers and "
                      "were counted as missing.")
        numbers[c] = vals
        counted[c] = len(vals)
        missing[c] = int((masks[c] & applies).sum()) - len(vals)

    add(field, "", "n", counted)
    add(field, "", "missing", missing)
    add(field, "", "mean", {c: _round(_mean(numbers[c])) for c in columns})
    add(field, "", "sd", {c: _round(_sd(numbers[c])) for c in columns})
    add(field, "", "median", {c: _round(_quantile(numbers[c], 0.5)) for c in columns})
    add(field, "", "q1", {c: _round(_quantile(numbers[c], 0.25)) for c in columns})
    add(field, "", "q3", {c: _round(_quantile(numbers[c], 0.75)) for c in columns})

    if not p_values:
        return None, None
    groups = [numbers[c] for c in columns if c != "overall"]
    return _continuous_p(groups, continuous_test)


def _categorical_rows(study, field, masks, columns, applies, add, p_values, seed):
    mapping = core.labels(study, field)
    if not mapping:
        core.warn(f"'{field}' has no choice list in the codebook, so it has no levels to "
                  "count. It was left out of the table.")
        return None, None
    checkbox = core.field_type(study, field) == "checkbox"
    usable_mask = core.usable(study, field)

    # The denominator every percentage is out of: asked, and answered.
    answered = {c: int((masks[c] & applies & usable_mask).sum()) for c in columns}
    counts = {}
    for code in mapping:
        if checkbox:
            column = f"{field}___{code}"
            ticked = (study.data[column].astype(str).str.strip() == "1"
                      if column in study.data.columns
                      else core._pandas().Series([False] * len(study.data),
                                                 index=study.data.index))
            counts[code] = {c: int((masks[c] & applies & ticked).sum()) for c in columns}
        else:
            values = study.data[field].astype(str).str.strip()
            counts[code] = {c: int((masks[c] & applies & usable_mask & (values == code)).sum())
                            for c in columns}

    for code, label in mapping.items():
        add(field, label, "n", counts[code])
        add(field, label, "pct",
            {c: (_round(100.0 * counts[code][c] / answered[c]) if answered[c] else None)
             for c in columns})
    add(field, "", "missing",
        {c: int((masks[c] & applies).sum()) - answered[c] for c in columns})

    if not p_values:
        return None, None
    table = [[counts[code][c] for code in mapping]
             for c in columns if c != "overall"]
    return _categorical_p(table, seed)


# --------------------------------------------------------------------------
# Statistics, in stdlib arithmetic
# --------------------------------------------------------------------------

def _mean(values):
    return sum(values) / len(values) if values else None


def _sd(values):
    """Sample standard deviation, n-1 denominator.

    Stated because it is the single commonest cause of a third-decimal
    disagreement between languages: R's sd() and Stata's summarize use n-1,
    numpy's std() defaults to n.
    """
    n = len(values)
    if n < 2:
        return None
    m = sum(values) / n
    return math.sqrt(sum((x - m) ** 2 for x in values) / (n - 1))


def _quantile(values, p):
    """Quantile by linear interpolation — R's type 7, pandas' default.

    Named because there are nine defensible definitions and a median is the one
    number a reader will re-derive by hand.
    """
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    h = (len(s) - 1) * p
    lo = math.floor(h)
    hi = math.ceil(h)
    return s[lo] + (h - lo) * (s[hi] - s[lo])


# ---- distributions (no scipy: this must run on a laptop with pandas only) ----

def _gammq(a, x):
    """Regularised upper incomplete gamma Q(a, x) — Numerical Recipes, §6.2."""
    if x < 0 or a <= 0:
        raise ValueError("bad arguments to the gamma function")
    if x == 0:
        return 1.0
    if x < a + 1.0:                                   # series
        ap, total, delta = a, 1.0 / a, 1.0 / a
        for _ in range(500):
            ap += 1
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * 1e-14:
                break
        return 1.0 - total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    b, c = x + 1.0 - a, 1e300                         # continued fraction
    d = 1.0 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-300:
            d = 1e-300
        c = b + an / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h * math.exp(-x + a * math.log(x) - math.lgamma(a))


def chi_square_p(statistic, df):
    """P(chi-square with `df` degrees of freedom >= statistic)."""
    if df <= 0 or statistic <= 0:
        return 1.0
    return _gammq(df / 2.0, statistic / 2.0)


def _betacf(a, b, x):
    """Continued fraction for the incomplete beta function — Numerical Recipes §6.4."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h


def _betai(a, b, x):
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_p(t, df):
    """Two-sided p-value for a t statistic."""
    if df <= 0 or not math.isfinite(t):
        return None
    return _betai(df / 2.0, 0.5, df / (df + t * t))


def normal_p(z):
    """Two-sided p-value for a z statistic."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def welch_t(a, b):
    """Welch's unequal-variance t test. Returns (t, df, p)."""
    if len(a) < 2 or len(b) < 2:
        return None, None, None
    ma, mb = _mean(a), _mean(b)
    va, vb = _sd(a) ** 2 / len(a), _sd(b) ** 2 / len(b)
    if va + vb == 0:
        return None, None, None
    t = (ma - mb) / math.sqrt(va + vb)
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    return t, df, student_t_p(t, df)


def mann_whitney(a, b):
    """Mann-Whitney U, normal approximation with tie and continuity correction."""
    if not a or not b:
        return None, None
    combined = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks, i = [0.0] * len(combined), 0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        average = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = average
        i = j + 1
    ra = sum(r for r, (_, g) in zip(ranks, combined) if g == 0)
    na, nb = len(a), len(b)
    u = ra - na * (na + 1) / 2.0
    mu = na * nb / 2.0
    counts, i = [], 0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        counts.append(j - i + 1)
        i = j + 1
    n = na + nb
    ties = sum(c ** 3 - c for c in counts)
    var = na * nb / 12.0 * ((n + 1) - ties / float(n * (n - 1)))
    if var <= 0:
        return u, None
    z = (abs(u - mu) - 0.5) / math.sqrt(var)
    return u, normal_p(z)


def _chi_square_statistic(table):
    """(statistic, df, expected) for a table of counts, rows = groups."""
    rows = [sum(r) for r in table]
    cols = [sum(c) for c in zip(*table)]
    total = sum(rows)
    if total == 0:
        return None, None, None
    expected = [[r * c / total for c in cols] for r in rows]
    stat = 0.0
    for observed_row, expected_row in zip(table, expected):
        for o, e in zip(observed_row, expected_row):
            if e > 0:
                stat += (o - e) ** 2 / e
    df = (len([r for r in rows if r > 0]) - 1) * (len([c for c in cols if c > 0]) - 1)
    return stat, df, expected


def fisher_exact_2x2(table):
    """Two-sided Fisher's exact test for a 2x2 table of counts."""
    (a, b), (c, d) = table
    row1, row2 = a + b, c + d
    col1 = a + c
    total = row1 + row2
    if total == 0 or row1 == 0 or row2 == 0 or col1 == 0 or col1 == total:
        return 1.0

    def probability(x):
        return (math.comb(row1, x) * math.comb(row2, col1 - x)) / math.comb(total, col1)

    observed = probability(a)
    low = max(0, col1 - row2)
    high = min(row1, col1)
    return min(1.0, sum(probability(x) for x in range(low, high + 1)
                        if probability(x) <= observed * (1 + 1e-9)))


def _monte_carlo_chi_square(table, seed, draws=MONTE_CARLO_DRAWS):
    """Chi-square p by shuffling group labels — for sparse tables, seeded.

    Used where the chi-square approximation is not trustworthy (an expected
    count below 5) and the table is bigger than 2x2, so Fisher's exact test is
    not available. `seed` fixes it, so the same data always gives the same p.
    """
    observed, _, _ = _chi_square_statistic(table)
    if observed is None:
        return None
    labels, values = [], []
    for group_index, row in enumerate(table):
        for level_index, count in enumerate(row):
            labels += [group_index] * count
            values += [level_index] * count
    if not labels:
        return None
    rng = random.Random(seed)
    n_groups, n_levels = len(table), len(table[0])
    hits = 0
    for _ in range(draws):
        rng.shuffle(labels)
        simulated = [[0] * n_levels for _ in range(n_groups)]
        for g, v in zip(labels, values):
            simulated[g][v] += 1
        stat, _, _ = _chi_square_statistic(simulated)
        if stat is not None and stat >= observed - 1e-12:
            hits += 1
    return (1.0 + hits) / (draws + 1.0)


def _categorical_p(table, seed):
    """A p-value for a counts table, and the name of the test that produced it."""
    table = [row for row in table if sum(row) > 0]
    if len(table) < 2:
        core.warn("a p-value needs at least two groups with records in them.")
        return None, None
    keep = [i for i, column in enumerate(zip(*table)) if sum(column) > 0]
    table = [[row[i] for i in keep] for row in table]
    if len(keep) < 2:
        return None, None
    stat, df, expected = _chi_square_statistic(table)
    sparse = any(e < 5 for row in expected for e in row)
    if sparse and len(table) == 2 and len(table[0]) == 2:
        return _round4(fisher_exact_2x2(table)), "Fisher's exact test"
    if sparse:
        return (_round4(_monte_carlo_chi_square(table, seed)),
                f"chi-square, p by {MONTE_CARLO_DRAWS} seeded simulations (seed {seed})")
    return _round4(chi_square_p(stat, df)), "chi-square test"


def _continuous_p(groups, which):
    groups = [g for g in groups if g]
    if len(groups) != 2:
        core.warn("p-values for a continuous variable compare two groups; this grouping has "
                  f"{len(groups)}, so the p-value column was left blank for it. Compare two "
                  "groups at a time.")
        return None, None
    a, b = groups
    if which == "mannwhitney":
        _, p = mann_whitney(a, b)
        return _round4(p), "Mann-Whitney U test"
    _, _, p = welch_t(a, b)
    return _round4(p), "Welch's t test"


def _round4(p):
    """p-values keep four places — two would print every small p as 0.0."""
    return None if p is None else float(format(float(p), ".4f"))


def _main() -> int:
    print(__doc__.strip())
    print("\nThis file is part of the ARGO analysis library. It is not run on its own —")
    print("an analysis script imports it. See the run-analysis skill for how to start one.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
