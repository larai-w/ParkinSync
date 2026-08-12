# Changelog

Notable changes to ParkinSync are recorded here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses semantic version tags.

## [Unreleased]

### Added

- Public security reporting and authorized-testing policy.
- Contributor setup, validation, privacy, and FHIR-boundary guidance.
- Pull request checks for synthetic data, deterministic artifacts, and public-repository hygiene.

### Changed since v1.3.0

- Added reproducible synthetic HL7 FHIR R4 transaction exports, grounded summaries, seven-day
  bundles, and an ephemeral HAPI round-trip test.
- Added bounded NZ Base 3.1.0 and JP Core 1.2.0 overlays with fail-closed validation.
- Hardened OCR and indoor-temperature ingestion behavior, packaging, CI, dependency auditing, and
  public-repository controls.
- Added the synthetic GutPacer-to-ParkinSync care-event integration contract.

## [1.3.0] - 2026-05-25

### Added

- Indoor-temperature telemetry ingestion and aggregation.
- Synthetic analytics fixture, schema audit, master schema template, and user documentation.
- Lambda packaging and deployment script.
- Dependabot configuration.

## Historical tags

Versions `1.0.0`, `1.1.0`, and `1.2.0` mark early OCR-pipeline development. Detailed release notes
were not maintained for those tags, and the three tags currently reference the same historical
commit.

[Unreleased]: https://github.com/larai-w/ParkinSync/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/larai-w/ParkinSync/tree/v1.3.0
