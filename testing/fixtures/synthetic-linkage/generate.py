#!/usr/bin/env python3
"""Generate the synthetic-linkage fixture: six fake ARGO studies with planted linkage cases.

Everything is made up. Two registries (CRC, Breast) and four children (R01, BRCA, Financial
toxicity, a pathology database), in the shapes the real exports have: different record-ID and
hospital-number field names, DAG spellings, parent-ID fields filled for some records only.

Planted cases, each counted in MANIFEST.json so the engine's output can be checked exactly:
hard links that agree with the keys, hard links with a typo, a hard link pointing at the wrong
patient, new links found by keys, swapped and misspelt names, leading-zero numbers, one-digit /
transposed / dropped-digit hospital-number typos, the same number at two hospitals, the same
number on two different people, a patient enrolled twice, histology-number typos, missing-data
codes, and people who are in no other study.

    python3 generate.py      # rewrites the CSVs, studies.csv, truth.csv and MANIFEST.json here
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "plugins/argo-core/skills/redcap-api/scripts"))
import argo_linkage_keys as lk  # noqa: E402

SEED = 20261015
rng = random.Random(SEED)

FIRST = ["Adaeze", "Babatunde", "Chinedu", "Damilare", "Ebere", "Folake", "Gbolahan", "Habiba",
         "Ikechukwu", "Jumoke", "Kayode", "Ladi", "Mojisola", "Nnamdi", "Olufemi", "Patience",
         "Rasheed", "Sade", "Temitope", "Usman", "Victoria", "Wale", "Yetunde", "Zubairu",
         "Abimbola", "Bukola", "Chiamaka", "Dauda", "Eniola", "Fatima", "Gideon", "Hadiza"]
LAST = ["Adebanjo", "Bamidele", "Chukwuemeka", "Dikko", "Ekwueme", "Fagbemi", "Gambo",
        "Hassan", "Ilori", "Jegede", "Kolawole", "Lawal", "Mbanefo", "Nwachukwu", "Ogunleye",
        "Popoola", "Quadri", "Rufai", "Salami", "Tijani", "Udeh", "Wakili", "Yakubu", "Zakari",
        "Akinola", "Babalola", "Chime", "Dangote", "Eze", "Fawole", "Gwarzo", "Haruna"]

used_keys: list[str] = []
used_hist: set[tuple] = set()
used_names: set[tuple] = set()


def near(a: str, b: str) -> bool:
    return a == b or a.lstrip("0") == b.lstrip("0") or lk._one_edit(a, b) is not None \
        or lk._one_edit(a.lstrip("0"), b.lstrip("0")) is not None


def new_hosp(leading_zero=False) -> str:
    while True:
        k = ("0" if leading_zero else str(rng.randint(1, 9))) + "".join(
            str(rng.randint(0, 9)) for _ in range(5))
        if not any(near(k, u) for u in used_keys):
            used_keys.append(k)
            return k


def new_hist(site) -> tuple:
    prefix = "H" if site == "OAUTHC" else "B"
    while True:
        n, y = rng.randint(100, 2999), rng.randint(15, 25)
        clash = any(n == m or lk._one_edit(str(n), str(m)) for (_, m, _) in used_hist)
        if not clash:
            used_hist.add((prefix, n, y))
            return prefix, n, y


def new_name() -> tuple:
    while True:
        f, l = rng.choice(FIRST), rng.choice(LAST)
        if (f, l) not in used_names and all(f != a and l != b for a, b in used_names):
            used_names.add((f, l))
            return f, l
        if len(used_names) > 28:                     # pool nearly spent: only the pair must be new
            if (f, l) not in used_names:
                used_names.add((f, l))
                return f, l


def hist_text(h, four_digit_year=False):
    p, n, y = h
    return f"{p}{n}/{2000 + y if four_digit_year else y:02d}"


class Person:
    count = 0

    def __init__(self, site, leading_zero=False):
        Person.count += 1
        self.pid = f"P{Person.count:03d}"
        self.site = site
        self.hosp = new_hosp(leading_zero)
        self.hist = new_hist(site)
        self.first, self.last = new_name()


def typo(key: str, kind: str) -> str:
    for _ in range(200):
        if kind == "one_digit":
            i = rng.randint(1, len(key) - 1)
            t = key[:i] + str((int(key[i]) + rng.randint(1, 9)) % 10) + key[i + 1:]
        elif kind == "transposed":
            i = rng.randint(1, len(key) - 2)
            if key[i] == key[i + 1]:
                continue
            t = key[:i] + key[i + 1] + key[i] + key[i + 2:]
        else:                                          # digit_missing
            i = rng.randint(1, len(key) - 1)
            t = key[:i] + key[i + 1:]
        a, b = lk.hospital_number(key, "oauthc"), lk.hospital_number(t, "oauthc")
        if lk.compare_hospital(a, b) == kind and not any(near(t, u) for u in used_keys if u != key):
            return t
    raise RuntimeError(f"could not make a {kind} typo of {key}")


def misspell(name: str) -> str:
    for i in range(len(name) - 2, 0, -1):
        if name[i] in "aeiou":
            alt = name[:i] + ("o" if name[i] != "o" else "u") + name[i + 1:]
            if lk.compare_names(("x", alt), ("x", name)) == ("ambiguous", "variant"):
                return alt
    raise RuntimeError(name)


# --- people ------------------------------------------------------------------------------------

crc_people = [Person("OAUTHC") for _ in range(64)] + [Person("LUTH") for _ in range(8)]
breast_people = [Person("OAUTHC") for _ in range(25)] + \
                [Person("OAUTHC", leading_zero=True) for _ in range(2)] + \
                [Person("LUTH") for _ in range(10)]
crc_oau = [p for p in crc_people if p.site == "OAUTHC"]
crc_luth = [p for p in crc_people if p.site == "LUTH"]
pool = iter(crc_oau)
take = lambda n: [next(pool) for _ in range(n)]  # noqa: E731

rows: dict[str, list[dict]] = {k: [] for k in ("crc", "breast", "r01", "brca", "fintox", "path")}
truth: list[tuple] = []
expect = {"hard_links": 0, "hard_confirmed": 0, "hard_with_typo": 0, "hard_disagrees": 0,
          "strong": 0, "probable": 0, "near_miss": 0, "conflict": 0, "duplicate": 0,
          "names_to_judge": 0, "blank_key": {}, "unlinked": {}}
crc_id = {}

# Registries
for i, p in enumerate(crc_people, 1):
    rid = f"40-{i}"
    crc_id[p.pid] = rid
    rows["crc"].append({"research_number": rid, "redcap_data_access_group": p.site.lower(),
                        "hospital_no": p.hosp, "histology_number": hist_text(p.hist),
                        "first_name": p.first, "surname": p.last})
    truth.append(("crc", rid, p.pid))
breast_id = {}
for i, p in enumerate(breast_people, 1):
    rid = str(i)
    breast_id[p.pid] = rid
    rows["breast"].append({"record_id": rid, "hospital_site": p.site, "hospital_number": p.hosp,
                           "surg_histopath_no": hist_text(p.hist, four_digit_year=True),
                           "first_name": p.first, "surname": p.last})
    truth.append(("breast", rid, p.pid))

r01_n = 0


def r01(p, *, hosp=None, site=None, first=None, last=None, hard=None, person=None):
    global r01_n
    r01_n += 1
    rid = str(r01_n)
    rows["r01"].append({"record_id": rid,
                        "redcap_data_access_group": {"OAUTHC": "oauthc_ife", "LUTH": "luth"}[
                            site or p.site],
                        "hospital_number": p.hosp if hosp is None else hosp,
                        "first_name": first or p.first, "last_name": last or p.last,
                        "colorectal_record_id": hard or ""})
    truth.append(("r01", rid, person or p.pid))
    return rid


# R01 (child of CRC)
for p in take(12):                                   # hard link, keys agree
    r01(p, hard=crc_id[p.pid])
    expect["hard_links"] += 1; expect["hard_confirmed"] += 1
for p in take(2):                                    # hard link, hospital number typed wrong
    r01(p, hosp=typo(p.hosp, "one_digit"), hard=crc_id[p.pid])
    expect["hard_links"] += 1; expect["hard_with_typo"] += 1; expect["near_miss"] += 1
for p in take(6):                                    # no hard link, keys agree -> new link
    r01(p); expect["strong"] += 1
for p in take(2):                                    # names swapped
    r01(p, first=p.last, last=p.first); expect["strong"] += 1
for p in take(2):                                    # surname misspelt -> probable, name check
    r01(p, last=misspell(p.last)); expect["probable"] += 1; expect["names_to_judge"] += 1
for kind in ("one_digit", "one_digit", "transposed", "transposed", "digit_missing", "digit_missing"):
    p = next(pool)
    r01(p, hosp=typo(p.hosp, kind)); expect["near_miss"] += 1
for p in take(2):                                    # same number, different person
    impostor = Person("OAUTHC")
    while lk.compare_names((impostor.first, impostor.last), (p.first, p.last)) != \
            ("different", "unrelated"):
        impostor.first, impostor.last = new_name()
    r01(p, first=impostor.first, last=impostor.last, person=impostor.pid)
    expect["conflict"] += 1
x, y = take(2)                                       # hard link points at the wrong patient
r01(y, hard=crc_id[x.pid])
expect["hard_links"] += 1; expect["hard_disagrees"] += 1
p = next(pool)                                       # same number recorded at the other hospital
r01(p, site="LUTH"); expect["near_miss"] += 1
for _ in range(2):                                   # hospital number is a missing-data code
    q = Person("OAUTHC")
    r01(q, hosp="-888")
expect["blank_key"]["r01"] = 2
for _ in range(3):                                   # in no other study
    r01(Person("OAUTHC"))
expect["unlinked"]["r01"] = 3

# Financial toxicity (child of both, single site OAUTHC)
fin_n = 0


def fintox(p, crc_hard="", breast_hard=""):
    global fin_n
    fin_n += 1
    rid = f"F{fin_n:02d}"
    rows["fintox"].append({"record_id": rid, "hospital_no": p.hosp, "first_name": p.first,
                           "surname": p.last, "colorectal_record_id": crc_hard,
                           "breast_record_id": breast_hard})
    truth.append(("fintox", rid, p.pid))


for p in take(4):
    fintox(p, crc_hard=crc_id[p.pid]); expect["hard_links"] += 1; expect["hard_confirmed"] += 1
b_oau = [p for p in breast_people if p.site == "OAUTHC" and not p.hosp.startswith("0")]
bpool = iter(b_oau)
for _ in range(4):
    p = next(bpool)
    fintox(p, breast_hard=breast_id[p.pid]); expect["hard_links"] += 1; expect["hard_confirmed"] += 1
for p in take(2):
    fintox(p); expect["strong"] += 1
expect["unlinked"]["fintox"] = 0

# BRCA (child of Breast, single site OAUTHC, hospital number field 'hosp_num')
brca_n = 0


def brca(p, hosp=None, hard=""):
    global brca_n
    brca_n += 1
    rid = str(brca_n)
    rows["brca"].append({"record_id": rid, "hosp_num": p.hosp if hosp is None else hosp,
                         "first_name": p.first, "surname": p.last, "breast_record_id": hard})
    truth.append(("brca", rid, p.pid))


for _ in range(8):
    p = next(bpool)
    brca(p, hard=breast_id[p.pid]); expect["hard_links"] += 1; expect["hard_confirmed"] += 1
for _ in range(3):
    brca(next(bpool)); expect["strong"] += 1
for p in [p for p in breast_people if p.hosp.startswith("0")]:   # zero dropped -> probable
    brca(p, hosp=p.hosp.lstrip("0")); expect["probable"] += 1
for _ in range(2):
    brca(Person("OAUTHC"))
expect["unlinked"]["brca"] = 2

# Pathology database (hospital no. + histology, no names)
path_n = 0


def path(p, hosp=None, hist=None):
    global path_n
    path_n += 1
    rid = f"PA-{path_n}"
    rows["path"].append({"record_id": rid, "redcap_data_access_group": "oau",
                         "hospital_number": p.hosp if hosp is None else hosp,
                         "histology_number_biopsy": hist or hist_text(p.hist),
                         "histology_number_surgery": ""})
    truth.append(("path", rid, p.pid))


for p in take(12):
    path(p); expect["strong"] += 1
for kind in ("year_differs", "year_differs", "prefix_differs", "one_digit"):
    p = next(pool)
    pre, n, yr = p.hist
    bad = {"year_differs": (pre, n, yr + 1), "prefix_differs": ("S", n, yr),
           "one_digit": (pre, int(typo(str(n), "one_digit")) if n >= 100 else n + 1, yr)}[kind]
    assert lk.compare_histology(lk.histology_number(hist_text(p.hist)),
                                lk.histology_number(hist_text(bad))) == kind, kind
    path(p, hist=hist_text(bad)); expect["near_miss"] += 1
for p in take(2):                                    # histology only, hospital number missing
    path(p, hosp=""); expect["probable"] += 1
for _ in range(2):
    path(Person("OAUTHC"))
expect["unlinked"]["path"] = 2

# A patient enrolled twice in CRC
p = next(pool)
rows["crc"].append({"research_number": f"40-{len(rows['crc']) + 1}",
                    "redcap_data_access_group": "oauthc", "hospital_no": p.hosp,
                    "histology_number": hist_text(p.hist), "first_name": p.first,
                    "surname": p.last})
truth.append(("crc", rows["crc"][-1]["research_number"], p.pid))
expect["duplicate"] += 1

# --- write ---------------------------------------------------------------------------------------

STUDIES = [
    # study, name, file, record_id_field, site_field, single_site, hosp_field, histology_fields,
    # first_name_field, last_name_field, parent_links
    ("crc", "CRC registry", "crc.csv", "research_number", "redcap_data_access_group", "",
     "hospital_no", "histology_number", "first_name", "surname", ""),
    ("breast", "Breast registry", "breast.csv", "record_id", "hospital_site", "",
     "hospital_number", "surg_histopath_no", "first_name", "surname", ""),
    ("r01", "R01", "r01.csv", "record_id", "redcap_data_access_group", "", "hospital_number", "",
     "first_name", "last_name", "colorectal_record_id=crc"),
    ("brca", "BRCA", "brca.csv", "record_id", "", "OAUTHC", "hosp_num", "", "first_name",
     "surname", "breast_record_id=breast"),
    ("fintox", "Financial toxicity", "fintox.csv", "record_id", "", "OAUTHC", "hospital_no", "",
     "first_name", "surname", "colorectal_record_id=crc;breast_record_id=breast"),
    ("path", "Pathology database", "path.csv", "record_id", "redcap_data_access_group", "",
     "hospital_number", "histology_number_biopsy;histology_number_surgery", "", "", ""),
]
HEAD = ["study", "name", "file", "record_id_field", "site_field", "single_site", "hosp_field",
        "histology_fields", "first_name_field", "last_name_field", "parent_links"]


def write_csv(path, header, data):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(data)


for study, recs in rows.items():
    write_csv(HERE / f"{study}.csv", list(recs[0]), [list(r.values()) for r in recs])
write_csv(HERE / "studies.csv", HEAD, STUDIES)
write_csv(HERE / "truth.csv", ["study", "record_id", "person"], truth)
manifest = {"seed": SEED, "synthetic": True,
            "note": "Made-up people. Counts are what link_patients.py must report.",
            "records": {k: len(v) for k, v in rows.items()}, "expect": expect}
(HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")
print(f"wrote {sum(len(v) for v in rows.values())} records in {len(rows)} studies; "
      f"expect {json.dumps(expect)}")
