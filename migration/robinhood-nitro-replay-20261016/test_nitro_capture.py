import copy
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error

import capture_replay as capture
import fee_accounting as fees


class HistoricalFeeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = json.loads((fees.PREVIOUS / 'evidence/historical-receipts/rpc_original_receipts.json').read_text())
        cls.receipts = [row['result'] for row in rows[1:]]

    def test_real_archive_has_eight_positive_l1_components(self):
        report = fees.report()
        self.assertEqual(report['receipt_count'], 22)
        self.assertEqual(report['positive_reported_l1_gas_count'], 8)
        self.assertEqual(report['zero_reported_l1_gas_count'], 14)
        self.assertIsNone(report['nqc_total_cost_wei'])

    def test_real_positive_component_is_included_not_added(self):
        r = next(r for r in self.receipts if r['transactionHash'].startswith('0x463862'))
        fee = fees.receipt_fee(r)
        self.assertEqual(fee['total_fee_wei'], 30369410152000)
        self.assertEqual(fee['total_gas'], 835886)
        self.assertEqual(fee['reported_l1_gas_in_l2_units'], 1346)
        self.assertEqual(fee['l1_allocation_at_receipt_price_wei'], 48902872000)
        self.assertEqual(fee['total_fee_wei'], fee['remaining_allocation_wei'] + fee['l1_allocation_at_receipt_price_wei'])

    def test_missing_l1_field_remains_unknown(self):
        r = copy.deepcopy(self.receipts[0])
        del r['gasUsedForL1']
        fee = fees.receipt_fee(r)
        self.assertIsNone(fee['reported_l1_gas_in_l2_units'])
        self.assertTrue(fee['missing_l1_field_is_not_zero'])

    def test_impossible_parent_gas_rejected(self):
        r = copy.deepcopy(self.receipts[0])
        r['gasUsedForL1'] = hex(int(r['gasUsed'], 16) + 1)
        with self.assertRaises(ValueError):
            fees.receipt_fee(r)


class CaptureBoundaryTests(unittest.TestCase):
    def test_components_have_no_double_counting(self):
        raw = '0x' + ''.join(format(n, '064x') for n in [800000, 2000, 20000000, 1])
        result = capture.decode_components(raw)
        self.assertEqual(result['estimated_total_fee_wei'], 16000000000000)
        self.assertEqual(result['estimated_execution_fee_wei'] + result['estimated_l1_fee_wei'], result['estimated_total_fee_wei'])
        self.assertFalse(result['is_actual_fee_receipt'])
        self.assertEqual(result['state_context'], 'PREVIOUS_BLOCK_END_NOT_PRE_TRANSACTION')

    def test_empty_or_malformed_components_do_not_become_zero_cost(self):
        for value in ['0x', '0x' + '00' * 128, '0x' + ''.join(format(n, '064x') for n in [1, 2, 1, 1])]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                capture.decode_components(value)

    def test_components_encoding_matches_cast_verified_vector(self):
        expected = ('0xc94e6eeb' + '0' * 24 + '1234567890123456789012345678901234567890'
                    + '0' * 64 + '0' * 62 + '60' + '0' * 63 + '4' + '12345678' + '0' * 56)
        self.assertEqual(capture.encode_components('0x1234567890123456789012345678901234567890', '0x12345678'), expected)

    def test_no_write_method_or_broadcast(self):
        with tempfile.TemporaryDirectory() as d:
            client = capture.Client('https://rpc.example.invalid/private-token', Path(d))
            for method in ['eth_sendTransaction', 'eth_sendRawTransaction', 'anvil_setStorageAt']:
                with self.assertRaisesRegex(capture.CaptureError, 'NOT_READ_ALLOWED'):
                    client.ask('forbidden', method, [])
            self.assertEqual(client.records, [])

    def test_403_stops_without_retry_or_credential_echo(self):
        class Denied:
            calls = 0
            def open(self, request, timeout):
                self.calls += 1
                raise urllib.error.HTTPError('https://rpc.example.invalid/secret', 403, 'secret', None, None)
        with tempfile.TemporaryDirectory() as d:
            client = capture.Client('https://rpc.example.invalid/secret', Path(d))
            client.opener = Denied()
            with self.assertRaisesRegex(capture.CaptureError, '^HTTP_403_STOP_NO_RETRY$'):
                client.ask('chain-id', 'eth_chainId', [])
            self.assertEqual(client.opener.calls, 1)
            self.assertNotIn('secret', json.dumps(client.records))
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_request_budget_is_enforced_before_transport(self):
        with tempfile.TemporaryDirectory() as d:
            client = capture.Client('https://rpc.example.invalid', Path(d))
            client.records = [{} for _ in range(capture.MAX_REQUESTS)]
            with self.assertRaisesRegex(capture.CaptureError, 'REQUEST_BUDGET'):
                client.ask('chain-id', 'eth_chainId', [])

    def test_redirects_do_not_change_endpoint(self):
        with self.assertRaisesRegex(capture.CaptureError, 'REDIRECT'):
            capture.NoRedirect().redirect_request(None, None, 302, None, None, 'https://another.invalid')


class TraceFormatFixtureTests(unittest.TestCase):
    """Synthetic parser fixtures, never presented as chain replay evidence."""
    def setUp(self):
        raw = json.loads((fees.PREVIOUS / 'evidence/historical-receipts/rpc_original_receipts.json').read_text())
        self.receipt = raw[1]['result']
        self.tx = {'from': self.receipt['from'], 'to': self.receipt['to'], 'input': '0x12345678', 'value': '0x0'}
        self.trace = {**self.tx, 'gasUsed': self.receipt['gasUsed'], 'logs': copy.deepcopy(self.receipt['logs']),
                      'calls': [{'to': address} for address in capture.CORE]}
        self.prestate = {address: {'code': '0x6000'} for address in capture.CORE | {self.tx['to']}}
        self.diff = {'pre': {'fixture': {}}, 'post': {'fixture': {}}}

    def check(self):
        return capture.trace_consistency(self.tx, self.receipt, self.trace, self.prestate, self.diff)

    def test_matching_wire_fixture_does_not_certify_nqc_or_local_replay(self):
        result = self.check()
        self.assertTrue(result['provider_trace_consistent_with_receipt'])
        self.assertFalse(result['independent_local_replay'])
        self.assertFalse(result['nqc_executor_replayed'])
        self.assertFalse(result['log_order_independently_verified'])

    def test_missing_route_call_rejected(self):
        self.trace['calls'].pop()
        with self.assertRaisesRegex(ValueError, 'omits route'):
            self.check()

    def test_missing_code_rejected(self):
        self.prestate[capture.route.NET]['code'] = '0x'
        with self.assertRaisesRegex(ValueError, 'missing route code'):
            self.check()

    def test_changed_trace_calldata_rejected(self):
        self.trace['input'] = '0x00000000'
        with self.assertRaisesRegex(ValueError, 'trace root mismatch'):
            self.check()

    def test_duplicate_trace_log_rejected(self):
        self.trace['logs'].append(copy.deepcopy(self.trace['logs'][0]))
        with self.assertRaisesRegex(ValueError, 'log multiset mismatch'):
            self.check()

    def test_changed_trace_gas_rejected(self):
        self.trace['gasUsed'] = hex(int(self.trace['gasUsed'], 16) + 1)
        with self.assertRaisesRegex(ValueError, 'trace gas differs'):
            self.check()

    def test_reverted_inner_frame_logs_do_not_count(self):
        self.trace['calls'].append({'error': 'execution reverted', 'logs': [copy.deepcopy(self.trace['logs'][0])]})
        self.assertTrue(self.check()['provider_trace_consistent_with_receipt'])

    def test_capture_pipeline_pins_parent_and_preserves_non_nqc_scope(self):
        receipt = self.receipt
        self.tx.update(hash=receipt['transactionHash'], blockHash=receipt['blockHash'],
                       blockNumber=receipt['blockNumber'], transactionIndex=receipt['transactionIndex'],
                       chainId=hex(4663), gas=hex(1200000), input='0x1234567800')
        self.trace['input'] = self.tx['input']
        parent = {'hash': '0x' + 'ab' * 32, 'number': hex(int(receipt['blockNumber'], 16) - 1)}
        header = {'hash': receipt['blockHash'], 'number': receipt['blockNumber'], 'parentHash': parent['hash'],
                  'stateRoot': '0x' + 'cd' * 32, 'timestamp': '0x6aadfab0',
                  'transactions': ['0x' + '00' * 32, receipt['transactionHash']]}
        responses = {'chain-id': hex(4663), 'client-version': 'SYNTHETIC_WIRE_TEST_NOT_NITRO',
                     'transaction': self.tx, 'receipt': receipt, 'block': header, 'parent': parent,
                     'call-trace': self.trace, 'prestate': self.prestate, 'state-diff': self.diff,
                     'prior-block-components': '0x' + ''.join(format(n, '064x') for n in [600000, 2000, 20000000, 1]),
                     'canonical-block-recheck': header}
        class FixtureClient:
            def __init__(self): self.calls = []
            def ask(self, label, method, params):
                self.calls.append((label, method, params))
                return responses[label]
        client = FixtureClient()
        result = capture.capture(client, receipt, '0x12345678')
        self.assertEqual(len(client.calls), 11)
        node_call = next(params for label, method, params in client.calls if label == 'prior-block-components')
        self.assertEqual(node_call[1], {'blockHash': parent['hash'], 'requireCanonical': True})
        self.assertFalse(result['nqc_full_route_replayed'])
        self.assertFalse(result['nqc_cost_measured'])

    def test_wrong_chain_stops_before_historical_queries(self):
        class WrongChain:
            count = 0
            def ask(self, label, method, params):
                self.count += 1
                return '0x1'
        client = WrongChain()
        with self.assertRaisesRegex(ValueError, 'wrong chain'):
            capture.capture(client, self.receipt, '0x12345678')
        self.assertEqual(client.count, 1)


if __name__ == '__main__':
    unittest.main()
