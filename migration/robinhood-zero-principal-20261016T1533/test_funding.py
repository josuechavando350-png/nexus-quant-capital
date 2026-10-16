from decimal import Decimal
import unittest

from funding_economics import evaluate, OUTCOMES


def synthetic_case(boundary='integrated'):
    # Artificial probabilities, quote and costs. Never inferred from historical cases.
    rows = {}
    for name, p, network, charge in zip(OUTCOMES, ['0.1', '0.2', '0.3', '0.4'],
                                      ['100000000000000', '50000000000000', '20000000000000', '0'],
                                      ['200000000000000', '100000000000000', '0', '0']):
        rows[name] = {'probability': p, 'network_fee_wei': network, 'sponsor_charge_wei': charge,
                      'external_invoice_wei': '0', 'offchain_cost_usdg': '0.01', 'conversion_cost_usdg': '0'}
    return dict(boundary=boundary, success_surplus_usdg='10', eth_usdg='3000', funder_share_bps='5000',
                fixed_cost_usdg_per_attempt='0.1', outcomes=rows)


class FundingTests(unittest.TestCase):
    def test_integrated_no_double_counting(self):
        result = evaluate(**synthetic_case())
        self.assertEqual(Decimal(result['expected_funder_cost_usdg']), Decimal('0.188'))
        self.assertEqual(Decimal(result['expected_funder_net_usdg']), Decimal('0.312'))
        self.assertEqual(Decimal(result['success_surplus_break_even_usdg']), Decimal('3.76'))
        self.assertFalse(result['bootstrap_funding_proven'])

    def test_external_bundler_recharges_bundle_revert(self):
        case = synthetic_case('external_bundler')
        case['outcomes']['bundle_revert']['external_invoice_wei'] = '30000000000000'
        result = evaluate(**case)
        self.assertEqual(Decimal(result['expected_funder_cost_usdg']), Decimal('0.257'))
        self.assertEqual(Decimal(result['expected_funder_net_usdg']), Decimal('0.243'))
        self.assertEqual(Decimal(result['success_surplus_break_even_usdg']), Decimal('5.14'))

    def test_rejection_still_has_offchain_and_fixed_cost(self):
        case = synthetic_case()
        for name, row in case['outcomes'].items():
            row['probability'] = str(int(name == 'preinclusion_rejection'))
        result = evaluate(**case)
        self.assertEqual(Decimal(result['expected_funder_net_usdg']), Decimal('-0.11'))
        self.assertIsNone(result['success_surplus_break_even_usdg'])

    def test_zero_share_cannot_repay_funder(self):
        case = synthetic_case(); case['funder_share_bps'] = '0'
        result = evaluate(**case)
        self.assertIsNone(result['success_surplus_break_even_usdg'])
        self.assertLess(Decimal(result['expected_funder_net_usdg']), 0)

    def test_all_share_to_funder_leaves_founder_zero(self):
        case = synthetic_case(); case['funder_share_bps'] = '10000'
        self.assertEqual(Decimal(evaluate(**case)['expected_founder_distribution_usdg']), 0)

    def test_missing_or_unknown_costs_rejected(self):
        for key in synthetic_case()['outcomes']['success']:
            for absent in (True, False):
                with self.subTest(key=key, absent=absent):
                    case = synthetic_case()
                    if absent:
                        del case['outcomes']['success'][key]
                    else:
                        case['outcomes']['success'][key] = None
                    with self.assertRaises(ValueError): evaluate(**case)

    def test_bad_numeric_values(self):
        for value in (True, 0.5, 'NaN', 'Infinity', '-1'):
            with self.subTest(value=value):
                case = synthetic_case(); case['eth_usdg'] = value
                with self.assertRaises(ValueError): evaluate(**case)

    def test_wei_integral(self):
        case = synthetic_case(); case['outcomes']['success']['network_fee_wei'] = '0.1'
        with self.assertRaises(ValueError): evaluate(**case)

    def test_four_outcomes_sum_to_one(self):
        case = synthetic_case(); case['outcomes']['success']['probability'] = '0.11'
        with self.assertRaises(ValueError): evaluate(**case)
        del case['outcomes']['success']
        with self.assertRaises(ValueError): evaluate(**case)

    def test_reverted_bundle_cannot_debit_paymaster(self):
        for name in ('bundle_revert', 'preinclusion_rejection'):
            case = synthetic_case(); case['outcomes'][name]['sponsor_charge_wei'] = '1'
            with self.assertRaises(ValueError): evaluate(**case)

    def test_rejection_cannot_have_network_fee(self):
        case = synthetic_case(); case['outcomes']['preinclusion_rejection']['network_fee_wei'] = '1'
        with self.assertRaises(ValueError): evaluate(**case)

    def test_integrated_invoice_rejected(self):
        case = synthetic_case(); case['outcomes']['bundle_revert']['external_invoice_wei'] = '1'
        with self.assertRaises(ValueError): evaluate(**case)

    def test_conversion_cost_and_fixed_cost_retained(self):
        case = synthetic_case(); case['outcomes']['success']['conversion_cost_usdg'] = '2'
        result = evaluate(**case)
        self.assertEqual(Decimal(result['expected_funder_cost_usdg']), Decimal('0.388'))

    def test_exact_break_even_is_not_profit(self):
        case = synthetic_case(); case['success_surplus_usdg'] = '3.76'
        result = evaluate(**case)
        self.assertEqual(Decimal(result['expected_funder_net_usdg']), 0)
        self.assertTrue(result['break_even_is_equality_not_positive_profit'])


if __name__ == '__main__':
    unittest.main()
