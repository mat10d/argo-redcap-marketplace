#!/usr/bin/env python3
"""setup_brief.py — generate MANUAL_SETUP_BRIEF.md for a study build from its SIR record.

Turns the per-study manual UI work into a copy-paste-and-click checklist: derives the File
Repository rename table, the Data Access Groups, the user→role table, and the build_tracking
commands directly from the SIR. Replaces hand-writing the brief each build.

Works with or without an access key ([[token-optional]]): pulls the SIR via the API if the Study
Tracker key is set, or reads a pre-pulled record JSON (`sir_update.py <RID> --pull > rec.json`)
with --from-json.

Usage:
    set -a; source ~/.argo/.env; set +a
    python3 setup_brief.py <RID> --out database-manager/<study> [--moniker HPV_SelfSampling]
    python3 setup_brief.py <RID> --from-json rec.json --out database-manager/<study> --moniker HPV_SelfSampling
"""
import argparse, json, os, sys, datetime, urllib.parse, urllib.request

def pull(rid):
    url=os.environ.get("REDCAP_URL"); tok=os.environ.get("STUDY_INITIATION_REQUEST")
    if not (url and tok):
        sys.exit("No REDCAP_URL/STUDY_INITIATION_REQUEST in env. Either source ~/.argo/.env, "
                 "or pass --from-json (sir_update.py <RID> --pull > rec.json).")
    data=urllib.parse.urlencode({"token":tok,"content":"record","format":"json","records[0]":rid}).encode()
    recs=json.loads(urllib.request.urlopen(urllib.request.Request(url,data=data,method="POST"),timeout=60).read())
    if not recs: sys.exit(f"SIR record {rid} not found.")
    return recs[0]

# doc field -> File Repository folder
def repo_folder(field):
    return "IRB and Ethics" if ("irb_file" in field or "consent" in field) else "Study Documents"
def repo_label(field):
    return {"sop":"SOP","eligibility_checklist":"ECL","quest_univ_file":"Questionnaire"}.get(field) or \
           field.replace("_file","").replace("_1","_UCH").replace("_2","_UNIOSUN").replace("quest_site","Questionnaire_site").title().replace("_","")

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
    # DAGs
    dags=[g(f) for f in sorted(r) if f.startswith("inst_name_") and g(f)]
    # IRB expiry check
    exp=g("irb_approval_expires"); exp_flag=""
    if exp:
        try:
            if datetime.date.fromisoformat(exp) < datetime.date.today():
                exp_flag=f"  ⚠️ **IRB expiry {exp} is PAST — confirm a renewal before production.**"
        except ValueError: pass
    # personnel
    people=[]
    if g("pi_user_name"): people.append((g("pi_user_name"),g("pi_user_email"),"Principal Investigator"))
    if g("pm_name"): people.append((g("pm_name"),g("pm_email"),"Project Manager"))
    if g("ra_name"): people.append((g("ra_name"),g("ra_email"),"Data Entry (RA)"))
    addl=g("addl_users")

    L=[]
    L.append(f"# MANUAL_SETUP_BRIEF — SIR {a.rid}: {g('project_title')[:80]}")
    L.append(f"\nPI: {g('pi_first_name')} {g('pi_surname')} · IRB {g('irb_number') or '—'} · "
             f"PID {g('new_project_pid') or '(not yet created)'} · moniker `{mon}`.{exp_flag}")
    L.append("\nMark `build_tracking` via `sir_update.py` if your Study Tracker access key is set up, "
             "else tick the same fields in the Study Tracker UI.\n")
    L.append("## 1. Create project → `project_created`\nUse the paste sheet (`CREATE_NEW_PROJECT_%s.txt` / `fill_new_project.py %s`). Mark with `--pid <PID>`." % (a.rid,a.rid))
    L.append("\n## 2. Upload the data dictionary → `dd_uploaded`\nDesigner → Data Dictionary → Upload the validated DD CSV.")
    L.append("\n## 3. Form vs survey\nDefault to data-entry forms unless the proposal says respondents self-complete.")
    if dags:
        L.append("\n## 4. Data Access Groups\nUser Rights → DAGs — create and assign users for: "+", ".join(dags)+".")
    L.append("\n## 5. User rights / roles → `user_rights_complete`\nUpload the roles CSV (User Rights → User Roles → Upload), then assign:")
    if people or addl:
        L.append("\n| User | Email | Role |\n|---|---|---|")
        for n,e,role in people: L.append(f"| {n} | {e or '—'} | {role} |")
        if addl: L.append(f"| *(additional, confirm roles)* | | {addl[:80]} |")
    else:
        L.append("\n*(no personnel named in the SIR — confirm with the PM)*")
    L.append("\nUsers without REDCap accounts → log them in the SPR (PID 221) via `manage-redcaps`.")
    L.append("\n## 6. File Repository (rename with moniker `%s`)" % mon)
    if docs:
        L.append("\n| SIR field / file | Upload as | Folder |\n|---|---|---|")
        for f,v in docs: L.append(f"| `{f}` = {v[:40]} | `{mon}_{repo_label(f)}` (keep ext) | {repo_folder(f)} |")
    else:
        L.append("\n*(no documents attached to the SIR)*")
    dc=g("data_collection")
    L.append("\n## 7. Data import → `data_imported`\n"+("Prospective → `data_imported=2` (no historical data)." if dc=="2" else "If retrospective data exists, map + import, then `data_imported=1`; else `=2`."))
    L.append("\n## 8. Review → Production (human gates — confirm each)\n`review_internal` (internal QA), `review_pi` (PI sign-off), then `study_production`."+(" "+exp_flag.strip() if exp_flag else ""))
    L.append("\n## Mark the tracker (works with or without an access key)\nWith an access key: run the Study Tracker step-marking script (`sir_update.py`, in the "
             "build-study skill) once per step, e.g.\n```\nsir_update.py %s --pid <PID> --mark-step project_created\n```\n"
             "No access key → tick these `build_tracking` boxes in the Study Tracker." % a.rid)
    if g("weekly_stat") or g("category"):
        L.append(f"\n## Weekly report\nFrom SIR: weekly_stat={g('weekly_stat')!r}, category={g('category')!r}.")
    else:
        L.append("\n## Weekly report\nSIR `weekly_stat`/`category` blank — confirm the report spec with the PM or skip.")

    out=os.path.join(a.out,"MANUAL_SETUP_BRIEF.md")
    open(out,"w").write("\n".join(L)+"\n")
    print(f"wrote {out} ({len(docs)} docs, {len(dags)} DAGs, {len(people)} named users)")

if __name__=="__main__": main()
