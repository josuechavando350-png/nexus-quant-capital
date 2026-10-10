import copy
import gzip
import json
import unittest
from unittest.mock import patch
import zipfile

import reconcile_trace_loans as loans


class TraceLoanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger, cls.report = loans.reconcile()
        cls.rows = list(map(json.loads, cls.ledger.splitlines()))
        cls.row = next(row for row in cls.rows if row['trace_loans'])
        cls.receipt = next(r['result'] for r in loans.source.lines(gzip.decompress(
            loans.source.source(loans.V2 / loans.source.INPUTS['receipts'])))
            if r['method'] == 'eth_getTransactionReceipt' and r['result']['transactionHash'] == cls.row['transaction_hash'])
        with zipfile.ZipFile(loans.V2 / loans.source.INPUTS['traces']) as archive:
            _, cls.nodes = loans.parse_trace(archive.read(cls.row['trace_member']))

    def test_full_127_winner_population_repeats_offline_without_admission(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
            ledger, report = loans.reconcile()
        self.assertEqual((ledger, report), (self.ledger, self.report))
        self.assertEqual((report['transactions_scanned'], report['transactions_with_selected_loan_observations'],
                          report['selected_loan_observations'], report['matched_receipt_transfer_legs']),
                         (127, 46, 49, 98))
        self.assertEqual(len(report['loans_by_asset']), 10)
        self.assertFalse(report['census_closed'])
        for row in self.rows:
            self.assertFalse(row['nqc_funding_admitted'])
            self.assertFalse(row['other_funding_routes_resolved'])
            self.assertIsNone(row['complete_profit_wei'])
            used = []
            for loan in row['trace_loans']:
                self.assertLess(loan['principal_log_index'], loan['repayment_log_index'])
                used.extend([loan['principal_log_index'], loan['repayment_log_index']])
                self.assertIsNone(loan['complete_financing_fee_raw'])
                self.assertFalse(loan['deployed_code_and_abi_proven'])
            self.assertEqual(len(used), len(set(used)))

    def test_missing_or_altered_repayment_log_rejected(self):
        index = self.row['trace_loans'][0]['repayment_log_index']
        for mode in ('missing', 'amount', 'recipient'):
            receipt = copy.deepcopy(self.receipt)
            log = next(l for l in receipt['logs'] if int(l['logIndex'], 16) == index)
            if mode == 'missing':
                receipt['logs'].remove(log)
            elif mode == 'amount':
                log['data'] = '0x' + format(int(log['data'], 16) - 1, '064x')
            else:
                log['topics'][2] = '0x' + '00' * 12 + 'ab' * 20
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'receipt population or order'):
                loans.match_loans(self.nodes, receipt, self.row)

    def test_duplicate_or_reordered_receipt_logs_rejected(self):
        for mode in ('duplicate', 'reordered'):
            receipt = copy.deepcopy(self.receipt)
            if mode == 'duplicate':
                receipt['logs'].insert(1, receipt['logs'][0])
            else:
                receipt['logs'].reverse()
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'duplicate or out-of-order log'):
                loans.match_loans(self.nodes, receipt, self.row)

    def test_reverted_loan_or_callback_rejected(self):
        loan = self.row['trace_loans'][0]
        for line in (loan['trace_line'], loan['callback_call_line']):
            nodes = copy.deepcopy(self.nodes)
            next(n for n in nodes if n['line'] == line)['successful_ancestry'] = False
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, 'unsettled|settlement'):
                loans.match_loans(nodes, self.receipt, self.row)

    def test_changed_callback_payload_rejected(self):
        nodes = copy.deepcopy(self.nodes)
        node = next(n for n in nodes if n['line'] == self.row['trace_loans'][0]['callback_call_line'])
        node['body'] = node['body'][:-1] + '00)'
        with self.assertRaisesRegex(ValueError, 'callback mismatch'):
            loans.match_loans(nodes, self.receipt, self.row)

    def test_transfer_call_disagreement_or_order_rejected(self):
        first = self.row['trace_loans'][0]
        for mode in ('amount', 'order', 'delegatecall'):
            nodes = copy.deepcopy(self.nodes)
            sent = next(n for n in nodes if n['line'] == first['principal_call_line'])
            if mode == 'amount':
                sent['body'] = sent['body'].replace(first['principal_raw'], str(int(first['principal_raw']) + 1), 1)
            elif mode == 'order':
                returned = next(n for n in nodes if n['line'] == first['repayment_call_line'])
                sent['body'], returned['body'] = returned['body'], sent['body']
            else:
                sent['body'] += ' [delegatecall]'
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'principal call mismatch|call shape or order'):
                loans.match_loans(nodes, self.receipt, self.row)

    def test_delegate_parent_keeps_calling_account_synthetic_context_case(self):
        owner, implementation, lender = ('0x' + x * 40 for x in ('1', '2', '3'))
        nodes = [{'parent': None, 'body': owner + '::f()'},
                 {'parent': 0, 'body': implementation + '::f() [delegatecall]'},
                 {'parent': 1, 'body': lender + '::f()'}]
        self.assertEqual(loans.contexts(nodes, '0x' + '4' * 40)[2], owner)

    def test_changed_source_consumer_rejected(self):
        path = loans.Path(loans.source.__file__)
        changed = path.read_bytes() + b'\n'
        with patch.object(type(path), 'read_bytes', return_value=changed), \
             self.assertRaisesRegex(ValueError, 'source consumer drift'):
            loans.pin_consumer()


if __name__ == '__main__':
    unittest.main()
