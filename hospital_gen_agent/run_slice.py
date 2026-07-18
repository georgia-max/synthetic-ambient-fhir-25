"""Top-level orchestrator: seed -> maze -> direct -> compress -> replay.

Runs the whole Hospital Generative Agents bake end to end and leaves
``web/master_movement.json``, ``web/meta.json``, and ``web/world.json`` ready for
the minimal grid renderer. Completes in canned LLM mode (no API key):

    cd hospital_gen_agent
    HGEN_LLM_MODE=canned .venv/bin/python run_slice.py

Two director modes (select with ``HGEN_MODE``):

* ``autonomous`` (DEFAULT) — the full hospital: all 25 dataset patients, each
  routed to their real department, arriving staggered and walking their care
  pathway via the live cognition loop (Clarence's verbatim OB consult kept).
* ``scripted`` — the legacy hand-timed OB vertical slice (``director.py``); a
  fallback that expects the 7-persona cast.

Then serve the web dir and open hospital.html:

    .venv/bin/python -m http.server 8000 --directory web
    # open http://localhost:8000/hospital.html
"""
from __future__ import annotations

import os

from hgen.config import HG, REPO, WEB
from hgen.world.grid import matrix_dir


def _build_maze() -> None:
    """(Re)build the maze matrices + web/world.json from the current grid spec."""
    from hgen.world.grid import write_assets, write_world_json
    write_assets()
    write_world_json()
    print("[maze] built matrices + web/world.json")


def _mode() -> str:
    """Director mode from HGEN_MODE (default: autonomous full-hospital bake)."""
    mode = os.environ.get("HGEN_MODE", "autonomous").strip().lower()
    return mode if mode in {"autonomous", "scripted"} else "autonomous"


def main() -> None:
    mode = _mode()
    print(f"=== Hospital Generative Agents — bake (mode: {mode}) ===")

    # 1. Seeding: dataset -> bootstrap files.
    print("\n[1/4] Seeding personas from the dataset ...")
    from hgen.seeding.build import main as seed_main
    seed_main()

    # 2. Maze matrices + renderer floor plan (rebuilt from the grid spec).
    print("\n[2/4] Building maze assets ...")
    _build_maze()

    # 3. Director: bake per-step movement.
    print("\n[3/4] Baking movement (director) ...")
    if mode == "scripted":
        from hgen.cognition.director import run_director
        n = run_director()
    else:
        from hgen.cognition.autonomous import run_autonomous
        n = run_autonomous()
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
