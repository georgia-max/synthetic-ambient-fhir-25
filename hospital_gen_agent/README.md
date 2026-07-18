# Hospital Generative Agents

A faithful reimplementation of Stanford's **generative_agents** (Smallville),
adapted to a hospital and driven by a synthetic FHIR dataset. Villagers become
patients and clinical staff; Smallville becomes a hospital. The 25 synthetic FHIR
encounters in `../dataset/synthetic-ambient-fhir-25.jsonl` are the knowledge the
agents hold about the hospital: they seed the world, each patient's chart, and the
staff's clinical knowledge.

See `CLAUDE.md` and `plans/` for the full port plan, seeding rules, and the
vertical-slice step script.

## What was built

A single **vertical slice**: hero patient **Clarence Reinger** (32F, prenatal
intake) walks the full care pathway while six other personas (spouse Marcus,
triage Nurse Reyes, OB Dr. Amari, clerk Rosa Diaz, and two background patients)
bring the hospital to life. The whole thing precomputes ("bakes") a replay bundle
that a minimal canvas renderer plays back deterministically.

- **`hgen/seeding/`** — dataset -> bootstrap. Turns the hero FHIR record into the
  Smallville persona layout (`scratch.json`, `spatial_memory.json`,
  `associative_memory/nodes.json`), derives the department map from `visit_type`,
  and loads staff clinical knowledge (vitals ranges, OB diagnoses) as memory nodes.
- **`hgen/cognition/`** — the ported cognitive architecture: `ConceptNode` /
  `Scratch` / `MemoryTree` structures and the `perceive -> retrieve -> plan ->
  reflect -> execute` module chain, same JSON contracts as the original.
- **`hgen/world/`** — the small logical maze (28x14), the five matrix CSVs, and a
  BFS pathfinder (`path_finder.py`), plus the renderer floor plan (`world.json`).
- **`hgen/llm/`** — the Anthropic (Claude-only) backend seam and prompt wrappers.
- **`hgen/cognition/director.py`** — owns the care-pathway schedule (the role
  `reverie.py` plays upstream), steps the cast through the visit using the real
  `perceive` + `execute` + pathfinder, injects the **verbatim** OB consult from
  the record transcript, and writes the two post-consult reflection thoughts.
- **`hgen/compress.py`** — delta-compresses per-step `movement/*.json` into
  `web/master_movement.json` (frame 0 full, later frames only changed personas).
- **`run_slice.py`** — the orchestrator: seed -> maze -> direct -> compress.
- **`web/`** — the minimal single-file canvas renderer (`hospital.html`) plus the
  three baked JSON files it consumes.

## Run

Use the repo virtualenv at `../.venv`. Do not `pip install` (the scaffold owns deps).

### Canned mode (default, no API key — deterministic)

```
cd hospital_gen_agent
HGEN_LLM_MODE=canned ../.venv/bin/python run_slice.py
```

This bakes `web/master_movement.json`, `web/meta.json`, and `web/world.json`
without touching the network. Every LLM call returns a deterministic per-prompt
stub, so re-bakes are byte-for-byte identical.

### Live mode (real Claude calls)

```
cd hospital_gen_agent
export ANTHROPIC_API_KEY=sk-ant-...
HGEN_LLM_MODE=live ../.venv/bin/python run_slice.py     # always call the API, refresh cache
HGEN_LLM_MODE=cache ../.venv/bin/python run_slice.py    # cache hit -> reuse, miss -> live call
```

Models: `claude-sonnet-5` for frequent cognition calls, `claude-opus-4-8` for the
reflection synthesis. Completions are cached under `hgen/.llm_cache/`. The OB
consult is always verbatim from the transcript (no model call) in every mode.

## View the demo

```
cd hospital_gen_agent
../.venv/bin/python -m http.server 8000 --directory web
# open http://localhost:8000/hospital.html
```

The renderer draws the labeled hospital grid, animates each persona tile-to-tile
from `master_movement.json`, shows the `pronunciatio` emoji over each head, the
`description` on hover/click, and the consult `chat` in a speech bubble.

## File / directory map

```
hospital_gen_agent/
├── run_slice.py                  orchestrator: seed -> maze -> direct -> compress
├── CLAUDE.md                     full port plan (locked decisions)
├── plans/
│   ├── SUBPLAN_A_seeding.md      dataset -> bootstrap rules
│   └── SUBPLAN_B_vertical_slice.md  cast, grid map, step script, acceptance criteria
├── hgen/                         the package
│   ├── config.py                 absolute paths, model ids, world constants
│   ├── contracts.py              movement / meta JSON contract helpers
│   ├── compress.py               movement/*.json -> web/master_movement.json (delta)
│   ├── seeding/                  dataset -> personas + world + staff knowledge
│   │   ├── build.py              seed entrypoint (python -m hgen.seeding.build)
│   │   ├── world.py  patients.py  staff.py  notes.py  names.py
│   ├── cognition/                ported generative-agents architecture
│   │   ├── memory.py             ConceptNode / Scratch / MemoryTree
│   │   ├── modules.py            perceive / retrieve / plan / reflect / execute
│   │   ├── persona.py            Persona.move chain
│   │   └── director.py           care-pathway schedule + verbatim consult + reflect
│   ├── world/                    maze + pathfinding + renderer floor plan
│   │   ├── grid.py  maze.py  build_maze.py  path_finder.py
│   └── llm/                      Claude-only backend
│       ├── claude_backend.py     Anthropic seam, 3 modes (canned/cache/live), cache
│       └── prompts.py            run_gpt_prompt_* wrappers
├── storage/
│   ├── base_hospital/
│   │   ├── meta.json
│   │   ├── personas/<Name>/bootstrap_memory/{scratch,spatial_memory,associative_memory/nodes}.json
│   │   └── movement/<step>.json  per-step backend output (baked)
│   └── assets/hospital/matrix/   maze_meta_info.json + 5 matrix CSVs
└── web/                          replay bundle + renderer
    ├── hospital.html             minimal canvas renderer
    ├── master_movement.json      delta-compressed replay (baked)
    ├── meta.json                 replay metadata (baked)
    └── world.json                renderer floor plan (baked)
```

Standalone entrypoints: `python -m hgen.seeding.build`,
`python -m hgen.cognition.director`, `python -m hgen.compress`.

## Known limitations (honest)

- **Scope is one vertical slice**, not a 25-agent hospital day. Only Clarence
  walks the full pathway; Nurse Reyes and Dr. Amari hold posts, Rosa and the two
  background patients sit/idle. Marcus is a follower sprite (one tile behind
  Clarence), not an independent cognition.
- **The director scripts the schedule.** The care-pathway ordering (arrive ->
  check in -> wait -> triage -> OB -> reflect -> discharge -> exit) is owned by
  `director.py`, standing in for the role `reverie.py` + first-day LLM planning
  play in the original. Movement *within* each beat is the real `perceive` +
  `execute` + BFS pathfinder.
- **Canned mode uses authored dialogue.** The check-in, triage banter, and
  background-patient lines are authored strings in the director that reflect the
  seeded staff knowledge (e.g. the nurse's vitals ranges) thematically; in canned
  mode they are not dynamically generated from memory. The OB consult is verbatim
  transcript by design in every mode. Live mode routes the surrounding beats
  through Claude, but the demo bundle shipped here is the canned bake.
- **Retrieval is keyword-only.** No embeddings; `get_embedding` is not wired for
  the slice (per the plan's default). Relevance recall is the keyword path.
- **Renderer is R2 (minimal grid).** No Phaser/Tiled tilemap; a lightweight
  labeled-room canvas. That is the locked renderer decision, not a regression.
- **Reflection depth is two thoughts.** After the consult, exactly two grounded
  reflection thoughts are written to Clarence (normal pregnancy; recurrent UTI
  surveillance), matching the note's two Assessment-and-Plan headings.
