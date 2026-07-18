"""The five cognitive-module functions of the ``Persona.move`` chain.

``perceive -> retrieve -> plan -> reflect -> execute`` keep the original data
flow and return shapes (``execute`` returns ``(next_tile, pronunciatio,
description)``). Planning follows the deterministic hospital CARE PATHWAY
(arrive -> reception -> wait -> triage -> department -> consult -> receive plan
-> discharge -> exit) instead of the original hourly schedule, while still
routing action-location resolution, pronunciatio, event triples, reactions, and
reflection through ``hgen.llm.prompts`` so it stays LLM-driven and runs fully in
canned mode (no API key).
"""
from __future__ import annotations

import math

from hgen.config import WORLD_NAME
from hgen.cognition.memory import add_days, parse_dt
from hgen.llm.prompts import (
    decide_to_talk,
    gen_action_game_object,
    gen_daily_plan,
    gen_event_triple,
    gen_pronunciatio,
    memo_on_convo,
    reflect_insights,
)

# Canonical vertical-slice addresses (match SUBPLAN_B section 2 and the maze).
W = WORLD_NAME
ADMISSIONS = f"{W}:Admissions:reception:reception desk"
WAITING = f"{W}:Waiting Room:waiting area:waiting chairs"
TRIAGE = f"{W}:Triage:triage bay 1:vitals station"
OB_EXAM = f"{W}:OB / Prenatal Clinic:exam room:exam table"
DISCHARGE = f"{W}:Discharge:discharge desk:exit"
HOME = "<spawn_loc>Home"


# --------------------------------------------------------------------------- #
# PERCEIVE                                                                     #
# --------------------------------------------------------------------------- #
def _event_poignancy(description: str) -> int:
    """Cheap deterministic poignancy for a perceived environment event."""
    return 1 if "idle" in description.lower() else 2


def perceive(persona, maze):
    """Grow spatial memory + add new nearby-arena events to memory.

    Returns the list of newly created event ConceptNodes (same as the original).
    """
    scr = persona.scratch
    curr_tile = tuple(scr.curr_tile)
    nearby = maze.get_nearby_tiles(curr_tile, scr.vision_r)

    # PERCEIVE SPACE — grow the spatial-memory tree from every nearby tile.
    for t in nearby:
        persona.s_mem.add_tile_to_tree(maze.access_tile(t))

    # PERCEIVE EVENTS — only within the persona's current arena.
    curr_arena = maze.get_tile_path(curr_tile, "arena")
    seen = set()
    ranked = []
    for t in nearby:
        td = maze.access_tile(t)
        if td["events"] and maze.get_tile_path(t, "arena") == curr_arena:
            dist = math.dist([t[0], t[1]], [curr_tile[0], curr_tile[1]])
            for ev in td["events"]:
                if ev not in seen:
                    seen.add(ev)
                    ranked.append((dist, ev))
    ranked.sort(key=lambda x: x[0])
    perceived = [ev for _, ev in ranked[:scr.att_bandwidth]]

    ret_events = []
    for p_event in perceived:
        s, p, o, desc = p_event
        if not p:
            p, o, desc = "is", "idle", "idle"
        desc = f"{s.split(':')[-1]} is {desc}"
        spo = (s, p, o)
        if spo in persona.a_mem.get_summarized_latest_events(scr.retention):
            continue
        sub = s.split(":")[-1] if ":" in s else s
        obj = o.split(":")[-1] if ":" in o else o
        keywords = [sub, obj]
        poig = _event_poignancy(desc)
        node = persona.a_mem.add_event(scr.curr_time, s, p, o, desc,
                                       keywords, poig)
        ret_events.append(node)
        scr.importance_trigger_curr -= poig
        scr.importance_ele_n += 1
    return ret_events


# --------------------------------------------------------------------------- #
# RETRIEVE                                                                     #
# --------------------------------------------------------------------------- #
def retrieve(persona, perceived):
    """Keyword recall of related events/thoughts for each perceived event."""
    retrieved = {}
    for event in perceived:
        retrieved[event.description] = {
            "curr_event": event,
            "events": list(persona.a_mem.retrieve_relevant_events(
                event.subject, event.predicate, event.object)),
            "thoughts": list(persona.a_mem.retrieve_relevant_thoughts(
                event.subject, event.predicate, event.object)),
        }
    return retrieved


# --------------------------------------------------------------------------- #
# PLAN                                                                         #
# --------------------------------------------------------------------------- #
def _is_patient(persona) -> bool:
    return (persona.scratch.living_area or "") == "Home"


def _care_pathway(persona) -> list[dict]:
    """Build the ordered pathway steps for this persona (patient vs staff).

    Patients are routed to THEIR department's exam/bed via ``scratch.dept_address``
    (set at seeding from ``visit_type``); it falls back to OB_EXAM so the hero
    slice keeps working when a persona predates the dept_address field.
    """
    scr = persona.scratch
    if _is_patient(persona):
        reason = scr.currently or "the visit"
        dept = scr.dept_address or OB_EXAM
        return [
            {"desc": "walking in to check in", "address": ADMISSIONS, "duration": 2},
            {"desc": "checking in at reception", "address": ADMISSIONS, "duration": 2},
            {"desc": "waiting to be seen", "address": WAITING, "duration": 3},
            {"desc": "getting triaged (vitals and history)", "address": TRIAGE, "duration": 3},
            {"desc": f"consulting with the doctor about {reason}", "address": dept, "duration": 4},
            {"desc": "receiving the care plan", "address": dept, "duration": 2},
            {"desc": "getting discharge instructions", "address": DISCHARGE, "duration": 2},
            {"desc": "leaving the hospital", "address": HOME, "duration": 2},
        ]
    # Staff hold a single-stage "on shift" loop at their station (dept_address).
    if scr.dept_address:
        return [{"desc": f"on shift in {scr.living_area}",
                 "address": scr.dept_address, "duration": 999}]
    if "nurse" in (scr.name or "").lower() or "triage" in (scr.learned or "").lower():
        return [{"desc": "on shift taking vitals in triage", "address": TRIAGE, "duration": 999}]
    if "reception" in (scr.currently or "").lower() or "clerk" in (scr.learned or "").lower():
        return [{"desc": "on shift at reception", "address": ADMISSIONS, "duration": 999}]
    return [{"desc": f"on shift in {scr.living_area}", "address": OB_EXAM, "duration": 999}]


def _long_term_planning(persona):
    """First-day / new-day planning: build the care pathway (daily_req)."""
    persona.stage = 0
    persona.scratch.daily_req = _care_pathway(persona)
    # Exercise the daily-plan prompt (its steps ground the pathway narrative).
    gen_daily_plan(persona)
    persona.scratch.act_address = None  # force _set_action this step


def _at_target(persona, maze) -> bool:
    """True once the persona is standing on its action tile with no path left."""
    addr = persona.scratch.act_address
    if not addr:
        return False
    tiles = maze.address_tiles.get(addr, set())
    return tuple(persona.scratch.curr_tile) in tiles and not persona.scratch.planned_path


def _resolve_address(persona, maze, addr, desc) -> str:
    """Refine the game_object via the LLM when spatial memory knows the arena.

    Keeps the canonical colon address for routing; the intended object is
    offered first so canned mode stays correct while still exercising the
    action-location resolution prompt.
    """
    parts = addr.split(":")
    if len(parts) < 4:
        return addr
    world, sector, arena, obj = parts[0], parts[1], parts[2], parts[3]
    objs = persona.s_mem.tree.get(world, {}).get(sector, {}).get(arena)
    if not objs:
        return addr
    opts = [obj] + [o for o in objs if o != obj] if obj in objs else list(objs)
    chosen = gen_action_game_object(persona, opts)
    return f"{world}:{sector}:{arena}:{chosen}"


def _set_action(persona, maze, stage: int):
    """Populate the current action (address, desc, emoji, event triple)."""
    scr = persona.scratch
    pathway = scr.daily_req
    step = pathway[min(stage, len(pathway) - 1)]
    desc = step["desc"]
    addr = _resolve_address(persona, maze, step["address"], desc)

    scr.act_address = addr
    scr.act_description = desc
    scr.act_pronunciatio = gen_pronunciatio(desc)
    scr.act_event = list(gen_event_triple(persona, desc))
    scr.act_start_time = scr.curr_time
    scr.act_duration = step.get("duration", 3)
    scr.act_path_set = False
    scr.planned_path = []


def _determine_action(persona, maze):
    """Advance the pathway when the current action's target is reached."""
    scr = persona.scratch
    if scr.act_address is None:
        _set_action(persona, maze, getattr(persona, "stage", 0))
        return
    if _at_target(persona, maze):
        persona.stage = getattr(persona, "stage", 0) + 1
        if persona.stage < len(scr.daily_req):
            _set_action(persona, maze, persona.stage)
        else:  # stay at the final step (already standing there)
            persona.stage = len(scr.daily_req) - 1


def _maybe_react(persona, maze, personas, retrieved):
    """Light reaction: open a conversation with a co-located, idle persona."""
    scr = persona.scratch
    if scr.chatting_with or not retrieved:
        return
    my_arena = maze.get_tile_path(tuple(scr.curr_tile), "arena")
    for name, other in personas.items():
        if name == scr.name or other.scratch.curr_tile is None:
            continue
        if maze.get_tile_path(tuple(other.scratch.curr_tile), "arena") != my_arena:
            continue
        if scr.chatting_with_buffer.get(name, 0) > 0:
            continue
        if decide_to_talk(persona, other, f"both in {my_arena}"):
            scr.chatting_with = name
            scr.chat = [[scr.name, "Hello."], [name, "Hello."]]
            scr.act_event = [scr.name, "chat with", name]
            scr.chatting_with_buffer[name] = 4
            return


def plan(persona, maze, personas, new_day, retrieved):
    """Run long-term planning, action selection, and reactions.

    Returns the target action address (``persona.scratch.act_address``).
    """
    # First-day planning also fires when the pathway has not been built yet
    # (seeded scratch already carries curr_time, so new_day can be False here).
    if new_day or not persona.scratch.daily_req:
        _long_term_planning(persona)
    _determine_action(persona, maze)
    _maybe_react(persona, maze, personas, retrieved)

    # Chat-state cleanup (mirrors the original): drop stale chat if not chatting.
    scr = persona.scratch
    if scr.act_event[1] != "chat with":
        scr.chatting_with = None
        scr.chat = None
        scr.chatting_end_time = None
    for pname in list(scr.chatting_with_buffer.keys()):
        if pname != scr.chatting_with and scr.chatting_with_buffer[pname] > 0:
            scr.chatting_with_buffer[pname] -= 1
    return scr.act_address


# --------------------------------------------------------------------------- #
# REFLECT                                                                      #
# --------------------------------------------------------------------------- #
def _reflection_trigger(persona) -> bool:
    return (persona.scratch.importance_trigger_curr <= 0
            and bool(persona.a_mem.seq_event + persona.a_mem.seq_thought))


def _reset_reflection_counter(persona):
    persona.scratch.importance_trigger_curr = persona.scratch.importance_trigger_max
    persona.scratch.importance_ele_n = 0


def run_reflect(persona):
    """Synthesize higher-level thought nodes from recent memories (Opus)."""
    n = max(persona.scratch.importance_ele_n, 1)
    recent = [node for node in (persona.a_mem.seq_event + persona.a_mem.seq_thought)
              if "idle" not in (node.embedding_key or "").lower()]
    recent.sort(key=lambda nd: parse_dt(nd.last_accessed))
    statements = [nd.embedding_key for nd in recent[-n:]]
    if not statements:
        return
    for thought, idxs in reflect_insights(persona, statements):
        evidence = [recent[-n:][i].node_id for i in idxs
                    if 0 <= i < len(statements)]
        _add_thought(persona, thought, evidence)


def reflect_on_convo(persona, convo_text: str):
    """Post-conversation memo -> a thought node (grounds the consult takeaway)."""
    memo = memo_on_convo(persona, convo_text)
    memo = f"{persona.scratch.name} {memo}"
    last = persona.a_mem.get_last_chat(persona.scratch.chatting_with)
    evidence = [last.node_id] if last else None
    return _add_thought(persona, memo, evidence)


def _add_thought(persona, thought, evidence):
    scr = persona.scratch
    s, p, o = gen_event_triple(persona, thought)
    node = persona.a_mem.add_thought(
        scr.curr_time, s, p, o, thought, [s, p, o], 5,
        expiration=add_days(scr.curr_time, 30), filling=evidence or None,
    )
    return node


def reflect(persona):
    """Fire an importance-triggered reflection when the threshold is crossed."""
    if _reflection_trigger(persona):
        run_reflect(persona)
        _reset_reflection_counter(persona)


# --------------------------------------------------------------------------- #
# EXECUTE                                                                      #
# --------------------------------------------------------------------------- #
def execute(persona, maze, personas, plan):
    """Path toward the action address; return (next_tile, emoji, description)."""
    scr = persona.scratch
    curr = tuple(scr.curr_tile)

    if not scr.act_path_set:
        target_tiles = list(maze.address_tiles.get(plan, {curr}))
        best_path = None
        for t in target_tiles:
            p = maze.get_path(curr, t)
            if p and (best_path is None or len(p) < len(best_path)):
                best_path = p
        if not best_path:
            best_path = [curr]
        scr.planned_path = [list(t) for t in best_path[1:]]
        scr.act_path_set = True

    ret = list(scr.curr_tile)
    if scr.planned_path:
        ret = scr.planned_path[0]
        scr.planned_path = scr.planned_path[1:]

    description = f"{scr.act_description} @ {scr.act_address}"
    return ret, scr.act_pronunciatio, description
