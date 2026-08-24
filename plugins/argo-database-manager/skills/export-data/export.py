#!/usr/bin/env python3
"""Download things out of a REDCap study — records, the data dictionary, or both.

Everything is saved as a file on your computer. Nothing in this script changes anything in
REDCap; it only reads. (Importing is a separate, more careful path — see the SKILL.md.)

Usage (the script finds your settings file itself — nothing to load first):

    # See what a key opens, without downloading anything
    python3 export.py --token-env CRC_TOKEN --info

    # The usual thing: records + data dictionary into a dated folder
    python3 export.py --token-env CRC_TOKEN --out database-manager/exports/crc

    # Just the data dictionary
    python3 export.py --token-env CRC_TOKEN --out database-manager/exports/crc --what metadata

    # Only some forms
    python3 export.py --token-env CRC_TOKEN --out database-manager/exports/crc \\
        --forms demographics,followup

One run saves the whole set, so nobody has to pick an encoding before knowing what they need:

    <slug>_datadictionary_<date>.csv                  the field list
    <slug>_records_raw_<date>.csv                     codes (1, 2) — what the ARGO tools read
    <slug>_records_labelled_<date>.csv                the same records, labels — for reading
    <slug>_records_deidentified_raw_<date>.csv       \\ the same again, with every field the
    <slug>_records_deidentified_labelled_<date>.csv  / dictionary flags as an identifier removed
    <slug>_records_labelled_tidy_<date>.csv           labelled, checkbox options one per field
    README.md                                         what each file is, which is safe to share

`--only-raw` / `--only-labelled` narrow the records files; `--what` picks records vs dictionary.
The de-identified copies are written only when the dictionary actually flags something: an
identical file under a name promising de-identification is worse than no file at all, so when
nothing is flagged the README says that instead.

A relative `--out` is taken as relative to the folder your ARGO settings file lives in — your ARGO
folder — not to whatever directory the command happened to run from. Absolute paths are used
exactly as given.

A note on identifiable data: REDCap decides how much you can see at all from the permissions of
the account the access key belongs to. The de-identified copy drops the fields REDCap's own data
dictionary marks with `Identifier?` — a filter, not a judgement: a field nobody flagged is still
in it. For an extract de-identified at source, ask your REDCap administrator for a key tied to an
account whose export rights are set to "De-Identified". Either way, open the file and check it
before sharing it with anyone.

If there's no access key for the study yet, the script says so and explains where a key goes —
your ARGO settings file, never the chat. Without one, the records and the dictionary can be
downloaded from the REDCap website by hand (see access-tiers.md, Tier 2), and every ARGO tool
reads those — as long as the website download is the **raw data** one, which is what the raw file
here is too. The website also offers a labelled export; that is a different file, and the tools
don't want it.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from datetime import datetime, timezone
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
from argo_redcap_client import RedcapClient, RedcapError, load_env_file  # noqa: E402


def no_token_advice(setting_name: str = "CRC_TOKEN") -> str:
    """What to do about a missing key: add one, or download the files by hand.

    Downloading an export is the whole point of this script, so the first thing offered is the
    key — added to the settings file, never typed into a chat. The website route stays here for
    anyone who can't get a key: no ARGO workflow may depend on having one.
    """
    return (
        "If you do have a key for this study, it belongs in your ARGO settings file — the file\n"
        "called .env inside your ARGO folder. The quickest way there: open the ARGO folder and\n"
        "double-click 'Add keys here', which opens that file in a text editor. Add a line reading\n"
        f"    {setting_name}=<the key your REDCap administrator gave you>\n"
        "save the file, and run this again. Never type a key into a chat message — it stays in\n"
        "the transcript.\n"
        "\n"
        "If you can't get a key, nothing is blocked: the same two files can be downloaded from the\n"
        "REDCap website by hand, and every ARGO tool reads them happily — as long as you pick the\n"
        "raw version of the data export, which is the one this script saves.\n"
        "\n"
        "  1. Open the study in REDCap in your web browser.\n"
        "  2. For the data: go to 'Data Exports, Reports, and Stats', choose 'All data', and export\n"
        "     it as CSV. When it asks about the format, choose 'CSV / Microsoft Excel (raw data)'\n"
        "     — raw means the codes REDCap stores (1, 2), not the labels ('Male', 'Female').\n"
        "  3. For the field list: go to the 'Data Dictionary' page and download it as CSV.\n"
        "\n"
        "Save both files somewhere you'll find them again, then point the analysis tools at them."
    )


def human_size(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "bytes" else f"{n / 1:,.1f} {unit}"
        n /= 1024
    return f"{n} bytes"


def count_rows(text: str, id_column: str | None = None) -> "tuple[int, int]":
    """(data rows, distinct ids) in a CSV, counted with a real CSV parser.

    Physical lines are NOT rows. A free-text field containing a line break spans several lines
    of the file, and counting those told one user their export held 2,143 patients when it
    actually held 1,525 — a number they would have put in a paper. csv.reader understands the
    quoting rules that make a value span lines; `text.count("\\n")` does not.

    `id_column` names the record-ID column; when it's given, the second number is how many
    distinct ids appear, which is how repeat-instrument rows show up (more rows than ids).
    """
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return 0, 0
    try:
        id_index = header.index(id_column) if id_column else -1
    except ValueError:
        id_index = -1
    rows = 0
    ids = set()
    for row in reader:
        if not row or (len(row) == 1 and not row[0].strip()):
            continue          # a trailing blank line is not a record
        rows += 1
        if id_index >= 0 and id_index < len(row):
            ids.add(row[id_index])
    return rows, (len(ids) if id_index >= 0 else rows)


def describe_count(rows: int, ids: int, unit: str, id_column: "str | None") -> str:
    """How many things are in this file, in words that don't over-claim.

    "Patients" is only said when the id column proves it: one row per id. A project with repeat
    instruments has more rows than patients, and the phrase says both numbers rather than
    quietly conflating them.
    """
    if id_column and ids and rows != ids:
        return f"{rows:,} {unit} across {ids:,} patients"
    if id_column and ids:
        return f"{rows:,} {unit} — one per patient"
    return f"{rows:,} {unit}"


def write_file(path: Path, text: str, label: str, unit: str = "rows",
               id_column: str | None = None, encoding_note: str = "") -> dict:
    """Save one downloaded file, say plainly what landed in it, and describe it for the README.

    The count is of real CSV rows, never physical lines, and `unit` names what a row IS in this
    particular file — fields in a data dictionary, records in an export.
    """
    path.write_text(text)
    size = path.stat().st_size
    rows, ids = count_rows(text, id_column)
    count = describe_count(rows, ids, unit, id_column)
    suffix = f" {encoding_note}" if encoding_note else ""
    print(f"  Saved {label}{suffix}: {path.name}  ({count}, {human_size(size)})")
    return {"name": path.name, "label": label, "encoding": encoding_note.strip("() ") or "—",
            "count": count, "rows": rows, "ids": ids, "size": human_size(size)}


RAW_NOTE = "raw codes"
LABELLED_NOTE = "readable labels"

# What REDCap writes in the data dictionary's `identifier` column when a field is flagged as
# identifiable. Only 'y' is used in practice; the rest are accepted so a hand-edited dictionary
# can't quietly un-flag a name or a hospital number.
IDENTIFIER_YES = {"y", "yes", "1", "true"}


def field_flags(dd_csv_text: str) -> "tuple[list, list]":
    """(identifier fields, checkbox fields) read from the data dictionary.

    The dictionary is the only thing that knows which fields carry a name, a hospital number or
    an address — REDCap has no other way to tell, and neither do we. Reading it here means the
    de-identified file below is derived from the project's own declaration rather than from a
    guess about column names.
    """
    identifiers, checkboxes = [], []
    for row in csv.DictReader(io.StringIO(dd_csv_text or "")):
        name = (row.get("field_name") or "").strip()
        if not name:
            continue
        if (row.get("identifier") or "").strip().lower() in IDENTIFIER_YES:
            identifiers.append(name)
        if (row.get("field_type") or "").strip().lower() == "checkbox":
            checkboxes.append(name)
    return identifiers, checkboxes


def _columns_for(header: list, fields: list) -> set:
    """Indices of the columns belonging to these fields, checkbox option columns included.

    A checkbox field `ethnicity` is exported as `ethnicity___1`, `ethnicity___2`, … (and
    `ethnicity____888` for a negative code). Dropping only the exact name would leave every
    option column behind, which for an identifier is the whole problem.
    """
    wanted = set(fields)
    return {i for i, col in enumerate(header)
            if col in wanted or any(col.startswith(f"{f}___") for f in wanted)}


def drop_fields(csv_text: str, fields: list) -> str:
    """The same CSV with the named fields removed, columns and all."""
    rows = list(csv.reader(io.StringIO(csv_text)))
    if not rows:
        return csv_text
    drop = _columns_for(rows[0], fields)
    if not drop:
        return csv_text
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for row in rows:
        writer.writerow([v for i, v in enumerate(row) if i not in drop])
    return buf.getvalue()


def collapse_checkboxes(csv_text: str, checkbox_fields: list) -> "str | None":
    """One column per checkbox field instead of one per option, for reading by eye.

    A labelled export writes the chosen option's label into `field___N` and leaves the others
    blank, so a five-option checkbox eats five columns of a spreadsheet to say one thing. This
    joins them back into `field` with "; " between the ticked ones. Returns None when the export
    has no checkbox columns at all, so no pointless duplicate file is written.

    A convenience view only — never a replacement for the two originals, which are what the
    tools read.
    """
    rows = list(csv.reader(io.StringIO(csv_text)))
    if not rows:
        return None
    header = rows[0]
    groups: dict = {}
    for i, col in enumerate(header):
        for base in checkbox_fields:
            if col.startswith(f"{base}___"):
                groups.setdefault(base, []).append(i)
                break
    if not groups:
        return None
    first = {cols[0]: base for base, cols in groups.items()}
    members = {i for cols in groups.values() for i in cols}

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for n, row in enumerate(rows):
        out = []
        for i, value in enumerate(row):
            if i in first:
                if n == 0:
                    out.append(first[i])
                else:
                    ticked = [str(row[j]).strip() for j in groups[first[i]]
                              if j < len(row) and str(row[j]).strip()]
                    out.append("; ".join(ticked))
            elif i not in members:
                out.append(value)
        writer.writerow(out)
    return buf.getvalue()


def write_readme(out: Path, title: str, pid, stamp: str, id_field: str,
                 entries: list, identifiers: "list | None" = None) -> Path:
    """A README.md in the export folder saying what each file is.

    An export folder with three near-identically-named CSVs in it is a puzzle a week later, and
    "which one do I give the analysis?" is exactly the question that gets answered wrong. So the
    answer ships next to the files, in the folder, where the person opening it will see it —
    including the row counts, so a truncated or half-downloaded file is obvious.
    """
    lines = [
        f"# Export — {title}",
        "",
        f"REDCap project {pid}. Downloaded {stamp}. The column identifying each record is "
        f"`{id_field}`.",
        "",
        "| File | What it is | Encoding | Size |",
        "|---|---|---|---|",
    ]
    for e in entries:
        lines.append(f"| `{e['name']}` | {e['label']}, {e['count']} | {e['encoding']} | "
                     f"{e['size']} |")
    lines += [
        "",
        "## Which one do I use?",
        "",
        "**The raw file** — the one named `..._records_raw_<date>.csv`. ARGO's QA and analysis "
        "tools read the codes REDCap stores (`1`, `2`) and turn them into words themselves, "
        "using the data dictionary in this folder. The labelled file holds the same records with "
        "those codes already written out (`Male`, `Female`) — it is for reading by eye, and it "
        "is the wrong input for the tools, which would treat the labels as unknown values.",
        "",
        "Every records file here contains the same rows. Row counts above are real CSV rows: a "
        "free-text answer containing a line break spans several lines of the file, so counting "
        "lines overstates them.",
        "",
        "## Which one is safe to share?",
        "",
    ]
    deidentified = [e for e in entries if "deidentified" in e["name"]]
    if deidentified and identifiers:
        lines += [
            "**The `_deidentified_` files, and only those.** Every field the data dictionary "
            "marks as an identifier has been removed from them, columns and all:",
            "",
        ]
        lines += [f"- `{name}`" for name in identifiers]
        lines += [
            "",
            "Read that list before you rely on it. It is REDCap's own `Identifier?` flag, which "
            "someone had to tick when the field was created — a field nobody flagged is still "
            "in these files even if its contents identify a person (a free-text note naming a "
            "relative, a rare diagnosis in a small district). De-identification is a judgement, "
            "not a column filter; this is the filter, and you are the judgement.",
        ]
    elif identifiers is not None and not identifiers:
        lines += [
            "**None of these files has been de-identified, because the data dictionary marks no "
            "field as an identifier.** No `_deidentified_` copy was written — it would have been "
            "byte-for-byte the same file under a name promising something it hadn't done.",
            "",
            "That is a statement about the dictionary, not about the data. If this project holds "
            "names, hospital numbers or addresses, the fields carrying them have not been "
            "flagged in REDCap, and someone should fix that in the Designer (the `Identifier?` "
            "column) before this export is shared.",
        ]
    else:
        lines += ["No records were exported in this run, so there is nothing to de-identify."]
    lines += [
        "",
        "## Handle with care",
        "",
        "These files may contain identifiable patient data. What an export contains at all is "
        "decided by the permissions of the account the access key belongs to. Check any file "
        "before sharing it with anyone.",
        "",
    ]
    path = out / "README.md"
    path.write_text("\n".join(lines))
    print("  Saved README.md: says what each file is, how many records it holds, which one the "
          "QA and\n    analysis tools read (the raw one), and which one is safe to share.")
    return path


def resolve_out(out: str, settings_file: "Path | None") -> Path:
    """Where `--out` actually points.

    An absolute path (or one starting with ~) is used exactly as given. A relative one is
    measured from the folder holding the ARGO settings file — the user's ARGO folder — because
    that is where the rest of their work lives and where they will go looking for the export.
    Measuring from the working directory instead put files wherever the session happened to be
    standing, which in a Cowork session is nowhere the user can see. With no settings file
    anywhere, there is nothing better to anchor on, so the working directory stands.
    """
    path = Path(out).expanduser()
    if path.is_absolute() or settings_file is None:
        return path
    return (Path(settings_file).resolve().parent / path)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Download records and/or the data dictionary from a REDCap study.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=no_token_advice(),
    )
    ap.add_argument("--token-env", required=True,
                    help="The name of the setting that holds your access key for this study, "
                         "e.g. CRC_TOKEN")
    ap.add_argument("--out", help="Folder to save the downloaded files into — normally "
                                  "database-manager/exports/<study>. A relative path is taken "
                                  "from your ARGO folder (where your settings file lives), not "
                                  "from wherever you ran this")
    ap.add_argument("--what", choices=["records", "metadata", "both"], default="both",
                    help="What to download. Default: both")
    ap.add_argument("--forms", help="Only these forms, comma-separated (default: all forms)")
    # Both encodings are saved by default, so there is no question to ask and no wrong answer to
    # give. These narrow it when someone knows they want only one.
    only = ap.add_mutually_exclusive_group()
    only.add_argument("--only-raw", action="store_true",
                      help="Save only the raw-codes records file, not the labelled one")
    only.add_argument("--only-labelled", action="store_true",
                      help="Save only the labelled records file, not the raw one")
    # Accepted and hidden: commands saved before both encodings became the default still run,
    # meaning what they meant then, instead of dying on an unrecognised argument.
    ap.add_argument("--raw", dest="only_raw", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--labels", dest="only_labelled", action="store_true",
                    help=argparse.SUPPRESS)
    ap.add_argument("--info", action="store_true",
                    help="Just say which project this key opens, and stop")
    ap.add_argument("--expect-project", metavar="NAME_OR_PID",
                    help="Refuse to download unless the key opens this project, by name or number")
    args = ap.parse_args()
    if args.only_raw and args.only_labelled:
        # Only reachable through the two hidden legacy flags together. Asking for only-raw and
        # only-labelled is asking for both, not for nothing.
        args.only_raw = args.only_labelled = False

    # Load the settings file ourselves, and keep hold of WHERE it was: its folder is the ARGO
    # folder, and that is what a relative --out is measured from. Anchoring on the working
    # directory instead scattered exports wherever a session happened to be standing.
    settings_file = load_env_file()

    client = RedcapClient.from_env(args.token_env)
    if client is None:
        print(RedcapClient.explain_missing_token(
            args.token_env, "download anything from this study",
            fallback=no_token_advice(args.token_env)))
        return 1

    try:
        info = client.project_info()
        title = (info.get("project_title") or "?").strip()
        pid = info.get("project_id", "?")

        if args.expect_project:
            expect = str(args.expect_project).strip()
            client.confirm_project(
                expect_title=None if expect.isdigit() else expect,
                expect_pid=expect if expect.isdigit() else None,
            )

        id_field = client.record_id_field()
        print(f"Study: {title!r} (project {pid})")
        print(f"The column identifying each record is called {id_field!r}.")

        if args.info:
            forms = sorted({f.get("form_name", "") for f in client.export_metadata()} - {""})
            print(f"It has {len(forms)} form(s): {', '.join(forms)}")
            return 0

        if not args.out:
            print(
                "\nTell me where to save the download, with --out, for example:\n"
                "\n"
                f"    python3 {os.path.basename(__file__)} --token-env {args.token_env} "
                "--out database-manager/exports/<study>"
            )
            return 2

        out = resolve_out(args.out, settings_file)
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        slug = "".join(c if c.isalnum() else "-" for c in title.lower())[:40].strip("-")

        print(f"\nSaving into {out}")
        forms = [f.strip() for f in args.forms.split(",")] if args.forms else []
        form_params = {f"forms[{i}]": form for i, form in enumerate(forms)}
        entries = []

        # The dictionary is always pulled, even when only records were asked for: it is what
        # says which fields are identifiers, and the de-identified file below is derived from
        # that declaration rather than from a guess about column names. It is only SAVED when
        # it was asked for.
        dd = client.export_metadata_csv(**form_params)
        identifiers, checkboxes = field_flags(dd)

        if args.what in ("metadata", "both"):
            entries.append(write_file(out / f"{slug}_datadictionary_{stamp}.csv", dd,
                                      "data dictionary", unit="fields"))

        if args.what in ("records", "both"):
            # Both encodings, every time. They are the same records written two ways, one file
            # is worth having whichever question comes next, and asking the user to choose
            # between "raw" and "labelled" up front is asking them to know something they
            # reasonably don't. The README in the folder says which is which.
            encodings = []
            if not args.only_labelled:
                encodings.append("raw")
            if not args.only_raw:
                encodings.append("labelled")

            texts = {}
            for name in encodings:
                labelled = name == "labelled"
                params = {"rawOrLabel": "label" if labelled else "raw",
                          "exportCheckboxLabel": "true" if labelled else "false",
                          "exportDataAccessGroups": "true", **form_params}
                texts[name] = client.export_records_csv(**params)
                note = LABELLED_NOTE if labelled else f"{RAW_NOTE} — what the ARGO tools read"
                entries.append(write_file(
                    out / f"{slug}_records_{name}_{stamp}.csv", texts[name], "records",
                    unit="records", id_column=id_field, encoding_note=f"({note})"))

            # A copy with every dictionary-flagged identifier removed — the one that can leave
            # the building. Skipped entirely when the dictionary flags nothing: an identical
            # file under a name promising de-identification is worse than no file at all.
            if identifiers:
                print(f"\n  The data dictionary flags {len(identifiers)} field(s) as "
                      f"identifiers: {', '.join(identifiers)}")
                for name in encodings:
                    entries.append(write_file(
                        out / f"{slug}_records_deidentified_{name}_{stamp}.csv",
                        drop_fields(texts[name], identifiers), "records, identifiers removed",
                        unit="records", id_column=id_field,
                        encoding_note=f"({RAW_NOTE if name == 'raw' else LABELLED_NOTE})"))
            else:
                print("\n  The data dictionary flags no field as an identifier, so no "
                      "de-identified copy was\n    written — it would have been the same file "
                      "under a name promising otherwise. The\n    README says so.")

            # A convenience view: checkbox options folded back into one column each. Additional,
            # never a replacement — the two files above are what the tools read.
            if "labelled" in encodings:
                tidy = collapse_checkboxes(texts["labelled"], checkboxes)
                if tidy:
                    entries.append(write_file(
                        out / f"{slug}_records_labelled_tidy_{stamp}.csv", tidy,
                        "records, checkbox columns folded into one each",
                        unit="records", id_column=id_field,
                        encoding_note=f"({LABELLED_NOTE}, for reading by eye)"))

        if entries:
            write_readme(out, title, pid, stamp, id_field, entries,
                         identifiers if args.what in ("records", "both") else None)

        print("\nDone. Nothing in REDCap was changed — this only read data out.")
        return 0

    except RedcapError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
