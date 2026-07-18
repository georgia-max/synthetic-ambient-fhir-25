"""The Maze: loads the generated matrices into an addressable tile grid.

Mirrors the original Stanford ``Maze`` logic and public surface (access_tile,
get_tile_path, get_nearby_tiles, address_tiles, collision lookup, tile event
mutation) but is self-contained: it reads the CSV matrices written by
``grid.write_assets`` and needs no Django/Tiled coupling.

Every tile carries world/sector/arena/game_object/collision/events, and the
reverse index ``address_tiles`` maps a colon address string to the set of
(x, y) tiles that satisfy it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from hgen.config import MAZE_NAME
from hgen.world.grid import COLLISION_CHAR, matrix_dir


def _read_row_matrix(path: Path, width: int, height: int) -> list[list[str]]:
    """Read a single-row CSV and reshape to a [y][x] matrix of strings."""
    raw = [p.strip() for p in path.read_text(encoding="utf-8").strip().split(",")]
    return [raw[i * width:(i + 1) * width] for i in range(height)]


def _read_blocks(path: Path) -> dict[str, str]:
    """Read a special_blocks CSV to {color_id: last_field_name}."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        out[parts[0]] = parts[-1]
    return out


class Maze:
    """The simulated hospital map as a 2-D matrix of tile dictionaries."""

    def __init__(self, maze_name: str = MAZE_NAME, matrix_root: Optional[Path] = None):
        self.maze_name = maze_name
        mdir = Path(matrix_root) if matrix_root else matrix_dir(maze_name)

        meta = json.load(open(mdir / "maze_meta_info.json", encoding="utf-8"))
        self.maze_width = int(meta["maze_width"])
        self.maze_height = int(meta["maze_height"])
        self.sq_tile_size = int(meta["sq_tile_size"])
        self.world_name = meta.get("world_name", "")
        self.special_constraint = meta.get("special_constraint", "")

        # Special blocks: color-id -> name.
        blocks = mdir / "special_blocks"
        wb_rows = [
            [p.strip() for p in ln.split(",")]
            for ln in (blocks / "world_blocks.csv").read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        self.world_block = wb_rows[0][-1]
        sb = _read_blocks(blocks / "sector_blocks.csv")
        ab = _read_blocks(blocks / "arena_blocks.csv")
        gob = _read_blocks(blocks / "game_object_blocks.csv")
        slb = _read_blocks(blocks / "spawning_location_blocks.csv")

        # Matrices ([y][x]).
        maze = mdir / "maze"
        w, h = self.maze_width, self.maze_height
        self.collision_maze = _read_row_matrix(maze / "collision_maze.csv", w, h)
        sector_maze = _read_row_matrix(maze / "sector_maze.csv", w, h)
        arena_maze = _read_row_matrix(maze / "arena_maze.csv", w, h)
        game_object_maze = _read_row_matrix(maze / "game_object_maze.csv", w, h)
        spawning_maze = _read_row_matrix(maze / "spawning_location_maze.csv", w, h)

        # Build the tile dictionaries.
        self.tiles: list[list[dict]] = []
        for y in range(h):
            row = []
            for x in range(w):
                td = {
                    "world": self.world_block,
                    "sector": sb.get(sector_maze[y][x], ""),
                    "arena": ab.get(arena_maze[y][x], ""),
                    "game_object": gob.get(game_object_maze[y][x], ""),
                    "spawning_location": slb.get(spawning_maze[y][x], ""),
                    "collision": self.collision_maze[y][x] != "0",
                    "events": set(),
                }
                row.append(td)
            self.tiles.append(row)

        # Each game object seeds a default (idle) event on its tile.
        for y in range(h):
            for x in range(w):
                if self.tiles[y][x]["game_object"]:
                    obj_name = ":".join([
                        self.tiles[y][x]["world"],
                        self.tiles[y][x]["sector"],
                        self.tiles[y][x]["arena"],
                        self.tiles[y][x]["game_object"],
                    ])
                    self.tiles[y][x]["events"].add((obj_name, None, None, None))

        # Reverse index: address string -> set of (x, y) tiles.
        self.address_tiles: dict[str, set[tuple[int, int]]] = {}
        for y in range(h):
            for x in range(w):
                t = self.tiles[y][x]
                addresses = []
                if t["sector"]:
                    addresses.append(f'{t["world"]}:{t["sector"]}')
                if t["arena"]:
                    addresses.append(f'{t["world"]}:{t["sector"]}:{t["arena"]}')
                if t["game_object"]:
                    addresses.append(
                        f'{t["world"]}:{t["sector"]}:{t["arena"]}:{t["game_object"]}'
                    )
                if t["spawning_location"]:
                    addresses.append(f'<spawn_loc>{t["spawning_location"]}')
                for add in addresses:
                    self.address_tiles.setdefault(add, set()).add((x, y))

    # ----------------------------------------------------------------- #
    # Access                                                            #
    # ----------------------------------------------------------------- #
    def access_tile(self, tile: tuple[int, int]) -> dict:
        """Return the tile-detail dict at (x, y)."""
        x, y = tile
        return self.tiles[y][x]

    def collision(self, tile: tuple[int, int]) -> bool:
        """Return True if (x, y) is a collision (wall) tile."""
        x, y = tile
        return self.tiles[y][x]["collision"]

    def turn_coordinate_to_tile(self, px: tuple[int, int]) -> tuple[int, int]:
        """Convert a pixel coordinate to a tile coordinate."""
        import math
        return (math.ceil(px[0] / self.sq_tile_size),
                math.ceil(px[1] / self.sq_tile_size))

    def get_tile_path(self, tile: tuple[int, int], level: str) -> str:
        """Rebuild the colon address of a tile down to ``level``.

        ``level`` is one of world / sector / arena / game_object.
        """
        x, y = tile
        t = self.tiles[y][x]
        path = f"{t['world']}"
        if level == "world":
            return path
        path += f":{t['sector']}"
        if level == "sector":
            return path
        path += f":{t['arena']}"
        if level == "arena":
            return path
        path += f":{t['game_object']}"
        return path

    def get_nearby_tiles(self, tile: tuple[int, int], vision_r: int) -> list[tuple[int, int]]:
        """Return the tiles inside a square vision window around ``tile``, clamped."""
        x, y = tile
        left = max(0, x - vision_r)
        right = min(self.maze_width - 1, x + vision_r + 1)
        bottom = min(self.maze_height - 1, y + vision_r + 1)
        top = max(0, y - vision_r)
        nearby = []
        for i in range(left, right):
            for j in range(top, bottom):
                nearby.append((i, j))
        return nearby

    # ----------------------------------------------------------------- #
    # Tile event mutation                                               #
    # ----------------------------------------------------------------- #
    def add_event_from_tile(self, curr_event: tuple, tile: tuple[int, int]) -> None:
        """Add an event triple/quad to a tile."""
        self.tiles[tile[1]][tile[0]]["events"].add(curr_event)

    def remove_event_from_tile(self, curr_event: tuple, tile: tuple[int, int]) -> None:
        """Remove an event from a tile."""
        events = self.tiles[tile[1]][tile[0]]["events"]
        events.discard(curr_event)

    def turn_event_from_tile_idle(self, curr_event: tuple, tile: tuple[int, int]) -> None:
        """Reset a tile event to its idle (object, None, None, None) form."""
        events = self.tiles[tile[1]][tile[0]]["events"]
        for event in list(events):
            if event == curr_event:
                events.remove(event)
                events.add((event[0], None, None, None))

    def remove_subject_events_from_tile(self, subject: str, tile: tuple[int, int]) -> None:
        """Remove all events with the given subject from a tile."""
        events = self.tiles[tile[1]][tile[0]]["events"]
        for event in list(events):
            if event[0] == subject:
                events.remove(event)

    # ----------------------------------------------------------------- #
    # Pathfinding convenience                                           #
    # ----------------------------------------------------------------- #
    def get_path(self, start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
        """4-connected BFS path from ``start`` to ``end`` (inclusive)."""
        from hgen.world.path_finder import path_finder
        return path_finder(self.collision_maze, start, end, COLLISION_CHAR)
