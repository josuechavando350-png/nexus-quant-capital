"""Original collateral delivery selection plus observed USDC payment, with synthetic state."""
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import build_aave_delivery_execution as builder

identity = builder.identity
payment = builder.payment
EVIDENCE = builder.DIRECTORY
COLLATERAL = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
ATOKEN = '0x4d5f47fa6a74757f35c14fd3a6ef8e3c9bc514e8'


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = identity.read_json(EVIDENCE / 'compiler/input.json.gz')
        cls.raw = gzip.decompress((EVIDENCE / 'compiler/output.json.gz').read_bytes())
        cls.fixture = identity.read_json(identity.MODULE / 'fixtures/aave_delivery_execution.json')
        cls.examples = {m: {n: identity.read_json(EVIDENCE / 'synthetic' / m / (n + '.json'))
            for n in ['input', 'output']} for m in ['atoken', 'underlying']}

    def run_cli(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.json'; p.write_text(json.dumps(data))
            return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'], 'simulate', '--input', str(p)], capture_output=True, text=True)

    def test_compiler_sources_and_original_settings_remain_unchanged(self):
        original = identity.read_json(identity.EVIDENCE / 'source.json.gz')
        identity.verify_provenance(original)
        self.assertEqual({k: v for k, v in self.value['sources'].items() if k != builder.NAME}, original['sources'])
        settings = copy.deepcopy(self.value['settings']); settings.pop('outputSelection')
        expected = identity.compilation_input(original)['settings']; expected.pop('outputSelection')
        self.assertEqual(settings, expected)
        self.assertEqual(self.fixture['compiler_sha256'], identity.COMPILER_SHA)
        self.assertEqual(self.fixture['compiler_output_sha256'], identity.sha(self.raw))

    def test_original_delivery_if_else_and_payment_event_are_byte_exact(self):
        value, harness, segments = builder.harness_input()
        self.assertEqual(value, self.value); self.assertEqual(harness, (identity.MODULE / builder.NAME).read_text())
        original = value['sources'][payment.underlying.transfer.SOURCE_PATH]['content']
        a = original.index('    if (params.receiveAToken) {')
        branch = original[a:original.index('    // Transfer fee to treasury', a)]
        self.assertIn(branch, harness)
        self.assertEqual(identity.sha(branch.encode()), segments['unchanged_collateral_delivery_branch'])
        a = original.index('    // Transfers the debt asset being repaid to the aToken')
        self.assertIn(original[a:original.index('\n  }', a)], harness)
        self.assertIn('params.receiveAToken = input.receiveAToken;', harness)
        self.assertIn('LiquidationLogic._burnCollateralATokens(reserve, params, vars);', harness)
        self.assertNotIn('UnderlyingView', harness)
        self.assertEqual(segments, self.fixture['extracted_segments'])

    def test_rebuild_is_offline_and_prior_observed_dependencies_and_gaps_are_preserved(self):
        with patch.object(payment.capture, 'Rpc', side_effect=AssertionError('no new network capture')):
            self.assertEqual(builder.fixture(self.value, self.raw), self.fixture)
        prior = identity.read_json(identity.MODULE / 'fixtures/aave_payment_execution.json')
        for name, contract in prior['contracts'].items():
            if name != payment.CONTRACT: self.assertEqual(contract, self.fixture['contracts'][name])
        self.assertEqual(self.fixture['previous_payment_fixture_sha256'],
            identity.sha((identity.MODULE / 'fixtures/aave_payment_execution.json').read_bytes()))
        for k in ['initial_health_validation_executed', 'historical_state_authenticated', 'complete_liquidation_verified',
            'same_asset_cache_branch_executed', 'usdc_full_source_runtime_match', 'weth_full_source_runtime_match',
            'proxy_code_runtime_match_verified', 'activation_allowed', 'receive_atoken_only', 'receive_underlying_only']:
            self.assertFalse(self.fixture[k])
        self.assertTrue(self.fixture['both_collateral_delivery_modes_executed'])
        self.assertTrue(self.fixture['collateral_delivery_mode_supplied'])

    def test_changed_harness_or_settings_cannot_reuse_retained_compilation(self):
        for kind in ['source', 'optimizer', 'missing']:
            value = copy.deepcopy(self.value)
            if kind == 'source': value['sources'][builder.NAME]['content'] = value['sources'][builder.NAME]['content'].replace('input.receiveAToken;', 'false;')
            elif kind == 'optimizer': value['settings']['optimizer']['runs'] += 1
            else: value['sources'].pop(next(k for k in value['sources'] if k != builder.NAME))
            with self.assertRaises(ValueError): builder.fixture(value, self.raw)

    def test_both_closed_cli_examples_replay_all_25_words_logs_and_state(self):
        for mode, example in self.examples.items():
            result = self.run_cli(example['input'])
            self.assertEqual(result.returncode, 0, result.stderr)
            out = json.loads(result.stdout); self.assertEqual(out, example['output'])
            words = [int(out['output'][i:i+64], 16) for i in range(2, len(out['output']), 64)]
            self.assertEqual(len(words), 25); self.assertEqual(words[-3:], [60, 240, 60])
            self.assertEqual(words[10:14], [66, 47, 14, 1000] if mode == 'atoken' else [66, 20, 14, 973])
            self.assertEqual(words[19], 1000 if mode == 'atoken' else 960)
            self.assertEqual(int(out['logs'][-1]['data'][-64:], 16), mode == 'atoken')
            self.assertEqual(example['input']['snapshot']['kind'], 'synthetic_fixture')
            self.assertFalse(out['canonical_state_authenticated'])

    def test_atoken_route_needs_no_weth_account_and_preserves_supply(self):
        example = self.examples['atoken']
        self.assertTrue(all(a['address'] != COLLATERAL for a in example['input']['snapshot']['accounts']))
        token = next(a for a in example['input']['snapshot']['accounts'] if a['address'] == ATOKEN)
        self.assertNotIn('61', token['storage'])
        self.assertTrue(all(l['address'] != COLLATERAL for l in example['output']['logs']))
        delta = next(a for a in example['output']['account_deltas'] if a['address'] == ATOKEN)
        self.assertNotIn('54', delta['storage'])

    def test_mode_switch_uses_same_compiled_code_and_changes_actual_branch(self):
        data = copy.deepcopy(self.examples['underlying']['input'])
        data['call']['calldata'] = data['call']['calldata'][:-64] + f'{1:064x}'
        result = self.run_cli(data); self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout); expected = self.examples['atoken']['output']
        for k in ['output', 'logs']: self.assertEqual(out[k], expected[k])
        changes = lambda o: {a['address']: a['storage'] for a in o['account_deltas'] if a['storage']}
        self.assertEqual(changes(out), changes(expected))
        # Switching the minimal aToken witness set to WETH must fail closed.
        data = copy.deepcopy(self.examples['atoken']['input'])
        data['call']['calldata'] = data['call']['calldata'][:-64] + f'{0:064x}'
        result = self.run_cli(data); self.assertNotEqual(result.returncode, 0); self.assertEqual(result.stdout, '')

    def test_late_payment_pause_reverts_every_write_and_event_in_both_modes(self):
        for example in self.examples.values():
            data = copy.deepcopy(example['input'])
            token = next(a for a in data['snapshot']['accounts'] if a['address'] == payment.capture.USDC)
            token['storage']['1'] = str(1 << 160)
            result = self.run_cli(data); self.assertEqual(result.returncode, 0, result.stderr)
            out = json.loads(result.stdout); self.assertEqual(out['status'], 'revert')
            self.assertIn(b'Pausable: paused'.hex(), out['output']); self.assertEqual(out['logs'], [])
            self.assertTrue(all(not a['storage'] for a in out['account_deltas']))

    def test_invalid_abi_mode_is_rejected_without_any_contract_effect(self):
        original = self.examples['atoken']['input']
        for suffix in ['', f'{2:064x}', f'{2**256-1:064x}']:
            data = copy.deepcopy(original); data['call']['calldata'] = data['call']['calldata'][:-64] + suffix
            result = self.run_cli(data); self.assertEqual(result.returncode, 0, result.stderr)
            out = json.loads(result.stdout); self.assertEqual(out['status'], 'revert'); self.assertEqual(out['output'], '0x')
            self.assertEqual(out['logs'], []); self.assertTrue(all(not a['storage'] for a in out['account_deltas']))


if __name__ == '__main__':
    unittest.main()
