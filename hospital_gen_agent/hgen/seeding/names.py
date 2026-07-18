"""Name normalization: dataset records -> clean, stable persona names.

Synthea puts digit suffixes in ``encounter.subject.display`` but ``patient.name``
is clean; we normalize defensively per subplan A section 1.
"""
from __future__ import annotations

import re
from typing import Optional


def strip_digits(token: str) -> str:
    """Drop a trailing digit run from a name token ('Clarence5' -> 'Clarence')."""
    return re.sub(r"\d+$", "", token).strip()


def patient_name(patient: dict) -> tuple[str, str, str]:
    """Return (full, first, last) from a FHIR Patient resource, digits stripped."""
    nm = patient["name"][0]
    first = strip_digits(nm.get("given", [""])[0])
    last = strip_digits(nm.get("family", ""))
    full = f"{first} {last}".strip()
    return full, first, last


def patient_prefix(patient: dict) -> Optional[str]:
    """Return the display prefix ('Mrs.') if present, else None."""
    pref = patient["name"][0].get("prefix")
    return pref[0] if pref else None


def parse_clinician_name(transcript: str, fallback: str = "Dr. OB") -> str:
    """Parse the clinician name from the first ``DR:`` turn.

    Looks for 'I am Dr. X' / 'Dr. X'; falls back to a role name.
    """
    for line in transcript.splitlines():
        if line.startswith("DR:"):
            m = re.search(r"Dr\.\s+([A-Z][a-zA-Z'\-]+)", line)
            if m:
                return f"Dr. {m.group(1)}"
            break
    return fallback


def parse_family_name(transcript: str, fallback: str = "Family (spouse)") -> str:
    """Parse the family member's name from the patient's mention.

    Matches 'this is my husband/wife/partner, X'; else falls back.
    """
    m = re.search(
        r"this is my (?:husband|wife|partner|spouse)[,]?\s+([A-Z][a-zA-Z'\-]+)",
        transcript,
    )
    if m:
        return m.group(1)
    return fallback
