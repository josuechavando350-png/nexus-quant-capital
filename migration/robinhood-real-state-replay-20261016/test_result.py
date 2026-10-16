import copy
import json
import unittest

from audit_result import (HERE, EP, USEROP, audit, native_fee, operation,
                          ordered_logs, validate_overrides)
from nitro_read import validate


class RealEvidenceTests(unittest.TestCase):
    def test_full_archived_reconciliation(self):
        report = audit(HERE / 'evidence')
        self.assertEqual(report['surplus_before_gas_usdg_raw'], 32060665)
        self.assertEqual(report['nqc_success']['network_fee_wei'], 57601054408000)
        self.assertEqual(report['nqc_success']['sponsor_charge_wei'], 79616762214000)
        self.assertEqual(report['local_protocol_read_slots_confirmed_by_nitro'], 112)
        self.assertFalse(report['realized_nqc_revenue'])
        self.assertFalse(report['production_bundler_admission_proven'])

    def test_all_recorded_remote_requests_are_read_only_and_bounded(self):
        count = 0
        for phase in (HERE / 'evidence').glob('nitro-phase*'):
            for record in json.loads((phase / 'requests.json').read_text()):
                validate(dict(record['request'], label=record['label']))
                count += 1
        self.assertEqual(count, 18)


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.trace = json.loads((HERE / 'evidence/nitro-phase5/01-nqc-plain-eoa-success.json').read_text())['result']
        self.data = json.loads((HERE / 'evidence/final-simulation-input.json').read_text())

    def test_refund_mismatch_is_rejected(self):
        for item in self.trace['afterEVMTransfers']:
            if item['purpose'] == 'gasRefund':
                item['value'] = hex(int(item['value'], 16) + 1)
        with self.assertRaises(ValueError):
            native_fee(self.trace)

    def test_negative_native_fee_is_rejected(self):
        self.trace['beforeEVMTransfers'] = []
        with self.assertRaises(ValueError):
            native_fee(self.trace)

    def test_bundle_success_does_not_imply_operation_success(self):
        def corrupt(frame):
            for log in frame.get('logs', []):
                if log['topics'][0] == USEROP:
                    log['data'] = log['data'][:66] + '0' * 64 + log['data'][130:]
            for child in frame.get('calls', []):
                corrupt(child)
        corrupt(self.trace)
        with self.assertRaises(ValueError):
            operation(self.trace, True)

    def test_index_must_match_nested_position(self):
        self.trace['logs'][0]['index'] = '0xffff'
        with self.assertRaises(ValueError):
            ordered_logs(self.trace)

    def test_bad_log_position_is_rejected(self):
        self.trace['logs'][0]['position'] = '0xffff'
        with self.assertRaises(ValueError):
            ordered_logs(self.trace)

    def test_reverted_subtree_logs_are_discarded(self):
        self.trace['error'] = 'execution reverted'
        self.assertEqual(ordered_logs(self.trace), [])

    def test_unindexed_trace_preserves_interleaving(self):
        expected = [log['data'] for log in ordered_logs(self.trace)]
        def strip(frame):
            for log in frame.get('logs', []):
                log.pop('index')
            for child in frame.get('calls', []):
                strip(child)
        strip(self.trace)
        self.assertEqual([log['data'] for log in ordered_logs(self.trace)], expected)

    def test_oracle_override_is_rejected(self):
        self.data['state_overrides']['0xcde9599059f8ae6d6b9f33a0af7877827ec75f16'] = {'code': '0x00'}
        with self.assertRaises(ValueError):
            validate_overrides(self.data)

    def test_unknown_bundler_delegation_is_rejected(self):
        self.data['state_overrides'][self.data['transaction']['from']]['code'] = '0xef0100'
        with self.assertRaises(ValueError):
            validate_overrides(self.data)

    def test_sponsor_funding_must_be_explicit(self):
        del self.data['state_overrides'][EP]['balance']
        with self.assertRaises((ValueError, KeyError)):
            validate_overrides(self.data)


class RpcBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.item = {'label': 'test', 'method': 'debug_traceCall', 'params': [
            {'to': EP, 'data': '0x'}, '0x3fa6f62',
            {'tracer': 'callTracer', 'timeout': '10s', 'reexec': 0, 'txIndex': '0x1'}]}

    def test_send_method_refused(self):
        self.item['method'] = 'eth_sendRawTransaction'
        with self.assertRaises(ValueError):
            validate(self.item)

    def test_latest_block_refused(self):
        self.item['params'][1] = 'latest'
        with self.assertRaises(ValueError):
            validate(self.item)

    def test_unbounded_reexecution_refused(self):
        self.item['params'][2]['reexec'] = 100000
        with self.assertRaises(ValueError):
            validate(self.item)

    def test_protocol_override_refused(self):
        self.item['params'][2]['stateOverrides'] = {'0x9d53d5e3bd5e8d4cbfa6db1ca238aea02e651010': {'balance': '0x0'}}
        with self.assertRaises(ValueError):
            validate(self.item)


if __name__ == '__main__':
    unittest.main()
