# Synthetic JP Core R4 profile-validation track

This directory demonstrates a bounded Japanese profiling step on ParkinSync's tracked synthetic
seven-day FHIR transaction. It pins **JP Core 1.2.0**, which the official publication history lists
as the current R4 release, and derives from the existing weekly Bundle rather than creating a new
clinical or identity dataset.

## Profile scope

| Resource type | Count | Validation target |
|---|---:|---|
| Patient | 1 | `http://jpfhir.jp/fhir/core/StructureDefinition/JP_Patient` |
| Observation | 14 | `http://jpfhir.jp/fhir/core/StructureDefinition/JP_Observation_VitalSigns` |
| MedicationStatement | 14 | Base FHIR R4; source has medication text but no reviewed Japanese medication code |
| CarePlan | 1 | Base FHIR R4; no reviewed JP Core use-case mapping is declared |

All 14 Observations already carry reviewed LOINC vital-sign codes, UCUM units, standard FHIR
`vital-signs` category, status, subject, effective time, and value. JP Core additionally requires a
`JP_SimpleObservationCategory_CS|vital-signs` category slice. The derivative adds that jurisdictional
classification while retaining the original standard category. This does not add a new clinical fact.
The Patient already has the identifier required by the JP Core profile, using ParkinSync's
conspicuously synthetic temporary namespace.

JP Core's MedicationStatement guidance says medication coding system, code, and display must be
present. ParkinSync's source contains only explicit demonstration text. The formal profile package
does not encode every prose requirement as a machine-enforced differential constraint, so a validator
could accept a profile declaration that is not faithful to the written guidance. This track therefore
leaves MedicationStatement at base R4 instead of inventing YJ, HOT, GS1, or local codes.

## Shared jurisdiction overlay

[`src/fhir_jurisdiction.py`](../../src/fhir_jurisdiction.py) supplies the common fail-closed contract
used by both JP Core and NZ Base:

- the source must be the reviewed 30-resource synthetic weekly transaction;
- no source resource may already declare a profile;
- each jurisdiction chooses an explicit resource-type-to-profile map and optional deterministic
  structural overlay;
- the only permitted differences are a derivative Bundle ID, exact `meta.profile` declarations, and
  the jurisdiction's explicitly reviewed overlay; and
- references, transaction requests, IDs, observations, medications, and care-plan content remain
  byte-for-byte equivalent after removing those declarations.

Country-specific modules retain their own no-inference checks because NHI/NZMT and Japanese
identifier/terminology boundaries are not interchangeable.

## Package-version risk

The official publication index lists JP Core 1.2.0 as the current R4 release dated 2025-07-30.
However, the downloadable package's own metadata currently includes `notForPublication: true` and
describes itself as a draft, despite its active 1.2.0 StructureDefinitions and release listing. The CI
pin is therefore reproducible evidence against the named package, not a claim that its metadata is
internally consistent or that it is suitable for a production procurement or compliance decision.
Any production adoption must re-check the official publication status and package digest.

## No-inference boundary

The generator does not create a Japanese patient identifier, demographics, institution, performer,
medication code, JP Core terminology coding beyond the required vital-signs category, diagnosis, or
treatment meaning. MedicationStatement and CarePlan remain base R4. This avoids making the example
look more locally complete by adding facts that do not exist in the source.

## Evidence and run

[`generated/manifest.json`](generated/manifest.json) pins the package ID, official download URL,
package SHA-256, the required `jpfhir-terminology` 1.4.0 package and digest, source and derivative
SHA-256 digests, exact profile counts, excluded inferences, and validation scope. These Japanese
packages are not currently resolvable through the standard FHIR package registries, so CI downloads
both official `jpfhir.jp` archives and verifies their digests before validation.

There is also an upstream package-ID mismatch: JP Core declares
`jpfhir-terminology.r4#1.4.0`, while the official terminology archive identifies itself as
`jpfhir-terminology#1.4.0`. CI keeps the verified archive unchanged and exposes the same files under
the dependency ID expected by the Validator package cache. This compatibility alias does not change
any CodeSystem, ValueSet, profile, or package metadata content.

```bash
PYTHONPATH=src python scripts/generate_jpcore_fhir.py --check
PYTHONPATH=src python -m unittest tests.test_fhir_jpcore -v

# Requires Java 17+ and the pinned HL7 Validator CLI used by CI.
FHIR_VALIDATOR_JAR=/path/to/validator_cli.jar \
  JP_CORE_PACKAGE='jpfhir.jp.core#1.2.0' \
  JP_CORE_PACKAGE_TGZ=/path/to/verified/package.tgz \
  JP_TERMINOLOGY_PACKAGE_TGZ=/path/to/verified/jpfhir-terminology.r4-1.4.0.tgz \
  scripts/validate_fhir_jpcore.sh
```

The validator runs with `-tx n/a`; no public terminology server receives the Bundle. Warnings remain
visible and are documented after the first main-branch CI run.

## Conformance boundary

This proves bounded instance validation for the declared Patient and VitalSigns Observation profiles
against the pinned package. It does not prove complete JP Core guidance, terminology validation,
electronic medical record integration, production server acceptance, clinical safety, security,
performance, medical-device, regulatory, or arbitrary Japanese implementation conformance. The
separate HAPI round trip checks base transaction persistence; it does not configure HAPI as a JP Core
conformance server.

Official references:

- [JP Core publication history](https://jpfhir.jp/fhir/core/)
- [JP Core Patient 1.2.0](https://jpfhir.jp/fhir/core/1.2.0/StructureDefinition-jp-patient.html)
- [JP Core MedicationStatement 1.2.0](https://jpfhir.jp/fhir/core/1.2.0/StructureDefinition-jp-medicationstatement.html)
- [JP Core VitalSigns Observation 1.2.0](https://jpfhir.jp/fhir/core/1.2.0/StructureDefinition-jp-observation-vitalsigns.html)
- [FHIR R4 specification](https://hl7.org/fhir/R4/)
