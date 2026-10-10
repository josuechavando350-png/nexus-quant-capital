import copy
import gzip
import json
import unittest
from unittest.mock import patch

from reconcile_weth_accounts import (
    account_flows, reconcile, source, keyed, flash_transfer_check, INPUTS, V2, WETH, WITHDRAWAL,
)


class WethAccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger, cls.report = reconcile()
        cls.rows = {r['retrospective_rank']: r for r in map(json.loads, cls.ledger.splitlines())}
        tx = cls.rows[1]['transaction_hash']
        cls.receipt = next(r['result'] for r in map(json.loads, gzip.decompress(
            source(V2 / INPUTS['receipts'])).splitlines())
            if r['method'] == 'eth_getTransactionReceipt' and r['params'][0] == tx)
        cls.edges = cls.rows[1]['native_edges']
        cls.gas = int(cls.rows[1]['whole_transaction_gas_wei'])

    def test_real_population_replays_byte_identically_without_network(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
            ledger, report = reconcile()
        self.assertEqual(ledger, self.ledger)
        self.assertEqual(report, self.report)
        self.assertEqual((report['transactions'], report['account_rows'], report['native_edges'],
                          report['weth_withdrawal_events']), (9, 97, 26, 10))
        self.assertEqual(report['root_weth_flow_differs_from_selected_leg_gross_ranks'], [2, 3, 4, 5])
        self.assertFalse(report['complete_profit_proven'])
        self.assertFalse(report['census_closed'])

    def test_rank_one_unwrap_is_not_double_counted_as_weth_and_native(self):
        row = self.rows[1]
        root = row['root_account']
        self.assertEqual(root['weth_transfer_log_delta_wei'], '96156124691020450')
        self.assertEqual(root['weth_withdrawal_burn_wei'], '96156124691020450')
        self.assertEqual(root['weth_event_delta_wei'], '0')
        self.assertEqual(root['native_trace_delta_before_gas_wei'], '9975')
        self.assertEqual(row['transaction_sender']['native_trace_delta_before_gas_wei'], '-9975')
        self.assertIsNone(root['complete_profit_wei'])

    def test_gas_is_debited_once_to_sender_not_all_accounts_or_all_legs(self):
        for row in self.rows.values():
            accounts, gas = row['accounts'], int(row['whole_transaction_gas_wei'])
            self.assertEqual(sum(int(a['receipt_gas_debit_wei']) for a in accounts), gas)
            self.assertEqual(sum(int(a['native_trace_delta_after_gas_wei']) for a in accounts), -gas)
            self.assertEqual(sum(int(a['receipt_gas_debit_wei']) > 0 for a in accounts), 1)
            self.assertTrue(all(a['receipt_gas_debit_wei'] == '0' or a['is_transaction_sender'] for a in accounts))
            self.assertFalse(row['ownership_aggregation_performed'])

    def test_mixed_transaction_is_not_attributed_only_to_weth_liquidation(self):
        row = self.rows[2]
        self.assertGreater(int(row['root_weth_transfer_delta_minus_selected_leg_gross_wei']), 0)
        self.assertTrue(any(a['other_token_log_deltas'] for a in row['accounts']))
        self.assertIsNone(row['complete_profit_wei'])
        self.assertFalse(row['other_assets_converted_or_summed'])
        self.assertFalse(row['nqc_executable_value_admitted'])

    def test_duplicate_input_identity_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate input identity'):
            keyed([{'id': 1}, {'id': 1}], 'id')

    def test_duplicate_native_edge_rejected(self):
        # A duplicated non-withdrawal edge must not silently amplify payment.
        edges = copy.deepcopy(self.edges)
        edges.append(next(e for e in edges if not e['weth_withdraw_return']))
        with self.assertRaisesRegex(ValueError, 'duplicate native edge'):
            account_flows(self.receipt, edges, self.gas)

    def test_missing_withdrawal_native_edge_rejected(self):
        with self.assertRaisesRegex(ValueError, 'withdrawal/native parity'):
            account_flows(self.receipt, [e for e in self.edges if not e['weth_withdraw_return']], self.gas)

    def test_altered_withdrawal_value_rejected(self):
        receipt = copy.deepcopy(self.receipt)
        log = next(l for l in receipt['logs'] if l['address'] == WETH and l['topics'][0] == WITHDRAWAL)
        log['data'] = '0x' + format(int(log['data'], 16) + 1, '064x')
        with self.assertRaisesRegex(ValueError, 'withdrawal/native parity'):
            account_flows(receipt, self.edges, self.gas)

    def test_unknown_weth_event_is_not_silently_omitted(self):
        receipt = copy.deepcopy(self.receipt)
        log = next(l for l in receipt['logs'] if l['address'] == WETH)
        log['topics'][0] = '0x' + 'ab' * 32
        with self.assertRaisesRegex(ValueError, 'unsupported WETH event'):
            account_flows(receipt, self.edges, self.gas)

    def test_malformed_withdrawal_abi_rejected(self):
        receipt = copy.deepcopy(self.receipt)
        log = next(l for l in receipt['logs'] if l['address'] == WETH and l['topics'][0] == WITHDRAWAL)
        log['topics'][1] = '0x' + 'ff' * 32
        with self.assertRaisesRegex(ValueError, 'address padding'):
            account_flows(receipt, self.edges, self.gas)

    def test_delegate_or_reverted_values_cannot_be_settled_payments(self):
        for field, value in [('delegatecall', True), ('successful_ancestry', False)]:
            with self.subTest(field=field):
                edges = copy.deepcopy(self.edges)
                edges[0][field] = value
                with self.assertRaisesRegex(ValueError, 'unsettled native edge'):
                    account_flows(self.receipt, edges, self.gas)

    def test_negative_boolean_or_overflow_gas_rejected(self):
        for gas in [-1, True, 2**256]:
            with self.subTest(gas=gas), self.assertRaisesRegex(ValueError, 'gas integer domain'):
                account_flows(self.receipt, self.edges, gas)

    def test_rank_five_flash_principal_and_repayment_match_without_nqc_admission(self):
        row = self.rows[5]
        check, = row['recognized_flash_transfer_checks']
        self.assertEqual(check['principal_wei'], '342642361343309991')
        self.assertEqual(check['principal_wei'], check['repayment_wei'])
        self.assertEqual(check['fee_wei'], '0')
        self.assertFalse(row['unrecognized_financing_routes_and_obligations_resolved'])

    def test_changed_flash_repayment_amount_rejected(self):
        event = self.rows[5]['recognized_flash_events'][0]
        receipt = next(r['result'] for r in map(json.loads, gzip.decompress(
            source(V2 / INPUTS['receipts'])).splitlines())
            if r['method'] == 'eth_getTransactionReceipt' and r['params'][0] == event['transaction_hash'])
        check, = self.rows[5]['recognized_flash_transfer_checks']
        log = next(l for l in receipt['logs'] if int(l['logIndex'], 16) == check['repayment_log_index'])
        log['data'] = '0x' + format(int(log['data'], 16) - 1, '064x')
        with self.assertRaisesRegex(ValueError, 'flash repayment transfer mismatch'):
            flash_transfer_check(event, receipt['logs'])

    def test_changed_pinned_source_bytes_rejected(self):
        path = V2 / INPUTS['references']
        changed = path.read_bytes() + b'\n'
        with patch.object(type(path), 'read_bytes', return_value=changed), \
             self.assertRaisesRegex(ValueError, 'pinned source drift'):
            source(path)


if __name__ == '__main__':
    unittest.main()
