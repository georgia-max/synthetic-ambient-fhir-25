# Data Structure — synthetic-ambient-fhir-25

Each record = **one clinical encounter** (25 total, one patient each). A record is a
**deeply nested JSON object**, not a flat table. The canonical file
`synthetic-ambient-fhir-25.jsonl` holds one such object per line.

## Structure at a glance

```
record
├── id                              str    "<patient_id>::<encounter_id>"
├── metadata                        dict   encounter facts + per-type FHIR counts
├── patient_context                 dict   who the patient is + their whole-chart summary
│   ├── patient                     dict   FHIR Patient resource
│   └── longitudinal_summary        dict   resource_counts, condition_labels, medication_labels
├── encounter_fhir                  dict   this visit's structured clinical data
│   ├── encounter                   dict   FHIR Encounter resource
│   └── related_resources           dict   lists of FHIR resources grouped by type
│       ├── Condition        [ ... ]
│       ├── Observation      [ ... ]   ← richest; numeric/coded values
│       ├── Procedure        [ ... ]
│       ├── DiagnosticReport [ ... ]
│       └── Immunization / MedicationRequest / ImagingStudy [ ... ]
├── transcript                      str    ambient conversation (DR:/PT:/NURSE:/FAMILY:)
├── note                            str    SOAP-style clinical note (markdown)
├── after_visit_summary             str    patient-facing summary
└── after_visit_summary_provenance  dict   how the AVS was generated
```

## Sample value for each field

### Top level

| field | type | sample |
|---|---|---|
| `id` | str | `"3a3a1f26-…464::3a3a1f26-…faea"` (patient_id::encounter_id) |
| `transcript` | str | `"DR: Good morning — Ali, right? Come on in, grab a seat…"` (~1,241–1,669 words) |
| `note` | str | `"**Subjective:** Ali Kuhic is a 31-year-old man presenting for…"` (~499–645 words) |
| `after_visit_summary` | str | `"Visit summary  What we discussed • Gingivitis • Chronic…"` (~120–219 words) |

### metadata

| field | type | sample |
|---|---|---|
| `source` | str | `"synthea-fhir-r4"` |
| `synthetic` | bool | `True` |
| `patient_id` / `encounter_id` | str | `"3a3a1f26-…"` UUIDs |
| `encounter_reference` | str | `"urn:uuid:3a3a1f26-…faea"` |
| `date` | str | `"2022-08-05T05:19:56-07:00"` (ISO 8601 w/ tz) |
| `status` | str | `"finished"` |
| `visit_type` | str | `"General examination of patient (procedure)"` |
| `document_status` | str | `"current"` |
| `visit_title` | str | `"Annual physical — preventive screening and migraine check-in"` |
| `related_resource_counts` | dict | `{Condition:3, Observation:15, Procedure:6, DiagnosticReport:4, Immunization:2}` |

### patient_context.patient (FHIR Patient)

| field | type | sample |
|---|---|---|
| `resourceType` | str | `"Patient"` |
| `id` | str | `"3a3a1f26-…464"` |
| `name` | list | `[{use, family:"Kuhic", given:[…], prefix:[…]}]` |
| `gender` | str | `"male"` |
| `birthDate` | str | `"1991-05-24"` |
| `maritalStatus` | dict | `{coding:[…], text:"Never Married"}` |
| `address` | list | `[{city:"Chelsea", state:"MA", country:"US"}]` |
| `communication` | list | `[{language:{…}}]` |

### patient_context.longitudinal_summary (whole-chart background)

| field | type | sample |
|---|---|---|
| `resource_counts` | dict | `{Condition:25, Observation:84, Procedure:49, Encounter:22, …}` (14 types) |
| `condition_labels` | list[str] | `["Risk activity involvement (finding)", "Received higher education (finding)", …]` |
| `medication_labels` | list[str] | `[]` (empty here; populated for many patients) |

### encounter_fhir.encounter (FHIR Encounter)

`resourceType`, `id`, `status:"finished"`, `class:{system, code:"AMB"}`, `type:[…]`,
`subject:{reference, display:"Mr. … Kuhic920"}`, `participant:[…]`,
`period:{start, end}`, `location:[…]`, `serviceProvider:{…, display:"WHITLEY WELLNESS LLC"}`

### encounter_fhir.related_resources

A dict of lists, each a standard FHIR R4 resource, grouped by type
(`Condition`, `Observation`, `Procedure`, `DiagnosticReport`, `Immunization`,
`MedicationRequest`, `ImagingStudy`). Example **Observation**:

```json
{
  "resourceType": "Observation",
  "status": "final",
  "code": { "text": "Body mass index (BMI) [Ratio]" },
  "effectiveDateTime": "2022-08-05T05:19:56-07:00",
  "valueQuantity": { "value": 25.32, "unit": "kg/m2" }
}
```

Observation values can also appear as `valueCodeableConcept`, `valueString`, or
`component[]` (e.g. blood-pressure systolic/diastolic) — the notebook's `obs_value()`
helper handles all of these forms.

### after_visit_summary_provenance

```json
{
  "method": "deterministic_extractive_v1",
  "source": "clinical_note_assessment_and_plan",
  "review_status": "not_clinically_reviewed"
}
```

## Derived DataFrame (flat table for analysis)

The nested records aren't tabular, so `dataset_explore.ipynb` flattens them into a
DataFrame `df` — **one row per encounter, 10 columns**:

| column | type | sample |
|---|---|---|
| `date` | date | `2022-08-05` |
| `visit_title` | str | `"Annual physical — preventive screening…"` |
| `visit_type` | str | `"General examination of patient (procedure)"` |
| `gender` | str | `"male"` |
| `age` | int | `31` |
| `transcript_words` | int | `1485` |
| `note_words` | int | `555` |
| `avs_words` | int | `137` |
| `fhir_at_visit` | int | `30` |
| `chart_resources` | int | `260` |
