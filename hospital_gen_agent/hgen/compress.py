"""Compress per-step movement into the delta-encoded replay bundle.

Folds ``storage/<sim_code>/movement/<step>.json`` (0..N) into
``web/master_movement.json`` and copies ``meta.json`` to ``web/meta.json``.
Mirrors the original ``compress_sim_storage.py``: frame 0 carries every persona,
later frames carry only the personas whose ``movement`` / ``pronunciatio`` /
``description`` / ``chat`` changed since their last emitted entry. The renderer
(``web/hospital.html``) carries state forward to reconstruct each frame.

``web/world.json`` is produced by the world component and is left untouched.

Run (cwd = hospital_gen_agent):
    python -m hgen.compress
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from hgen.config import STORAGE, WEB
from hgen.contracts import read_json, read_meta, write_json


def _movement_steps(move_dir: Path) -> list[int]:
    """Return the sorted step numbers present in ``move_dir`` (0..N)."""
    steps = []
    for p in move_dir.glob("*.json"):
        try:
            steps.append(int(p.stem))
        except ValueError:
            continue
    return sorted(steps)


def compress(sim_code: str = "base_hospital",
             storage: Optional[Path] = None,
             web: Optional[Path] = None) -> Path:
    """Bake ``master_movement.json`` + ``meta.json`` into the web dir.

    Returns the path to the written ``master_movement.json``.
    """
    base = (Path(storage) if storage else STORAGE) / sim_code
    web_dir = Path(web) if web else WEB
    move_dir = base / "movement"
    meta_file = base / "reverie" / "meta.json"

    steps = _movement_steps(move_dir)
    if not steps:
        raise FileNotFoundError(f"no movement/<step>.json files in {move_dir}")

    persona_names = list(read_meta(meta_file)["persona_names"])

    master: dict[str, dict] = {}
    last: dict[str, dict] = {}
    for i in steps:
        frame = read_json(move_dir / f"{i}.json")["persona"]
        master[str(i)] = {}
        for p in persona_names:
            if p not in frame:
                continue
            entry = {
                "movement": frame[p]["movement"],
                "pronunciatio": frame[p]["pronunciatio"],
                "description": frame[p]["description"],
                "chat": frame[p].get("chat"),
            }
            if i == steps[0] or entry != last.get(p):
                master[str(i)][p] = entry
                last[p] = entry

    web_dir.mkdir(parents=True, exist_ok=True)
    out = web_dir / "master_movement.json"
    write_json(out, master)
    shutil.copyfile(meta_file, web_dir / "meta.json")
    return out


def main() -> None:
    out = compress()
    n_frames = len(read_json(out))
    print(f"Compressed {n_frames} frames -> {out}")
    print(f"Copied meta.json -> {WEB / 'meta.json'}")


if __name__ == "__main__":
    main()
