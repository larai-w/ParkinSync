# Production OCR Lambda Reconciliation (Issue #26)

Original finding: 2026-07-28
Reconciled: 2026-08-12
Scope: `ParkinSync_OCR_Handler` (`us-east-1`)

All production checks described here were read-only. No Lambda invocation, code
update, configuration update, or production-data access was performed.

## Current status

**Production and repository `main` are reconciled.** On 2026-08-12, the deployed
ZIP was exported and its single `lambda_function.py` was compared with
`src/ParkinSync_OCR_Handler.py` at `main` commit
`47ccbc518da0784d0491207202ed15124cf95398`.

| Evidence | Result |
| --- | --- |
| Source size | 14,306 bytes in both locations |
| Source SHA-256 | `c4efd393ca0aac04bbd09a0c3eeab9c98c444ece4ca93843930f5105d62001dd` |
| Byte comparison | Exact match |
| Syntax parse | Pass |
| Runtime / handler | Python 3.12 / `lambda_function.lambda_handler` |
| Immutable release | `prod` alias points to version 2, matching the deployed source |
| Latest-main CI | CI and security baseline passed for the compared commit |

The production function was last modified on 2026-08-02. That deployment resolved
the mismatch recorded on 2026-07-28.

## Historical finding

The 2026-07-28 production export did not match the then-current `main`:

| Source at the time | SHA-256 | Matched production? |
| --- | --- | --- |
| Deployed `lambda_function.py` | `5408b36f…b2b2019` | — |
| `feature/fable5-mvp-hardening:src/lambda_function.py` | `5408b36f…b2b2019` | Yes |
| `main:src/ParkinSync_OCR_Handler.py` | `6e3d9c46…0db9710` | No |

Production then carried idempotent S3 processing, OCR-failure quarantine and
notification, filename-based date recovery, and broader date parsing that `main`
lacked. Issue #27 subsequently ported those capabilities while retaining `main`'s
25-column schema and URL-decoding of S3 object keys.

This history explains why `deploy.sh` previously required
`ALLOW_UNRECONCILED_DEPLOY=1` for OCR releases. That override is no longer needed
and the stale block has been removed.

## Deployment configuration

The reconciliation audit found different intentional production timeouts for the
two functions:

- OCR handler: 90 seconds
- Indoor telemetry logger: 60 seconds

`deploy.sh` now preserves these independently with `OCR_LAMBDA_TIMEOUT` and
`IOT_LAMBDA_TIMEOUT`. A dry run builds and validates the packages without updating
AWS:

```bash
DRY_RUN=1 DEPLOY_TARGET=ocr bash deploy.sh
DRY_RUN=1 DEPLOY_TARGET=iot bash deploy.sh
```

A real production deployment still requires explicit owner review and approval.
Reconciliation removes an obsolete safety block; it does not authorize deployment.

## Rollback

The `prod` alias targets an immutable published version. If a future release
regresses, move the alias back to the last known-good version or redeploy the last
known-good commit through the reviewed release path. Do not hot-fix production from
an uncommitted local file.
