---
title: "Building ParkinSync: A Serverless Pipeline for Paper-Based Care Logs"
audience: "English development blog"
status: "draft"
privacy: "anonymized; review before publication"
---

# Building ParkinSync: A Serverless Pipeline for Paper-Based Care Logs

ParkinSync started from a practical constraint: in home-care workflows, paper is often the most reliable interface.

The goal was not to replace that interface with a new app. The goal was to preserve the workflow that caregivers could actually maintain, then build a cloud pipeline around it so the data could be reviewed, normalized, and analyzed over time.

The result is a lightweight serverless system that connects structured care logs, environmental telemetry, and weather context into a single analysis-ready dataset.

## The Design Constraint

Care data is often fragmented across paper notes, caregiver observations, sensor readings, and weather conditions. Each source is useful, but the value appears only when the streams can be aligned by date and reviewed together.

The first version explored OCR as the primary ingestion path. That exposed an important limitation: handwriting, low-contrast scans, table boundaries, and symptom-related writing variability can make fully automated extraction unreliable.

For this domain, unreliable automation is worse than slower ingestion. The system therefore moved toward a Human-in-the-Loop design: OCR can assist with structure validation, but a verified human step protects the master dataset from bad input.

## Architecture

ParkinSync uses two decoupled Lambda functions.

The clinical ingestion function is triggered by uploads to an S3 staging bucket. It processes the structured log, enriches the row with historical weather context, and appends the normalized result to Google Sheets.

The environmental telemetry function runs on an EventBridge schedule. It polls indoor sensor data and appends readings to a separate staging tab. Spreadsheet formulas then compute daily aggregates such as average, minimum, and maximum temperature without adding another compute service.

The core services are:

- AWS Lambda for event-driven and scheduled compute
- Amazon S3 for upload staging
- Amazon Textract for document structure extraction
- AWS Secrets Manager for API credentials
- Google Sheets API for the operational data store
- SwitchBot Open API for indoor telemetry
- Visual Crossing for historical weather enrichment
- SageMaker notebooks for exploratory analysis

This is intentionally small. The system does not need a database cluster, container platform, or complex orchestration layer for the current scale.

## Why Google Sheets Stayed in the Architecture

Google Sheets is not usually the first tool people imagine for clinical analytics, but it is useful here for one reason: it is visible to non-engineers.

The master ledger can be inspected, corrected, and exported without requiring a custom admin interface. For a project where data integrity matters more than ingestion volume, this tradeoff is acceptable.

The cloud pipeline handles repeatable ingestion and enrichment. Sheets handles transparent review and lightweight aggregation. Python handles analysis.

## Human-in-the-Loop as a Data Quality Strategy

The most important architectural decision was not which API to call. It was deciding where automation should stop.

In a health-related workflow, a plausible but wrong OCR result can be dangerous. A symptom score, medication timing, or observation note should not silently become structured data unless it has been verified.

ParkinSync treats HITL not as a temporary workaround, but as part of the data quality model.

## Lessons Learned

The main lesson was that serverless architecture is useful only when it supports the operational reality of the users.

For this project, the winning shape was not maximum automation. It was a modest pipeline that respected paper-based care, preserved human review, and still produced a clean dataset for analysis.

The next step is to harden the ingestion path further: idempotent S3 processing, review queues for ambiguous OCR output, clearer deployment automation, and fully anonymized public sample artifacts.

ParkinSync is not a diagnostic system. It is an informatics bridge: a way to make everyday care observations easier to preserve, inspect, and analyze.
