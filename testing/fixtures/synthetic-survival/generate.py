#!/usr/bin/env python3
"""Seeded generator for the SYN synthetic SURVIVAL fixture.

SYNTHETIC TEST STUDY — "SYN — Synthetic Colorectal Cohort", follow-up edition.
Every value in every file this script writes is fabricated. No real people,
sites, or data.

It EXTENDS the existing synthetic cohort rather than inventing a new one: the
same 200 SYN- records, the same two sites, the same demographics and TNM stage,
and the same data dictionary (copied unchanged — the follow-up form already has
`fu_date`, `follow_status` and `death_date`). What changes is the dates: the
QA fixture's dates are deliberately incoherent (it exists to be audited), so
here the diagnosis → surgery → follow-up → death pathway is regenerated to be
clinically plausible, with a hazard that depends on N stage, M stage and age.

Then a small, exact set of defects is engineered in — the ones a time-to-event
derivation must refuse to paper over:

    dx_date is a date missing-data code (8888-08-08, 9999-09-09)   2
    dx_date blank although the patient consented                  2
    follow_status blank                                           2
    died (status 3) but death_date blank                          2
    died but death_date is a missing-data code (8888-08-08)       1
    alive, but fu_date (last follow-up) blank                     3
    death_date before dx_date                                     1
    death_date filled in although status is not "Deceased"        1
    age = -999 (Cox covariate missing, record still analysed)     2

plus the 4 non-consented records inherited from the source, whose dx_date is
blank because its branching logic ([consented] = 1) never fired.

Regenerates, byte-identically on every run (stdlib only, no timestamps):

    datadictionary.csv   copied from ../synthetic-study/ (unchanged)
    records.csv          200 records, coherent dates, engineered defects
    MANIFEST.json        every engineered count, and the counts the survival
                         analysis must report under the reference plan

Run:  python3 generate.py     (writes into its own directory)
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os
import random
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "..", "synthetic-study")
SEED = 20261008

#: The reference analysis plan the MANIFEST's expected counts are computed under.
PLAN = {
    "origin": "dx_date",
    "event_field": "follow_status",
    "event_codes": ["3"],
    "event_date": "death_date",
    "censor_date": "fu_date",
    "end_of_follow_up": "2026-06-30",
    "group_by": "tnm_n",
    "covariates": ["age", "sex", "tnm_n", "tnm_m"],
}

DAYS_PER_MONTH = 365.25 / 12
BASE_MEDIAN_MONTHS = 40.0          # N0 M0, age 60
LOG_HR = {"n1": 0.47, "n2": 0.95, "m1": 0.90, "age_per_year": 0.02}
LOSS_MEAN_MONTHS = 150.0           # ~10% lost to follow-up
FU_WINDOW = (dt.date(2026, 3, 1), dt.date(2026, 8, 31))   # last visit of the living
DATA_CLOSE = dt.date(2026, 8, 31)                         # nothing is dated after this


def d(s):
    return dt.date.fromisoformat(s)


def rand_between(rng, a, b):
    return a + dt.timedelta(days=rng.randint(0, (b - a).days))


def build_records(rng):
    with open(os.path.join(SOURCE, "records.csv"), newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames
        rows = [dict(r) for r in reader]

    for r in rows:
        consented = r["consented"] == "1"
        # --- the clinical pathway, coherent this time ----------------------------
        for f in ("dx_date", "surgery_date", "fu_date", "follow_status", "recurrence_date",
                  "recurrence_site", "death_date", "support_needed", "next_fu_date",
                  "lost_reason"):
            r[f] = ""
        if not consented:
            continue                                   # dx_date not asked: branching
        dx = rand_between(rng, dt.date(2023, 1, 1), dt.date(2024, 12, 31))
        r["dx_date"] = dx.isoformat()
        r["enrol_date"] = (dx + dt.timedelta(days=rng.randint(0, 30))).isoformat()
        if r["surgery_done"] == "1":
            r["surgery_date"] = (dx + dt.timedelta(days=rng.randint(14, 90))).isoformat()

        lin = (LOG_HR["n1"] * (r["tnm_n"] == "1") + LOG_HR["n2"] * (r["tnm_n"] == "2")
               + LOG_HR["m1"] * (r["tnm_m"] == "1")
               + LOG_HR["age_per_year"] * (int(r["age"]) - 60))
        rate = math.log(2) / BASE_MEDIAN_MONTHS * math.exp(lin)
        t_death = dx + dt.timedelta(days=round(rng.expovariate(rate) * DAYS_PER_MONTH))
        t_loss = dx + dt.timedelta(days=round(rng.expovariate(1 / LOSS_MEAN_MONTHS)
                                              * DAYS_PER_MONTH))
        last_visit = rand_between(rng, *FU_WINDOW)

        if t_death <= min(t_loss, last_visit):
            r["follow_status"] = "3"
            r["death_date"] = t_death.isoformat()
            r["fu_date"] = min(t_death + dt.timedelta(days=rng.randint(0, 30)),
                               DATA_CLOSE).isoformat()
        elif t_loss < last_visit:
            r["follow_status"] = "4"
            r["fu_date"] = t_loss.isoformat()
            r["lost_reason"] = str(rng.randint(1, 3))
            r["support_needed"] = str(rng.randint(0, 1))
        else:
            r["fu_date"] = last_visit.isoformat()
            if rng.random() < 0.3:
                r["follow_status"] = "2"
                rec = rand_between(rng, dx + dt.timedelta(days=90), last_visit)
                r["recurrence_date"] = rec.isoformat()
                r["recurrence_site"] = str(rng.randint(1, 3))
                r["support_needed"] = str(rng.randint(0, 1))
            else:
                r["follow_status"] = "1"
            r["next_fu_date"] = (last_visit + dt.timedelta(days=180)).isoformat()
    return header, rows


def engineer(rng, rows):
    """Plant the defects, each on its own records, and say which records got which."""
    consented = [r for r in rows if r["consented"] == "1"]
    dead = [r for r in consented if r["follow_status"] == "3"]
    alive = [r for r in consented if r["follow_status"] in ("1", "2")]
    used = set()

    def pick(pool, k):
        pool = [r for r in pool if r["syn_id"] not in used]
        chosen = rng.sample(pool, k)
        used.update(r["syn_id"] for r in chosen)
        return chosen

    planted = {}
    chosen = pick(consented, 2)
    chosen[0]["dx_date"], chosen[1]["dx_date"] = "8888-08-08", "9999-09-09"
    planted["dx_date_mdc"] = chosen
    for r in (chosen := pick(consented, 2)):
        r["dx_date"] = ""
    planted["dx_date_blank"] = chosen
    for r in (chosen := pick(consented, 2)):
        r["follow_status"] = ""
        r["death_date"] = ""
    planted["status_blank"] = chosen
    for r in (chosen := pick(dead, 2)):
        r["death_date"] = ""
    planted["death_date_blank"] = chosen
    for r in (chosen := pick(dead, 1)):
        r["death_date"] = "8888-08-08"
    planted["death_date_mdc"] = chosen
    for r in (chosen := pick(alive, 3)):
        r["fu_date"] = ""
    planted["fu_date_blank"] = chosen
    for r in (chosen := pick(dead, 1)):
        r["death_date"] = (d(r["dx_date"]) - dt.timedelta(days=40)).isoformat()
    planted["death_before_dx"] = chosen
    for r in (chosen := pick(alive, 1)):
        r["death_date"] = r["fu_date"]
    planted["death_date_not_dead"] = chosen
    # Cox covariate missing — the record stays in the KM/log-rank analysis.
    for r in (chosen := pick(consented, 2)):
        r["age"] = "-999"
    planted["age_mdc"] = chosen
    return {k: sorted(r["syn_id"] for r in v) for k, v in planted.items()}


def expected(rows):
    """What the survival analysis must report under PLAN — computed here, separately
    from the library, so the test compares two independent derivations."""
    end = d(PLAN["end_of_follow_up"])
    reasons, analysed = {}, []
    for r in rows:
        why = None
        if r["consented"] != "1":
            why = "start_not_applicable"
        elif r["dx_date"] in ("6666-06-06", "7777-07-07", "8888-08-08", "9999-09-09"):
            why = "start_mdc"
        elif r["dx_date"] == "":
            why = "start_blank"
        elif r["follow_status"] == "":
            why = "status_unknown"
        elif r["follow_status"] == "3" and r["death_date"] in ("", "8888-08-08"):
            why = "event_date_missing"
        elif r["follow_status"] != "3" and r["death_date"] != "":
            why = "event_date_contradicts_status"
        elif r["follow_status"] != "3" and r["fu_date"] == "":
            why = "censor_date_missing"
        else:
            start = d(r["dx_date"])
            stop = d(r["death_date"] if r["follow_status"] == "3" else r["fu_date"])
            if stop < start:
                why = "end_before_start"
        if why:
            reasons[why] = reasons.get(why, 0) + 1
            continue
        start = d(r["dx_date"])
        event = r["follow_status"] == "3"
        stop = d(r["death_date"] if event else r["fu_date"])
        administratively_censored = stop > end
        if administratively_censored:
            stop, event = end, False
        analysed.append((r, (stop - start).days, event, administratively_censored))

    by_group = {}
    for r, _, event, _ in analysed:
        g = by_group.setdefault(r["tnm_n"], {"n": 0, "events": 0})
        g["n"] += 1
        g["events"] += int(event)
    return {
        "excluded": dict(sorted(reasons.items())),
        "excluded_total": sum(reasons.values()),
        "analysed": len(analysed),
        "events": sum(int(e) for _, _, e, _ in analysed),
        "censored_at_end_of_follow_up": sum(int(a) for *_, a in analysed),
        "by_group": dict(sorted(by_group.items())),
        "cox_complete_cases": sum(1 for r, *_ in analysed if r["age"] != "-999"),
    }


def main():
    rng = random.Random(SEED)
    header, rows = build_records(rng)
    planted = engineer(rng, rows)

    shutil.copyfile(os.path.join(SOURCE, "datadictionary.csv"),
                    os.path.join(HERE, "datadictionary.csv"))
    with open(os.path.join(HERE, "records.csv"), "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "contract_version": 1,
        "synthetic": True,
        "note": "SYNTHETIC TEST DATA — no real people. Derived from ../synthetic-study.",
        "seed": SEED,
        "n_records": len(rows),
        "plan": PLAN,
        "planted": planted,
        "expected": expected(rows),
    }
    with open(os.path.join(HERE, "MANIFEST.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps(manifest["expected"], indent=2))


if __name__ == "__main__":
    main()
