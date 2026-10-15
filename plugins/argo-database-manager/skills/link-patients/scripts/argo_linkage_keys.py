#!/usr/bin/env python3
"""argo_linkage_keys.py — clean and compare the keys ARGO links patients on.

Three keys link a patient across ARGO studies: the hospital number (unique only within one
hospital, so always read with its site), the histology number (identifies a specimen, not a
person) and the name. All three are typed by hand, so all three carry typos. This module turns
each raw value into a comparable form and says how close two values are — it never decides a
link. The linkage skill turns these answers into tiers, review items and RA worklists.

Everything here is deterministic and local: no network, no model, no REDCap. Stdlib only.

  site_code("oauthc_ife")                    -> "OAUTHC"
  hospital_number("ostc-012345")             -> key "012345", site from the prefix if known
  compare_hospital(a, b)                     -> "exact" | "leading_zero" | "one_digit" | ...
  histology_number("H1641/2021")             -> prefix "H", number 1641, year 21
  compare_histology(a, b)                    -> "exact" | "year_differs" | "prefix_differs" | ...
  compare_names(("Ade", "Bello"), ("Bello", "Ade"))   -> ("same", "swapped")
  compare_pair(rec_a, rec_b)                 -> what agrees, what nearly agrees, what conflicts

Formats come from the old linkage scripts and the P20 histology rules (2026-10-15). Formats
nobody has confirmed (LUTH's long hospital-number form) are kept whole and flagged, not guessed.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# --- sites -------------------------------------------------------------------------------------

# Every spelling seen in DAGs, choice labels and number prefixes -> one site code.
SITE_ALIASES = {
    "OAUTHC": ["oauthc", "oauthc_ife", "oau", "ife", "oauthc ife", "oauthc-ife"],
    "LUTH": ["luth", "lagos university teaching hospital"],
    "LASUTH": ["lasuth"],
    "UITH": ["uith", "uith_ilorin", "ilorin"],
    "NHA": ["nha", "nha_abuja", "national hospital abuja"],
    "UMTH": ["umth", "maiduguri"],
    "UCH": ["uch", "uch_ibadan", "ibadan"],
    "FMC": ["fmc"],
    "FTHA": ["ftha"],
}
_ALIAS = {a: code for code, names in SITE_ALIASES.items() for a in names + [code.lower()]}


def site_code(raw) -> str | None:
    """The site code for any known spelling, or None if the spelling is unknown."""
    s = re.sub(r"\s+", " ", str(raw or "").strip().lower())
    return _ALIAS.get(s) or _ALIAS.get(s.replace(" ", "_"))


# --- missing values ----------------------------------------------------------------------------

MDC_CODES = {"-666", "-777", "-888", "-999",
             "06-06-6666", "07-07-7777", "08-08-8888", "09-09-9999"}
_BLANKS = {"", "NAN", "NONE", "NULL", "NA", "N/A"}


def _missing_reason(s: str) -> str | None:
    if s in _BLANKS:
        return "blank"
    if s in MDC_CODES:
        return "missing-data code"
    if not re.search(r"\d", s):
        return "placeholder"          # NIL, NYR, UNKNOWN, NOT AVAILABLE ...
    return None


# --- hospital numbers --------------------------------------------------------------------------

@dataclass(frozen=True)
class HospitalNumber:
    raw: str
    key: str = ""                     # comparable form; "" when missing
    site: str | None = None
    suffix: str = ""                  # repeat-patient suffix (-1, -2)
    flags: frozenset = field(default_factory=frozenset)
    missing: str | None = None        # why it is missing, if it is


def hospital_number(raw, site=None) -> HospitalNumber:
    """Clean one hospital number. `site` is the record's site (any spelling); a site prefix
    inside the value (e.g. OAUTHC-123456) wins over it."""
    raw = "" if raw is None else str(raw)
    s = raw.strip().upper()
    site = site_code(site) if site else None
    gone = _missing_reason(s)
    if gone:
        return HospitalNumber(raw, site=site, missing=gone)
    flags = set()

    cleaned = re.sub(r"\(.*?\)", " ", s).replace("*", " ").strip()   # annotations
    cleaned = re.sub(r"\s+[A-Z][A-Z .]*$", "", cleaned)               # trailing words
    if cleaned != s:
        flags.add("annotated")
    s = cleaned

    m = re.match(r"^([A-Z]{2,8})[\s\-/_.]*(\d.*)$", s)
    if m:
        prefix_site = site_code(m.group(1))
        if prefix_site:
            site, s = prefix_site, m.group(2)
            flags.add("site_prefix")

    suffix = ""
    m = re.match(r"^(\d{5,7})\s*-\s*(\d)$", s)
    if m:
        s, suffix = m.group(1), m.group(2)
        flags.add("repeat_suffix")

    compact = re.sub(r"[\s\-/._]", "", s)
    if compact.isdigit():
        if len(compact) == 5:
            flags.add("five_digit")
        elif len(compact) == 7:
            flags.add("seven_digit")
        elif len(compact) not in (5, 6, 7):
            flags.add("unusual_length")
    else:
        flags.add("unrecognised_format")   # LUTH long form, register formats: kept whole
    return HospitalNumber(raw, key=compact, site=site, suffix=suffix, flags=frozenset(flags))


def _one_edit(a: str, b: str) -> str | None:
    """'one_digit', 'transposed' or 'digit_missing' when a and b differ by exactly one edit."""
    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diffs) == 1:
            return "one_digit"
        if len(diffs) == 2 and diffs[1] == diffs[0] + 1 and a[diffs[0]] == b[diffs[1]] \
                and a[diffs[1]] == b[diffs[0]]:
            return "transposed"
        return None
    if abs(len(a) - len(b)) == 1:
        short, long_ = sorted((a, b), key=len)
        for i in range(len(long_)):
            if long_[:i] + long_[i + 1:] == short:
                return "digit_missing"
    return None


def compare_hospital(a: HospitalNumber, b: HospitalNumber) -> str | None:
    """How two hospital numbers relate, or None if they don't.

    exact / suffix_differs / leading_zero — the same number;
    one_digit / transposed / digit_missing — a likely typo (same site only);
    different_site — the same number recorded at two hospitals.
    A number is only unique within a hospital, so a match across two known sites is never
    'exact'."""
    if a.missing or b.missing or not a.key or not b.key:
        return None
    if a.site and b.site and a.site != b.site:
        return "different_site" if a.key == b.key or a.key.lstrip("0") == b.key.lstrip("0") \
            else None
    if a.key == b.key:
        return "exact" if a.suffix == b.suffix else "suffix_differs"
    if a.key.isdigit() and b.key.isdigit() and a.key.lstrip("0") == b.key.lstrip("0"):
        return "leading_zero"
    return _one_edit(a.key, b.key)


# --- histology numbers -------------------------------------------------------------------------

@dataclass(frozen=True)
class HistologyNumber:
    raw: str
    prefix: str = ""                  # H, B, S, TH, HP ... ("" when written without one)
    number: int | None = None
    year: int | None = None           # two digits
    flags: frozenset = field(default_factory=frozenset)
    missing: str | None = None

    @property
    def key(self):
        return (self.prefix, self.number, self.year) if self.number is not None else None


def _year2(y: str) -> int | None:
    v = int(y)
    if len(y) == 2:
        return v
    return v % 100 if 1990 <= v <= 2099 else None


def histology_number(raw, site=None) -> HistologyNumber:
    """Parse one histology number into prefix, number and two-digit year.

    Year last is the norm (H1641/21, B951/2021, S-553-23). The LASUTH private lab writes year
    first (B 22/3700): read that way when the site is LASUTH, or when year-last would give an
    impossible year. A B number with the site unknown and both readings possible is flagged
    'ambiguous_b'."""
    raw = "" if raw is None else str(raw)
    s = raw.strip().upper()
    gone = _missing_reason(s)
    if gone:
        return HistologyNumber(raw, missing=gone)
    site = site_code(site) if site else None
    s = re.sub(r"\s+", " ", s)
    flags = set()

    last = re.match(r"^([A-Z]{0,3})\s*[./-]?\s*(\d{1,6})\s*[/|\-.]\s*(\d{2}|\d{4})$", s)
    first = re.match(r"^([A-Z]{1,3})\s*[./-]?\s*(\d{2})\s*[/|]\s*(\d{3,6})$", s)
    year_last = (last.group(1), int(last.group(2)), _year2(last.group(3))) if last else None
    year_first = (first.group(1), int(first.group(3)), _year2(first.group(2))) if first else None

    if year_last and year_last[2] is None:
        year_last = None
    if year_first and (site == "LASUTH" or year_last is None):
        flags.add("year_first")
        prefix, number, year = year_first
    elif year_last:
        prefix, number, year = year_last
        if year_first and year_first[0] == "B" and site is None:
            flags.add("ambiguous_b")
    else:
        return HistologyNumber(raw, flags=frozenset({"unrecognised_format"}))
    return HistologyNumber(raw, prefix, number, year, frozenset(flags))


def split_histology(raw) -> list[str]:
    """One field sometimes holds several numbers: 'H123/21, H456/22'."""
    return [p.strip() for p in re.split(r"[,;]|\s+AND\s+", str(raw or ""), flags=re.I)
            if p.strip()]


def compare_histology(a: HistologyNumber, b: HistologyNumber) -> str | None:
    """exact / exact_no_prefix (one side written without its letter) — the same specimen;
    year_differs / prefix_differs / one_digit — a likely typo; None otherwise.
    A shared histology number links records about one specimen, not necessarily one person."""
    if a.key is None or b.key is None:
        return None
    if a.key == b.key:
        return "exact"
    same_num, same_year = a.number == b.number, a.year == b.year
    if same_num and same_year:
        return "exact_no_prefix" if not a.prefix or not b.prefix else "prefix_differs"
    if same_num and a.prefix == b.prefix and a.year is not None and b.year is not None \
            and abs(a.year - b.year) in (1, 99):
        return "year_differs"
    if same_year and a.prefix == b.prefix and _one_edit(str(a.number), str(b.number)):
        return "one_digit"
    return None


# --- names -------------------------------------------------------------------------------------

TITLES = {"mr", "mrs", "miss", "ms", "dr", "prof", "chief", "alhaji", "alhaja", "mallam",
          "pastor", "rev", "sir", "madam", "master", "baby", "late"}


def name_tokens(*parts) -> list[str]:
    """Lowercase, accent-free name words, titles dropped: ('Mrs. Adébáyọ̀', 'BELLO') -> ['adebayo', 'bello']."""
    text = " ".join(str(p or "") for p in parts)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return [t for t in re.split(r"[^a-z]+", text) if t and t not in TITLES]


def jaro_winkler(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    window = max(max(len(a), len(b)) // 2 - 1, 0)
    a_hit, b_hit = [False] * len(a), [False] * len(b)
    matches = 0
    for i, ch in enumerate(a):
        for j in range(max(0, i - window), min(len(b), i + window + 1)):
            if not b_hit[j] and b[j] == ch:
                a_hit[i] = b_hit[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    a_m = [c for c, h in zip(a, a_hit) if h]
    b_m = [c for c, h in zip(b, b_hit) if h]
    transpositions = sum(x != y for x, y in zip(a_m, b_m)) / 2
    jaro = (matches / len(a) + matches / len(b) + (matches - transpositions) / matches) / 3
    prefix = 0
    for x, y in zip(a[:4], b[:4]):
        if x != y:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


VARIANT = 0.88      # tokens at least this similar count as a spelling variant
UNRELATED = 0.70    # below this for every pairing, the names share nothing


def _token_match(x: str, y: str) -> str | None:
    if x == y:
        return "exact"
    if (len(x) == 1 and y.startswith(x)) or (len(y) == 1 and x.startswith(y)):
        return "initial"
    if jaro_winkler(x, y) >= VARIANT:
        return "variant"
    return None


def compare_names(a, b) -> tuple[str, str]:
    """Compare two names given as (first, last) pairs or plain strings.

    Returns (verdict, reason): verdict is 'same', 'different' or 'ambiguous' — ambiguous ones are
    what the linkage skill hands to a person (or to the in-session Haiku step). Reasons: exact,
    swapped, variant, initial, partial, unrelated, missing."""
    ta = name_tokens(*a) if isinstance(a, (tuple, list)) else name_tokens(a)
    tb = name_tokens(*b) if isinstance(b, (tuple, list)) else name_tokens(b)
    if not ta or not tb:
        return ("ambiguous", "missing")
    if ta == tb:
        return ("same", "exact")
    if sorted(ta) == sorted(tb):
        return ("same", "swapped")
    short, long_ = sorted((ta, tb), key=len)
    kinds, used = [], set()
    for x in short:
        best = None
        for j, y in enumerate(long_):
            if j in used:
                continue
            k = _token_match(x, y)
            if k and (best is None or ["exact", "variant", "initial"].index(k)
                      < ["exact", "variant", "initial"].index(best[1])):
                best = (j, k)
        if best:
            used.add(best[0])
            kinds.append(best[1])
    if not kinds:
        top = max(jaro_winkler(x, y) for x in ta for y in tb)
        return ("different", "unrelated") if top < UNRELATED else ("ambiguous", "partial")
    if len(kinds) < len(short):
        return ("ambiguous", "partial")
    if "initial" in kinds:
        return ("ambiguous", "initial")
    if "variant" in kinds:
        return ("ambiguous", "variant")
    return ("ambiguous", "partial")     # all of the shorter name found inside a longer one


# --- one pair of records -----------------------------------------------------------------------

AGREE = {"exact", "suffix_differs", "leading_zero", "exact_no_prefix"}
TYPO = {"one_digit", "transposed", "digit_missing", "year_differs", "prefix_differs"}


@dataclass
class PairFinding:
    hospital: str | None              # compare_hospital result
    histology: str | None             # best compare_histology result across the two records
    names: tuple[str, str]            # compare_names result
    kind: str                         # 'agree', 'near_miss', 'conflict' or 'unrelated'
    explain: str                      # one plain sentence for a reviewer or an RA


def compare_pair(a: dict, b: dict) -> PairFinding:
    """Compare two records: dicts with any of site, hospital_number, histology (str or list),
    first_name, last_name. The kinds:
      agree      — the keys present agree (names included);
      near_miss  — keys agree except one that differs by a likely typo: an RA worklist row;
      conflict   — a key agrees but the names share nothing: wrong patient or a reused number;
      unrelated  — nothing ties them."""
    ha = hospital_number(a.get("hospital_number"), a.get("site"))
    hb = hospital_number(b.get("hospital_number"), b.get("site"))
    hosp = compare_hospital(ha, hb)

    def hist(rec):
        vals = rec.get("histology") or []
        vals = vals if isinstance(vals, (list, tuple)) else split_histology(vals)
        return [histology_number(v, rec.get("site")) for v in vals]
    rank = ["exact", "exact_no_prefix", "year_differs", "prefix_differs", "one_digit"]
    hits = [compare_histology(x, y) for x in hist(a) for y in hist(b)]
    hits = [h for h in hits if h]
    histo = min(hits, key=rank.index) if hits else None

    names = compare_names((a.get("first_name"), a.get("last_name")),
                          (b.get("first_name"), b.get("last_name")))
    keys = [k for k in (hosp, histo) if k]
    agree = [k for k in keys if k in AGREE]
    typo = [k for k in keys if k in TYPO]
    name_ok = names[0] == "same" or names[1] in ("variant", "initial")

    if agree and names == ("different", "unrelated"):
        return PairFinding(hosp, histo, names, "conflict",
                           "Same number but the names share nothing: wrong patient or a reused number.")
    if hosp == "different_site" and name_ok:
        return PairFinding(hosp, histo, names, "near_miss",
                           "Same hospital number recorded at two hospitals: which is right?")
    if agree and name_ok and not typo:
        return PairFinding(hosp, histo, names, "agree", "The keys agree.")
    if agree and not typo and names[1] == "missing":
        # One side has no names (a pathology database): the numbers are all there is.
        return PairFinding(hosp, histo, names, "agree", "The numbers agree; no names to compare.")
    if (agree and typo) or (typo and name_ok):
        what = {"one_digit": "differ in one digit", "transposed": "have two digits swapped",
                "digit_missing": "differ by a missing digit", "year_differs": "differ in the year",
                "prefix_differs": "differ in the letter prefix"}[typo[0]]
        which = "Hospital numbers" if hosp in TYPO else "Histology numbers"
        return PairFinding(hosp, histo, names, "near_miss",
                           f"Same patient? {which} {what}. Check the chart and correct REDCap.")
    if agree and names[0] == "ambiguous":
        return PairFinding(hosp, histo, names, "near_miss",
                           f"Numbers agree; names need a check ({names[1]}).")
    return PairFinding(hosp, histo, names, "unrelated", "Nothing ties these records.")
