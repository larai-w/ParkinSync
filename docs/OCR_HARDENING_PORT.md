# OCR Hardening Port (Issue #27)

Date: 2026-07-28
Related: [PRODUCTION_LAMBDA_RECONCILIATION.md](PRODUCTION_LAMBDA_RECONCILIATION.md) (Issue #26)

## Context

Issue #26 verified that the deployed OCR Lambda was byte-identical to the
unrelated-history branch `feature/fable5-mvp-hardening`, not to `main`. That branch
holds hardening `main` lacked, but it cannot be merged normally (no common ancestor).

Issue #27 is the decision on that branch. **Decision: port the hardened capabilities
into `main` by hand through this reviewed PR, then archive the branch.** A straight
"redeploy `main`" was rejected because `main` also had value the deployed image had
lost — most importantly the full 25-column master schema and `unquote_plus` key
decoding. The port keeps `main`'s richer output and adds the branch's hardening.

## Capability-by-capability decision

| Capability | In `main` before | In production | Decision | Value | Risk | Test |
| --- | --- | --- | --- | --- | --- | --- |
| Idempotent S3 processing (`_is_already_processed` / `_mark_as_processed`, S3 object tag) | ✗ | ✓ | **Port** | Duplicate S3 events / retries don't double-write rows to the sheet | Tag read/write needs `s3:GetObjectTagging` / `s3:PutObjectTagging`; tag-check failure fails open (treated as unprocessed) by design | `TestIdempotency` (5) + handler short-circuit test |
| OCR failure quarantine + notification (`_quarantine_and_notify`, `review/` prefix, SNS) | ✗ | ✓ | **Port** | Failed scans are copied to `review/` and a human is notified instead of silently lost | Needs `s3:CopyObject` and `sns:Publish`; SNS only fires when `SNS_TOPIC_ARN` is set; non-fatal by design | `TestQuarantine` (3) + `test_no_table_quarantines_and_returns_404` |
| Filename-based date recovery (`_infer_month_from_key`) | ✗ | ✓ | **Port** | Day-only cells ("20th") resolve using the month in the filename | Filename patterns are heuristic; returns `None` when unsure (safe) | `TestDateParsing.test_infer_month_*` (3) |
| Broader date parsing (`parse_log_date`) | ✗ (naive `replace('/','-')`) | ✓ | **Port** | Handles Japanese `4月20日`, English month names, ordinals, ISO, numeric, day-only | Wrong parse would fetch the wrong day's weather; unparseable returns `None` → "Weather N/A", no bad API call | `TestDateParsing` (9) + weather tests |
| 25-column master schema (A–Y, emoji + numeric temp cols) | ✓ | ✗ (regressed to 13 cols) | **Keep `main`** | ParkinSync's canonical daily schema; the deployed image had dropped columns | Losing it would break the downstream sheet/analytics contract | `TestHistoricalWeather` tuple tests |
| `unquote_plus` S3 key decoding | ✓ | ✗ (raw key) | **Keep `main`** | Correct handling of URL-encoded / multibyte (Japanese) object keys | Raw keys mis-handle encoded filenames | exercised via handler tests |

## Behavior change worth noting

On an unexpected error the handler now **quarantines the file and re-raises** (matching
production) instead of returning a `500` dict. For an S3-triggered Lambda this lets AWS
retry / route to a DLQ, and the idempotency tag prevents double-processing on retry.
The "no table detected" case still returns `404` (after quarantine), and success / skip
/ already-processed still return `200`.

## Verification

- `PYTHONPATH=src python -m unittest discover -s tests`: **29 tests pass** (was ~5).
- No secrets or production identifiers added: the spreadsheet ID is still read from
  Secrets Manager (`GOOGLE_SHEET_ID`), not hardcoded; only `SECRET_ID` keeps its
  pre-existing public default.

## Follow-ups

- After this PR merges, **archive `feature/fable5-mvp-hardening`** (its useful content is
  now in `main`); record the archival so the unrelated-history branch is not resurrected.
- **Completed 2026-08-12:** read-only comparison confirmed `main` and production are
  byte-identical. The obsolete Issue #26 guard was removed; production deployment
  still requires explicit owner review.
