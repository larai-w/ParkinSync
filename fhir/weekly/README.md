# Seven-day synthetic FHIR evidence

This directory extends the one-day FHIR R4 interoperability demo to an explicit seven-day window.
Generation and summary remain synthetic, offline, descriptive, and human-review-only. The tracked
Bundle is also sent to a disposable, runner-local HAPI server by a separate integration test; no
participant or production record is sent. No value is interpreted as diagnosis, treatment evidence,
or a medication effect.

## Reviewed input contract

`synthetic-weekly-records.json` declares:

- one synthetic Patient and one seven-day CarePlan;
- two explicit medication schedules with dose, UCUM unit, time, and daily taken/not-taken values;
- two reviewed Observation schedules, body temperature and heart rate, with an explicit value for
  every day;
- the fixed analysis window `2035-01-01` through `2035-01-07`; and
- an explicit material-corrections array, empty for the tracked fixture.

The year 2035 is a conspicuous publication-safety marker. It is not a forecast or real care period.
The generator refuses to infer a missing adherence value or Observation value.

## Generated evidence

`scripts/generate_weekly_fhir.py` produces four deterministic files under `generated/`:

| Artifact | Evidence |
|---|---|
| `bundle-synthetic-weekly-transaction-bundle.json` | FHIR R4 transaction with 1 Patient, 14 MedicationStatement, 14 Observation, and 1 CarePlan resources |
| `fact-bundle.json` | 28 event facts plus 3 weekly aggregate facts with stable IDs and source provenance |
| `weekly-summary.json` | Three plain-language statements plus structured window, source, count, missingness, and correction metadata |
| `manifest.json` | Resource counts, status, generator, file inventory, and SHA-256 digests |

The transaction keeps deterministic `urn:uuid` fullUrls, matching `PUT ResourceType/id` requests,
and resolvable Patient references. CI validates it independently with HL7 Validator CLI in offline
terminology mode.

The separate [server round-trip test](../server/README.md) submits the same Bundle to one pinned HAPI
R4 image, reads every resource back, and verifies exact semantic preservation under a narrow,
documented normalization allowlist.

## Aggregate methods

All weekly calculations run before narrative generation and without an LLM:

- Medication records: count all MedicationStatement facts and count status `not-taken`.
- Each Observation code: count recorded facts and calculate the minimum and maximum recorded values.

Every aggregate stores the exact source fact IDs and a human-readable method. The tracked summary
cites the medication aggregate, both `not-taken` event facts, and each Observation aggregate. The
candidate gate rejects changed numbers, unknown or absent citations, omitted `not-taken` records,
causal claims, clinical advice, and instruction-like output.

The ranges are descriptive only. They do not establish a trend, normal range, cause, diagnosis,
treatment response, or clinical significance.

## Missingness and corrections

The output records the analysis window, included FHIR resource types, record counts, missing days,
missing or extra events by day/type, required-value coverage, and material corrections. A missing day,
wrong daily event count, source-quality finding, or invalid resource produces `insufficient_data` and
no narrative statements.

## Run

```bash
PYTHONPATH=src python scripts/generate_weekly_fhir.py --check
PYTHONPATH=src python -m unittest tests.test_fhir_weekly -v

# CI also validates the weekly transaction Bundle with the pinned HL7 Validator CLI.
FHIR_VALIDATOR_JAR=/path/to/validator_cli.jar scripts/validate_fhir_r4.sh
```

This is base FHIR R4 software evidence and one pinned-server integration check, not arbitrary-server,
terminology-server, NZ Base, NZ Patient Summary, clinical, medical-device, security, performance,
or regulatory conformance.
