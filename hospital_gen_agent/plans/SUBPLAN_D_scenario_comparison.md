# Subplan D — ER surge comparison: capacity, bottleneck, and prediction

Demo goal: show that we can (1) generate synthetic patients, (2) simulate a whole
day of an **Emergency Department**, and (3) **predict** how a sudden mass-casualty
surge (a building fire sending many emergency patients at once) hits ER throughput
— by comparing two staffing scenarios:

- **Scenario A:** 1 ER doctor.
- **Scenario B:** 3 ER doctors.

Headline output: an **XY chart, x = time of day, y = waiting time**, one line per
scenario, plus bottleneck charts contrasting A vs B. The story: when the fire hits,
1 ER doctor means the waiting room explodes and critical patients wait; 3 ER doctors
absorb the same surge.

Plan only, no code.

## Data truth (read this first)

**The dataset has no emergency encounters.** Visit types are general exams,
prenatal, hospital/isolation admissions, hospice, and check-ups; encounter classes
are AMB / IMP / HH — there is no `EMER` class and no ER visit. So the ER surge
patients are **synthetically generated**, not seeded from the 25 records. That is on
theme: the pitch is literally "we can create synthetic patients and simulate a
surge." Concretely:

- **Baseline load** (optional): the 25 real dataset patients flow through their own
  departments across the day as normal hospital traffic.
- **ER surge (the star):** a synthetic generator produces mass-casualty emergency
  patients — fire casualties with realistic acuity (burns, smoke inhalation,
  trauma), arrival burst, and triage levels. These never existed in the data; we
  invent them, which is the point.

## Architecture truth

**This is a discrete-event simulation (DES) / queueing problem, not a
generative-agents problem.** Waiting time, queue length, utilization, and surge
recovery are what DES engines (SimPy) compute cleanly and cheaply. Driving dozens
of LLM agents through a full day x 2 scenarios x a surge would be slow and costly
and would not yield tidy metrics.

```
  synthetic ER patients (fire surge) ─┐
  + optional dataset baseline load  ──┤
                                      ▼
             DES engine (SimPy): ER modeled as N doctors + M beds
                                      │
             ┌────────────┬──────────┴──────────┐
             ▼            ▼                      ▼
        Scenario A    Scenario B          Fire surge injection
        (1 ER doc)    (3 ER docs)         (mass casualties at T_fire)
                                      │
                                      ▼
            metrics: wait/stage, queue over time, utilization,
                     throughput, LOS, time-to-clear-surge, bottleneck
                                      │
                                      ▼
         comparison dashboard: XY wait chart + bottleneck charts
```

The generative-agents work (Subplans A/B/C) is the **qualitative** layer (watch one
believable patient); this subplan is the **quantitative** layer (predict ER
operations under load). Same synthetic-patient theme, one demo arc:
"meet a synthetic patient → now flood the ER with a fire → here's what breaks."

Note: the abandoned `../../sim/` folder already implemented a SimPy intake pipeline
with waiting-time / utilization / bottleneck metrics and surge + short-staffed
presets. It is directly reusable as the ER engine's starting point; adapt it rather
than rebuild.

## The ER model

- **Stages:** arrival -> ER triage (ESI level) -> treatment (ER doctor + bed) ->
  disposition (discharge / admit to ward). Triage uses the **Emergency Severity
  Index (ESI 1-5)**: 1-2 = critical (immediate), 3 = urgent, 4-5 = less urgent.
- **Resources:** `er_doctors` (the knob: 1 vs 3), `er_beds` (fixed, e.g. 8),
  triage nurses. Treatment is a `PriorityResource` keyed by ESI so criticals are
  seen first.
- **Service times:** per-ESI treatment-time distributions (criticals take longer);
  modeled parameters, not learned from the data (state this honestly).

## The surge ("fire in a building")

- At `T_fire`, inject `K` synthetic emergency patients (e.g. 12-20) over a short
  window (10-20 min), skewed to high acuity (ESI 1-3: burns, smoke inhalation,
  trauma).
- Both scenarios run the **same** patients, arrival stream, and seed — only
  `er_doctors` differs — so the comparison is apples-to-apples.
- Knobs for the demo: `er_doctors`, `T_fire`, `K` (surge size), acuity mix.

## Charts (the deliverable)

**1. Headline XY — ER waiting time over the day (A vs B).**
```
 wait (min)
  90│                 ╭─╮   A: 1 ER doctor
    │                ╭╯ ╰─╮
  60│      fire→    ╭╯    ╰──╮
    │             ╭╯         ╰──╮
  30│      ──────╯              ╰────  B: 3 ER doctors
    │  ───────────────────────────────
   0└──────────────────────────────────  time of day
     08   10   12   14   16   18
```
Vertical marker at `T_fire`. The gap between the lines after the fire is the whole
pitch.

**2. ER queue length over time (A vs B).** Under A the waiting room fills and drains
slowly after the fire; under B it barely rises. Area/line, both scenarios.

**3. Wait by ESI level (A vs B).** Bars per ESI 1-5: shows that under A even
critical (ESI 1-2) patients wait dangerously; under B criticals stay near-zero wait.
This is the clinically damning chart.

**4. ER doctor utilization (A vs B).** Under A doctors are pinned at ~100% through
the surge (overloaded, no slack); under B there is headroom.

**5. Summary tiles:** mean / 95th-percentile wait, patients seen, longest queue,
**time to clear the surge**, and (optional) "critical patients who waited > X min" —
per scenario, with the A-vs-B delta.

## Deliverable options (open decision D1)

- A) **Streamlit dashboard** (recommended): sliders for `er_doctors`, `T_fire`, `K`,
  acuity mix; runs both scenarios; Plotly charts; a "trigger fire" button. Fast,
  interactive, demoable.
- B) **Static HTML + Plotly:** pre-bake both scenarios to JSON, one self-contained
  page (matches the no-build ethos). Easiest to screen-record.
- C) **Extend the pretty frontend (Subplan C):** animate the ER filling up during
  the surge with a live wait chart underneath. Most impressive, most work.

Recommendation: **A** now; **C** later to marry the visual ER with the numbers.

## Module outline (planned)

```
hgen/scenarios/
├── er_patients.py   synthetic ER/fire-casualty generator (ESI, arrivals, service)
├── engine.py        SimPy ER: PriorityResource(er_doctors) + beds; run one day
├── surge.py         inject K casualties at T_fire
├── metrics.py       wait/stage, queue-over-time, utilization, ESI waits, time-to-clear
├── compare.py       run A and B on the same seed -> comparison dataset
└── app.py           Streamlit dashboard (charts + knobs)   [option A]
```

Reuse the `../../sim/` SimPy pipeline; add the ER-specific ESI triage + casualty
generator.

## Acceptance criteria (what the demo must show)

1. Synthetic ER/fire-casualty patients generated on demand (no dataset ER needed).
2. Both scenarios run on the same patients/seed (fair comparison).
3. The **XY wait-time chart** clearly shows A's wait spiking after the fire while B
   stays low.
4. The **wait-by-ESI** (or queue-over-time) chart shows the ER as the bottleneck and
   the A-vs-B contrast, including that criticals wait under A.
5. A **surge knob** (fire time / size / doctors) that visibly changes the outcome on
   re-run — the prediction beat.
6. Deterministic given a seed.

## Honest caveats

- ER patients, arrival bursts, and service times are **synthetic modeled
  assumptions** (the dataset has no ER data). Prediction here = "simulate under
  assumed parameters," the standard, correct use of DES. Say so in the demo.
- The comparison is a what-if, not a trained forecaster.

## Open decisions

- **D1 — Deliverable:** Streamlit (recommended) vs static HTML+Plotly vs animated
  frontend.
- **D2 — Baseline load:** ER surge only (cleaner, all-synthetic) vs surge on top of
  the 25 real dataset patients flowing through other departments (richer, ties back
  to the dataset).
- **D3 — Acuity model:** full ESI 1-5 (recommended, realistic) vs simple
  routine/urgent/critical.
- **D4 — Engine:** adapt `../../sim/` (recommended) vs build `hgen/scenarios/` fresh.
