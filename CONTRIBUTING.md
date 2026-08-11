# Contributing to ParkinSync

Thank you for helping improve ParkinSync. Contributions should be small, reviewable, reproducible,
and safe for a public health-adjacent repository.

## Public and health-data boundary

Before opening an issue or pull request:

- use synthetic fixtures only;
- do not include participant-derived data, personal information, raw care records, facility
  identifiers, credentials, private reports, or production logs;
- describe observations and software behavior without implying diagnosis, treatment, prevention,
  or clinical effectiveness;
- preserve missingness, provenance, and the existing fail-closed FHIR mapping boundaries;
- do not add a national FHIR profile claim without reproducible validation evidence.

If you find a vulnerability, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Set up the project

ParkinSync uses Python 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-fhir.txt
```

Run the unit tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Validate a change

Run the checks relevant to your change. Documentation-only changes should at least run the public
repository boundary check and README link tests.

```bash
python3 scripts/check_public_repo.py --working-tree
PYTHONPATH=src python -m unittest tests.test_readme_links -v
python scripts/check_public_artifacts.py
python scripts/generate_synthetic_fixture.py --check
python scripts/export_synthetic_fhir.py --check
PYTHONPATH=src python scripts/generate_grounded_summary.py --check
PYTHONPATH=src python scripts/generate_weekly_fhir.py --check
PYTHONPATH=src python scripts/generate_nzbase_fhir.py --check
PYTHONPATH=src python scripts/generate_jpcore_fhir.py --check
```

The full CI workflow also runs the pinned HL7 Validator CLI and jurisdiction-specific validation.
Do not weaken or bypass a failing public-boundary, security, data-quality, or FHIR validation check.

## Make a pull request

1. Open or reference an issue that states the intended outcome and acceptance evidence.
2. Create a focused branch from the current `main` unless a maintainer directs otherwise.
3. Add or update tests for behavior changes.
4. Keep generated artifacts deterministic and commit them only when the repository already tracks
   that artifact class.
5. Update documentation and [CHANGELOG.md](CHANGELOG.md) when the user-visible or maintainer-visible
   behavior changes.
6. Complete every applicable item in the pull request template and record the commands you ran.

Do not deploy AWS resources or run tests against production as part of a contribution. A dry-run
package check is available for deployment-related changes:

```bash
DRY_RUN=1 DEPLOY_TARGET=iot bash deploy.sh
```

Submission of a contribution indicates that you agree to license it under the repository's
[MIT License](LICENSE).
