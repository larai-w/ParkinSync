# ParkinSync Analytics Subsystem

This directory contains the pipeline components designated for exploratory data analysis (EDA) and clinical modeling downstream within Amazon SageMaker.

### Contents
- `sample_data_v1.3.csv`: A development fixture retained for schema and EDA testing. It is not clinical
  evidence; publication provenance, re-identification risk, and any synthetic replacement are governed
  by [Issue #35](https://github.com/larai-w/ParkinSync/issues/35).
- `pd_correlation_analysis.py`: A diagnostic Python script used to verify schema compliance and evaluate basic statistical trends across multi-variable data fields.
