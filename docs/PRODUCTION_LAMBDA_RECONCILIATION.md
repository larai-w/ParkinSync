# Production OCR Lambda Reconciliation (Issue #26)

Date: 2026-07-28
Scope: `ParkinSync_OCR_Handler` (production, `us-east-1`)
Method: read-only AWS export + hash + source comparison. No production code was
modified and no invocation was performed. No secrets, environment values, or care
data are recorded here.

## Summary (verified source of truth)

**Production is NOT running repository `main`.** The deployed OCR Lambda is
byte-identical to the isolated-history branch `feature/fable5-mvp-hardening`, which
carries hardening that `main` does not have. `main` is a simpler, older
implementation.

Two consequences:

1. Repository `main` must **not** be described as matching production.
2. Running `deploy.sh` from `main` as-is would **overwrite the hardened production
   code with the simpler `main` code** — a regression on a health-safety path. See
   the guardrail added to `deploy.sh`.

## Evidence

Exported with `aws lambda get-function` / `get-function-configuration` (read-only):

| Property | Value |
| --- | --- |
| Handler | `lambda_function.lambda_handler` |
| Runtime | `python3.12` |
| Deployed package | single `lambda_function.py` (no vendored deps in the package) |
| Package `CodeSha256` | `n5O5xQLpe7AfgDP6B9u1qk7yMWrOw3QmyV6imLSmQ8E=` |
| Deployed `lambda_function.py` sha256 | `5408b36f8df8f90c3e281e1f3db9652de6b2738059fce7326e77cb937e2b2019` |
| Deployed LastModified | 2026-07-12 |

Source comparison (sha256 of the handler source):

| Source | sha256 | Matches production? |
| --- | --- | --- |
| Deployed `lambda_function.py` | `5408b36f…b2b2019` | — |
| `feature/fable5-mvp-hardening:src/lambda_function.py` | `5408b36f…b2b2019` | **YES — byte-identical** |
| `main:src/ParkinSync_OCR_Handler.py` | `6e3d9c46…0db9710` | No |

## Handler contract and behavior comparison

Both versions share the same trigger contract: S3 event
(`event['Records'][0]['s3']…`), handler name `lambda_function.lambda_handler`,
runtime `python3.12`. The behavioral gap is entirely additive hardening present in
production and absent from `main`:

| Capability | `main` | Production (deployed) | Issue #27 candidate |
| --- | --- | --- | --- |
| Idempotent S3 processing (`_is_already_processed` / `_mark_as_processed`) | ✗ | ✓ | yes |
| OCR failure quarantine + notification (`_quarantine_and_notify`, SNS) | ✗ | ✓ | yes |
| Filename-based date recovery (`_infer_month_from_key`) | ✗ | ✓ | yes |
| Broader date parsing (`parse_log_date(fallback_month=…)`) | ✗ | ✓ | yes |
| Skips `review/`-prefixed objects | ✗ | ✓ | — |
| Decodes S3 key with `urllib.parse.unquote_plus` | ✓ | ✗ (uses raw key) | — |

The four hardening capabilities are exactly the "candidate capabilities" listed in
**Issue #27**. In other words, production already runs the isolated branch's hardened
OCR path; #27's port-or-reject decision should treat production behavior as the
reference, not as an untested proposal.

One divergence runs the other way: `main` decodes the S3 object key with
`unquote_plus` (safer for URL-encoded / multibyte filenames) while the deployed code
uses the raw key. Any port to `main` should keep the hardened capabilities **and**
the safer key decoding.

## Decision (recommended — pending owner ratification)

Do **not** redeploy `main` to "reconcile". `main` is behind production; deploying it
would remove idempotency, failure quarantine/notification, and date recovery from a
health-safety path.

Recommended path (also resolves #27):

1. Treat the deployed / `feature/fable5-mvp-hardening` OCR code as the production
   source of truth.
2. Port the four hardened capabilities **plus** `main`'s safer `unquote_plus` key
   decoding into `main` through normal reviewed PRs, with tests.
3. Only after `main` demonstrably matches or supersedes production behavior, allow
   `deploy.sh` from `main`.

## Smoke test and rollback evidence

- **Non-sensitive smoke test:** the exported production `lambda_function.py` passes
  `python3 -m py_compile` (syntactically valid). No production invocation was run;
  invoking the live OCR path would touch Google Sheets / SNS / care data and is out
  of scope for a non-sensitive check. The isolated branch also carries
  `tests/test_lambda_function.py` as the relevant suite for this code.
- **Rollback evidence:** the exact production artifact is recoverable — the deployed
  `lambda_function.py` is byte-identical to `feature/fable5-mvp-hardening`
  (sha256 `5408b36f…b2b2019`), which is committed in this repository. If a future
  deploy regresses production, redeploying that source restores current behavior.

## Follow-ups

- Port hardened capabilities into `main` via PRs (Issue #27).
- After the port, update `deploy.sh` so it deploys the reconciled `main` and remove
  the guardrail comment.
- Keep the private handoff note's "production source of truth" line in sync with this
  document.
