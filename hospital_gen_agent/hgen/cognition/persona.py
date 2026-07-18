"""The Persona: identity + the three memory structures + the move() chain.

Loads a bootstrap dir (``scratch.json`` / ``spatial_memory.json`` /
``associative_memory/``) into a ``Scratch``, ``MemoryTree``, and
``AssociativeMemory``, then runs the original cognitive sequence
``perceive -> retrieve -> plan -> reflect -> execute`` in ``move()`` and returns
the execute triple ``(next_tile, pronunciatio, description)``.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional, Union

from hgen.config import DATETIME_FMT, STORAGE
from hgen.contracts import PathLike, Scratch, persona_bootstrap_dir
from hgen.cognition.memory import AssociativeMemory, MemoryTree, parse_dt
from hgen.cognition import modules


class Persona:
    """A generative agent: patient or clinical staff."""

    def __init__(self, name: str, boot_dir: PathLike):
        self.name = name
        boot = Path(boot_dir)
        self.scratch = Scratch.load(boot / "scratch.json")
        self.s_mem = MemoryTree(boot / "spatial_memory.json")
        self.a_mem = AssociativeMemory(boot / "associative_memory")
        # Pathway progress (transient; not part of the persisted contract).
        self.stage = 0

    # ---- loading -------------------------------------------------------- #
    @classmethod
    def load(cls, name: str, sim_code: str = "base_hospital",
             storage: Optional[PathLike] = None) -> "Persona":
        """Load a seeded persona from ``storage/<sim_code>/personas/<name>``."""
        root = Path(storage) if storage else STORAGE
        boot = persona_bootstrap_dir(root / sim_code / "personas", name)
        return cls(name, boot)

    # ---- saving --------------------------------------------------------- #
    def save(self, save_dir: PathLike) -> Path:
        """Persist scratch / spatial / associative memory to ``save_dir``."""
        save_dir = Path(save_dir)
        (save_dir / "associative_memory").mkdir(parents=True, exist_ok=True)
        self.scratch.save(save_dir / "scratch.json")
        self.s_mem.save(save_dir / "spatial_memory.json")
        self.a_mem.save(save_dir / "associative_memory")
        return save_dir

    # ---- cognitive-module thin wrappers -------------------------------- #
    def perceive(self, maze):
        return modules.perceive(self, maze)

    def retrieve(self, perceived):
        return modules.retrieve(self, perceived)

    def plan(self, maze, personas, new_day, retrieved):
        return modules.plan(self, maze, personas, new_day, retrieved)

    def reflect(self):
        return modules.reflect(self)

    def execute(self, maze, personas, plan):
        return modules.execute(self, maze, personas, plan)

    # ---- the main step -------------------------------------------------- #
    def move(self, maze, personas, curr_tile, curr_time: Union[str, datetime.datetime]):
        """Run one cognitive step; return (next_tile, pronunciatio, description)."""
        self.scratch.curr_tile = list(curr_tile)

        curr_time_str = (curr_time if isinstance(curr_time, str)
                         else curr_time.strftime(DATETIME_FMT))
        new_day = False
        if not self.scratch.curr_time:
            new_day = "First day"
        else:
            prev, now = parse_dt(self.scratch.curr_time), parse_dt(curr_time_str)
            if prev.strftime("%A %B %d") != now.strftime("%A %B %d"):
                new_day = "New day"
        self.scratch.curr_time = curr_time_str

        perceived = self.perceive(maze)
        retrieved = self.retrieve(perceived)
        plan = self.plan(maze, personas, new_day, retrieved)
        self.reflect()
        return self.execute(maze, personas, plan)


# --------------------------------------------------------------------------- #
# Smoke run: step Dr. Amari and Clarence Reinger against the maze              #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import datetime as _dt

    from hgen.config import SEC_PER_STEP
    from hgen.world.maze import Maze

    maze = Maze()
    clarence = Persona.load("Clarence Reinger")
    amari = Persona.load("Dr. Amari")
    personas = {clarence.name: clarence, amari.name: amari}

    # Spawn tiles: Clarence at Home, Dr. Amari at the OB exam table.
    start_tiles = {
        clarence.name: (2, 13),
        amari.name: (23, 3),
    }
    t = _dt.datetime(2026, 3, 21, 8, 0, 0)

    print(f"=== Smoke run: {SEC_PER_STEP}s/step, canned LLM mode ===")
    for step in range(8):
        curr_time = t.strftime(DATETIME_FMT)
        print(f"\n-- step {step}  ({curr_time}) --")
        for p in (clarence, amari):
            tile = start_tiles[p.name]
            next_tile, emoji, desc = p.move(maze, personas, tile, curr_time)
            start_tiles[p.name] = tuple(next_tile)  # advance sprite
            print(f"  {p.name:16s} {emoji}  {next_tile}  {desc}")
        t += _dt.timedelta(seconds=SEC_PER_STEP)

    print("\nClarence memory nodes:", len(clarence.a_mem.id_to_node))
    print("Clarence learned OB sectors:",
          clarence.s_mem.get_str_accessible_sectors("General Hospital"))
