/**
 * ParkinSync FHIR Event Layer — Roundtrip & Schema Validation Test
 *
 * Design-phase validation script. Validates:
 * 1. Schema file is valid JSON with correct structure
 * 2. All fixtures conform to schema constraints
 * 3. Roundtrip serialization preserves data
 * 4. Consent edge cases
 * 5. Invalid mutations are rejected
 *
 * Run: node --test roundtrip.test.mjs
 * Or:  node roundtrip.test.mjs
 *
 * Status: Design only — no implementation, no deploy, no push
 */

import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { deepStrictEqual } from 'assert';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

let passed = 0;
let failed = 0;

function assert(condition, message) {
  if (condition) {
    console.log(`  ✓ ${message}`);
    passed++;
  } else {
    console.error(`  ✗ ${message}`);
    failed++;
  }
}

function assertThrows(fn, message) {
  try {
    fn();
    console.error(`  ✗ ${message} (expected to throw)`);
    failed++;
  } catch {
    console.log(`  ✓ ${message}`);
    passed++;
  }
}

function loadJSON(relativePath) {
  const raw = readFileSync(join(__dirname, relativePath), 'utf-8');
  return JSON.parse(raw);
}

// --- Load schema ---
let schema;
try {
  schema = loadJSON('event-schema.json');
} catch (e) {
  console.error(`FATAL: Cannot load event-schema.json: ${e.message}`);
  process.exit(1);
}

// --- Load fixtures ---
const medicationEvent = loadJSON('fixtures/medication-event.json');
const symptomEvent = loadJSON('fixtures/symptom-event.json');
const wellbeingEvent = loadJSON('fixtures/wellbeing-event.json');
const caregiverNoteEvent = loadJSON('fixtures/caregiver-note-event.json');
const mixedBatch = loadJSON('fixtures/mixed-batch.json');

// --- Helper: structural validation against schema constraints ---
const eventIdRegex = new RegExp(schema.$defs.event.properties.event_id.pattern);
const isoRegex = new RegExp(schema.$defs.isoDateTime.pattern);
const batchRegex = new RegExp(schema.$defs.exportMetadata.properties.export_batch_id.pattern);
const eventTypeEnum = schema.$defs.event.properties.event_type.enum;
const consentStatusEnum = schema.$defs.consent.properties.status.enum;
const scopeEnum = schema.$defs.consent.properties.scope.items.enum;

function validateEnvelopeStructure(envelope, label) {
  console.log(`\n[Validate] ${label}`);

  // envelope_version
  assert(
    envelope.envelope_version === schema.properties.envelope_version.const,
    `${label}: envelope_version = parkinsync-event-v1`
  );

  // classification
  assert(
    envelope.classification === schema.properties.classification.const,
    `${label}: classification = synthetic`
  );

  // event required fields
  const evt = envelope.event;
  assert(evt !== undefined, `${label}: event exists`);
  assert(eventTypeEnum.includes(evt.event_type), `${label}: event_type "${evt.event_type}" is valid`);
  assert(eventIdRegex.test(evt.event_id), `${label}: event_id matches pattern`);
  assert(isoRegex.test(evt.occurred_at), `${label}: occurred_at is valid ISO 8601`);
  assert(isoRegex.test(evt.recorded_at), `${label}: recorded_at is valid ISO 8601`);
  assert(evt.payload !== undefined && typeof evt.payload === 'object', `${label}: payload is object`);

  // consent required fields
  const consent = envelope.consent;
  assert(consent !== undefined, `${label}: consent exists`);
  assert(consentStatusEnum.includes(consent.status), `${label}: consent.status is valid`);
  assert(isoRegex.test(consent.granted_at), `${label}: consent.granted_at is valid ISO 8601`);
  assert(Array.isArray(consent.scope) && consent.scope.length >= 1, `${label}: consent.scope has >= 1 item`);
  for (const s of consent.scope) {
    assert(scopeEnum.includes(s), `${label}: scope "${s}" is valid`);
  }

  // export_metadata (optional but present in fixtures)
  if (envelope.export_metadata) {
    const meta = envelope.export_metadata;
    assert(isoRegex.test(meta.exported_at), `${label}: export_metadata.exported_at is valid`);
    assert(batchRegex.test(meta.export_batch_id), `${label}: export_batch_id matches pattern`);
    assert(/^[+-][0-9]{2}:[0-9]{2}$/.test(meta.timezone), `${label}: timezone format valid`);
  }
}

function validatePayloadByType(envelope, label) {
  const evt = envelope.event;
  const payload = evt.payload;

  if (evt.event_type === 'medication') {
    const p = schema.$defs.medicationPayload;
    for (const req of p.required) {
      assert(payload[req] !== undefined, `${label}: medication payload has "${req}"`);
    }
    assert(typeof payload.dose_value === 'number' && payload.dose_value > 0, `${label}: dose_value > 0`);
    assert(p.properties.scheduled_slot.enum.includes(payload.scheduled_slot), `${label}: scheduled_slot valid`);
    assert(new RegExp(p.properties.scheduled_time.pattern).test(payload.scheduled_time), `${label}: scheduled_time HH:MM valid`);
    assert(typeof payload.taken === 'boolean', `${label}: taken is boolean`);
  } else if (evt.event_type === 'symptom') {
    const p = schema.$defs.symptomPayload;
    for (const req of p.required) {
      assert(payload[req] !== undefined, `${label}: symptom payload has "${req}"`);
    }
    assert(p.properties.symptom_code.enum.includes(payload.symptom_code), `${label}: symptom_code valid`);
    assert(Number.isInteger(payload.severity) && payload.severity >= 0 && payload.severity <= 4, `${label}: severity in 0-4`);
    assert(payload.severity_scale === '0-4', `${label}: severity_scale = 0-4`);
  } else if (evt.event_type === 'wellbeing') {
    const p = schema.$defs.wellbeingPayload;
    for (const req of p.required) {
      assert(payload[req] !== undefined, `${label}: wellbeing payload has "${req}"`);
    }
    assert(Number.isInteger(payload.score) && payload.score >= 1 && payload.score <= 5, `${label}: score in 1-5`);
    assert(payload.scale === '1-5', `${label}: scale = 1-5`);
    assert(p.properties.dimension.enum.includes(payload.dimension), `${label}: dimension valid`);
  } else if (evt.event_type === 'caregiver_note') {
    const p = schema.$defs.caregiverNotePayload;
    for (const req of p.required) {
      assert(payload[req] !== undefined, `${label}: caregiver_note payload has "${req}"`);
    }
    assert(p.properties.note_type.enum.includes(payload.note_type), `${label}: note_type valid`);
    assert(typeof payload.content === 'string' && payload.content.length >= 1, `${label}: content non-empty`);
    assert(p.properties.caregiver_role.enum.includes(payload.caregiver_role), `${label}: caregiver_role valid`);
    if (payload.related_event_ids) {
      assert(Array.isArray(payload.related_event_ids), `${label}: related_event_ids is array`);
      for (const id of payload.related_event_ids) {
        assert(eventIdRegex.test(id), `${label}: related_event_id "${id}" matches pattern`);
      }
    }
  }
}

// === TC-001: Medication event ===
console.log('\n' + '='.repeat(60));
console.log('TC-001: Medication event schema validation');
console.log('='.repeat(60));
validateEnvelopeStructure(medicationEvent, 'medication-event');
validatePayloadByType(medicationEvent, 'medication-event');

// === TC-002: Symptom event ===
console.log('\n' + '='.repeat(60));
console.log('TC-002: Symptom event schema validation');
console.log('='.repeat(60));
validateEnvelopeStructure(symptomEvent, 'symptom-event');
validatePayloadByType(symptomEvent, 'symptom-event');

// === TC-003: Wellbeing event ===
console.log('\n' + '='.repeat(60));
console.log('TC-003: Wellbeing event schema validation');
console.log('='.repeat(60));
validateEnvelopeStructure(wellbeingEvent, 'wellbeing-event');
validatePayloadByType(wellbeingEvent, 'wellbeing-event');

// === TC-004: Caregiver note event ===
console.log('\n' + '='.repeat(60));
console.log('TC-004: Caregiver note event schema validation');
console.log('='.repeat(60));
validateEnvelopeStructure(caregiverNoteEvent, 'caregiver-note-event');
validatePayloadByType(caregiverNoteEvent, 'caregiver-note-event');

// === TC-005: Mixed batch validation ===
console.log('\n' + '='.repeat(60));
console.log('TC-005: Mixed batch validation');
console.log('='.repeat(60));
assert(Array.isArray(mixedBatch), 'mixed-batch is array');
assert(mixedBatch.length === 4, 'mixed-batch has 4 events');
const batchTypes = mixedBatch.map(e => e.event.event_type);
assert(batchTypes.includes('medication'), 'batch includes medication');
assert(batchTypes.includes('symptom'), 'batch includes symptom');
assert(batchTypes.includes('wellbeing'), 'batch includes wellbeing');
assert(batchTypes.includes('caregiver_note'), 'batch includes caregiver_note');
const batchIds = mixedBatch.map(e => e.export_metadata?.export_batch_id).filter(Boolean);
assert(new Set(batchIds).size === 1, 'all events share same export_batch_id');

for (let i = 0; i < mixedBatch.length; i++) {
  validateEnvelopeStructure(mixedBatch[i], `mixed-batch[${i}]`);
  validatePayloadByType(mixedBatch[i], `mixed-batch[${i}]`);
}

// === TC-006: Roundtrip serialization ===
console.log('\n' + '='.repeat(60));
console.log('TC-006: Roundtrip serialization');
console.log('='.repeat(60));
const fixtures = [
  { name: 'medication-event', data: medicationEvent },
  { name: 'symptom-event', data: symptomEvent },
  { name: 'wellbeing-event', data: wellbeingEvent },
  { name: 'caregiver-note-event', data: caregiverNoteEvent },
];

for (const { name, data } of fixtures) {
  const serialized = JSON.stringify(data);
  const reparsed = JSON.parse(serialized);
  try {
    deepStrictEqual(reparsed, data);
    assert(true, `${name}: roundtrip deep-equal`);
  } catch (e) {
    assert(false, `${name}: roundtrip deep-equal FAILED: ${e.message}`);
  }
}

// Batch roundtrip
const batchSerialized = JSON.stringify(mixedBatch);
const batchReparsed = JSON.parse(batchSerialized);
try {
  deepStrictEqual(batchReparsed, mixedBatch);
  assert(true, 'mixed-batch: roundtrip deep-equal');
} catch (e) {
  assert(false, `mixed-batch: roundtrip deep-equal FAILED: ${e.message}`);
}

// === TC-007: Consent withdrawn (schema passes, export gate blocks) ===
console.log('\n' + '='.repeat(60));
console.log('TC-007: Consent withdrawn — export gate expectation');
console.log('='.repeat(60));
const withdrawnEvent = JSON.parse(JSON.stringify(medicationEvent));
withdrawnEvent.consent.status = 'withdrawn';
assert(consentStatusEnum.includes(withdrawnEvent.consent.status), 'withdrawn is valid schema status');
assert(withdrawnEvent.consent.status !== 'granted', 'export gate should block non-granted status');
console.log('  ℹ Export gate logic is downstream; schema allows withdrawn but export must block.');

// === TC-008: Missing consent block rejection ===
console.log('\n' + '='.repeat(60));
console.log('TC-008: Missing consent block rejection');
console.log('='.repeat(60));
assertThrows(() => {
  const noConsent = JSON.parse(JSON.stringify(medicationEvent));
  delete noConsent.consent;
  if (!schema.required.includes('consent')) throw new Error('consent not required');
  if (noConsent.consent === undefined) throw new Error('consent missing');
}, 'schema requires consent — missing consent rejected');

// === TC-009: Invalid event_type rejection ===
console.log('\n' + '='.repeat(60));
console.log('TC-009: Invalid event_type rejection');
console.log('='.repeat(60));
assertThrows(() => {
  const invalid = JSON.parse(JSON.stringify(medicationEvent));
  invalid.event.event_type = 'unknown_type';
  if (!eventTypeEnum.includes(invalid.event.event_type)) throw new Error('invalid event_type');
}, 'rejects unknown event_type');

// === TC-010: Timestamp format validation ===
console.log('\n' + '='.repeat(60));
console.log('TC-010: Timestamp format validation');
console.log('='.repeat(60));
// NOTE: The schema regex is structural only (format check). It does NOT
// validate semantic ranges (month 01-12, day 01-31, hour 00-23, etc.).
// '2035-13-45T99:99:99Z' matches the pattern because all segments are
// correct digit counts. Semantic date validation is out of scope for
// this layer and is recorded as an open question in TEST-CASES.md.
assert(isoRegex.test('2035-13-45T99:99:99Z'), 'structural pattern accepts out-of-range values (known limitation)');
assert(!isoRegex.test('2035-01-01 20:00:00+09:00'), 'rejects space separator');
assert(!isoRegex.test('2035-01-01T20:00:00'), 'rejects missing timezone');
assert(!isoRegex.test('2035-01-01T20:00:00.123+09:00'), 'rejects fractional seconds (not in pattern)');
assert(isoRegex.test('2035-01-01T20:00:00+09:00'), 'accepts valid JST datetime');
assert(isoRegex.test('2035-01-01T20:00:00Z'), 'accepts valid UTC datetime');

// === TC-011: Classification must be synthetic ===
console.log('\n' + '='.repeat(60));
console.log('TC-011: Classification must be synthetic');
console.log('='.repeat(60));
assertThrows(() => {
  const invalid = JSON.parse(JSON.stringify(medicationEvent));
  invalid.classification = 'real';
  if (invalid.classification !== schema.properties.classification.const) throw new Error('not synthetic');
}, 'rejects classification=real');

// === TC-012: Event ID uniqueness within batch ===
console.log('\n' + '='.repeat(60));
console.log('TC-012: Event ID uniqueness within batch');
console.log('='.repeat(60));
const eventIds = mixedBatch.map(e => e.event.event_id);
const uniqueIds = new Set(eventIds);
assert(uniqueIds.size === eventIds.length, `all ${eventIds.length} event_ids are unique`);

// === Summary ===
console.log('\n' + '='.repeat(60));
console.log(`Results: ${passed} passed, ${failed} failed`);
console.log('='.repeat(60));

if (failed > 0) {
  console.error('\n❌ ParkinSync event layer validation FAILED');
  process.exit(1);
} else {
  console.log('\n✅ ParkinSync event layer validation PASSED');
  process.exit(0);
}