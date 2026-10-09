#!/usr/bin/env python3
"""setup_brief.py — generate MANUAL_SETUP_BRIEF.md for a study build from its SIR record.

Opens with the build's ONE outstanding list: the 7 Study Tracker steps in tracker order (what,
who, what it waits on, done / not done — read from the record), then every open request in the
build folder's `outstanding_requests.csv`. Below it, the details derived from the SIR: the File
Repository rename table, the Data Access Groups, the user→role table, the survey-setup clicks.

The file is regenerated whole on every run — never appended to — so it never carries a stale
status line above a newer one.

Works with or without an access key ([[token-optional]]): pulls the SIR via the API if the Study
Tracker key is set, or reads a pre-pulled record JSON (`sir_update.py <RID> --pull > rec.json`)
with --from-json.

Usage (it finds your ARGO settings file by itself — there is nothing to load first):
    python3 setup_brief.py <RID> --out database-manager/<study> [--moniker HPV_SelfSampling]
    python3 setup_brief.py <RID> --from-json rec.json --out database-manager/<study> --moniker HPV_SelfSampling
"""
import argparse, json, os, re, sys, datetime, urllib.parse, urllib.request
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
from argo_trackers import SIR_BUILD_STEPS, PROGRESS_NOT_DONE  # noqa: E402

def pull(rid):
    load_env_file()          # the settings file loads itself; nothing to source by hand
    url=os.environ.get("REDCAP_URL"); tok=os.environ.get("STUDY_INITIATION_REQUEST")
    if not (url and tok):
        sys.exit("The REDCap address (REDCAP_URL) or the Study Tracker access key\n"
                 "(STUDY_INITIATION_REQUEST) isn't in your ARGO settings file yet. Add them —\n"
                 "open your ARGO folder and double-click 'Add keys here' — or work from a\n"
                 "pre-pulled record instead: sir_update.py <RID> --pull > rec.json, then pass\n"
                 "--from-json rec.json.")
    data=urllib.parse.urlencode({"token":tok,"content":"record","format":"json","records[0]":rid}).encode()
    recs=json.loads(urllib.request.urlopen(urllib.request.Request(url,data=data,method="POST"),timeout=60).read())
    if not recs: sys.exit(f"SIR record {rid} not found.")
    return recs[0]

# doc field -> File Repository folder
def repo_folder(field):
    return "IRB and Ethics" if ("irb_file" in field or "consent" in field) else "Study Documents"

# Stems for the document fields the SIR carries. Site-numbered fields (`_1`.. `_10`) take
# their site tag from the SIR's own institution list — never from a hardcoded site name.
DOC_STEMS = {"quest_univ_file": "Questionnaire", "quest_site": "Questionnaire",
             "sop": "SOP", "eligibility_checklist": "ECL",
             "irb_file": "IRB", "consent_file": "Consent",
             "consent_prof": "ConsentProfessional"}
SITE_STOPWORDS = {"of", "and", "the", "for", "de", "du", "des", "la", "le", "el"}


def site_names(rec):
    """{'1': 'Korle Bu Teaching Hospital', ...} from the SIR's inst_name_1..10 fields."""
    out = {}
    for f, v in rec.items():
        m = re.fullmatch(r"inst_name_(\d+)", f)
        if m and str(v).strip():
            out[m.group(1)] = str(v).strip()
    return out


def site_token(name):
    """Short filename-safe tag for an institution, derived from that institution's own name:
    'University College Hospital (UCH)' -> UCH; 'Korle Bu Teaching Hospital' -> KBTH."""
    m = re.search(r"\(([A-Za-z][A-Za-z0-9\-]{1,15})\)", name)
    if m:
        return re.sub(r"[^A-Za-z0-9]", "", m.group(1)).upper()
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name) if w and w.lower() not in SITE_STOPWORDS]
    if not words:
        return ""
    if len(words) == 1:
        return words[0][:16]
    return "".join(w[0] for w in words).upper()[:10]


def repo_label(field, sites):
    """(filename stem, site column) for one document field. Returns a [TODO] instead of a
    site tag when the SIR names no institution for that number — never a guessed site."""
    m = re.search(r"_(\d+)$", field)
    stem_key = field[:m.start()] if m else field
    stem = DOC_STEMS.get(field) or DOC_STEMS.get(stem_key) or \
        stem_key.replace("_file", "").title().replace("_", "")
    if not m:
        return stem, "—"
    n = m.group(1)
    name = sites.get(n)
    if not name:
        return f"{stem}_[TODO site {n}]", f"[TODO] `inst_name_{n}` is blank in the SIR"
    tag = site_token(name)
    return (f"{stem}_{tag}" if tag else f"{stem}_[TODO site {n}]"), name

# The build's hard stop — the ONE list (Matteo, 2026-10-09). If any of these is missing, no data
# dictionary is drafted: no partial build, no "proceed with assumptions". build-study's SKILL.md
# names the same three, and a guard test holds the two together.
# (document, the SIR fields that carry it — empty when the SIR has no field for it)
HARD_STOP_DOCUMENTS = (
    ("questionnaire", ("quest_univ_file", "quest_site_")),
    ("protocol", ()),
    ("ethics approval letter", ("irb_file_",)),
)


def missing_hard_stop_documents(rec):
    """Hard-stop documents the SIR record shows no file for. The protocol has no SIR field, so it
    can't be checked here — the build checks the folder for it."""
    missing = []
    for name, prefixes in HARD_STOP_DOCUMENTS:
        if not prefixes:
            continue
        if not any(str(v).strip() and str(v).strip() not in ("0", "1", "2")
                   and (f == p or f.startswith(p)) for f, v in rec.items() for p in prefixes):
            missing.append(name)
    return missing


# The build's outstanding work, keyed to the Study Tracker's 7 build steps in tracker order —
# the same steps, names and order the weekly check counts (N/7). Setup work the tracker has no
# flag for (DAGs, File Repository, weekly report, survey settings) is folded into the step it
# has to be finished before, so there is ONE list and every item on it has a done/not-done state.
# (what to do, who does it). {rid} and {setup} are filled in per study.
STEP_ROWS = {
    # step: (what to do, who does it, what it waits on)
    "project_created": ("Create the project from `CREATE_NEW_PROJECT_{rid}.txt` "
                        "(REDCap → New Project). Note the PID.", "Database manager", "—"),
    "dd_uploaded": ("Upload the checked data dictionary "
                    "(Designer → Data Dictionary → Upload).", "Database manager",
                    "The three documents; DD passes `validate_dd.py`"),
    "user_rights_complete": ("Upload the roles CSV (User Rights → User Roles → Upload). "
                             "{dags}Add the users in the table below.", "Database manager",
                             "Project created"),
    "data_imported": ("{import_text}", "Database manager", "DD uploaded"),
    "review_internal": ("Finish setup: {setup}. Then check the whole build.", "ARGO internal QA",
                        "Steps above done"),
    "review_pi": ("PI checks the project and answers `OPEN_QUESTIONS.md`.", "PI",
                  "Internal QA done"),
    "study_production": ("Move to Production (Project Setup).", "Database manager",
                         "PI sign-off; IRB approval in date{irb_gap}"),
}
# Requests the user made during the build that are not tracker steps ("mark the identifiers so
# exports drop them"). They live in ONE file in the build folder, and the brief renders every
# open one into the same Outstanding table — so the closing "are we done?" can't drop one.
REQUESTS_FILE = "outstanding_requests.csv"
REQUEST_COLUMNS = ("item", "who", "waiting_on", "status")


def read_requests(folder):
    """Rows of the build folder's request list, open ones only. Missing file → none."""
    path = Path(folder) / REQUESTS_FILE
    if not path.exists():
        return [], 0
    import csv as _csv
    with open(path, newline="") as fh:
        rows = [{k: (v or "").strip() for k, v in r.items() if k} for r in _csv.DictReader(fh)]
    open_rows = [r for r in rows if r.get("item") and r.get("status", "").lower() != "done"]
    return open_rows, len(rows) - len(open_rows)


HUMAN_GATES = ("review_internal", "review_pi", "study_production")


def step_done(rec, step):
    """The tracker's own done rule (argo_trackers): any settled answer that isn't "no"."""
    return str(rec.get(step) or "").strip().lower() not in PROGRESS_NOT_DONE


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("rid"); ap.add_argument("--out",required=True,help="Folder to write the brief into — normally database-manager/<study>")
    ap.add_argument("--moniker",help="Study moniker for File Repository renames (default: PI surname)")
    ap.add_argument("--from-json",help="Use a pre-pulled record JSON instead of the API (works without an access key)")
    a=ap.parse_args()
    r=json.load(open(a.from_json)) if a.from_json else pull(a.rid)
    if isinstance(r,list): r=r[0]
    g=lambda k: str(r.get(k,"")).strip()
    mon=a.moniker or (g("pi_surname") or "STUDY")
    os.makedirs(a.out,exist_ok=True)

    # File Repository docs present on the record
    docs=[]
    for f,v in r.items():
        if any(s in f for s in ["quest_univ_file","quest_site_","sop","eligibility_checklist","irb_file_","consent_file_","consent_prof_"]) \
           and str(v).strip() and str(v).strip() not in ("0","1","2"):
            docs.append((f,v))
    missing_docs=missing_hard_stop_documents(r)
    # DAGs / sites — the SIR's institution list is the only source of site names
    sites=site_names(r)
    dags=[sites[k] for k in sorted(sites,key=int)]
    # IRB expiry check
    exp=g("irb_approval_expires"); exp_flag=""
    if exp:
        try:
            if datetime.date.fromisoformat(exp) < datetime.date.today():
                exp_flag=f"⚠️ IRB approval expired on {exp}. Get the renewal before production."
        except ValueError: pass
    # personnel
    people=[]
    if g("pi_user_name"): people.append((g("pi_user_name"),g("pi_user_email"),"Principal Investigator"))
    if g("pm_name"): people.append((g("pm_name"),g("pm_email"),"Project Manager"))
    if g("ra_name"): people.append((g("ra_name"),g("ra_email"),"Data Entry (RA)"))
    addl=g("addl_users")
    prospective = g("data_collection")=="2"
    setup=["File Repository" if docs else None, "weekly report", "survey settings (only if a survey)"]

    fill={"rid":a.rid,
          "dags":(f"Create the DAGs ({len(dags)} sites). " if dags else ""),
          "import_text":("Prospective — nothing to import. Mark it with `--set data_imported=2`." if prospective else
                         "Old data to load? Map it, check it with `validate_import.py`, import it "
                         "(Data Import Tool), then mark it. No old data? `--set data_imported=2`."),
          "setup":", ".join(x for x in setup if x),
          "irb_gap":"".join(f"; {w} missing on the SIR" for k,w in
                            (("irb_number","IRB number"),("irb_approval_expires","IRB expiry"))
                            if not g(k))}
    rows=[]
    for step in SIR_BUILD_STEPS:
        what,who,waits=STEP_ROWS[step]
        rows.append((step,what.format(**fill),who,waits.format(**fill),
                     "Done" if step_done(r,step) else "Not done"))
    n_done=sum(1 for *_,st in rows if st=="Done")
    requests,n_closed=read_requests(a.out)

    L=[]
    L.append(f"# Setup brief — SIR {a.rid}: {g('project_title')[:80]}")
    L.append(f"\nPI: {g('pi_first_name')} {g('pi_surname')} · IRB: {g('irb_number') or '—'} · "
             f"PID: {g('new_project_pid') or 'not created yet'} · Moniker: `{mon}`")
    if exp_flag: L.append(f"\n{exp_flag}")
    irb_blank=[f"`{k}` ({w})" for k,w in (("irb_number","IRB number"),
                                           ("irb_approval_expires","IRB expiry date")) if not g(k)]
    if irb_blank:
        L.append(f"\n⚠️ Blank on the SIR: {' and '.join(irb_blank)}. The PM / requester updates "
                 "it on the Study Tracker before production. It doesn't block the build.")
    needed=", ".join(n for n,_ in HARD_STOP_DOCUMENTS)
    them='it' if len(missing_docs)==1 else 'them'
    if not step_done(r,"dd_uploaded"):
        if missing_docs:
            L.append(f"\n⛔ The build can't start. Missing from the SIR: {', '.join(missing_docs)}. "
                     f"Ask the PM to send {them}.")
        L.append(f"\nNo data dictionary until all three are in the build folder: {needed}.")
    elif missing_docs:
        L.append(f"\n⚠️ Missing from the SIR: {', '.join(missing_docs)}. Get {them} before production.")

    L.append(f"\n## Outstanding — {n_done}/{len(rows)} tracker steps done, "
             f"{len(requests)} open request{'s' if len(requests)!=1 else ''}")
    L.append("\nThe 7 Study Tracker steps in tracker order (status from the Study Tracker), then "
             f"every open request from `{REQUESTS_FILE}`. This is the one list.")
    L.append("\n| Item | Who | Waiting on | Status |\n|---|---|---|---|")
    for step,what,who,waits,st in rows:
        L.append(f"| `{step}` — {what} | {who} | {waits} | {st} |")
    for q in requests:
        L.append(f"| {q['item']} | {q.get('who') or '[TODO]'} | {q.get('waiting_on') or '—'} | "
                 f"Not done |")
    if n_closed:
        L.append(f"\n{n_closed} closed request{'s' if n_closed!=1 else ''} not shown.")
    L.append(f"\nMark a step when it's done: `sir_update.py {a.rid} --mark-step <step>` "
             f"(first one: add `--pid <PID>`). The last three need a yes from the person named. "
             f"No Study Tracker key? Tick the same box in the Study Tracker.")

    L.append("\n## Details")
    L.append("\n### Data dictionary (`dd_uploaded`)")
    L.append("The DD matches the printed questionnaire exactly. Two files go with it:")
    L.append("\n- `OPEN_QUESTIONS.md` — each guess the build made where the form was unclear "
             "(\"we assumed X — right?\"). Always written, even if empty.")
    L.append("- `<name>_redcap_changes.docx` — changes the questionnaire itself needs, as tracked "
             "changes on the original. A `<name>_redcap_changes.md` list if the original is a PDF. "
             "Only if there are changes.")
    L.append("\nTypos and numbering go in neither: they are built as printed.")
    L.append("\n**`@MDC-EXEMPT`** in the Field Annotation column: leave it. REDCap ignores it — it is "
             "invisible to respondents and changes nothing on upload. It tells `validate_dd.py` the "
             "missing-data codes were left off on purpose (validated scales). Strip it and those "
             "fields fail ARGO validation.")

    L.append("\n### Survey settings (only if people fill it in themselves)")
    L.append("Default is data-entry forms. If it is a survey, the DD upload does not set it up. Do:")
    L.append("\n1. Project Setup → **Enable \"Use surveys in this project\"**.")
    L.append("2. Designer → **enable each instrument as a survey**.")
    L.append("3. Survey Settings → title, instructions, and the **approved consent text** on the "
             "baseline survey.")
    L.append("4. Survey Settings → **Question Numbering = \"Custom numbering\"**. Otherwise REDCap "
             "renumbers the questions and the survey stops matching the paper form.")
    L.append("\nCheck the DD has: an **email field** (if more than one round), **one instrument "
             "per round**, **baseline-vs-follow-up branching**, a **consent question first**, and "
             "**no missing-data codes** (surveys never get them; clear the SIR's "
             "`missing_data_codes` boxes). None of these is on the 7-step tracker — they are part "
             "of `review_internal`.")

    if dags:
        L.append("\n### DAGs (`user_rights_complete`)")
        L.append("User Rights → DAGs — create one per site, then put each user in theirs: "
                 + ", ".join(dags) + ".")
    L.append("\n### Users (`user_rights_complete`)")
    if people or addl:
        L.append("\n| User | Email | Role |\n|---|---|---|")
        for n,e,role in people: L.append(f"| {n} | {e or '—'} | {role} |")
        if addl: L.append(f"| *(more — confirm roles)* | | {addl[:80]} |")
    else:
        L.append("\nNo one is named in the SIR. Ask the PM.")
    L.append("\nThe roles CSV gives Study Builder and Project Manager exports with identifier "
             "fields removed. Only fields flagged `Identifier?` are removed — check the flags.")
    L.append("\nNo REDCap account yet? Log them in the Study Personnel Request tracker (PID 221). "
             "A REDCap admin makes the account.")

    L.append("\n### File Repository (`review_internal`) — moniker `%s`" % mon)
    if docs:
        L.append("\n| SIR field / file | Rename to | Folder | Site |\n|---|---|---|---|")
        for f,v in docs:
            label,site=repo_label(f,sites)
            L.append(f"| `{f}` = {v[:40]} | `{mon}_{label}` (keep ext) | {repo_folder(f)} | {site} |")
        L.append("\n**Stage the files, don't just list them.** Put the renamed files in "
                 "`file-repository/` in the build folder, in table order. If a file had tracked "
                 "changes, stage it with the changes **accepted**, and keep the `_redcap_changes` "
                 "copy beside it.")
    else:
        L.append("\nNo documents are attached to the SIR.")

    L.append("\n### Weekly report (`review_internal`)")
    if g("weekly_stat") or g("category"):
        L.append(f"From the SIR: weekly_stat={g('weekly_stat')!r}, category={g('category')!r}.")
    else:
        L.append("Not set in the SIR. Ask the PM, or skip.")

    out=os.path.join(a.out,"MANUAL_SETUP_BRIEF.md")
    open(out,"w").write("\n".join(L)+"\n")
    print(f"wrote {out} ({n_done}/{len(rows)} steps done, {len(docs)} docs, {len(dags)} DAGs, "
          f"{len(people)} named users)")

if __name__=="__main__": main()
