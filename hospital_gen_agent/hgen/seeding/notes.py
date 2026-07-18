"""Transcript, clinical-note, and after-visit-summary parsing (subplan A section 5).

The note splits on the three real headings ``**Subjective:**`` / ``**Objective:**``
/ ``**Assessment and Plan:**``. Transcript splits on ``DR:``/``PT:``/``NURSE:``/
``FAMILY:`` speaker markers.
"""
from __future__ import annotations

import re

SPEAKERS = ("DR", "PT", "NURSE", "FAMILY")

# Keywords that mark a patient turn as a real symptom/history account (not banter).
_SYMPTOM_KW = (
    "period", "tired", "fatigue", "queasy", "queasiness", "nausea", "nauseous",
    "sick", "dizzy", "dizziness", "faint", "woozy", "pain", "ache", "sore",
    "bleeding", "spotting", "cramp", "burning", "fever", "infection", "uti",
    "urination", "frequency", "worry", "worried", "scared", "hurt", "symptom",
)
_HIGH_KW = ("scared", "worry", "worried", "bleeding", "pain", "infection", "uti", "fever")
_MILD_KW = ("tired", "fatigue", "queasy", "queasiness", "nausea", "woozy")


def parse_transcript(transcript: str) -> list[tuple[str, str]]:
    """Split a transcript into ordered (speaker, text) turns on speaker markers."""
    turns: list[tuple[str, str]] = []
    pattern = re.compile(r"^(" + "|".join(SPEAKERS) + r"):\s*(.*)$")
    for line in transcript.splitlines():
        line = line.strip()
        if not line:
            continue
        m = pattern.match(line)
        if m:
            turns.append((m.group(1), m.group(2).strip()))
        elif turns:  # continuation of the previous speaker's turn
            spk, txt = turns[-1]
            turns[-1] = (spk, (txt + " " + line).strip())
    return turns


def patient_symptom_turns(turns: list[tuple[str, str]], limit: int = 3) -> list[str]:
    """Return the first ``limit`` PT turns that describe symptoms (skipping banter)."""
    out: list[str] = []
    for spk, txt in turns:
        if spk != "PT":
            continue
        low = txt.lower()
        if any(kw in low for kw in _SYMPTOM_KW):
            out.append(txt)
            if len(out) >= limit:
                break
    return out


def symptom_poignancy(text: str) -> int:
    """Poignancy 4-6 for a symptom account (worry/pain -> 6, mild -> 4, else 5)."""
    low = text.lower()
    if any(kw in low for kw in _HIGH_KW):
        return 6
    if any(kw in low for kw in _MILD_KW):
        return 4
    return 5


def parse_note(note: str) -> dict:
    """Split a SOAP note into {subjective, objective, assessment_and_plan}."""
    sections = {"subjective": "", "objective": "", "assessment_and_plan": ""}
    headings = [
        ("subjective", r"\*\*Subjective:\*\*"),
        ("objective", r"\*\*Objective:\*\*"),
        ("assessment_and_plan", r"\*\*Assessment and Plan:\*\*"),
    ]
    for i, (key, pat) in enumerate(headings):
        start = re.search(pat, note)
        if not start:
            continue
        s = start.end()
        e = len(note)
        for _, npat in headings[i + 1:]:
            nxt = re.search(npat, note[s:])
            if nxt:
                e = s + nxt.start()
                break
        sections[key] = note[s:e].strip()
    return sections


def assessment_headings(assessment_and_plan: str) -> list[str]:
    """Return the ``### <diagnosis>`` headings from the Assessment and Plan section."""
    return [h.strip() for h in re.findall(r"^###\s+(.*)$", assessment_and_plan, re.M)]


def avs_next_steps(after_visit_summary: str) -> list[str]:
    """Return the bulleted 'Next steps' items from an after-visit summary."""
    steps = []
    for line in after_visit_summary.splitlines():
        line = line.strip()
        if line.startswith("•"):
            steps.append(line.lstrip("• ").strip())
    return steps
