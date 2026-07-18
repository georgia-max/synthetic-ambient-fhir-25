# web/ — minimal grid replayer (R2)

`hospital.html` is a single-file, dependency-free vanilla-JS canvas replayer for
the hospital vertical slice. No frameworks, no CDN.

## Run

Browsers block `file://` fetch, so serve this folder:

```
cd /Users/georgia/Desktop/synthetic-ambient-fhir-25/hospital_gen_agent/web
/Users/georgia/Desktop/synthetic-ambient-fhir-25/.venv/bin/python -m http.server
# then open http://localhost:8000/hospital.html
```

## Inputs (siblings of hospital.html)

- `world.json` — `{tile_size, width, height, rooms:[{id,label,x,y,w,h,color}], objects:[{label,x,y}]}`
- `meta.json` — `{start_date, curr_time, sec_per_step, persona_names, step, ...}`
- `master_movement.json` — `{"<step>": {"<persona>": {movement:[x,y], pronunciatio, description, chat}}}`
  (delta-compressed: a persona appears only on steps where its state changed;
  the replayer carries forward last-known state.)

If `master_movement.json` is missing, the page shows how to bake it
(`run_slice.py`) and serve the folder. `world.json`/`meta.json` fall back to
inferred defaults if absent.

## Features

Labeled colored rooms + object labels, personas as labeled dots that smoothly
interpolate tile-to-tile, `pronunciatio` emoji over each head, speech bubbles
for consult `chat`, a header clock advancing `sec_per_step` per step,
play/pause (space) + speed + restart controls, click-a-persona detail panel,
and looped playback.
