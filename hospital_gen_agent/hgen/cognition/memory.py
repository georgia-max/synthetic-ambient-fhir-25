"""The two long-term memory structures for a persona.

``AssociativeMemory`` is the memory stream of ``ConceptNode``s (event / thought /
chat), newest-first, keyword-indexed, with the original ``new_retrieve`` scoring
(recency*0.5 + relevance*3 + importance*2). Relevance falls back to keyword
overlap when embeddings are empty (the vertical-slice default).

``MemoryTree`` is the spatial memory: a nested ``world -> sector -> arena ->
[game_objects]`` dict, grown as the agent perceives new tiles, exposing the same
``get_str_accessible_*`` helpers the planning prompts use.

Both mirror the Stanford ``associative_memory.py`` / ``spatial_memory.py`` logic
and public surface but operate over the ``hgen.contracts`` dataclasses (string
datetimes) instead of the original datetime objects.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Optional

from hgen.config import DATETIME_FMT
from hgen.contracts import (
    ConceptNode,
    PathLike,
    make_concept_node,
    read_json,
    read_associative_memory,
    write_associative_memory,
)


# --------------------------------------------------------------------------- #
# Datetime helpers (contracts store datetimes as DATETIME_FMT strings)         #
# --------------------------------------------------------------------------- #
def parse_dt(s: Optional[str]) -> Optional[datetime.datetime]:
    """Parse a DATETIME_FMT string to a datetime (None passthrough)."""
    if s is None:
        return None
    if isinstance(s, datetime.datetime):
        return s
    return datetime.datetime.strptime(s, DATETIME_FMT)


def fmt_dt(dt: datetime.datetime) -> str:
    """Format a datetime back to a DATETIME_FMT string."""
    return dt.strftime(DATETIME_FMT)


def add_days(created: str, days: int) -> str:
    """Return ``created`` shifted by ``days`` as a DATETIME_FMT string."""
    return fmt_dt(parse_dt(created) + datetime.timedelta(days=days))


_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


# --------------------------------------------------------------------------- #
# AssociativeMemory                                                            #
# --------------------------------------------------------------------------- #
class AssociativeMemory:
    """The memory stream: ConceptNodes indexed newest-first + by keyword."""

    def __init__(self, amem_dir: Optional[PathLike] = None):
        self.id_to_node: dict[str, ConceptNode] = {}
        # Sequences are newest-first (index 0 == most recent), like the original.
        self.seq_event: list[ConceptNode] = []
        self.seq_thought: list[ConceptNode] = []
        self.seq_chat: list[ConceptNode] = []
        # Keyword -> nodes (lowercased keys), also newest-first.
        self.kw_to_event: dict[str, list[ConceptNode]] = {}
        self.kw_to_thought: dict[str, list[ConceptNode]] = {}
        self.kw_to_chat: dict[str, list[ConceptNode]] = {}
        self.kw_strength_event: dict[str, int] = {}
        self.kw_strength_thought: dict[str, int] = {}
        self.embeddings: dict = {}
        if amem_dir is not None:
            self.load(amem_dir)

    # ---- load / save ---------------------------------------------------- #
    def load(self, amem_dir: PathLike) -> None:
        """Load nodes.json / embeddings.json / kw_strength.json into indexes."""
        amem_dir = Path(amem_dir)
        emb_path = amem_dir / "embeddings.json"
        if emb_path.exists():
            self.embeddings = read_json(emb_path)
        kw_path = amem_dir / "kw_strength.json"
        if kw_path.exists():
            kw = read_json(kw_path)
            self.kw_strength_event = dict(kw.get("kw_strength_event") or {})
            self.kw_strength_thought = dict(kw.get("kw_strength_thought") or {})
        # Nodes come back oldest-first; index each (front-insert -> newest-first).
        for node in read_associative_memory(amem_dir):
            self._index(node)

    def save(self, amem_dir: PathLike) -> None:
        """Write nodes/embeddings/kw_strength back to ``amem_dir``."""
        write_associative_memory(
            amem_dir,
            list(self.id_to_node.values()),
            embeddings=self.embeddings,
            kw_strength={
                "kw_strength_event": self.kw_strength_event,
                "kw_strength_thought": self.kw_strength_thought,
            },
        )

    # ---- indexing ------------------------------------------------------- #
    def _index(self, node: ConceptNode) -> None:
        """Insert an already-built node into every index (front == newest)."""
        self.id_to_node[node.node_id] = node
        if node.type == "event":
            seq, kw_to = self.seq_event, self.kw_to_event
        elif node.type == "thought":
            seq, kw_to = self.seq_thought, self.kw_to_thought
        else:
            seq, kw_to = self.seq_chat, self.kw_to_chat
        seq.insert(0, node)
        for kw in {k.lower() for k in node.keywords}:
            kw_to.setdefault(kw, []).insert(0, node)

    def _next_counts(self, node_type: str) -> tuple[int, int]:
        node_count = len(self.id_to_node) + 1
        seq = {"event": self.seq_event, "thought": self.seq_thought,
               "chat": self.seq_chat}[node_type]
        return node_count, len(seq) + 1

    def _bump_kw_strength(self, node_type: str, predicate: str, obj: str,
                          keywords: list[str]) -> None:
        if f"{predicate} {obj}" == "is idle":
            return
        strength = (self.kw_strength_event if node_type == "event"
                    else self.kw_strength_thought)
        for kw in {k.lower() for k in keywords}:
            strength[kw] = strength.get(kw, 0) + 1

    # ---- writers -------------------------------------------------------- #
    def add_event(self, created, s, p, o, description, keywords, poignancy,
                  *, expiration=None, filling=None, embedding_key=None):
        """Add an event node (prepended newest-first) and return it."""
        node_count, type_count = self._next_counts("event")
        node = make_concept_node(
            node_count, type_count, "event", s, p, o, description, created,
            poignancy, list(keywords), depth=0, expiration=expiration,
            embedding_key=embedding_key or description, filling=filling,
            last_accessed=created,
        )
        self._index(node)
        self._bump_kw_strength("event", p, o, list(keywords))
        self.embeddings.setdefault(node.embedding_key, [])
        return node

    def add_thought(self, created, s, p, o, description, keywords, poignancy,
                    *, expiration=None, filling=None, embedding_key=None):
        """Add a thought node; depth = 1 + max(depth of evidence nodes)."""
        node_count, type_count = self._next_counts("thought")
        depth = 1
        if filling:
            depths = [self.id_to_node[i].depth for i in filling
                      if i in self.id_to_node]
            if depths:
                depth += max(depths)
        node = make_concept_node(
            node_count, type_count, "thought", s, p, o, description, created,
            poignancy, list(keywords), depth=depth, expiration=expiration,
            embedding_key=embedding_key or description, filling=filling,
            last_accessed=created,
        )
        self._index(node)
        self._bump_kw_strength("thought", p, o, list(keywords))
        self.embeddings.setdefault(node.embedding_key, [])
        return node

    def add_chat(self, created, s, p, o, description, keywords, poignancy,
                 *, expiration=None, filling=None, embedding_key=None):
        """Add a chat node (holds the utterance rows in ``filling``)."""
        node_count, type_count = self._next_counts("chat")
        node = make_concept_node(
            node_count, type_count, "chat", s, p, o, description, created,
            poignancy, list(keywords), depth=0, expiration=expiration,
            embedding_key=embedding_key or description, filling=filling,
            last_accessed=created,
        )
        self._index(node)
        self.embeddings.setdefault(node.embedding_key, [])
        return node

    # ---- keyword recall ------------------------------------------------- #
    def get_summarized_latest_events(self, retention: int) -> set:
        """Set of (s, p, o) triples for the most recent ``retention`` events."""
        return {n.spo() for n in self.seq_event[:retention]}

    def retrieve_relevant_events(self, s_content, p_content, o_content) -> list:
        """Events keyed by any of the three SPO contents (deduped by node_id)."""
        return self._recall(self.kw_to_event, (s_content, p_content, o_content))

    def retrieve_relevant_thoughts(self, s_content, p_content, o_content) -> list:
        """Thoughts keyed by any of the three SPO contents (deduped by node_id)."""
        return self._recall(self.kw_to_thought, (s_content, p_content, o_content))

    @staticmethod
    def _recall(kw_index: dict, contents) -> list:
        seen: set[str] = set()
        out: list[ConceptNode] = []
        for c in contents:
            if c and c.lower() in kw_index:
                for node in kw_index[c.lower()]:
                    if node.node_id not in seen:
                        seen.add(node.node_id)
                        out.append(node)
        return out

    def get_last_chat(self, target_name: str):
        """Return the most recent chat node keyed by ``target_name``."""
        key = (target_name or "").lower()
        if key in self.kw_to_chat and self.kw_to_chat[key]:
            return self.kw_to_chat[key][0]
        return None

    # ---- scored retrieval ---------------------------------------------- #
    def new_retrieve(self, focal_points, scratch=None, n_count: int = 30) -> dict:
        """Score-and-rank recall for each focal point.

        Combines normalized recency (``recency_decay^age``), importance
        (poignancy), and relevance (cosine on embeddings, else keyword
        overlap) with the original weights ``[0.5, 3, 2]``. Returns
        ``{focal_pt: [ConceptNode, ...]}`` (highest score first).
        """
        decay = getattr(scratch, "recency_decay", 0.995) if scratch else 0.995
        rec_w = getattr(scratch, "recency_w", 1) if scratch else 1
        rel_w = getattr(scratch, "relevance_w", 1) if scratch else 1
        imp_w = getattr(scratch, "importance_w", 1) if scratch else 1
        now = getattr(scratch, "curr_time", None) if scratch else None

        retrieved: dict = {}
        for focal_pt in focal_points:
            nodes = [n for n in (self.seq_event + self.seq_thought)
                     if "idle" not in (n.embedding_key or "").lower()]
            # Chronological (oldest-first) by last_accessed, like the original.
            nodes.sort(key=lambda n: parse_dt(n.last_accessed) or datetime.datetime.min)

            recency = _normalize({n.node_id: decay ** (i + 1)
                                  for i, n in enumerate(nodes)})
            importance = _normalize({n.node_id: n.poignancy for n in nodes})
            relevance = _normalize({n.node_id: self._relevance(focal_pt, n)
                                    for n in nodes})

            gw = [0.5, 3, 2]
            master = {
                n.node_id: (rec_w * recency[n.node_id] * gw[0]
                            + rel_w * relevance[n.node_id] * gw[1]
                            + imp_w * importance[n.node_id] * gw[2])
                for n in nodes
            }
            top = sorted(master.items(), key=lambda kv: kv[1], reverse=True)[:n_count]
            chosen = [self.id_to_node[k] for k, _ in top]
            if now:
                for n in chosen:
                    n.last_accessed = now
            retrieved[focal_pt] = chosen
        return retrieved

    def _relevance(self, focal_pt: str, node: ConceptNode) -> float:
        """Cosine on embeddings if both present, else keyword-overlap fallback."""
        emb = self.embeddings.get(node.embedding_key)
        focal_emb = self.embeddings.get(focal_pt)
        if emb and focal_emb and len(emb) == len(focal_emb):
            return _cos_sim(emb, focal_emb)
        focal = _tokens(focal_pt)
        if not focal:
            return 0.0
        text = _tokens(node.embedding_key + " " + " ".join(node.keywords))
        return len(focal & text) / len(focal)


def _normalize(d: dict) -> dict:
    """Scale dict values into [0, 1]; a flat dict maps to 0.5 everywhere."""
    if not d:
        return d
    lo, hi = min(d.values()), max(d.values())
    rng = hi - lo
    if rng == 0:
        return {k: 0.5 for k in d}
    return {k: (v - lo) / rng for k, v in d.items()}


def _cos_sim(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# --------------------------------------------------------------------------- #
# MemoryTree (spatial memory)                                                  #
# --------------------------------------------------------------------------- #
class MemoryTree:
    """A ``world -> sector -> arena -> [game_objects]`` spatial-memory tree."""

    def __init__(self, path: Optional[PathLike] = None):
        self.tree: dict = {}
        if path is not None and Path(path).exists():
            self.tree = read_json(path)

    def save(self, path: PathLike) -> None:
        """Write the tree to ``path`` (spatial_memory.json)."""
        from hgen.contracts import write_spatial_memory
        write_spatial_memory(path, self.tree)

    # ---- accessible-string helpers used by the planning prompts --------- #
    def get_str_accessible_sectors(self, curr_world: str) -> str:
        """Comma-joined sectors the persona knows inside ``curr_world``."""
        return ", ".join(self.tree.get(curr_world, {}).keys())

    def get_str_accessible_sector_arenas(self, sector: str) -> str:
        """Comma-joined arenas known inside a ``world:sector`` address."""
        curr_world, curr_sector = sector.split(":")
        if not curr_sector:
            return ""
        return ", ".join(self.tree.get(curr_world, {}).get(curr_sector, {}).keys())

    def get_str_accessible_arena_game_objects(self, arena: str) -> str:
        """Comma-joined objects known inside a ``world:sector:arena`` address."""
        curr_world, curr_sector, curr_arena = arena.split(":")
        if not curr_arena:
            return ""
        node = self.tree.get(curr_world, {}).get(curr_sector, {})
        objs = node.get(curr_arena) or node.get(curr_arena.lower()) or []
        return ", ".join(objs)

    def add_tile_to_tree(self, tile: dict) -> None:
        """Grow the tree with a perceived tile's world/sector/arena/object."""
        w, s, a, g = (tile.get("world"), tile.get("sector"),
                      tile.get("arena"), tile.get("game_object"))
        if not w:
            return
        self.tree.setdefault(w, {})
        if s:
            self.tree[w].setdefault(s, {})
        if s and a:
            self.tree[w][s].setdefault(a, [])
        if s and a and g and g not in self.tree[w][s][a]:
            self.tree[w][s][a].append(g)
