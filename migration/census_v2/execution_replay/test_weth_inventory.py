import copy
import gzip
import json
import unittest
from unittest.mock import patch

import reconcile_weth_accounts as accounts
import reconcile_weth_inventory as inventory


class WethInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger, cls.report = inventory.reconcile()
        cls.rows = {r['retrospective_rank']: r for r in map(json.loads, cls.ledger.splitlines())}
        cls.receipts = {r['result']['transactionHash']: r['result'] for r in accounts.lines(gzip.decompress(
            accounts.source(accounts.V2 / accounts.INPUTS['receipts'])))
            if r['method'] == 'eth_getTransactionReceipt'}

    def compute(self, receipt, rank=1):
        row = self.rows[rank]
        return inventory.ordered_inventory(receipt, row, [a['address'] for a in row['accounts']])

    def test_actual_evidence_repeats_offline_without_promoting_admission(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
            ledger, report = inventory.reconcile()
        self.assertEqual((ledger, report), (self.ledger, self.report))
        self.assertEqual((report['transactions'], report['account_rows'], report['weth_operations'],
                          report['positive_initial_bounds'], report['bounds_exceeding_final_delta']),
                         (9, 97, 50, 21, 15))
        self.assertEqual(report['root_positive_initial_bound_ranks'], [4])
        self.assertFalse(report['census_closed'])
        for row in self.rows.values():
            self.assertFalse(row['zero_initial_bound_proves_nqc_financing'])
            self.assertFalse(row['nqc_executable_value_admitted'])
            self.assertFalse(row['account_ownership_aggregated'])
            self.assertIsNone(row['complete_profit_wei'])

    def test_actual_floors_are_sufficient_and_every_positive_floor_is_tight(self):
        for row in self.rows.values():
            initial = {a['address']: int(a['minimum_initial_weth_wei']) for a in row['accounts']}
            final = inventory.replay(row['weth_operations'], initial)
            self.assertEqual(final, {a['address']: initial[a['address']] + int(a['final_observed_weth_delta_wei'])
                                     for a in row['accounts']})
            for owner, floor in initial.items():
                if floor:
                    with self.subTest(rank=row['retrospective_rank'], owner=owner), \
                         self.assertRaisesRegex(ValueError, 'insufficient initial inventory'):
                        inventory.replay(row['weth_operations'], {**initial, owner: floor - 1})

    def test_actual_rank_four_root_needs_inventory_before_withdrawal(self):
        root = self.rows[4]['root_account']
        self.assertEqual(root['minimum_initial_weth_wei'], '3379677466555340')
        self.assertEqual(root['binding_debit']['log_index'], 39)
        self.assertEqual(root['final_observed_weth_delta_wei'], '-3379677466555340')

    def test_actual_repaid_lender_zero_end_delta_still_needs_initial_inventory(self):
        lender = next(a for a in self.rows[5]['accounts']
                      if a['address'] == '0xba12222222228d8ba445958a75a0704d566bf2c8')
        self.assertEqual(lender['final_observed_weth_delta_wei'], '0')
        self.assertEqual(lender['minimum_initial_weth_wei'], '342642361343309991')
        self.assertTrue(lender['ordering_adds_inventory_requirement'])
        self.assertEqual(lender['binding_debit']['log_index'], 13)
        self.assertFalse(lender['is_root_execution_account'])

    def test_self_transfer_checks_debit_before_credit_synthetic_semantic_case(self):
        receipt = copy.deepcopy(self.receipts[self.rows[1]['transaction_hash']])
        log = next(l for l in receipt['logs'] if l['address'] == accounts.WETH
                   and l['topics'][0] == accounts.TRANSFER)
        log['topics'][2] = log['topics'][1]
        receipt['logs'] = [log]
        rows, _ = self.compute(receipt)
        owner = accounts.address_word(log['topics'][1][2:])
        row = next(r for r in rows if r['address'] == owner)
        self.assertEqual(row['final_observed_weth_delta_wei'], '0')
        self.assertEqual(int(row['minimum_initial_weth_wei']), int(log['data'], 16))

    def test_removed_duplicate_and_reordered_logs_are_rejected(self):
        original = self.receipts[self.rows[1]['transaction_hash']]
        for mode in ('removed', 'duplicate', 'reordered'):
            receipt = copy.deepcopy(original)
            if mode == 'removed':
                receipt['logs'][0]['removed'] = True
            elif mode == 'duplicate':
                receipt['logs'].insert(1, receipt['logs'][0])
            else:
                receipt['logs'].reverse()
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.compute(receipt)

    def test_unsupported_weth_event_and_malformed_amount_are_rejected(self):
        for mode in ('event', 'data'):
            receipt = copy.deepcopy(self.receipts[self.rows[1]['transaction_hash']])
            log = next(l for l in receipt['logs'] if l['address'] == accounts.WETH)
            if mode == 'event':
                log['topics'][0] = '0x' + 'ab' * 32
            else:
                log['data'] = '0x01'
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'WETH inventory'):
                self.compute(receipt)

    def test_changed_pinned_account_evidence_is_rejected(self):
        name = inventory.PINS[1]
        path = inventory.V2 / name
        changed = path.read_bytes() + b'\n'
        with patch.object(type(path), 'read_bytes', return_value=changed), \
             self.assertRaisesRegex(ValueError, 'inventory source drift'):
            inventory.pinned(name)


if __name__ == '__main__':
    unittest.main()
