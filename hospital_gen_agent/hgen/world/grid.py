"""The 28x14 hospital grid spec + matrix/world.json generation.

Defines the logical maze for the vertical slice: rooms (sector/arena),
game_objects, the spawn tile, the corridor spine, and the connector doors.
Tile coordinates and colon addresses match SUBPLAN_B section 2 exactly so that
seeding spatial addresses and director targets line up.

Address language: ``world:sector:arena:game_object`` (same as the original).
The five single-row CSV matrices (collision, sector, arena, game_object,
spawning_location) plus special_blocks CSVs are the backend contract; world.json
is the renderer floor-plan.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from hgen.config import STORAGE, WEB, WORLD_NAME, MAZE_NAME

# --------------------------------------------------------------------------- #
# Grid constants                                                              #
# --------------------------------------------------------------------------- #
WIDTH = 28
HEIGHT = 14
TILE_SIZE = 32
COLLISION_CHAR = "1"  # non-"0" marks a wall in the collision matrix
WORLD_ID = "1"
SPAWN_NAME = "Home"
SPAWN_ID = "30"
SPAWN_TILE = (2, 13)

# The corridor spine (row 7, open x=2..26) and the vertical connector doors that
# join each room to the spine. Everything not carved below is a collision wall.
CORRIDOR_ROW = 7
CORRIDOR_X = range(2, 27)  # x = 2..26 inclusive
DOOR_TILES = [(4, 6), (13, 6), (23, 6), (4, 8), (23, 8)]


@dataclass
class Obj:
    """A game_object placed at a single tile."""

    name: str
    x: int
    y: int
    obj_id: str


@dataclass
class Room:
    """A sector+arena room occupying an inclusive tile rectangle."""

    key: str
    sector: str
    arena: str
    label: str
    color: str
    rect: tuple[int, int, int, int]  # (x0, y0, x1, y1) inclusive interior
    sector_id: str
    arena_id: str
    objects: list[Obj] = field(default_factory=list)

    def tiles(self):
        """Yield every (x, y) tile inside this room's interior rectangle."""
        x0, y0, x1, y1 = self.rect
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                yield (x, y)


# --------------------------------------------------------------------------- #
# The floor plan (tiles + addresses match SUBPLAN_B section 2)                 #
# --------------------------------------------------------------------------- #
ROOMS: list[Room] = [
    Room(
        "admissions", "Admissions", "reception", "Admissions", "#5b8def",
        (1, 1, 11, 5), "2", "10",
        [Obj("reception desk", 4, 3, "20"), Obj("check-in kiosk", 6, 3, "21")],
    ),
    Room(
        "triage", "Triage", "triage bay 1", "Triage", "#3fb98f",
        (13, 1, 20, 5), "3", "11",
        [Obj("vitals station", 13, 3, "22")],
    ),
    Room(
        "ob", "OB / Prenatal Clinic", "exam room", "OB / Prenatal", "#e86aa6",
        (22, 1, 26, 5), "4", "12",
        [Obj("exam table", 23, 3, "23"), Obj("ultrasound machine", 25, 4, "24")],
    ),
    Room(
        "waiting", "Waiting Room", "waiting area", "Waiting Room", "#e0a53f",
        (1, 9, 20, 12), "5", "13",
        [Obj("waiting chairs", 4, 10, "25"),
         Obj("waiting chairs", 5, 10, "25"),
         Obj("waiting chairs", 6, 10, "25")],
    ),
    Room(
        "discharge", "Discharge", "discharge desk", "Discharge", "#9b6ae8",
        (22, 9, 26, 12), "6", "14",
        [Obj("exit", 23, 10, "26")],
    ),
]


# --------------------------------------------------------------------------- #
# Walkability + matrices                                                       #
# --------------------------------------------------------------------------- #
def walkable_tiles() -> set[tuple[int, int]]:
    """Return every non-collision tile: room interiors + corridor + doors + spawn."""
    walk: set[tuple[int, int]] = set()
    for room in ROOMS:
        walk.update(room.tiles())
    for x in CORRIDOR_X:
        walk.add((x, CORRIDOR_ROW))
    walk.update(DOOR_TILES)
    walk.add(SPAWN_TILE)
    return walk


def _blank_grid() -> list[list[str]]:
    return [["0" for _ in range(WIDTH)] for _ in range(HEIGHT)]


def build_matrices() -> dict[str, list[list[str]]]:
    """Build the five 2D matrices ([y][x]) of color-id strings."""
    walk = walkable_tiles()
    collision = _blank_grid()
    sector = _blank_grid()
    arena = _blank_grid()
    game_object = _blank_grid()
    spawning = _blank_grid()

    # Collision: wall everywhere that is not walkable.
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if (x, y) not in walk:
                collision[y][x] = COLLISION_CHAR

    # Sector + arena fill each room rectangle; objects mark single tiles.
    for room in ROOMS:
        for (x, y) in room.tiles():
            sector[y][x] = room.sector_id
            arena[y][x] = room.arena_id
        for obj in room.objects:
            game_object[obj.y][obj.x] = obj.obj_id

    sx, sy = SPAWN_TILE
    spawning[sy][sx] = SPAWN_ID

    return {
        "collision": collision,
        "sector": sector,
        "arena": arena,
        "game_object": game_object,
        "spawning_location": spawning,
    }


def _flatten(matrix: list[list[str]]) -> str:
    """Row-major single-row CSV, matching the original single-row export."""
    return ", ".join(matrix[y][x] for y in range(HEIGHT) for x in range(WIDTH))


# --------------------------------------------------------------------------- #
# special_blocks CSV bodies                                                    #
# --------------------------------------------------------------------------- #
def special_blocks() -> dict[str, str]:
    """Return {filename: csv_text} for the special_blocks folder."""
    world = f"{WORLD_ID}, {WORLD_NAME}"

    sectors = [f"{r.sector_id}, {WORLD_NAME}, {r.sector}" for r in ROOMS]

    arenas = [f"{r.arena_id}, {WORLD_NAME}, {r.sector}, {r.arena}" for r in ROOMS]

    objects: list[str] = []
    seen_obj: set[str] = set()
    for r in ROOMS:
        for o in r.objects:
            if o.obj_id in seen_obj:
                continue
            seen_obj.add(o.obj_id)
            objects.append(f"{o.obj_id}, {WORLD_NAME}, {r.sector}, {r.arena}, {o.name}")

    spawns = [f"{SPAWN_ID}, {WORLD_NAME}, {SPAWN_NAME}"]

    return {
        "world_blocks.csv": world + "\n",
        "sector_blocks.csv": "\n".join(sectors) + "\n",
        "arena_blocks.csv": "\n".join(arenas) + "\n",
        "game_object_blocks.csv": "\n".join(objects) + "\n",
        "spawning_location_blocks.csv": "\n".join(spawns) + "\n",
    }


def meta_info() -> dict:
    """maze_meta_info.json contents."""
    return {
        "world_name": WORLD_NAME,
        "maze_width": WIDTH,
        "maze_height": HEIGHT,
        "sq_tile_size": TILE_SIZE,
        "special_constraint": "",
    }


# --------------------------------------------------------------------------- #
# Renderer world.json                                                          #
# --------------------------------------------------------------------------- #
def world_json() -> dict:
    """Floor-plan spec for the minimal grid renderer."""
    rooms = []
    for r in ROOMS:
        x0, y0, x1, y1 = r.rect
        rooms.append({
            "id": r.key,
            "label": r.label,
            "x": x0,
            "y": y0,
            "w": x1 - x0 + 1,
            "h": y1 - y0 + 1,
            "color": r.color,
        })

    objects = []
    for r in ROOMS:
        for o in r.objects:
            objects.append({"label": o.name, "x": o.x, "y": o.y})
    objects.append({"label": SPAWN_NAME, "x": SPAWN_TILE[0], "y": SPAWN_TILE[1]})

    return {
        "tile_size": TILE_SIZE,
        "width": WIDTH,
        "height": HEIGHT,
        "rooms": rooms,
        "objects": objects,
    }


# --------------------------------------------------------------------------- #
# Writers                                                                      #
# --------------------------------------------------------------------------- #
def matrix_dir(maze_name: str = MAZE_NAME) -> Path:
    """Path to the matrix folder for ``maze_name`` under storage/assets."""
    return STORAGE / "assets" / maze_name / "matrix"


def write_assets(maze_name: str = MAZE_NAME) -> Path:
    """Write maze_meta_info.json, the five matrix CSVs, and special_blocks CSVs."""
    import json

    mdir = matrix_dir(maze_name)
    maze_folder = mdir / "maze"
    blocks_folder = mdir / "special_blocks"
    maze_folder.mkdir(parents=True, exist_ok=True)
    blocks_folder.mkdir(parents=True, exist_ok=True)

    with open(mdir / "maze_meta_info.json", "w", encoding="utf-8") as f:
        json.dump(meta_info(), f, indent=2)

    matrices = build_matrices()
    csv_names = {
        "collision": "collision_maze.csv",
        "sector": "sector_maze.csv",
        "arena": "arena_maze.csv",
        "game_object": "game_object_maze.csv",
        "spawning_location": "spawning_location_maze.csv",
    }
    for key, fname in csv_names.items():
        (maze_folder / fname).write_text(_flatten(matrices[key]) + "\n", encoding="utf-8")

    for fname, body in special_blocks().items():
        (blocks_folder / fname).write_text(body, encoding="utf-8")

    return mdir


def write_world_json(path: Optional[Path] = None) -> Path:
    """Write the renderer floor-plan to web/world.json."""
    import json

    path = Path(path) if path else (WEB / "world.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(world_json(), f, indent=2)
    return path
