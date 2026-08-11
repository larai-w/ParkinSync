## Outcome

Closes #

Describe the user, operational, data-quality, or research-readiness outcome.

## Acceptance evidence

- [ ] Linked acceptance criteria are satisfied
- [ ] Python tests and relevant fixture checks pass
- [ ] Commands run and relevant outputs are recorded below
- [ ] Generated artifacts remain deterministic when applicable
- [ ] Production-safe or operator checks are recorded when required
- [ ] Documentation and runbooks reflect the change

Evidence:

## Risk review

- [ ] No credentials, personal health information, raw care records, or private reports are included
- [ ] New or changed examples use clearly marked synthetic data only
- [ ] Missing data, lineage, idempotency, and failure recovery were considered
- [ ] Health-related language remains observational and does not imply diagnosis or treatment
- [ ] FHIR mappings, profiles, and summaries preserve provenance and fail closed when evidence is missing
- [ ] `python3 scripts/check_public_repo.py --working-tree` passes
- [ ] Rollback or recovery is documented for material cloud changes

## Decision note

Record the tradeoff, dependency, research limitation, or follow-up a future maintainer should know.
