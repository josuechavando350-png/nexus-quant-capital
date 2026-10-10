import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from verify_funding import verify, metrics, economics, HERE


class FundingReadbackTests(unittest.TestCase):
    def test_retained_replays_are_network_free_and_not_admission(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            report = verify(HERE / "inputs/funding-scenarios.zip")
        self.assertFalse(report["census_closed"])
        e = report["economics"]
        self.assertIsNone(e["complete_profit_wei"])
        self.assertEqual(e["balancer_residual_after_atomic_payment_before_gas_wei"], "240390311727552")
        self.assertEqual(e["aave_residual_if_matching_payment_before_gas_wei"], "-5101616615551362")
        for profile in e["gas_component_profiles"]:
            self.assertGreater(int(profile["stress"][0]["remaining_for_all_other_costs_wei"]), 0)
            self.assertLess(int(profile["stress"][2]["remaining_for_all_other_costs_wei"]), 0)

    def test_corrupted_archive_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.zip"
            p.write_bytes((HERE / "inputs/funding-scenarios.zip").read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "archive digest"):
                verify(p)

    def test_duplicate_metrics_and_missing_test_success_rejected(self):
        with zipfile.ZipFile(HERE / "inputs/funding-scenarios.zip") as z:
            raw = z.read("bid-offline-002/balancer_bid/normal.log")
        with self.assertRaisesRegex(ValueError, "duplicate metric"):
            metrics(raw + b"\n  NQC_RANK1_FORK_WETH_SURPLUS_WEI: 123\n")
        with self.assertRaisesRegex(ValueError, "successful test"):
            metrics(raw.replace(b"2 passed; 0 failed; 0 skipped", b"0 passed; 2 failed; 0 skipped"))

    def test_double_counted_bid_rejected(self):
        report = verify(HERE / "inputs/funding-scenarios.zip")
        altered = copy.deepcopy(report["metrics"])
        altered["bid-offline-002"]["balancer_bid/normal"]["WETH_SURPLUS_WEI"] -= 95915734379292898
        with self.assertRaisesRegex(ValueError, "double counted"):
            economics(altered, 59451728)


if __name__ == "__main__":
    unittest.main()
