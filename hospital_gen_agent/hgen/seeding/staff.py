"""Staff persona seeding: authored personas + dataset-aggregated knowledge.

Subplan A section 4. Staff power comes from aggregating the 25 records into
clinical knowledge nodes: the triage nurse learns vital-sign ranges, each
department doctor learns the common conditions/procedures for their department.
Staff hold the full world tree as spatial memory.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from hgen.contracts import ConceptNode, Scratch
from hgen.seeding.names import parse_family_name
from hgen.seeding.notes import assessment_headings, parse_note, parse_transcript
from hgen.seeding.patients import (
    NodeBuilder,
    _created_times,
    _plus_30d,
    poignancy_for,
    short_label,
)
from hgen.seeding.world import (
    CURR_TIME,
    canonical_world_tree,
    department_for,
    patient_start_spatial,
)

# Physiologic vitals the triage nurse aggregates (code.text -> display name).
VITAL_DISPLAY = {
    "Heart rate": "heart rate",
    "Respiratory rate": "respiratory rate",
    "Body Weight": "body weight",
    "Body Height": "body height",
    "Body mass index (BMI) [Ratio]": "body mass index",
    "Body temperature": "body temperature",
    "Oxygen saturation in Arterial blood": "oxygen saturation",
}
BP_CODE = "Blood pressure panel with all children optional"


def _fmt(x: float) -> str:
    """Format a measurement, dropping a trailing .0."""
    return str(int(x)) if float(x) == int(x) else f"{x:.1f}"


def _obs_code(o: dict) -> str:
    return (o.get("code") or {}).get("text", "")


def aggregate_vitals(records: list[dict]) -> dict:
    """Collect vital-sign value ranges across every record's Observations.

    Returns {display_name: {"lo","hi","unit"}} for scalar vitals plus a special
    "blood pressure" entry with systolic/diastolic ranges.
    """
    scalars: dict[str, list[float]] = {}
    units: dict[str, str] = {}
    sys_vals: list[float] = []
    dia_vals: list[float] = []
    for r in records:
        for o in r["encounter_fhir"]["related_resources"].get("Observation", []):
            code = _obs_code(o)
            if code == BP_CODE:
                for comp in o.get("component") or []:
                    ct = _obs_code(comp)
                    vq = comp.get("valueQuantity") or {}
                    if "Systolic" in ct and vq.get("value") is not None:
                        sys_vals.append(vq["value"])
                    elif "Diastolic" in ct and vq.get("value") is not None:
                        dia_vals.append(vq["value"])
            elif code in VITAL_DISPLAY:
                vq = o.get("valueQuantity") or {}
                if vq.get("value") is not None:
                    scalars.setdefault(code, []).append(vq["value"])
                    units[code] = vq.get("unit", "")

    out: dict = {}
    for code in VITAL_DISPLAY:  # deterministic order
        vals = scalars.get(code)
        if vals:
            out[VITAL_DISPLAY[code]] = {
                "lo": min(vals), "hi": max(vals), "unit": units.get(code, "")
            }
    if sys_vals and dia_vals:
        out["blood pressure"] = {
            "sys_lo": min(sys_vals), "sys_hi": max(sys_vals),
            "dia_lo": min(dia_vals), "dia_hi": max(dia_vals), "unit": "mm[Hg]",
        }
    return out


def _staff_scratch(
    name: str, age: int, learned: str, dept: str, plan_verbs: str, curr_time: str
) -> Scratch:
    parts = name.split(" ", 1)
    return Scratch(
        curr_time=curr_time,
        name=name,
        first_name=parts[0],
        last_name=parts[1] if len(parts) > 1 else "",
        age=age,
        innate="steady, attentive, kind",
        learned=learned,
        currently=f"on shift in {dept}",
        lifestyle="works clinical shifts at the hospital",
        living_area=dept,
        daily_plan_req=f"See patients in {dept}: {plan_verbs}.",
    )


def build_reception(
    records: list[dict], name: str = "Rosa Diaz", curr_time: str = CURR_TIME
) -> tuple[Scratch, dict, list[ConceptNode]]:
    """Authored reception clerk with minimal front-desk knowledge."""
    scratch = _staff_scratch(
        name, 41, "front-desk reception clerk", "Admissions",
        "greet arrivals, check them in, and direct them to the waiting room",
        curr_time,
    )
    chronic, _ = _created_times(curr_time)
    nb = NodeBuilder()
    nb.add("thought", name, "knows", "the check-in process",
           f"{name} checks patients in and routes them to Triage or their clinic.",
           chronic, 4, [name, "check-in"], expiration=_plus_30d(chronic))
    nb.add("thought", name, "can book", "follow-up nurse visits",
           f"{name} books follow-up nurse visits and next appointments at the desk.",
           chronic, 4, [name, "appointments"], expiration=_plus_30d(chronic))
    return scratch, canonical_world_tree(), nb.nodes


def build_triage_nurse(
    records: list[dict], name: str = "Nurse Reyes", curr_time: str = CURR_TIME
) -> tuple[Scratch, dict, list[ConceptNode]]:
    """Triage nurse whose knowledge is aggregated vital-sign ranges."""
    scratch = _staff_scratch(
        name, 38, "triage nurse", "Triage",
        "take vitals, get a brief history, assign acuity, and call patients back",
        curr_time,
    )
    chronic, _ = _created_times(curr_time)
    nb = NodeBuilder()
    vitals = aggregate_vitals(records)
    for vital, v in vitals.items():
        if vital == "blood pressure":
            desc = (
                f"Typical blood pressure runs about {_fmt(v['sys_lo'])}/"
                f"{_fmt(v['dia_lo'])} to {_fmt(v['sys_hi'])}/{_fmt(v['dia_hi'])} "
                f"{v['unit']} here."
            )
        else:
            unit = f" {v['unit']}" if v["unit"] else ""
            desc = f"Typical {vital} runs about {_fmt(v['lo'])}-{_fmt(v['hi'])}{unit} here."
        nb.add("thought", name, "knows", vital, desc, chronic, 5, [name, vital],
               expiration=_plus_30d(chronic))
    return scratch, canonical_world_tree(), nb.nodes


def build_department_doctor(
    records: list[dict],
    name: str,
    dept: str,
    *,
    learned: str,
    plan_verbs: str,
    hero_record: Optional[dict] = None,
    curr_time: str = CURR_TIME,
    top_conditions: int = 6,
    top_procedures: int = 6,
) -> tuple[Scratch, dict, list[ConceptNode]]:
    """Department doctor: common conditions/procedures for their department, plus
    (if given) the hero record's Assessment/Plan as the expected outcome."""
    scratch = _staff_scratch(name, 45, learned, dept, plan_verbs, curr_time)
    chronic, _ = _created_times(curr_time)
    nb = NodeBuilder()

    dept_records = [r for r in records if department_for(r["metadata"]["visit_type"]) == dept]

    # Common conditions: longitudinal labels + this-visit Conditions in this dept.
    cond_counts: Counter = Counter()
    for r in dept_records:
        labels = list(r["patient_context"]["longitudinal_summary"].get("condition_labels", []))
        for c in r["encounter_fhir"]["related_resources"].get("Condition", []):
            t = (c.get("code") or {}).get("text")
            if t:
                labels.append(t)
        for l in labels:
            if poignancy_for(l) >= 5:  # clinical only
                cond_counts[short_label(l)] += 1
    for sl, _cnt in sorted(cond_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_conditions]:
        nb.add("thought", name, "commonly sees", sl,
               f"{name} commonly sees {sl} in {dept}.",
               chronic, 6, [name, sl], expiration=_plus_30d(chronic))

    # Common procedures ordered in this department.
    proc_counts: Counter = Counter()
    for r in dept_records:
        for p in r["encounter_fhir"]["related_resources"].get("Procedure", []):
            t = (p.get("code") or {}).get("text")
            if t:
                proc_counts[short_label(t)] += 1
    common_procs = [sl for sl, c in sorted(proc_counts.items(), key=lambda kv: (-kv[1], kv[0]))
                    if c >= 2][:top_procedures]
    for sl in common_procs:
        nb.add("thought", name, "orders", sl, f"{name} orders {sl} at these visits.",
               chronic, 5, [name, sl], expiration=_plus_30d(chronic))

    # Hero expected outcome from the note's Assessment and Plan.
    if hero_record is not None:
        hp = hero_record["patient_context"]["patient"]
        hero_first = hp["name"][0].get("given", [""])[0]
        import re as _re
        hero_first = _re.sub(r"\d+$", "", hero_first)
        hero_last = _re.sub(r"\d+$", "", hp["name"][0].get("family", ""))
        hero_name = f"{hero_first} {hero_last}".strip()
        ap = parse_note(hero_record.get("note", "")).get("assessment_and_plan", "")
        heads = assessment_headings(ap)
        if heads:
            nb.add(
                "thought", name, "expects for", hero_name,
                f"For {hero_name}, {name} expects: " + "; ".join(heads) + ".",
                chronic, 7, [name, hero_name], expiration=_plus_30d(chronic),
                filling=[ap],
            )
    return scratch, canonical_world_tree(), nb.nodes


def build_family(
    hero_record: dict,
    hero_name: str,
    *,
    name: Optional[str] = None,
    curr_time: str = CURR_TIME,
) -> tuple[Scratch, dict, list[ConceptNode]]:
    """Authored follower spouse (no cognition), named from the transcript."""
    fam = name or parse_family_name(hero_record.get("transcript", ""), fallback="Marcus")
    scratch = Scratch(
        curr_time=curr_time,
        name=fam,
        first_name=fam.split(" ")[0],
        last_name="",
        age=34,
        innate="supportive, a little nervous, quick to take notes",
        learned=f"here to support {hero_name}",
        currently=f"here supporting {hero_name} at her prenatal visit",
        lifestyle="excited about the pregnancy",
        living_area="Home",
        daily_plan_req=f"Accompany {hero_name} to her prenatal visit and take notes.",
    )
    chronic, recent = _created_times(curr_time)
    nb = NodeBuilder()
    nb.add("thought", fam, "is", f"{hero_name}'s husband",
           f"{fam} is {hero_name}'s husband, here for the first prenatal visit.",
           chronic, 6, [fam, hero_name], expiration=_plus_30d(chronic))
    nb.add("thought", fam, "is", "excited and taking notes",
           f"{fam} is excited and writing everything down for {hero_name}.",
           recent, 5, [fam, "notes"], expiration=_plus_30d(recent))
    return scratch, patient_start_spatial(), nb.nodes
