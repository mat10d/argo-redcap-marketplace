#!/usr/bin/env python3
"""Load Study Tracker (SIR) records in bulk from a spreadsheet, at chosen record numbers.

This writes to the Study Tracker (project 224) — ARGO's own project-management records, not
patient data. It assigns each row a record number in sorted order, so it can both update records
that already exist and create the ones that don't.

Because it writes at specific record numbers, **you must say which range of record numbers it is
allowed to touch** before it will write anything. That way a re-run against a different
spreadsheet can't quietly overwrite records outside the range you had in mind.

Usage:
    set -a; source ~/.argo/.env; set +a

    # See what it would do, without changing anything (always do this first)
    python3 backfill_sir_from_csv.py --csv active_dbs.csv

    # Actually write, allowing only record numbers 1 to 108 to be touched
    python3 backfill_sir_from_csv.py --csv active_dbs.csv --record-id-range 1-108 --commit
"""
import os, sys, csv, json, difflib, re, argparse

def _add_argo_core_to_path():
    """Find argo-core's scripts folder and make it importable.

    Searches for the FILE argo_redcap_client.py, never for a directory named "argo-core":
    plugin directories are named differently per environment (Claude Code uses
    <marketplace>/<plugin>/<version>/; Cowork uses opaque plugin_<id>/ names with the plugin
    name only inside its manifest), so a name-based search finds nothing in some of them.
    """
    from pathlib import Path as _P
    marker = "argo_redcap_client.py"
    override = os.environ.get("ARGO_CORE_SCRIPTS")
    if override and (_P(override).expanduser() / marker).exists():
        sys.path.insert(0, str(_P(override).expanduser())); return
    for root in ("/mnt/.remote-plugins", "~/.claude/plugins", "~/.claude/plugins/cache"):
        base = _P(root).expanduser()
        if base.is_dir():
            hits = sorted(base.glob(f"**/{marker}"))
            if hits:
                sys.path.insert(0, str(hits[-1].parent)); return
    for parent in _P(__file__).resolve().parents:
        for cand in (parent / "plugins" / "argo-core" / "skills" / "redcap-api" / "scripts",
                     parent / "plugins" / "argo-core" / "scripts",
                     parent / "argo-core" / "scripts"):
            if (cand / marker).exists():
                sys.path.insert(0, str(cand)); return


_add_argo_core_to_path()
from argo_redcap_client import RedcapClient, RedcapError  # noqa: E402

SIR_TITLE = "Study Tracker"
SIR_PID = "224"

def fuzz_norm(t):
    t = (t or '').lower(); t = re.sub(r'[^a-z0-9 ]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

# --- Field mapping helpers (from earlier backfill_sir_from_csv.py) ---
STUDY_TYPE_MAP = {
    "OAU REDCap (main studies)": "1", "OAU REDCap (NCAT studies)": "4",
    "OAU REDCap (ARGO surveys)": "6", "OAU REDCap (other studies)": "3",
    "OAU REDCap (pathology databases": "3", "MSK REDCap": "3", "UCSF REDCap": "3",
    "Inactiveprospective studies": "3",
}
LOCATION_MAP = {"OAU":"1","MSK":"2","MSKCC":"2","UCSF":"3"}

def parse_irb(raw):
    if not raw or not raw.strip(): return 0, []
    sites = []
    for line in re.split(r"[\n;]+", raw):
        m = re.match(r"\s*([^:]+):\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})", line)
        if not m: continue
        site = m.group(1).strip()
        d = m.group(2).replace(".","/").replace("-","/").split("/")
        if len(d) != 3: continue
        dd, mm, yyyy = d[0].zfill(2), d[1].zfill(2), d[2]
        if len(yyyy) == 2: yyyy = "20" + yyyy
        try:
            if not (1 <= int(dd) <= 31 and 1 <= int(mm) <= 12 and 1900 <= int(yyyy) <= 2100):
                continue
        except ValueError:
            continue
        sites.append((site, f"{yyyy}-{mm}-{dd}"))  # REDCap import format
        if len(sites)==10: break
    return len(sites), sites

def excel_to_payload(row, record_id):
    p = {"record_id": str(record_id)}
    if row.get("project_title"): p["project_title"] = row["project_title"]
    if row.get("new_project_pid"): p["new_project_pid"] = row["new_project_pid"]
    if row.get("shortened_study_name"): p["shortened_study_name"] = row["shortened_study_name"]
    excel_status = (row.get("study_status") or "").strip()
    if row.get("source_sheet") == "Inactiveprospective studies": excel_status = "6"
    if excel_status:
        try:
            if int(excel_status) >= 2: p["study_production"] = "1"
        except: pass
        p["study_status"] = excel_status
    for f in ["ethical_clearance_obtained","submitted_to_redcap_admin","consent_profs_sheet",
              "elig_chklist_sheet","consent_sheet","questionnaire_proforma","sop_uploaded",
              "report_made_in_redcap","ra_training_manual_siv"]:
        v = (row.get(f) or "").strip()
        if v in ("0","1"): p[f] = v
    for f in ["redcap_support_lead","admin_support_qa_meetings","admin_support_assignment",
              "ra_training_assignment","biostatistician_assigned","qa_manager","linkages"]:
        v = (row.get(f) or "").strip()
        if v: p[f] = v
    st = STUDY_TYPE_MAP.get(row.get("source_sheet"))
    if st: p["study_type"] = st
    loc = LOCATION_MAP.get((row.get("redcap_location") or "").strip().upper())
    if loc: p["redcap_location_built"] = loc
    CANCER_TYPE_MAP = {"CRC":"1","COLORECTAL":"1","BREAST":"2","GASTRIC":"3","PROSTATE":"4","HEPATOBILIARY":"5","HPB":"5","SARCOMA":"6","MIXED":"7","OTHER":"8"}
    ct = (row.get("cancer_type") or "").strip().upper()
    if ct:
        mapped = CANCER_TYPE_MAP.get(ct)
        if mapped: p["cancer_type"] = mapped
    n, sites = parse_irb(row.get("irb_approval_expires_raw",""))
    if n > 0:
        p["irb_site_count"] = str(n)
        for i,(s,d) in enumerate(sites, 1):
            p[f"irb_site_{i}"] = s
            p[f"irb_site_{i}_expiry"] = d
    raw_irb = (row.get("irb_approval_expires_raw") or "").strip()
    if raw_irb and (n==0 or "\n" in raw_irb):
        p["build_notes"] = f"IRB expiry raw (verify): {raw_irb}"
    return p

# --- Build master list (same logic as the audit) ---
def find_pid(excel, pid):
    for i,r in enumerate(excel):
        if r.get('new_project_pid') == str(pid): return i
    return None

def build_master(client, csv_path):
    existing = client.export_records(**{'fields[0]': 'record_id', 'fields[1]': 'project_title'})
    csv_path = os.path.expanduser(csv_path)
    if not os.path.exists(csv_path):
        raise SystemExit(
            f"I couldn't find the spreadsheet you asked me to read:\n"
            f"    {csv_path}\n"
            "\n"
            "Check the file name and folder are right. If the path has spaces in it, put quotes\n"
            'around it, like --csv "My Folder/active dbs.csv".'
        )
    with open(csv_path) as f:
        excel = list(csv.DictReader(f))
    if not excel:
        raise SystemExit(
            f"The spreadsheet {csv_path} has no rows in it (only a header, or nothing at all).\n"
            "Nothing to load, so I've stopped without changing anything."
        )
    MANUAL = {'24':find_pid(excel,7390), '79':None, '80':find_pid(excel,182),
              '85':None, '86':find_pid(excel,192), '100':None, '101':find_pid(excel,237),
              '102':find_pid(excel,238)}
    # Post-rename SIR IDs for manual matches:
    MANUAL = {
        '16': find_pid(excel, 7390),  # AIM 3
        '80': find_pid(excel, 182),   # BCCD/R2S
        '86': find_pid(excel, 192),   # RA 2025
        '101': find_pid(excel, 237),  # RA 2026
        '102': find_pid(excel, 238),  # R2S adherence
    }
    sir_to_excel = {}
    used = set()
    for rid, idx in MANUAL.items():
        if idx is not None: sir_to_excel[rid] = idx; used.add(idx)
    for s in existing:
        rid = s['record_id']
        if rid in sir_to_excel: continue
        sn = fuzz_norm(s.get('project_title',''))
        if not sn: continue
        best_i, best_score = None, 0
        for i, r in enumerate(excel):
            if i in used: continue
            sc = difflib.SequenceMatcher(None, sn, fuzz_norm(r['project_title'])).ratio()
            if sc > best_score: best_score, best_i = sc, i
        if best_score >= 0.78: sir_to_excel[rid] = best_i; used.add(best_i)

    matched_excel = set(sir_to_excel.values())
    SIR_RID_TO_PID = {'105':244, '103':242, '104':243}

    records = []
    for i, r in enumerate(excel):
        if i in matched_excel: continue
        records.append({'kind':'create','sir_rid':None,'excel_row':r,'excel_pid':r.get('new_project_pid','').strip(),
                        'sheet':r.get('source_sheet',''),'title':r['project_title']})
    for s in existing:
        rid = s['record_id']
        eidx = sir_to_excel.get(rid)
        e = excel[eidx] if eidx is not None else None
        pid = (e.get('new_project_pid','').strip() if e else '') or str(SIR_RID_TO_PID.get(rid,'') or '')
        sheet = e.get('source_sheet','') if e else ''
        if not sheet:
            tl = (s.get('project_title') or '').lower()
            sheet = 'MSK REDCap (SIR-only)' if ('msk' in tl or 'immuno-oncology' in tl or 'aim 3' in tl or 'metabolite' in tl) else 'OAU REDCap (SIR-only)'
        records.append({'kind':'update' if eidx is not None else 'sir-only',
                        'sir_rid':rid,'excel_row':e,'excel_pid':pid,'sheet':sheet,
                        'title':s.get('project_title') or '(no title)'})

    def bucket(r):
        if 'MSK' in r['sheet']: return 0
        if 'UCSF' in r['sheet']: return 1
        return 2
    def pid_key(r):
        try: return int(r['excel_pid'])
        except: return 10**9
    records.sort(key=lambda r: (bucket(r), pid_key(r)))
    for i, r in enumerate(records, 1):
        r['target_rid'] = i
    return records

def parse_record_id_range(text):
    """Turn '1-108' into (1, 108). Anything else gets a message explaining the format."""
    match = re.fullmatch(r'\s*(\d+)\s*-\s*(\d+)\s*', text or '')
    if not match:
        raise SystemExit(
            f"I didn't understand the record number range {text!r}.\n"
            "\n"
            "Write it as two numbers with a dash between them — the first record number and the\n"
            "last one this run is allowed to touch. For example:\n"
            "\n"
            "    --record-id-range 1-108"
        )
    low, high = int(match.group(1)), int(match.group(2))
    if low > high:
        raise SystemExit(
            f"The record number range {text!r} runs backwards — {low} is higher than {high}.\n"
            "Put the smaller number first, like --record-id-range 1-108."
        )
    return low, high


def main():
    ap = argparse.ArgumentParser(
        description="Load Study Tracker records in bulk from a spreadsheet.")
    ap.add_argument('--csv', required=True,
                    help='Path to the active-databases CSV to backfill from '
                         '(e.g. "$ARGO_PM_ROOT/active_dbs_normalized_with_pid.csv")')
    ap.add_argument('--record-id-range', metavar='LOW-HIGH',
                    help='Which record numbers this run may touch, e.g. 1-108. '
                         'Required with --commit. Anything outside the range is skipped.')
    ap.add_argument('--commit', action='store_true',
                    help='Actually write to the Study Tracker. Without this, nothing is changed.')
    ap.add_argument('--limit', type=int, default=0,
                    help='Only process the first N rows (useful for a cautious first run).')
    args = ap.parse_args()

    # No token? Say so plainly and stop — but never pretend this is the user's fault.
    client = RedcapClient.from_env('STUDY_INITIATION_REQUEST', label=SIR_TITLE)
    if client is None:
        raise SystemExit(RedcapClient.explain_missing_token(
            'STUDY_INITIATION_REQUEST',
            'load records into the Study Tracker',
            fallback=(
                "This particular task needs the access key — there's no file-upload alternative\n"
                "for it. Ask your ARGO REDCap administrator for the Study Tracker key, add it to\n"
                "~/.argo/.env, and run this again. Everything else in the build skill works\n"
                "without one."
            ),
        ))

    allowed = None
    if args.commit:
        if not args.record_id_range:
            raise SystemExit(
                "Before writing anything, I need to know which record numbers I'm allowed to\n"
                "touch in the Study Tracker.\n"
                "\n"
                "This is a safety check: this tool writes to specific record numbers, and without\n"
                "a stated range a re-run against a different spreadsheet could overwrite records\n"
                "you didn't mean to change.\n"
                "\n"
                "Run it again with the range added, for example:\n"
                "\n"
                f"    python3 {os.path.basename(__file__)} --csv {args.csv} "
                "--record-id-range 1-108 --commit"
            )
        allowed = parse_record_id_range(args.record_id_range)
    elif args.record_id_range:
        allowed = parse_record_id_range(args.record_id_range)

    try:
        records = build_master(client, args.csv)
    except RedcapError as e:
        raise SystemExit(str(e))
    creates = [r for r in records if r['kind']=='create']
    updates = [r for r in records if r['kind']=='update']
    print(f"Master: {len(records)} | creates: {len(creates)} | updates: {len(updates)} | sir-only: {sum(1 for r in records if r['kind']=='sir-only')}")

    work = []  # (target_rid, payload, kind)
    for r in creates:
        work.append((r['target_rid'], excel_to_payload(r['excel_row'], r['target_rid']), 'CREATE'))
    for r in updates:
        # SIR record is at sir_rid (== target_rid after rename). Apply Excel data.
        work.append((r['target_rid'], excel_to_payload(r['excel_row'], r['target_rid']), 'UPDATE'))

    if args.limit:
        work = work[:args.limit]

    # Enforce the stated record number range: anything outside it is dropped, and said out loud.
    if allowed:
        low, high = allowed
        in_range = [w for w in work if low <= w[0] <= high]
        skipped = [w for w in work if not (low <= w[0] <= high)]
        if skipped:
            numbers = ", ".join(str(w[0]) for w in skipped[:10])
            more = f" (and {len(skipped) - 10} more)" if len(skipped) > 10 else ""
            print(f"Skipping {len(skipped)} rows outside the range {low}-{high} you allowed: "
                  f"{numbers}{more}")
        work = in_range

    print(f"\nQueued: {len(work)} write operations\n")
    if not work:
        print("Nothing to do — no rows fell inside the allowed record number range.")
        return

    if not args.commit:
        for tr, p, kind in work[:5]:
            print(f"\n[{kind}] target_rid={tr}")
            for k, v in sorted(p.items()):
                print(f"  {k}: {str(v)[:80]}")
        if len(work) > 5:
            print(f"\n… and {len(work) - 5} more, not shown.")
        print(
            "\nNothing has been changed — this was a preview.\n"
            "If the above looks right, run it again with the range you want to allow and --commit:\n"
            f"\n    python3 {os.path.basename(__file__)} --csv {args.csv} "
            f"--record-id-range {work[0][0]}-{work[-1][0]} --commit"
        )
        return

    # Confirm once, up front, that this key really opens the Study Tracker — before any write.
    try:
        client.confirm_project(expect_title=SIR_TITLE, expect_pid=SIR_PID)
    except RedcapError as e:
        raise SystemExit(str(e))

    failures = 0
    for i, (tr, p, kind) in enumerate(work, 1):
        try:
            mode = 'overwrite' if kind == 'CREATE' else 'normal'
            resp = client.import_records([p], overwrite=mode)
            print(f"  [{i}/{len(work)}] {kind} record_id={tr}: {resp}")
        except RedcapError as e:
            failures += 1
            print(f"  [{i}/{len(work)}] {kind} record_id={tr} FAILED: "
                  f"{str(e).strip().splitlines()[0]}")

    print(f"\nDone. {len(work) - failures} of {len(work)} records written.")
    if failures:
        print(f"{failures} did not go through — the FAILED lines above say why for each one.")
        sys.exit(1)

if __name__ == '__main__':
    main()
