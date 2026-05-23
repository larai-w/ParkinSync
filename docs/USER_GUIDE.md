# ParkinSync v1.3.0 — End-User Operational Guide

This document provides administrative and operational guidelines for caregivers and clinical analysts interacting with the ParkinSync serverless ecosystem.

---

## 1. Caregiver Workflow (Data Ingestion)

To ingest clinical bedside records into the active analytics pipeline, follow these structured steps:

1. **Manual Transcription:** Transcribe handwritten bedside observations into the standardized grid template (see `design/` folder) to ensure high baseline data legibility.
2. **Scan to PDF:** Utilize a smartphone scanning application to convert the structured paper log into a high-contrast, clean PDF document.
3. **S3 Upload:** Log into the AWS Console (or authorized edge gateway) and upload the finalized PDF directly into the `incoming/` folder of the designated **Amazon S3 ingestion bucket**.
4. **Trigger Verification:** The upload automatically invokes the `ParkinSync_OCR_Handler` Lambda function. Execution flow latency will complete in approximately 1.124 seconds.

---

## 2. Clinical Data Management (Google Sheets)

The central data repository is divided into a multi-tab structure to maintain complete separation between raw telemetry and verified clinical logs:

### 📊 "Environmental Raw Data" Tab
* **Purpose:** Stores the 3-hour continuous climate data streamed asynchronously from localized SwitchBot IoT sensors via `ParkinSync_IndoorTemp_Logger`.
* **Action Required:** None. This tab is completely automated and should not be modified manually.

### 👑 "Master Sheet" (The Clinical Ledger)
* **Purpose:** The definitive clinical timeline matching normalized patient symptoms, medication timings, and environmental summaries.
* **Human-in-the-Loop (HITL) Validation:** 
  * Built-in spreadsheet formulas calculate the precise medication delays in Column D automatically.
  * If anomalous text formatting or clinical boundary violations occur during automated S3 ingestion, conditional formatting will automatically flag the targeted row.
  * **Analyst Action:** Review flagged fields manually, make adjustments based on the primary paper log reference, and clear the flag to authorize the row for machine learning training.

---

## 3. Analytical Research Execution (Amazon SageMaker)

Once data rows are validated and stabilized in the Master Sheet:

1. Open the **Amazon SageMaker Studio** console environment.
2. Navigate to the `/analytics` directory and initialize the Jupyter Notebook framework.
3. Run the evaluation scripts to refresh the **Pearson's r correlation matrices**, tracking how acute pressure changes or post-rehabilitation fatigue map to motor rigidity time intervals.
