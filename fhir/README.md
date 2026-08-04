# ParkinSync FHIR R4 interoperability demo

This directory demonstrates an offline adapter from an explicit, synthetic ParkinSync normalized
record to HL7 FHIR R4.0.1. It generates six resource instances across four resource types,
`Patient`, `MedicationStatement`, `Observation`, and `CarePlan`, plus a deterministic transaction
`Bundle` containing those resources.

The demo is a software interoperability artifact, not a clinical record, medical device, or claim of
conformance with a national implementation guide. The generators are offline. A separate integration
test sends only the tracked synthetic weekly Bundle to a disposable, runner-local HAPI server.

## Why the adapter uses an explicit normalized record

The current 25-column ParkinSync ledger contains medication windows and caregiver observations, but it
does not contain every semantic field required for a faithful FHIR mapping. In particular, a time in
`Morning` does not establish the medication identity, dose, or whether a scheduled dose was taken.
`Switchbot_Avg` is ambient room temperature, not body temperature.

The v1 adapter therefore refuses to infer those facts. The public input fixture supplies the missing
fields explicitly and remains separate from participant or production data. A future production
adapter would require an approved source contract, consent and access controls, and jurisdiction-
specific profile review.

## Pipeline

```text
synthetic_normalized_record.json
  -> src/fhir_export.py
  -> fhir.resources 6.4.0 (FHIR 4.0.1 models)
  -> deterministic JSON resources + transaction Bundle + manifest
  -> model, transaction, reference, provenance, and reproducibility tests
  -> HL7 Validator CLI 6.10.0 (offline terminology mode in CI)
  -> deterministic fact bundle, data-quality gate, and grounded offline summary
  -> separate seven-day transaction, aggregate facts, missingness, and weekly summary
  -> pinned ephemeral HAPI transaction + 30-resource semantic read-back check
  -> shared jurisdiction overlay contract
       -> NZ Base 3.1.0 Patient/MedicationStatement validation
       -> JP Core 1.2.0 Patient/VitalSigns Observation validation
```

## Mapping

| Normalized input | FHIR R4 target | Coding or rule |
|---|---|---|
| `classification=synthetic` | `meta.tag` on every resource | Local data-classification code system; input is rejected otherwise |
| `patient.id` | `Patient.id` and every `subject.reference` | Deterministic ID prefixed `synthetic-` |
| `patient.identifier` | `Patient.identifier` | Temporary identifier in the demo-only VEAI identifier system |
| `medications[].name` | `MedicationStatement.medicationCodeableConcept.text` | Text only; no RxNorm code is invented |
| `medications[].taken` | `MedicationStatement.status` | `true` -> `completed`; `false` -> `not-taken` |
| `medications[].dose` | `MedicationStatement.dosage.doseAndRate.doseQuantity` | Explicit value and UCUM unit from input |
| `recorded_date` + `scheduled_time` + `timezone` | `effectiveDateTime`, `dateAsserted`, `dosage.timing.event` | ISO 8601 timestamp with UTC offset |
| `observations[kind=body-temperature]` | `Observation` | LOINC `8310-5`; UCUM `Cel` |
| `observations[kind=heart-rate]` | `Observation` | LOINC `8867-4`; UCUM `/min` |
| `care_plan.*` | `CarePlan` status, intent, title, description, period, activity | Explicit synthetic plan fields; no diagnosis or treatment recommendation |

## Transaction Bundle

The generated Bundle has `type=transaction`. Every entry contains:

- a deterministic and unique `urn:uuid` `fullUrl`;
- the complete synthetic resource;
- a `PUT` request whose URL exactly matches `ResourceType/id`; and
- internal Patient references rewritten to the Patient entry's `fullUrl`.

The adapter checks fullUrl uniqueness, request/resource identity, and reference resolution before
serialization. It does not perform network I/O. The separate [ephemeral server test](server/README.md)
tests the client-assigned logical IDs against one pinned HAPI configuration without implying that an
arbitrary target server will accept them.

LOINC codes are limited to the reviewed mappings above. Unsupported observation kinds fail instead of
falling back to a guessed code. The source references are the official
[FHIR R4 resource definitions](https://hl7.org/fhir/R4/resourcelist.html),
[LOINC 8310-5](https://loinc.org/8310-5/), and
[LOINC 8867-4](https://loinc.org/8867-4/).

## Current 25-column gaps

| Existing ParkinSync field | v1 decision |
|---|---|
| `Morning`, `Lunch`, `Evening`, `Bedtime`, `Bedtime_2` | Not converted without explicit medication identity, dose, and taken/not-taken state |
| `Bowel`, `Movi`, `Condition_C`, `Condition_Num`, event flags | Not assigned a LOINC or SNOMED CT code until the concept definitions and terminology mapping are reviewed |
| `Daily_Notes` | Not exported; free text can carry identifying or unsupported clinical content |
| Weather and `Switchbot_*` | Not represented as patient vital signs; they are environmental context |
| Patient and care-plan fields | Absent from the ledger; supplied only by the synthetic demo contract |

## Run and validate

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-fhir.txt

python scripts/export_synthetic_fhir.py --check
PYTHONPATH=src python -m unittest tests.test_fhir_export -v

# Requires Java 17+ and a separately downloaded pinned validator_cli.jar.
FHIR_VALIDATOR_JAR=/path/to/validator_cli.jar scripts/validate_fhir_r4.sh

# No model or network access is used.
PYTHONPATH=src python scripts/generate_grounded_summary.py --check
```

`fhir.resources` validates FHIR R4 model structure, data types, cardinalities implemented by the model,
and required fields. ParkinSync additionally checks resource IDs, required resource types, synthetic
classification, and transaction references. CI also runs HL7 Validator CLI `6.10.0`, whose JAR is
downloaded from the versioned official release and checked against a pinned SHA-256 digest. The
validator runs with `-tx n/a`, so the gate covers base R4 parsing, structure, and FHIRPath invariants
without relying on a public terminology server.

The base artifacts in this directory are not implementation-guide or terminology-server validation,
clinical review, or regulatory certification. Separate [NZ Base](nzbase/README.md) and
[JP Core](jpcore/README.md) tracks derive synthetic Bundles through one shared fail-closed overlay
contract. Each jurisdiction keeps a distinct profile map and no-inference boundary. National patient
summaries, identity integration, terminology services, and full use-case contracts remain separate
design and governance decisions.

The separate [grounded-summary experiment](summary/README.md) consumes the validated transaction
Bundle. It retains FHIRPath provenance, calculates data-quality findings without a model, and requires
fact citations and exact numeric consistency before returning a human-review-only result.

The [seven-day evidence extension](weekly/README.md) generates 30 resources across one explicit
synthetic week. It calculates medication counts and Observation ranges without an LLM, retains every
source fact ID and aggregation method, and returns no narrative when a day or expected event is missing.

The [ephemeral HAPI round trip](server/README.md) submits that synthetic weekly Bundle inside CI,
checks every transaction response, reads all 30 resources back, and permits only documented
server-managed metadata and reference-resolution differences.

The [NZ Base profile-validation track](nzbase/README.md) adds only reviewed `meta.profile`
declarations to a derivative of the weekly Bundle. It explicitly leaves Observation and CarePlan at
base R4 and refuses to fabricate an NHI, NZ-specific demographics, or NZMT coding.

The [JP Core profile-validation track](jpcore/README.md) applies the same shared overlay contract to
Patient and VitalSigns Observation. It leaves MedicationStatement at base R4 because the written JP
Core guidance requires Japanese medication coding that the source does not contain.
