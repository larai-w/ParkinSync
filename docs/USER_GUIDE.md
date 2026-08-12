# ParkinSync v1.3.0 — Operator Guide

This document describes the current caregiver-ingestion and telemetry-aggregation workflow. ParkinSync
supports record processing and exploratory analysis; it does not provide diagnosis or treatment advice.

---

## 1. Caregiver Workflow (Data Ingestion)

To ingest clinical bedside records into the active analytics pipeline, follow these structured steps:

1. **Manual Transcription:** Transcribe handwritten bedside observations into the standardized grid template (see `design/` folder) to ensure high baseline data legibility.
2. **Scan to PDF:** Utilize a smartphone scanning application to convert the structured paper log into a high-contrast, clean PDF document.
3. **S3 Upload:** Log into the AWS Console (or authorized edge gateway) and upload the finalized PDF directly into the `incoming/` folder of the designated **Amazon S3 ingestion bucket**.
4. **Trigger Verification:** The upload invokes the `ParkinSync_OCR_Handler` Lambda function. Confirm
   successful processing in the CloudWatch log; do not rely on a fixed latency assumption.

---

## 2. Clinical Data Management (Google Sheets)

The central data repository is divided into a multi-tab structure to maintain complete separation between raw telemetry and verified clinical logs:

### `TempHistory` raw telemetry tab

- **Purpose:** Stores measured-at timestamps, indoor-temperature samples, and non-sensitive EventBridge
  event IDs appended by
  `ParkinSync_IndoorTemp_Logger`.
- **Source of truth:** Repository-managed Python code performs aggregation. Spreadsheet formulas are
  not the aggregation authority.
- **Action required:** Do not edit routine rows manually. Correct malformed rows only through the
  documented recovery process below.

### Master tab

- **Default tab:** `Sheet1`; set `MASTER_SHEET` on the Lambda when production uses a different name.
- **Purpose:** Holds the 25-column review timeline. Column B is the date key and columns U:X hold the
  indoor summary, average, minimum, and maximum.
- **Write boundary:** Aggregation updates U:X only when exactly one Master row matches the local date.
  It never creates a Master row or overwrites unrelated columns.
- **Human review:** Review source transcription and flagged fields before using a row in exploratory
  analysis.

### Daily aggregation behavior

1. The Lambda polls SwitchBot and records the actual poll time in JST.
2. The Lambda appends the numeric sample and EventBridge event ID to `TempHistory`.
3. A retry with the same EventBridge ID is treated as a duplicate and is not appended again. Manual
   invocations without an ID use the measured minute as a best-effort fallback.
4. All valid samples for that local calendar date are recomputed into mean, minimum, and maximum.
5. The Lambda updates U:X when one matching date exists in the Master tab.

The Lambda returns a non-destructive status when no Master date exists, when duplicate Master dates
exist, or when the target date has no valid telemetry. A later scheduled invocation retries a missing
date automatically while that local date is active. Cross-midnight and delayed deliveries are assigned
to the actual sensor-poll date; they are not backdated to the EventBridge schedule time.

### Recovery

1. Check the `aggregate` status in the Lambda response or CloudWatch log.
2. For `master-date-missing`, add or verify the intended Master row, then invoke the original event again.
3. For `duplicate-master-date`, resolve the duplicate date before retrying; the Lambda deliberately
   writes nothing while the date key is ambiguous.
4. For `no-valid-samples`, correct only the malformed telemetry row or upstream sensor response, then
   retry the original EventBridge event so its event ID remains stable.
5. Never paste private source records into GitHub issues, test fixtures, or logs.

Deploy this component without touching the separately guarded OCR Lambda:

```bash
DRY_RUN=1 DEPLOY_TARGET=iot bash deploy.sh
DEPLOY_TARGET=iot AWS_REGION=us-east-1 bash deploy.sh
```

The first command builds and validates a source-only ZIP without updating AWS. Both production
functions use compatible dependency Layers; duplicating those libraries in the function ZIP can exceed
the 128 MB runtime memory boundary. `VENDOR_DEPS=1` is an explicit opt-in for a reviewed target without
Layers and still selects Linux x86_64 wheels. Deployment requires an explicit production review.

---

## 3. Exploratory Analysis (Amazon SageMaker)

Once data rows are validated and stabilized in the Master Sheet:

1. Open the **Amazon SageMaker Studio** console environment.
2. Navigate to the `/analytics` directory and initialize the Jupyter Notebook framework.
3. Run the evaluation scripts to refresh exploratory summaries and correlation matrices.

Treat results as hypotheses for review. An observed association does not establish causation and must
not be used to change medication or make a diagnosis.
