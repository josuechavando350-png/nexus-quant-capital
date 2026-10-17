"""Negative admission regression suite; standard-library-only; no RPC, no secrets."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from preflight import check  # noqa: E402

SOURCE = json.loads((ROOT / "fixtures" / "illustrative.json").read_text())


def sample(**overrides):
    return {**SOURCE, **overrides}


class PreflightTests(unittest.TestCase):
    def test_realistic_synthetic_fixture_must_block(self):
        got = check(SOURCE)
        self.assertEqual(got.status, "BLOCKED")
        self.assertIn("EXECUTOR_NOT_DEPLOYED_OR_SPONSORED_DEPLOYMENT_UNPROVEN", got.blockers)
        self.assertIn("REAL_DEX_ROUTE_NOT_SIMULATED", got.blockers)
        self.assertIn("BUILDER_REVENUE_NOT_MEASURED", got.blockers)
        self.assertIn("CAPTURE_COMPETITION_UNPROVEN", got.blockers)
        self.assertEqual(got.operator_profit_loan_units, 3500000)
        self.assertFalse(got.is_live_executable)

    def test_no_deployment_is_blocker(self):
        self.assertIn("EXECUTOR_NOT_DEPLOYED_OR_SPONSORED_DEPLOYMENT_UNPROVEN", check(sample()).blockers)

    def test_no_real_swap_is_blocker(self):
        self.assertIn("REAL_DEX_ROUTE_NOT_SIMULATED", check(sample()).blockers)

    def test_no_builder_revenue_proof_is_blocker(self):
        self.assertIn("BUILDER_REVENUE_NOT_MEASURED", check(sample()).blockers)

    def test_sponsor_cannot_cover_maximum_gas(self):
        got = check(sample(builder_sponsor_advance_wei="100000000000000"))
        self.assertIn("SPONSOR_CANNOT_PREPAY_GAS_LIMIT", got.blockers)

    def test_eth_tip_must_be_funded_by_conversion(self):
        got = check(sample(native_eth_out_wei="0"))
        self.assertIn("BUILDER_TIP_NOT_FUNDED_WITH_ETH", got.blockers)

    def test_positive_loan_profit_is_not_enough_for_builder(self):
        got = check(sample(builder_revenue_wei="100000000000000"))
        self.assertIn("BUILDER_NOT_REPAID_WITH_MARGIN", got.blockers)
        self.assertEqual(got.operator_profit_loan_units, 3500000)

    def test_negative_loan_profit_blocks(self):
        got = check(sample(collateral_loan_out_units="101000000"))
        self.assertIn("OPERATOR_NET_PROFIT_NON_POSITIVE", got.blockers)

    def test_wrong_gas_fields_block(self):
        got = check(sample(effective_gas_price_wei="3000000000", gas_used=400001))
        self.assertIn("INVALID_EIP1559_GAS_FEES", got.blockers)
        self.assertIn("GAS_EXCEEDS_LIMIT_OR_ZERO", got.blockers)

    def test_unverified_liquidation_blocks(self):
        got = check(sample(morpho_liquidatable=False, prestate_observed=False))
        self.assertIn("POSITION_NOT_LIQUIDATABLE_AT_PRESTATE", got.blockers)
        self.assertIn("PRESTATE_NOT_AUTHENTICATED", got.blockers)

    def test_synthetic_perfect_quote_still_blocked(self):
        got = check(sample(executor_deployed=True, collateral_compatibility_proven=True,
                           route_simulated_exact_state=True, builder_revenue_measured=True,
                           competition_evidence_proven=True))
        self.assertEqual(got.blockers, ["SYNTHETIC_ONLY_NOT_HISTORICAL_PROOF"])

    def test_zero_operator_wallet_is_mandatory(self):
        got = check(sample(zero_operator_eth=False, zero_operator_tokens=False))
        self.assertIn("EXTERNAL_ETH_SUBSIDY_PRESENT", got.blockers)
        self.assertIn("EXTERNAL_TOKEN_SUBSIDY_PRESENT", got.blockers)

    def test_strict_fields_prevent_undeclared_profits(self):
        with self.assertRaises(ValueError):
            check(sample(extra_profit="9999999"))

    def test_bad_block_hash_rejected(self):
        with self.assertRaises(ValueError):
            check(sample(block_hash="not_a_real_block"))

    def test_negative_values_rejected(self):
        with self.assertRaises(ValueError):
            check(sample(repaid_loan_units="-1"))

    def test_booleans_not_silently_accepted_as_money(self):
        with self.assertRaises(ValueError):
            check(sample(repaid_loan_units=True))

    def test_historical_model_pass_not_equal_execution_certification(self):
        got = check(sample(evidence_type="HISTORICAL_REPLAY", executor_deployed=True,
                           collateral_compatibility_proven=True, route_simulated_exact_state=True,
                           builder_revenue_measured=True, competition_evidence_proven=True))
        self.assertEqual(got.status, "MODEL_SCREEN_PASS_ONLY")
        self.assertFalse(got.is_live_executable)
        self.assertFalse(got.is_capture_proven)
        self.assertEqual(got.certification, "NOT_CERTIFIED")


if __name__ == "__main__":
    unittest.main()
