# Research Evidence and Claim Boundaries

ParkinSync is a research-engineering prototype for structuring caregiver observations and contextual
telemetry. This page maps product decisions to peer-reviewed sources and states what those sources do
not establish. It is not medical advice and does not present project-generated observations as clinical
evidence.

## Evidence map

| Source | What it supports | What it does not establish | ParkinSync design implication |
|---|---|---|---|
| [Bohlmann, Mostafa, and Kumar (2021)](https://doi.org/10.2196/26993) | A scoping review of 43 studies found growing use of machine learning for medication-adherence prediction and monitoring, alongside a need for more realistic testing and evaluation of user acceptability. | It does not validate ParkinSync's implementation, predictions, or clinical effectiveness. | Treat machine learning as a future research direction and retain observable, reviewable data flows. |
| [Bertolazzi, Quaglia, and Bongelli (2024)](https://doi.org/10.1186/s12889-024-18036-5) | An integrative review of 29 studies and 6,213 older adults identified interacting demographic, health, dispositional, technology, and social factors in health-technology adoption. | It does not prove that every older adult prefers paper or that one interface works across care settings. | Preserve familiar workflows, minimize added burden, and validate usability with intended users. |
| [Mantri et al. (2021)](https://doi.org/10.17294/2330-0698.1836) | A survey of 2,110 people with Parkinson's Disease documented varied descriptions and self-reported triggers of OFF periods, plus communication challenges. | Self-reported triggers do not establish individual-level causation or validate environmental predictions. | Capture time-stamped observations and context without converting associations into treatment claims. |
| [Leta et al. (2023)](https://doi.org/10.1111/ene.15734) | A narrative review describes gastrointestinal barriers that may affect levodopa transport and absorption. | It does not show that a bowel observation predicts an individual's OFF period or justify changing medication. | Keep gastrointestinal observations as optional context for human review, not an automated recommendation. |
| [Goddard, Roudsari, and Wyatt (2012)](https://doi.org/10.1136/amiajnl-2011-000089) | A systematic review documents automation bias in health-related decision support and discusses mediators and mitigations. | Human review does not guarantee perfect accuracy, and this source does not certify ParkinSync's workflow. | Keep a human verification boundary around noisy OCR and consequential interpretations. |
| [Ho et al. (2024)](https://doi.org/10.1080/23294515.2023.2274582) | The paper frames multi-level ethical considerations for AI health monitoring involving people with Parkinson's Disease. | It does not provide regulatory approval or demonstrate that a particular architecture is compliant. | Treat consent, access, publication, and re-identification risk as release gates rather than documentation afterthoughts. |

## Project evidence boundary

The public repository can demonstrate software behavior through source code, tests, schemas, synthetic
or publication-reviewed fixtures, and reproducible benchmarks. It cannot demonstrate treatment benefit,
diagnostic accuracy, or generalizable clinical relationships.

The academic final report contains case-specific source material and is intentionally not included in
this repository. It informed this evidence audit, but its individual observations, screenshots, schedules,
and correlation results are not public claims. A correlation result should be published only when its
dataset has a documented publication basis and the analysis exposes sample size, missing-data handling,
assumptions, uncertainty, and reproducible code. Even then, an association is not causation.

Project files such as `analytics/sample_data_v1.3.csv` and generated charts are development artifacts,
not clinical evidence. Their publication status and re-identification risk remain governed by
[Issue #35](https://github.com/larai-w/ParkinSync/issues/35).

## Claim language

Use:

- "records and synchronizes observations"
- "supports exploratory analysis"
- "an observed association requires validation"
- "human review remains required"

Avoid without independently reviewable evidence and the appropriate governance:

- "proves" or "clinically validates"
- "clinical-grade" or "production-ready clinical system"
- treatment, dosing, or diagnostic recommendations
- causal conclusions drawn from a single context or small dataset

Last reviewed: 2026-08-01.
