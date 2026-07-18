"""Top-level orchestrator: seed -> maze -> direct -> compress -> replay.

Runs the whole Hospital Generative Agents vertical slice end to end and leaves
``web/master_movement.json``, ``web/meta.json``, and ``web/world.json`` ready for
the minimal grid renderer. Completes in canned LLM mode (no API key):

    cd hospital_gen_agent
    HGEN_LLM_MODE=canned .venv/bin/python run_slice.py

Then serve the web dir and open hospital.html:

    .venv/bin/python -m http.server 8000 --directory web
    # open http://localhost:8000/hospital.html
"""
from __future__ import annotations

from hgen.config import HG, REPO, WEB
from hgen.world.grid import matrix_dir


def _ensure_maze() -> None:
    """Build the maze matrices + web/world.json if they are missing."""
    mdir = matrix_dir()
    world_json = WEB / "world.json"
    need = (not (mdir / "maze_meta_info.json").exists()
            or not (mdir / "maze" / "collision_maze.csv").exists()
            or not world_json.exists())
    if need:
        from hgen.world.grid import write_assets, write_world_json
        write_assets()
        write_world_json()
        print("[maze] built matrices + web/world.json")
    else:
        print("[maze] matrices + web/world.json present")


def main() -> None:
    print("=== Hospital Generative Agents — vertical slice bake ===")

    # 1. Seeding: dataset -> bootstrap files.
    print("\n[1/4] Seeding personas from the dataset ...")
    from hgen.seeding.build import main as seed_main
    seed_main()

    # 2. Maze matrices + renderer floor plan.
    print("\n[2/4] Ensuring maze assets ...")
    _ensure_maze()

    # 3. Director: bake per-step movement.
    print("\n[3/4] Baking movement (director) ...")
    from hgen.cognition.director import run_director
    n = run_director()
    print(f"[director] wrote {n} movement frames")

    # 4. Compress to the replay bundle.
    print("\n[4/4] Compressing to the replay bundle ...")
    from hgen.compress import compress
    out = compress()
    print(f"[compress] wrote {out}")

    print("\n=== Done. To view the replay: ===")
    print(f"  cd {HG}")
    print(f"  {REPO / '.venv' / 'bin' / 'python'} -m http.server 8000 --directory web")
    print("  open http://localhost:8000/hospital.html")


if __name__ == "__main__":
    main()
