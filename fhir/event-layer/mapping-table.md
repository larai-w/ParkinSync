# ParkinSync Event → FHIR R4 Mapping Table

Version: 1.0.0 | Date: 2026-08-22 | Classification: synthetic-only

## Forward Mapping (Event → FHIR)

| Event Field | FHIR Resource | FHIR Path | Notes |
|---|---|---|---|
| event.event_id | All | .id | Direct mapping |
| event.occurred_at | MedicationStatement | .effectiveDateTime | ISO 8601 |
| event.occurred_at | Observation | .effectiveDateTime | ISO 8601 |
| event.occurred_at | DocumentReference | .context.period.start | For caregiver notes |
| event.recorded_at | All | .meta.lastUpdated | Provenance tracking |
| payload.medication_name | MedicationStatement | .medicationCodeableConcept.text | No RxNorm required (synthetic) |
| payload.dose_value + dose_unit | MedicationStatement | .dosage[0].dose | With UCUM code |
| payload.taken=true | MedicationStatement | .status="completed" | |
| payload.taken=false | MedicationStatement | .status="not-taken" | |
| payload.symptom_code | Observation | .code.coding[0].code | Custom CodeSystem |
| payload.severity | Observation | .valueQuantity.value | 0-4 scale |
| payload.context_note | Observation | .note[0].text | Omit if null |
| payload.score | Observation | .valueInteger | 1-5 scale |
| payload.dimension | Observation | .code.coding[0].code | wellbeing-dimensions CS |
| payload.note_type | DocumentReference | .type.coding[0].code | caregiver-note-types CS |
| payload.content | DocumentReference | .content[0].attachment.data | Base64-encoded UTF-8 |
| payload.caregiver_role | DocumentReference | .author[0].display | Format: "Synthetic caregiver ({role} role)" |
| payload.related_event_ids | DocumentReference | .context.related[].reference | Type-prefixed: Observation/evt-... |
| consent (all) | Bundle | .entry[].resource.meta.tag | Tag: consent-status |
| classification | All | .extension[event-provenance] | Always "synthetic\|..." |

## Reverse Mapping (FHIR → Event)

| FHIR Path | Event Field | Notes |
|---|---|---|
| .id | event.event_id | Direct |
| .effectiveDateTime | event.occurred_at | Normalize timezone |
| .medicationCodeableConcept.text | payload.medication_name | |
| .dosage[0].dose.value | payload.dose_value | |
| .dosage[0].dose.unit | payload.dose_unit | |
| .dosage[0].dose.code | payload.ucum_code | |
| .status="completed" | payload.taken=true | |
| .status="not-taken" | payload.taken=false | |
| .code.coding[0].code | payload.symptom_code / dimension | Context-dependent |
| .valueQuantity.value | payload.severity | |
| .valueInteger | payload.score | |
| .note[0].text | payload.context_note / note | Null if absent |
| .type.coding[0].code | payload.note_type | |
| .content[0].attachment.data | payload.content | Base64 decode |
| .context.related[].reference | payload.related_event_ids | Strip type prefix |
| .extension[event-provenance] | classification + source | Parse pipe-delimited |

## CodeSystems (Synthetic)

| CodeSystem URI | Codes |
|---|---|
| parkinsync.example/fhir/CodeSystem/symptom-types | tremor, rigidity, bradykinesia, dyskinesia, sleep_disturbance, fatigue, other |
| parkinsync.example/fhir/CodeSystem/wellbeing-dimensions | overall, physical, emotional, social |
| parkinsync.example/fhir/CodeSystem/caregiver-note-types | observation, concern, routine, communication |
| parkinsync.example/fhir/CodeSystem/severity-scale | 0-4 |

## Provenance Extension

URL: `https://parkinsync.example/fhir/StructureDefinition/event-provenance`  
Format: `{classification}|{source}|{schema_version}`  
Example: `synthetic|self-reported|v1.0.0`

Sources: app-recorded, self-reported, caregiver-reported, device-sync

## Unresolved / Human Gates

- [ ] JP Core profile conformance level (informational vs strict)
- [ ] Whether DocumentReference or Communication resource is better for caregiver notes
- [ ] Consent tag system URI registration
- [ ] Cross-project event vocabulary alignment (GutPacer, Medication Promise)