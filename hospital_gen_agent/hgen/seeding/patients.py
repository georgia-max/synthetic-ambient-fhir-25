"""Patient persona seeding: one record -> Scratch + associative nodes + spatial tree.

Subplan A section 3. Only pre-visit knowledge is seeded; this-visit Condition,
Observation values, and note Assessment/Plan are withheld (they are visit
outcomes, delivered by the consult and post-consult reflection).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

from hgen.config import DATETIME_FMT
from hgen.contracts import ConceptNode, Scratch, make_concept_node
from hgen.seeding.names import patient_name
from hgen.seeding.notes import (
    parse_transcript,
    patient_symptom_turns,
    symptom_poignancy,
)
from hgen.seeding.world import CURR_TIME, exam_address_for, patient_start_spatial

# Poignancy rubric (subplan A section 3c): first matching level wins, high -> low.
POIGNANCY_RUBRIC: list[tuple[int, tuple[str, ...]]] = [
    (9, ("cancer", "sepsis", "end-stage", "end stage", "hospice", "pneumonia",
         "hypoxemia", "terminal", "metastatic")),
    (8, ("normal pregnancy", "pregnan", "covid", "myocardial", "stroke")),
    (7, ("diabetes", "hypertension", "hyperlipidemia", "metabolic syndrome",
         "chronic kidney", "ckd")),
    (6, ("urinary tract infection", "uti", "migraine", "back pain", "osteoarthritis",
         "anemia", "prediabetes", "scoliosis", "chronic pain", "chronic low back",
         "chronic neck")),
    (5, ("stress", "social isolation", "depression", "anxiety", "intimate partner",
         "abuse", "transport", "lack of access", "isolation")),
    (3, ("medication review", "risk activity", "review due")),
    (2, ("higher education", "high school", "educated")),
]

MAX_SYMPTOM_CHARS = 150


def poignancy_for(label: str) -> int:
    """Deterministic 1-10 poignancy for a condition/finding label (default 4)."""
    low = label.lower()
    for level, kws in POIGNANCY_RUBRIC:
        if any(k in low for k in kws):
            return level
    return 4


def short_label(label: str) -> str:
    """Strip a trailing '(disorder)'/'(finding)' qualifier and lowercase."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", label).strip().lower()


def age_at(birth_date: str, on_date: str) -> int:
    """Whole-year age from ISO birthDate and encounter date."""
    b = date.fromisoformat(birth_date[:10])
    d = date.fromisoformat(on_date[:10])
    return d.year - b.year - ((d.month, d.day) < (b.month, b.day))


def visit_reason(visit_title: str) -> str:
    """Reason for visit: the text after the em dash, lowercased first letter."""
    r = visit_title.split("—", 1)[1].strip() if "—" in visit_title else visit_title.strip()
    return (r[0].lower() + r[1:]) if r else r


def _trim(text: str, n: int = MAX_SYMPTOM_CHARS) -> str:
    """Trim a quote to ~n chars on a word boundary, with an ellipsis."""
    text = text.strip()
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(",.;: ") + "…"


class NodeBuilder:
    """Accumulates ConceptNodes with running node_count / per-type type_count."""

    def __init__(self) -> None:
        self.nodes: list[ConceptNode] = []
        self._n = 0
        self._type_count: dict[str, int] = {}

    def add(
        self,
        node_type: str,
        subject: str,
        predicate: str,
        obj: str,
        description: str,
        created: str,
        poignancy: int,
        keywords: list[str],
        *,
        expiration: Optional[str] = None,
        embedding_key: Optional[str] = None,
        filling: Optional[list] = None,
    ) -> ConceptNode:
        """Append one node in insertion (chronological) order."""
        self._n += 1
        self._type_count[node_type] = self._type_count.get(node_type, 0) + 1
        node = make_concept_node(
            self._n,
            self._type_count[node_type],
            node_type,
            subject,
            predicate,
            obj,
            description,
            created,
            poignancy,
            keywords,
            expiration=expiration,
            embedding_key=embedding_key,
            filling=filling,
        )
        self.nodes.append(node)
        return node


def _created_times(curr_time: str) -> tuple[str, str]:
    """Return (chronic_created, recent_created) backdated from sim start."""
    base = datetime.strptime(curr_time, DATETIME_FMT)
    chronic = (base - timedelta(days=365)).strftime(DATETIME_FMT)
    recent = (base - timedelta(days=1)).strftime(DATETIME_FMT)
    return chronic, recent


def _plus_30d(created: str) -> str:
    """Thought expiration = created + 30 days (matches the original)."""
    return (datetime.strptime(created, DATETIME_FMT) + timedelta(days=30)).strftime(DATETIME_FMT)


def build_patient(
    record: dict,
    *,
    name: Optional[str] = None,
    curr_time: str = CURR_TIME,
) -> tuple[Scratch, dict, list[ConceptNode]]:
    """Build (scratch, spatial_tree, nodes) for one patient record.

    ``name`` overrides the persona key (used for background 'Patient A'/'Patient B').
    """
    patient = record["patient_context"]["patient"]
    meta = record["metadata"]
    longit = record["patient_context"]["longitudinal_summary"]
    rr = record["encounter_fhir"]["related_resources"]

    full, first, last = patient_name(patient)
    if name:
        full = name
        parts = name.split(" ", 1)
        first, last = parts[0], (parts[1] if len(parts) > 1 else "")

    age = age_at(patient["birthDate"], meta["date"])
    reason = visit_reason(meta["visit_title"])

    # Classify longitudinal condition labels.
    labels = longit.get("condition_labels", [])
    clinical = [l for l in labels if poignancy_for(l) >= 6]
    sdoh = [l for l in labels if poignancy_for(l) == 5]
    # This-visit conditions are current, not chart history -> excluded from `learned`.
    visit_cond_shorts = {
        short_label((c.get("code") or {}).get("text", "")) for c in rr.get("Condition", [])
    }
    background = [short_label(l) for l in clinical if short_label(l) not in visit_cond_shorts]

    learned = (
        "has a history of " + ", ".join(background) if background
        else "no significant past medical history"
    )
    lifestyle = (
        "dealing with " + ", ".join(short_label(l) for l in sdoh) if sdoh
        else "generally settled home and work life"
    )

    scratch = Scratch(
        curr_time=curr_time,
        name=full,
        first_name=first,
        last_name=last,
        age=age,
        innate="warm, a little anxious",
        learned=learned,
        currently=f"here for {reason}",
        lifestyle=lifestyle,
        living_area="Home",
        daily_plan_req=(
            "Go to the hospital: check in at Admissions, wait to be called, get "
            f"triaged, see the doctor about {reason}, get a plan, then go home."
        ),
        # Route this patient to their real department (from visit_type).
        dept_address=exam_address_for(meta["visit_type"]),
    )

    # Associative memory (oldest -> newest).
    nb = NodeBuilder()
    chronic_created, recent_created = _created_times(curr_time)

    # 1. Chronic/background conditions the patient already knows about.
    for label in clinical:
        sl = short_label(label)
        nb.add(
            "thought", full, "has", sl, f"{full} has {sl}.",
            chronic_created, poignancy_for(label), [full, sl],
            expiration=_plus_30d(chronic_created),
        )

    # 2. Chief complaint (why they are here today).
    nb.add(
        "thought", full, "is here for", reason, f"{full} is here for {reason}.",
        recent_created, 6, [full, reason],
        expiration=_plus_30d(recent_created),
    )

    # 3. Symptom account from the patient's own transcript turns.
    for quote in patient_symptom_turns(parse_transcript(record.get("transcript", ""))):
        q = _trim(quote)
        nb.add(
            "event", full, "reports", "symptoms", q,
            recent_created, symptom_poignancy(quote), [full, "symptoms"],
            embedding_key=q,
        )

    return scratch, patient_start_spatial(), nb.nodes
