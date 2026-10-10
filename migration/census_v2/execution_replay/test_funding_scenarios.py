import re
import tempfile
from pathlib import Path
import unittest
import zipfile
from funding_scenarios import scenario_bytes, apply_scenario, SCENARIO_SHAS
from run_fork import TEST_PATH
from rpc_witness import sha


class FundingScenarioTests(unittest.TestCase):
    def original(self):
        with zipfile.ZipFile(Path(__file__).parent / "inputs/rpc-recovery.zip") as z:
            return z.read("nodies-004/source/" + TEST_PATH)

    def test_both_scenarios_keep_every_original_assertion(self):
        raw = self.original()
        conditions = re.findall(r'require\((.*?)\);', raw.decode(), re.S)
        for variant, digest in SCENARIO_SHAS.items():
            with self.subTest(variant=variant):
                modified = scenario_bytes(raw, variant)
                self.assertEqual(sha(modified), digest)
                retained = re.findall(r'require\((.*?)\);', modified.decode(), re.S)
                for condition in conditions:
                    if variant.startswith("balancer") and 'premiumBps == 5' in condition:
                        continue  # Replaced only by that provider's observed fee rule.
                    self.assertIn(condition, retained)
                self.assertIn("type(uint96).max", modified.decode())
                self.assertIn("FAILED_OPERATION_CONSUMED_IDENTITY", modified.decode())

    def test_overlay_rejects_changed_sources_wrong_pin_and_repeat(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / TEST_PATH
            p.parent.mkdir()
            p.write_bytes(self.original())
            with self.assertRaisesRegex(ValueError, "postimage"):
                apply_scenario(root, "balancer", "00" * 32)
            apply_scenario(root, "balancer", SCENARIO_SHAS["balancer"])
            with self.assertRaisesRegex(ValueError, "preimage"):
                apply_scenario(root, "balancer", SCENARIO_SHAS["balancer"])
        with self.assertRaises(ValueError):
            scenario_bytes(self.original() + b"\n", "aave")


if __name__ == "__main__":
    unittest.main()
