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

Metadata comes from REDCap if you have the study's access key, or from the Data Dictionary
CSV you downloaded from the website if you don't — the same two ways build_worklists.py takes
its input. Nothing here needs a key.

Usage (files you downloaded — no access key needed):
  python3 summarize_for_ra.py --metadata-csv datadictionary.csv \\
    --questions RA_questions.md --out RA_summaries/ [--round-label "2026-05-24"]

Usage (with the study's access key):
  python3 summarize_for_ra.py --token-env CRC_TOKEN \\
    --questions RA_questions.md --out RA_summaries/ [--round-label "2026-05-24"]

`--push-drafts` is a migration-only input; a normal QA round has none and can leave it out.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import re
import sys
from io import StringIO
from pathlib import Path

# The shared ARGO scripts are vendored into this skill's own scripts/ folder by release.py,
# so imports never depend on where — or whether — other plugins are installed. The parents walk
# is only for running from a source checkout before the first sync.
_here = Path(__file__).resolve().parent
for _cand in (_here / "scripts",
              *(p / "plugins/argo-core/skills/redcap-api/scripts" for p in _here.parents)):
    if (_cand / "argo_redcap_client.py").exists():
        sys.path.insert(0, str(_cand))
        break
from argo_redcap_client import load_env_file  # noqa: E402


def load_metadata(url: str, token: str) -> dict:
    """Metadata from the REDCap API. `requests` is imported here, not at the top of the file,
    so the no-key path below works on a machine that has never installed it."""
    import requests

    r = requests.post(url, data={"token": token, "content": "metadata",
                                  "format": "csv", "returnFormat": "json"}, timeout=120)
    r.raise_for_status()
    return {m["field_name"]: m for m in csv.DictReader(StringIO(r.text))}


def load_metadata_file(path: str) -> dict:
    """Metadata from a Data Dictionary CSV downloaded from REDCap — the no-key path.

    build_worklists.py already reads both shapes REDCap hands out (an API metadata export,
    which already has `field_name`, and the Designer's "Download Data Dictionary" CSV, which
    has human column headers) and it lives in this same folder. Reuse it rather than keeping
    a second copy of that header map here: two copies drifting apart is precisely the failure
    this project forbids.
    """
    if not os.path.exists(path):
        sys.exit(
            f"I couldn't find the data dictionary:\n"
            f"    {path}\n"
            "\n"
            "Download it from the REDCap project's Data Dictionary page (Designer → Download\n"
            "Data Dictionary) and give me that file."
        )
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from build_worklists import load_metadata_csv
    except ImportError as e:
        sys.exit(
            "Reading a data dictionary from a file needs the same libraries the worklist\n"
            f"builder uses, and one of them isn't installed here: {e}\n"
            "\n"
            "Install them with:\n"
            "\n"
            "    python3 -m pip install pandas openpyxl pyyaml\n"
            "\n"
            "I have not written any summaries."
        )
    return {m["field_name"]: m for m in load_metadata_csv(path)}


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
    if not os.path.isdir(push_dir):
        # A normal QA round has no push_drafts at all (staging is migration-only) —
        # summaries then come from the questions file alone.
        return out
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


def site_key(header: str) -> str:
    """The site a `## ` header names, normalised: whole header, lowercased, spaces collapsed.

    It used to take the FIRST WORD, so `## Site Alpha` and `## Site Beta` both became "site" and
    one site's questions were served to every RA. The whole header is the name; only casing and
    the whitespace someone typed are ignored.
    """
    return " ".join(str(header or "").split()).lower()


def parse_questions(qpath: str, warn=print) -> dict:
    """{site_key: markdown_text} — splits on `## <SITE>` headers.

    Two headers that normalise to the same key are merged (they are the same site written
    twice), but never silently: a warning names them, because the alternative reading — two
    genuinely different sites the author expected to keep apart — would mean one RA receiving
    another site's questions.
    """
    if not os.path.exists(qpath):
        return {}
    with open(qpath) as fh:
        text = fh.read()
    out = {}
    seen_headers = {}
    # Split on '## ' at line start
    parts = re.split(r"\n## ", "\n" + text)
    for chunk in parts[1:]:
        first_line, _, body = chunk.partition("\n")
        header = first_line.strip()
        site = site_key(header)
        if not site or site.startswith("(other") or site in ("—", "-"):
            continue
        if site in seen_headers and seen_headers[site] != header:
            warn(f"  Note: the headings '## {seen_headers[site]}' and '## {header}' name the "
                 f"same site once spacing and capitals are ignored, so their questions have "
                 f"been merged into one summary. Rename one of them if they are meant to be "
                 f"different sites.")
        seen_headers.setdefault(site, header)
        out[site] = (out.get(site, "") + "\n" + body).strip()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="REDCap API URL (access-key mode)")
    ap.add_argument("--token-env", help="Name of the setting holding the access key (access-key mode)")
    ap.add_argument("--metadata-csv",
                    help="No-key mode: the Data Dictionary CSV you downloaded from REDCap")
    ap.add_argument("--records-csv",
                    help="No-key mode: the record export CSV. Accepted so the command matches "
                         "build_worklists.py; only the data dictionary is actually read here.")
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

    if args.metadata_csv:
        print(f"No-key mode: reading the data dictionary from {args.metadata_csv} ...")
        meta_by = load_metadata_file(args.metadata_csv)
    elif args.records_csv:
        sys.exit(
            "To write the RA summaries from files on your computer I need the DATA DICTIONARY,\n"
            "not the record export — the summaries translate field codes back into the wording\n"
            "the RA will recognise.\n"
            "\n"
            "Download it from the REDCap project's Data Dictionary page and pass it instead:\n"
            "\n"
            "    --metadata-csv datadictionary.csv"
        )
    elif args.token_env:
        # Load the ARGO settings file ourselves. Nothing for the user to source first, and
        # --url is only needed if their REDCap address isn't in that file already.
        load_env_file()
        url = args.url or os.environ.get("REDCAP_URL")
        tok = os.environ.get(args.token_env)
        if not tok:
            sys.exit(
        f"No access key called {args.token_env} is in your ARGO settings file, so I can't reach\n"
        "REDCap.\n"
        "\n"
        "An access key (REDCap calls it an API token) is a long password that lets a tool read\n"
        "or update one specific REDCap project on your behalf. Your REDCap administrator\n"
        "creates it for you — it isn't something you can generate yourself.\n"
        "\n"
        "If you already have one: open your ARGO folder, double-click 'Add keys here' to open\n"
        f"your settings file, add the line {args.token_env}=<your key>, save, and run this again.\n"
        "\n"
        "Or work from the data dictionary you downloaded instead — no key needed:\n"
        "\n"
        "    --metadata-csv datadictionary.csv"
    )
        if not url:
            sys.exit(
        "I have your access key, but not the web address of your REDCap system.\n"
        "\n"
        "It's a single line of text ending in /api/. Open your ARGO folder, double-click\n"
        "'Add keys here', and add it on the REDCAP_URL line:\n"
        "\n"
        "    REDCAP_URL=https://your-redcap-site.org/api/"
    )
        meta_by = load_metadata(url, tok)
    else:
        sys.exit(
            "I need the study's field definitions to write the summaries, and you haven't told\n"
            "me where to get them. There are two ways, and you only need one:\n"
            "\n"
            "  From the Data Dictionary you downloaded from REDCap (the usual way):\n"
            "      --metadata-csv datadictionary.csv\n"
            "\n"
            "  Or, if you have an access key for this study set up:\n"
            "      --token-env YOUR_STUDY_TOKEN"
        )
    changes = parse_push_drafts(args.push_drafts, meta_by, args.id_field)
    questions = parse_questions(args.questions)

    sites = sorted(set(changes) | set(questions))
    os.makedirs(args.out, exist_ok=True)
    label = f" ({args.round_label})" if args.round_label else ""

    # One file per site. A site name with spaces in it becomes underscores in the filename;
    # if two site names would land on the same file, say so rather than overwrite one with the
    # other — that would hand a whole site's questions to the wrong RA.
    filenames = {}
    for site in sites:
        stem = re.sub(r"\s+", "_", site)
        if stem in filenames:
            print(f"  Note: sites '{filenames[stem]}' and '{site}' both want the file "
                  f"{stem}.md; writing '{site}' second. Rename one of them.")
        filenames[stem] = site

    for site in sites:
        stem = re.sub(r"\s+", "_", site)
        path = os.path.join(args.out, f"{stem}.md")
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
