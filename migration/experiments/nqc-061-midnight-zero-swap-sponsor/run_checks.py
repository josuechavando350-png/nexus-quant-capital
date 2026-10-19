"""NQC061 offline checks. Does not try to fetch onchain data."""
from pathlib import Path
import unittest
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
suite = unittest.defaultTestLoader.discover(str(ROOT),pattern='test_*.py')
res=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if res.wasSuccessful() else 1)
