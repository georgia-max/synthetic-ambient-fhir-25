"""Seeding CLI: dataset -> vertical-slice bootstrap files.

Run (cwd = hospital_gen_agent):
    python -m hgen.seeding.build

Writes storage/base_hospital/{reverie/meta.json, environment/0.json,
personas/<Name>/bootstrap_memory/...} for the seven-persona slice cast, then
prints a summary. Deterministic: a pure function of the dataset.
"""
from __future__ import annotations

import json

from hgen.config import DATASET, STORAGE
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
from hgen.seeding.world import CURR_TIME, START_DATE

HERO_NAME = "Clarence Reinger"
OB_DEPT = "OB / Prenatal Clinic"
GENERAL_EXAM = "General examination of patient (procedure)"

# Persona order for meta.json (subplan B section 3).
PERSONA_ORDER = [
    "Clarence Reinger", "Marcus", "Nurse Reyes", "Dr. Amari",
    "Rosa Diaz", "Patient A", "Patient B",
]

# Spawn tiles (subplan B section 2).
SPAWN_TILES = {
    "Clarence Reinger": (2, 13),
    "Marcus": (3, 13),
    "Nurse Reyes": (13, 3),
    "Dr. Amari": (23, 3),
    "Rosa Diaz": (4, 3),
    "Patient A": (4, 10),
    "Patient B": (5, 10),
}


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
    """Pick the first ``n`` general-exam records other than the hero (deterministic)."""
    out = []
    for r in records:
        if r is hero:
            continue
        if r["metadata"]["visit_type"] == GENERAL_EXAM:
            out.append(r)
        if len(out) == n:
            break
    return out


def build_cast(records: list[dict]) -> dict:
    """Build every persona -> (scratch, spatial_tree, nodes)."""
    hero = find_hero(records)
    bg_a, bg_b = find_backgrounds(records, hero)
    cast = {
        "Clarence Reinger": build_patient(hero),
        "Marcus": build_family(hero, HERO_NAME, name="Marcus"),
        "Nurse Reyes": build_triage_nurse(records, name="Nurse Reyes"),
        "Dr. Amari": build_department_doctor(
            records, "Dr. Amari", OB_DEPT,
            learned="obstetrician (OB)",
            plan_verbs="review the chart, examine, order prenatal labs and an "
                       "ultrasound, and counsel patients",
            hero_record=hero,
        ),
        "Rosa Diaz": build_reception(records, name="Rosa Diaz"),
        "Patient A": build_patient(bg_a, name="Patient A"),
        "Patient B": build_patient(bg_b, name="Patient B"),
    }
    return cast


def main() -> None:
    records = load_records()
    cast = build_cast(records)

    base = STORAGE / "base_hospital"
    personas_dir = base / "personas"

    # Persona bootstraps.
    for name in PERSONA_ORDER:
        scratch, spatial, nodes = cast[name]
        write_persona_bootstrap(personas_dir, scratch, spatial, nodes)

    # meta.json + environment/0.json.
    meta = make_meta(START_DATE, CURR_TIME, PERSONA_ORDER)
    write_meta(base / "reverie" / "meta.json", meta)
    env = make_environment({n: SPAWN_TILES[n] for n in PERSONA_ORDER})
    write_environment(base / "environment", 0, env)

    # Summary.
    print(f"Seeded {len(PERSONA_ORDER)} personas -> {base}")
    print(f"  meta: start={START_DATE!r} curr_time={CURR_TIME!r} "
          f"sec_per_step={meta['sec_per_step']} maze={meta['maze_name']!r} step={meta['step']}")
    total = 0
    for name in PERSONA_ORDER:
        _, _, nodes = cast[name]
        total += len(nodes)
        types = {}
        for nd in nodes:
            types[nd.type] = types.get(nd.type, 0) + 1
        tsum = ", ".join(f"{k}:{v}" for k, v in sorted(types.items())) or "—"
        print(f"  {name:<18} spawn={SPAWN_TILES[name]}  nodes={len(nodes):>2} ({tsum})")
    print(f"  total associative nodes: {total}")


if __name__ == "__main__":
    main()
