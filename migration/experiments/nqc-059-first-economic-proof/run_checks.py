"""New NQC059 isolated Python tests; source-history verification requires full checkout."""
from pathlib import Path
import unittest
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_*.py')
res=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if res.wasSuccessful() else 1)
