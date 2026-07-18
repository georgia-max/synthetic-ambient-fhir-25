"""CLI: write the hospital maze matrices + renderer world.json, then self-test.

Run from the hospital_gen_agent package root::

    .venv/bin/python -m hgen.world.build_maze

Writes:
  storage/assets/hospital/matrix/{maze_meta_info.json, maze/*.csv, special_blocks/*.csv}
  web/world.json

Then loads the Maze and pathfinds Home -> reception -> triage -> OB exam,
printing each leg's length as a sanity check.
"""
from __future__ import annotations

from hgen.config import MAZE_NAME
from hgen.world.grid import (
    COLLISION_CHAR,
    SPAWN_NAME,
    write_assets,
    write_world_json,
)
from hgen.world.maze import Maze
from hgen.world.path_finder import path_finder


def _one_tile(maze: Maze, address: str) -> tuple[int, int]:
    """Return a representative tile for an address (min by (y, x) for stability)."""
    tiles = maze.address_tiles.get(address)
    if not tiles:
        raise KeyError(f"address not found in maze: {address!r}")
    return min(tiles, key=lambda t: (t[1], t[0]))


def self_test() -> None:
    """Pathfind Home -> reception -> triage -> OB exam and print leg lengths."""
    maze = Maze(MAZE_NAME)

    legs = [
        ("Home", f"<spawn_loc>{SPAWN_NAME}"),
        ("reception", "General Hospital:Admissions:reception:reception desk"),
        ("triage", "General Hospital:Triage:triage bay 1:vitals station"),
        ("OB exam", "General Hospital:OB / Prenatal Clinic:exam room:exam table"),
    ]
    waypoints = [(name, _one_tile(maze, addr)) for name, addr in legs]

    print(f"Maze '{maze.maze_name}': {maze.maze_width}x{maze.maze_height}, "
          f"tile {maze.sq_tile_size}px, world {maze.world_name!r}")
    print("Waypoints:", {n: t for n, t in waypoints})

    total = 0
    for (a_name, a_tile), (b_name, b_tile) in zip(waypoints, waypoints[1:]):
        path = path_finder(maze.collision_maze, a_tile, b_tile, COLLISION_CHAR)
        assert path, f"NO PATH {a_name} {a_tile} -> {b_name} {b_tile}"
        assert path[0] == a_tile and path[-1] == b_tile
        total += len(path) - 1
        print(f"  {a_name} {a_tile} -> {b_name} {b_tile}: "
              f"{len(path)} tiles ({len(path) - 1} steps)")
    print(f"Total journey: {total} steps")


def main() -> None:
    mdir = write_assets(MAZE_NAME)
    wjson = write_world_json()
    print(f"Wrote matrices to {mdir}")
    print(f"Wrote renderer floor-plan to {wjson}")
    self_test()


if __name__ == "__main__":
    main()
