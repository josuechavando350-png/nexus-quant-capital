from pathlib import Path
import sys
import unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_*.py')
r=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if r.wasSuccessful() else 1)
