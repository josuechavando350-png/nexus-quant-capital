"""Offline tests, no network or account side effects."""
from pathlib import Path
import sys
import unittest

here=Path(__file__).resolve().parent
sys.path.insert(0,str(here))
suite=unittest.defaultTestLoader.discover(str(here), pattern='test_retention.py')
run=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if run.wasSuccessful() else 1)
