"""Seeding CLI: dataset -> full-hospital bootstrap files.

Run (cwd = hospital_gen_agent):
    python -m hgen.seeding.build

Builds a patient persona for EVERY dataset record (25), routed to its real
department by ``visit_type``, plus the hero's spouse Marcus and the clinical
staff: one doctor per clinical department (5), two triage nurses, and a reception
clerk. Writes storage/base_hospital/{reverie/meta.json, environment/0.json,
personas/<Name>/bootstrap_memory/...} and prints a summary.

Deterministic: a pure function of the dataset. Persona names are stable and
collision-free (duplicates get the last 4 of patient_id appended).
"""
from __future__ import annotations

import json

from hgen.config import DATASET, STORAGE, WORLD_NAME
from hgen.contracts import (
    make_environment,
    make_meta,
    write_environment,
    write_meta,
    write_persona_bootstrap,
)
from hgen.seeding.names import patient_name
from hgen.seeding.patients import build_patient
from hgen.seeding.staff import (
    build_department_doctor,
    build_family,
    build_reception,
    build_triage_nurse,
)
from hgen.seeding.world import CURR_TIME, START_DATE, department_for

HERO_NAME = "Clarence Reinger"
OB_DEPT = "OB / Prenatal Clinic"
GENERAL_EXAM = "General examination of patient (procedure)"

# --------------------------------------------------------------------------- #
# Staff roster: one doctor per clinical department + nurses + reception clerk. #
# --------------------------------------------------------------------------- #
# (name, department, learned, plan_verbs). Dr. Amari (OB) additionally carries
# the hero record's Assessment/Plan (wired in build_cast).
DOCTORS = [
    ("Dr. Amari", OB_DEPT, "obstetrician (OB)",
     "review the chart, examine, order prenatal labs and an ultrasound, and counsel patients"),
    ("Dr. Okafor", "General Medicine", "general practitioner",
     "review the chart, examine, order routine labs, and give preventive-care advice"),
    ("Dr. Bhatt", "Inpatient Ward", "hospitalist",
     "admit the patient, manage the inpatient stay, and coordinate the procedure"),
    ("Dr. Nguyen", "Isolation Unit", "infectious-disease physician",
     "assess in isolation, order infection work-up, and manage precautions"),
    ("Dr. Serrano", "Hospice / Palliative", "palliative-care physician",
     "review goals of care, manage comfort, and support the patient and family"),
]

# Spawn tiles for staff (their on-shift station; must be walkable in the maze).
STAFF_SPAWN = {
    "Rosa Diaz": (4, 3),
    "Nurse Reyes": (12, 3),
    "Nurse Kim": (13, 3),
    "Dr. Amari": (31, 3),
    "Dr. Okafor": (22, 3),
    "Dr. Bhatt": (38, 3),
    "Dr. Nguyen": (17, 11),
    "Dr. Serrano": (27, 11),
}

# Patients (and Marcus) spawn at / beside the Home entrance on the corridor.
HOME_TILE = (1, 8)
MARCUS_TILE = (2, 8)


def load_records() -> list[dict]:
    """Load the dataset JSONL, one record per line."""
    with open(DATASET, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def find_hero(records: list[dict]) -> dict:
    """Return the Clarence Reinger prenatal record."""
    for r in records:
        if patient_name(r["patient_context"]["patient"])[0] == HERO_NAME:
            return r
    raise ValueError(f"hero record {HERO_NAME!r} not found in dataset")


def find_backgrounds(records: list[dict], hero: dict, n: int = 2) -> list[dict]:
    """Pick the first ``n`` general-exam records other than the hero (deterministic).

    Retained for the legacy scripted director fallback (Patient A / Patient B).
    """
    out = []
    for r in records:
        if r is hero:
            continue
        if r["metadata"]["visit_type"] == GENERAL_EXAM:
            out.append(r)
        if len(out) == n:
            break
    return out


def _unique_patient_names(records: list[dict]) -> dict[int, str]:
    """Map each record's index to a stable, collision-free persona name.

    Duplicate normalized names get the last 4 of the patient_id appended
    (subplan A section 1), keeping keys unique across the whole cast.
    """
    # First pass: how many records share each normalized name.
    counts: dict[str, int] = {}
    for r in records:
        full = patient_name(r["patient_context"]["patient"])[0]
        counts[full] = counts.get(full, 0) + 1
    # Second pass: disambiguate only the collisions, deterministically.
    out: dict[int, str] = {}
    for i, r in enumerate(records):
        full = patient_name(r["patient_context"]["patient"])[0]
        if counts[full] > 1:
            pid = str(r["patient_context"]["patient"].get("id", ""))
            full = f"{full} {pid[-4:]}" if pid else full
        out[i] = full
    return out


def build_cast(records: list[dict]) -> tuple[dict, list[str]]:
    """Build every persona -> (scratch, spatial_tree, nodes) and the persona order.

    Order: hero, spouse, the other 24 patients (dataset order), then staff.
    """
    hero = find_hero(records)
    names_by_idx = _unique_patient_names(records)

    cast: dict = {}
    patient_order: list[str] = []

    # 1. All 25 patients, each routed to its real department by visit_type.
    for i, r in enumerate(records):
        pname = names_by_idx[i]
        cast[pname] = build_patient(r, name=pname)
        patient_order.append(pname)

    # 2. Hero's spouse (follower, no cognition).
    cast["Marcus"] = build_family(hero, HERO_NAME, name="Marcus")

    # 3. Staff: reception clerk, two triage nurses, one doctor per department.
    cast["Rosa Diaz"] = build_reception(records, name="Rosa Diaz")
    cast["Nurse Reyes"] = build_triage_nurse(records, name="Nurse Reyes")
    cast["Nurse Kim"] = build_triage_nurse(records, name="Nurse Kim")
    for dname, dept, learned, verbs in DOCTORS:
        cast[dname] = build_department_doctor(
            records, dname, dept, learned=learned, plan_verbs=verbs,
            hero_record=(hero if dept == OB_DEPT else None),
        )

    # Persona order: hero first, spouse next, the rest of the patients, then staff.
    hero_first = [HERO_NAME] + [n for n in patient_order if n != HERO_NAME]
    staff_order = (["Marcus", "Rosa Diaz", "Nurse Reyes", "Nurse Kim"]
                   + [d[0] for d in DOCTORS])
    order = hero_first + staff_order
    return cast, order


def _spawn_tiles(order: list[str]) -> dict[str, tuple[int, int]]:
    """Assign a spawn tile to every persona (patients at Home; staff on-station)."""
    tiles: dict[str, tuple[int, int]] = {}
    for name in order:
        if name == "Marcus":
            tiles[name] = MARCUS_TILE
        elif name in STAFF_SPAWN:
            tiles[name] = STAFF_SPAWN[name]
        else:  # a patient
            tiles[name] = HOME_TILE
    return tiles


def main() -> None:
    records = load_records()
    cast, order = build_cast(records)
    spawn = _spawn_tiles(order)

    base = STORAGE / "base_hospital"
    personas_dir = base / "personas"

    # Persona bootstraps.
    for name in order:
        scratch, spatial, nodes = cast[name]
        write_persona_bootstrap(personas_dir, scratch, spatial, nodes)

    # meta.json + environment/0.json.
    meta = make_meta(START_DATE, CURR_TIME, order)
    write_meta(base / "reverie" / "meta.json", meta)
    env = make_environment({n: spawn[n] for n in order})
    write_environment(base / "environment", 0, env)

    # Summary.
    patients = [n for n in order if cast[n][0].living_area == "Home" and n != "Marcus"]
    print(f"Seeded {len(order)} personas ({len(patients)} patients + "
          f"{len(order) - len(patients)} staff/family) -> {base}")
    print(f"  meta: start={START_DATE!r} curr_time={CURR_TIME!r} "
          f"sec_per_step={meta['sec_per_step']} maze={meta['maze_name']!r} step={meta['step']}")
    # Department routing evidence.
    print("  routing (visit_type -> department):")
    for i, r in enumerate(records):
        pname = _unique_patient_names(records)[i]
        dept = department_for(r["metadata"]["visit_type"])
        print(f"    {pname:<22} {dept}")
    total = sum(len(cast[n][2]) for n in order)
    print(f"  total associative nodes: {total}")


if __name__ == "__main__":
    main()
