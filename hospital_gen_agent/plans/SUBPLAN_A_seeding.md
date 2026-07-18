# Subplan A — Seeding rules: dataset → generative-agent bootstrap

Expands section 4 of `../CLAUDE.md`. Exact rules for turning `../../dataset/`
(25 FHIR encounters) into the bootstrap artifacts the ported reverie backend
loads: the world/maze address space, each persona's `scratch.json`,
`associative_memory/`, and `spatial_memory.json`, plus staff clinical knowledge.

Plan only, no code. All field paths below are real (verified against the data).
Running example throughout: the hero record **Clarence Reinger** (32F, prenatal
intake, OB, Dr. Amari).

Inputs:  `dataset/synthetic-ambient-fhir-25.jsonl` (via `dataset/explore.py`).
Outputs: `environment/frontend_server/storage/base_hospital/` (personas +
`environment/0.json` + `reverie/meta.json`) and the maze matrices under
`static_dirs/assets/hospital/matrix/`.

---

## 1. Name normalization

Names must be clean and human. Synthea puts digit suffixes in
`encounter.subject.display` ("Clarence5 Reinger292") but `patient.name` is clean.

- **Patient name**: `patient.name[0].given[0] + " " + patient.name[0].family`
  → "Clarence Reinger". Defensive: strip trailing digits from each token
  (`re.sub(r"\d+$", "", tok)`).
- **Prefix** (`patient.name[0].prefix[0]`, e.g. "Mrs.") kept for display only.
- **Clinician name**: parse the first `DR:` turn of `transcript` for "I am Dr. X"
  / "Dr. X"; fall back to a role name ("Dr. OB"). Hero → "Dr. Amari".
- **Family member**: if the transcript has a `FAMILY:` speaker, name it from the
  patient's mention ("this is my husband, Marcus") or label generically
  ("Marcus (spouse)"). Hero → "Marcus".

Persona `name` is the unique key everywhere (scratch, memory keys, movement JSON,
meta `persona_names`), so it must be stable and collision-free. If two records
normalize to the same name, append the last 4 of `patient_id`.

---

## 2. World spec generation

The world tree and the maze address space are derived once from the whole dataset,
then hand-placed on the grid (subplan B). Rule set:

**Sectors (departments):**
- Shared, always present: `Admissions`, `Waiting Room`, `Triage`,
  `Diagnostics / Lab`, `Pharmacy`, `Discharge`.
- Clinical departments: one per distinct `metadata.visit_type`, via this map:

```
General examination of patient (procedure)     -> General Medicine
Encounter for check up (procedure)             -> General Medicine
Prenatal initial visit (regime/therapy)        -> OB / Prenatal Clinic
Hospital admission (procedure)                 -> Inpatient Ward
Hospital admission for isolation (procedure)   -> Isolation Unit
Admission to hospice (procedure)               -> Hospice / Palliative
unknown                                         -> General Medicine
```

**Emergency Department (authored, not from the data):** the dataset has no ER
encounters, so an `Emergency Department` sector is added as an authored department
for the surge scenario (Subplan D). Its patients are synthetically generated
(mass-casualty fire cases, ESI 1-5), not seeded from the 25 records. Arenas: `ER
triage`, `ER bay 1..N` (doctor + bed), `ER waiting`. This sector is only needed for
the Subplan D surge demo, not the OB vertical slice.

**Arenas + game_objects** (authored, but informed by the data):
- `Diagnostics / Lab` objects are informed by the union of `DiagnosticReport.code.text`
  and `Observation.code.text` seen in the data (blood draw chair, analyzer,
  ultrasound, imaging table).
- `Pharmacy` is included whenever any record has `MedicationRequest` resources.
- Each clinical department gets at least one `exam room` arena with an
  `exam table` + `computer`; OB additionally gets `ultrasound machine` + `doppler`.

**Output**: a canonical world tree (the master `spatial_memory` the staff hold),
same nested shape as the original:
`{ "General Hospital": { <sector>: { <arena>: [<game_object>, ...] } } }`.
The vertical slice (subplan B) only instantiates the sectors its cast touches.

---

## 3. Patient persona seeding (one per record)

### 3a. `scratch.json` field map

| scratch field | source | Clarence value |
|---------------|--------|----------------|
| `name` / `first_name` / `last_name` | §1 normalization | "Clarence Reinger" / "Clarence" / "Reinger" |
| `age` | `age_at(patient.birthDate, metadata.date)` | 32 |
| `innate` | optional light traits; leave generic or infer tone from transcript | "warm, a little anxious" |
| `learned` | one-line chart summary from `longitudinal_summary.condition_labels` (clinical ones only) | "has a history of recurrent urinary tract infections" |
| `currently` | reason for visit from `metadata.visit_title` (text after the em dash) | "here for an initial prenatal evaluation, newly pregnant" |
| `lifestyle` | social-determinant condition_labels if present (stress, social isolation, transport problem), else generic | generic |
| `living_area` | `"Home"` | "Home" |
| `daily_plan_req` | template with visit_title | "Go to the hospital for a prenatal intake: check in, get triaged, see the OB, get a plan, go home." |
| runtime fields (`act_*`, `chat*`, `planned_path`, `f_daily_schedule`) | null/empty at bootstrap (identical to the original base persona) | null/[] |
| cognition params (`vision_r`, `retention`, `importance_trigger_max`, weights) | copy the original defaults | as-is |

### 3b. `associative_memory` node generation

Each node is a `ConceptNode` with the original schema:
`{node_id, node_count, type_count, type, depth, created, expiration, subject,
predicate, object, description, embedding_key, poignancy, keywords, filling}`.

Seed only what the patient would know **before** the visit. Rules:

1. **Chronic/background conditions** — from `longitudinal_summary.condition_labels`,
   keep only clinical findings (drop pure admin/education findings, see the drop
   list in 3c). One `thought` node each:
   - triple `(name, "has", <condition short label>)`
   - description `"<name> has <condition>."`
   - poignancy from the rubric (3c)
   - keywords `{name, condition head noun}`
   - Clarence → `("Clarence Reinger", "has", "recurrent urinary tract infection")`,
     poignancy 6, and `("Clarence Reinger", "has", "normal pregnancy")`, poignancy 8.

2. **Chief complaint** — one `thought` from `visit_title`:
   `(name, "is here for", <visit reason>)`, description
   `"<name> is here for <reason>."`, poignancy 6.
   Clarence → "Clarence Reinger is here for an initial prenatal evaluation."

3. **Symptom account** — extract the first 2-3 `PT:` turns of `transcript` that
   describe symptoms (skip pure pleasantries). Store each as an `event` node:
   `(name, "reports", "symptoms")`, description = the trimmed quote (≤ ~150 chars),
   `embedding_key` = the quote, poignancy 4-6.
   Clarence → "reports fatigue and mild morning queasiness relieved by eating early."

4. **NOT pre-seeded to the patient**: `related_resources.Condition` (the diagnosis
   recorded at this visit), `Observation` values (vitals/labs taken today), the
   `note` Assessment/Plan. These are visit **outcomes**; they enter memory only via
   the consult and the post-consult reflection (§5), preserving the arc.

### 3c. Poignancy rubric (1-10)

Deterministic keyword mapping on the condition/finding label. Higher = more
memorable, which drives retrieval importance and the reflection trigger.

```
9  life-threatening / terminal: cancer, sepsis, end-stage, hospice, pneumonia, hypoxemia
8  serious / pregnancy: normal pregnancy, COVID-19, myocardial, stroke
7  chronic disease: diabetes, hypertension, hyperlipidemia, metabolic syndrome, CKD
6  active symptomatic / recurrent: UTI, migraine, back pain, osteoarthritis, anemia, prediabetes
5  psychosocial / SDOH: stress, social isolation, depression screen, anxiety
3  administrative / lifestyle finding: medication review due, risk activity involvement
2  demographic finding: received higher education, educated to high school level
1  idle / none
```

Drop list (never become nodes): pure education/administrative findings unless the
scene needs them. "Medication review due" and "Received higher education" are
dropped from Clarence's clinical memory.

### 3d. `spatial_memory.json` (known at start)

Patients start knowing only the public path; they learn departments by perceiving,
exactly like villagers.

```json
{ "General Hospital": {
    "Admissions":   { "reception":     ["reception desk", "check-in kiosk"] },
    "Waiting Room": { "waiting area":  ["waiting chairs"] },
    "Triage":       { "triage bay 1":  ["vitals station"] } } }
```

### 3e. Timestamps and IDs

- `created`: backdate before sim start so recency decay is meaningful. Chronic
  conditions → `start_date - 365d` (or `Condition.onsetDateTime` if present).
  Chief complaint / symptoms → `start_date - 1d`.
- `expiration`: `null` for events; `created + 30d` for thoughts (matches original).
- `node_id`: `"node_<count>"`, assigned in insertion order; newest prepended
  (the original stores newest-first).
- `last_accessed` = `created` at bootstrap.

---

## 4. Staff persona + clinical knowledge seeding

Staff are authored personas whose power is dataset-aggregated knowledge. This is
the literal "dataset = what the agents know about the hospital."

### 4a. Roster (vertical slice needs the first three)

Reception clerk, Triage nurse, OB doctor (hero dept). Full build adds GP,
hospitalist, palliative doctor, lab tech, pharmacist.

### 4b. Aggregation rules → knowledge nodes

Group records by department (via the §2 map), then aggregate:

- **Triage nurse** — from every record's `Observation` resources, collect
  `code.text` and typical value ranges (min/median/max of `valueQuantity.value`,
  or component values for blood pressure). One `thought` per common vital:
  `("Nurse", "knows", "<vital>")`, description
  `"Typical <vital> runs about <lo>-<hi> <unit> here."` poignancy 5.
  e.g. "Typical blood pressure runs about 98/83 to 140/90 mm[Hg] here."
- **Department doctor** — from the records in that department:
  - top `condition_labels` and `related_resources.Condition.code.text`
    → `("Dr. X", "commonly sees", "<condition>")`, poignancy 6.
  - common `Procedure.code.text` → `("Dr. X", "orders", "<procedure>")`.
  - OB example: "Dr. Amari commonly sees normal pregnancy and recurrent UTI in
    prenatal intakes; orders transabdominal ultrasound and prenatal labs."
- **Lab tech** — union of `DiagnosticReport.code.text` + lab `Observation.code.text`
  → knowledge nodes of runnable tests.
- **Pharmacist** — from `MedicationRequest`. Caveat: many `MedicationRequest`s use
  `medicationReference` (a urn), and `longitudinal_summary.medication_labels` is
  often empty in this dataset, so med names are frequently unavailable. Rule: use
  `medication_labels` where non-empty; otherwise seed generic pharmacy knowledge.
  Flag this gap rather than inventing drug names.

### 4c. Staff `scratch.json`

`name` authored; `age` plausible; `learned` = their specialty; `currently` = "on
shift in <department>"; `daily_plan_req` = "See patients in <department>:
<role-specific verbs>." `living_area` = their department. Staff spatial memory =
the full authored world tree (they know the whole hospital).

---

## 5. Note and after-visit-summary parsing (the outcome arc)

Parse `note` on the three real headings: `**Subjective:**`, `**Objective:**`,
`**Assessment and Plan:**` (note the wording is "Assessment and Plan"). Roles:

- **Assessment and Plan** → the ground-truth diagnosis + plan. Seeded into the
  **doctor's** memory as the expected outcome for the hero patient, and used as the
  target of the **patient's post-consult reflection** (the thought the patient
  should form after the consult).
- **Subjective** → corroborates the patient's symptom nodes (3b.3); not required if
  transcript turns already cover them.
- **after_visit_summary** → what the patient "remembers to do" after discharge; one
  post-visit `thought` created during the discharge step.

Because the consult is verbatim transcript (locked), the diagnosis is delivered by
the real dialogue; the note's Assessment/Plan only seeds the reflection wording so
the patient's takeaway matches the real plan.

---

## 6. Output artifact inventory

Mirror the original bootstrap layout so the ported backend loads them unchanged:

```
storage/base_hospital/
├── reverie/meta.json                          start_date, curr_time, sec_per_step,
│                                               maze_name="hospital", persona_names, step=0
├── environment/0.json                         spawn tiles per persona (subplan B grid)
└── personas/<Name>/bootstrap_memory/
    ├── scratch.json                           §3a / §4c
    ├── spatial_memory.json                    §3d (patients) / full tree (staff)
    └── associative_memory/
        ├── nodes.json                         §3b / §4b nodes, newest-first
        ├── embeddings.json                    {} if keyword-only retrieval (default)
        └── kw_strength.json                   {"kw_strength_event":{}, "kw_strength_thought":{}}
```

Plus maze matrices under `static_dirs/assets/hospital/matrix/` (subplan B).

---

## 7. Determinism and validation

- Seeding is a pure function of the dataset; no randomness. Same input → same
  bootstrap, so replays are reproducible.
- Validate each persona: scratch parses, every node has a poignancy in 1-10, every
  keyword indexes at least one node, spatial-memory addresses exist in the maze
  address space.
- Validate the world: every `visit_type` in the slice maps to a sector that exists
  in the maze matrices; every persona spawn tile in `environment/0.json` is a
  non-collision tile.
