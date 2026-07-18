"""Shared data schemas + JSON IO contracts.

These are the artifacts every component agrees on: the ``ConceptNode`` (a single
associative-memory record), the ``Scratch`` (short-term identity + current
action), and the on-disk JSON layout used by seeding, cognition, and the
director/renderer. The shapes mirror the original Stanford generative_agents
bootstrap layout so the ported backend loads them unchanged; only the values and
a few defaults (per the plans) differ.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional, Union

from hgen.config import DATETIME_FMT, MAZE_NAME  # noqa: F401  (re-exported convenience)

PathLike = Union[str, Path]


# --------------------------------------------------------------------------- #
# Low-level JSON helpers                                                       #
# --------------------------------------------------------------------------- #
def read_json(path: PathLike) -> Any:
    """Load and return the JSON object at ``path``."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: PathLike, obj: Any, indent: int = 2) -> None:
    """Write ``obj`` as JSON to ``path``, creating parent dirs as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent)


# --------------------------------------------------------------------------- #
# ConceptNode — one associative-memory record                                 #
# --------------------------------------------------------------------------- #
@dataclass
class ConceptNode:
    """A single memory-stream node (event / thought / chat).

    An SPO triple + natural-language description + retrieval metadata, matching
    the original ``ConceptNode``. ``created``/``expiration``/``last_accessed``
    are stored as strings in ``DATETIME_FMT``.
    """

    node_id: str
    node_count: int
    type_count: int
    type: str  # "event" | "thought" | "chat"
    depth: int
    created: str
    expiration: Optional[str]
    last_accessed: str
    subject: str
    predicate: str
    object: str
    description: str
    embedding_key: str
    poignancy: int  # 1-10
    keywords: list[str] = field(default_factory=list)
    filling: Optional[list] = None

    def spo(self) -> tuple[str, str, str]:
        """Return the (subject, predicate, object) triple."""
        return (self.subject, self.predicate, self.object)

    def to_dict(self) -> dict:
        """Serialize to the per-node dict stored under a node_id key in nodes.json."""
        return {
            "node_count": self.node_count,
            "type_count": self.type_count,
            "type": self.type,
            "depth": self.depth,
            "created": self.created,
            "expiration": self.expiration,
            "last_accessed": self.last_accessed,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "description": self.description,
            "embedding_key": self.embedding_key,
            "poignancy": self.poignancy,
            "keywords": list(self.keywords),
            "filling": self.filling,
        }

    @classmethod
    def from_dict(cls, node_id: str, d: dict) -> "ConceptNode":
        """Rebuild a ConceptNode from its node_id and per-node dict."""
        created = d["created"]
        return cls(
            node_id=node_id,
            node_count=d["node_count"],
            type_count=d["type_count"],
            type=d["type"],
            depth=d["depth"],
            created=created,
            expiration=d.get("expiration"),
            last_accessed=d.get("last_accessed", created),
            subject=d["subject"],
            predicate=d["predicate"],
            object=d["object"],
            description=d["description"],
            embedding_key=d.get("embedding_key", d["description"]),
            poignancy=d["poignancy"],
            keywords=list(d.get("keywords", [])),
            filling=d.get("filling"),
        )


def make_concept_node(
    node_count: int,
    type_count: int,
    node_type: str,
    subject: str,
    predicate: str,
    object: str,
    description: str,
    created: str,
    poignancy: int,
    keywords: Optional[list[str]] = None,
    *,
    depth: Optional[int] = None,
    expiration: Optional[str] = None,
    embedding_key: Optional[str] = None,
    filling: Optional[list] = None,
    last_accessed: Optional[str] = None,
) -> ConceptNode:
    """Convenience factory. Assigns ``node_id`` from ``node_count`` and applies
    original defaults (depth 0 for event/chat, 1 for thought; embedding_key
    defaults to the description; last_accessed defaults to created)."""
    if depth is None:
        depth = 1 if node_type == "thought" else 0
    return ConceptNode(
        node_id=f"node_{node_count}",
        node_count=node_count,
        type_count=type_count,
        type=node_type,
        depth=depth,
        created=created,
        expiration=expiration,
        last_accessed=last_accessed or created,
        subject=subject,
        predicate=predicate,
        object=object,
        description=description,
        embedding_key=embedding_key or description,
        poignancy=poignancy,
        keywords=list(keywords or []),
        filling=filling,
    )


# --------------------------------------------------------------------------- #
# Scratch — short-term identity + current action                              #
# --------------------------------------------------------------------------- #
@dataclass
class Scratch:
    """Per-persona short-term memory / identity.

    Mirrors the original ``Scratch`` fields and defaults (with the plan's
    overrides: vision_r/att_bandwidth/retention = 8, recency_decay = 0.995).
    Datetimes are held as strings in ``DATETIME_FMT``.
    """

    # Persona hyperparameters.
    vision_r: int = 8
    att_bandwidth: int = 8
    retention: int = 8

    # World information.
    curr_time: Optional[str] = None
    curr_tile: Optional[list] = None
    daily_plan_req: Optional[str] = None
    # Care-pathway target: the department exam/bed (patients) or on-shift station
    # (staff) this persona is routed to. Set at seeding; read by _care_pathway.
    dept_address: Optional[str] = None

    # Core identity.
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    age: Optional[int] = None
    innate: Optional[str] = None
    learned: Optional[str] = None
    currently: Optional[str] = None
    lifestyle: Optional[str] = None
    living_area: Optional[str] = None

    # Retrieval / reflection weights.
    recency_w: int = 1
    relevance_w: int = 1
    importance_w: int = 1
    recency_decay: float = 0.995
    importance_trigger_max: int = 150
    importance_trigger_curr: int = 150
    importance_ele_n: int = 0

    # Planning.
    daily_req: list = field(default_factory=list)
    f_daily_schedule: list = field(default_factory=list)
    f_daily_schedule_hourly_org: list = field(default_factory=list)

    # Current action.
    act_address: Optional[str] = None
    act_start_time: Optional[str] = None
    act_duration: Optional[int] = None
    act_description: Optional[str] = None
    act_pronunciatio: Optional[str] = None
    act_event: list = field(default_factory=lambda: [None, None, None])
    act_obj_description: Optional[str] = None
    act_obj_pronunciatio: Optional[str] = None
    act_obj_event: list = field(default_factory=lambda: [None, None, None])

    # Chat state.
    chatting_with: Optional[str] = None
    chat: Optional[list] = None  # [[speaker, utterance], ...] | None
    chatting_with_buffer: dict = field(default_factory=dict)
    chatting_end_time: Optional[str] = None

    # Pathfinding.
    act_path_set: bool = False
    planned_path: list = field(default_factory=list)

    def __post_init__(self) -> None:
        # act_event defaults to [name, None, None] like the original.
        if self.act_event == [None, None, None] and self.name is not None:
            self.act_event = [self.name, None, None]

    def to_dict(self) -> dict:
        """Serialize to the scratch.json dict."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: dict) -> "Scratch":
        """Build a Scratch from a scratch.json dict (ignores unknown keys)."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    def save(self, path: PathLike) -> None:
        """Write this scratch to ``path`` (scratch.json)."""
        write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: PathLike) -> "Scratch":
        """Load a Scratch from ``path`` (scratch.json)."""
        return cls.from_dict(read_json(path))


# --------------------------------------------------------------------------- #
# meta.json                                                                    #
# --------------------------------------------------------------------------- #
def make_meta(
    start_date: str,
    curr_time: str,
    persona_names: list[str],
    *,
    fork_sim_code: str = "base_hospital",
    sec_per_step: int = 30,
    maze_name: str = MAZE_NAME,
    step: int = 0,
) -> dict:
    """Build a meta.json dict with the standard key set."""
    return {
        "fork_sim_code": fork_sim_code,
        "start_date": start_date,
        "curr_time": curr_time,
        "sec_per_step": sec_per_step,
        "maze_name": maze_name,
        "persona_names": list(persona_names),
        "step": step,
    }


def write_meta(path: PathLike, meta: dict) -> None:
    """Write a meta.json dict to ``path``."""
    write_json(path, meta)


def read_meta(path: PathLike) -> dict:
    """Read a meta.json dict from ``path``."""
    return read_json(path)


# --------------------------------------------------------------------------- #
# environment/<step>.json  and  movement/<step>.json                          #
# --------------------------------------------------------------------------- #
def make_environment(tiles: dict[str, tuple[int, int]], maze_name: str = MAZE_NAME) -> dict:
    """Build an environment step dict: {name: {"maze", "x", "y"}}."""
    return {
        name: {"maze": maze_name, "x": int(xy[0]), "y": int(xy[1])}
        for name, xy in tiles.items()
    }


def write_environment(env_dir: PathLike, step: int, env: dict) -> None:
    """Write ``env`` to ``env_dir/<step>.json``."""
    write_json(Path(env_dir) / f"{step}.json", env)


def read_environment(env_dir: PathLike, step: int) -> dict:
    """Read ``env_dir/<step>.json``."""
    return read_json(Path(env_dir) / f"{step}.json")


def make_movement(personas: dict[str, dict], curr_time: str) -> dict:
    """Build a movement step dict.

    ``personas`` maps name -> {"movement":[x,y], "pronunciatio":str,
    "description":str, "chat": None | [[speaker, line], ...]}.
    """
    return {"persona": personas, "meta": {"curr_time": curr_time}}


def make_movement_entry(
    movement: list[int],
    pronunciatio: str,
    description: str,
    chat: Optional[list] = None,
) -> dict:
    """Build one persona's movement entry."""
    return {
        "movement": [int(movement[0]), int(movement[1])],
        "pronunciatio": pronunciatio,
        "description": description,
        "chat": chat,
    }


def write_movement(mvmt_dir: PathLike, step: int, movement: dict) -> None:
    """Write ``movement`` to ``mvmt_dir/<step>.json``."""
    write_json(Path(mvmt_dir) / f"{step}.json", movement)


def read_movement(mvmt_dir: PathLike, step: int) -> dict:
    """Read ``mvmt_dir/<step>.json``."""
    return read_json(Path(mvmt_dir) / f"{step}.json")


# --------------------------------------------------------------------------- #
# spatial_memory.json                                                         #
# --------------------------------------------------------------------------- #
def write_spatial_memory(path: PathLike, tree: dict) -> None:
    """Write a spatial-memory tree {world: {sector: {arena: [objects]}}}."""
    write_json(path, tree)


def read_spatial_memory(path: PathLike) -> dict:
    """Read a spatial-memory tree."""
    return read_json(path)


# --------------------------------------------------------------------------- #
# associative_memory/  (nodes.json, embeddings.json, kw_strength.json)         #
# --------------------------------------------------------------------------- #
def nodes_to_dict(nodes: list[ConceptNode]) -> dict:
    """Serialize a list of ConceptNodes to the nodes.json dict, newest-first.

    Nodes are keyed by ``node_id`` and ordered by descending ``node_count`` so
    the newest node appears first, matching the original storage order.
    """
    ordered = sorted(nodes, key=lambda n: n.node_count, reverse=True)
    return {n.node_id: n.to_dict() for n in ordered}


def nodes_from_dict(d: dict) -> list[ConceptNode]:
    """Rebuild ConceptNodes from a nodes.json dict (returns oldest-first)."""
    nodes = [ConceptNode.from_dict(nid, nd) for nid, nd in d.items()]
    nodes.sort(key=lambda n: n.node_count)
    return nodes


def empty_kw_strength() -> dict:
    """Return the empty keyword-strength structure."""
    return {"kw_strength_event": {}, "kw_strength_thought": {}}


def write_associative_memory(
    amem_dir: PathLike,
    nodes: list[ConceptNode],
    *,
    embeddings: Optional[dict] = None,
    kw_strength: Optional[dict] = None,
) -> None:
    """Write nodes.json, embeddings.json, and kw_strength.json to ``amem_dir``.

    ``embeddings`` defaults to ``{}`` (keyword-only retrieval) and
    ``kw_strength`` to the empty event/thought structure.
    """
    amem_dir = Path(amem_dir)
    amem_dir.mkdir(parents=True, exist_ok=True)
    write_json(amem_dir / "nodes.json", nodes_to_dict(nodes))
    write_json(amem_dir / "embeddings.json", embeddings or {})
    write_json(amem_dir / "kw_strength.json", kw_strength or empty_kw_strength())


def read_associative_memory(amem_dir: PathLike) -> list[ConceptNode]:
    """Read nodes.json from ``amem_dir`` and return ConceptNodes (oldest-first)."""
    return nodes_from_dict(read_json(Path(amem_dir) / "nodes.json"))


# --------------------------------------------------------------------------- #
# Full persona bootstrap dir                                                   #
# --------------------------------------------------------------------------- #
def persona_bootstrap_dir(personas_dir: PathLike, name: str) -> Path:
    """Return ``<personas_dir>/<name>/bootstrap_memory``."""
    return Path(personas_dir) / name / "bootstrap_memory"


def write_persona_bootstrap(
    personas_dir: PathLike,
    scratch: Scratch,
    spatial_tree: dict,
    nodes: list[ConceptNode],
    *,
    embeddings: Optional[dict] = None,
    kw_strength: Optional[dict] = None,
) -> Path:
    """Write a persona's full bootstrap_memory dir and return its path.

    Layout (mirrors the original)::

        <personas_dir>/<name>/bootstrap_memory/
        ├── scratch.json
        ├── spatial_memory.json
        └── associative_memory/{nodes.json, embeddings.json, kw_strength.json}

    ``name`` is taken from ``scratch.name``.
    """
    if not scratch.name:
        raise ValueError("scratch.name must be set to write a persona bootstrap dir")
    boot = persona_bootstrap_dir(personas_dir, scratch.name)
    boot.mkdir(parents=True, exist_ok=True)
    scratch.save(boot / "scratch.json")
    write_spatial_memory(boot / "spatial_memory.json", spatial_tree)
    write_associative_memory(
        boot / "associative_memory",
        nodes,
        embeddings=embeddings,
        kw_strength=kw_strength,
    )
    return boot
