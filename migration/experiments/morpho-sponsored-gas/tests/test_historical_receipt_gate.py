"""Negative controls: historical winning tokens must not be called NQC P&L."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from historical_receipt_gate import inspect  # noqa: E402


class HistoricalReceiptGateTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "observations/ethereum_morpho_2026-10-14_complex_winner.json"
        self.record = json.loads(path.read_text())

    def test_observed_receipt_consistent_but_no_profit(self):
        result = inspect(self.record)
        self.assertEqual(result.status, "RECEIPT_RECONCILED_INCOMPLETE_NO_PROFIT_AUTHORITY")
        self.assertEqual(result.reconciled_weth_residual_raw, 1849712239770038)
        self.assertEqual(result.observed_gas_fee_wei, 198416195275125)
        self.assertIsNone(result.profit_estimate)
        self.assertIsNone(result.ethers_received_by_nqc_wei)
        self.assertFalse(result.live_executable)
        self.assertFalse(result.certified)
        self.assertIn("BUILDER_SPONSORSHIP_AND_BUILDER_REVENUE_UNPROVEN", result.blockers)

    def test_changed_block_hash_fails(self):
        self.record["block_hash"] = "0x" + "0" * 64
        with self.assertRaises(ValueError):
            inspect(self.record)

    def test_changed_tx_fails(self):
        self.record["transaction_hash"] = "0x" + "0" * 64
        with self.assertRaises(ValueError):
            inspect(self.record)

    def test_fake_nqc_claim_fails(self):
        self.record["scope"] = "NQC_PROFIT_VERIFIED"
        with self.assertRaises(ValueError):
            inspect(self.record)

    def test_fabricated_profit_does_not_promote(self):
        self.record["profit_estimate_usd"] = 1_000_000
        self.assertIsNone(inspect(self.record).profit_estimate)

    def test_modified_weth_amount_fails(self):
        self.record["weth_unwrapped_raw"] = str(int(self.record["weth_unwrapped_raw"]) + 1)
        with self.assertRaises(ValueError):
            inspect(self.record)

    def test_modified_gas_fails(self):
        self.record["gas_fee_wei"] = str(int(self.record["gas_fee_wei"]) - 1)
        with self.assertRaises(ValueError):
            inspect(self.record)

    def test_fabricated_priority_fee_fails(self):
        self.record["priority_fee_wei"] = "1"
        with self.assertRaises(ValueError):
            inspect(self.record)

    def test_negative_or_boolean_amount_rejected(self):
        for bad in (-1, True, -1.0, "-1", "1.0"):
            with self.subTest(bad=bad):
                record = copy.deepcopy(self.record)
                record["gas_used"] = bad
                with self.assertRaises(ValueError):
                    inspect(record)

    def test_cannot_alter_morpho_identity(self):
        self.record["morpho_address"] = "0x" + "1" * 40
        with self.assertRaises(ValueError):
            inspect(self.record)


if __name__ == "__main__":
    unittest.main()
