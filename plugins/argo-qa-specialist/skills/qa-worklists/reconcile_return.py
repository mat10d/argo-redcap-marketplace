"""Check REDCap itself against what an RA sent back. Reads only — never writes.

The RA's returned worklist is a claim: "I entered this". This script checks the claim against
what REDCap holds NOW, cell by cell, for every cell the worklist flagged and the RA answered:

  IN REDCAP    REDCap holds the RA's answer (codes and labels, dates and checkboxes compared
               the way REDCap stores them). Nothing to do.
  NOT ENTERED  REDCap still shows what it showed when the worklist went out — the RA wrote
               the answer in the spreadsheet only. Ask them to enter it in REDCap.
  DIFFERS      REDCap holds something else. A question for the RA; never settled by us.
  UNCLEAR      We can't read the RA's answer (not one of the field's choices, a date we can't
               parse) or can't match the column to a field. A question for the RA.

Rows the RA marked with a note but no cell change (often "RESOLVED") are checked the same way:
each flagged cell on that row is either in REDCap now, or still blank.

Field comments (REDCap's Field Comment Log) are shown beside the cells they belong to. They are
evidence, never values: a blank cell with a comment explaining it stays blank until the QA
specialist decides what to do with it. Two more checks read them (rules in field_comments.py),
for the records on this worklist:
  - a blank cell whose comment looks like the value itself -> "value may be in the comment —
    enter it in the field" (a question for the RA);
  - a filled cell whose comment clearly says the opposite ("not done", "declined") -> "comment
    and value may disagree — check" (for you to look at).
Blue cells (a comment had already explained the blank) the RA left alone are not counted as
untouched — nothing was asked there.

Where REDCap's current state comes from — one of:
  --token-env CRC_TOKEN                          the study's access key (pulls directly)
  --records-csv export.csv --metadata-csv dd.csv  a Data Export (raw) + Data Dictionary
                                                  downloaded AFTER the RA's return

Field comments, optional:
  --comments field_comment_log.csv   Applications -> Field Comment Log -> download (CSV)
  With an access key and no file, the comments are read from the project's logging if the key
  is allowed to; otherwise this is skipped and the report says how to include them.

Usage:
  python3 reconcile_return.py <original.xlsx> <returned.xlsx> \\
      --records-csv export.csv --metadata-csv dd.csv \\
      [--comments field_comment_log.csv] [--site "Site Alpha"] [--out report.md]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

# Same-folder imports, always: this skill carries its own copy of everything it needs.
_here = Path(__file__).resolve().parent
sys.path.insert(0, str(_here))
for _cand in (_here / "scripts",
              *(p / "plugins/argo-core/skills/redcap-api/scripts" for p in _here.parents)):
    if (_cand / "argo_redcap_client.py").exists():
        sys.path.insert(0, str(_cand))
        break

# The workbooks are read exactly once, by the same code the audit uses. A second reader is how
# two tools end up disagreeing about which cells the RA answered.
from review_responses import diff  # noqa: E402
# Field comments are read, indexed and judged in ONE place, shared with build_worklists.py; the
# names below stay importable from here (upload_mdc.py and the tests use them).
from field_comments import (  # noqa: E402,F401
    BUILTIN_CHOICES, FIELD_COMMENT_HEADERS, FIELD_COMMENT_REQUIRED, Comment, _norm, _read_csv,
    choices_for, comment_text, comments_from_logging, comments_through_key, disagrees_with_value,
    index_comments, parse_choices, read_comment_log, validation, value_in_comment,
    DISAGREES, VALUE_IN_COMMENT,
)

IN_REDCAP = "IN REDCAP"
NOT_ENTERED = "NOT ENTERED"
DIFFERS = "DIFFERS"
UNCLEAR = "UNCLEAR"
STATUSES = (IN_REDCAP, NOT_ENTERED, DIFFERS, UNCLEAR)

# Missing data codes, from argo-core's mdc-rules.md (the single source of their meaning).
MDC_MEANINGS = {
    "-666": "Patient does not know",
    "-777": "Patient refused to answer",
    "-888": "Missing in case notes",
    "-999": "Other missing",
}
# Date fields carry the same four codes in date form. REDCap shows DD-MM-YYYY on the form; the
# API stores and imports YYYY-MM-DD (mdc-rules.md, redcap-date-import.md).
MDC_DATE_IMPORT = {"-666": "6666-06-06", "-777": "7777-07-07",
                   "-888": "8888-08-08", "-999": "9999-09-09"}
MDC_FROM_DATE = {v: k for k, v in MDC_DATE_IMPORT.items()}

# What an RA types in a cell to say "I entered it in REDCap" instead of retyping the value.
FILLED_MARKERS = {"filled", "done", "entered", "updated", "resolved", "corrected", "fixed",
                  "filled in redcap", "entered in redcap", "updated in redcap"}
# Words in a RESPONSE note that claim the row was dealt with in REDCap.
RESOLVED_NOTE_WORDS = ("resolv", "filled", "entered", "updated", "corrected", "fixed", "done")

CHOICE_TYPES = ("radio", "dropdown", "yesno", "truefalse")

class Check(NamedTuple):
    """One cell checked against REDCap."""
    record: str
    header: str            # the worklist column heading
    field: str             # the REDCap field name ("" if the column couldn't be matched)
    ra_wrote: str          # "" for a RESOLVED-note row the RA left blank
    redcap_now: str        # what REDCap holds, as a person reads it
    status: str
    why: str = ""          # plain reason, mainly for UNCLEAR
    kind: str = "yellow"   # "amber" = we couldn't read the field's condition
    from_note: bool = False
    mdc: str = ""          # the RA's answer is this missing-data code (e.g. "-888")


class Reconciliation(NamedTuple):
    site: str
    id_field: str
    checks: list           # [Check]
    still_blank_explained: list   # [Check] — noted rows, still blank, note isn't "resolved"
    notes: dict            # record -> RA note
    comments: dict         # (record, field) -> [Comment]
    flagged_fields: set    # {(record, field)}
    out_of_scope: list     # review_responses.OutOfScopeEdit
    untouched: int         # flagged cells with no answer and no note
    source: str
    comment_source: str
    held_back: tuple = ()  # [(Check, reason)] — RA-returned MDCs that need the RA's word first
    mdc_share_note: str = ""
    explained_left: int = 0     # blue cells (comment already explained the blank), not answered
    comment_flags: tuple = ()   # [CommentFlag] — value in the comment / comment disagrees


class CommentFlag(NamedTuple):
    """A field comment that needs a look (field_comments.value_in_comment / disagrees_with_value)."""
    record: str
    header: str            # the worklist heading if the field is on it, else the field's label
    field: str
    redcap_now: str        # "blank", or the value as a person reads it
    comment: str
    reason: str


# ---------------------------------------------------------------------------- reading REDCap

def is_date_field(meta: dict) -> bool:
    return meta.get("field_type") == "text" and validation(meta).startswith(("date", "datetime"))


def checkbox_code(col: str, base: str) -> str:
    """'sym___2' -> '2', 'sym____888' -> '-888' (REDCap writes a minus as an extra underscore)."""
    suf = col[len(base):]
    if suf.startswith("____"):
        return "-" + suf[4:]
    if suf.startswith("___"):
        return suf[3:]
    return ""


def checkbox_columns(base: str, columns) -> dict:
    """{code: column} for a checkbox field, from the columns REDCap actually exported."""
    return {checkbox_code(c, base): c for c in columns if c.startswith(f"{base}___")}


_DD_TO_META = {
    "Variable / Field Name": "field_name", "Form Name": "form_name", "Field Type": "field_type",
    "Field Label": "field_label", "Choices, Calculations, OR Slider Labels":
        "select_choices_or_calculations",
    "Text Validation Type OR Show Slider Number": "text_validation_type_or_show_slider_number",
    "Text Validation Min": "text_validation_min", "Text Validation Max": "text_validation_max",
    "Branching Logic (Show field only if...)": "branching_logic",
    "Field Annotation": "field_annotation", "Field Note": "field_note",
}


def load_metadata_file(path: str) -> list:
    """A Data Dictionary CSV — the API shape (field_name) or the Designer download (headings)."""
    rows, cols = _read_csv(path, "data dictionary")
    if "field_name" not in cols:
        rows = [{_DD_TO_META.get(k, k): v for k, v in r.items()} for r in rows]
    if not rows or "field_name" not in rows[0]:
        raise SystemExit(
            f"This doesn't look like a REDCap data dictionary:\n    {path}\n\n"
            "Download it from Designer -> Download Data Dictionary, and try again.")
    return rows


def load_from_files(records_csv: str, metadata_csv: str):
    rows, cols = _read_csv(records_csv, "records export")
    return rows, cols, load_metadata_file(metadata_csv)


def load_from_key(token_env: str):
    """(rows, columns, metadata, client) through the shared client. Raw codes, all records."""
    from argo_redcap_client import RedcapClient, RedcapError
    client = RedcapClient.from_env(token_env)
    if client is None:
        raise SystemExit(RedcapClient.explain_missing_token(
            token_env, "read the study's current data",
            fallback=("Nothing is blocked: download a fresh Data Export (raw) and the Data\n"
                      "Dictionary from the REDCap website, and use --records-csv and\n"
                      "--metadata-csv instead.")))
    try:
        metadata = client.export_metadata()
        text = client.export_records_csv(rawOrLabel="raw", exportCheckboxLabel="false",
                                         exportDataAccessGroups="true")
    except RedcapError as e:
        raise SystemExit(str(e))
    reader = csv.DictReader(io.StringIO(text))
    return list(reader), list(reader.fieldnames or []), metadata, client


# ---------------------------------------------------------------------------- values

def _date(text: str, meta: dict) -> "str | None":
    """Any reasonable date -> YYYY-MM-DD (plus ' HH:MM' for datetime fields), else None.

    DD/MM vs MM/DD is settled by the field's own validation type, never guessed.
    """
    s = text.strip()
    if s in MDC_FROM_DATE:
        return s
    for disp, imp in (("06-06-6666", "6666-06-06"), ("07-07-7777", "7777-07-07"),
                      ("08-08-8888", "8888-08-08"), ("09-09-9999", "9999-09-09")):
        if s == disp:
            return imp
    if s in MDC_DATE_IMPORT:            # "-888" typed into a date field: same code, date form
        return MDC_DATE_IMPORT[s]
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::\d{2})?)?$", s)
    if m:
        y, mo, d, hh, mm = m.groups()
        out = f"{y}-{int(mo):02d}-{int(d):02d}"
    else:
        m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?:\s+(\d{1,2}):(\d{2}))?$", s)
        if not m:
            return None
        a, b, y, hh, mm = m.groups()
        mdy = "mdy" in validation(meta)
        mo, d = (a, b) if mdy else (b, a)
        out = f"{y}-{int(mo):02d}-{int(d):02d}"
    try:
        dt.date.fromisoformat(out)
    except ValueError:
        if out not in MDC_FROM_DATE:
            return None
    if hh is not None and validation(meta).startswith("datetime") and not (hh == "0" * len(hh)
                                                                          and mm == "00"):
        out += f" {int(hh):02d}:{mm}"
    return out


def canon(text: str, meta: dict) -> "tuple[object | None, str]":
    """(the value as REDCap stores it, reason if unreadable). Checkboxes -> frozenset of codes."""
    s = str(text or "").strip()
    ftype = meta.get("field_type", "")
    if ftype == "checkbox":
        if not s:
            return frozenset(), ""
        choices = choices_for(meta)
        by_label = {_norm(v): k for k, v in choices.items()}
        if _norm(s) in by_label:                       # a label that itself contains a comma
            return frozenset([by_label[_norm(s)]]), ""
        codes = set()
        for part in s.split(","):
            p = part.strip()
            if not p:
                continue
            code = p if p in choices else by_label.get(_norm(p))
            if code is None:
                return None, f'"{p}" is not one of this field\'s options'
            codes.add(code)
        return frozenset(codes), ""
    if not s:
        return "", ""
    if re.fullmatch(r"-?\d+\.0+", s):
        s = s.split(".")[0]
    if ftype in CHOICE_TYPES:
        choices = choices_for(meta)
        if s in choices:
            return s, ""
        by_label = {_norm(v): k for k, v in choices.items()}
        if _norm(s) in by_label:
            return by_label[_norm(s)], ""
        return None, f'"{s}" is not one of this field\'s choices'
    if is_date_field(meta):
        d = _date(s, meta)
        return (d, "") if d else (None, f'"{s}" is not a date we can read')
    if validation(meta) in ("integer", "number", "number_1dp", "number_2dp") or \
            validation(meta).startswith("number"):
        try:
            return float(s), ""
        except ValueError:
            pass
    return _norm(s), ""


def current_value(row: dict, field: str, meta: dict, columns) -> object:
    if meta.get("field_type") == "checkbox":
        return frozenset(code for code, col in checkbox_columns(field, columns).items()
                         if str(row.get(col, "")).strip() == "1")
    raw = str(row.get(field, "") or "").strip()
    value, _ = canon(raw, meta)
    return raw.lower() if value is None else value


def is_blank(value) -> bool:
    return value in ("", None) or value == frozenset()


def same(a, b) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, str) and isinstance(b, str) and (" " in a) != (" " in b) and \
            re.match(r"^\d{4}-\d{2}-\d{2}", a) and re.match(r"^\d{4}-\d{2}-\d{2}", b):
        return a[:10] == b[:10]                    # a datetime vs a date: compare the date
    return a == b


def show(value, meta: dict) -> str:
    """How a person reads a stored value: codes as their labels, blanks as 'blank'."""
    if is_blank(value):
        return "blank"
    choices = choices_for(meta)
    if isinstance(value, frozenset):
        return ", ".join(choices.get(c, c) for c in sorted(value))
    if isinstance(value, float):
        return f"{value:g}"
    if meta.get("field_type") in CHOICE_TYPES:
        return f"{choices.get(value, value)}"
    return str(value)


def mdc_code_of(value, meta: dict) -> str:
    """The missing-data code this stored value is, or ""."""
    if isinstance(value, frozenset):
        return next(iter(value)) if len(value) == 1 and next(iter(value)) in MDC_MEANINGS else ""
    if isinstance(value, float):
        value = f"{value:g}"
    if is_date_field(meta):
        return MDC_FROM_DATE.get(str(value)[:10], "")
    return str(value) if str(value) in MDC_MEANINGS else ""


# ---------------------------------------------------------------------------- MDC judgement

# An RA-returned missing-data code is not taken on trust. Each one is checked before it can be
# uploaded; a doubtful one goes back to the RA as a question (decided 2026-10-09).
# Words that point at one code's meaning (mdc-rules.md). A note or field comment that points at
# a DIFFERENT code than the one entered is a question.
MDC_HINTS = {
    "-666": ("does not know", "doesn't know", "didn't know", "did not know", "not sure",
             "unsure", "can't remember", "cannot remember", "don't know"),
    "-777": ("refus", "declin", "did not want", "didn't want", "would not say",
             "wouldn't say"),
    "-888": ("case note", "chart", "not documented", "not recorded", "no record", "folder",
             "case file", "missing in"),
}
# The patient could not have answered — so "does not know" / "refused" can't be right.
DEATH_WORDS = ("died", "dead", "deceased", "death")
# The value seems to exist somewhere: enter it, don't code it as missing.
VALUE_EXISTS = ("paper chart", "in the chart", "in the file", "in the folder", "will enter",
                "to be entered", "will update", "pending", "awaiting", "found it", "available in",
                "have it", "later")
NEGATIONS = ("not ", "no ", "n't ", "never ")
# A site whose returned answers are mostly missing-data codes gets one line saying so.
HIGH_MDC_SHARE = 0.4
HIGH_MDC_MIN = 5


def _says(text: str, phrases) -> bool:
    """A phrase occurs, and isn't negated just before it ("not in the chart")."""
    t = _norm(text)
    for p in phrases:
        start = t.find(p)
        while start != -1:
            if not any(n in t[max(0, start - 12):start] for n in NEGATIONS):
                return True
            start = t.find(p, start + 1)
    return False


def mdc_doubt(c: Check, meta: dict, note: str, comments: list, survey_forms=()) -> str:
    """Why this RA-returned code needs the RA's word before anyone uploads it, or ""."""
    code, ftype = c.mdc, meta.get("field_type", "")
    if meta.get("form_name") in set(survey_forms or ()):
        return "self-completed survey — surveys carry no missing-data codes"
    if "@MDC-EXEMPT" in (meta.get("field_annotation") or ""):
        return "field is marked @MDC-EXEMPT"
    if (meta.get("matrix_group_name") or "").strip():
        return "validated scale (matrix) — no missing-data codes"
    if ftype in ("radio", "dropdown", "checkbox"):
        if code not in choices_for(meta):
            return f"{code} is not one of this field's choices"
    elif ftype in ("text", "notes"):
        if validation(meta).startswith("datetime"):
            return "date-and-time fields are entered by the RA"
        forms = ((MDC_DATE_IMPORT[code], "-".join(reversed(MDC_DATE_IMPORT[code].split("-"))))
                 if is_date_field(meta) else (code,))
        if not any(f in (meta.get("field_note") or "") for f in forms):
            return f"field note doesn't list {code} — this field may not take codes"
    else:
        return f"a {ftype} field takes no missing-data codes"
    said = " ".join([note] + [x.text for x in comments])
    if not said.strip():
        return "-999 needs a reason (RA note or field comment)" if code == "-999" else ""
    if _says(said, VALUE_EXISTS):
        return "note/comment suggests the value exists — enter it instead"
    if code in ("-666", "-777") and _says(said, DEATH_WORDS):
        return f"{code} means the patient answered; note/comment says the patient died"
    other = [k for k, words in MDC_HINTS.items() if k != code and _says(said, words)]
    if other and not (code in MDC_HINTS and _says(said, MDC_HINTS[code])):
        return (f"code is {code} ({MDC_MEANINGS[code]}); note/comment reads like {other[0]} "
                f"({MDC_MEANINGS[other[0]]})")
    return ""


def mdc_share_note(checks: list) -> str:
    """One line when a site's answers are unusually often missing-data codes, else ""."""
    answered = [c for c in checks if not c.from_note and c.ra_wrote]
    mdc = [c for c in answered if c.mdc]
    if len(mdc) >= HIGH_MDC_MIN and answered and len(mdc) / len(answered) > HIGH_MDC_SHARE:
        return (f"High share of missing-data codes: {len(mdc)} of {len(answered)} answers "
                f"({len(mdc) / len(answered):.0%}). Worth a word with the site.")
    return ""


# ---------------------------------------------------------------------------- the check

def _round_date(worklist: str) -> str:
    """The round a worklist belongs to, from its folder: worklists/<YYYY-MM-DD>/with_MDC/x."""
    for part in reversed(Path(worklist).resolve().parts):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", part):
            return part
    return ""


def check_cell(rid, header, ra_text, orig_text, row, meta, field, columns, kind,
               from_note=False) -> Check:
    if row is None:
        return Check(rid, header, field, ra_text, "", UNCLEAR,
                     "this record isn't in the REDCap data", kind, from_note)
    now = current_value(row, field, meta, columns)
    now_s = show(now, meta)
    if isinstance(now, str) and now and meta.get("field_type") in ("text", "notes") \
            and not is_date_field(meta):
        now_s = str(row.get(field, "")).strip()        # as typed, not as compared
    orig, _ = canon(orig_text, meta)
    if from_note or _norm(ra_text) in FILLED_MARKERS:
        if is_blank(now) or same(now, orig):
            return Check(rid, header, field, ra_text, now_s, NOT_ENTERED, "", kind, from_note)
        return Check(rid, header, field, ra_text, now_s, IN_REDCAP, "", kind, from_note)
    ra, why = canon(ra_text, meta)
    mdc = mdc_code_of(ra, meta) if ra is not None else ""
    if ra is None:
        return Check(rid, header, field, ra_text, now_s, UNCLEAR, why, kind)
    if same(now, ra):
        return Check(rid, header, field, ra_text, now_s, IN_REDCAP, "", kind, mdc=mdc)
    if is_blank(now) or same(now, orig):
        return Check(rid, header, field, ra_text, now_s, NOT_ENTERED, "", kind, mdc=mdc)
    return Check(rid, header, field, ra_text, now_s, DIFFERS, "", kind, mdc=mdc)


def reconcile(original: str, returned: str, rows: list, columns: list, metadata: list,
              comments: "list | None" = None, site: str = "", source: str = "",
              comment_source: str = "", survey_forms=()) -> Reconciliation:
    from ingest_response import build_label_maps, header_to_field

    audit = diff(original, returned)
    meta_by = {m["field_name"]: m for m in metadata}
    label2fields, _ = build_label_maps(meta_by)
    to_field = lambda h: header_to_field(h, label2fields, meta_by)  # noqa: E731
    id_field = audit.id_field
    by_id = {str(r.get(id_field, "")).strip(): r for r in rows}
    if rows and id_field not in columns:
        raise SystemExit(
            f"The REDCap data has no {id_field!r} column, so I can't match its records to the\n"
            "worklist. If you downloaded it from the website, choose CSV (raw data) — the\n"
            "column headings must be the field names, not their labels.")

    flagged = audit.flagged or {}
    checks, explained = [], []
    flagged_fields = set()
    for (rid, header) in flagged:
        f, _ = to_field(header)
        flagged_fields.add((rid, f or header))

    for rid in sorted(audit.by_record):
        for ans in audit.by_record[rid]:
            field, why = to_field(ans.field)
            if not field:
                checks.append(Check(rid, ans.field, "", ans.now, "", UNCLEAR,
                                    f"couldn't match this column to a REDCap field ({why})",
                                    ans.kind))
                continue
            checks.append(check_cell(rid, ans.field, ans.now, ans.was, by_id.get(rid),
                                     meta_by[field], field, columns, ans.kind))

    # Rows with a note and no cell change: check each flagged cell on that row.
    answered = set(audit.by_record)
    untouched = explained_left = 0
    for (rid, header), (orig_text, kind) in sorted(flagged.items()):
        if kind == "explained" and not any(a.field == header
                                           for a in audit.by_record.get(rid, [])):
            explained_left += 1          # a comment already explained it; nothing was asked
            continue
        if rid in answered:
            if not any(a.field == header for a in audit.by_record[rid]):
                untouched += 1
            continue
        note = audit.notes.get(rid, "")
        if not note:
            untouched += 1
            continue
        field, why = to_field(header)
        if not field:
            checks.append(Check(rid, header, "", "", "", UNCLEAR,
                                f"couldn't match this column to a REDCap field ({why})",
                                kind, True))
            continue
        c = check_cell(rid, header, "", orig_text, by_id.get(rid), meta_by[field], field,
                       columns, kind, from_note=True)
        claims_done = any(w in _norm(note) for w in RESOLVED_NOTE_WORDS)
        if c.status == NOT_ENTERED and not claims_done:
            explained.append(c)
        else:
            checks.append(c)

    if not site:
        dags = [str(by_id[r].get("redcap_data_access_group", "")).strip()
                for r in {k[0] for k in flagged} if r in by_id]
        dags = [d for d in dags if d]
        site = max(set(dags), key=dags.count) if dags else Path(original).stem

    comment_index = index_comments(comments or [], meta_by, to_field)
    flags = comment_flags(comment_index, {k[0] for k in flagged}, flagged, by_id, meta_by,
                          columns, to_field)
    held = []
    for c in checks:
        if _mdc_candidate(c):
            why = mdc_doubt(c, meta_by.get(c.field, {}), audit.notes.get(c.record, ""),
                            comment_index.get((c.record, c.field), []), survey_forms)
            if why:
                held.append((c, why))
    return Reconciliation(site, id_field, checks, explained, audit.notes, comment_index,
                          flagged_fields, audit.out_of_scope, untouched, source, comment_source,
                          held, mdc_share_note(checks), explained_left, tuple(flags))


def comment_flags(comment_index: dict, records: set, flagged: dict, by_id: dict, meta_by: dict,
                  columns, to_field) -> list:
    """Field comments on this worklist's records that look like the value, or contradict it.

    Judged against what REDCap holds NOW. Rules: field_comments.py. Never changes a value.
    """
    from build_worklists import clean_label
    heading = {}
    for (rid, header) in flagged:
        f, _ = to_field(header)
        if f:
            heading[f] = header
    out = []
    for (rid, field), cs in sorted(comment_index.items()):
        meta, row = meta_by.get(field), by_id.get(rid)
        if rid not in records or meta is None or row is None:
            continue
        now = current_value(row, field, meta, columns)
        if meta.get("field_type") == "checkbox":
            raw = ",".join(sorted(now))
        else:
            raw = str(row.get(field, "") or "").strip()
        header = heading.get(field) or clean_label(meta.get("field_label", "")) or field
        for c in cs:
            reason = (value_in_comment(c.text, meta) if is_blank(now)
                      else disagrees_with_value(c.text, raw, meta))
            if reason:
                out.append(CommentFlag(rid, header, field, show(now, meta), c.text, reason))
                break
    return out


# ---------------------------------------------------------------------------- the report

def _cell(text) -> str:
    return str(text or "").replace("|", "/").replace("\n", " ").strip()


def _comment_text(rec: Reconciliation, rid: str, field: str) -> str:
    return comment_text(rec.comments.get((rid, field), []))


def _mdc_candidate(c: Check) -> bool:
    return (c.status == NOT_ENTERED and bool(c.mdc) and c.redcap_now == "blank"
            and c.kind != "amber" and not c.from_note)


def uploadable_mdc(rec: Reconciliation) -> list:
    """NOT ENTERED cells whose answer is a missing-data code, REDCap is blank, and nothing in
    the RA's note or the field comment casts doubt on the code.

    Only a candidate list for the report; upload_mdc.py re-checks every rule before writing.
    """
    held = {(c.record, c.field) for c, _ in rec.held_back}
    return [c for c in rec.checks if _mdc_candidate(c) and (c.record, c.field) not in held]


def render(rec: Reconciliation) -> str:
    by = {s: [c for c in rec.checks if c.status == s] for s in STATUSES}
    noted_blank = [c for c in by[NOT_ENTERED] if c.from_note]
    typed = [c for c in by[NOT_ENTERED] if not c.from_note]
    mdc = uploadable_mdc(rec)
    L = [f"# REDCap check — {rec.site}", ""]
    L.append(f"Checked against: {rec.source}")
    if rec.comment_source:
        L.append(f"Field comments: {rec.comment_source}")
    L += ["", "| In REDCap | Not entered | Differs | Unclear |", "|---|---|---|---|",
          f"| {len(by[IN_REDCAP])} | {len(by[NOT_ENTERED])} | {len(by[DIFFERS])} "
          f"| {len(by[UNCLEAR])} |", ""]
    if mdc:
        L.append(f"{len(mdc)} of the not-entered answers are missing-data codes you may upload "
                 "yourself (upload_mdc.py). Everything else, the RA enters.")
    if rec.held_back:
        L.append(f"{len(rec.held_back)} missing-data code(s) held back — questions for the RA.")
    if rec.mdc_share_note:
        L.append(rec.mdc_share_note)
    if rec.untouched:
        L.append(f"{rec.untouched} flagged cell(s) came back untouched. The next worklist "
                 "build will list them again.")
    if rec.explained_left:
        L.append(f"{rec.explained_left} blue cell(s) — already explained by a field comment — "
                 "came back unanswered. Nothing to do.")
    in_comment = [f for f in rec.comment_flags if f.reason.startswith(VALUE_IN_COMMENT)]
    disagree = [f for f in rec.comment_flags if f.reason == DISAGREES]
    if in_comment:
        L.append(f"{len(in_comment)} blank cell(s) where the value may be in the field comment.")
    if disagree:
        L.append(f"{len(disagree)} cell(s) where the field comment and the value may disagree.")
    L.append("")

    def note(rid):
        return _cell(rec.notes.get(rid, ""))

    def table(title, rows, cols, render_row):
        if not rows:
            return
        L.extend([f"## {title}", "", "| " + " | ".join(cols) + " |",
                  "|" + "---|" * len(cols)])
        for c in rows:
            L.append("| " + " | ".join(_cell(x) for x in render_row(c)) + " |")
        L.append("")

    amber = lambda c: " (amber: check it applies)" if c.kind == "amber" else ""  # noqa: E731
    std = ["Record", "Field", "RA wrote", "REDCap now", "RA note", "Field comment"]
    held = {(c.record, c.field): why for c, why in rec.held_back}
    typed = [c for c in typed if (c.record, c.field) not in held]
    table("Not entered — ask the RA to enter these in REDCap", typed, std, lambda c: (
        c.record, c.header + amber(c) + (" [MDC — you may upload]" if c in mdc else ""),
        c.ra_wrote, c.redcap_now, note(c.record), _comment_text(rec, c.record, c.field)))
    table("Marked resolved, but REDCap is still blank — ask the RA", noted_blank,
          ["Record", "Field", "REDCap now", "RA note", "Field comment"], lambda c: (
              c.record, c.header + amber(c), c.redcap_now, note(c.record),
              _comment_text(rec, c.record, c.field)))
    table("MDCs held back — ask the RA", [c for c, _ in rec.held_back],
          ["Record", "Field", "RA wrote", "Why held back"], lambda c: (
              c.record, c.header, c.ra_wrote, held[(c.record, c.field)]))
    table("Differs — ask the RA which is right", by[DIFFERS], std, lambda c: (
        c.record, c.header + amber(c), c.ra_wrote, c.redcap_now, note(c.record),
        _comment_text(rec, c.record, c.field)))
    table("Unclear — ask the RA what they meant", by[UNCLEAR],
          ["Record", "Field", "RA wrote", "REDCap now", "Why"], lambda c: (
              c.record, c.header + amber(c), c.ra_wrote, c.redcap_now, c.why))
    table("Still blank, RA explained — you decide: no action, or a question",
          rec.still_blank_explained, ["Record", "Field", "RA note", "Field comment"], lambda c: (
              c.record, c.header, note(c.record), _comment_text(rec, c.record, c.field)))

    # Flagged cells still blank that carry a field comment: often the reason for the blank.
    blank_with_comment = []
    for c in typed + [h for h, _ in rec.held_back] + noted_blank + rec.still_blank_explained:
        if rec.comments.get((c.record, c.field)):
            blank_with_comment.append(c)
    table("Still blank, with a field comment — you decide (never converted to a code for you)",
          blank_with_comment, ["Record", "Field", "Field comment"], lambda c: (
              c.record, c.header, _comment_text(rec, c.record, c.field)))

    table("Value may be in the comment — ask the RA to enter it in the field", in_comment,
          ["Record", "Field", "REDCap now", "Field comment", "Why"], lambda f: (
              f.record, f.header, f.redcap_now, f.comment,
              f.reason.replace(VALUE_IN_COMMENT, "").strip(" ()") or "free-text field"))
    table("Comment and value may disagree — check", disagree,
          ["Record", "Field", "REDCap now", "Field comment"], lambda f: (
              f.record, f.header, f.redcap_now, f.comment))

    # Only this worklist's records: a key run reads the WHOLE project's comments, and another
    # site's comments are not this site's business.
    on_list = {k[0] for k in rec.flagged_fields}
    off = sorted((k, v) for k, v in rec.comments.items()
                 if k not in rec.flagged_fields and k[0] in on_list)
    if off:
        L += ["## Field comments on cells not on the worklist", "",
              "| Record | Field | Field comment |", "|---|---|---|"]
        for (rid, field), _ in off:
            L.append(f"| {_cell(rid)} | {_cell(field)} | {_cell(_comment_text(rec, rid, field))} |")
        L.append("")
    if rec.out_of_scope:
        L += [f"## Changed in the worklist but never asked about ({len(rec.out_of_scope)})", "",
              "Ask the RA what they changed and why. Not checked against REDCap.", ""]
        for e in rec.out_of_scope:
            L.append(f"- {e.record} — {e.field}: {e.was or 'blank'} → {e.now}")
        L.append("")

    L += questions_block(rec)
    return "\n".join(L).rstrip() + "\n"


def questions_block(rec: Reconciliation) -> list:
    """Ready to paste into RA_questions.md: one ## site section, second person, per record."""
    items = {}
    held = {(c.record, c.field): why for c, why in rec.held_back}
    ok_mdc = uploadable_mdc(rec)
    asked = set()
    for c in rec.checks:
        if c.status != IN_REDCAP:
            asked.add((c.record, c.field))
        if (c.record, c.field) in held and not c.from_note:
            items.setdefault(c.record, {}).setdefault("held", []).append(c)
        elif c.status == NOT_ENTERED and c not in ok_mdc:
            items.setdefault(c.record, {}).setdefault("enter", []).append(c)
        elif c.status in (DIFFERS, UNCLEAR):
            items.setdefault(c.record, {}).setdefault(c.status, []).append(c)
    for f in rec.comment_flags:
        if f.reason.startswith(VALUE_IN_COMMENT) and (f.record, f.field) not in asked:
            items.setdefault(f.record, {}).setdefault("in_comment", []).append(f)
    if not items:
        return []
    L = ["## For RA_questions.md", "", "Copy the block below into RA_questions.md.", "",
         f"## {rec.site}"]
    for rid in sorted(items):
        it = items[rid]
        for c in it.get("enter", []):
            still = ("REDCap is still blank" if c.redcap_now == "blank"
                     else f"REDCap still shows \"{c.redcap_now}\"")
            if c.from_note:
                L.append(f"### {rid} — {c.header}: you marked this resolved, but {still}. "
                         "Could you enter it in REDCap?")
            else:
                L.append(f"### {rid} — {c.header}: you wrote \"{c.ra_wrote}\" on the worklist, "
                         f"but {still}. Could you enter it in REDCap?")
        for c in it.get("held", []):
            L.append(f"### {rid} — {c.header}: you wrote {c.ra_wrote} "
                     f"({MDC_MEANINGS.get(c.mdc, 'a missing-data code')}). We held it back: "
                     f"{held[(c.record, c.field)]}. Could you check, and enter the right answer "
                     "in REDCap?")
        for c in it.get(DIFFERS, []):
            L.append(f"### {rid} — {c.header}: you wrote \"{c.ra_wrote}\", but REDCap shows "
                     f"\"{c.redcap_now}\". Which is right? Please make REDCap match.")
        for c in it.get(UNCLEAR, []):
            L.append(f"### {rid} — {c.header}: you wrote \"{c.ra_wrote}\". What did you mean? "
                     "Please enter the answer in REDCap.")
        for f in it.get("in_comment", []):
            L.append(f"### {rid} — {f.header}: the field is blank in REDCap, but its field "
                     f"comment reads \"{f.comment}\". If that is the answer, could you enter it "
                     "in the field itself?")
    L.append("")
    return L


# ---------------------------------------------------------------------------- command line

def gather(args) -> tuple:
    """Load REDCap's current state (key or files), the comments, and reconcile.

    -> (rec, client or None, rows, columns, metadata) — the exact state the check used.
    """
    client = None
    if args.records_csv or args.metadata_csv:
        if not (args.records_csv and args.metadata_csv):
            raise SystemExit("Give me both files: --records-csv export.csv --metadata-csv dd.csv")
        rows, columns, metadata = load_from_files(args.records_csv, args.metadata_csv)
        when = dt.datetime.fromtimestamp(os.path.getmtime(args.records_csv)).strftime("%Y-%m-%d %H:%M")
        source = f"{Path(args.records_csv).name} (file dated {when})"
        if os.path.getmtime(args.records_csv) < os.path.getmtime(args.returned):
            print("Warning: this export is older than the RA's returned workbook. If it was "
                  "downloaded before the RA's work, every answer will look NOT ENTERED. "
                  "Download a fresh export.", file=sys.stderr)
    elif args.token_env:
        from argo_redcap_client import load_env_file
        load_env_file()
        if args.url:
            os.environ["REDCAP_URL"] = args.url
        rows, columns, metadata, client = load_from_key(args.token_env)
        source = f"REDCap, pulled {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    else:
        raise SystemExit(
            "I need REDCap's current data to check against. Either:\n"
            "  --records-csv export.csv --metadata-csv dd.csv   (downloaded after the RA's return)\n"
            "  --token-env YOUR_STUDY_KEY                        (if you have the study's key)")

    comments, comment_source = [], ""
    if args.comments:
        comments = read_comment_log(args.comments)
        comment_source = f"{Path(args.comments).name} ({len(comments)} comment(s))"
    elif client is not None:
        comments, why = comments_through_key(client, args.comments_since)
        comment_source = (f"{why} ({len(comments)} comment(s))" if comments or "logging" in why
                          else "not included — download Applications → Field Comment Log and "
                               "pass it with --comments")
    else:
        comment_source = ("not included — download Applications → Field Comment Log and pass it "
                          "with --comments")

    surveys = [f.strip() for f in (args.survey_forms or "").split(",") if f.strip()]
    rec = reconcile(args.original, args.returned, rows, columns, metadata, comments,
                    site=args.site or "", source=source, comment_source=comment_source,
                    survey_forms=surveys)
    return rec, client, rows, columns, metadata


def add_source_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("original", help="The worklist you sent the site (.xlsx)")
    ap.add_argument("returned", help="The worklist the RA sent back (.xlsx)")
    ap.add_argument("--token-env", help="Name of the setting holding the study's access key")
    ap.add_argument("--url", help="REDCap API address, if it isn't in your settings file")
    ap.add_argument("--records-csv", help="No-key mode: a fresh Data Export (raw data) CSV")
    ap.add_argument("--metadata-csv", help="No-key mode: the Data Dictionary CSV")
    ap.add_argument("--comments", help="The Field Comment Log CSV downloaded from REDCap")
    ap.add_argument("--comments-since", default="",
                    help="With a key: only replay logging from this date (YYYY-MM-DD). Leave it out — "
                         "comments explaining a blank often predate the round by years, and "
                         "a cut-off history replays edits and deletes wrongly.")
    ap.add_argument("--site", help="Site name for the report (defaults to the records' DAG)")
    ap.add_argument("--survey-forms", default="",
                    help="Comma-separated forms that are self-completed surveys (no codes there)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_source_args(ap)
    ap.add_argument("--out", help="Write the report here (.md) as well as printing it")
    args = ap.parse_args()
    rec = gather(args)[0]
    text = render(rec)
    print(text)
    if args.out:
        Path(args.out).expanduser().parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).expanduser().write_text(text)
        print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
