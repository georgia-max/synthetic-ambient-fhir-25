"""The hospital grid spec + matrix/world.json generation.

Defines the logical maze: every clinical department the 25-patient dataset uses
(General Medicine, OB / Prenatal Clinic, Inpatient Ward, Isolation Unit,
Hospice / Palliative) plus the shared sectors every patient touches (Admissions,
Triage, Waiting Room, Discharge). Each clinical department carries the exam
table / bed a doctor sits at. Rooms line a single horizontal corridor spine so
BFS pathfinding reaches every department from the Home spawn and on to Discharge.

Layout (WIDTH x HEIGHT tiles, corridor on row 8)::

      TOP ROOMS  (y 1..6)   Admissions  Triage  General Medicine  OB  Inpatient
      corridor   (row 8, x 1..40)  ===================================
      BOTTOM ROOMS (y 10..13) Waiting  Isolation  Hospice  Discharge

Top rooms join the spine through a door on row 7; bottom rooms through a door on
row 9. Home is the spawn tile on the corridor's left end.

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
WIDTH = 42
HEIGHT = 15
TILE_SIZE = 32
COLLISION_CHAR = "1"  # non-"0" marks a wall in the collision matrix
WORLD_ID = "1"
SPAWN_NAME = "Home"
SPAWN_ID = "30"
SPAWN_TILE = (1, 8)

# The corridor spine (row 8, open x=1..40) and the door tiles that join each room
# to the spine (row 7 for the top row of rooms, row 9 for the bottom row).
# Everything not carved below is a collision wall.
CORRIDOR_ROW = 8
CORRIDOR_X = range(1, 41)  # x = 1..40 inclusive
DOOR_TILES = [
    # top-room doors (row 7)
    (4, 7), (12, 7), (22, 7), (31, 7), (38, 7),
    # bottom-room doors (row 9)
    (6, 9), (17, 9), (27, 9), (37, 9),
]


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
# The floor plan                                                              #
# --------------------------------------------------------------------------- #
# sector/arena/object NAMES here must match hgen.seeding.world (canonical tree +
# DEPARTMENT_EXAM) and the canonical addresses in hgen.cognition.modules.
ROOMS: list[Room] = [
    # --- top row of rooms (y 1..6, door on row 7) ---------------------------
    Room(
        "admissions", "Admissions", "reception", "Admissions", "#5b8def",
        (1, 1, 7, 6), "2", "20",
        [Obj("reception desk", 4, 3, "40"), Obj("check-in kiosk", 6, 3, "41")],
    ),
    Room(
        "triage", "Triage", "triage bay 1", "Triage", "#3fb98f",
        (9, 1, 16, 6), "3", "21",
        [Obj("vitals station", 12, 3, "42")],
    ),
    Room(
        "genmed", "General Medicine", "exam room", "General Medicine", "#6bd39a",
        (18, 1, 26, 6), "4", "22",
        [Obj("exam table", 22, 3, "43"), Obj("computer", 24, 3, "44")],
    ),
    Room(
        "ob", "OB / Prenatal Clinic", "exam room", "OB / Prenatal", "#e86aa6",
        (28, 1, 34, 6), "5", "23",
        [Obj("exam table", 31, 3, "45"), Obj("ultrasound machine", 33, 4, "46")],
    ),
    Room(
        "inpatient", "Inpatient Ward", "ward bay", "Inpatient Ward", "#c792ea",
        (36, 1, 40, 6), "6", "24",
        [Obj("ward bed", 38, 3, "47")],
    ),
    # --- bottom row of rooms (y 10..13, door on row 9) ----------------------
    Room(
        "waiting", "Waiting Room", "waiting area", "Waiting Room", "#e0a53f",
        (1, 10, 11, 13), "7", "25",
        [Obj("waiting chairs", 4, 11, "48"),
         Obj("waiting chairs", 5, 11, "48"),
         Obj("waiting chairs", 6, 11, "48")],
    ),
    Room(
        "isolation", "Isolation Unit", "isolation room", "Isolation Unit", "#ffcf5c",
        (13, 10, 21, 13), "8", "26",
        [Obj("isolation bed", 17, 11, "49"), Obj("PPE station", 19, 11, "50")],
    ),
    Room(
        "hospice", "Hospice / Palliative", "palliative room", "Hospice / Palliative",
        "#f06595", (23, 10, 32, 13), "9", "27",
        [Obj("palliative bed", 27, 11, "51"), Obj("family chairs", 29, 11, "52")],
    ),
    Room(
        "discharge", "Discharge", "discharge desk", "Discharge", "#9b6ae8",
        (34, 10, 40, 13), "10", "28",
        [Obj("exit", 37, 11, "53")],
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
def _obj_type(name: str) -> str:
    """Map a game_object name to a renderer icon type (keeps the floor plan
    legible without hard-coding coordinates in the frontend)."""
    n = name.lower()
    if "bed" in n:
        return "bed"
    if "desk" in n:
        return "desk"
    if "kiosk" in n:
        return "kiosk"
    if "vitals" in n:
        return "vitals"
    if "exam table" in n:
        return "exam_table"
    if "computer" in n:
        return "computer"
    if "ultrasound" in n:
        return "ultrasound"
    if "chair" in n:
        return "chairs"
    if "ppe" in n:
        return "ppe"
    if "exit" in n:
        return "exit"
    return "generic"


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
            objects.append({"label": o.name, "x": o.x, "y": o.y,
                            "type": _obj_type(o.name)})
    objects.append({"label": SPAWN_NAME, "x": SPAWN_TILE[0], "y": SPAWN_TILE[1],
                    "type": "home"})

    # Circulation: the corridor spine + the door tiles that open onto it, so the
    # renderer can draw walls with real doorways instead of solid boxes.
    corridor = {"x": min(CORRIDOR_X), "y": CORRIDOR_ROW,
                "w": len(CORRIDOR_X), "h": 1}
    doors = [{"x": x, "y": y} for (x, y) in DOOR_TILES]

    return {
        "tile_size": TILE_SIZE,
        "width": WIDTH,
        "height": HEIGHT,
        "rooms": rooms,
        "corridor": corridor,
        "doors": doors,
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
