"""Arithmetic regression tests; synthetic witnesses never authorize trading."""
import dataclasses
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from morpho_liquidation_math import (  # noqa: E402
    PostAccrualWitness, WAD, U256, calculate, incentive_factor,
    mul_div, to_assets, to_shares,
)


class MorphoMathTests(unittest.TestCase):
    def setUp(self):
        self.w = PostAccrualWitness(
            total_borrow_assets=10000,
            total_borrow_shares=10_000_000_000,
            borrower_borrow_shares=600_000_000,
            borrower_collateral=1000,
            oracle_price=5*10**35,
            lltv=8*10**17,
        )

    def test_math_has_no_live_profit_authority(self):
        q = calculate(self.w, 300_000_000)
        self.assertEqual(q.status, "MATH_ONLY_NOT_AN_EXECUTABLE_OPPORTUNITY")
        self.assertFalse(q.certified)
        self.assertFalse(q.live_executable)
        self.assertTrue(q.prestate_liquidatable)
        self.assertEqual(q.max_safe_borrow_assets, 400)
        self.assertGreater(q.borrower_debt_assets_rounded_up, 400)
        self.assertLessEqual(q.seized_assets, self.w.borrower_collateral)
        self.assertEqual(q.repaid_shares, 300_000_000)

    def test_ceiling_vs_floor_on_share_conversion(self):
        self.assertEqual(to_assets(1, 5, 1, up=True), 1)
        self.assertEqual(to_assets(1, 5, 1, up=False), 0)
        self.assertEqual(to_shares(1, 5, 1, up=True), 166667)
        self.assertEqual(to_shares(1, 5, 1, up=False), 166666)

    def test_incentive_cap(self):
        self.assertEqual(incentive_factor(1), 1150000000000000000)
        self.assertGreater(incentive_factor(8*10**17), WAD)
        self.assertLess(incentive_factor(8*10**17), 1150000000000000000)

    def test_healthy_position_rejected(self):
        w = dataclasses.replace(self.w, oracle_price=10**36)
        with self.assertRaisesRegex(ValueError, "HEALTHY_POSITION"):
            calculate(w, 100_000_000)

    def test_no_borrower_debt(self):
        with self.assertRaises(ValueError):
            calculate(dataclasses.replace(self.w, borrower_borrow_shares=0), 1)

    def test_liquidation_cannot_repay_more_than_borrowed(self):
        with self.assertRaises(ValueError):
            calculate(self.w, self.w.borrower_borrow_shares + 1)

    def test_liquidation_cannot_seize_extra_collateral(self):
        with self.assertRaises(ValueError):
            calculate(self.w, self.w.borrower_borrow_shares)

    def test_oracle_zero_rejected(self):
        with self.assertRaises(ValueError):
            calculate(dataclasses.replace(self.w, oracle_price=0), 300_000_000)

    def test_no_market_state_rejected(self):
        with self.assertRaises(ValueError):
            calculate(dataclasses.replace(self.w, total_borrow_shares=0), 300_000_000)

    def test_lltv_invalid(self):
        for lltv in (0, WAD, WAD+1, -1, True):
            with self.subTest(lltv=lltv), self.assertRaises(ValueError):
                calculate(dataclasses.replace(self.w, lltv=lltv), 300_000_000)

    def test_avoid_floats_and_bool_as_amounts(self):
        for bad in (1.0, True, -1, '1'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                calculate(self.w, bad)

    def test_round_up_is_checked_under_uint256(self):
        with self.assertRaisesRegex(ValueError, "overflow"):
            mul_div(U256, 1, 2, up=True)
        with self.assertRaisesRegex(ValueError, "overflow"):
            mul_div(U256, 2, 2)


if __name__ == '__main__':
    unittest.main()
