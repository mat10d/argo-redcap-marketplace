#!/usr/bin/env python3
"""link_patients.py — link patients across ARGO studies from their exports. Read-only.

Reads one export per study (CSV, as downloaded from REDCap) and a studies file saying, for each
study, which fields hold the record ID, site, hospital number, histology numbers, names and parent
IDs. It never writes to REDCap and never calls a model. It writes, into --out:

  links.csv           accepted links: hard (a parent ID the study already stores) and strong
                      (site + hospital number + names agree, or hospital and histology numbers
                      agree where a study holds no names)
  persons.csv         one ARGO person ID per linked group of records
  hard_link_check.csv every stored parent ID, checked against the keys
  review.csv          for a person to decide: conflicts, a patient enrolled twice, parent IDs
                      that point at the wrong patient, and probable links
  near_misses.csv     likely typos, one row per pair; also split per site under worklists/
  names_to_judge.csv  name pairs the local check couldn't settle (names only, nothing else)
  summary.json        the counts

    python3 link_patients.py --studies studies.csv --exports <folder> --out <folder>

The output holds names and hospital numbers: send --out to ~/.argo/linkage/, never to a folder
Cowork can read.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import argo_linkage_keys as lk  # noqa: E402

STUDY_FIELDS = ["study", "name", "file", "record_id_field", "site_field", "single_site",
                "hosp_field", "histology_fields", "first_name_field", "last_name_field",
                "parent_links"]
STRONG_HOSP = {"exact", "suffix_differs"}
STRONG_HIST = {"exact", "exact_no_prefix"}


class Record:
    __slots__ = ("study", "rid", "site", "raw", "hosp", "hist", "parents", "expects")

    def __init__(self, study, rid, site, raw, parents):
        self.study, self.rid, self.site, self.raw, self.parents = study, rid, site, raw, parents
        self.hosp = lk.hospital_number(raw["hospital_number"], site)
        self.hist = [lk.histology_number(h, site) for h in raw["histology"]]

    @property
    def ref(self):
        return (self.study, self.rid)

    def has_key(self):
        return bool(self.hosp.key) or any(h.key for h in self.hist)


# --- reading -----------------------------------------------------------------------------------

def read_studies(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        studies = list(csv.DictReader(f))
    missing = [c for c in STUDY_FIELDS if studies and c not in studies[0]]
    if missing:
        sys.exit(f"The studies file {path} is missing these columns: {', '.join(missing)}.")
    return studies


def parse_parent_links(text):
    """'colorectal_record_id=crc[cohort=1];breast_colorectal_record_id=breast[cancer_type_cat=1]'
    -> [(field, parent_study, condition_column, allowed_values)]. The condition says which records
    should have this parent: R01's cohort 1 only, or Financial toxicity's one parent field pointing
    at Breast or CRC depending on cancer type. No condition: every record."""
    links = []
    for part in filter(None, (x.strip() for x in str(text or "").split(";"))):
        m = re.match(r"^([a-z0-9_]+)\s*=\s*([A-Za-z0-9_-]+)\s*(?:\[\s*([a-z0-9_]+)\s*=\s*([^\]]+)\])?$", part)
        if not m:
            sys.exit(f"I can't read the parent link '{part}'. Write it as field=study, or "
                     "field=study[column=value|value], e.g. colorectal_record_id=crc[cohort=1].")
        field, parent, col, vals = m.groups()
        links.append((field, parent, col, set(v.strip() for v in vals.split("|")) if vals else None))
    return links


def _merge_rows(rows, rid_field):
    """One record per ID. Projects with repeating forms or events export several rows per record:
    keep the first non-blank value of each field, and every distinct value under '__all__'."""
    merged, order = {}, []
    for r in rows:
        rid = r[rid_field]
        if rid not in merged:
            merged[rid] = {"__all__": {}}
            order.append(rid)
        m = merged[rid]
        for k, v in r.items():
            v = (v or "").strip()
            if v and not m.get(k):
                m[k] = v
            if v:
                m["__all__"].setdefault(k, [])
                if v not in m["__all__"][k]:
                    m["__all__"][k].append(v)
    return [merged[i] for i in order]


def read_records(spec, folder):
    path = Path(folder) / spec["file"]
    if not path.exists():
        sys.exit(f"I can't find the export for {spec['name']}: {path}. Download it from REDCap "
                 "(Data Exports, all records, CSV) and save it under that name.")
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)
    rid_field = spec["record_id_field"]
    if rid_field not in header:
        sys.exit(f"The export for {spec['name']} has no column '{rid_field}'. Export it again "
                 "choosing 'CSV / Microsoft Excel (raw data)', so the columns carry variable names, "
                 "not question labels.")
    links = parse_parent_links(spec["parent_links"])
    sites = lk.site_choices(spec.get("site_choices", "")) if spec.get("site_choices") else {}
    hist_fields = [h for h in spec["histology_fields"].split(";") if h]
    out = []
    for r in _merge_rows(rows, rid_field):
        site = spec["single_site"] or (r.get(spec["site_field"], "") if spec["site_field"] else "")
        site = sites.get(site, site)          # a coded site field: 0 -> OAUTHC
        hist = []
        for h in hist_fields:
            for v in r["__all__"].get(h, []):
                hist.extend(x for x in lk.split_histology(v) if x not in hist)
        raw = {"site": site, "hospital_number": r.get(spec["hosp_field"], ""), "histology": hist,
               "first_name": r.get(spec["first_name_field"], "") if spec["first_name_field"] else "",
               "last_name": r.get(spec["last_name_field"], "") if spec["last_name_field"] else ""}
        hard, expects = {}, []
        for field, parent, col, vals in links:
            if col and r.get(col, "") not in vals:
                continue
            expects.append(parent)
            if r.get(field, "").strip():
                hard[parent] = r[field].strip()
        rec = Record(spec["study"], r[rid_field], site, raw, hard)
        rec.expects = expects
        out.append(rec)
    return out


# --- candidate pairs ---------------------------------------------------------------------------

def _variants(key):
    """The key, the key without leading zeros, and the key with each one character removed.
    Two keys one substitution, swap or dropped digit apart always share one of these."""
    out = {key, key.lstrip("0")}
    out.update(key[:i] + key[i + 1:] for i in range(len(key)))
    return out


def candidate_pairs(records):
    buckets = defaultdict(set)
    for i, r in enumerate(records):
        if r.hosp.key:
            for v in _variants(r.hosp.key):
                buckets[("h", v)].add(i)
        for h in r.hist:
            if h.key:
                buckets[("n", h.number, h.year)].add(i)
                buckets[("p", h.prefix, h.number)].add(i)
                for v in _variants(str(h.number)):
                    buckets[("d", h.prefix, h.year, v)].add(i)
    pairs = set()
    for members in buckets.values():
        if len(members) > 50:          # a placeholder everyone shares: no information in it
            continue
        ms = sorted(members)
        pairs.update((a, b) for x, a in enumerate(ms) for b in ms[x + 1:])
    return sorted(pairs)


# --- linking -----------------------------------------------------------------------------------

def tier(f):
    if f.kind != "agree":
        return f.kind
    names_missing = f.names[1] == "missing"
    if f.hospital in STRONG_HOSP and (f.names[0] == "same"
                                      or (names_missing and f.histology in STRONG_HIST)):
        return "strong"
    return "probable"


def link(studies, records):
    by_ref = {r.ref: r for r in records}
    out = {k: [] for k in ("links", "hard_check", "review", "near_misses", "names_to_judge")}
    hard_pairs, held = set(), set()

    def row(kind, a, b, f, explain):
        return {"kind": kind, "study_a": a.study, "record_a": a.rid, "study_b": b.study,
                "record_b": b.rid, "hospital": f.hospital or "", "histology": f.histology or "",
                "names": "/".join(f.names), "explain": explain}

    # 1. Parent IDs the studies already store.
    for c in records:
        for parent_study, prid in c.parents.items():
            p = by_ref.get((parent_study, prid))
            if p is None:
                out["review"].append({"kind": "hard_link_missing_parent", "study_a": c.study,
                                      "record_a": c.rid, "study_b": parent_study,
                                      "record_b": prid, "hospital": "", "histology": "",
                                      "names": "", "explain": "The stored parent ID is not a "
                                      "record in the parent study's export."})
                continue
            hard_pairs.add(frozenset((c.ref, p.ref)))
            f = lk.compare_pair(c.raw, p.raw)
            verifiable = (c.hosp.key and p.hosp.key) or (any(h.key for h in c.hist)
                                                        and any(h.key for h in p.hist))
            if f.kind == "agree" or (f.kind == "unrelated" and not verifiable):
                state = "confirmed" if f.kind == "agree" else "unverifiable"
            elif f.kind == "near_miss":
                state = "typo"
                out["near_misses"].append(row("near_miss", c, p, f,
                                              "Already linked; " + f.explain[0].lower() + f.explain[1:]))
            else:
                state = "disagrees"
                held.add(c.ref)
                out["review"].append(row("hard_link_disagrees", c, p, f,
                                         "The stored parent ID points at a patient whose numbers "
                                         "and name don't match."))
            out["hard_check"].append({"study": c.study, "record": c.rid, "parent_study": p.study,
                                      "parent_record": p.rid, "state": state})
            if state in ("confirmed", "unverifiable", "typo"):
                out["links"].append(row("hard", c, p, f, "Parent ID stored in the study."))

    # 2. Pairs found by the keys.
    judged = 0
    for i, j in candidate_pairs(records):
        a, b = records[i], records[j]
        if frozenset((a.ref, b.ref)) in hard_pairs:
            continue
        f = lk.compare_pair(a.raw, b.raw)
        t = tier(f)
        if t == "unrelated":
            continue
        if a.study == b.study:
            if t in ("strong", "probable"):
                out["review"].append(row("duplicate", a, b, f,
                                         "The same patient looks enrolled twice in one study."))
            continue
        if a.ref in held or b.ref in held:
            note = next(r for r in out["review"] if r["kind"] == "hard_link_disagrees"
                        and (r["study_a"], r["record_a"]) in (a.ref, b.ref))
            note["explain"] += f" The numbers point at {b.study if a.ref in held else a.study} " \
                               f"{b.rid if a.ref in held else a.rid} instead."
            continue
        if t == "strong":
            out["links"].append(row("strong", a, b, f, f.explain))
        elif t == "probable":
            out["review"].append(row("probable", a, b, f, "Probably the same patient: "
                                     + ("numbers agree, names need a check."
                                        if f.names[0] == "ambiguous" and f.names[1] != "missing"
                                        else "only one number agrees.")))
        elif t == "near_miss":
            out["near_misses"].append(row("near_miss", a, b, f, f.explain))
        elif t == "conflict":
            out["review"].append(row("conflict", a, b, f, f.explain))
        if f.names[0] == "ambiguous" and f.names[1] not in ("missing",):
            judged += 1
            out["names_to_judge"].append({
                "pair": judged,
                "name_a": " ".join(lk.name_tokens(a.raw["first_name"], a.raw["last_name"])),
                "name_b": " ".join(lk.name_tokens(b.raw["first_name"], b.raw["last_name"]))})

    # 3. People: one ID per group joined by accepted links.
    parent = {r.ref: r.ref for r in records}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for l in out["links"]:
        a, b = find((l["study_a"], l["record_a"])), find((l["study_b"], l["record_b"]))
        if a != b:
            parent[max(a, b)] = min(a, b)
    groups = defaultdict(list)
    for r in records:
        groups[find(r.ref)].append(r.ref)
    persons, n = [], 0
    for root in sorted(groups, key=lambda g: sorted(groups[g])):
        n += 1
        for study, rid in sorted(groups[root]):
            persons.append({"argo_person_id": f"ARGO-{n:06d}", "study": study, "record_id": rid})
    out["persons"] = persons

    # 4. Counts.
    in_link = {(l["study_a"], l["record_a"]) for l in out["links"]} | \
              {(l["study_b"], l["record_b"]) for l in out["links"]}
    in_near = {(r["study_a"], r["record_a"]) for r in out["near_misses"]} | \
              {(r["study_b"], r["record_b"]) for r in out["near_misses"]}
    in_review = {(r["study_a"], r["record_a"]) for r in out["review"]} | \
                {(r["study_b"], r["record_b"]) for r in out["review"]}
    per_study = {}
    for s in studies:
        recs = [r for r in records if r.study == s["study"]]
        c = defaultdict(int)
        for r in recs:
            if r.ref in in_link:
                c["linked"] += 1
            elif r.ref in in_near:
                c["near_miss"] += 1
            elif r.ref in in_review:
                c["review"] += 1
            elif not r.has_key():
                c["blank_key"] += 1
            else:
                c["unlinked"] += 1
        scoped = [r for r in recs if r.expects]
        if scoped:
            c["expected_a_parent"] = len(scoped)
            c["expected_but_not_linked"] = sum(1 for r in scoped if r.ref not in in_link)
        per_study[s["study"]] = {"records": len(recs), **c}
    hard_states = defaultdict(int)
    for h in out["hard_check"]:
        hard_states[h["state"]] += 1
    kinds = defaultdict(int)
    for r in out["review"]:
        kinds[r["kind"]] += 1
    out["summary"] = {
        "records": len(records), "people": n,
        "hard_links": len(out["hard_check"]) + kinds["hard_link_missing_parent"],
        "hard_confirmed": hard_states["confirmed"], "hard_with_typo": hard_states["typo"],
        "hard_disagrees": hard_states["disagrees"], "hard_unverifiable": hard_states["unverifiable"],
        "strong": sum(1 for l in out["links"] if l["kind"] == "strong"),
        "probable": kinds["probable"], "near_miss": len(out["near_misses"]),
        "conflict": kinds["conflict"], "duplicate": kinds["duplicate"],
        "names_to_judge": len(out["names_to_judge"]), "per_study": per_study}
    return out


# --- writing -----------------------------------------------------------------------------------

WORKLIST_COLS = ["What to check", "Study A", "Record A", "Hospital no. A", "Histology no. A",
                 "Name A", "Study B", "Record B", "Hospital no. B", "Histology no. B", "Name B",
                 "RESPONSE"]


def _write(path, rows, header=None):
    header = header or (list(rows[0]) if rows else ["(none)"])
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def write_outputs(out, records, folder):
    folder = Path(folder)
    (folder / "worklists").mkdir(parents=True, exist_ok=True)
    for name in ("links", "persons", "hard_check", "review", "near_misses", "names_to_judge"):
        fname = "hard_link_check.csv" if name == "hard_check" else f"{name}.csv"
        _write(folder / fname, out[name])
    (folder / "summary.json").write_text(json.dumps(out["summary"], indent=1) + "\n")
    by_ref = {r.ref: r for r in records}
    per_site = defaultdict(list)
    for n in out["near_misses"]:
        a, b = by_ref[(n["study_a"], n["record_a"])], by_ref[(n["study_b"], n["record_b"])]
        site = b.hosp.site or a.hosp.site or "unknown_site"
        side = lambda r: [r.study, r.rid, r.raw["hospital_number"], "; ".join(r.raw["histology"]),  # noqa: E731
                          f"{r.raw['first_name']} {r.raw['last_name']}".strip()]
        per_site[site].append(dict(zip(WORKLIST_COLS, [n["explain"], *side(a), *side(b), ""])))
    for site, rows in per_site.items():
        _write(folder / "worklists" / f"near_misses_{site}.csv", rows, WORKLIST_COLS)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--studies", help="the studies file (one row per study)")
    ap.add_argument("--exports", help="the folder holding each study's export")
    ap.add_argument("--out", help="where to write the results (keep it outside Cowork's folder)")
    args = ap.parse_args(argv)
    if not (args.studies and args.exports and args.out):
        print("Give me three things: --studies (which fields each study uses), --exports (the "
              "folder with each study's downloaded CSV) and --out (where to put the results, "
              "e.g. ~/.argo/linkage/run-<date>). Nothing is written to REDCap.")
        return 2
    studies = read_studies(args.studies)
    records = [r for s in studies for r in read_records(s, args.exports)]
    out = link(studies, records)
    write_outputs(out, records, args.out)
    s = out["summary"]
    print(f"{s['records']} records in {len(studies)} studies -> {s['people']} people.")
    print(f"Links: {s['hard_confirmed']} stored parent IDs confirmed, {s['strong']} new by numbers "
          f"and name. Stored parent IDs to check: {s['hard_with_typo']} with a typo, "
          f"{s['hard_disagrees']} pointing at the wrong patient.")
    print(f"For a person: {s['conflict']} conflicts, {s['duplicate']} enrolled twice, "
          f"{s['probable']} probable. For the RAs: {s['near_miss']} near-misses. "
          f"Names to judge: {s['names_to_judge']}.")
    print(f"Written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
