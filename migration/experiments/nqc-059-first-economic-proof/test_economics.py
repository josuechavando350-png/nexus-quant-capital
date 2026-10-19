import json
import unittest
from decimal import Decimal
from pathlib import Path
from economics import (
    payout_allocation, bounded_residual, decimal_amount,
    decimal_display_interval, run,
)

CASE = json.loads((Path(__file__).resolve().parent / 'reported_case.json').read_text(encoding='utf-8'))

class ExactLedgerTests(unittest.TestCase):
    def test_payouts_exact_same_asset(self):
        a = payout_allocation(CASE)
        self.assertEqual(a['observed_source_reported_payout_total_WETH'], '0.216220')
        self.assertFalse(a['coinbase_is_builder_proven'])
    def test_discrepancy_vs_rounded_display(self):
        a = payout_allocation(CASE)
        self.assertNotEqual(a['observed_source_reported_payout_total_WETH'], CASE['post_exit_display_WETH'])
    def test_round_to_nearest_interval(self):
        lo, hi = decimal_display_interval('0.2162', 4, 'nearest')
        self.assertEqual(lo, Decimal('0.21615'))
        self.assertEqual(hi, Decimal('0.21625'))
    def test_truncation_interval(self):
        lo, hi = decimal_display_interval('0.2162', 4, 'truncated')
        self.assertEqual(lo, Decimal('0.2162'))
        self.assertEqual(hi, Decimal('0.2163'))
    def test_rounding_max_conditional_slack(self):
        b = bounded_residual(CASE, 'nearest')
        self.assertEqual(b['residual_conditional_upper_exclusive_WETH'], '0.000030')
        self.assertEqual(b['residual_conditional_lower_WETH'], '0')
        self.assertTrue(b['post_exit_interval_right_open'])
        self.assertFalse(b['extra_sponsor_ETH_can_be_inferred'])
    def test_truncation_max_conditional_slack(self):
        b = bounded_residual(CASE, 'truncated')
        self.assertEqual(b['residual_conditional_upper_exclusive_WETH'], '0.000080')
        self.assertEqual(b['residual_conditional_lower_WETH'], '0')
    def test_unknown_sponsor_or_economic_admission(self):
        data = run()
        self.assertIsNone(data['sponsor_terms'])
        self.assertIsNone(data['gas_price'])
        self.assertFalse(data['commercial_admission'])
        self.assertEqual(data['outcome_for_NQC'], 'UNKNOWN')
    def test_float_and_negative_rejected(self):
        for v in (0.5, '-0.1', '1e3', 'NaN', 'Infinity'):
            with self.assertRaises(ValueError):
                decimal_amount(v)
    def test_no_cross_asset_combination(self):
        x = dict(CASE)
        x['denomination'] = 'ETH'
        with self.assertRaises(ValueError):
            payout_allocation(x)
    def test_rounding_boundary_unproven_if_insolvent(self):
        x = dict(CASE)
        x['coinbase_payout_WETH'] = '0.300000'
        b = bounded_residual(x, 'nearest')
        self.assertFalse(b['solvent_reported_allocation_possible'])
        self.assertIsNone(b['residual_conditional_upper_exclusive_WETH'])

if __name__ == '__main__':
    unittest.main()
