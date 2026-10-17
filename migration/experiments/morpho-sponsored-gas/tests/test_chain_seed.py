"""Historical receipt arithmetic, not NQC P&L or builder sponsorship proof."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads((ROOT / "observations" / "ethereum_morpho_2026-06-26_seed.json").read_text())


class ReadonlyHistoricalSeedTests(unittest.TestCase):
    def test_gas_accounting_matches_receipt(self):
        gas = RECORD["gas_used"]
        base = int(RECORD["base_fee_per_gas_wei"])
        priority = int(RECORD["priority_fee_per_gas_wei"])
        self.assertEqual(gas * base, int(RECORD["gas_burnt_wei"]))
        self.assertEqual(gas * priority, int(RECORD["validator_priority_fee_wei"]))
        self.assertEqual(gas * (base + priority), int(RECORD["actual_fee_wei"]))
        self.assertEqual(base + priority, int(RECORD["actual_effective_gas_price_wei"]))

    def test_winner_not_callback_or_sponsored_nqc(self):
        self.assertEqual(RECORD["callback_data"], "0x")
        self.assertEqual(RECORD["scope"], "EXTERNAL_HISTORICAL_WINNER_NOT_NQC")
        self.assertIn("sponsored gas", RECORD["limits"][0])
        self.assertEqual(RECORD["chain_id"], 1)


class ComplexWinnerAccountingTests(unittest.TestCase):
    COMPLEX = json.loads((ROOT / "observations" / "ethereum_morpho_2026-10-14_complex_winner.json").read_text())

    def test_weth_movements_reconcile_without_fake_profit(self):
        o = self.COMPLEX
        self.assertEqual(
            int(o["weth_minted_raw"]),
            int(o["weth_repaid_to_morpho_raw"]) +
            int(o["weth_unwrapped_raw"]) +
            int(o["weth_unexplained_transfer_gap_raw"]),
        )
        self.assertEqual(int(o["ezeth_seized_raw"]), int(o["ezeth_sent_onward_raw"]))

    def test_gas_basefee_without_visible_priority_tip(self):
        o = self.COMPLEX
        self.assertEqual(int(o["gas_price_wei"]), int(o["base_fee_per_gas_wei"]))
        self.assertEqual(int(o["gas_used"]) * int(o["gas_price_wei"]), int(o["gas_fee_wei"]))
        self.assertEqual(int(o["priority_fee_wei"]), 0)


if __name__ == "__main__":
    unittest.main()
