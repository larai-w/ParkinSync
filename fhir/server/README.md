# Ephemeral HAPI FHIR round-trip evidence

This integration test submits only the tracked synthetic seven-day transaction Bundle to a temporary
HAPI FHIR R4 server inside a GitHub-hosted runner. It then reads all 30 resources by logical ID and
requires their submitted semantic content to match exactly.

## Fixed test boundary

The machine-readable [`roundtrip-contract.json`](roundtrip-contract.json) pins:

- HAPI image `hapiproject/hapi:v8.10.0-2` and its immutable image digest;
- FHIR R4 version `4.0.1` and the exact 30-resource composition;
- runner-loopback network exposure and container-local H2 storage; and
- destruction of the container and stored synthetic records after every job.

The workflow has no credentials and does not connect to participant, production, or public FHIR
systems. HAPI's starter image is intentionally used only as disposable integration-test
infrastructure; it is not secured or represented as a production deployment.

## Verification contract

[`src/fhir_roundtrip.py`](../../src/fhir_roundtrip.py) requires:

1. a loopback server URL and synthetic classification on the Bundle and every resource before POST;
2. an R4 `CapabilityStatement` declaring FHIR `4.0.1` and REST server mode;
3. one successful transaction-response entry per submitted resource;
4. response locations matching each requested `ResourceType/id`;
5. successful read-back of all 30 logical IDs;
6. retention of `meta.tag=synthetic` on every resource; and
7. exact semantic equality after a narrow normalization allowlist.

Only server-managed `meta.versionId`, `meta.lastUpdated`, and `meta.source` may differ. Transaction
`urn:uuid` references may resolve to the matching relative `ResourceType/id`. Medication status and
dose, Observation code/value/unit/time, CarePlan content, IDs, and all other submitted fields must
remain equal.

The sanitized JSON result is retained as a GitHub Actions artifact for 30 days. It contains counts,
server software metadata, and pass/fail checks, but no FHIR resource content.

## Run

The dedicated
[`FHIR server round trip`](../../.github/workflows/fhir-roundtrip.yml) workflow runs automatically
when its implementation or FHIR artifacts change, and can also be dispatched manually. Local execution
requires Docker:

```bash
HAPI_IMAGE='hapiproject/hapi:v8.10.0-2@sha256:c5e53fb34bf39958c336837795f504673103f212e179ced14c8f7b96b585a182'
docker run --detach --name parkinsync-hapi --publish 127.0.0.1:8080:8080 "$HAPI_IMAGE"
PYTHONPATH=src python scripts/verify_fhir_roundtrip.py \
  --base-url http://127.0.0.1:8080/fhir \
  --report /tmp/parkinsync-fhir-roundtrip-report.json
docker rm --force parkinsync-hapi
```

The standard unit suite uses an in-process mock FHIR server to exercise success and fail-closed paths
without Docker or network access.

This evidence demonstrates interoperability with one pinned disposable server configuration. It is
not arbitrary-server, terminology, profile, security, performance, availability, clinical, or
regulatory conformance.
