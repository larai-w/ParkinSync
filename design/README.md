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
