#!/usr/bin/env python3
"""Explore the synthetic-ambient-fhir-25 dataset.

25 synthetic clinical encounters (one per patient). Each record pairs an
ambient conversation transcript with the resulting clinical note, an
after-visit summary, the patient's chart background, and structured FHIR R4
context.

Run:  python3 explore.py
      python3 explore.py --record 0     # dump one full encounter
"""

import argparse
import json
import statistics
from collections import Counter
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).parent
JSONL = HERE / "synthetic-ambient-fhir-25.jsonl"


def load_records(path=JSONL):
    """Load the canonical JSONL dataset, one record per line."""
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def parse_date(s):
    """Parse an ISO date/datetime string to a date, tolerating a 'Z' suffix."""
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date()


def age_at(birth_date, on_date):
    """Whole-year age of a patient on a given date."""
    b, d = parse_date(birth_date), parse_date(on_date)
    return d.year - b.year - ((d.month, d.day) < (b.month, b.day))


def hr(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def overview(records):
    hr("OVERVIEW")
    print(f"Records: {len(records)}")
    patients = {r["metadata"]["patient_id"] for r in records}
    print(f"Unique patients: {len(patients)}")
    dates = sorted(parse_date(r["metadata"]["date"]) for r in records)
    print(f"Encounter date range: {dates[0]} → {dates[-1]}")


def demographics(records):
    hr("DEMOGRAPHICS")
    genders = Counter(r["patient_context"]["patient"]["gender"] for r in records)
    print("Gender:", dict(genders))

    ages = [
        age_at(r["patient_context"]["patient"]["birthDate"], r["metadata"]["date"])
        for r in records
    ]
    print(
        f"Age at visit: min={min(ages)}  median={int(statistics.median(ages))}  "
        f"max={max(ages)}  mean={statistics.mean(ages):.1f}"
    )
    bands = Counter()
    for a in ages:
        bands[f"{(a // 10) * 10}s"] += 1
    print("Age bands:", dict(sorted(bands.items())))

    states = Counter(
        r["patient_context"]["patient"].get("address", [{}])[0].get("state", "?")
        for r in records
    )
    print("States:", dict(states.most_common()))


def visit_types(records):
    hr("VISIT TYPES")
    types = Counter(r["metadata"]["visit_type"] for r in records)
    for vt, n in types.most_common():
        print(f"  {n:>2}  {vt}")


def text_sizes(records):
    hr("TEXT SIZES (word counts)")
    for label, key in [("Transcript", "transcript"), ("Note", "note"),
                       ("After-visit summary", "after_visit_summary")]:
        counts = [len(r[key].split()) for r in records]
        print(
            f"  {label:<22} min={min(counts):>5}  "
            f"median={int(statistics.median(counts)):>5}  max={max(counts):>5}  "
            f"total={sum(counts):>6}"
        )


def fhir_resources(records):
    hr("FHIR RESOURCES RECORDED AT THE VISIT")
    per_encounter = Counter()
    totals = Counter()
    for r in records:
        counts = r["metadata"]["related_resource_counts"]
        per_encounter[r["metadata"]["visit_title"]] = sum(counts.values())
        totals.update(counts)
    print("By resource type (across all encounters):")
    for rtype, n in totals.most_common():
        print(f"  {n:>5}  {rtype}")
    print(f"\n  Total FHIR resources at visits: {sum(totals.values())}")

    hr("LONGITUDINAL CHART SIZE (full patient record)")
    chart_totals = [
        sum(r["patient_context"]["longitudinal_summary"]["resource_counts"].values())
        for r in records
    ]
    print(
        f"  Resources per patient chart: min={min(chart_totals)}  "
        f"median={int(statistics.median(chart_totals))}  max={max(chart_totals)}"
    )


def top_conditions(records):
    hr("MOST COMMON ACTIVE CONDITIONS (across patient charts)")
    conds = Counter()
    for r in records:
        conds.update(r["patient_context"]["longitudinal_summary"]["condition_labels"])
    for label, n in conds.most_common(15):
        print(f"  {n:>2}  {label}")


def encounter_table(records):
    hr("ENCOUNTER INDEX")
    rows = sorted(records, key=lambda r: parse_date(r["metadata"]["date"]))
    print(f"  {'date':<12} {'age':>3} {'sex':<6} {'fhir':>5}  title")
    for r in rows:
        m = r["metadata"]
        p = r["patient_context"]["patient"]
        age = age_at(p["birthDate"], m["date"])
        fhir = sum(m["related_resource_counts"].values())
        print(
            f"  {parse_date(m['date']).isoformat():<12} {age:>3} "
            f"{p['gender']:<6} {fhir:>5}  {m['visit_title']}"
        )


def dump_record(records, i):
    """Print one full encounter in a readable form."""
    r = records[i]
    m = r["metadata"]
    hr(f"RECORD {i}: {m['visit_title']}")
    print(f"Date: {parse_date(m['date'])}   Type: {m['visit_type']}")
    print(f"FHIR at visit: {m['related_resource_counts']}")
    for label, key in [("TRANSCRIPT", "transcript"), ("NOTE", "note"),
                       ("AFTER-VISIT SUMMARY", "after_visit_summary")]:
        print(f"\n--- {label} ---")
        print(r[key].strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", type=int, metavar="N",
                    help="dump the full transcript/note/AVS for record N")
    args = ap.parse_args()

    records = load_records()

    if args.record is not None:
        dump_record(records, args.record)
        return

    overview(records)
    demographics(records)
    visit_types(records)
    text_sizes(records)
    fhir_resources(records)
    top_conditions(records)
    encounter_table(records)


if __name__ == "__main__":
    main()
