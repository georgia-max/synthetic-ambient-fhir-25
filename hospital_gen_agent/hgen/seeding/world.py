"""World spec: visit_type -> department map and the canonical world tree.

Subplan A section 2. The world tree is the master ``spatial_memory`` staff hold;
patients start knowing only the public path (``patient_start_spatial``).
"""
from __future__ import annotations

from hgen.config import WORLD_NAME

# Sim clock (subplan B section 3).
START_DATE = "March 21, 2026"
CURR_TIME = "March 21, 2026, 08:00:00"

# visit_type -> department (sector). Subplan A section 2.
VISIT_TYPE_TO_DEPARTMENT = {
    "General examination of patient (procedure)": "General Medicine",
    "Encounter for check up (procedure)": "General Medicine",
    "Prenatal initial visit (regime/therapy)": "OB / Prenatal Clinic",
    "Hospital admission (procedure)": "Inpatient Ward",
    "Hospital admission for isolation (procedure)": "Isolation Unit",
    "Admission to hospice (procedure)": "Hospice / Palliative",
}


def department_for(visit_type: str) -> str:
    """Map a ``metadata.visit_type`` to its department, defaulting to General Medicine."""
    return VISIT_TYPE_TO_DEPARTMENT.get(visit_type, "General Medicine")


# department (sector) -> the exam-table / bed the department's doctor sits at.
# These colon addresses MUST match the room sector/arena/game_object names in
# hgen.world.grid so pathfinding + routing line up.
DEPARTMENT_EXAM = {
    "General Medicine": f"{WORLD_NAME}:General Medicine:exam room:exam table",
    "OB / Prenatal Clinic": f"{WORLD_NAME}:OB / Prenatal Clinic:exam room:exam table",
    "Inpatient Ward": f"{WORLD_NAME}:Inpatient Ward:ward bay:ward bed",
    "Isolation Unit": f"{WORLD_NAME}:Isolation Unit:isolation room:isolation bed",
    "Hospice / Palliative": f"{WORLD_NAME}:Hospice / Palliative:palliative room:palliative bed",
}

# Shared-station addresses staff hold.
TRIAGE_STATION = f"{WORLD_NAME}:Triage:triage bay 1:vitals station"
RECEPTION_STATION = f"{WORLD_NAME}:Admissions:reception:reception desk"


def exam_address_for(visit_type: str) -> str:
    """Return the department exam/bed address a patient with ``visit_type`` targets."""
    return DEPARTMENT_EXAM[department_for(visit_type)]


def canonical_world_tree() -> dict:
    """The full hospital spatial tree (world -> sector -> arena -> [game_objects]).

    Shared sectors plus one arena per clinical department. This is the master
    spatial memory every staff persona holds.
    """
    return {
        WORLD_NAME: {
            "Admissions": {
                "reception": ["reception desk", "check-in kiosk", "waiting chairs"],
            },
            "Waiting Room": {
                "waiting area": ["waiting chairs"],
            },
            "Triage": {
                "triage bay 1": ["vitals station", "exam stool", "computer"],
                "triage bay 2": ["vitals station", "exam stool", "computer"],
            },
            "General Medicine": {
                "exam room": ["exam table", "computer", "sink", "blood-pressure cuff"],
                "nurse station": ["computer", "medication cart"],
            },
            "OB / Prenatal Clinic": {
                "exam room": ["exam table", "doppler", "computer", "ultrasound machine"],
                "ultrasound room": ["ultrasound machine", "exam table"],
            },
            "Inpatient Ward": {
                "ward bay": ["ward bed", "monitor", "nurse station"],
            },
            "Isolation Unit": {
                "isolation room": ["isolation bed", "PPE station", "monitor"],
            },
            "Hospice / Palliative": {
                "palliative room": ["palliative bed", "family chairs", "comfort cart"],
            },
            "Diagnostics / Lab": {
                "lab": ["blood draw chair", "analyzer", "imaging table", "ultrasound"],
            },
            "Pharmacy": {
                "pharmacy": ["pharmacy counter", "medication shelves"],
            },
            "Discharge": {
                "discharge desk": ["exit"],
            },
        }
    }


def patient_start_spatial() -> dict:
    """What a patient knows at spawn: the public path only (subplan A section 3d)."""
    return {
        WORLD_NAME: {
            "Admissions": {"reception": ["reception desk", "check-in kiosk"]},
            "Waiting Room": {"waiting area": ["waiting chairs"]},
            "Triage": {"triage bay 1": ["vitals station"]},
        }
    }
