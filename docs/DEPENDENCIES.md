# Linux application and FHIR dependency snapshot

`constraints-python312.txt` pins direct and transitive versions for the Python
3.12 Linux x86_64 application/FHIR CI environment. Its initial snapshot comes from the
successful [main CI run on 2026-10-06](https://github.com/larai-w/ParkinSync/actions/runs/37392300841).
This is a version snapshot, not a wheel/hash lock or proof that the packages are
free of vulnerabilities. The dependency audit remains a separate check.

Use a fresh Linux environment so unrelated installed tools do not mask missing pins:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install pip==26.2.1
python -m pip install -r requirements.txt -r requirements-fhir.txt -c constraints-python312.txt
python -m pip check
python scripts/check_dependency_snapshot.py
python scripts/run_local_tests.py
```

CI installs with the same constraint file and fails if a package is missing,
has changed version, or was added transitively without a pin. The pip/setuptools/
wheel toolchain is excluded from the application snapshot; the install command
pins pip separately. Updating a direct requirement without updating its resolved
snapshot either fails resolution or fails the post-install check.

For an intentional update, resolve the requirements in a disposable Python 3.12
environment, inspect the full package/version diff, update the constraints, and
run `pip check`, the snapshot check, the synthetic tests, and the dependency audit.
Review the PR and its CI results before merging. Avoid accepting unrelated
upgrades merely because the resolver selected them.

The optional P3 environment (`analytics/requirements-p3.txt`) is separate and is
not covered by this snapshot. Install and verify it in another environment; its
extra packages would correctly fail the application/FHIR snapshot check.
`deploy.sh` uses existing production Lambda layers by default. Vendoring and
production layer contents are not frozen by this local/CI snapshot; a production
release still needs its artifact/layer verification and owner approval.

This snapshot is not a cross-platform lock. In particular, cryptography 50.0.2
does not publish an Intel macOS wheel, so a binary-only install of this Linux
snapshot fails there. General local development still uses the unconstrained
requirements command in the README; do not weaken the security floor or silently
replace the CI snapshot with a different local version.
