import copy
import gzip
import unittest
from unittest.mock import patch

import compare_strategy_families as c


class StrategyFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = [
            [r['result'] for r in c.accounts.lines(gzip.decompress(c.accounts.source(c.V2 / c.accounts.INPUTS['receipts'])))
             if r['method'] == 'eth_getTransactionReceipt'],
            c.accounts.lines(c.pinned(c.PINS[6])),
            c.accounts.lines(c.pinned(c.PINS[1])), c.accounts.lines(c.pinned(c.PINS[4])),
            c.accounts.lines(c.accounts.source(c.V2 / c.accounts.INPUTS['flashes'])),
        ]

    def test_full_partition_reproducible_and_no_admission(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
            first = c.reconcile(); second = c.reconcile()
        self.assertEqual(first, second)
        report = first[1]
        self.assertEqual((report['transactions'], report['liquidation_events'], report['distinct_collateral_debt_pairs']),
                         (127, 139, 53))
        self.assertEqual({r['family']: r['transactions'] for r in report['families']},
                         {'SINGLE_SAME_ASSET': 9, 'SINGLE_CROSS_ASSET': 107, 'MULTI_WITH_CROSS_ASSET': 11})
        self.assertEqual(report['transactions_with_selected_funding_observation'], 65)
        self.assertIsNone(report['success_probability'])
        self.assertFalse(report['census_closed'])
        self.assertEqual(report['economically_admitted_nqc_transactions'], 0)

    def test_missing_or_duplicate_winner_rejected(self):
        for mode in ('missing', 'duplicate'):
            args = copy.deepcopy(self.inputs)
            if mode == 'missing': args[0].pop()
            else: args[0].append(args[0][0])
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'population|duplicate'):
                c.compare(*args)

    def test_event_or_amount_rewrite_rejected(self):
        for mode in ('commitment', 'amount'):
            args = copy.deepcopy(self.inputs)
            if mode == 'commitment': args[1][0]['event_commitments'][0] = '0' * 64
            else: args[1][0]['asset_legs'][0]['debt_repaid_raw'] = '999'
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'commitment|aggregate event'):
                c.compare(*args)

    def test_old_omissions_are_explicit_and_unexpected_ones_rejected(self):
        rows = c.compare(*self.inputs)
        self.assertEqual({r['transaction_hash']: r['recognized_flash_log_indices'] for r in rows
                          if r['legacy_economic_flash_index_discrepancy']}, c.LEGACY_FLASH_OMISSIONS)
        args = copy.deepcopy(self.inputs)
        next(e for e in args[1] if e['recognized_flash_log_indices'])['recognized_flash_log_indices'] = []
        with self.assertRaisesRegex(ValueError, 'unexpected flash'):
            c.compare(*args)

    def test_flash_fee_or_gas_rewrite_rejected(self):
        args = copy.deepcopy(self.inputs); args[4][0]['event_fee_raw'] = '99'
        with self.assertRaisesRegex(ValueError, 'flash binding'):
            c.compare(*args)
        args = copy.deepcopy(self.inputs); args[1][0]['historical_gas']['execution_wei'] = '0'
        with self.assertRaisesRegex(ValueError, 'gas mismatch'):
            c.compare(*args)

    def test_single_family_count_is_not_all_weth(self):
        rows = c.compare(*self.inputs)
        selected = [r for r in rows if r['family'] == 'SINGLE_SAME_ASSET']
        self.assertEqual(len({l['debt_asset'] for r in selected for l in r['liquidation_events']}), 3)
        self.assertTrue(all(r['capture_probability'] is None and not r['nqc_execution_admitted'] for r in rows))


if __name__ == '__main__':
    unittest.main()
