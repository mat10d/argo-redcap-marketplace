"""Per-RA Markdown summary: what we're pushing AND what's still open.

Reads:
  push_drafts/<site>_<workbook>.csv   — staged updates per (site, workbook)
  RA_questions.md                     — open items, expected to use ## <SITE> headers
  REDCap metadata                     — used to translate codes back to labels

Writes:
  RA_summaries/<site>.md              — one file per site, sent back to the RA

For each site, the summary has two sections:
  1. "Changes we're making to REDCap based on your responses"
  2. "Questions for you" (extracted from RA_questions.md matching the site name)

Code translation:
  - radio/dropdown: numeric code → label (e.g. m_score=-888 → "Missing in case notes")
  - checkbox: field___N=1 → "checked: <label>", field___N=0 → "unchecked: <label>"
  - Negative checkbox codes use 4 underscores (field____888 → option -888)

Usage:
  python3 summarize_for_ra.py --url $REDCAP_URL --token-env CRC_TOKEN \\
    --push-drafts push_drafts/ --questions RA_questions.md \\
    --out RA_summaries/ [--round-label "2026-05-24"]
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import re
import sys
from io import StringIO

import requests


def load_metadata(url: str, token: str) -> dict:
    r = requests.post(url, data={"token": token, "content": "metadata",
                                  "format": "csv", "returnFormat": "json"}, timeout=120)
    r.raise_for_status()
    return {m["field_name"]: m for m in csv.DictReader(StringIO(r.text))}


def _choices(meta_row: dict) -> dict:
    out = {}
    for part in (meta_row.get("select_choices_or_calculations", "") or "").split("|"):
        if "," in part:
            c, l = part.split(",", 1)
            out[c.strip()] = l.strip()
    return out


def _label_for_field(meta_row: dict) -> str:
    lbl = re.sub(r"\s+", " ", meta_row.get("field_label", "") or "").strip().rstrip(" ?.:;")
    return lbl or meta_row.get("field_name", "")


def _parse_col(col: str, meta_by: dict) -> tuple:
    """(base_field, choice_code_or_None) for both `f___N` and `f____N` forms."""
    if col in meta_by:
        return col, None
    # negative code form first (4 underscores)
    m = re.match(r"^(.+)____(\d+)$", col)
    if m:
        return m.group(1), "-" + m.group(2)
    m = re.match(r"^(.+)___(.+)$", col)
    if m:
        return m.group(1), m.group(2)
    return col, None


def _render_record_changes(rid: str, row: dict, meta_by: dict, id_field: str) -> list:
    """One bullet list of human-readable changes for a record's row."""
    # Group by base field, accumulate checkbox toggles
    bullets = []
    grouped = {}
    for col, val in row.items():
        if col == id_field or val == "":
            continue
        base, code = _parse_col(col, meta_by)
        m = meta_by.get(base)
        if not m:
            bullets.append(f"  - `{col}` → `{val}`  *(field not in metadata)*")
            continue
        ftype = m.get("field_type", "")
        flabel = _label_for_field(m)
        choices = _choices(m)
        if code is None:
            # scalar (radio/dropdown/text/date)
            if ftype in ("radio", "dropdown", "yesno"):
                label = choices.get(val, val)
                bullets.append(f"  - **{flabel}**: → `{val}` ({label})")
            else:
                bullets.append(f"  - **{flabel}**: → `{val}`")
        else:
            # checkbox toggle
            verb = "checked" if val == "1" else ("unchecked" if val == "0" else f"set to {val}")
            label = choices.get(code, code)
            grouped.setdefault(flabel, []).append(f"{verb}: `{code}` ({label})")
    # Merge checkbox toggles into one bullet per field
    for flabel, toggles in grouped.items():
        bullets.append(f"  - **{flabel}**: " + "; ".join(toggles))
    return bullets


def _primary_field(row: dict, meta_by: dict, id_field: str) -> str:
    """The first base field touched in a row — used to group records by topic."""
    for col, val in row.items():
        if col == id_field or val == "":
            continue
        base, _ = _parse_col(col, meta_by)
        return base
    return ""


def parse_push_drafts(push_dir: str, meta_by: dict, id_field: str) -> dict:
    """{site_lower: {workbook: {primary_field: [(record_id, [bullets...]), ...]}}}"""
    out = {}
    for fn in sorted(os.listdir(push_dir)):
        if not fn.endswith(".csv"):
            continue
        site, _, workbook = fn[:-4].partition("_")
        if not workbook:
            workbook = ""
        with open(os.path.join(push_dir, fn)) as f:
            r = csv.DictReader(f)
            for row in r:
                rid = row.get(id_field, "").strip()
                if not rid:
                    continue
                bullets = _render_record_changes(rid, row, meta_by, id_field)
                if not bullets:
                    continue
                primary = _primary_field(row, meta_by, id_field)
                (out.setdefault(site.lower(), {})
                    .setdefault(workbook, {})
                    .setdefault(primary, [])
                    .append((rid, bullets)))
    return out


def parse_questions(qpath: str) -> dict:
    """{site_lower: markdown_text} — splits on `## <SITE>` headers."""
    if not os.path.exists(qpath):
        return {}
    text = open(qpath).read()
    out = {}
    # Split on '## ' at line start
    parts = re.split(r"\n## ", "\n" + text)
    for chunk in parts[1:]:
        first_line, _, body = chunk.partition("\n")
        site = first_line.strip().split()[0].lower() if first_line.strip() else ""
        if not site or site in ("(other", "—"):
            continue
        out.setdefault(site, "").strip()
        out[site] = (out.get(site, "") + "\n" + body).strip()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--token-env", required=True)
    ap.add_argument("--push-drafts", default="push_drafts")
    ap.add_argument("--questions", default="RA_questions.md")
    ap.add_argument("--out", default="RA_summaries")
    ap.add_argument("--round", dest="round_tag", default=None,
                    help="Round label appended to --out and --push-drafts so reruns don't overwrite. Defaults to today's date (YYYY-MM-DD). Pass '--round=' to disable.")
    ap.add_argument("--round-label", default="",
                    help="Optional display label for the round, shown in the summary heading (defaults to --round value)")
    ap.add_argument("--id-field", default="research_number")
    args = ap.parse_args()
    if args.round_tag is None:
        args.round_tag = _dt.date.today().isoformat()
    if args.round_tag:
        args.out = os.path.join(args.out, args.round_tag)
        # Per-round push_drafts subdir if it exists; otherwise fall back to flat.
        candidate = os.path.join(args.push_drafts, args.round_tag)
        if os.path.isdir(candidate):
            args.push_drafts = candidate
        if not args.round_label:
            args.round_label = args.round_tag
        print(f"Round: {args.round_tag} → reading {args.push_drafts}/, writing {args.out}/")

    tok = os.environ.get(args.token_env)
    if not tok:
        sys.exit(f"Env var {args.token_env} is not set")

    meta_by = load_metadata(args.url, tok)
    changes = parse_push_drafts(args.push_drafts, meta_by, args.id_field)
    questions = parse_questions(args.questions)

    sites = sorted(set(changes) | set(questions))
    os.makedirs(args.out, exist_ok=True)
    label = f" ({args.round_label})" if args.round_label else ""

    for site in sites:
        path = os.path.join(args.out, f"{site}.md")
        lines = [f"# QA summary — {site.upper()}{label}", ""]
        site_changes = changes.get(site, {})
        if site_changes:
            lines.append("## Changes we're making to REDCap based on your responses")
            lines.append("")
            for workbook, field_groups in site_changes.items():
                lines.append(f"### {workbook or '(unnamed workbook)'}")
                lines.append("")
                # Order groups by record count descending (biggest topics first)
                for primary in sorted(field_groups, key=lambda f: -len(field_groups[f])):
                    records = field_groups[primary]
                    meta = meta_by.get(primary, {})
                    fname = _label_for_field(meta) if meta else primary
                    lines.append(f"#### {fname} — {len(records)} record"
                                 + ("s" if len(records) != 1 else ""))
                    lines.append("")
                    for rid, bullets in records:
                        lines.append(f"- **{rid}**")
                        lines.extend(bullets)
                    lines.append("")
        else:
            lines.append("## Changes we're making to REDCap based on your responses")
            lines.append("")
            lines.append("*(none queued for push this round)*")
            lines.append("")

        qbody = questions.get(site, "").strip()
        if qbody:
            lines.append("## Questions for you")
            lines.append("")
            lines.append(qbody)

        with open(path, "w") as f:
            f.write("\n".join(lines).rstrip() + "\n")
        n_chg = sum(len(recs)
                    for workbook_groups in site_changes.values()
                    for recs in workbook_groups.values())
        n_q = qbody.count("### ") if qbody else 0
        print(f"  wrote {path}  ({n_chg} record-changes, {n_q} open questions)")


if __name__ == "__main__":
    main()
