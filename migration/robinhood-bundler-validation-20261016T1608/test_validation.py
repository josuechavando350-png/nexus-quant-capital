import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import validation as v
import run_local as runner


def abi_result(case):
    window = case['window']
    packed = (window['valid_until'] << 160) | (window['valid_after'] << 208)
    words = [32, 320, 0, 0, 0, 0, case['stake_fixture_wei'], case['unstake_delay_fixture_seconds'],
             0, 0, 0, 129999, window['budget_wei'], 0, packed, 160, 0]
    return '0x'+''.join(n.to_bytes(32, 'big').hex() for n in words)


class Tests(unittest.TestCase):
    def test_keccak_and_deposit_mapping(self):
        self.assertEqual(v.keccak256(b'').hex(), 'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470')
        self.assertEqual(v.DEPOSIT, '0xefc40b0a359e87f75c5b351a9b756a72a62ce917f34ed43fce329a33d269eb2d')

    def test_compiled_deposit_layout(self):
        layout = v.read(v.HERE/'build/simulation-artifact.json')['storageLayout']
        root = next(x for x in layout['storage'] if x['label'] == 'deposits')
        self.assertEqual(root['slot'], '0')
        fields = layout['types'][layout['types'][root['type']]['value']]['members']
        self.assertEqual([(x['label'], x['slot'], x['offset']) for x in fields],
                         [('deposit', '0', 0), ('staked', '1', 0), ('stake', '1', 1),
                          ('unstakeDelaySec', '1', 15), ('withdrawTime', '1', 19)])

    def test_fixture_preserves_original_account_and_signature(self):
        for name in v.CASES:
            case = v.fixture(name)
            source = v.read(v.ROOT/case['source'])
            account = source['addresses']['account']
            self.assertEqual(case['stateOverrides'][account]['code'], source['state_overrides'][account]['code'])
            self.assertTrue(source['transaction']['data'].endswith(case['transaction']['data'][74:]))
            self.assertEqual(case['transaction']['data'][:10], '0xc3bce009')

    def test_stake_only_changes_fixture_state(self):
        a = v.fixture(v.CASES[0]); b = v.fixture(v.CASES[1])
        self.assertEqual(a['transaction'], b['transaction'])
        self.assertEqual(a['stateOverrides'][v.PM], b['stateOverrides'][v.PM])
        x = copy.deepcopy(b['stateOverrides']); x[v.EP]['state'][v.STAKE] = a['stateOverrides'][v.EP]['state'][v.STAKE]
        x[v.EP]['balance'] = a['stateOverrides'][v.EP]['balance']
        self.assertEqual(a['stateOverrides'], x)

    def test_negative_controls_are_explicit(self):
        self.assertEqual(int(v.fixture('31s_zero_deposit')['stateOverrides'][v.EP]['state'][v.DEPOSIT], 16), 0)
        self.assertEqual(int(v.fixture('31s_zero_budget')['stateOverrides'][v.PM]['state'][v.SLOT1], 16), 0)

    def test_decoder_three_cases(self):
        for name in v.CASES[:3]:
            case = v.fixture(name); decoded = v.decode_result(abi_result(case))
            self.assertEqual(decoded['prefund_wei'], 249541240000000)
            self.assertEqual(decoded['paymaster_stake_wei'], case['stake_fixture_wei'])
            self.assertEqual(decoded['valid_until']-decoded['valid_after'], 1 if name.startswith('1s_') else 31)

    def test_decoder_rejects_truncation_and_extra_data(self):
        raw = abi_result(v.fixture(v.CASES[0]))
        for bad in (raw[:-2], raw+'00', '0x', '0x'+bytes(32).hex()):
            with self.assertRaises(ValueError): v.decode_result(bad)

    def test_zero_context_does_not_imply_admission(self):
        case = v.fixture(v.CASES[0])
        trace = {'calls': [{'type': 'RETURN', 'data': abi_result(case)}], 'callsFromEntryPoint': [
            {'topLevelTargetAddress': v.PM, 'access': {v.PM: {'reads': {v.SLOT1: v.word(249541240000000)},
             'writes': {v.SLOT1: 1}}}, 'opcodes': {'SLOAD': 1, 'SSTORE': 1}}]}
        result = v.summarize(case, trace)
        self.assertFalse(result['full_bundler_admission_proven'])
        self.assertFalse(result['funding_available_proven'])

    def test_missing_storage_evidence_rejected(self):
        case = v.fixture(v.CASES[0])
        trace = {'calls': [{'type': 'RETURN', 'data': abi_result(case)}], 'callsFromEntryPoint': []}
        with self.assertRaises(AssertionError): v.summarize(case, trace)

    def test_negative_control_needs_revert(self):
        case = v.fixture('31s_zero_deposit')
        with self.assertRaises(ValueError):
            v.summarize(case, {'calls': [{'type': 'RETURN', 'data': '0x'+b'AA31'.hex()}]})

    def test_no_signing_sending_or_remote_endpoint(self):
        self.assertEqual(runner.URL, 'http://127.0.0.1:18569')
        with tempfile.TemporaryDirectory() as d:
            journal = runner.LocalJournal(Path(d), runner.time.monotonic())
            for method in ('eth_sendTransaction', 'eth_sendRawTransaction', 'eth_sign', 'personal_sign'):
                with self.assertRaises(ValueError): journal.rpc(method, [])
            self.assertEqual(journal.rows, [])

    def test_no_redirects(self):
        self.assertIsNone(runner.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def test_no_requests_after_failure_or_budget(self):
        with tempfile.TemporaryDirectory() as d:
            journal = runner.LocalJournal(Path(d), runner.time.monotonic())
            journal.failed = True
            with self.assertRaises(ValueError): journal.rpc('eth_chainId', [])
            journal.failed = False; journal.rows = [{}]*512
            with self.assertRaises(ValueError): journal.rpc('eth_chainId', [])

    def test_deadline_includes_wait(self):
        with tempfile.TemporaryDirectory() as d:
            journal = runner.LocalJournal(Path(d), 0)
            journal.last = 879.9
            with patch.object(runner.time, 'monotonic', return_value=880):
                with self.assertRaisesRegex(ValueError, 'deadline'): journal.rpc('eth_chainId', [])
            self.assertTrue(journal.failed)


if __name__ == '__main__':
    unittest.main()
