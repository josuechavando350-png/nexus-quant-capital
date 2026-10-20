"""Offline-only test runner, no Morpho API access."""
import sys
from pathlib import Path
import unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_bulk_shadow.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
