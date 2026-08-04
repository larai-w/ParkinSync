# Synthetic NZ Base R4 profile-validation track

This directory demonstrates a bounded New Zealand profiling step on ParkinSync's tracked synthetic
seven-day FHIR transaction. It uses the current published **NZ Base 3.1.0** package, based on FHIR R4
4.0.1. It is a deterministic derivative of the existing weekly Bundle, not a separate clinical or
identity dataset.

## Profile scope

NZ Base 3.1.0 defines profiles for two of the four ParkinSync resource types:

| Resource type | Count | Validation target |
|---|---:|---|
| Patient | 1 | `http://hl7.org.nz/fhir/StructureDefinition/NzPatient` |
| MedicationStatement | 14 | `http://hl7.org.nz/fhir/StructureDefinition/NzMedicationStatement` |
| Observation | 14 | Base FHIR R4; NZ Base 3.1.0 defines no Observation profile |
| CarePlan | 1 | Base FHIR R4; NZ Base 3.1.0 defines no CarePlan profile |

The generator adds the applicable canonical URL to each resource's `meta.profile`. The transaction
request URLs, fullUrls, references, medication status/dose/time, Observation code/value/unit/time,
CarePlan content, and synthetic resource IDs remain unchanged. The derivative Bundle receives a new
synthetic logical ID so the two public artifacts cannot be confused.

## No-inference boundary

The synthetic Patient retains the local temporary identifier under
`https://veai.jp/fhir/synthetic-patient`. The generator does **not** create an NHI or infer NZ
ethnicity, iwi, citizenship, residency, address, sex at birth, or another demographic extension.
Medication remains explicit text because the source does not contain a reviewed NZMT code.

These omissions are intentional data-quality behavior. A fabricated NHI or terminology code would
make a validator example look richer while weakening factual integrity.

## Evidence

[`generated/manifest.json`](generated/manifest.json) pins:

- package `fhir.org.nz.ig.base#3.1.0`;
- source and derivative SHA-256 digests;
- exact resource and profile counts;
- base-R4-only resource types; and
- excluded inferences and validation scope.

The public-artifact guard independently reconstructs the allowed overlay and rejects any other
semantic difference. Unit tests cover deterministic output, exact profile placement, no NHI, no
NZMT invention, fail-closed source classification, and reproducibility.

## Run

```bash
PYTHONPATH=src python scripts/generate_nzbase_fhir.py --check
PYTHONPATH=src python -m unittest tests.test_fhir_nzbase -v

# Requires Java 17+ and the pinned HL7 Validator CLI used by CI.
FHIR_VALIDATOR_JAR=/path/to/validator_cli.jar \
  NZ_BASE_PACKAGE='fhir.org.nz.ig.base#3.1.0' \
  scripts/validate_fhir_nzbase.sh
```

The validator loads the pinned published package and runs with `-tx n/a`; no public terminology
server is queried. CI caches downloaded FHIR packages and still verifies the package version on every
run.

### Validator result and warning boundary

The first pinned-package [CI validation](https://github.com/larai-w/ParkinSync/actions/runs/30869044857)
completed with **0 errors, 79 warnings, and 74 notes**. The warnings are retained rather than hidden:

- UCUM and NZMT terminology cannot be fully checked while the public terminology server is disabled;
- `DomainResource.text` narrative is a FHIR best-practice recommendation, not a profile requirement;
- Observation performer is recommended, but the synthetic source has no factual performer; and
- the local synthetic-classification code system is intentionally outside the NZ Base package.

These are explicit evidence limitations. The demo does not invent an NZMT code, performer, narrative,
or demographic fact merely to reduce warning counts. A future terminology-enabled validation track
requires a separately approved server, licensing, privacy, and reproducibility decision.

## Conformance boundary

This proves instance validation for the declared `NzPatient` and `NzMedicationStatement` profiles
against the named package version. It does not prove a complete NZ use case, NZ Patient Summary,
terminology-server, NHI integration, production API, clinical, security, performance, medical-device,
regulatory, or arbitrary New Zealand implementation conformance. NZ Base is a reusable base guide and
does not by itself define which profiles or interactions a particular implementation must support.

Official references:

- [NZ Base Implementation Guide 3.1.0](https://fhir.org.nz/ig/base/)
- [NZ Base profile index](https://fhir.org.nz/ig/base/profiles.html)
- [FHIR R4 specification](https://hl7.org/fhir/R4/)
