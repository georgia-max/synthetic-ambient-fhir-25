"""DIRECTOR: bake the vertical-slice replay (subplan B section 4).

Steps the seven-persona cast through Clarence Reinger's prenatal visit, writing
one ``storage/base_hospital/movement/<step>.json`` per step in the contract
shape. Movement is driven by the real cognition loop (``modules.perceive`` +
``modules.execute`` + the maze pathfinder) with the director owning the care-
pathway schedule (the role ``reverie.py`` plays in the original). Marcus follows
Clarence one tile behind; background patients sit and idle.

The OB consult is injected VERBATIM: the hero record ``transcript`` is parsed into
``(speaker, text)`` turns (DR->Dr. Amari, PT->Clarence, FAMILY->Marcus) and paced
across the consult steps, with a running window of the last few lines and the
``pronunciatio`` following the active speaker. After the consult, two reflection
thought nodes are written to Clarence via the cognition reflect path
(``modules._add_thought`` / ``prompts.memo_on_convo``), grounded in the note's
Assessment and Plan.

Runs fully in canned LLM mode (no API key). Deterministic.
"""
from __future__ import annotations

import datetime
import math
from pathlib import Path
from typing import Optional

from hgen.config import DATETIME_FMT, SEC_PER_STEP, STORAGE, WORLD_NAME
from hgen.contracts import (
    make_movement,
    make_movement_entry,
    persona_bootstrap_dir,
    read_meta,
    write_movement,
)
from hgen.cognition.persona import Persona
from hgen.cognition import modules
from hgen.llm import prompts
from hgen.world.maze import Maze
from hgen.seeding.build import find_hero, load_records
from hgen.seeding.notes import assessment_headings, parse_note, parse_transcript

# --------------------------------------------------------------------------- #
# Canonical addresses (match the maze + modules.py)                           #
# --------------------------------------------------------------------------- #
W = WORLD_NAME
ADMISSIONS = f"{W}:Admissions:reception:reception desk"
WAITING = f"{W}:Waiting Room:waiting area:waiting chairs"
TRIAGE = f"{W}:Triage:triage bay 1:vitals station"
OB_EXAM = f"{W}:OB / Prenatal Clinic:exam room:exam table"
DISCHARGE = f"{W}:Discharge:discharge desk:exit"
HOME = "<spawn_loc>Home"

# --------------------------------------------------------------------------- #
# Emoji glyphs (pronunciatio)                                                  #
# --------------------------------------------------------------------------- #
WALK = "\U0001F6B6"   # 🚶
WAIT = "⌛"       # ⌛
STETH = "\U0001FA7A"  # 🩺
PREG = "\U0001F930"   # 🤰
HEART = "\U0001FAC0"  # 🫀  (fetal heart tones beat)
THINK = "\U0001F4AD"  # 💭
CHECK = "✅"      # ✅
TALK = "\U0001F4AC"   # 💬
MAN = "\U0001F468"    # 👨

# Emoji a persona shows while listening in a conversation.
LISTEN_EMOJI = {
    "Dr. Amari": STETH,
    "Nurse Reyes": STETH,
    "Clarence Reinger": PREG,
    "Marcus": MAN,
    "Rosa Diaz": TALK,
}
# Emoji a persona shows while it is the active speaker.
SPEAK_EMOJI = dict(LISTEN_EMOJI)

CAST = ["Clarence Reinger", "Marcus", "Nurse Reyes", "Dr. Amari",
        "Rosa Diaz", "Patient A", "Patient B"]
COGNITIVE = ["Clarence Reinger", "Nurse Reyes", "Dr. Amari"]

SPAWN = {
    "Clarence Reinger": (2, 13), "Marcus": (3, 13), "Nurse Reyes": (13, 3),
    "Dr. Amari": (23, 3), "Rosa Diaz": (4, 3), "Patient A": (4, 10),
    "Patient B": (5, 10),
}

# Consult tableau (offset so the three participants do not overlap).
CONSULT_TABLEAU = {
    "Clarence Reinger": (24, 3),
    "Dr. Amari": (23, 3),
    "Marcus": (22, 3),
}
SPEAKER_MAP = {"DR": "Dr. Amari", "PT": "Clarence Reinger", "FAMILY": "Marcus"}
# Transcript beats where Dr. Amari's emoji switches to fetal heart tones.
_ULTRASOUND_KW = ("flicker", "heartbeat", "heart sounds", "look at the screen",
                  "listened in", "the screen")


# --------------------------------------------------------------------------- #
# Note-plan helpers (ground the post-consult reflections)                      #
# --------------------------------------------------------------------------- #
def _plan_sections(assessment_and_plan: str) -> list[tuple[str, str]]:
    """Return [(heading, first_bullet), ...] from the Assessment and Plan text."""
    out: list[tuple[str, str]] = []
    heading: Optional[str] = None
    bullet: Optional[str] = None
    for line in assessment_and_plan.splitlines():
        s = line.strip()
        if s.startswith("###"):
            if heading is not None:
                out.append((heading, bullet or ""))
            heading = s.lstrip("# ").strip()
            bullet = None
        elif s.startswith("-") and bullet is None:
            bullet = s.lstrip("- ").strip()
    if heading is not None:
        out.append((heading, bullet or ""))
    return out


# --------------------------------------------------------------------------- #
# Director                                                                     #
# --------------------------------------------------------------------------- #
class Director:
    """Runs the scripted care-pathway step loop, baking movement frames."""

    def __init__(self, sim_code: str = "base_hospital",
                 storage: Optional[Path] = None):
        root = Path(storage) if storage else STORAGE
        self.base = root / sim_code
        self.personas_dir = self.base / "personas"
        self.movement_dir = self.base / "movement"
        self.maze = Maze()

        meta = read_meta(self.base / "reverie" / "meta.json")
        self.t = datetime.datetime.strptime(meta["curr_time"], DATETIME_FMT)

        self.personas = {n: Persona(n, persona_bootstrap_dir(self.personas_dir, n))
                         for n in CAST}
        self.positions = {n: SPAWN[n] for n in CAST}
        self.step = 0

        # Per-persona standing action: {target, emoji, desc}.
        self.action = {n: {"target": None, "emoji": WAIT, "desc": ""} for n in CAST}
        self._init_standing_actions()

        # Hero record: transcript turns + note plan.
        hero = find_hero(load_records())
        self.hero = hero
        self.consult_turns = [(SPEAKER_MAP[s], txt)
                              for s, txt in parse_transcript(hero["transcript"])
                              if s in SPEAKER_MAP]
        self.plan_sections = _plan_sections(
            parse_note(hero["note"])["assessment_and_plan"])
        self.consult_chat_id: Optional[str] = None

    # ---- setup ---------------------------------------------------------- #
    def _init_standing_actions(self):
        self.action["Rosa Diaz"] = {"target": ADMISSIONS, "emoji": TALK,
            "desc": f"working at the reception desk @ {ADMISSIONS}"}
        self.action["Nurse Reyes"] = {"target": TRIAGE, "emoji": STETH,
            "desc": f"on shift in triage @ {TRIAGE}"}
        self.action["Dr. Amari"] = {"target": OB_EXAM, "emoji": STETH,
            "desc": f"reviewing charts in the OB clinic @ {OB_EXAM}"}
        for n in ("Patient A", "Patient B"):
            self.action[n] = {"target": WAITING, "emoji": WAIT,
                "desc": f"waiting to be seen @ {WAITING}"}
        self.action["Marcus"] = {"target": None, "emoji": WALK,
            "desc": f"arriving with Clarence @ {ADMISSIONS}"}
        self.action["Clarence Reinger"] = {"target": ADMISSIONS, "emoji": WALK,
            "desc": f"walking in to check in @ {ADMISSIONS}"}

    # ---- time ----------------------------------------------------------- #
    def time_str(self) -> str:
        return self.t.strftime(DATETIME_FMT)

    # ---- cognition-backed movement -------------------------------------- #
    def _advance(self, name: str, target: str):
        """Run perceive + execute (BFS pathfinding) one step toward ``target``."""
        p = self.personas[name]
        scr = p.scratch
        scr.curr_time = self.time_str()
        scr.curr_tile = list(self.positions[name])
        modules.perceive(p, self.maze)  # grows spatial memory + events
        if scr.act_address != target:
            scr.act_address = target
            scr.act_path_set = False
            scr.planned_path = []
        next_tile, _, _ = modules.execute(p, self.maze, self.personas, target)
        self.positions[name] = tuple(next_tile)

    def _perceive_only(self, name: str, tile):
        p = self.personas[name]
        p.scratch.curr_time = self.time_str()
        p.scratch.curr_tile = list(tile)
        modules.perceive(p, self.maze)

    # ---- one baked frame ------------------------------------------------ #
    def tick(self, chats: Optional[dict] = None, pin: Optional[dict] = None):
        """Advance everyone one step and write movement/<step>.json."""
        chats = chats or {}
        pin = pin or {}
        clar_prev = self.positions["Clarence Reinger"]

        for name in COGNITIVE:
            if name in pin:
                self.positions[name] = pin[name]
                self._perceive_only(name, pin[name])
            else:
                self._advance(name, self.action[name]["target"])

        # Marcus follows one tile behind Clarence (unless pinned).
        self.positions["Marcus"] = pin.get("Marcus", clar_prev)
        # Rosa + background patients hold their seats (positions unchanged).

        entries = {}
        for name in CAST:
            act = self.action[name]
            chat = chats.get(name)
            emoji = act["emoji"]
            entries[name] = make_movement_entry(
                list(self.positions[name]), emoji, act["desc"], chat)
        write_movement(self.movement_dir, self.step,
                       make_movement(entries, self.time_str()))
        self.step += 1
        self.t += datetime.timedelta(seconds=SEC_PER_STEP)

    # ---- phase primitives ----------------------------------------------- #
    def _clar_arrived(self, target: str) -> bool:
        return tuple(self.positions["Clarence Reinger"]) in \
            self.maze.address_tiles.get(target, set())

    def walk_clarence(self, target: str, phrase: str, max_steps: int = 60):
        """Walk Clarence (+following Marcus) to ``target``; idle everyone else."""
        self.action["Clarence Reinger"] = {"target": target, "emoji": WALK,
            "desc": f"{phrase} @ {target}"}
        self.action["Marcus"] = {"target": None, "emoji": WALK,
            "desc": f"walking with Clarence @ {target}"}
        n = 0
        while not self._clar_arrived(target) and n < max_steps:
            self.tick()
            n += 1
        self.tick()  # one settling frame on arrival

    def walk_steps(self, target: str, phrase: str, n_steps: int):
        """Walk Clarence toward ``target`` for a fixed number of steps."""
        self.action["Clarence Reinger"] = {"target": target, "emoji": WALK,
            "desc": f"{phrase} @ {target}"}
        self.action["Marcus"] = {"target": None, "emoji": WALK,
            "desc": f"leaving with Clarence @ {target}"}
        for _ in range(n_steps):
            self.tick()

    def dwell(self, name_desc: dict, emoji: dict, steps: int,
              chats_seq=None, pin=None):
        """Hold position for ``steps`` frames with optional per-step chats."""
        for name, desc in name_desc.items():
            self.action[name] = {"target": self.action[name]["target"],
                                 "emoji": emoji.get(name, self.action[name]["emoji"]),
                                 "desc": desc}
        for i in range(steps):
            chats = chats_seq(i) if chats_seq else None
            self.tick(chats=chats, pin=pin)

    # ---- conversation pacing -------------------------------------------- #
    def run_convo(self, turns, descs: dict, rate: int, extra_dwell: int = 0,
                  pin: Optional[dict] = None):
        """Emit a conversation, ~``rate`` turns/step, bubble on the active speaker."""
        participants = list(descs.keys())
        for name in participants:
            self.action[name] = {"target": self.action[name]["target"],
                                 "emoji": LISTEN_EMOJI.get(name, TALK),
                                 "desc": descs[name]}
        n_turns = len(turns)
        n_steps = math.ceil(n_turns / rate) + extra_dwell
        for local in range(n_steps):
            revealed = min(n_turns, (local + 1) * rate)
            window = [[spk, txt] for spk, txt in turns[max(0, revealed - 3):revealed]]
            chats = None
            if revealed > 0:
                active, atext = turns[revealed - 1]
                # Reset everyone to listening, spotlight the active speaker.
                for name in participants:
                    self.action[name]["emoji"] = LISTEN_EMOJI.get(name, TALK)
                self.action[active]["emoji"] = SPEAK_EMOJI.get(active, TALK)
                if active == "Dr. Amari" and any(k in atext.lower()
                                                 for k in _ULTRASOUND_KW):
                    self.action[active]["emoji"] = HEART
                chats = {active: window}
            self.tick(chats=chats, pin=pin)

    # ---- reflection (post-consult) -------------------------------------- #
    def _record_consult_chat(self):
        clar = self.personas["Clarence Reinger"]
        clar.scratch.chatting_with = "Dr. Amari"
        filling = [[spk, txt] for spk, txt in self.consult_turns]
        node = clar.a_mem.add_chat(
            self.time_str(), "Clarence Reinger", "discussed", "Dr. Amari",
            "consult with Dr. Amari about the pregnancy",
            ["dr. amari", "consult", "pregnancy", "clarence reinger"], 7,
            filling=filling)
        self.consult_chat_id = node.node_id

    def write_reflections(self):
        """Write two reflection thought nodes to Clarence (grounded in the note)."""
        clar = self.personas["Clarence Reinger"]
        evidence = [self.consult_chat_id] if self.consult_chat_id else None
        convo_text = "\n".join(f"{spk}: {txt}" for spk, txt in self.consult_turns)
        # Exercise the Opus post-convo memo (reflect path).
        memo = prompts.memo_on_convo(clar, convo_text)

        secs = self.plan_sections
        if secs:
            head1, bull1 = secs[0]
            t1 = (f"{memo.rstrip('.')}; today confirmed a {head1.lower()} "
                  f"— {bull1}" if bull1 else
                  f"{memo.rstrip('.')}; today confirmed a {head1.lower()}.")
        else:
            t1 = memo
        modules._add_thought(clar, t1, evidence)

        if len(secs) >= 2:
            head2, bull2 = secs[1]
            t2 = (f"Clarence learned that because of the {head2.lower()}, "
                  f"{bull2}" if bull2 else
                  f"Clarence must stay vigilant about the {head2.lower()}.")
        else:
            t2 = ("Clarence will call the clinic the same day for any urinary "
                  "symptoms, given the recurrent UTI history.")
        modules._add_thought(clar, t2, evidence)

    # ---- the full journey ----------------------------------------------- #
    def run(self) -> int:
        """Bake all movement frames; return the number of steps written."""
        self.movement_dir.mkdir(parents=True, exist_ok=True)
        for stale in self.movement_dir.glob("*.json"):  # avoid orphaned frames
            stale.unlink()

        # 0. First-day planning (builds the care pathway on the hero cognition).
        modules.plan(self.personas["Clarence Reinger"], self.maze,
                     self.personas, "First day", {})

        # 1. Arrival: Home -> reception.
        self.walk_clarence(ADMISSIONS, "walking in to check in")

        # 2. Check-in conversation with Rosa.
        self.run_convo(
            [
                ("Rosa Diaz", "Good morning! Checking in?"),
                ("Clarence Reinger", "Yes — Clarence Reinger, here for my first prenatal visit."),
                ("Rosa Diaz", "You're all set. Please have a seat; they'll call you shortly."),
            ],
            descs={
                "Rosa Diaz": f"checking in a patient @ {ADMISSIONS}",
                "Clarence Reinger": f"checking in at reception @ {ADMISSIONS}",
            },
            rate=1, extra_dwell=1)

        # 3. Waiting room: walk to a chair, then idle (background patients chat).
        self.walk_clarence(WAITING, "walking to the waiting room")

        def waiting_chat(i):
            if i == 1:
                return {"Patient A": [["Patient A", "First time here?"]]}
            if i == 2:
                return {"Patient B": [["Patient A", "First time here?"],
                                      ["Patient B", "No, just a check-up. Long wait today."]]}
            return None

        self.dwell(
            {"Clarence Reinger": f"waiting to be seen @ {WAITING}",
             "Marcus": f"waiting with Clarence @ {WAITING}",
             "Patient A": f"chatting in the waiting room @ {WAITING}",
             "Patient B": f"chatting in the waiting room @ {WAITING}"},
            {"Clarence Reinger": WAIT, "Marcus": WAIT,
             "Patient A": TALK, "Patient B": TALK},
            steps=5, chats_seq=waiting_chat)

        # 4. To triage.
        self.walk_clarence(TRIAGE, "heading to triage")

        # 5. Triage: vitals + brief history (grounded in the nurse's knowledge).
        self.run_convo(
            [("Nurse Reyes", "Let's get your vitals — blood pressure first."),
             ("Clarence Reinger", "Okay."),
             ("Nurse Reyes", "118 over 72, heart rate 78 — all in a healthy range."),
             ("Clarence Reinger", "Good. I get UTIs a lot; that's my worry."),
             ("Nurse Reyes", "I'll flag that for the doctor. Temperature's normal, no fever.")],
            descs={
                "Nurse Reyes": f"taking vitals @ {TRIAGE}",
                "Clarence Reinger": f"getting triaged (vitals and history) @ {TRIAGE}",
            },
            rate=1)

        # 6. To the OB clinic.
        self.walk_clarence(OB_EXAM, "walking to the OB clinic")

        # 7. The verbatim consult (centerpiece).
        self.run_convo(
            self.consult_turns,
            descs={
                "Dr. Amari": f"consulting with Clarence and Marcus @ {OB_EXAM}",
                "Clarence Reinger": f"in the prenatal consult @ {OB_EXAM}",
                "Marcus": f"supporting Clarence in the consult @ {OB_EXAM}",
            },
            rate=2, extra_dwell=1, pin=CONSULT_TABLEAU)
        self._record_consult_chat()

        # 8. Reflection: Clarence internalizes the plan (two thought nodes).
        self.write_reflections()
        self.dwell(
            {"Clarence Reinger": f"thinking about the care plan @ {OB_EXAM}",
             "Marcus": f"talking it over with Clarence @ {OB_EXAM}"},
            {"Clarence Reinger": THINK, "Marcus": MAN},
            steps=4, pin=CONSULT_TABLEAU)

        # 9. Discharge.
        self.walk_clarence(DISCHARGE, "heading to discharge")
        self.dwell(
            {"Clarence Reinger": f"getting discharge instructions @ {DISCHARGE}",
             "Marcus": f"waiting with Clarence @ {DISCHARGE}"},
            {"Clarence Reinger": CHECK, "Marcus": MAN},
            steps=4,
            chats_seq=lambda i: {"Clarence Reinger": [
                ["Clarence Reinger",
                 "Got it — next prenatal visit in four weeks."]]} if i == 1 else None)

        # 10. Exit.
        self.walk_steps(HOME, "leaving the hospital", n_steps=6)

        # Persist grown memory + reflections for the cognitive personas.
        for name in COGNITIVE:
            self.personas[name].save(persona_bootstrap_dir(self.personas_dir, name))

        return self.step


def run_director(sim_code: str = "base_hospital",
                 storage: Optional[Path] = None) -> int:
    """Bake the vertical slice; return the number of movement frames written."""
    d = Director(sim_code=sim_code, storage=storage)
    n = d.run()
    return n


def main() -> None:
    n = run_director()
    print(f"Director baked {n} movement frames -> "
          f"{STORAGE / 'base_hospital' / 'movement'}")


if __name__ == "__main__":
    main()
