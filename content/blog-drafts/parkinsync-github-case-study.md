---
title: "ParkinSync Technical Case Study"
audience: "GitHub project documentation / portfolio case study"
status: "draft"
privacy: "anonymized; review before publication"
---

# ParkinSync Technical Case Study

ParkinSync is a serverless data pipeline for converting structured home-care observations into an analysis-ready dataset. It combines paper-based caregiver workflows, human verification, weather enrichment, indoor telemetry, and exploratory analytics.

This document is a public, anonymized case-study draft. It is intended for GitHub or portfolio use and should not include the original capstone report, source documents, raw logs, precise care-location details, private dates, or patient-identifying details.

## Problem

Home-care observations can contain useful longitudinal signals, but they are often captured in fragmented formats:

- Paper logs written by caregivers
- Environmental data from separate sensors
- Weather context from external services
- Manual notes that are hard to compare over time

The project goal was to preserve the low-friction paper workflow while creating a reliable cloud-backed dataset for later review and exploratory analysis.

## Constraints

- The input workflow had to remain simple for non-technical caregivers.
- Data quality mattered more than ingestion speed.
- The system needed to avoid hardcoded credentials.
- The architecture had to stay inexpensive and maintainable.
- Public artifacts must be anonymized before publication.

## Solution

ParkinSync uses a hybrid Human-in-the-Loop pipeline.

Care logs are scanned or uploaded to S3. A Lambda function processes the document structure, enriches rows with historical weather data, and appends verified records to Google Sheets. A second scheduled Lambda function collects indoor telemetry and appends it to a separate sheet. Spreadsheet formulas create daily aggregates, and Python analysis scripts consume the normalized dataset.

## Architecture Summary

| Layer | Implementation |
|---|---|
| Upload staging | Amazon S3 |
| Event processing | AWS Lambda |
| Scheduled telemetry | Amazon EventBridge + AWS Lambda |
| OCR / structure extraction | Amazon Textract |
| Secrets | AWS Secrets Manager |
| Operational ledger | Google Sheets API |
| Indoor telemetry | SwitchBot Open API |
| Weather context | Visual Crossing Weather API |
| Analysis | Python, Pandas, NumPy, SciPy, SageMaker |

## Why Human-in-the-Loop

Early OCR tests showed that autonomous handwritten extraction was not reliable enough for a health-related care-log workflow. ParkinSync therefore treats human verification as a core part of the design.

The system can automate transport, enrichment, formatting, and aggregation. It should not silently convert uncertain handwriting into authoritative clinical data.

## Repository Hygiene

The public repository should contain:

- Source code
- Architecture diagrams
- Unit tests
- Deployment scripts
- Anonymized sample data
- Public user documentation
- Anonymized blog or case-study drafts

The public repository should not contain:

- Original capstone report PDFs
- Pages, Keynote, Word, or PowerPoint source documents
- Raw care logs
- Private Google Sheets identifiers
- API keys or service account JSON
- Precise patient, family, caregiver, or location identifiers

The repository includes a CI guard at `scripts/check_public_artifacts.py` to prevent known private report filenames, office-source documents, and common secret patterns from being tracked again.

## Current Status

The project has a working serverless ingestion architecture, unit tests for the OCR handler utilities, deployment packaging for both Lambda functions, and anonymized sample analytics assets.

The next recommended engineering tasks are:

- Confirm the live Lambda code matches the current `main` branch.
- Decide whether to migrate hardening features from the isolated MVP branch.
- Add idempotency to S3 processing.
- Add review-folder routing and notifications for failed or ambiguous OCR outputs.
- Replace private capstone artifacts with anonymized public documentation.

## Public Positioning

ParkinSync should be described as a care-informatics and data-engineering project, not as a diagnostic or medical decision-making product.

The appropriate public claim is that it helps preserve, normalize, and analyze caregiver observations. Any clinical interpretation should remain framed as exploratory and non-diagnostic.
