"""REDCap field comments — read once, here, for every QA tool that uses them.

Field comments (REDCap's Field Comment Log) are where RAs explain a blank — and, sometimes, where
they typed the actual value instead of entering it in the field. This module is the one place
that:

  READS them      read_comment_log()      the downloaded CSV (Applications -> Field Comment Log;
                                          real headings `Record, Field, User, Datetime, Comment`)
                  comments_through_key()  rebuilt from the project's WHOLE logging history
                                          (REDCap has no API for the log itself, but every add /
                                          edit / delete is logged)
  INDEXES them    index_comments()        {(record, field): [Comment]}
  JUDGES them     explains_blank()        the comment explains why the cell is blank
                  value_in_comment()      the comment looks like the VALUE, not an explanation
                  disagrees_with_value()  the comment contradicts a filled value

Used by build_worklists.py (shorter worklists), reconcile_return.py (the audit report) and,
through reconcile_return.gather, upload_mdc.py. Comments are evidence, never values: nothing here
ever turns a comment into a value, and a blank stays blank.
"""

from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------- reading

# The Field Comment Log download. OAU REDCap 13.11.4 (2026-10-09) names its columns
# `Record, Field, User, Datetime, Comment`; other versions vary, so headings are matched by
# alias, in this one table, and a file whose headings don't match fails loudly and names them.
FIELD_COMMENT_HEADERS = {
    "record": ("record", "record id", "record_id"),
    "field": ("field", "field name", "variable", "variable name"),
    "event": ("event", "event name"),
    "instance": ("instance", "repeat instance"),
    "user": ("user", "username"),
    "comment": ("comment", "comments"),
    "time": ("datetime", "date/time", "timestamp", "date", "time"),   # OAU 13.11.4 says "Datetime"
}
FIELD_COMMENT_REQUIRED = ("record", "field", "comment")


class Comment(NamedTuple):
    record: str
    field: str
    text: str
    user: str = ""
    time: str = ""
    event: str = ""


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _read_csv(path: str, what: str) -> "tuple[list, list]":
    p = Path(path).expanduser()
    if not p.is_file():
        raise SystemExit(f"I couldn't find the {what}:\n    {p}\n\nCheck the file name and folder.")
    with open(p, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def _header_role(header: str) -> str:
    h = _norm(header)
    for role, aliases in FIELD_COMMENT_HEADERS.items():
        if h in aliases:
            return role
    return ""


def read_comment_log(path: str) -> list:
    """The Field Comment Log CSV -> [Comment]. Headings matched by alias, never by position."""
    rows, headers = _read_csv(path, "Field Comment Log")
    roles = {}
    unrecognised = []
    for h in headers:
        role = _header_role(h)
        if role and role not in roles:
            roles[role] = h
        else:
            unrecognised.append(h)
    missing = [r for r in FIELD_COMMENT_REQUIRED if r not in roles]
    if missing:
        raise SystemExit(
            "I can't read this Field Comment Log — I don't recognise its column headings.\n"
            f"    file: {path}\n"
            f"    headings found: {', '.join(repr(h) for h in headers) or '(none)'}\n"
            f"    not recognised: {', '.join(repr(h) for h in unrecognised) or '(none)'}\n"
            f"    still needed:   {', '.join(missing)}\n"
            "\n"
            "Download it from REDCap: Applications -> Field Comment Log -> export (CSV). If that\n"
            "is what this is, REDCap has named its columns differently from what ARGO expects —\n"
            "send this message to the ARGO team so the heading list can be updated.")
    out = []
    for r in rows:
        get = lambda role: str(r.get(roles.get(role, ""), "") or "").strip()  # noqa: E731
        if not get("record") or not get("comment"):
            continue
        out.append(Comment(get("record"), get("field"), get("comment"),
                           get("user"), get("time"), get("event")))
    return out


_LOG_DETAIL = re.compile(r"^\s*(Add|Edit|Delete) field comment\s*\((.*)\)\s*$", re.S | re.I)


def _split_details(inner: str) -> dict:
    """'Record: 7, Event: "x, y", Field: "f", Comment: "a \\"b\\""' -> dict. Quote-aware."""
    parts, buf, quoted, esc = [], [], False, False
    for ch in inner:
        if esc:
            buf.append(ch); esc = False
        elif ch == "\\" and quoted:
            esc = True
        elif ch == '"':
            quoted = not quoted
        elif ch == "," and not quoted:
            parts.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    out = {}
    for p in parts:
        key, sep, val = p.partition(":")
        if sep:
            out[key.strip().lower()] = val.strip()
    return out


def comments_from_logging(entries: list) -> list:
    """Replay REDCap logging (logtype=manage) into the field comments that exist now.

    Kept: action 'Manage/Design' (REDCap 13 returns it with a trailing space) whose details read
    'Add|Edit|Delete field comment (Record: …, Field: …, Comment: …)'. Replayed oldest first:
    an edit replaces the latest comment by the same person on that cell, a delete removes it.
    Verified 2026-10-09 on OAU REDCap 13.11.4 (CRC: 1,601 comment lines -> 1,398 live comments).
    The field name is NOT quoted in `details`; the comment text is.
    """
    def ts(e):
        return str(e.get("timestamp", ""))
    live = {}
    for e in sorted(entries, key=ts):
        if str(e.get("action", "")).strip() != "Manage/Design":
            continue
        m = _LOG_DETAIL.match(str(e.get("details", "")))
        if not m:
            continue
        verb, d = m.group(1).lower(), _split_details(m.group(2))
        rec, field = d.get("record", "").strip(), d.get("field", "").strip()
        if not rec or not field:
            continue
        key, user = (rec, field), str(e.get("username", ""))
        c = Comment(rec, field, d.get("comment", ""), user, ts(e), d.get("event", ""))
        thread = live.setdefault(key, [])
        mine = [i for i, x in enumerate(thread) if x.user == user] or list(range(len(thread)))
        if verb == "add":
            thread.append(c)
        elif verb == "edit" and mine:
            thread[mine[-1]] = c
        elif verb == "edit":
            thread.append(c)
        elif verb == "delete" and mine:
            hit = [i for i in mine if thread[i].text == c.text]
            thread.pop(hit[-1] if hit else mine[-1])
    return [c for thread in live.values() for c in thread]


def comments_through_key(client, since: str = "") -> "tuple[list, str]":
    """Field comments from the project's logging, or ([], why-not). Never raises, never writes."""
    params = {"content": "log", "logtype": "manage"}
    if since:
        params["beginTime"] = f"{since} 00:00"
    try:
        entries = client._post(**params)      # the shared client's transport; read-only
    except Exception:                        # no Logging right, or an older REDCap
        return [], "not available through the access key"
    if not isinstance(entries, list):
        return [], "not available through the access key"
    return comments_from_logging(entries), f"project logging since {since or 'the start'}"


def index_comments(comments: list, meta_by: dict, header_to_field=None) -> dict:
    """{(record, field_name): [Comment]}. The log may name a checkbox column or a label."""
    out = {}
    for c in comments:
        field = c.field
        if field not in meta_by:
            base = field.split("___")[0]
            if base in meta_by:
                field = base
            elif header_to_field is not None:
                field = header_to_field(field)[0] or field
        out.setdefault((c.record, field), []).append(c)
    return out


def comment_text(comments: list) -> str:
    """One line for a person to read: 'text (user) / text (user)'."""
    return " / ".join(c.text + (f" ({c.user})" if c.user else "") for c in comments)


# ---------------------------------------------------------------------------- judging
#
# THE RULES, in one place. Each returns a short plain reason, or "" when it doesn't apply.
#
#   explains_blank(text)
#       The comment contains a phrase from EXPLANATION_PHRASES (whole words), or a negation
#       followed by more words ("not measured", "no weight recorded"). A bare "No" is NOT an
#       explanation — on a yes/no field it is the value.
#
#   value_in_comment(text, meta)        — only ever asked about a BLANK cell
#       Never, if explains_blank(text): the explanation lexicon wins over any value-like match.
#       choice field  the whole comment matches one of the field's choice labels, ignoring case,
#                     spacing and end punctuation, allowing small typos (1 letter for labels of
#                     4-8 letters, 2 above that; shorter labels must match exactly); or a choice
#                     label of 5+ letters appears whole in a comment of 8 words or fewer.
#                     Missing-data-code options don't count.
#       date field    the comment contains a real calendar date, year 1900-2100
#                     (2023-03-05, 05/03/2023, 5.3.2023, 5 March 2023, March 5, 2023).
#       number field  the comment contains a number (not a date, not a missing-data code) that
#                     fits the field: a whole number for integer fields, inside min/max if set.
#       text field    (no date/number validation) the comment is not explanation-like.
#
#   disagrees_with_value(text, value, meta)   — only ever asked about a FILLED cell
#       The comment STARTS with a clear negation (DISAGREE_STARTS, after an optional
#       "patient"/"pt"), contains no hedge or confirmation (DISAGREE_EXCEPTIONS), and the value
#       is not a missing-data code and not a "No"-type answer (NO_TYPE_LABEL, or 0).
#       Deliberately narrow: a false alarm costs a QA specialist's time on every round.

EXPLANATION_PHRASES = (
    "missing", "not available", "unavailable", "n/a", "na", "not in chart", "not in the chart",
    "not in file", "not in the file", "not in folder", "not documented", "undocumented",
    "not recorded", "no record", "no records", "unknown", "not known", "lost", "transferred",
    "referred", "died", "dead", "deceased", "death", "pending", "awaiting", "not done",
    "not applicable", "not found", "could not", "couldn't", "cannot", "can't", "unable",
    "declined", "refused", "absconded", "ltfu", "illegible", "not collected", "not sent",
    "not traceable", "untraceable", "checked", "confirmed", "verified", "asked", "queried",
    "query", "contacted", "will", "later", "follow up", "follow-up", "see ",
)
# A negation followed by at least one more word reads as an explanation of a blank.
_NEGATED_PHRASE = re.compile(r"\b(?:no|not|never|none|nil)\b\s+\w|\w+n't\b\s+\w")

DISAGREE_STARTS = ("no", "none", "not done", "not performed", "did not", "didn't",
                   "never had", "never", "declined")
DISAGREE_EXCEPTIONS = ("no change", "no changes", "no issue", "no issues", "no problem",
                       "no problems", "no further", "no other", "no new", "no query",
                       "no queries", "no response", "no reply", "no comment", "no comments",
                       "confirmed", "correct", "verified", "as entered", "but", "however",
                       "except", "although")
NO_TYPE_LABEL = re.compile(r"^(?:no|none|not|never|nil|negative|absent|denied|declined)\b")

MDC_CODES = ("-666", "-777", "-888", "-999", "666")
_MDC_DATES = ("6666-06-06", "7777-07-07", "8888-08-08", "9999-09-09")
_CHOICE_KINDS = ("radio", "dropdown", "yesno", "truefalse", "checkbox")
BUILTIN_CHOICES = {"yesno": {"1": "Yes", "0": "No"}, "truefalse": {"1": "True", "0": "False"}}


def _plain(text) -> str:
    """Lowercase, curly quotes straightened, punctuation at the ends and extra spaces dropped."""
    t = str(text or "").replace("’", "'").replace("‘", "'")
    t = re.sub(r"\s+", " ", t.strip().lower())
    return t.strip(" .,;:!?\"'()[]-")


def _has_phrase(t: str, phrase: str) -> bool:
    if phrase.endswith(" "):                       # "see " — a word that must be followed by more
        return re.search(r"\b" + re.escape(phrase), t + " ") is not None
    return re.search(r"(?<![\w/])" + re.escape(phrase) + r"(?![\w/])", t) is not None


def explains_blank(text: str) -> bool:
    t = _plain(text)
    if not t:
        return False
    return any(_has_phrase(t, p) for p in EXPLANATION_PHRASES) or bool(_NEGATED_PHRASE.search(t))


def validation(meta: dict) -> str:
    """The field's validation type, lowercased ('date_dmy', 'integer', ...)."""
    return (meta.get("text_validation_type_or_show_slider_number") or "").strip().lower()


def parse_choices(spec: str) -> dict:
    """'1, Yes | 0, No' -> {'1': 'Yes', '0': 'No'}."""
    out = {}
    for part in (spec or "").split("|"):
        part = part.strip()
        if not part:
            continue
        code, sep, label = part.partition(",")
        out[code.strip()] = label.strip() if sep else code.strip()
    return out


def choices_for(meta: dict) -> dict:
    """{code: label} — yes/no and true/false carry REDCap's built-in choices."""
    ftype = meta.get("field_type", "")
    return BUILTIN_CHOICES.get(ftype) or parse_choices(meta.get("select_choices_or_calculations", ""))


def _edit_distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _label_matches(comment: str, label: str) -> bool:
    lab = _plain(label)
    if not lab:
        return False
    if comment == lab:
        return True
    n = len(lab.replace(" ", ""))
    allowed = 0 if n < 4 else (1 if n <= 8 else 2)
    if allowed and _edit_distance(comment, lab) <= allowed:
        return True
    return (n >= 5 and len(comment.split()) <= 8
            and re.search(r"\b" + re.escape(lab) + r"\b", comment) is not None)


_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_DATE_PATTERNS = (
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b"), "dmy|mdy"),
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + _MON + r",?\s+(\d{4})\b"), "d mon y"),
    (re.compile(r"\b" + _MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"), "mon d y"),
)


def _real(y, m, d) -> bool:
    try:
        return 1900 <= int(y) <= 2100 and bool(dt.date(int(y), int(m), int(d)))
    except ValueError:
        return False


def dates_in(text: str) -> list:
    """Every real calendar date written in the text, as the text wrote it."""
    t, found = _plain(text), []
    for rx, shape in _DATE_PATTERNS:
        for m in rx.finditer(t):
            g = m.groups()
            if shape == "ymd":
                ok = _real(g[0], g[1], g[2])
            elif shape == "dmy|mdy":
                ok = _real(g[2], g[1], g[0]) or _real(g[2], g[0], g[1])
            elif shape == "d mon y":
                ok = _real(g[2], _MONTHS[g[1]], g[0])
            else:
                ok = _real(g[2], _MONTHS[g[0]], g[1])
            if ok:
                found.append(m.group(0))
    return found


def _numbers_in(text: str) -> list:
    t = _plain(text)
    for d in dates_in(text):
        t = t.replace(d, " ")
    return [n for n in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.]*\d)", t)
            if n not in MDC_CODES]


def _fits(number: str, meta: dict) -> bool:
    v = validation(meta)
    if v == "integer" and "." in number:
        return False
    x = float(number)
    for bound, ok in (("text_validation_min", lambda b: x >= b),
                      ("text_validation_max", lambda b: x <= b)):
        raw = (meta.get(bound) or "").strip()
        try:
            if raw and not ok(float(raw)):
                return False
        except ValueError:
            pass
    return True


def field_kind(meta: dict) -> str:
    """'choice' / 'date' / 'number' / 'text' / '' (a field type comments aren't judged on)."""
    ftype, v = meta.get("field_type", ""), validation(meta)
    if ftype in _CHOICE_KINDS:
        return "choice"
    if ftype in ("text", "notes"):
        if v.startswith(("date", "datetime")):
            return "date"
        if v == "integer" or v.startswith("number"):
            return "number"
        return "text"
    return ""


VALUE_IN_COMMENT = "value may be in the comment — enter it in the field"
DISAGREES = "comment and value may disagree — check"


def value_in_comment(text: str, meta: dict) -> str:
    """For a BLANK cell: why this comment looks like the value itself, or ""."""
    if not str(text or "").strip() or explains_blank(text):
        return ""
    kind, t = field_kind(meta), _plain(text)
    if kind == "choice":
        for code, label in choices_for(meta).items():
            if code in MDC_CODES:
                continue
            if _label_matches(t, label):
                return f'{VALUE_IN_COMMENT} (reads like "{label}")'
        return ""
    if kind == "date":
        found = dates_in(text)
        return f"{VALUE_IN_COMMENT} (a date: {found[0]})" if found else ""
    if kind == "number":
        nums = [n for n in _numbers_in(text) if _fits(n, meta)]
        return f"{VALUE_IN_COMMENT} (a number: {nums[0]})" if nums else ""
    if kind == "text":
        return VALUE_IN_COMMENT
    return ""


def _is_mdc(value: str) -> bool:
    v = str(value or "").strip()
    return v in MDC_CODES or v[:10] in _MDC_DATES


def _no_type(value: str, meta: dict) -> bool:
    """The filled value is itself a 'No'-type answer, so a negating comment agrees with it."""
    v = str(value or "").strip()
    try:
        if float(v) == 0:
            return True
    except ValueError:
        pass
    choices = choices_for(meta)
    labels = [choices.get(p.strip(), p.strip()) for p in v.split(",")] if choices else [v]
    return any(NO_TYPE_LABEL.match(_plain(lab)) for lab in labels)


def disagrees_with_value(text: str, value, meta: dict) -> str:
    """For a FILLED cell: why the comment may contradict the value, or "".

    `value` is what REDCap holds as REDCap stores it (choice CODES; for a checkbox, the ticked
    codes joined by commas).
    """
    v = str(value or "").strip()
    if not v or _is_mdc(v) or all(_is_mdc(p) for p in v.split(",")) or not field_kind(meta):
        return ""
    if _no_type(v, meta):
        return ""
    t = re.sub(r"^(?:the )?(?:patient|pt\.?)\s+", "", _plain(text))
    if not any(re.match(re.escape(s) + r"\b", t) for s in DISAGREE_STARTS):
        return ""
    if any(_has_phrase(t, x) for x in DISAGREE_EXCEPTIONS):
        return ""
    return DISAGREES
