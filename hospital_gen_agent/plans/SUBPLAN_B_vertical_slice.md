# Subplan B — Vertical-slice step script

Expands section 11 of `../CLAUDE.md`. The exact one-patient journey the demo bakes
and replays: cast, the minimal grid map with real tile coordinates, `meta.json`,
and a step-by-step timeline mapping each beat to the cognitive functions that fire
and the `master_movement.json` frames produced.

Plan only, no code. Locked decisions from `../CLAUDE.md` §0 apply: Claude-only
cognition, minimal grid renderer, single vertical slice, verbatim consult.

Hero record: **Clarence Reinger**, 32F, "Prenatal intake visit — initial obstetric
evaluation", OB, clinician **Dr. Amari**, spouse **Marcus** present.

---

## 1. Cast

| Persona | Role | Seed source (subplan A) |
|---------|------|--------------------------|
| Clarence Reinger | hero patient | hero record: scratch + memory + transcript |
| Marcus | family (walks with Clarence, no cognition) | transcript FAMILY speaker |
| Nurse Reyes | triage nurse | staff aggregate: vitals knowledge |
| Dr. Amari | OB doctor | staff aggregate: OB knowledge + hero note Assessment/Plan |
| Rosa Diaz | reception clerk | authored, minimal |
| 2 background patients | ambience in the waiting room | two other records, memory only, short loops |

Only Clarence, Nurse Reyes, and Dr. Amari run the full cognitive loop. Marcus is a
follower sprite (copies Clarence's path, one tile behind). Background patients run
a trivial sit-and-idle loop so the waiting room is not empty.

---

## 2. The minimal grid map

A small logical maze (28 wide × 14 tall) is enough for real addressing and BFS
pathfinding. The renderer draws labeled rooms; the backend uses the matrices.

```
      col:  0    5    10   15   20   25
  row 0   ┌───────────────────────────────────┐
      1   │ [ADMISSIONS ]     [ TRIAGE ]       │
      2   │  reception         triage bay 1    │      [ OB / PRENATAL ]
      3   │  ▣ desk            ▣ vitals        │       ▣ exam table
      4   │                                    │       ◇ ultrasound
      5   │····································· │  ← corridor spine (row 7)
      7   │===================================│
      9   │ [WAITING ROOM ]                    │      [ DISCHARGE ]
     10   │  ▣▣▣ chairs                        │       ▣ desk / exit
     12   │                                    │
     13   │ ◊ Home/entrance (spawn)            │
          └───────────────────────────────────┘
```

Tile coordinates (x, y) and addresses used by the seed + pathfinding:

| Address (`world:sector:arena:game_object`) | tile (x,y) |
|--------------------------------------------|-----------|
| spawn / `Home` | (2, 13) |
| `General Hospital:Admissions:reception:reception desk` | (4, 3) |
| `General Hospital:Waiting Room:waiting area:waiting chairs` | (4, 10), (5,10), (6,10) |
| `General Hospital:Triage:triage bay 1:vitals station` | (13, 3) |
| `General Hospital:OB / Prenatal Clinic:exam room:exam table` | (23, 3) |
| `General Hospital:OB / Prenatal Clinic:exam room:ultrasound machine` | (25, 4) |
| `General Hospital:Discharge:discharge desk:exit` | (23, 10) |

Corridor: row 7 is open across x=2..26; vertical connectors at x=4, x=13, x=23
join rooms to the spine. Everything else on the room borders is a collision tile.
This yields the five matrices subplan A/§6 references (collision, sector, arena,
game_object, spawning_location), hand-authored at this size in minutes.

---

## 3. `meta.json` and timing

```json
{ "fork_sim_code": "base_hospital",
  "start_date": "March 21, 2026",
  "curr_time": "March 21, 2026, 08:00:00",
  "sec_per_step": 30,
  "maze_name": "hospital",
  "persona_names": ["Clarence Reinger","Marcus","Nurse Reyes","Dr. Amari","Rosa Diaz","Patient A","Patient B"],
  "step": 0 }
```

`sec_per_step = 30` (30 game-seconds per step) keeps the whole visit to a
manageable step count. The visit spans ~50 minutes of game time → ~100 steps.
The renderer animates each step over `tile_width / movement_speed` frames, so
playback is smooth and the on-screen clock ticks 30s per step.

---

## 4. Step script (the journey)

Phases with approximate step ranges, the cognitive functions that fire, and the
resulting `master_movement.json` content (emoji = `pronunciatio`, quote = a `chat`
snippet). Steps are illustrative; exact counts depend on path lengths.

| Steps | Phase | What happens | Cognitive functions | movement content |
|-------|-------|--------------|---------------------|------------------|
| 0-4 | **Arrival** | Clarence (+Marcus) spawn at Home, walk to reception. First-day plan builds the care pathway. | `plan._long_term_planning` (first day) → daily_req; `execute` A* to reception | 🚶 "walking in @ ...:Admissions:reception" |
| 5-9 | **Check-in** | Rosa the clerk checks Clarence in; short exchange; routed to the waiting room. | `perceive` sees clerk; `_should_react`→`decide_to_talk` yes; brief `agent_chat_v2` (LLM, 2 turns); `reflect` (light) | 💬 "checking in @ ...:reception:reception desk" |
| 10-18 | **Waiting** | Clarence sits in the waiting room; background patients idle nearby. | `plan._determine_action` → wait action; `execute` to a chair | ⌛ "waiting to be seen @ ...:Waiting Room:waiting area:waiting chairs" |
| 19-24 | **To triage** | Nurse Reyes calls Clarence; both walk to triage bay 1. | Reyes `plan` action "call next patient"; Clarence reaction; both `execute` | 🚶 / 🩺 "heading to triage" |
| 25-38 | **Triage** | Vitals + brief history. Nurse knowledge (vitals ranges) grounds the banter. Acuity noted. | `agent_chat_v2` (LLM, grounded by nurse's vitals thoughts + Clarence's symptom nodes); Clarence `perceive`/`retrieve` | 🩺 "taking vitals @ ...:Triage:triage bay 1:vitals station"; chat 3-4 turns |
| 39-45 | **To OB** | Clarence (+Marcus) walk from triage to the OB exam room; Dr. Amari waiting. | `plan` action "go to OB exam"; `execute` A* across corridor | 🚶 "walking to OB clinic @ ...:OB / Prenatal Clinic:exam room" |
| 46-78 | **Consult (verbatim)** | The real transcript plays out: Dr. Amari, Clarence, Marcus. Ultrasound beat. This is the centerpiece. | `decide_to_talk` opens the convo; **chat = verbatim transcript turns** (no LLM); paced per §5 | 🤰/🩺/👨 rotating; chat = real `DR:`/`PT:`/`FAMILY:` lines |
| 79-84 | **Reflection** | After the consult, Clarence forms the takeaway (grounded by the note's Assessment/Plan). Dr. Amari records the assessment. | `reflect`: `planning_thought_on_convo` + `memo_on_convo` (LLM, Opus) → new thought nodes | 💭 "thinking about the plan @ ...:exam room" |
| 85-95 | **Discharge** | Clarence (+Marcus) walk to discharge; after-visit-summary becomes a remembered to-do. | `plan` action "discharge"; `execute`; discharge `thought` from AVS | ✅ "getting discharge instructions @ ...:Discharge:discharge desk:exit" |
| 96-100 | **Exit** | Clarence and Marcus leave via the exit tile; sprites fade. | `execute` to exit; end of slice | 🚶 "leaving @ ...:exit" |

Throughout, Nurse Reyes and Dr. Amari continue their own loops (idle, chart,
call next) so the world is alive, not frozen around the hero.

---

## 5. Consult transcript pacing (verbatim)

The consult `chat` comes straight from the hero `transcript`, not the model. Rule:

1. Parse `transcript` into ordered turns `(speaker, text)` on `DR:`/`PT:`/`FAMILY:`
   markers (the parser already written in `dataset/dataset_explore.ipynb`).
2. Map speakers to personas: `DR:`→Dr. Amari, `PT:`→Clarence, `FAMILY:`→Marcus.
3. Emit turns across the consult steps: ~1 turn per step, so a 30-turn consult
   fills ~30 steps (46-78 above). Each step's `chat` for the active speaker holds
   the running window of the last few lines (matching how the original renders the
   last N lines in the bubble).
4. `pronunciatio` follows the speaker (🩺 doctor, 🤰 patient, 👨 family); the
   ultrasound line switches the object emoji to 🫀 (fetal heart tones) for one beat.
5. No safety filter or LLM call is needed; the content is fixed, real, and already
   clinically reviewed in shape.

This makes the highest-stakes, most-watched scene deterministic and exact.

---

## 6. Background life

Two background patients (`Patient A`, `Patient B`) are seeded from two other
records (memory only, no consult). Their loop: spawn, walk to a waiting chair, idle
with occasional 💬 to each other (one short LLM exchange, cached). They exist to
make the waiting room read as a real hospital, not a single-actor stage.

---

## 7. Per-phase expected outputs (bake)

Running the slice writes `movement/<step>.json` for steps 0-100, which
`compress_sim_storage` folds into `compressed_storage/base_hospital/
master_movement.json`. Expected:
- Every step has a valid `meta.curr_time` advancing 30s per step.
- Clarence's `description` moves through the address chain Admissions → Waiting
  Room → Triage → OB exam room → Discharge → exit.
- Consult steps carry verbatim transcript `chat`.
- Two reflection `thought` nodes appear in Clarence's `nodes.json` after step 78.

---

## 8. Acceptance criteria (what the video must show)

1. Clarence arrives, checks in, and is routed correctly to **OB** (proving
   `visit_type` → department seeding works).
2. A **triage** exchange grounded in the nurse's vitals knowledge (proving staff
   knowledge seeding works).
3. The **verbatim consult** with Dr. Amari and Marcus present, including the
   ultrasound / fetal-heart beat (proving dialogue grounding).
4. A visible **reflection**: after the consult, Clarence's takeaway thought appears
   and matches the note's plan (proving the memory write-back arc).
5. Discharge and exit, with a living waiting room in the background.
6. Everything replays from a single baked `master_movement.json`, deterministically
   (proving the precompute-then-replay pipeline).

---

## 9. Bake + replay procedure (build-time, later)

```
1. Seed        run seeding (subplan A) -> storage/base_hospital/ + maze matrices
2. Run         port reverie; run the slice for ~100 steps (Claude-backed cognition,
               verbatim consult injected) -> movement/<step>.json
3. Compress    compress_sim_storage -> compressed_storage/base_hospital/master_movement.json
4. Replay      minimal grid renderer loads master_movement.json + meta.json
5. Record      dry run, then capture the video
```

Cost note: with the consult verbatim and only three full-cognition agents over
~100 steps, the model surface is small (schedule + action resolution + a few
reactions + two reflections). Sonnet 5 handles the frequent calls; Opus 4.8 the
two reflection syntheses. All output cached so re-bakes are cheap.
