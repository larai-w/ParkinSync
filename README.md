# ParkinSync

**A serverless data pipeline that bridges paper-based caregiver logs with cloud analytics for Parkinson's Disease care.**

Caregiver observations written on structured paper forms are manually transcribed, then ingested into AWS, enriched with weather and indoor temperature telemetry, and normalized into a 25-column schema for correlation analysis in Amazon SageMaker.

**Status:** In development (v1.3.0)

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
the publication boundary for project-generated observations.

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
  └─ Amazon SageMaker  (exploratory Pearson r and lag analyses)

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
| Deploy | `deploy.sh` (bash, `aws lambda update-function-code`) |

---

## Testing

```
tests/test_lambda_function.py       — 29 OCR, weather, date, idempotency,
                                      quarantine, and handler cases
tests/test_indoor_temp_logger.py    — 9 synthetic telemetry cases covering daily
                                      aggregation, JST measurement dates, retries,
                                      missing/duplicate master dates, and mocked
                                      end-to-end Sheets synchronization
analytics/pd_correlation_analysis.py — schema and exploratory-analysis audit
```

Run tests: `PYTHONPATH=src python -m unittest discover -s tests -v` (requires `pip install -r requirements.txt`)

---

## Local Development

```bash
# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Unit tests
PYTHONPATH=src python -m unittest discover -s tests -v

# Schema audit (uses analytics/sample_data_v1.3.csv)
python analytics/pd_correlation_analysis.py

# Deploy only the indoor telemetry Lambda; OCR remains behind its release guard
DEPLOY_TARGET=iot AWS_REGION=us-east-1 bash deploy.sh

# Build and verify the Linux package without updating AWS
DRY_RUN=1 DEPLOY_TARGET=iot bash deploy.sh
```

---

## Repository Layout

```
src/
  ParkinSync_OCR_Handler.py    # Event-driven Lambda: OCR + weather enrichment
  indoor_temp_logger.py        # Schedule-driven Lambda: SwitchBot telemetry
tests/
  test_lambda_function.py      # OCR and weather unittest suite
  test_indoor_temp_logger.py   # Synthetic daily-aggregation unittest suite
analytics/
  pd_correlation_analysis.py   # EDA / schema audit script
  sample_data_v1.3.csv         # Development fixture; not clinical evidence (25 columns)
architecture/                  # SVG system and sequence diagrams
design/                        # Paper log template, master schema definition
docs/                          # Public user guide only
content/blog-drafts/           # Anonymized GitHub case-study draft
scripts/                       # CI and repository hygiene checks
deploy.sh                      # Lambda packaging and deployment script
```

---

## Security & Privacy

- All API credentials (Google Service Account JSON, SwitchBot key, Visual Crossing key) are stored exclusively in AWS Secrets Manager — no hardcoded values in source.
- Personally identifiable information is omitted at the ingestion boundary.
- IAM roles follow the principle of least privilege, scoped to required S3 buckets and Sheets targets.
- Capstone source documents and non-anonymized PDFs are intentionally excluded from the public repository. CI blocks known report filenames, office-source documents, and common secret patterns.

---

## Branching

- `main`: stable, matches live Lambda deployments
- `development`: active iteration

---

## License

MIT — see [LICENSE](LICENSE)

Part of the [VEAI LAB.](https://veai.jp) ecosystem — [ParkinSync product page](https://veai.jp/apps/parkinsync/)
