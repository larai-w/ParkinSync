# ParkinSync

**A serverless data pipeline that bridges paper-based caregiver logs with cloud analytics for Parkinson's Disease care.**

Caregiver observations written on structured paper forms are manually transcribed, then ingested into AWS, enriched with weather and indoor temperature telemetry, and normalized into a 25-column schema for correlation analysis in Amazon SageMaker.

**Status:** In development (v1.3.0)

[![CI](https://github.com/larai-w/ParkinSync/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/larai-w/ParkinSync/actions/workflows/ci.yml?query=branch%3Amain)
[![Security baseline](https://github.com/larai-w/ParkinSync/actions/workflows/security-baseline.yml/badge.svg?branch=main)](https://github.com/larai-w/ParkinSync/actions/workflows/security-baseline.yml?query=branch%3Amain)

---

## Five-minute FHIR review

The FHIR path is fully present on `main`; it is not a generated-artifact-only demonstration. A
technical reviewer can follow the evidence in this order:

| Review question | Direct evidence | What to verify |
|---|---|---|
| How are ParkinSync fields mapped without inventing clinical meaning? | [`src/fhir_export.py`](src/fhir_export.py) and the [mapping boundary](fhir/README.md) | Reviewed LOINC/UCUM mappings, explicit medication fields, synthetic-only enforcement, and fail-closed input checks |
| Does the transaction resolve and validate? | [Generated R4 transaction Bundle](fhir/generated/bundle-synthetic-transaction-bundle.json) and [`tests/test_fhir_export.py`](tests/test_fhir_export.py) | Deterministic `fullUrl` values, matching `PUT` requests, Patient reference resolution, and independent HL7 Validator CI |
| How is GenAI grounding enforced? | [`src/fhir_summary.py`](src/fhir_summary.py), [fact bundle](fhir/summary/generated/fact-bundle.json), and [offline summary](fhir/summary/generated/offline-summary.json) | Stable fact IDs, value-level FHIRPath provenance, exact-number checks, mandatory citations, and human review |
| Does the summary cover a real seven-day evidence window? | [`src/fhir_weekly.py`](src/fhir_weekly.py), [weekly transaction Bundle](fhir/weekly/generated/bundle-synthetic-weekly-transaction-bundle.json), and [weekly summary](fhir/weekly/generated/weekly-summary.json) | 30 FHIR resources, 28 event facts, 3 traceable aggregate facts, complete daily coverage, and structured missingness |
| What happens with adversarial or incomplete input? | [`tests/test_fhir_summary.py`](tests/test_fhir_summary.py) and [evaluation cases](fhir/summary/evaluation-cases.json) | Rejection of changed numbers, uncited claims, omitted `not-taken` medication, conflicting timestamps, clinical advice, and prompt-injection text |
| Is the evidence reproducible and continuously checked? | [CI workflow](.github/workflows/ci.yml), [latest main CI](https://github.com/larai-w/ParkinSync/actions/workflows/ci.yml?query=branch%3Amain), and [latest security baseline](https://github.com/larai-w/ParkinSync/actions/workflows/security-baseline.yml?query=branch%3Amain) | Deterministic regeneration, public-artifact policy, full test suite, HL7 Validator CLI, secret scan, and dependency audit |

The fixture year **2035 is intentional**: a conspicuous future date, synthetic IDs, and
`meta.tag=synthetic` reduce the risk that demonstration records are mistaken for current participant
data. It is not a forecast or a real care period.

**Evidence boundary:** this proves a synthetic, offline base FHIR R4 transaction and grounded-summary
software path. It does not claim terminology-server, NZ Base, NZ Patient Summary, clinical, medical-
device, treatment, or regulatory conformance, and it does not send records to a FHIR server.

---

## Why this exists

OFF periods in Parkinson's Disease are described in varied ways and are not always captured or
communicated systematically. Everyday care tools also rarely align caregiver observations with
contextual data in a form that can be reviewed later. ParkinSync synchronizes these streams by date
and produces a tidy dataset for exploratory analysis; it does not test treatment efficacy or establish
that an observed association is causal.

## Research Evidence and Boundaries

ParkinSync's design rationale is informed by peer-reviewed work on medication-adherence technology,
health-technology adoption among older adults, OFF-period reporting, gastrointestinal barriers to
levodopa absorption, and automation bias. These sources motivate product decisions; they do not
validate ParkinSync's clinical outcomes.

Key sources:

- [Bohlmann, Mostafa, and Kumar (2021) — machine learning and medication adherence](https://doi.org/10.2196/26993)
- [Bertolazzi, Quaglia, and Bongelli (2024) — health-technology adoption by older adults](https://doi.org/10.1186/s12889-024-18036-5)
- [Mantri et al. (2021) — descriptions and self-reported triggers of OFF periods](https://doi.org/10.17294/2330-0698.1836)
- [Leta et al. (2023) — gastrointestinal barriers to levodopa transport and absorption](https://doi.org/10.1111/ene.15734)

See the
**[claim-to-source evidence map](docs/RESEARCH_EVIDENCE.md)** for supported claims, limitations, and
the publication boundary for project-generated observations. The
**[data governance policy](docs/DATA_GOVERNANCE.md)** defines consent, access, retention, research,
publication tiers, and time-series re-identification review.

---

## Product Management

ParkinSync doubles as a working **product-management portfolio** — a research-driven data product built
solo and AI-assisted, delivered with an evidence-first, boundary-aware discipline. What it demonstrates:

- **Evidence-based delivery** — the goal is a reviewable, analysis-ready dataset, and the project is
  explicit about what it does *not* claim: public fixtures and exploratory analyses are not clinical
  evidence, diagnosis, or treatment guidance.
- **Stakeholder management** — it preserves the caregiver's existing paper workflow (no new app to adopt)
  while producing structured data for whoever reviews it later; a human stays at the boundary where raw
  observations become records.
- **Technical product management** — a serverless pipeline owned end to end: multi-stream ingestion
  (paper logs + weather + indoor telemetry), a fixed schema, and a deliberate choice to keep OCR as
  supporting infrastructure rather than the final authority (see **Architecture** below).
- **Agile in practice** — a live **[GitHub Project — ParkinSync Delivery](https://github.com/users/larai-w/projects/4)**
  and **[issues](https://github.com/larai-w/ParkinSync/issues)** tracking experiments, decisions and tasks.

Related engineering write-ups are on the [VEAI LAB blog](https://veai.jp/blog/).

---

## Research Direction

ParkinSync is also the seed of a longer research programme: moving from **manual, environment-correlated
logging** toward **automated, sensor-driven analysis of movement in Parkinson's Disease**. Planned directions:

- **Wearable / ambient sensing** — augment or replace manual paper logs with inertial and ambient sensors
  to capture gait, tremor, and daily-activity signals continuously and unobtrusively at home.
- **Machine learning on sensor data** — investigate whether validated sensor datasets can support
  detection of **gait anomalies, fall risk, and daily-rhythm disruptions**, and analysis of how motor
  observations co-vary with environmental context. These questions require consent, representative
  data, and validation beyond the current repository.
- **Human-in-the-loop clinical interpretation** — keep a caregiver or clinician at the boundary between
  raw signals and care decisions; the system informs, it does not diagnose.

This direction is exploratory and forward-looking — the current codebase is the data-pipeline foundation it
would build on. It aligns with doctoral research interests in **AgeTech, human activity recognition, and AI
for digital health and wearable sensing.**

---

## Architecture

```
Caregiver paper log
  │
  └─ [manual scan / upload to S3]
         │
         ▼
  AWS S3 (ingestion staging bucket)
         │
         ├─ S3 event trigger
         │      ▼
         │  Lambda: ParkinSync_OCR_Handler  (Python 3.12)
         │    ├─ Amazon Textract  (form key-value extraction)
         │    ├─ Visual Crossing Weather API  (historical weather by log date)
         │    └─ Google Sheets API v4  (append verified row to master ledger)
         │
         └─ [independent, schedule-driven]
                ▼
         Amazon EventBridge  (cron: every 3 hours)
                ▼
         Lambda: ParkinSync_IndoorTemp_Logger  (Python 3.12)
           ├─ SwitchBot Open API  (indoor temperature)
           └─ Google Sheets API v4
                ├─ append measured-at timestamp + event ID to TempHistory
                └─ recompute local-day avg/min/max and update
                   U:X only when one matching master row exists

Master ledger (Google Sheets, 25-column schema)
  ├─ Amazon SageMaker  (exploratory Pearson r and lag analyses)
  └─ Offline FHIR R4 adapter (synthetic demo only)
       ├─ Patient / MedicationStatement / Observation / CarePlan transaction Bundle
       ├─ deterministic facts, data-quality gate, and grounded offline summary
       └─ seven-day Bundle, aggregate facts, missingness, and weekly summary

Secrets: AWS Secrets Manager (Google SA JSON, SwitchBot key, Weather API key)
IaC: deploy.sh (bash) — packages Lambda zips and calls aws lambda update-function-code
```

The OCR step is Human-in-the-Loop: Textract validates form structure but does not auto-fill fields. A human operator verifies the transcription before cloud ingestion, reducing garbage-in data.

---

## Tech Stack

| Layer | Choice |
|---|---|
| Compute | AWS Lambda (Python 3.12), 2 decoupled functions |
| Scheduling | Amazon EventBridge (3-hour cron) |
| OCR / Audit | Amazon Textract |
| Secrets | AWS Secrets Manager |
| Aggregation | Python Lambda + Google Sheets API v4 |
| IoT polling | SwitchBot Open API |
| Weather enrichment | Visual Crossing Weather API |
| Analytics | Amazon SageMaker, Python Pandas / NumPy / SciPy |
| Interoperability demo | HL7 FHIR R4.0.1, `fhir.resources` / Pydantic |
| Deploy | `deploy.sh` (bash, `aws lambda update-function-code`) |

---

## Testing

```
tests/test_lambda_function.py       — 29 OCR, weather, date, idempotency,
                                      quarantine, and handler cases
tests/test_indoor_temp_logger.py    — 11 synthetic telemetry cases covering daily
                                      aggregation, JST measurement dates, retries,
                                      missing/duplicate master dates, dependency
                                      failure propagation, and mocked Sheets sync
analytics/pd_correlation_analysis.py — synthetic-fixture schema and EDA audit
tests/test_fhir_export.py           — FHIR R4 mapping, safety, reference, and
                                      reproducibility checks
tests/test_fhir_summary.py          — grounded fact provenance, data quality,
                                      adversarial claims, and summary gating
tests/test_fhir_weekly.py           — seven-day generation, aggregate provenance,
                                      missingness, and weekly adversarial checks
tests/test_readme_links.py          — reviewer-path and repository-relative link checks
```

Run tests: `PYTHONPATH=src python -m unittest discover -s tests -v` (requires
`pip install -r requirements.txt -r requirements-fhir.txt`)

---

## Local Development

```bash
# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-fhir.txt

# Unit tests
PYTHONPATH=src python -m unittest discover -s tests -v

# Schema audit (uses the deterministic synthetic fixture)
python analytics/pd_correlation_analysis.py

# Confirm generated public artifacts are reproducible
python scripts/generate_synthetic_fixture.py --check
python scripts/export_synthetic_fhir.py --check
PYTHONPATH=src python scripts/generate_grounded_summary.py --check
PYTHONPATH=src python scripts/generate_weekly_fhir.py --check

# Deploy only the indoor telemetry Lambda; OCR remains behind its release guard
DEPLOY_TARGET=iot AWS_REGION=us-east-1 bash deploy.sh

# Build and verify the source-only package without updating AWS
DRY_RUN=1 DEPLOY_TARGET=iot bash deploy.sh
```

---

## Repository Layout

```
src/
  ParkinSync_OCR_Handler.py    # Event-driven Lambda: OCR + weather enrichment
  indoor_temp_logger.py        # Schedule-driven Lambda: SwitchBot telemetry
  fhir_export.py               # Synthetic normalized record -> FHIR R4 adapter
  fhir_summary.py              # FHIR facts, data quality, and summary claim gate
  fhir_weekly.py               # Seven-day synthetic Bundle and aggregate facts
tests/
  test_lambda_function.py      # OCR and weather unittest suite
  test_indoor_temp_logger.py   # Synthetic daily-aggregation unittest suite
  test_fhir_export.py          # FHIR model, mapping, and reproducibility tests
  test_fhir_summary.py         # Grounding, quality, and adversarial summary tests
  test_fhir_weekly.py          # Weekly completeness, provenance, and claim tests
fhir/                          # Synthetic FHIR and grounded-summary evidence
analytics/
  pd_correlation_analysis.py   # EDA / schema audit script
  synthetic_sample_data_v1.3.csv # Deterministic fixture; not clinical evidence
  synthetic_fixture_manifest.json # Public provenance and permitted-use boundary
architecture/                  # SVG system and sequence diagrams
design/                        # Paper log template, master schema definition
docs/                          # Public product, evidence, and governance documentation
content/blog-drafts/           # Anonymized GitHub case-study draft
scripts/                       # CI and repository hygiene checks
deploy.sh                      # Lambda packaging and deployment script
```

---

## Security & Privacy

- All API credentials (Google Service Account JSON, SwitchBot key, Visual Crossing key) are stored exclusively in AWS Secrets Manager — no hardcoded values in source.
- The ingestion contract excludes personally identifiable information; each approved collection must
  enforce its reviewed data map before records enter the pipeline.
- IAM roles follow the principle of least privilege, scoped to required S3 buckets and Sheets targets.
- Capstone source documents and non-anonymized PDFs are intentionally excluded from the public repository. CI blocks known report filenames, office-source documents, and common secret patterns.
- Participant-derived data is not permitted in Git. See [Data Governance](docs/DATA_GOVERNANCE.md) for
  consent, withdrawal, deletion, retention, access, publication, and re-identification controls.

---

## Branching

- `main`: stable, matches live Lambda deployments
- `development`: active iteration

---

## License

MIT — see [LICENSE](LICENSE)

Part of the [VEAI LAB.](https://veai.jp) ecosystem — [ParkinSync product page](https://veai.jp/apps/parkinsync/)
