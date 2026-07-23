# ParkinSync — Agent Rules

## Private material — strategy, business, growth

- Business, growth, roadmap, pricing, revenue, sales/pilot, and market-analysis planning — plus
  internal worklogs and handovers — must **never** be committed to this public repo. They live in
  the private **`larai-w/veai-private`** repo (per-product folders; synced and backed up).
- Machine-local scratch may go in `docs-private/` (gitignored — local only, not synced).
- A pre-commit guard (`scripts/check_public_repo.py` via `.githooks/`) blocks this content and
  secrets from being committed here; never bypass it with `--no-verify`. On a fresh clone, run once:
  `git config core.hooksPath .githooks`.

## General

- This is a public repository. Do not commit secrets, non-anonymized data, or capstone/report
  source documents. Keep health-adjacent language limited to recording and analysis, not diagnosis.
