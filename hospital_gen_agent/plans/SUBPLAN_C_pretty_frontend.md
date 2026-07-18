# Subplan C — Prettier hospital frontend

Upgrade the replay renderer (`web/hospital.html`) from the current "colored boxes +
labeled dots" grid into a hospital environment that reads as a real place, with
recognizable **patient / doctor / nurse / clerk / family** characters, furnished
rooms, and clean typography. Same data contract (`world.json` + `meta.json` +
`master_movement.json`), same "open in a browser, no build step" property.

Plan only, no code.

## Where we are now

`web/hospital.html` (vanilla canvas) already draws labeled department rectangles,
agents as colored dots with a name + emoji, speech bubbles, a clock, and
play/pause/speed. It works but looks schematic: dots not characters, name labels
overlap when agents cluster, rooms are empty rectangles, and the right third of
the screen is dead space.

## Target look

```
┌───────────────────────────────────────────────┬───────────────────────┐
│  🏥 General Hospital        Mar 21 · 08:44   ▶ │  PATIENT CARD          │
│                                                │  ┌───────────────────┐ │
│  ┌── Admissions ──┐  ┌── Triage ──┐  ┌─ OB ─┐  │  │ 🧕 Clarence R., 32 │ │
│  │ 🪑🪑  🖥️ desk   │  │ 🩺 [bed]    │  │ 🛏️📺 │  │  │ Prenatal intake   │ │
│  │   👩‍⚕️clerk       │  │  👩‍⚕️nurse    │  │ 👨‍⚕️dr │  │  │ Hx: recurrent UTI │ │
│  └────────┬────────┘  └──────┬─────┘  └───┬──┘  │  │ 🗣 "I get UTIs a  │ │
│  ═════════╪══════════ hall ══╪════════════╪═══  │  │     lot..."       │ │
│  ┌── Waiting ─────────────┐   ┌─ Discharge ─┐   │  └───────────────────┘ │
│  │ 🪑🪑🪑  🧍🧍 patients    │   │  ▢ exit      │   │  CAST (click to follow)│
│  └────────────────────────┘   └─────────────┘   │  ● Clarence  ● Dr Amari│
└───────────────────────────────────────────────┴───────────────────────┘
```

## What changes

1. **Characters, not dots.** Each persona is a small avatar chosen by role:
   patient, doctor, nurse, clerk, family. Two art options (pick in D1). Avatars
   face their walk direction and bob slightly while moving.
2. **Role assignment.** Map each `persona_name` to a role. Cleanest: `world.json`
   (or a new `cast.json`) carries `{name, role, color}`, written by the seeding /
   world step so the renderer does not hardcode names. Fallback heuristic: name
   contains "Dr." -> doctor, "Nurse" -> nurse, clerk names -> clerk, "Marcus"/
   family -> family, else patient.
3. **Furnished rooms.** `world.json.objects` already lists labeled objects per
   room (reception desk, vitals station, exam table, ultrasound, chairs, exit).
   Draw each as a small furniture glyph/sprite at its tile instead of a gray
   square, and draw a floor texture + walls + a door gap on the corridor side.
4. **Department theming.** Each sector keeps its accent color but gets a tinted
   floor, a header pill with an icon, and a soft border. Corridor drawn as a
   distinct floor.
5. **Readable labels.** Name tags render in a rounded chip above the avatar,
   hidden when zoomed out or when avatars overlap (show on hover instead). No more
   "PatiePatient B" collisions.
6. **Styled speech bubbles.** Rounded bubble with a tail, speaker name in bold, up
   to 3 lines, department-tinted border. The consult bubble is larger/centered.
7. **Patient card panel (right column).** Fills the dead space: when a patient is
   selected (or auto-follow the hero), show a card with avatar, age, visit reason,
   a couple of chart facts (from the seed), and their current line. Reads like a
   mini-EHR. Requires exposing a little per-patient seed data to the renderer (see
   D2).
8. **Header polish.** Title with logo, live clock, step scrubber, play/pause,
   speed, and (for Subplan D) a scenario label.

## Data the renderer needs (small additions)

- `cast.json` (or extend `world.json`): `[{name, role, color}]` for avatars.
- `patient_cards.json` (optional, for the panel): `{name: {age, reason,
  facts:[...]}}` derived from the seed. Small, non-PHI (synthetic).
- `world.json.objects` already exists; ensure every furniture piece has a `kind`
  (desk/chair/bed/table/ultrasound/exit) so the renderer picks the right glyph.

No change to `master_movement.json`.

## Open decisions

**D1 — Character art.**
- A) **Emoji / inline-SVG avatars** (recommended): role-based emoji or hand-drawn
  SVG figures, colored per role. Zero assets, crisp at any zoom, fast. Looks
  clean and intentional, not pixel-perfect.
- B) **CC0 top-down sprite sheet** (e.g. Kenney / LPC): real little characters
  with walk frames. Prettier, but adds an image asset + sprite-slicing code and a
  license note. More time.

**D2 — Patient card data.** Expose a small `patient_cards.json` from the seed
(recommended, richest) vs. keep the panel to name + current action only (no new
data file).

**D3 — Scope of motion.** Simple position lerp + directional facing (recommended)
vs. full 4-direction walk-cycle animation (needs sprite sheet from D1-B).

## Build outline (once decided)

1. Emit `cast.json` (+ optional `patient_cards.json`) from the world/seeding step.
2. Rewrite the draw layer of `hospital.html`: floor/walls/doors, furniture glyphs,
   role avatars, chip labels, styled bubbles.
3. Add the right-column patient card panel.
4. Keep the existing replay/clock/controls logic; only the paint layer changes.
5. Verify via the browse skill (screenshot the arrival, triage, and consult beats).

## Non-goals

Still no Phaser/Tiled/build step (keeps the double-click-to-open property). Not a
3D or isometric view. This is a polish pass on the existing 2D top-down replay.
