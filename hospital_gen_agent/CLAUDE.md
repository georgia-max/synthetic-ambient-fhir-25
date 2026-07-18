# Hospital Generative Agents — Faithful Port Plan

Recreate **Generative Agents (Smallville, Stanford, arXiv 2304.03442)** for a
**hospital**, following the actual `../generative_agents-main/` code logic (not a
reimplementation from the paper). Villagers become **patients and clinical staff**;
Smallville becomes a **hospital**. The `../dataset/` (25 synthetic FHIR encounters)
is the **knowledge the agents have about the hospital**: it seeds the world, the
staff's clinical knowledge, and each patient's own chart and dialogue.

Ground rules for this effort:
- Keep the original cognitive architecture intact: same `move()` chain, same three
  memory structures, same maze addressing, same `movement`/`meta` replay contract.
- The `../sim/` SimPy folder is abandoned. Movement comes from agent cognition, not
  a discrete-event queue.
- This is a plan only. No code here.

---

## 0. Locked decisions

| # | Decision | Choice | Consequence |
|---|----------|--------|-------------|
| 1 | LLM backend | **Claude only** | `gpt_structure.py` calls swap to the Anthropic API; no OpenAI. `claude-sonnet-5` for frequent calls, `claude-opus-4-8` for the hard reflection. |
| 2 | Renderer | **Minimal grid (R2)** | Own lightweight canvas/grid reading `master_movement.json`. No Phaser, no Tiled map authoring. |
| 3 | Scope | **Single vertical slice** | One hero patient + triage nurse + dept doctor + a few background patients. Not a 25-agent day. |
| 4 | Consult dialogue | **Verbatim transcript** | The hero consult replays the real `transcript` as `chat`. No LLM call for the diagnosis scene. |

Everything below is written to these four choices.

**Subplans** (detailed specs):
- `plans/SUBPLAN_A_seeding.md` — exact dataset → bootstrap rules (world spec,
  patient/staff `scratch` + memory nodes, poignancy rubric, note parsing).
- `plans/SUBPLAN_B_vertical_slice.md` — the one-patient step script (cast, grid
  map with tile coords, `meta.json`, per-step timeline, acceptance criteria).

---

## 1. How the original actually works (the parts we preserve)

**One simulation step** (`reverie.py :: start_server`): the frontend writes each
agent's tile into `environment/<step>.json`; the backend reads it, runs every
agent's `Persona.move()`, writes each agent's decision into `movement/<step>.json`,
then advances `step` and `curr_time` by `sec_per_step`.

**`Persona.move(maze, personas, curr_tile, curr_time)`** runs the chain, in order:

```
perceive(maze) ─> retrieve(perceived) ─> plan(...) ─> reflect() ─> execute(...)
   |                  |                     |            |             |
 nearby tiles     keyword +            daily plan +   convo->       A* path,
 & events ->      embedding recall     action addr    thoughts,     returns
 ConceptNodes     of memories          + reactions    insights      (next_tile,
 into a_mem                            (LLM calls)    (LLM calls)    emoji, desc)
```

**Three memory structures per agent:**
- `scratch` — identity (name, age, `innate`/`learned`/`currently`/`lifestyle`),
  the daily schedule, and the current action (`act_address`, `act_description`,
  `act_pronunciatio` emoji, `act_event` triple, chat state).
- `associative_memory` — the memory stream of `ConceptNode`s (type `event` /
  `thought` / `chat`), each an SPO triple + description + embedding + poignancy
  (1-10) + keywords + evidence links. Newest-first; keyword and embedding indexed.
- `spatial_memory` — a nested tree `world -> sector -> arena -> [game_objects]`,
  grown as the agent perceives new tiles.

**The maze** addresses every tile as `world:sector:arena:game_object`. Planning
LLM calls are constrained to pick locations that exist in the agent's spatial
memory. Assets: `maze_meta_info.json`, five single-row matrix CSVs (collision,
sector, arena, game_object, spawning_location), five `special_blocks` CSVs mapping
color ids to names, and a Tiled tilemap JSON for the visuals.

**Retrieval scoring** (`new_retrieve`): normalized recency (`0.99^age`),
importance (poignancy), relevance (cosine to a focal-point embedding), combined
`recency*0.5 + relevance*3 + importance*2`, top-N.

**Reflection** fires when accumulated poignancy crosses a threshold; it asks the
LLM for focal questions, retrieves, and synthesizes higher-level `thought` nodes.

**Replay** (`templates/demo`): the frontend animates `master_movement.json`
(`{step: {agent: {movement:[x,y], pronunciatio, description, chat}}}`) + `meta.json`
frame by frame. `compress_sim_storage.py` bakes per-step `movement/*.json` into the
delta-compressed `master_movement.json`.

---

## 2. Domain mapping: Smallville -> Hospital

| Original | Hospital | Seeded from |
|----------|----------|-------------|
| Villager persona | **Patient agent** | one dataset record |
| (n/a) | **Staff agents**: reception clerk, triage nurse, dept doctors, lab tech, pharmacist | authored + dataset aggregates |
| `world` | "General Hospital" | one world |
| `sector` (Hobbs Cafe) | **Department** (Triage, OB Clinic, ...) | `visit_type` -> department |
| `arena` (cafe) | **Room** (triage bay, exam room, ward bay) | authored |
| `game_object` (stove) | bed, exam table, vitals station, reception desk, chair | authored |
| daily schedule | **care pathway** (arrive -> reception -> triage -> dept -> consult -> discharge) | patient's plan |
| task decomposition | breaking "get triaged" into vitals, history, acuity | LLM, same code |
| action -> sector/arena/object LLM calls | "get vitals" -> `Triage:bay 1:vitals station` | same code, hospital spatial memory |
| `decide_to_talk` reaction | patient <-> nurse / patient <-> doctor consult | same code |
| conversation (`agent_chat_v2`) | **intake interview, doctor consult** | `transcript` grounds it |
| convo -> thoughts (reflect) | patient learns the diagnosis; doctor records it | `note` grounds it |
| `pronunciatio` emoji | 🤒 🤰 🩺 💉 🧪 🛏️ 💊 ✅ ⌛ 💬 | LLM, same call |
| `description` "sleeping @ ..." | "being triaged @ General Hospital:Triage:bay 1" | same format |

### Departments derived from the dataset

`visit_type` counts (25 records) map to sectors, so the floor plan reflects the
real case mix:

```
visit_type                                    department (sector)        n
General examination / Encounter for check up  General Medicine           15
Prenatal initial visit                        OB / Prenatal Clinic        4
Hospital admission (procedure)                Inpatient Ward              3
Admission to hospice                          Hospice / Palliative        2
Hospital admission for isolation              Isolation Unit              1
```

Plus shared sectors every patient touches: **Admissions/Reception**, **Waiting
Room**, **Triage**, **Diagnostics/Lab** (from Observation + DiagnosticReport
resources), **Pharmacy** (from MedicationRequest), **Discharge**.

---

## 3. The hospital world model

Same `world:sector:arena:game_object` hierarchy. Example spatial-memory tree an
OB doctor would hold:

```
General Hospital
├── Admissions
│   └── reception           [reception desk, waiting chairs, check-in kiosk]
├── Triage
│   ├── triage bay 1        [vitals station, exam stool, computer]
│   └── triage bay 2        [vitals station, exam stool, computer]
├── General Medicine
│   ├── exam room 1..4       [exam table, computer, sink, blood-pressure cuff]
│   └── nurse station        [computer, medication cart]
├── OB / Prenatal Clinic
│   ├── ultrasound room      [ultrasound machine, exam table]
│   └── exam room            [exam table, doppler, computer]
├── Inpatient Ward          [ward bed 1..6, nurse station, monitor]
├── Isolation Unit          [isolation bed, PPE station, monitor]
├── Hospice / Palliative    [palliative bed, family chairs, comfort cart]
├── Diagnostics / Lab       [blood draw chair, analyzer, imaging table]
├── Pharmacy                [pharmacy counter, medication shelves]
└── Discharge               [discharge desk, exit]
```

Room-level `game_object`s are the LLM's action targets, exactly like `stove` or
`bed` in the original.

---

## 4. Agents seeded from the dataset

### 4a. Patient personas (one per record, 25 total)

Bootstrap files mirror the original persona layout
(`personas/<Name>/bootstrap_memory/{scratch.json, spatial_memory.json,
associative_memory/*}`), filled from the record.

**`scratch.json`** grounded example (record: 32F prenatal intake):

```
name         : synthetic name from Patient.name  (e.g. "Maria Alvarez")
first/last   : split of that name
age          : from birthDate vs encounter date  (32)
innate       : light traits (optional; synthesize or leave generic)
learned      : chart summary from longitudinal_summary.condition_labels
               "history of anemia; first pregnancy; ..."
currently    : reason for visit from visit_title
               "here for an initial prenatal evaluation"
lifestyle    : social-determinant conditions if present (stress, social isolation)
living_area  : "Home"  (spawns outside, arrives at Admissions)
daily_plan_req: "Go to the hospital for a prenatal intake, check in, get triaged,
                see the OB, get a plan, go home."
```

**`associative_memory`** seed nodes (become the patient's recallable memories):
- One `thought` per active `condition_label`: `(name, has, <condition>)`,
  poignancy scaled by clinical weight (chronic/serious higher).
- One `thought` for the chief complaint from `visit_title`, poignancy ~6.
- `chat`/`event` nodes from the **transcript**: the patient's own account of
  symptoms, extracted from `PT:` turns. This is what the patient "says" in the
  intake and consult.
- The `note` (diagnosis + plan) is **not** given to the patient up front. It is
  the outcome the consult should reach (see 4c and 6).

**`spatial_memory`**: patient starts knowing only Admissions, Waiting Room, and
Triage; learns the rest by perceiving as they walk, like villagers.

### 4b. Staff personas (authored, dataset-informed)

Reception clerk, 2 triage nurses, one doctor per department (GP, OB,
hospitalist, palliative), lab tech, pharmacist. Their `scratch.currently` is "on
shift in <department>." Their power comes from **dataset-aggregated clinical
knowledge** loaded into associative memory (4c).

### 4c. The dataset as hospital knowledge (the core of this task)

A preprocessing pass turns the 25 records into three knowledge products. This is
the literal reading of "use the dataset as knowledge you know about the hospital."

```
                 ┌──────────────── dataset/ (25 FHIR encounters) ───────────────┐
                 │  patient_context · encounter_fhir · transcript · note · AVS   │
                 └───────────────┬───────────────┬───────────────┬───────────────┘
                                 │               │               │
             per-record          │        aggregate by dept      │  aggregate global
                 v               │               v               │        v
        Patient persona     World/dept spec   Staff clinical    Hospital semantic
        (scratch + a_mem +   (sectors from     memory (a_mem):   memory shared by
         transcript chat)    visit_type;       common conditions staff: top diagnoses,
                             lab from Obs;      per dept, typical  typical vitals ranges
                             pharmacy from      observations,      (from Observation
                             MedicationRequest) procedures/tests   values), procedures
```

Concretely, staff memory nodes are synthesized from aggregates:
- **Triage nurse** knows vital-sign patterns from `Observation` codes + values
  across records (heart rate, BP, BMI ranges), so triage dialogue is realistic.
- **Each doctor** knows the common conditions and diagnoses for their department
  (top `condition_labels` and note diagnoses filtered by `visit_type`).
- **Lab tech** knows the tests that occur (`DiagnosticReport` + `Observation`
  panels). **Pharmacist** knows common meds (`MedicationRequest`).
These load as `thought` nodes with sensible poignancy so retrieval surfaces them
during consults.

---

## 5. The cognitive loop, readapted (same code paths)

Each stage keeps its original function and data flow; only the domain content
changes.

- **perceive**: agents notice nearby agents and room objects and their events
  ("triage bay 1 is occupied", "Dr. Okafor is idle", "patient looks unwell").
  Same `vision_r` window, same poignancy scoring.
- **retrieve**: keyword recall for reactions, embedding-scored recall for
  planning/consults. Medical memories dominate what surfaces.
- **plan**:
  - The daily schedule becomes the **care pathway**. First-day planning yields
    the broad strokes (check in, wait, triage, see doctor, discharge); task
    decomposition breaks "get triaged" into vitals + history + acuity, using the
    same `task_decomp` LLM call.
  - Action-location resolution (`generate_action_sector/arena/game_object`) routes
    the patient to the correct department by `visit_type` and to a concrete object
    (vitals station, exam table), constrained by spatial memory.
  - Reactions: when a patient and a nurse/doctor are co-located and idle,
    `decide_to_talk` opens a conversation.
- **converse**: the intake interview and doctor consult. `agent_chat_v2` builds
  each utterance from retrieved memories; we bias retrieval so the patient's real
  transcript lines and the doctor's dataset knowledge surface (see 6).
- **reflect**: after the consult, `planning_thought_on_convo` and
  `memo_on_convo` write new thoughts: the patient internalizes the diagnosis and
  plan; the doctor records the assessment. Same code, medical content.
- **execute**: BFS pathfinding to the target tile; returns `(next_tile, emoji,
  description)`. Unchanged.

---

## 6. Dialogue grounding (the trick that makes it real and cheap)

The dataset already contains the real clinician-patient `transcript` and the
`note` (diagnosis + plan).

**Locked: verbatim transcript for the hero consult.** When the patient and the
department doctor open a conversation, `chat` is populated directly from the real
`transcript` turns (`DR:`/`PT:` lines), paced across steps like a normal
conversation. The clinical substance is exactly the dataset, there is no model
call for the highest-stakes scene, and it cannot drift or stall on camera.

The LLM still drives everything around the consult: triage banter, `decide_to_talk`
reactions, action-location planning, and the post-consult reflection where the
patient internalizes the diagnosis (the `note` seeds that reflection). So the
signature generative-agents behavior stays; only the consult content is fixed to
the real transcript.

---

## 7. Data contracts (reused verbatim, hospital content)

`meta.json`
```json
{ "fork_sim_code": "base_hospital", "start_date": "March 21, 2026",
  "curr_time": "March 21, 2026, 08:00:00", "sec_per_step": 10,
  "maze_name": "hospital",
  "persona_names": ["Maria Alvarez", "Nurse Reyes", "Dr. Okafor"], "step": 0 }
```

`movement/<step>.json` (backend output; compressed into `master_movement.json`)
```json
{ "persona": {
    "Maria Alvarez": { "movement": [x, y], "pronunciatio": "🤰",
      "description": "waiting to be triaged @ General Hospital:Waiting Room:chairs",
      "chat": null },
    "Nurse Reyes": { "movement": [x, y], "pronunciatio": "🩺",
      "description": "taking vitals @ General Hospital:Triage:triage bay 1:vitals station",
      "chat": [["Nurse Reyes","Let's get your blood pressure."],
               ["Maria Alvarez","Okay, thank you."]] } },
  "meta": { "curr_time": "March 21, 2026, 08:20:00" } }
```

`environment/<step>.json` (frontend -> backend tiles) and the persona bootstrap
JSON (`scratch.json`, `spatial_memory.json`, `associative_memory/nodes.json`) keep
the exact original schemas; only values change.

---

## 8. Frontend, maze assets, renderer decision

The replay frontend is domain-agnostic and consumes only `master_movement.json`
+ `meta.json`.

**Locked: minimal grid renderer (R2).** A lightweight single-file canvas draws the
hospital as a labeled room grid and animates agents tile-to-tile from
`master_movement.json`, with the `pronunciatio` emoji over each head, the
`description` on hover/click, and the consult `chat` in a speech bubble. It reads
the same tile coordinates the backend produces, so the data pipeline is identical
to the original; only the paint layer is simpler.

What this drops: the Phaser tilemap and the authored Tiled hospital map with its
five matrix CSVs of visuals. We still need a small **logical** maze for the
backend (addressing + pathfinding, section 3/10), but not a decorated tileset. A
Phaser + Tiled upgrade is an explicit post-hackathon stretch, not in this build.

---

## 9. LLM requirement (this port needs a model)

A faithful port is LLM-driven: planning, task decomposition, action-location
resolution, reactions, and reflection all call a model. **Locked: Claude only.**

- **Backend swap**: replace the repo's OpenAI calls in `persona/prompt_template/
  gpt_structure.py` (`ChatGPT_single_request`, `GPT4_request`, `get_embedding`)
  with the Anthropic API. Every `run_gpt_prompt_*` wrapper flows through those two
  functions, so this is a single, contained seam. Keep the `.txt` prompt templates
  as-is; only the transport changes.
- **Model tiers**: `claude-sonnet-5` for the frequent, cheap calls (hourly
  schedule, task decomposition, action sector/arena/object, pronunciatio, event
  triple, decide-to-talk). `claude-opus-4-8` for the low-frequency, high-value
  calls (reflection insight synthesis, post-consult memo). Ground every prompt in
  dataset-derived memory so output stays clinically realistic.
- **Embeddings**: the original uses OpenAI embeddings for relevance retrieval. With
  Claude-only, swap to a local sentence-embedding model (e.g. a small
  `sentence-transformers` model) for `get_embedding`, or, for the vertical slice,
  fall back to the keyword-only retrieval path (`retrieve()`), which needs no
  embeddings at all. Decide at build time; keyword-only is enough for one slice.
- **Precompute offline, replay**: run the cognition to bake
  `master_movement.json`, then the demo replays. No live API during the video.
- **Verbatim consult** (section 6) removes the largest generation from the loop, so
  the model surface is small: a few agents over one patient's journey.

---

## 10. Directory layout (mirrors the original structure)

```
hospital_gen_agent/
├── CLAUDE.md                         this plan
├── reverie/
│   └── backend_server/
│       ├── reverie.py                step loop (ported; Claude-backed gpt_structure)
│       ├── maze.py                   unchanged logic; loads hospital matrices
│       ├── path_finder.py            unchanged
│       └── persona/                  cognitive_modules + memory_structures (ported)
├── environment/
│   └── frontend_server/
│       ├── storage/base_hospital/    seeded personas + environment/0.json + meta.json
│       ├── compressed_storage/       baked master_movement.json for replay
│       └── static_dirs/assets/hospital/
│           ├── matrix/               maze_meta_info.json + 5 CSVs + special_blocks/
│           └── visuals/              hospital Tiled map JSON + tilesets   [R1]
├── seeding/                          dataset -> bootstrap (plan; the new work)
│   ├── build_world                   visit_type -> sectors; Obs/Med -> lab/pharmacy
│   ├── build_patients                record -> scratch + a_mem + transcript chat
│   └── build_staff_knowledge         aggregates -> staff a_mem clinical memory
└── README.md                         run + record instructions
```

Reuse from the parent repo: `../dataset/explore.py` loaders and
`../dataset/DATA_STRUCTURE.md` for field access during seeding.

---

## 11. Recommended hackathon scope: one faithful vertical slice

A full 25-agent hospital day is not feasible in the time. Ship a believable
**vertical slice** that shows the whole architecture working end to end:

- **Cast**: 1 hero patient (the prenatal record is vivid), 1 triage nurse, 1 OB
  doctor, plus 2-3 background patients for life in the waiting room.
- **Journey**: arrive at Admissions -> check in -> wait -> triage (vitals + history
  conversation) -> walk to OB Clinic -> consult with the doctor (grounded in the
  real transcript) -> reflection (patient learns the plan) -> discharge.
- **Proof of the architecture**: memory seeded from the chart, perceive/plan/execute
  moving the agent room to room, a real grounded consult, and a post-consult
  reflection written back to memory.
- Precompute, compress, replay on R2 (upgrade to R1 map if time remains).

### Build phases

```
Phase 1  Seeding      dataset -> world spec + hero patient bootstrap + staff knowledge
Phase 2  Backend port bring reverie + persona modules over; swap gpt_structure to Claude
Phase 3  Maze         hospital matrices (small grid) so addressing + pathfinding work
Phase 4  Run + bake   run the slice, compress to master_movement.json
Phase 5  Replay       R2 renderer reads master_movement.json + meta.json
Phase 6  Record       dry run, then capture the video
[stretch] R1 Tiled hospital map · more agents · LLM-regenerated consults
```

---

## 12. Risks and mitigations

- **Full port is large.** Mitigation: vertical slice (section 11), reuse the
  original modules rather than rewriting.
- **Tiled map authoring blows the clock.** Mitigation: R2 grid first; R1 is stretch.
- **LLM cost/latency/nondeterminism.** Mitigation: precompute + replay; small cast;
  verbatim transcript for the consult; cache all model output.
- **Faithful port needs a maze even at minimum** (addressing + pathfinding depend
  on the matrices). Mitigation: author a small hand-made grid, not the full floor.
- **Clinical realism drift.** Mitigation: ground every staff/patient prompt in
  dataset-derived memory; prefer verbatim transcript for the diagnosis.

---

## 13. Decisions — resolved (see section 0)

1. **LLM backend**: Claude only. `claude-sonnet-5` frequent, `claude-opus-4-8`
   reflection. Anthropic swap isolated to `gpt_structure.py`.
2. **Renderer**: minimal grid (R2). No Phaser/Tiled.
3. **Scope**: single vertical slice (hero patient + nurse + doctor + background).
4. **Consult dialogue**: verbatim transcript.

Remaining build-time choice (not blocking the plan): embeddings via a local model
vs keyword-only retrieval for the slice (section 9). Default to keyword-only.
