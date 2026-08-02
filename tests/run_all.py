#!/usr/bin/env python3
"""Run every ARGO test. Needs no REDCap access, no tokens, no network.

    python3 tests/run_all.py
"""
import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent

if __name__ == "__main__":
    suite = unittest.TestLoader().discover(str(TESTS), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if result.wasSuccessful():
        print(f"\nAll {result.testsRun} checks passed.")
    sys.exit(0 if result.wasSuccessful() else 1)
