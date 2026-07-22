# ParkinSync

**A serverless data pipeline that bridges paper-based caregiver logs with cloud analytics for Parkinson's Disease care.**

Caregiver observations written on structured paper forms are manually transcribed, then ingested into AWS, enriched with weather and indoor temperature telemetry, and normalized into a 25-column schema for correlation analysis in Amazon SageMaker.

**Status:** In development (v1.3.0)

---

## Why this exists

Motor symptoms in Parkinson's Disease are often reported to vary with environmental factors such as temperature and barometric pressure. Everyday care tools rarely capture this context alongside caregiver observations. ParkinSync collects both streams, synchronizes them by date, and produces a tidy dataset for exploratory data analysis.

---

## Product Management

ParkinSync doubles as a working **product-management portfolio** — a research-driven data product built
solo and AI-assisted, delivered with an evidence-first, boundary-aware discipline. What it demonstrates:

- **Evidence-based delivery** — the goal is a reviewable, analysis-ready dataset, and the project is
  explicit about what it does *not* claim: it is exploratory, not diagnostic, on limited anonymized data.
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
           └─ SwitchBot Open API  (indoor temperature/humidity)
               └─ Google Sheets API v4  (staging tab)
                      │
                      └─ Native spreadsheet formulas compute daily
                         avg/min/max  (no additional serverless cost)

Master ledger (Google Sheets, 25-column schema)
  └─ Amazon SageMaker  (Pandas/NumPy Pearson r correlation, lag analysis)

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
| Aggregation | Google Sheets API v4 |
| IoT polling | SwitchBot Open API |
| Weather enrichment | Visual Crossing Weather API |
| Analytics | Amazon SageMaker, Python Pandas / NumPy / SciPy |
| Deploy | `deploy.sh` (bash, `aws lambda update-function-code`) |

---

## Testing

```
tests/test_lambda_function.py  — 5 Python unittest cases
  TestHistoricalWeather (2 cases):
    - happy path: returns (summary, raw_data) tuple
    - graceful degradation on network failure
  TestWeatherEmoji (2 cases):
    - condition-to-emoji mapping
    - unknown condition fallback
  TestLambdaHandler (1 case):
    - returns HTTP 404 when Textract finds no table in document

analytics/pd_correlation_analysis.py  — schema audit script
    (verifies 25-column alignment, computes thermal gradient,
     weekday/weekend split, symptom-temperature Pearson r)
```

Run tests: `python -m pytest tests/` (requires `pip install -r requirements.txt` and `PYTHONPATH=src`)

---

## Local Development

```bash
# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Unit tests
PYTHONPATH=src python -m pytest tests/ -v

# Schema audit (uses analytics/sample_data_v1.3.csv)
python analytics/pd_correlation_analysis.py

# Deploy both Lambda functions (requires AWS CLI + IAM permissions)
AWS_REGION=us-east-1 bash deploy.sh
```

---

## Repository Layout

```
src/
  ParkinSync_OCR_Handler.py    # Event-driven Lambda: OCR + weather enrichment
  indoor_temp_logger.py        # Schedule-driven Lambda: SwitchBot telemetry
tests/
  test_lambda_function.py      # unittest suite
analytics/
  pd_correlation_analysis.py   # EDA / schema audit script
  sample_data_v1.3.csv         # Anonymized sample dataset (25 columns)
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
