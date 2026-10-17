import copy
import json
import unittest

from monthly_census import (EVIDENCE, audit, integer, normalize, receipt_check,
                            required_wins, validate_pages, units, log_coverage_check)
from historical_rpc_audit import load, TX_B


class MonthlyCensusTests(unittest.TestCase):
    def setUp(self):
        read = lambda name: json.loads((EVIDENCE / name).read_text())
        self.forward = [read(f'page-{i:03}.json') for i in range(3)]
        self.reverse = [read(f'reverse-{i:03}.json') for i in range(2)]
        self.seven, self.selection = read('seven-day.json'), read('selection.json')

    def rows(self, forward=None, reverse=None):
        return validate_pages(forward or self.forward, reverse or self.reverse, self.seven, self.selection)

    def test_census_is_not_profit_or_independent_opportunity_count(self):
        result = audit()
        self.assertEqual((result['windows']['30d']['observed_events'],
                          result['windows']['30d']['observed_transactions']), (143, 141))
        self.assertEqual((result['windows']['7d']['observed_events'],
                          result['windows']['7d']['observed_transactions']), (29, 28))
        self.assertEqual(result['windows']['30d']['bad_debt_events'], 43)
        self.assertEqual(result['receipt_status_counts'], {'UNAVAILABLE': 22, 'RPC_API_EVENT_CROSSCHECK': 1})
        self.assertIsNone(result['income_categories']['D_monthly_profit_expectation_usd'])
        self.assertIsNone(result['windows']['30d']['nqc_technically_eligible_count'])
        self.assertEqual(result['economic_admitted_operations'], 0)

    def test_pagination_missing_terminal_duplicate_and_conflict_fail(self):
        with self.assertRaises(ValueError):
            self.rows(forward=self.forward[:2])
        altered = copy.deepcopy(self.forward)
        altered[1]['response']['data']['marketTransactions']['items'].insert(
            0, altered[0]['response']['data']['marketTransactions']['items'][-1])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.rows(forward=altered)
        altered = copy.deepcopy(self.reverse)
        altered[0]['response']['data']['marketTransactions']['items'][0]['data']['repaidAssets'] = 1
        with self.assertRaisesRegex(ValueError, 'differs'):
            self.rows(reverse=altered)

    def test_exact_units_window_boundaries_and_unknown_receipt(self):
        for invalid in (True, 1.0, '1e18', '-1', -1, '01'):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                integer(invalid)
        self.assertEqual(units(6392502690919791, 18), '0.006392502690919791')
        row = copy.deepcopy(self.forward[0]['response']['data']['marketTransactions']['items'][0])
        for timestamp in (self.selection['start_30d']-1, self.selection['end_exclusive']):
            row['timestamp'] = timestamp
            with self.assertRaises(ValueError):
                normalize(row, self.selection['start_30d'], self.selection['end_exclusive'])
        result = receipt_check(None, self.rows()[:1])
        self.assertIsNone(result['gas_wei_per_transaction'])
        self.assertIsNone(result['net_profit'])

    def test_rpc_receipt_event_amounts_and_transaction_gas_are_checked(self):
        rows = [r for r in self.rows() if r['txHash'] == TX_B]
        receipt = load('b-receipt.json')['response']['result']
        self.assertEqual(receipt_check(receipt, rows)['gas_wei_per_transaction'], 198416195275125)
        rows[0]['repaidAssets'] += 1
        with self.assertRaises(ValueError):
            receipt_check(receipt, rows)
        with self.assertRaises(ValueError):
            receipt_check(receipt, self.rows()[:2])

    def test_missing_known_positive_log_cannot_certify_coverage(self):
        request = json.loads((EVIDENCE / 'b-morpho-logs.json').read_text())
        result = log_coverage_check(request, load('b-receipt.json')['response']['result'])
        self.assertEqual(result['status'], 'KNOWN_POSITIVE_OMISSION_OR_CONFLICT')
        self.assertEqual((result['receipt_events'], result['get_logs_events']), (1, 0))
        self.assertFalse(result['usable_for_complete_census'])

    def test_target_requirements_are_exact_and_include_fixed_costs(self):
        self.assertEqual(required_wins(100000, 10000), 10)
        self.assertEqual(required_wins(100000, 10000, 1), 11)
        self.assertEqual(required_wins(5000000, 50000, 10000), 101)
        for margin in (0, -1, 0.1, True):
            with self.subTest(margin=margin), self.assertRaises(ValueError):
                required_wins(100000, margin)
