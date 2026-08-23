# ParkinSync Synthetic FHIR Event Layer Design

Version: 1.0.0  
Date: 2026-08-22  
Status: Draft for Qwen implementation  
Classification: synthetic-only / research-assetization

## 1. Purpose

Extend ParkinSync's existing FHIR R4 adapter from static daily/weekly records to an **event-stream architecture** that supports:
- Medication events (existing, extended)
- Symptom events (new)
- Wellbeing events (new)
- Caregiver note events (new)

All data is **synthetic-only**. No real patient data, no EHR connection, no diagnostic/treatment claims.

## 2. Scope Boundaries

| Allowed | Not Allowed |
|---------|-------------|
| Synthetic event schema design | Real patient data |
| FHIR R4 resource mapping | EHR/PHR live connection |
| Round-trip validation tests | Diagnostic assertions |
| Provenance tracking | Treatment recommendations |
| Consent metadata fields | External data transmission |
| Versioned export contract | Production deployment |

## 3. Event Types

### 3.1 Medication Event (existing, extended)

```json
{
  "event_type": "medication",
  "event_id": "evt-med-20350101-001",
  "occurred_at": "2035-01-01T07:05:00+09:00",
  "recorded_at": "2035-01-01T07:06:00+09:00",
  "payload": {
    "medication_name": "Synthetic demonstration medicine A",
    "dose_value": 100,
    "dose_unit": "mg",
    "ucum_code": "mg",
    "scheduled_slot": "morning",
    "scheduled_time": "07:00",
    "taken": true,
    "reason_if_missed": null
  }
}
```

### 3.2 Symptom Event (new)

```json
{
  "event_type": "symptom",
  "event_id": "evt-sym-20350101-001",
  "occurred_at": "2035-01-01T14:30:00+09:00",
  "recorded_at": "2035-01-01T14:35:00+09:00",
  "payload": {
    "symptom_code": "tremor",
    "severity": 2,
    "severity_scale": "0-4",
    "duration_minutes": 15,
    "context_note": "synthetic note for testing",
    "laterality": null
  }
}
```

Supported symptom codes (synthetic vocabulary):
- `tremor` - subjective tremor report
- `rigidity` - subjective stiffness report
- `bradykinesia` - subjective slowness report
- `dyskinesia` - involuntary movement report
- `sleep_disturbance` - sleep quality issue
- `fatigue` - tiredness report
- `other` - requires `context_note`

### 3.3 Wellbeing Event (new)

```json
{
  "event_type": "wellbeing",
  "event_id": "evt-wb-20350101-001",
  "occurred_at": "2035-01-01T20:00:00+09:00",
  "recorded_at": "2035-01-01T20:01:00+09:00",
  "payload": {
    "score": 4,
    "scale": "1-5",
    "dimension": "overall",
    "note": "synthetic wellbeing note"
  }
}
```

Wellbeing dimensions:
- `overall` - general daily wellbeing
- `physical` - physical comfort
- `emotional` - mood state
- `social` - social interaction quality

### 3.4 Caregiver Note Event (new)

```json
{
  "event_type": "caregiver_note",
  "event_id": "evt-cg-20350101-001",
  "occurred_at": "2035-01-01T18:00:00+09:00",
  "recorded_at": "2035-01-01T18:05:00+09:00",
  "payload": {
    "note_type": "observation",
    "content": "Synthetic caregiver observation for testing",
    "caregiver_role": "family",
    "related_event_ids": ["evt-sym-20350101-001"]
  }
}
```

Note types:
- `observation` - factual observation
- `concern` - worry or concern (flagged for review)
- `routine` - routine care activity
- `communication` - communication with care team

## 4. FHIR R4 Mapping

### 4.1 Mapping Table

| Event Type | FHIR Resource | Key Fields | Profile |
|------------|---------------|------------|---------|
| medication | MedicationStatement | medication, effectiveDateTime, status | JP Core MedicationStatement |
| symptom | Observation | code, valueQuantity/valueCodeableConcept, note | Observation (subjective) |
| wellbeing | Observation | code (custom), valueInteger, interpretation | Observation (survey) |
| caregiver_note | DocumentReference | content, type, context | JP Core DocumentReference |

### 4.2 Medication → MedicationStatement

```json
{
  "resourceType": "MedicationStatement",
  "id": "evt-med-20350101-001",
  "status": "completed",
  "medicationCodeableConcept": {
    "text": "Synthetic demonstration medicine A"
  },
  "subject": { "reference": "Patient/synthetic-patient-001" },
  "effectiveDateTime": "2035-01-01T07:05:00+09:00",
  "dosage": [{
    "text": "100 mg",
    "dose": {
      "value": 100,
      "unit": "mg",
      "code": "mg"
    }
  }],
  "extension": [{
    "url": "https://parkinsync.example/fhir/StructureDefinition/event-provenance",
    "valueString": "synthetic|app-recorded|v1.0.0"
  }]
}
```

Status mapping:
- `taken: true` → `status: "completed"`
- `taken: false` → `status: "not-taken"`

### 4.3 Symptom → Observation

```json
{
  "resourceType": "Observation",
  "id": "evt-sym-20350101-001",
  "status": "final",
  "category": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/observation-category",
      "code": "survey",
      "display": "Survey"
    }]
  }],
  "code": {
    "coding": [{
      "system": "https://parkinsync.example/fhir/CodeSystem/symptom-types",
      "code": "tremor",
      "display": "Subjective tremor report"
    }],
    "text": "Tremor severity (synthetic scale)"
  },
  "subject": { "reference": "Patient/synthetic-patient-001" },
  "effectiveDateTime": "2035-01-01T14:30:00+09:00",
  "valueQuantity": {
    "value": 2,
    "unit": "severity score",
    "system": "https://parkinsync.example/fhir/CodeSystem/severity-scale",
    "code": "0-4"
  },
  "note": [{
    "text": "synthetic note for testing"
  }],
  "extension": [{
    "url": "https://parkinsync.example/fhir/StructureDefinition/event-provenance",
    "valueString": "synthetic|self-reported|v1.0.0"
  }]
}
```

### 4.4 Wellbeing → Observation

```json
{
  "resourceType": "Observation",
  "id": "evt-wb-20350101-001",
  "status": "final",
  "category": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/observation-category",
      "code": "survey",
      "display": "Survey"
    }]
  }],
  "code": {
    "coding": [{
      "system": "https://parkinsync.example/fhir/CodeSystem/wellbeing-dimensions",
      "code": "overall",
      "display": "Overall wellbeing"
    }],
    "text": "Wellbeing score (1-5 synthetic scale)"
  },
  "subject": { "reference": "Patient/synthetic-patient-001" },
  "effectiveDateTime": "2035-01-01T20:00:00+09:00",
  "valueInteger": 4,
  "interpretation": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
      "code": "N",
      "display": "Normal"
    }]
  }],
  "extension": [{
    "url": "https://parkinsync.example/fhir/StructureDefinition/event-provenance",
    "valueString": "synthetic|self-reported|v1.0.0"
  }]
}
```

Interpretation mapping (synthetic, non-clinical):
- 1-2 → `"L"` (Low)
- 3 → `"N"` (Normal)
- 4-5 → `"H"` (High)

### 4.5 Caregiver Note → DocumentReference

```json
{
  "resourceType": "DocumentReference",
  "id": "evt-cg-20350101-001",
  "status": "current",
  "type": {
    "coding": [{
      "system": "https://parkinsync.example/fhir/CodeSystem/caregiver-note-types",
      "code": "observation",
      "display": "Caregiver observation"
    }]
  },
  "subject": { "reference": "Patient/synthetic-patient-001" },
  "date": "2035-01-01T18:05:00+09:00",
  "author": [{
    "display": "Synthetic caregiver (family role)"
  }],
  "content": [{
    "attachment": {
      "contentType": "text/plain",
      "data": "U3ludGhldGljIGNhcmVnaXZlciBvYnNlcnZhdGlvbiBmb3IgdGVzdGluZw=="
    }
  }],
  "context": {
    "related": [{
      "reference": "Observation/evt-sym-20350101-001"
    }]
  },
  "extension": [{
    "url": "https://parkinsync.example/fhir/StructureDefinition/event-provenance",
    "valueString": "synthetic|caregiver-reported|v1.0.0"
  }]
}
```

## 5. Provenance & Consent

### 5.1 Provenance Extension

Every exported resource includes:
```
https://parkinsync.example/fhir/StructureDefinition/event-provenance
```

Format: `{classification}|{source}|{schema_version}`
- classification: always `synthetic`
- source: `app-recorded`, `self-reported`, `caregiver-reported`, `device-sync`
- schema_version: semver of event schema

### 5.2 Consent Metadata

Event envelope includes consent block:
```json
{
  "consent": {
    "status": "granted",
    "granted_at": "2035-01-01T00:00:00+09:00",
    "scope": ["research-export", "local-analysis"],
    "withdrawal_mechanism": "app-settings"
  }
}
```

Consent statuses:
- `granted` - export allowed
- `pending` - export blocked, local only
- `withdrawn` - export blocked, flag for deletion review

## 6. Event Envelope Schema

All events are wrapped in an envelope:

```json
{
  "envelope_version": "parkinsync-event-v1",
  "classification": "synthetic",
  "event": { ... },
  "consent": { ... },
  "export_metadata": {
    "exported_at": "2035-01-02T00:00:00+09:00",
    "export_batch_id": "batch-20350102-001",
    "timezone": "+09:00"
  }
}
```

## 7. Round-trip Requirements

For each event type:
1. Event JSON → FHIR Resource (forward mapping)
2. FHIR Resource → Event JSON (reverse mapping)
3. Assert: reverse(forward(event)) == event (semantic equality)

Semantic equality rules:
- Timestamps normalized to ISO 8601 with timezone
- Null fields omitted in both directions
- Extension fields preserved but not compared in payload

## 8. Test Categories

### 8.1 Schema Validation Tests
- Valid event passes schema validation
- Missing required field fails with clear error
- Invalid enum value fails
- Timestamp format validation

### 8.2 Round-trip Tests
- Each event type: forward → reverse → compare
- Batch of mixed events: all round-trip correctly
- Edge cases: empty notes, null optional fields

### 8.3 Missing Data Tests
- Event with missing `context_note` exports without note
- Event with missing `severity` exports as valueCodeableConcept only
- Caregiver note with empty `related_event_ids` exports without context.related

### 8.4 Consent Tests
- `consent.status: "withdrawn"` → export blocked, error returned
- `consent.status: "pending"` → local storage only, no export bundle
- Consent withdrawal after export → flag in manifest for review

### 8.5 Provenance Tests
- All exported resources contain provenance extension
- Provenance format matches `{classification}|{source}|{version}`
- Classification is always `synthetic` (never `real`, `patient`, etc.)

## 9. File Structure

```
fhir/
├── event-layer/
│   ├── EVENT-LAYER-DESIGN.md (this file)
│   ├── event-schema.json
│   ├── mapping-table.md
│   ├── TEST-CASES.md
│   └── fixtures/
│       ├── medication-event.json
│       ├── symptom-event.json
│       ├── wellbeing-event.json
│       ├── caregiver-note-event.json
│       └── mixed-batch.json
├── synthetic_normalized_record.json (existing)
└── weekly/ (existing)
```

## 10. Implementation Notes for Qwen

1. **Do not modify** existing `synthetic_normalized_record.json` or weekly records
2. Create new files only in `fhir/event-layer/`
3. Use Node.js ESM for test scripts if needed
4. All test data must use `classification: "synthetic"`
5. No network calls, no external APIs
6. Report: changed files, test results, unresolved issues, human gates

## 11. Human Gates

Before any merge to main:
- [ ] Design review by human owner
- [ ] Consent flow validation
- [ ] Privacy boundary confirmation (no PII in synthetic data)
- [ ] Cross-project compatibility check (GutPacer, Medication Promise)