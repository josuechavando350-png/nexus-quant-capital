import unittest
import gzip
from fractions import Fraction

from profitability_boundary import (MAX_RESERVE, WAD, amount_out, liquidation,
                                    minimum_depth, minimum_loan_reserve, report,
                                    reconcile_trace, ROOT)


class ProfitabilityBoundaryTests(unittest.TestCase):
    def test_exact_threshold_against_exhaustive_small_integer_pools(self):
        # Independent enumeration covers floor rounding and the equality limit.
        for amount in (1, 7, 31):
            for price in (Fraction(2, 3), Fraction(9, 10), Fraction(5, 2)):
                for target in range(1, 80):
                    boundary = minimum_depth(amount, target, price)
                    observed = next((k for k in range(1, 500)
                                     if amount_out(amount, price.denominator*k,
                                                   price.numerator*k) >= target), None)
                    if observed is not None:
                        self.assertTrue(boundary['possible'])
                        self.assertEqual(boundary['scale'], observed)
                    elif boundary['possible']:
                        self.assertGreaterEqual(boundary['scale'], 500)

    def test_old_budget_impossible_at_any_depth_and_fee_limit_is_strict(self):
        self.assertFalse(minimum_depth(liquidation().seized_assets, 85*WAD//10,
                                       Fraction(9, 10))['possible'])
        self.assertFalse(minimum_depth(1000, 997, Fraction(1))['possible'])

    def test_fixed_reserve_price_boundary_has_exact_neighbor(self):
        s = liquidation().seized_assets; x = 1000*WAD
        for target in (8*WAD, 811*WAD//100, 85*WAD//10):
            y = minimum_loan_reserve(s, x, target)
            self.assertGreaterEqual(amount_out(s, x, y), target)
            self.assertLess(amount_out(s, x, y-1), target)

    def test_pair_capacity_and_invalid_inputs_fail_closed(self):
        with self.assertRaises(ValueError): amount_out(1, MAX_RESERVE, 1)
        with self.assertRaises(ValueError): minimum_depth(True, 1, Fraction(1))
        with self.assertRaises(ValueError): minimum_depth(1, 1, 0.9)
        self.assertFalse(minimum_depth(MAX_RESERVE, 1, Fraction(1))['possible'])

    def test_healthy_counterfactual_is_not_a_candidate_and_costs_remain_unknown(self):
        r = report()
        self.assertEqual([x['protocol_math_permits'] for x in r['counterfactual_incentive_sensitivity']],
                         [True, True, False, False])
        self.assertIsNone(r['actual_gas_cost'])
        self.assertFalse(r['certified'])
        for row in r['depths']:
            self.assertEqual(row['spot_value']-row['impact_without_fee']-row['additional_fee_effect'],
                             row['executable_out'])

    def test_original_code_trace_matches_and_altered_boundary_is_rejected(self):
        text = gzip.decompress((ROOT/'evidence/2026-10-17-profitability/economic-boundary-traces.log.gz').read_bytes()).decode()
        observed = reconcile_trace(text)
        self.assertEqual(observed['boundary_rows_matched'], 4)
        self.assertIsNone(observed['production_gas'])
        with self.assertRaises(ValueError):
            reconcile_trace(text.replace('dexOut: 8109999999999999999', 'dexOut: 8110000000000000000', 1))
