"""Observed USDC identity and original payment composition; synthetic state only."""
import copy
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import build_aave_payment_execution as builder

identity = builder.identity
capture = builder.capture
EVIDENCE = builder.DIRECTORY
POOL = '0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2'
CALLER = '0x1111111111111111111111111111111111111111'


class PaymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history = capture.replay()
        cls.sources = {n: builder.usdc_input(n)[0] for n in builder.PROFILES}
        cls.raws = {n: gzip.decompress((EVIDENCE / 'compiler' / (n + '-output.json.gz')).read_bytes()) for n in builder.PROFILES}
        cls.outputs = {n: json.loads(r) for n, r in cls.raws.items()}
        cls.value = identity.read_json(EVIDENCE / 'compiler/harness-input.json.gz')
        cls.raw = gzip.decompress((EVIDENCE / 'compiler/harness-output.json.gz').read_bytes())
        cls.fixture = identity.read_json(identity.MODULE / 'fixtures/aave_payment_execution.json')

    def test_original_sources_settings_and_compilers_are_bound_without_source_repair(self):
        for name in builder.PROFILES:
            source, value = builder.usdc_input(name)
            self.assertEqual(value, identity.read_json(EVIDENCE / 'compiler' / (name + '-input.json.gz')))
            self.assertEqual(value['sources'], source['sources'])
            settings = copy.deepcopy(value['settings']); settings.pop('outputSelection')
            self.assertEqual(settings, source['compilation']['compilerSettings'])
            self.assertEqual(self.fixture['usdc_compiler_output_sha256'][name], identity.sha(self.raws[name]))
        original = identity.read_json(identity.EVIDENCE / 'source.json.gz')
        identity.verify_provenance(original)
        self.assertEqual({k: v for k, v in self.value['sources'].items() if k != builder.NAME}, original['sources'])
        settings = copy.deepcopy(self.value['settings']); settings.pop('outputSelection')
        expected = identity.compilation_input(original)['settings']; expected.pop('outputSelection')
        self.assertEqual(settings, expected)

    def test_full_observed_runtimes_are_preserved_and_both_metadata_gaps_remain_false(self):
        for name, (_, _, _, size, footer) in builder.PROFILES.items():
            result = builder.audit_usdc(name, self.sources[name], self.outputs[name], self.history)
            self.assertEqual(result, self.fixture['contracts'][name])
            self.assertFalse(result['full_runtime_recompiled']); self.assertFalse(result['metadata_hash_equal'])
            self.assertTrue(result['executable_prefix_equal']); self.assertFalse(result['historical_state_authenticated'])
            observed = bytes.fromhex(result['runtime_code'][2:])
            file, contract = self.sources[name]['compilation']['fullyQualifiedName'].rsplit(':', 1)
            compiled = bytes.fromhex(self.outputs[name]['contracts'][file][contract]['evm']['deployedBytecode']['object'])
            self.assertEqual(len(observed), size); self.assertEqual(compiled[:-footer], observed[:-footer])
            self.assertEqual(sum(a != b for a, b in zip(compiled, observed)), 32)
        self.assertEqual([h['block']['number'] for h in self.history], list(identity.BLOCKS))
        self.assertEqual(sum(len(h['records']) for h in self.history), 84)

    def test_compiler_body_footer_and_executed_layout_tampering_are_rejected(self):
        for name in builder.PROFILES:
            file, contract = self.sources[name]['compilation']['fullyQualifiedName'].rsplit(':', 1)
            for kind in ['body', 'footer', 'layout']:
                output = copy.deepcopy(self.outputs[name]); c = output['contracts'][file][contract]
                if kind == 'layout':
                    if name == 'usdc-implementation':
                        next(s for s in c['storageLayout']['storage'] if s['label'] == 'allowed')['slot'] = '9'
                    else:
                        def mutate(node):
                            if isinstance(node, dict):
                                if node.get('nodeType') == 'VariableDeclaration' and node.get('name') == 'ADMIN_SLOT': node['constant'] = False
                                for v in node.values(): mutate(v)
                            elif isinstance(node, list):
                                for v in node: mutate(v)
                        mutate(output['sources'][file]['ast'])
                else:
                    chars = list(c['evm']['deployedBytecode']['object']); i = 0 if kind == 'body' else len(chars) - 30
                    chars[i] = '1' if chars[i] != '1' else '2'; c['evm']['deployedBytecode']['object'] = ''.join(chars)
                with self.assertRaises(ValueError): builder.audit_usdc(name, self.sources[name], output, self.history)

    def test_history_routing_runtime_and_underlying_identity_changes_are_rejected(self):
        name = 'usdc-implementation'
        for kind in ['runtime', 'implementation', 'underlying', 'block', 'provider']:
            history = copy.deepcopy(self.history); h = history[0]
            if kind == 'runtime': h['runtimes'][capture.IMPLEMENTATION]['runtime_code'] = '0x00'
            elif kind == 'implementation': h['implementation_slot_word'] = '0x' + '00' * 32
            elif kind == 'underlying': h['underlying_slot_word'] = '0x' + '00' * 32
            elif kind == 'block': h['block']['number'] += 1
            else: next(r for r in h['records'] if r['request']['method'] == 'eth_getCode' and r['request']['params'][0] == capture.IMPLEMENTATION)['response']['result'] = '0x00'
            with self.assertRaises(ValueError): builder.audit_usdc(name, self.sources[name], self.outputs[name], history)

    def replay_mutation(self, kind):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / 'public'; shutil.copytree(EVIDENCE / 'public', d)
            p = d / 'usdc-000.json'; value = identity.read_json(p); rows = value['records']
            if kind == 'chain': rows[0]['response']['result'] = '0x2'
            elif kind == 'id': rows[0]['response']['id'] += 1
            elif kind == 'finality': rows[1]['response']['result']['number'] = '0x1'
            elif kind == 'header': rows[-1]['response']['result']['hash'] = '0x' + '11' * 32
            elif kind == 'missing': rows.pop()
            elif kind == 'provider': rows[0]['provider_id'] = 'unknown'
            elif kind == 'code': next(r for r in rows if r['request']['method'] == 'eth_getCode')['response']['result'] = '0x00'
            else: next(r for r in rows if r['request']['method'] == 'eth_getCode')['request']['params'][-1]['requireCanonical'] = False
            p.write_bytes(identity.encoded(value)); mp = d / 'manifest.json'; m = identity.read_json(mp)
            m['observations'][0]['sha256'] = identity.sha(p.read_bytes()); mp.write_bytes(identity.encoded(m))
            with self.assertRaises((ValueError, StopIteration)): capture.replay(d)

    def test_rehashed_capture_chain_pin_identity_and_provider_changes_are_rejected(self):
        for kind in ['chain', 'pin', 'id', 'provider']: self.replay_mutation(kind)

    def test_rehashed_capture_incomplete_finality_header_and_runtime_changes_are_rejected(self):
        for kind in ['missing', 'finality', 'header', 'code']: self.replay_mutation(kind)

    def test_fixture_rebuild_preserves_original_payment_event_and_explicit_unexecuted_gates(self):
        self.assertEqual(builder.fixture(self.value, self.raw, self.raws), self.fixture)
        value, harness, segments = builder.harness_input()
        self.assertEqual(value, self.value); self.assertEqual(harness, (identity.MODULE / builder.NAME).read_text())
        self.assertEqual(segments, self.fixture['extracted_segments'])
        original = value['sources'][builder.underlying.transfer.SOURCE_PATH]['content']
        a = original.index('    // Transfers the debt asset being repaid to the aToken')
        self.assertIn(original[a:original.index('\n  }', a)], harness)
        for k in ['debt_payment_executed', 'liquidation_event_executed', 'underlying_transfer_executed', 'receive_underlying_only']:
            self.assertTrue(self.fixture[k])
        for k in ['multi_reserve_bad_debt_executed', 'proxy_code_runtime_match_verified', 'usdc_full_source_runtime_match', 'initial_health_validation_executed', 'historical_state_authenticated', 'activation_allowed']:
            self.assertFalse(self.fixture[k])
        bad = copy.deepcopy(value); bad['sources'][builder.NAME]['content'] += '\n'
        with self.assertRaises(ValueError): builder.fixture(bad, self.raw, self.raws)

    def run_cli(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.json'; p.write_text(json.dumps(data))
            return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'], 'simulate', '--input', str(p)], capture_output=True, text=True)

    def test_closed_cli_example_matches_27_words_16_logs_and_all_storage_changes(self):
        data = identity.read_json(EVIDENCE / 'synthetic/input.json'); expected = identity.read_json(EVIDENCE / 'synthetic/output.json')
        result = self.run_cli(data); self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)
        words = [int(expected['output'][i:i+64], 16) for i in range(2, len(expected['output']), 64)]
        self.assertEqual(len(words), 27); self.assertEqual(words[-3:], [60, 240, 60])
        self.assertEqual(len(expected['logs']), 16)
        self.assertEqual(sum(len(d['storage']) for d in expected['account_deltas']), 24)
        self.assertFalse(expected['canonical_state_authenticated']); self.assertEqual(data['snapshot']['kind'], 'synthetic_fixture')
        for address, name in [(capture.USDC, 'usdc-proxy'), (capture.IMPLEMENTATION, 'usdc-implementation')]:
            a = next(a for a in data['snapshot']['accounts'] if a['address'] == address)
            self.assertEqual(a['runtime_code'], self.fixture['contracts'][name]['runtime_code'])

    def test_actual_proxy_getters_confirm_supplied_balance_allowance_pause_and_blacklist(self):
        original = identity.read_json(EVIDENCE / 'synthetic/input.json')
        selectors = self.fixture['contracts']['usdc-implementation']['selectors']
        for signature, words, expected in [
            ('balanceOf(address)', [int(CALLER, 16)], 100),
            ('balanceOf(address)', [int(capture.ATOKEN, 16)], 200),
            ('allowance(address,address)', [int(CALLER, 16), int(POOL, 16)], 100),
            ('paused()', [], 0), ('isBlacklisted(address)', [int(CALLER, 16)], 0),
        ]:
            data = copy.deepcopy(original); data['call'].update(to=capture.USDC, calldata='0x' + selectors[signature] + ''.join(f'{v:064x}' for v in words))
            result = self.run_cli(data); self.assertEqual(result.returncode, 0, result.stderr)
            out = json.loads(result.stdout); self.assertEqual(out['status'], 'success'); self.assertEqual(int(out['output'], 16), expected)
            self.assertEqual(out['logs'], []); self.assertTrue(all(not a['storage'] for a in out['account_deltas']))

    def test_cli_missing_usdc_code_routing_and_bad_hash_fail_closed(self):
        original = identity.read_json(EVIDENCE / 'synthetic/input.json')
        for kind in ['proxy', 'implementation', 'routing', 'hash']:
            data = copy.deepcopy(original); token = next(a for a in data['snapshot']['accounts'] if a['address'] == capture.USDC)
            if kind in ['proxy', 'implementation']:
                address = capture.USDC if kind == 'proxy' else capture.IMPLEMENTATION
                data['snapshot']['accounts'] = [a for a in data['snapshot']['accounts'] if a['address'] != address]
            elif kind == 'routing': token['storage'].pop(str(int(capture.IMPLEMENTATION_SLOT, 16)))
            else: token['code_hash'] = '0x' + '00' * 32
            result = self.run_cli(data); self.assertNotEqual(result.returncode, 0); self.assertEqual(result.stdout, '')

    def test_cli_late_usdc_pause_rolls_back_weth_debt_rates_fees_rewards_and_logs(self):
        data = identity.read_json(EVIDENCE / 'synthetic/input.json')
        token = next(a for a in data['snapshot']['accounts'] if a['address'] == capture.USDC)
        token['storage']['1'] = str(1 << 160)
        result = self.run_cli(data); self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout); self.assertEqual(out['status'], 'revert')
        self.assertEqual(out['logs'], []); self.assertTrue(all(not a['storage'] for a in out['account_deltas']))
        self.assertIn(b'Pausable: paused'.hex(), out['output'])


if __name__ == '__main__':
    unittest.main()
