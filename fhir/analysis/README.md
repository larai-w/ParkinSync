# Mapping-loss inventory

This directory contains the reproducibility artifact for the mapping-loss counts reported in the
ParkinSync interoperability study. It uses synthetic field definitions only; it contains no
participant, production, or facility data.

The inventory records the mapping decision and one or more explicitly assigned loss modes for each
of 15 source fields. The classifications are qualitative coding decisions made by the authors. The
script validates the vocabulary and reproduces the counts; it does not independently discover or
validate the classifications.

Run the manuscript-count check from the repository root:

```bash
python3 scripts/classify_mapping_loss.py --check
```

The expected result is:

- no field without an assigned loss mode (0/15);
- resource-target ambiguity on 11/15 fields; and
- two or more loss modes on 9/15 fields.

Changing a classification is allowed, but the check will fail until the manuscript-facing expected
counts are deliberately reviewed and updated with it.
