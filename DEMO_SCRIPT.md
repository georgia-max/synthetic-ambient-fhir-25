# "Hospital Generative Agents" — 60-Second Demo Script

*Abridge AI · screen recording + voiceover + burned-in captions · ~130 words / ~58 sec*

---

### 0:00 – 0:08 · THE HOOK
**Visual:** Black → fade into the static hospital grid, personas idle at their start positions.
**Caption:** `We built a digital twin of a hospital.`

> "This is a hospital that doesn't exist — a digital twin, built entirely from real patient intake data. Every room, every patient, every conversation traces back to an actual clinical encounter."

---

### 0:08 – 0:18 · THE DATA
**Visual:** Overlay — a patient intake / FHIR record scrolling, morphing into Clarence's `scratch.json` memory node.
**Caption:** `25 Abridge patient intakes → 25 digital twins`

> "We took twenty-five Abridge patient intakes and turned each one into a living digital twin — seeded from real chart history, vitals, and diagnoses. No hand-written characters. Synthetic patients, grounded in real clinical structure."

---

### 0:18 – 0:26 · THE WORLD
**Visual:** Zoom out on the full grid — check-in, triage, OB, and waiting areas labeled; the full cast idling.
**Caption:** `A living hospital: patients + staff who move, remember, reflect`

> "Drop them into a virtual hospital, and they come alive — patients and staff who move through the space, remember what happened, and reflect on it."

---

### 0:26 – 0:44 · THE WALKTHROUGH *(main footage)*
**Visual:** Clarence walks tile-to-tile: enters → checks in with clerk Rosa → waits → triage with Nurse Reyes → OB consult with Dr. Amari. Speech bubble on the consult.
**Captions:** `Arrives → Checks in → Triage → OB Consult` then `Verbatim from her intake transcript`

> "Meet Clarence. Watch her walk the full care pathway — check-in, triage, and an OB consult. And the dialogue isn't generated. It's the actual transcript from her intake, replayed word for word."

---

### 0:44 – 0:54 · UNDER THE HOOD
**Visual:** Five-box loop overlay, then two reflection thoughts appear over Clarence's head.
**Caption:** `Perceive → Retrieve → Plan → Reflect → Execute`

> "Underneath is a real generative-agent cognition loop — Stanford Smallville-style, rebuilt for a hospital and powered by Claude. After her consult, she reflects — grounded in her own chart."

---

### 0:54 – 1:00 · THE CLOSE
**Visual:** Pull back to the full cast → fade to title card.
**Caption:** `From patient intake to a hospital that simulates itself.`

> "Twenty-five intakes in — a whole hospital that thinks. Hospital Generative Agents: digital twins, built from your data."

**Title card:** `Hospital Generative Agents · A digital twin of a hospital, built from Abridge patient intake data · [github.com/…]`

---

**The arc:** *25 Abridge patient intakes → 25 grounded digital twins → a living hospital you can watch walk its own care pathways.*

## Production notes
- **Recording:** Bake the canned-mode replay first (`HGEN_LLM_MODE=canned ../.venv/bin/python run_slice.py`), then screen-record `master_movement.json` playing back at `http://localhost:8000/hospital.html`. Canned mode is deterministic — every take is identical.
- **Music:** Low ambient/tech underscore, no lyrics, tucked under the voiceover.
- **Captions:** Burn in on-screen text for silent autoplay (YouTube/social).
- **Pacing:** ~130 words reads comfortably in 55–60 sec at ~130–150 wpm. If long, trim the 0:26–0:44 walkthrough first — it's the most visual and carries silence well.

## Shot list
| Time | Shot | Source |
|------|------|--------|
| 0:00–0:08 | Black → static hospital grid | `hospital.html` idle frame |
| 0:08–0:18 | Intake/FHIR JSON → `scratch.json` overlay | `storage/base_hospital/personas/Clarence*/bootstrap_memory/scratch.json` |
| 0:18–0:26 | Full grid, all personas idle | `hospital.html` |
| 0:26–0:44 | Clarence's full pathway walk + OB speech bubble | `master_movement.json` replay |
| 0:44–0:54 | Cognition loop diagram + reflection thoughts | Custom overlay + `hospital.html` reflection popup |
| 0:54–1:00 | Full cast → title card | `hospital.html` / static graphic |
