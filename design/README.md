# ParkinSync Database & Schema Design

This directory contains the structural definitions and analog logging templates that govern the rigid 25-column data ledger of the ParkinSync v1.3.0 architecture.

## Directory Contents
- `log_template_2026_04.pdf`: The standardized analog bedside caregiver log template utilized to collect physical clinical entries.
- `master_schema_template.csv`: A blank production-ready template containing the explicit 25-column headers for cold storage synchronization.

## Data Dictionary & Schema Definitions (Columns A to Y)
1. **Processed**: Automated JST timestamp of system execution.
2. **Date / Day**: The exact clinical tracking event date and corresponding weekday.
3. **Morning / Lunch / Evening / Bedtime / Bedtime_2**: Five distinct temporal windows mapping daily medication intake schedules.
4. **Bowel / Movi / Emerg_Call / Ryusei_Eme / Condition_C / Condition_Num**: Quantitative and qualitative clinical biomarkers (e.g., symptom index scales, bowel movements, and emergency events).
5. **Daily_Notes**: Unstructured free-text clinical logs collected at the care frontier.
6. **Weather_Summary to Weather_Condition**: Five meteorological tracking metrics resolved from external weather stream APIs.
7. **Switchbot_Summary to Switchbot_Max**: High-fidelity indoor ambient telemetry variables captured at the client environment.
8. **File_Name**: The exact immutable source file path inside the historical Amazon S3 bucket.

## Versioned master-ledger compatibility

The candidate contract `parkinsync-master-ledger/v1` in
[`scripts/master_ledger_contract.py`](../scripts/master_ledger_contract.py) fixes the
existing 25 column names and their order. It is distinct from the architecture
release v1.3.0, product metadata, care-event and FHIR contract versions. The fixture
manifest declares the ledger contract. Generation, synthetic analysis and the
public-artifact check reject a changed template even when the fixture changes with it.
These checks cover tracked synthetic CSV consumers; they do not verify deployed
Google Sheets, OCR output or production migrations.

Proposed breaking-change procedure: keep the v1 baseline intact. A reorder, rename,
removal, duplicate or additional column requires a separately reviewed contract
version with explicit old/new fixtures, producer and consumer mappings, missingness
semantics and migration/rollback tests. Changing a version string alone does not
make a new contract supported. Preserve old-version fixtures to demonstrate their
continued behavior or explicit rejection. Do not migrate real records or change a
production writer from this synthetic contract change. Owner review is required
before adopting this proposal or applying a migration.
