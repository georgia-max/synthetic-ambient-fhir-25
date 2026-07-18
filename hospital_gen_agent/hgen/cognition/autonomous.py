"""AUTONOMOUS director: full generative-agents bake (live Claude).

Unlike the scripted ``director.py`` (fixed timeline, hardcoded triage lines), this
runs the real cognitive loop: every step each active agent calls ``Persona.move``
(perceive -> retrieve -> plan -> reflect -> execute), so movement and the care
pathway are agent-driven. Conversations are GENERATED live via
``prompts.gen_utterance``, grounded in each speaker's seeded memory. Two things
stay fixed by design:

* the OB consult is VERBATIM from the record transcript (the locked money shot);
* routing is agent-decided but grounded: the patient's department is chosen by
  ``prompts.gen_action_sector`` over the departments that exist on the map.

Writes ``storage/<sim>/movement/<step>.json`` per step (same contract as the
scripted bake), so ``compress.py`` and the renderer consume it unchanged.

Run via ``run_slice.py`` with ``HGEN_MODE=autonomous``. Use
``HGEN_LLM_MODE=cache`` for a paid-once, replayable bake (``canned`` still runs,
with stubbed dialogue).
"""
from __future__ import annotations

import datetime
import json
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
from hgen.seeding.notes import parse_transcript

W = WORLD_NAME
TRIAGE = f"{W}:Triage:triage bay 1:vitals station"
OB_EXAM = f"{W}:OB / Prenatal Clinic:exam room:exam table"
RECEPTION = f"{W}:Admissions:reception:reception desk"
WAITING = f"{W}:Waiting Room:waiting area:waiting chairs"

HERO, DOCTOR, NURSE, CLERK = "Clarence Reinger", "Dr. Amari", "Nurse Reyes", "Rosa Diaz"
SPOUSE = "Marcus"

LISTEN = "\U0001F442"   # 👂
SPEAK = "\U0001F4AC"    # 💬
HEART = "\U0001FAC0"    # 🫀 fetal heart
MAN = "\U0001F468"      # 👨


def _consult_turns(transcript: str) -> list[list[str]]:
    """Verbatim consult turns mapped DR->doctor, PT->hero, FAMILY->spouse."""
    role = {"DR": DOCTOR, "PT": HERO, "FAMILY": SPOUSE, "NURSE": NURSE}
    out = []
    for spk, txt in parse_transcript(transcript):
        who = role.get(spk.upper())
        if who:
            out.append([who, txt])
    return out


class _Convo:
    def __init__(self, kind, partners, context, turns, verbatim=None):
        self.kind = kind
        self.partners = partners          # (a, b) or (hero, doctor, spouse)
        self.context = context
        self.turns = turns                # max generated lines
        self.verbatim = verbatim          # list[[who,text]] or None
        self.history: list[list[str]] = []
        self.vi = 0                       # verbatim index
        self.done = False


class AutonomousDirector:
    """Steps the cast through Clarence's visit via live cognition + dialogue."""

    def __init__(self, sim_code: str = "base_hospital", max_steps: int = 170):
        self.sim_code = sim_code
        self.max_steps = max_steps
        self.sim = STORAGE / sim_code
        self.meta = read_meta(self.sim / "reverie" / "meta.json")
        self.maze = Maze()
        self.movement_dir = self.sim / "movement"
        self.movement_dir.mkdir(parents=True, exist_ok=True)

        names = self.meta["persona_names"]
        pdir = self.sim / "personas"
        self.personas = {n: Persona(n, persona_bootstrap_dir(pdir, n)) for n in names}

        env0 = json.loads((self.sim / "environment" / "0.json").read_text())
        self.tiles = {n: (env0[n]["x"], env0[n]["y"]) for n in names}

        self.t = datetime.datetime.strptime(self.meta["curr_time"], DATETIME_FMT)
        self.step = 0
        self.active = [n for n in (HERO, NURSE, DOCTOR, CLERK) if n in self.personas]
        self.ambient = [n for n in ("Patient A", "Patient B") if n in self.personas]
        self.consult = _consult_turns(find_hero(load_records())["transcript"])

        self.convos: dict[str, _Convo] = {}
        self.reflected = False

        # Precompute arena paths for the rooms we trigger dialogue in.
        self._arena_of_addr = {
            "triage": self._arena_for(TRIAGE),
            "ob": self._arena_for(OB_EXAM),
            "reception": self._arena_for(RECEPTION),
            "waiting": self._arena_for(WAITING),
        }

    # ---- helpers -------------------------------------------------------- #
    def _arena_for(self, addr: str) -> str:
        tiles = self.maze.address_tiles.get(addr)
        return self.maze.get_tile_path(tuple(next(iter(tiles))), "arena") if tiles else ""

    def _arena(self, name: str) -> str:
        tile = self.tiles.get(name)
        return self.maze.get_tile_path(tuple(tile), "arena") if tile else ""

    def time_str(self) -> str:
        return self.t.strftime(DATETIME_FMT)

    def _memories(self, name: str, n: int = 4) -> list[str]:
        p = self.personas[name]
        return [nd.embedding_key for nd in (p.a_mem.seq_thought + p.a_mem.seq_event)
                if nd.embedding_key][:n]

    def _route_decision(self):
        """Agent-decided, grounded routing to a department that exists on the map."""
        depts = sorted({
            addr.split(":")[1] for addr in self.maze.address_tiles
            if addr.startswith(W + ":") and ("Clinic" in addr or "Medicine" in addr)
        }) or ["OB / Prenatal Clinic"]
        scr = self.personas[HERO].scratch
        listed = "\n".join(f"- {d}" for d in depts)
        prompt = (
            f"{scr.name} is a patient. Reason for visit: {scr.currently}. "
            f"Background: {scr.learned}.\n"
            f"Which hospital department should they be routed to?\n{listed}\n"
            "Answer with exactly one department from the list."
        )
        raw = prompts.llm(prompt, model=prompts.MODEL_SONNET, max_tokens=32,
                          canned=depts[0])
        chosen = next((d for d in depts if d.lower() in raw.lower()), depts[0])
        print(f"[autonomous] {HERO} (agent) routed to: {chosen}")

    # ---- conversation triggering --------------------------------------- #
    def _maybe_start(self):
        """Open a conversation when the right agents are co-located."""
        def colo(a, b, arena_key):
            return (self._arena(a) and self._arena(a) == self._arena(b)
                    == self._arena_of_addr[arena_key])

        if "consult" not in self.convos and colo(HERO, DOCTOR, "ob"):
            self.convos["consult"] = _Convo(
                "consult", (HERO, DOCTOR, SPOUSE), "the prenatal consult",
                turns=0, verbatim=self.consult)
        elif "triage" not in self.convos and colo(HERO, NURSE, "triage"):
            self.convos["triage"] = _Convo(
                "triage", (NURSE, HERO), "triage: vitals and history", turns=4)
        elif "checkin" not in self.convos and colo(HERO, CLERK, "reception"):
            self.convos["checkin"] = _Convo(
                "checkin", (CLERK, HERO), "checking in at reception", turns=2)
        if ("waiting" not in self.convos and len(self.ambient) == 2
                and self._arena(self.ambient[0])
                and self._arena(self.ambient[0]) == self._arena(self.ambient[1])):
            self.convos["waiting"] = _Convo(
                "waiting", tuple(self.ambient), "small talk in the waiting room",
                turns=2)

    def _active_convo(self) -> Optional[_Convo]:
        for c in self.convos.values():
            if not c.done and c.kind in ("consult", "triage", "checkin"):
                return c
        return None

    def _pinned_names(self) -> set:
        pinned = set()
        for c in self.convos.values():
            if not c.done:
                pinned.update(c.partners)
        return pinned

    # ---- per-step dialogue --------------------------------------------- #
    def _advance_convo(self, c: _Convo, entries: dict):
        if c.verbatim is not None:
            self._advance_verbatim(c, entries)
        else:
            self._advance_generated(c, entries)

    def _advance_generated(self, c: _Convo, entries):
        a, b = c.partners[0], c.partners[1]
        speaker = a if len(c.history) % 2 == 0 else b
        listener = b if speaker == a else a
        utt, end = prompts.gen_utterance(
            self.personas[speaker], self.personas[listener], c.context,
            history=c.history, memories=self._memories(speaker))
        c.history.append([speaker, utt])
        window = c.history[-3:]
        for who in (a, b):
            if who in entries:
                entries[who]["chat"] = window
                entries[who]["pronunciatio"] = SPEAK if who == speaker else LISTEN
                entries[who]["description"] = (
                    f"{c.context} @ {self._arena(who)}")
        if end or len(c.history) >= c.turns:
            c.done = True
            # Reflection is reserved for the consult (handled in _advance_verbatim),
            # so triage/check-in small talk does not consume it.

    def _advance_verbatim(self, c: _Convo, entries):
        if c.vi >= len(c.verbatim):
            c.done = True
            if not self.reflected:
                self._reflect_after(c.context, c.verbatim)
            return
        window = []
        for _ in range(2):                     # ~2 turns per step
            if c.vi < len(c.verbatim):
                window.append(c.verbatim[c.vi])
                c.vi += 1
        speaker = window[-1][0]
        heart = any(k in t.lower() for _, t in window
                    for k in ("flicker", "heartbeat", "heart tones"))
        shown = c.verbatim[max(0, c.vi - 3):c.vi]
        for who in c.partners:
            if who in entries:
                entries[who]["chat"] = shown
                entries[who]["pronunciatio"] = HEART if heart else (
                    SPEAK if who == speaker else LISTEN)
                entries[who]["description"] = f"in the prenatal consult @ {self._arena(HERO)}"

    def _reflect_after(self, context, history):
        if self.reflected:
            return
        convo_text = "\n".join(f"{w}: {t}" for w, t in history)
        modules.reflect_on_convo(self.personas[HERO], convo_text)
        modules.run_reflect(self.personas[HERO])
        self.reflected = True
        print(f"[autonomous] {HERO} reflected after {context}")

    # ---- main loop ------------------------------------------------------ #
    def run(self) -> int:
        self._route_decision()
        while self.step < self.max_steps:
            self._maybe_start()
            pinned = self._pinned_names()
            entries = {}

            # Active cognition agents: move unless pinned in a conversation.
            for name in self.active:
                if name in pinned:
                    p = self.personas[name]
                    entries[name] = make_movement_entry(
                        list(self.tiles[name]), p.scratch.act_pronunciatio or SPEAK,
                        f"{p.scratch.act_description or 'talking'} @ {self._arena(name)}",
                        None)
                else:
                    p = self.personas[name]
                    nxt, emoji, desc = p.move(self.maze, self.personas,
                                              self.tiles[name], self.time_str())
                    self.tiles[name] = tuple(nxt)
                    entries[name] = make_movement_entry(list(nxt), emoji, desc, None)

            # Spouse follows the hero.
            if SPOUSE in self.personas:
                entries[SPOUSE] = make_movement_entry(
                    list(self.tiles[HERO]), MAN,
                    f"with Clarence @ {self._arena(HERO) or 'the hospital'}", None)

            # Ambient patients idle in the waiting room.
            for name in self.ambient:
                entries[name] = make_movement_entry(
                    list(self.tiles[name]), "⌛",
                    f"waiting @ {WAITING}", None)

            # Overlay the one active hero conversation + ambient chatter.
            active = self._active_convo()
            if active:
                self._advance_convo(active, entries)
            wc = self.convos.get("waiting")
            if wc and not wc.done:
                self._advance_generated(wc, entries)

            write_movement(self.movement_dir, self.step,
                           make_movement(entries, self.time_str()))
            self.step += 1
            self.t += datetime.timedelta(seconds=SEC_PER_STEP)

            # Stop after the hero leaves.
            hero_scr = self.personas[HERO].scratch
            if (self.step > 30 and "leav" in (hero_scr.act_description or "").lower()
                    and not hero_scr.planned_path):
                break

        for name in self.active:
            self.personas[name].save(persona_bootstrap_dir(self.sim / "personas", name))
        print(f"[autonomous] wrote {self.step} movement frames")
        return self.step


def run_autonomous(sim_code: str = "base_hospital", max_steps: int = 170) -> int:
    return AutonomousDirector(sim_code, max_steps).run()


if __name__ == "__main__":
    run_autonomous()
