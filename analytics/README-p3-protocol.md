# P3 readiness protocol (analysis protocol as code)

**Purpose.** The *pre-specified and version-frozen* analysis protocol for the P3 applied paper
(`career/phd/papers/P3-applied-ml-positioning-memo.md`). Metric definitions and
decision thresholds are **frozen (v1) before any real data is seen**, so running
on real data later is an **input swap, not a code or threshold change** — a guard
against p-hacking and post-hoc gate loosening.

## Run

```bash
# dependency (prefer an isolated environment)
python3 -m pip install -r requirements-p3.txt

# synthetic (default) — reuses the 30-day fixture from run_30_day_synthetic_readiness.py
python3 p3_readiness_protocol.py --output-dir /tmp/p3-readiness

# self-test (CI-friendly): asserts clean->ANALYZE_OK, degraded->NOT_READY,
# synthetic never READY, real+cleared->READY
python3 p3_readiness_protocol.py --self-test

# focused positive and negative contract tests
python3 test_p3_readiness_protocol.py

# real data, later, only after the external governance process in a restricted environment:
python3 p3_readiness_protocol.py --input approved-export.json --data-label real --governance-cleared
```

## Two fail-closed gates

1. **data_quality_gate** — computed only from the records:
   `ANALYZE_OK` / `HUMAN_REVIEW_REQUIRED` / `NOT_READY`.
   FAIL dominates REVIEW dominates PASS across 8 checks (canonical JSON Schema validity, day
   coverage, duplicate rate, per-source coverage, temporal continuity, not_recorded
   share, adherence class balance, label availability).
2. **research_release_gate** — `READY` / `NOT_YET`.
   **Synthetic input can never be READY.** Real data reaches READY only with an
   explicit operator `--governance-cleared` attestation AND a clean data-quality
   gate. The flag records an external human decision; it does not verify or
   replace ethics, legal, or organizational approval. Pipeline PASS is not
   research readiness.

Medication adherence labels and missingness are separate: only observed
`medication_taken` / `medication_missed` events count as usable outcome labels;
`not_recorded` never means a missed dose. Label availability is usable labels /
expected medication slots.

## Swap-in for real data (unchanged protocol)

When the governance gate passes, export approved records as a `care-event/v1`
JSON list inside the restricted environment and pass `--input`. The metrics,
thresholds, and gate logic are identical — only the data changes. Real exports
must never be committed to git.

## Honest scope

Synthetic pseudonymous fixture only unless an operator supplies real input under
clearance. This is a data-quality / ML-readiness protocol, **not** a
model-performance or clinical result.
