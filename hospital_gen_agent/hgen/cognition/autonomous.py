"""AUTONOMOUS director: full-hospital bake of ALL 25 dataset patients.

Runs the real cognitive loop for every persona: each step every active agent
calls ``Persona.move`` (perceive -> retrieve -> plan -> reflect -> execute), so
movement and the care pathway are agent-driven. Each patient is routed to THEIR
real department (seeded ``scratch.dept_address`` from ``visit_type``) and walks
Admissions -> Waiting -> Triage -> their department -> Discharge -> exit.

Arrivals are STAGGERED: each patient gets a ``start_step`` offset and waits at the
Home entrance until then, so the hospital fills up over time instead of all at
once. Clinical staff idle at their stations (doctor per department, two triage
nurses, a reception clerk).

Two things stay fixed by design:

* the OB consult is VERBATIM from Clarence Reinger's record transcript (the locked
  money shot): when Clarence reaches the OB exam table co-located with Dr. Amari,
  the real DR:/PT:/FAMILY: lines are injected as ``chat`` and he reflects on them;
* every other patient runs the same loop but with stubbed (no) dialogue, which
  keeps the whole bake running in canned mode with no API key.

Writes ``storage/<sim>/movement/<step>.json`` per step (same contract as the
scripted bake), so ``compress.py`` and the renderer consume it unchanged.

Run via ``run_slice.py`` (default) or ``HGEN_MODE=autonomous``. Deterministic in
canned mode.
"""
from __future__ import annotations

import datetime
import json

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
from hgen.world.maze import Maze
from hgen.seeding.build import find_hero, load_records
from hgen.seeding.notes import parse_transcript

W = WORLD_NAME
OB_EXAM = f"{W}:OB / Prenatal Clinic:exam room:exam table"
HOME = "<spawn_loc>Home"

HERO, DOCTOR, SPOUSE = "Clarence Reinger", "Dr. Amari", "Marcus"

WALK = "\U0001F6B6"     # 🚶
WAIT = "⌛"             # ⌛
LISTEN = "\U0001F442"   # 👂
SPEAK = "\U0001F4AC"    # 💬
HEART = "\U0001FAC0"    # 🫀 fetal heart
MAN = "\U0001F468"      # 👨
CHECK = "✅"            # ✅

# Transcript beats where the doctor's emoji switches to fetal-heart tones.
_ULTRASOUND_KW = ("flicker", "heartbeat", "heart tones", "heart sounds",
                  "the screen", "listened in")


def _consult_turns(transcript: str) -> list[list[str]]:
    """Verbatim consult turns mapped DR->doctor, PT->hero, FAMILY->spouse."""
    role = {"DR": DOCTOR, "PT": HERO, "FAMILY": SPOUSE}
    out = []
    for spk, txt in parse_transcript(transcript):
        who = role.get(spk.upper())
        if who:
            out.append([who, txt])
    return out


class AutonomousDirector:
    """Steps every persona through the hospital via live cognition; bakes frames."""

    def __init__(self, sim_code: str = "base_hospital",
                 max_steps: int = 320, stagger: int = 6):
        self.sim_code = sim_code
        self.max_steps = max_steps
        self.stagger = stagger
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
        self.home_tile = self.tiles.get(HERO, (1, 8))

        self.t = datetime.datetime.strptime(self.meta["curr_time"], DATETIME_FMT)
        self.step = 0

        # Roster: patients (living at Home, not the spouse), staff, and Marcus.
        self.spouse = SPOUSE if SPOUSE in self.personas else None
        self.patients = [n for n in names
                         if self.personas[n].scratch.living_area == "Home"
                         and n != self.spouse]
        self.staff = [n for n in names
                      if self.personas[n].scratch.living_area != "Home"]

        # Staggered arrivals: hero first (offset 0), then dataset order.
        self.start_step = {n: i * stagger for i, n in enumerate(self.patients)}
        self.left: dict[str, bool] = {n: False for n in self.patients}

        # Verbatim consult state.
        self.consult = _consult_turns(find_hero(load_records())["transcript"])
        self.consult_state = "pending"   # pending -> active -> done
        self.consult_vi = 0
        self.reflected = False
        self.ob_tiles = self.maze.address_tiles.get(OB_EXAM, set())
        self.ob_arena = (self.maze.get_tile_path(tuple(next(iter(self.ob_tiles))), "arena")
                         if self.ob_tiles else "OB / Prenatal Clinic:exam room")

    # ---- helpers -------------------------------------------------------- #
    def time_str(self) -> str:
        return self.t.strftime(DATETIME_FMT)

    def _move(self, name: str) -> dict:
        """Run one cognitive step for ``name`` and return its movement entry."""
        p = self.personas[name]
        nxt, emoji, desc = p.move(self.maze, self.personas, self.tiles[name],
                                  self.time_str())
        self.tiles[name] = tuple(nxt)
        return make_movement_entry(list(nxt), emoji, desc, None)

    # ---- verbatim consult overlay -------------------------------------- #
    def _advance_consult(self, entries: dict):
        """Reveal ~2 verbatim turns; pin Clarence, Dr. Amari, and Marcus."""
        for _ in range(2):
            if self.consult_vi < len(self.consult):
                self.consult_vi += 1
        shown = self.consult[max(0, self.consult_vi - 3):self.consult_vi]
        speaker = shown[-1][0] if shown else HERO
        heart = any(k in txt.lower() for _who, txt in shown for k in _ULTRASOUND_KW)

        pin = {HERO: self.tiles[HERO], DOCTOR: self.tiles[DOCTOR],
               SPOUSE: self.tiles[HERO]}
        for who, tile in pin.items():
            if who not in self.personas:
                continue
            emoji = HEART if (heart and who == DOCTOR) else (
                SPEAK if who == speaker else LISTEN)
            entries[who] = make_movement_entry(
                list(tile), emoji,
                f"in the prenatal consult @ {self.ob_arena}", shown)

        if self.consult_vi >= len(self.consult):
            self.consult_state = "done"
            self._reflect_after()

    def _reflect_after(self):
        """Post-consult reflection: Clarence internalizes the plan (grounded)."""
        if self.reflected:
            return
        convo_text = "\n".join(f"{w}: {t}" for w, t in self.consult)
        modules.reflect_on_convo(self.personas[HERO], convo_text)
        modules.run_reflect(self.personas[HERO])
        self.reflected = True
        print(f"[autonomous] {HERO} reflected after the verbatim consult")

    def _hero_at_ob(self) -> bool:
        return (tuple(self.tiles[HERO]) in self.ob_tiles
                and DOCTOR in self.personas
                and tuple(self.tiles[DOCTOR]) in self.ob_tiles)

    # ---- main loop ------------------------------------------------------ #
    def run(self) -> int:
        for stale in self.movement_dir.glob("*.json"):  # avoid orphaned frames
            stale.unlink()

        while self.step < self.max_steps:
            entries: dict = {}

            # Staff idle at their stations (still driven by the cognition loop).
            for name in self.staff:
                entries[name] = self._move(name)

            # Patients: staggered arrivals, then the full care pathway.
            for name in self.patients:
                if self.step < self.start_step[name]:
                    entries[name] = make_movement_entry(
                        list(self.tiles[name]), WAIT,
                        f"waiting to arrive @ {HOME}", None)
                    continue
                if name == HERO and self.consult_state == "active":
                    continue  # pinned; filled by the consult overlay below
                entries[name] = self._move(name)
                desc = entries[name]["description"]
                if "leaving" in desc.lower() and tuple(self.tiles[name]) == self.home_tile:
                    if not self.left[name]:
                        self.left[name] = True
                        entries[name]["pronunciatio"] = CHECK
                # Hero reaches the OB exam co-located with Dr. Amari -> consult.
                if (name == HERO and self.consult_state == "pending"
                        and self._hero_at_ob()):
                    self.consult_state = "active"
                    self.consult_vi = 0

            # Verbatim consult overlay (pins the three participants).
            if self.consult_state == "active":
                self._advance_consult(entries)

            # Spouse follows the hero one tile behind.
            if self.spouse:
                entries[self.spouse] = make_movement_entry(
                    list(self.tiles[HERO]), MAN,
                    f"with {HERO} @ the hospital", None)

            write_movement(self.movement_dir, self.step,
                           make_movement(entries, self.time_str()))
            self.step += 1
            self.t += datetime.timedelta(seconds=SEC_PER_STEP)

            # Stop once every patient has arrived and left and the consult is done.
            if (all(self.left.values()) and self.consult_state != "active"
                    and self.step > max(self.start_step.values(), default=0) + 10):
                break

        # Persist grown memory + reflections.
        for name in self.patients + self.staff:
            self.personas[name].save(persona_bootstrap_dir(self.sim / "personas", name))
        print(f"[autonomous] wrote {self.step} movement frames "
              f"({len(self.patients)} patients, {len(self.staff)} staff)")
        return self.step


def run_autonomous(sim_code: str = "base_hospital",
                   max_steps: int = 320, stagger: int = 6) -> int:
    return AutonomousDirector(sim_code, max_steps, stagger).run()


if __name__ == "__main__":
    run_autonomous()
