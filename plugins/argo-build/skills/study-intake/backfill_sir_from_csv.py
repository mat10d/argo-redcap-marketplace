#!/usr/bin/env python3
"""Backfill SIR with explicit record_ids per master sort.

Pushes 17 updates (in place) + 84 Excel creates at explicit record_ids 1-108
filling gaps left after the manual rename.
"""
import os, sys, csv, json, urllib.request, urllib.parse, difflib, re, argparse

REDCAP_URL = os.environ['REDCAP_URL']
SIR_TOKEN = os.environ['STUDY_INITIATION_REQUEST']

def api_post(token, **params):
    data = urllib.parse.urlencode({'token': token, 'format':'json', **params}).encode()
    req = urllib.request.Request(REDCAP_URL, data=data, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def api_post_record(token, payload, mode='normal'):
    data = urllib.parse.urlencode({
        'token': token, 'format':'json',
        'content':'record', 'overwriteBehavior': mode,
        'data': json.dumps(payload),
    }).encode()
    req = urllib.request.Request(REDCAP_URL, data=data, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

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

def build_master(csv_path):
    existing = api_post(SIR_TOKEN, content='record', **{'fields[0]':'record_id', 'fields[1]':'project_title'})
    with open(os.path.expanduser(csv_path)) as f:
        excel = list(csv.DictReader(f))
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', required=True,
                    help='Path to the active-databases CSV to backfill from '
                         '(e.g. "$ARGO_PM_ROOT/active_dbs_normalized_with_pid.csv")')
    ap.add_argument('--commit', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    records = build_master(args.csv)
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
    print(f"\nQueued: {len(work)} write operations\n")

    if not args.commit:
        for tr, p, kind in work[:5]:
            print(f"\n[{kind}] target_rid={tr}")
            for k, v in sorted(p.items()):
                print(f"  {k}: {str(v)[:80]}")
        print(f"\n[dry-run] No writes. Re-run with --commit.")
        return

    for i, (tr, p, kind) in enumerate(work, 1):
        try:
            mode = 'overwrite' if kind == 'CREATE' else 'normal'
            resp = api_post_record(SIR_TOKEN, [p], mode=mode)
            print(f"  [{i}/{len(work)}] {kind} record_id={tr}: {resp}")
        except Exception as e:
            print(f"  [{i}/{len(work)}] {kind} record_id={tr} FAILED: {e}")

if __name__ == '__main__':
    main()
