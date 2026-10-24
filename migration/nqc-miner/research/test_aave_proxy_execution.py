"""Adversarial provenance checks and an exact CLI replay with deployed proxy code."""
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import build_aave_proxy_execution as builder

identity = builder.identity
EVIDENCE = builder.DIRECTORY


class ProxyExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile, cls.value = builder.inputs()
        cls.output = identity.read_json(EVIDENCE / 'compiler/output.json.gz')
        cls.histories = builder.capture.replay()
        cls.fixture = identity.read_json(identity.MODULE / 'fixtures/aave_proxy_execution.json')

    def test_retained_fixture_rebuilds_from_pinned_sources_and_both_providers(self):
        self.assertEqual(builder.retained_fixture(), self.fixture)
        self.assertEqual(len(self.fixture['proxy_samples']), 10)
        self.assertEqual(len({s['proxy'] for s in self.fixture['proxy_samples']}), 6)
        self.assertEqual(len(self.fixture['excluded_proxy_samples']), 2)
        for flag in ['proxy_synthetic', 'historical_state_authenticated', 'complete_liquidation_verified', 'executable_eligibility_verified', 'activation_allowed']:
            self.assertFalse(self.fixture[flag])
        for flag in ['pool_entrypoint_synthetic', 'rewards_controller_synthetic', 'proxy_code_runtime_match_verified']:
            self.assertTrue(self.fixture[flag])
        self.assertEqual(self.fixture['previous_fixture_sha256'], identity.sha((identity.MODULE / 'fixtures/aave_debt_execution.json').read_bytes()))

    def test_compilation_preserves_all_source_bytes_and_original_settings(self):
        source = identity.read_json(EVIDENCE / 'source.json.gz')
        self.assertEqual(self.value['sources'], source['sources'])
        actual = copy.deepcopy(self.value['settings']); actual.pop('outputSelection')
        self.assertEqual(actual, source['compilation']['compilerSettings'])
        self.assertEqual(self.value, identity.read_json(EVIDENCE / 'compiler/input.json.gz'))
        self.assertEqual(identity.sha(gzip.decompress((EVIDENCE / 'compiler/output.json.gz').read_bytes())), self.profile['compiler_output_sha256'])
        index = identity.read_json(identity.EVIDENCE / 'compiler-list.json.gz')
        build = next(b for b in index['builds'] if b['longVersion'] == self.profile['compiler_version'])
        self.assertEqual(build['sha256'], '0x' + self.profile['compiler_sha256'])
        runtime = builder.render(self.output, self.profile)
        self.assertEqual(runtime['runtime_sha256'], builder.RUNTIME_SHA)
        self.assertEqual(len(runtime['substitutions']), 6)
        self.assertEqual(runtime['admin'], builder.ADMIN)

    def test_modified_code_metadata_or_immutable_locations_are_rejected(self):
        path, name = self.profile['target'].rsplit(':', 1)
        for mutation in ['metadata', 'body', 'immutable-size', 'immutable-name', 'immutable-overlap']:
            output = copy.deepcopy(self.output)
            code = output['contracts'][path][name]['evm']['deployedBytecode']
            key = next(iter(code['immutableReferences']))
            refs = code['immutableReferences'][key]
            if mutation in ['metadata', 'body']:
                i = -1 if mutation == 'metadata' else 0
                chars = list(code['object']); chars[i] = '1' if chars[i] != '1' else '2'; code['object'] = ''.join(chars)
            elif mutation == 'immutable-size': refs[0]['length'] = 31
            elif mutation == 'immutable-overlap': refs[1]['start'] = refs[0]['start']
            else: code['immutableReferences'] = {'999999999': refs}
            with self.assertRaises(ValueError, msg=mutation): builder.render(output, self.profile)

    def test_modified_provider_code_slot_or_block_pin_is_rejected(self):
        for mutation in ['code', 'slot', 'block', 'derived-slot']:
            histories = copy.deepcopy(self.histories)
            h = histories[0]; token = h['tokens'][0]
            if mutation == 'derived-slot':
                token['slot_word'] = '0x' + '00' * 32
            else:
                method = 'eth_getStorageAt' if mutation == 'slot' else 'eth_getCode'
                row = next(r for r in h['records'] if r['request']['method'] == method and r['request']['params'][0] == token['proxy'])
                if mutation == 'block': row['request']['params'][-1]['requireCanonical'] = False
                else: row['response']['result'] = '0x' + '00' * 32
            with self.assertRaises(ValueError, msg=mutation): builder.fixture_from(self.output, self.profile, histories)

    def test_missing_coverage_and_unknown_excluded_family_are_rejected(self):
        histories = copy.deepcopy(self.histories); histories[0]['tokens'].pop()
        with self.assertRaises(ValueError): builder.fixture_from(self.output, self.profile, histories)
        histories = copy.deepcopy(self.histories)
        token = next(t for h in histories for t in h['tokens'] if t['proxy_sha256'] == builder.EXCLUDED_SHA)
        token['proxy_sha256'] = '0' * 64
        with self.assertRaises(ValueError): builder.fixture_from(self.output, self.profile, histories)

    def run_cli(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.json'; path.write_text(json.dumps(data))
            return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'], 'simulate', '--input', str(path)], capture_output=True, text=True)

    def test_actual_proxy_example_reexecutes_exactly_through_real_cli(self):
        data = identity.read_json(EVIDENCE / 'synthetic/input.json')
        expected = identity.read_json(EVIDENCE / 'synthetic/output.json')
        proxy = next(a for a in data['snapshot']['accounts'] if a['address'] == builder.ADDRESS)
        self.assertEqual(proxy['runtime_code'], self.fixture['contracts']['AuditedDebtProxy']['runtime_code'])
        self.assertEqual(proxy['storage'][str(int(builder.capture.probe.SLOT, 16))], str(int('b27c52c7f84819e3157993489741cb60786ae330', 16)))
        result = self.run_cli(data); self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)
        self.assertFalse(expected['canonical_state_authenticated'])
        self.assertEqual(expected['status'], 'success')
        old = identity.read_json(identity.MODULE / 'evidence/aave-debt-execution-20261023/synthetic/output.json')
        for key in ['output', 'logs', 'account_deltas']:
            if key == 'account_deltas':
                # Gas changes account balances; compare all changed contract storage.
                self.assertEqual({a['address']: a['storage'] for a in expected[key] if a['storage']}, {a['address']: a['storage'] for a in old[key] if a['storage']})
            else: self.assertEqual(expected[key], old[key])

    def test_cli_rejects_missing_proxy_slot_target_or_tampered_code_hash(self):
        original = identity.read_json(EVIDENCE / 'synthetic/input.json')
        for mutation in ['slot', 'target', 'code']:
            data = copy.deepcopy(original)
            proxy = next(a for a in data['snapshot']['accounts'] if a['address'] == builder.ADDRESS)
            if mutation == 'slot': proxy['storage'].pop(str(int(builder.capture.probe.SLOT, 16)))
            elif mutation == 'target': data['snapshot']['accounts'] = [a for a in data['snapshot']['accounts'] if a['address'] != '0xb27c52c7f84819e3157993489741cb60786ae330']
            else: proxy['runtime_code'] = '0x00'
            result = self.run_cli(data)
            self.assertNotEqual(result.returncode, 0, mutation)
            self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
