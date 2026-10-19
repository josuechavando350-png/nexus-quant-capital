"""R5 CLI added after the timed matrix; its same gateway path was measured."""
import ast
from pathlib import Path
import unittest
from test_traversal import module, ROOT, R4


class ImportTests(unittest.TestCase):
    def test_cli_keeps_r4_input_preservation_and_fail_closed_semantics(self):
        def main_body(path):
            return next(ast.dump(n) for n in ast.parse(path.read_text()).body
                        if isinstance(n, ast.FunctionDef) and n.name == "main")
        self.assertEqual(main_body(R4 / "scripts/import_witness.py"), main_body(ROOT / "scripts/import_witness.py"))
        m = module("r5_cli_regression", R4 / "tests/test_stability.py")
        m.ROOT = ROOT
        m.StabilityTests.setUpClass()
        case = m.StabilityTests("test_offline_import_preserves_inputs_and_rejects_missing_real_proof")
        result = unittest.TestResult(); case.run(result)
        self.assertTrue(result.wasSuccessful(), str(result.errors + result.failures))


if __name__ == "__main__": unittest.main()
