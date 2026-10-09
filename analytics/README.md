# ParkinSync Analytics Subsystem

This directory contains schema validation and exploratory data analysis (EDA) examples. The tracked
data is deterministic and synthetic; it is not participant data or clinical evidence.

### Contents

- `synthetic_sample_data_v1.3.csv`: A 21-row fixture generated from the public 25-column schema and
  invented scenarios only.
- `synthetic_fixture_manifest.json`: Machine-readable provenance, scope, and prohibited uses.
- `pd_correlation_analysis.py`: Verifies the exact schema and synthetic markers, then exercises basic
  statistical code paths without making health claims.

Regenerate the fixture and manifest with:

```bash
python scripts/generate_synthetic_fixture.py
python scripts/generate_synthetic_fixture.py --check
```

Generated charts are not tracked. Any future participant-derived result must pass the publication tier
and re-identification review in [Data Governance](../docs/DATA_GOVERNANCE.md).

The synthetic EDA output includes observed/missing/invalid counts for each numeric
field and the pairwise-complete row count used for its single descriptive
correlation. Empty/whitespace cells are missing, zero remains observed, and
nonfinite or malformed numeric values stop statistics after printing audit counts.
Means and bowel totals use observed values only; totals are explicitly subtotals.
With fewer than two complete pairs or a constant field, correlation is undefined.
Coverage denominators are input rows, not expected calendar days or participants.
The invented rows do not support confidence intervals, inferential p-values,
multiple-testing assurance or clinical relationships. No imputation, lag search
or empirical statistical inference is added.
