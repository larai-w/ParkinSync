#!/usr/bin/env python3
"""Run ParkinSync's core test suite with the repository source path configured.

The CI workflow supplies ``PYTHONPATH=src``. This small local entry point keeps the
same import boundary without requiring contributors to remember an environment
variable, and it never reaches AWS or reads production records.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"


def main() -> int:
    sys.path.insert(0, str(SRC))
    suite = unittest.defaultTestLoader.discover(str(TESTS))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
