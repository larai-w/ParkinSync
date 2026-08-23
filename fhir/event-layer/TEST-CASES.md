# ParkinSync FHIR Event Layer — Test Cases

Version: 1.0 (2026-08-22)
Scope: synthetic-only event envelope validation, roundtrip, consent edge cases.
Constraint: no push/deploy. Test execution local only.

---

## TC-001: Medication event schema validation

- **Input:** `fixtures/medication-event.json`
- **Expected:** validates against `event-schema.json` with zero errors
- **Checks:**
  - `envelope_version` = `parkinsync-event-v1`
  - `event.event_type` = `medication`
  - `payload.dose_value` is number > 0
  - `payload.ucum_code` present
  - `consent.status` = `granted`

## TC-002: Symptom event schema validation

- **Input:** `fixtures/symptom-event.json`
- **Expected:** validates against `event-schema.json` with zero errors
- **Checks:**
  - `event.event_type` = `symptom`
  - `payload.symptom_code` in allowed enum
  - `payload.severity` within `0-4` scale bounds
  - `payload.severity_scale` = `0-4`

## TC-003: Wellbeing event schema validation

- **Input:** `fixtures/wellbeing-event.json`
- **Expected:** validates against `event-schema.json` with zero errors
- **Checks:**
  - `event.event_type` = `wellbeing`
  - `payload.score` within `1-5` scale bounds
  - `payload.dimension` present

## TC-004: Caregiver note event schema validation

- **Input:** `fixtures/caregiver-note-event.json`
- **Expected:** validates against `event-schema.json` with zero errors
- **Checks:**
  - `event.event_type` = `caregiver_note`
  - `payload.note_type` in allowed enum
  - `payload.related_event_ids` is array of strings

## TC-005: Mixed batch validation

- **Input:** `fixtures/mixed-batch.json`
- **Expected:** every element validates against `event-schema.json`
- **Checks:**
  - array length = 4
  - event types cover: medication, symptom, wellbeing, caregiver_note
  - all share same `export_batch_id`

## TC-006: Roundtrip serialization

- **Input:** each single-event fixture
- **Steps:**
  1. Parse JSON → object
  2. Serialize object → JSON string (stable key order)
  3. Re-parse → object
- **Expected:** deep-equal with original parsed object

## TC-007: Consent withdrawn rejection

- **Input:** synthetic mutation of `medication-event.json` with `consent.status` = `withdrawn`
- **Expected:** validation passes schema but export gate must block
- **Note:** export gate logic is out of scope for this layer; test documents expected behavior for downstream

## TC-008: Missing consent block rejection

- **Input:** synthetic mutation with `consent` removed
- **Expected:** schema validation fails (consent is required)

## TC-009: Invalid event_type rejection

- **Input:** synthetic mutation with `event.event_type` = `unknown_type`
- **Expected:** schema validation fails

## TC-010: Timestamp format validation

- **Input:** synthetic mutation with `event.occurred_at` = `2035-13-45T99:99:99Z` (invalid)
- **Expected:** schema validation fails (date-time format)

## TC-011: Classification must be synthetic

- **Input:** synthetic mutation with `classification` = `real`
- **Expected:** schema validation fails (enum constraint)

## TC-012: Event ID uniqueness within batch

- **Input:** `fixtures/mixed-batch.json`
- **Expected:** all `event.event_id` values are unique
- **Checks:** no duplicate IDs across 4 events

---

## Execution

```bash
cd /Users/irevail8/Developer/ParkinSync/fhir/event-layer
node --test roundtrip.test.mjs
```

## Open Questions (unresolved)

1. Should `caregiver_note.payload.content` have a max-length constraint?
2. Should `related_event_ids` be validated for referential integrity within the same batch?
3. Is `export_metadata.export_batch_id` required to match a batch manifest (future)?
4. Timezone in `export_metadata` — should it be constrained to IANA tz database names?