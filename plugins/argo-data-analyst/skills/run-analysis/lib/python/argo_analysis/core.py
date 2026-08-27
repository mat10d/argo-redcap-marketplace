#!/usr/bin/env python3
"""argo_analysis.core — the study, its codebook, and the rules that make a
number honest.

Everything else in this library goes through here, because the same three
questions decide whether a Table 1 is right or quietly wrong:

  1. **What is missing?**  REDCap stores "missing with a reason" as ordinary
     values (-666, -777, -888, -999, and the older 666). Left alone they are
     read as ages, scores and grades, and they poison every mean silently.
     `apply_missing` clears them everywhere; every statistic in this library
     also refuses to count them, so a script that forgets the step still gets
     the right answer.
  2. **What do the codes mean?**  `labels` reads the choice list out of the
     data dictionary, so levels come out in *codebook* order — the order the
     questionnaire asks them in — and a level nobody happened to tick still
     shows up, as a zero, instead of vanishing.
  3. **Who was even asked?**  A field behind branching logic was never shown
     to most participants. Counting those people in the denominator is the
     most common way a real Table 1 misleads: pregnancy status asked of the
     111 women in a 200-person cohort is 111 people's data, not 200's.
     `applicable` and `denominator` answer that question per field.

Nothing here talks to REDCap or to the network. It reads two CSV files: the
record export (raw codes) and the data dictionary.

    from argo_analysis import core
    study = core.apply_missing(core.load_study("records.csv", "datadictionary.csv"))
    core.denominator(study, "pregnancy_status")      # 111, not 200
"""

from __future__ import annotations

import importlib
import re
import sys
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Constants that every language port must agree on
# --------------------------------------------------------------------------

#: REDCap missing-data codes. Values, as far as the file is concerned; missing,
#: as far as any analysis is concerned. 666 is the legacy spelling and is kept
#: because older ARGO studies still carry it.
MDC_CODES = frozenset({"-666", "-777", "-888", "-999", "666"})

#: Every non-count statistic in this library is rounded here. Two places, once,
#: in one constant, so Python and R cannot drift apart by a decimal.
DECIMALS = 2

#: The 18 columns of a REDCap data dictionary, in REDCap's own order.
DD_COLUMNS = [
    "field_name", "form_name", "section_header", "field_type", "field_label",
    "select_choices_or_calculations", "field_note",
    "text_validation_type_or_show_slider_number", "text_validation_min",
    "text_validation_max", "identifier", "branching_logic", "required_field",
    "custom_alignment", "question_number", "matrix_group_name",
    "matrix_ranking", "field_annotation",
]

# The website's "Download Data Dictionary" button writes human headings; the API
# writes the machine names above. Both are normal things for a user to hand us,
# so both are accepted and immediately normalised to one shape.
_WEBSITE_TO_API = {
    "Variable / Field Name": "field_name",
    "Form Name": "form_name",
    "Section Header": "section_header",
    "Field Type": "field_type",
    "Field Label": "field_label",
    "Choices, Calculations, OR Slider Labels": "select_choices_or_calculations",
    "Field Note": "field_note",
    "Text Validation Type OR Show Slider Number":
        "text_validation_type_or_show_slider_number",
    "Text Validation Min": "text_validation_min",
    "Text Validation Max": "text_validation_max",
    "Identifier?": "identifier",
    "Branching Logic (Show field only if...)": "branching_logic",
    "Required Field?": "required_field",
    "Custom Alignment": "custom_alignment",
    "Question Number (surveys only)": "question_number",
    "Matrix Group Name": "matrix_group_name",
    "Matrix Ranking?": "matrix_ranking",
    "Field Annotation": "field_annotation",
}

#: The column REDCap uses for the site / data access group, when a study has one.
SITE_FIELD = "redcap_data_access_group"

#: Field types that carry a choice list, i.e. that are categorical by construction.
CHOICE_TYPES = ("radio", "dropdown", "checkbox", "yesno", "truefalse")

#: Text-validation types that make a free-text field a number we may average.
NUMERIC_VALIDATIONS = ("integer", "number", "number_1dp", "number_2dp",
                       "number_3dp", "number_4dp")


# --------------------------------------------------------------------------
# Optional add-ons, asked for in words the user can act on
# --------------------------------------------------------------------------

class MissingToolkit(RuntimeError):
    """An add-on this step needs is not installed. The message says how to get it."""


def require(module_name: str, pip_name: str, purpose: str):
    """Import an optional add-on, or explain — in one plain sentence and one
    copyable command — how to install it.

    Imported here rather than at the top of the file on purpose: a laptop with
    nothing installed must still be able to *open* this library, read its help
    and run the parts that need nothing. Only the step that actually needs
    pandas should be the step that complains about pandas.
    """
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:                       # pragma: no cover - env specific
        raise MissingToolkit(
            f"This step needs {pip_name}, a free add-on for Python that {purpose}.\n"
            f"It is not installed on this computer yet. Open a terminal window, type\n"
            f"the line below, press Enter, wait for it to finish, then run this again:\n\n"
            f"    python3 -m pip install {pip_name}\n"
        ) from exc


def _pandas():
    return require("pandas", "pandas", "reads spreadsheets and does the arithmetic")


# --------------------------------------------------------------------------
# Things we could not read, said out loud
# --------------------------------------------------------------------------

#: Branching conditions this run could not understand. Reported the first time
#: each one is seen, and kept here so a workbook's Notes sheet can list them.
UNPARSEABLE_LOGIC: list = []

#: Everything this run warned about, in order, for the record.
WARNINGS: list = []

_SAID = set()


def warn(message: str) -> None:
    """Say something once, to the screen, and remember it.

    Silence is the failure mode this library is most afraid of: a condition we
    could not read, a variable we could not summarise, a group column that was
    blank. Each of those changes a number, so each of them gets said.
    """
    WARNINGS.append(message)
    if message in _SAID:
        return
    _SAID.add(message)
    print(f"WARNING: {message}", file=sys.stderr)


def reset_warnings() -> None:
    """Forget what has been warned about (used by tests, and between studies)."""
    UNPARSEABLE_LOGIC.clear()
    WARNINGS.clear()
    _SAID.clear()


# --------------------------------------------------------------------------
# The study
# --------------------------------------------------------------------------

@dataclass
class Study:
    """One study's export and its codebook, held together.

    data      one row per record, raw REDCap codes, everything a string
    dd        the data dictionary, normalised to the 18 API column names
    id_field  the record identifier — the data dictionary's first field
    sites     "redcap_data_access_group" if the export has one, else None
    """

    data: "object"
    dd: "object"
    id_field: str
    sites: "object" = None

    def __getitem__(self, key):
        """Dict-style access, so `study["data"]` reads the same in every language."""
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None

    def __len__(self):
        return len(self.data)


def load_study(export_csv, dictionary_csv) -> Study:
    """Read a record export and a data dictionary off disk.

    Both files stay exactly as REDCap wrote them — nothing is coerced to a
    number, nothing is renamed, blanks stay blank. Everything is read as text
    because REDCap codes are text ("01" is not 1) and because a column that is
    numeric today gets a "not assessed" typed into it tomorrow.
    """
    pd = _pandas()
    data = pd.read_csv(export_csv, dtype=str, keep_default_na=False)
    dd = pd.read_csv(dictionary_csv, dtype=str, keep_default_na=False)

    if "field_name" not in dd.columns:
        dd = dd.rename(columns=_WEBSITE_TO_API)
    if "field_name" not in dd.columns:
        raise ValueError(
            f"{dictionary_csv} does not look like a REDCap data dictionary: it has no\n"
            "'Variable / Field Name' column (from the website) and no 'field_name'\n"
            "column (from the API). Download it again from Project Setup →\n"
            "Data Dictionary → Download the current Data Dictionary."
        )
    for column in DD_COLUMNS:                 # a short dictionary is still a dictionary
        if column not in dd.columns:
            dd[column] = ""
    dd = dd[DD_COLUMNS + [c for c in dd.columns if c not in DD_COLUMNS]]

    if dd.empty:
        raise ValueError(f"{dictionary_csv} has no fields in it.")

    return Study(
        data=data,
        dd=dd,
        id_field=str(dd.iloc[0]["field_name"]).strip(),
        sites=SITE_FIELD if SITE_FIELD in data.columns else None,
    )


def apply_missing(study: Study) -> Study:
    """Turn every missing-data code into a blank, in every field.

    Returns a new Study; the one passed in is left alone, so a script can show
    "before and after" if it wants to. Running it twice changes nothing.

    This is deliberately blunt — ALL fields, not a chosen few — because the
    codes mean the same thing wherever they appear, and because a list of
    "fields that use MDC" is exactly the kind of thing that goes out of date.
    """
    data = study.data.copy()
    for column in data.columns:
        stripped = data[column].astype(str).str.strip()
        data[column] = stripped.mask(stripped.isin(MDC_CODES), "")
    return Study(data=data, dd=study.dd, id_field=study.id_field, sites=study.sites)


# --------------------------------------------------------------------------
# The codebook
# --------------------------------------------------------------------------

def meta(study: Study, field: str) -> dict:
    """The data dictionary row for a field, as a plain dict ({} if unknown).

    A checkbox column in an export is `symptoms___3`; its codebook entry is
    `symptoms`. Look-ups follow that automatically.
    """
    base = field.split("___")[0]
    rows = study.dd[study.dd["field_name"].astype(str).str.strip() == base]
    if rows.empty:
        return {}
    return {k: ("" if v is None else str(v)) for k, v in rows.iloc[0].to_dict().items()}


def field_type(study: Study, field: str) -> str:
    """A field's REDCap type ("radio", "text", …), or "" if it is not in the codebook."""
    return meta(study, field).get("field_type", "").strip()


def field_label(study: Study, field: str) -> str:
    """A field's question wording, tidied of stray whitespace and trailing punctuation.

    Falls back to the field name, so a chart of a column that is not in the
    codebook (the site column, typically) still gets a title.
    """
    label = meta(study, field).get("field_label", "").strip()
    if not label:
        return field
    return re.sub(r"\s+", " ", label).strip().rstrip(" ?.:;")


def labels(study: Study, field: str) -> dict:
    """{code: label} for a field, in codebook order.

    Yes/no and true/false fields carry no choice list in the dictionary — REDCap
    knows what they mean — so they get the map REDCap uses. Forgetting that is
    what produces a Table 1 with an empty row where "Ever used tobacco?" should be.

    Missing-data codes offered as choices (so an RA can record *why* a value is
    absent) are NOT levels of the variable and are left out here; they are
    counted as missing instead.
    """
    entry = meta(study, field)
    ftype = entry.get("field_type", "").strip()
    if ftype == "yesno":
        return {"0": "No", "1": "Yes"}
    if ftype == "truefalse":
        return {"0": "False", "1": "True"}
    raw = entry.get("select_choices_or_calculations", "")
    if ftype not in ("radio", "dropdown", "checkbox") or not raw.strip():
        return {}
    out = {}
    for chunk in raw.split("|"):
        if "," not in chunk:
            continue
        code, label = chunk.split(",", 1)
        code = code.strip()
        if code in MDC_CODES:
            continue
        out[code] = re.sub(r"\s+", " ", label).strip()
    return out


# --------------------------------------------------------------------------
# Branching logic: who was actually asked
# --------------------------------------------------------------------------

# One clause pattern, used everywhere. It must accept everything REDCap's
# Designer actually emits, which is broader than it first appears:
#   [field] = 'value'     quoted, the form most documentation shows
#   [field] = 1           UNQUOTED — what REDCap writes for numeric codes, and by
#                         far the most common form in practice. A stricter
#                         pattern that demanded quotes silently dropped 28% of
#                         branching fields on one live cohort and 70% on another.
#   [field(2)] = 1        a single checkbox option
#   [age] >= 18           numeric comparison
_CLAUSE_RE = re.compile(
    r"""\s*\[([a-zA-Z0-9_]+)(?:\((-?\w+)\))?\]\s*"""
    r"""(<=|>=|<>|!=|=|<|>)\s*"""
    r"""(?:'([^']*)'|"([^"]*)"|([^\s'"]+))\s*"""
)


def _clause_parts(clause: str):
    """(field, choice_code, operator, value) for one clause, or None if unreadable."""
    m = _CLAUSE_RE.fullmatch(clause)
    if not m:
        return None
    field, choice, op = m.group(1), m.group(2), m.group(3)
    value = next(g for g in (m.group(4), m.group(5), m.group(6)) if g is not None)
    return field, choice, op, value


def _clause_column(field: str, choice) -> str:
    """The export column a clause is about. `[symptoms(3)]` lives in `symptoms___3`."""
    if not choice:
        return field
    suffix = f"____{choice[1:]}" if choice.startswith("-") else f"___{choice}"
    return f"{field}{suffix}"


def _clause_results(clause: str, data) -> list:
    """One tri-state answer per record: True, False, or None for "cannot say".

    Evaluated a column at a time rather than a row at a time — same answers,
    but the regular expression runs once per condition instead of once per
    participant, which matters on a 40 000-record export.
    """
    parts = _clause_parts(clause)
    n = len(data)
    if parts is None:
        return [None] * n
    field, choice, op, val = parts
    column = _clause_column(field, choice)
    if column in data.columns:
        actual = data[column].astype(str).str.strip().tolist()
    else:
        actual = [""] * n                     # a condition about a field we were not sent

    if op in ("=", "<>", "!="):
        target = str(val).strip()
        if op == "=":
            return [a == target for a in actual]
        return [a != target for a in actual]

    try:
        right = float(str(val).strip())
    except (TypeError, ValueError):
        return [None] * n                     # comparing against something non-numeric

    out = []
    for a in actual:
        # A BLANK fails the comparison, and that is a definite answer, not an
        # unknown one: REDCap evaluates `[x] >= 1` with x empty as false and
        # hides the field, so we match it. Calling blanks "uncertain" instead
        # would flood every worklist and every denominator with false doubt.
        if a == "":
            out.append(False)
            continue
        try:
            left = float(a)
        except (TypeError, ValueError):
            out.append(None)                  # a genuinely non-numeric value
            continue
        out.append({"<": left < right, ">": left > right,
                    "<=": left <= right, ">=": left >= right}[op])
    return out


def evaluate_branching(logic: str, data) -> tuple:
    """(applies, certain) for every record, as two lists of True/False.

    `certain` is False for a record whose condition we could not fully read. In
    that case the field is reported as APPLYING — never silently drop a field
    because we could not read its condition, which is precisely the failure this
    grammar replaced — and the condition is warned about by name.

    Supported grammar: `[f]='v'`, `[f]=v` unquoted, `[f(n)]` checkbox options,
    AND / OR, and = != <> < > <= >=. Anything richer (a datediff, a nested
    calculation) is unreadable, and unreadable means "counts everyone".
    """
    n = len(data)
    if not logic or not str(logic).strip():
        return [True] * n, [True] * n

    or_parts = [
        [_clause_results(clause, data)
         for clause in re.split(r"\s+AND\s+", or_part, flags=re.IGNORECASE)]
        for or_part in re.split(r"\s+OR\s+", str(logic), flags=re.IGNORECASE)
    ]

    applies, certain = [], []
    for i in range(n):
        any_unparseable = False
        decided = False
        for branch_clauses in or_parts:
            branch, branch_unparseable = True, False
            for clause_results in branch_clauses:
                result = clause_results[i]
                if result is None:
                    branch_unparseable = any_unparseable = True
                    continue              # unknown — it decides nothing either way
                if not result:
                    branch = False
                    break
            if branch and not branch_unparseable:
                applies.append(True); certain.append(True); decided = True
                break                     # this branch is satisfied outright
        if decided:
            continue
        if any_unparseable:
            applies.append(True); certain.append(False)
        else:
            applies.append(False); certain.append(True)
    return applies, certain


def applicable(study: Study, field: str):
    """Did this field's branching logic fire, for each record? (a True/False column)

    A field with no branching logic applies to everyone. A field we could not
    read the condition of applies to everyone too, loudly: the condition is
    printed and kept in `UNPARSEABLE_LOGIC` so it can be listed on the Notes
    sheet of whatever this analysis produces.
    """
    pd = _pandas()
    logic = meta(study, field).get("branching_logic", "")
    applies, certain = evaluate_branching(logic, study.data)
    if not all(certain):
        condition = str(logic).strip()
        if condition not in UNPARSEABLE_LOGIC:
            UNPARSEABLE_LOGIC.append(condition)
        warn(
            f"the condition controlling '{field}' could not be read, so every record is "
            f"counted as having been asked it (nothing was dropped). The condition was:\n"
            f"    {condition}\n"
            f"Check by hand whether that is the denominator you want."
        )
    return pd.Series(applies, index=study.data.index, name=field)


def denominator(study: Study, field: str) -> int:
    """How many records this field was actually asked of.

    This is the number a percentage should be out of. Pregnancy status behind
    `[sex] = '2'` in a 200-person cohort has a denominator of 111, and quoting
    it out of 200 is not a rounding difference — it is a different claim.
    """
    return int(sum(bool(x) for x in applicable(study, field)))


def usable(study: Study, field: str):
    """Which records have a value we may compute on: present, and not a missing code.

    Checkbox fields are asked about as a whole (`symptoms`): a record counts as
    having answered if any of its option columns carries a 0 or a 1.
    """
    pd = _pandas()
    data = study.data
    if field_type(study, field) == "checkbox" and field not in data.columns:
        columns = [c for c in data.columns if c.startswith(f"{field}___")]
        if not columns:
            return pd.Series([False] * len(data), index=data.index, name=field)
        answered = None
        for column in columns:
            here = data[column].astype(str).str.strip() != ""
            answered = here if answered is None else (answered | here)
        return answered.rename(field)
    if field not in data.columns:
        warn(f"'{field}' is not a column in this export, so it has no values to summarise.")
        return pd.Series([False] * len(data), index=data.index, name=field)
    values = data[field].astype(str).str.strip()
    return (~values.isin(MDC_CODES) & (values != "")).rename(field)


def _main() -> int:
    print(__doc__.strip())
    print("\nThis file is part of the ARGO analysis library. It is not run on its own —")
    print("an analysis script imports it. See the run-analysis skill for how to start one.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
