"""Fail-closed regression tests, sponsorship for deploy + execute."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bundle_gate import check  # noqa: E402

BASE = json.loads((ROOT / "fixtures" / "synthetic_two_transaction_bundle.json").read_text())


def scenario(**changes):
    return {**BASE, **changes}


class BundleSponsorTests(unittest.TestCase):
    def test_base_blocks_unknown_deployment_and_physical_evidence(self):
        got = check(BASE)
        self.assertEqual(got.status, "BLOCKED")
        self.assertFalse(got.certified)
        self.assertFalse(got.live_executable)
        self.assertEqual(got.required_upfront_wei, 4_200_000_000_000_000)
        self.assertIn("BUILDER_SPONSORED_DEPLOYMENT_NOT_CONFIRMED", got.blockers)
        self.assertIn("SYNTHETIC_INPUT_NOT_REAL_BUNDLE", got.blockers)

    def test_zero_gas_sender_required(self):
        self.assertIn("NONZERO_OPERATOR_OR_EXECUTOR_CAPITAL", check(scenario(sender_initial_eth_wei="1")).blockers)

    def test_deployment_gas_cannot_be_omitted(self):
        self.assertIn("INSUFFICIENT_SPONSOR_ADVANCE_FOR_BOTH_TRANSACTIONS",
                      check(scenario(builder_advance_wei="2400000000000000")).blockers)

    def test_builder_must_keep_margin(self):
        self.assertIn("BUILDER_VALUE_INSUFFICIENT_AFTER_SPONSOR_COST",
                      check(scenario(builder_value_gross_wei="4550000000000000")).blockers)

    def test_coinbase_tip_not_builder_income(self):
        got = check(scenario(coinbase_tip_wei="999999999999999999"))
        self.assertIn("BUILDER_NET_BALANCE_NOT_VERIFIED", got.blockers)

    def test_perfect_synthetic_is_blocked(self):
        got = check(scenario(builder_receipts_verified=True, builder_value_measured=True,
            route_replayed=True, morpho_callback_replayed=True,
            target_tx_competition_replayed=True, builder_sponsored_deployment_supported=True))
        self.assertEqual(got.blockers, ["SYNTHETIC_INPUT_NOT_REAL_BUNDLE"])

    def test_historical_flags_do_not_certify(self):
        got = check(scenario(evidence_type="HISTORICAL_BUNDLE_TRACE",
            builder_receipts_verified=True, builder_value_measured=True,
            route_replayed=True, morpho_callback_replayed=True,
            target_tx_competition_replayed=True, builder_sponsored_deployment_supported=True))
        self.assertEqual(got.status, "MODEL_SCREEN_PASS_ONLY")
        self.assertFalse(got.certified)
        self.assertFalse(got.live_executable)

    def test_reversed_transactions_invalid(self):
        with self.assertRaises(ValueError):
            check(scenario(txs=list(reversed(BASE["txs"]))))

    def test_nonce_gap_invalid(self):
        txs = [dict(t) for t in BASE["txs"]]
        txs[1]["nonce"] = 3
        with self.assertRaises(ValueError):
            check(scenario(txs=txs))

    def test_mixed_signers_invalid(self):
        txs = [dict(t) for t in BASE["txs"]]
        txs[1]["from"] = "0x0000000000000000000000000000000000000001"
        with self.assertRaises(ValueError):
            check(scenario(txs=txs))

    def test_negative_advance_invalid(self):
        with self.assertRaises(ValueError):
            check(scenario(builder_advance_wei="-1"))

    def test_unknown_builder_invalid(self):
        with self.assertRaises(ValueError):
            check(scenario(builder="OTHER"))

    def test_undeclared_profit_invalid(self):
        with self.assertRaises(ValueError):
            check(scenario(extra_profit=1))


if __name__ == "__main__":
    unittest.main()
