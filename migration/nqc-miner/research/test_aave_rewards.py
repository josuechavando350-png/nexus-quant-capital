"""Historical code, closed-state controller execution and adversarial provenance."""
import copy
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import build_aave_rewards as builder

capture = builder.capture
identity = builder.identity
EVIDENCE = builder.DIRECTORY


class RewardsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles, cls.outputs = builder.retained_inputs()
        cls.rewards = capture.replay()
        cls.tokens = capture.dependencies.replay()
        cls.fixture = identity.read_json(identity.MODULE / 'fixtures/aave_rewards_execution.json')

    def test_complete_historical_capture_has_72_pinned_reads_and_three_agreed_identities(self):
        self.assertEqual([h['block']['number'] for h in self.rewards], list(identity.BLOCKS))
        self.assertEqual(sum(len(h['records']) for h in self.rewards), 72)
        for h in self.rewards:
            self.assertEqual(h['implementation'], builder.SPECS['rewards-implementation'][0])
            self.assertEqual({r['provider_id'] for r in h['records']}, set(capture.PROVIDERS))
            for flag in ['state_authenticated', 'transaction_prestate', 'external_behavior_verified', 'executable_eligibility_verified', 'activation_allowed']:
                self.assertFalse(h[flag])
        builder.audit(self.profiles, self.outputs, self.rewards, self.tokens)

    def test_capture_rejects_unpinned_foreign_slot_and_write_requests(self):
        provider = next(iter(capture.PROVIDERS)); pin = {'blockHash': self.rewards[0]['block']['hash'], 'requireCanonical': True}
        for method, args in [
            ('eth_sendRawTransaction', ['0x']),
            ('eth_call', [{}, pin]),
            ('eth_getStorageAt', [capture.REWARDS, capture.probe.SLOT, 'latest']),
            ('eth_getStorageAt', [capture.REWARDS, '0x0', pin]),
            ('eth_getStorageAt', [builder.SPECS['rewards-implementation'][0], capture.probe.SLOT, pin]),
            ('eth_getCode', [capture.REWARDS, {**pin, 'requireCanonical': False}]),
        ]:
            with self.assertRaises(ValueError): capture.validate_params(provider, method, args)

    def replay_mutation(self, mutate):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'public'; shutil.copytree(EVIDENCE / 'public', directory)
            path = directory / 'rewards-000.json'; value = identity.read_json(path); mutate(value)
            path.write_bytes(identity.encoded(value))
            manifest_path = directory / 'manifest.json'; manifest = identity.read_json(manifest_path)
            manifest['observations'][0]['sha256'] = identity.sha(path.read_bytes()); manifest_path.write_bytes(identity.encoded(manifest))
            with self.assertRaises((ValueError, StopIteration)): capture.replay(directory)

    def test_rehashed_capture_still_rejects_wrong_chain_provider_id_pin_or_derived_identity(self):
        def apply(value, kind):
            rows = value['records']
            if kind == 'chain': rows[0]['response']['result'] = '0x2'
            elif kind == 'provider': rows[0]['provider_id'] = 'foreign'
            elif kind == 'id': rows[0]['response']['id'] += 1
            elif kind == 'derived': value['implementation'] = capture.REWARDS
            else:
                row = next(r for r in rows if r['request']['method'] == 'eth_getStorageAt')
                row['request']['params'][-1]['requireCanonical'] = False
        for kind in ['chain', 'provider', 'id', 'derived', 'pin']:
            self.replay_mutation(lambda v: apply(v, kind))

    def test_rehashed_capture_rejects_provider_disagreement_incomplete_reads_and_bad_finality(self):
        def apply(value, kind):
            rows = value['records']
            if kind == 'missing': rows.pop()
            elif kind == 'finality': rows[1]['response']['result']['number'] = '0x1'
            elif kind == 'header': rows[2]['response']['result']['hash'] = '0x' + '11' * 32
            else:
                row = next(r for r in rows if r['request']['method'] == 'eth_getCode')
                row['response']['result'] = '0x6000'
        for kind in ['missing', 'finality', 'header', 'disagreement']:
            self.replay_mutation(lambda v: apply(v, kind))

    def test_sources_original_settings_and_compiler_outputs_are_bound(self):
        for profile in self.profiles:
            value = builder.source_input(profile)
            retained = identity.read_json(EVIDENCE / 'compiler' / (profile['name'] + '-input.json.gz'))
            self.assertEqual(value, retained)
            raw = gzip.decompress((EVIDENCE / 'compiler' / (profile['name'] + '-output.json.gz')).read_bytes())
            self.assertEqual(identity.sha(raw), profile['compiler_output_sha256'])
            if profile['name'] == 'second-proxy':
                original = builder.explorer_input(gzip.decompress((EVIDENCE / 'sources/second-proxy-explorer.html.gz').read_bytes()))
            else:
                original = identity.read_json(EVIDENCE / 'sources' / (profile['name'] + '.json.gz'))['stdJsonInput']
            self.assertEqual(original['sources'], value['sources'])
            left, right = copy.deepcopy(original['settings']), copy.deepcopy(value['settings'])
            left.pop('outputSelection', None); right.pop('outputSelection', None); self.assertEqual(left, right)

    def test_profile_identity_immutable_and_compiler_changes_are_rejected(self):
        for field, replacement in [('address', capture.REWARDS), ('compiler_sha256', '0' * 64), ('immutables', {'EMISSION_MANAGER': capture.REWARDS})]:
            p = copy.deepcopy(next(p for p in self.profiles if p['name'] == 'rewards-implementation'))
            p[field] = replacement
            with self.assertRaises(ValueError): builder.source_input(p)

    def test_immutable_reference_bounds_names_and_overlap_are_rejected(self):
        p = next(p for p in self.profiles if p['name'] == 'rewards-proxy'); path, name = p['target'].rsplit(':', 1)
        for kind in ['size', 'name', 'overlap', 'nonzero']:
            output = copy.deepcopy(self.outputs[p['name']]); code = output['contracts'][path][name]['evm']['deployedBytecode']
            refs = code['immutableReferences']; key = next(iter(refs))
            if kind == 'size': refs[key][0]['length'] = 31
            elif kind == 'name': code['immutableReferences'] = {'999999': refs[key]}
            elif kind == 'overlap': refs[key][1]['start'] = refs[key][0]['start']
            else:
                start = refs[key][0]['start'] * 2; code['object'] = code['object'][:start] + '01' + code['object'][start + 2:]
            with self.assertRaises(ValueError): builder.render(output, p)

    def test_runtime_body_and_metadata_changes_fail_historical_byte_comparison(self):
        for p in self.profiles:
            for end in [False, True]:
                outputs = copy.deepcopy(self.outputs); path, name = p['target'].rsplit(':', 1)
                code = outputs[p['name']]['contracts'][path][name]['evm']['deployedBytecode']; chars = list(code['object']); i = -1 if end else 0; chars[i] = '1' if chars[i] != '1' else '2'; code['object'] = ''.join(chars)
                with self.assertRaises(ValueError): builder.audit(self.profiles, outputs, self.rewards, self.tokens)

    def test_provider_runtime_slot_and_block_mutations_fail_audit(self):
        for kind in ['runtime', 'slot', 'pin', 'derived']:
            histories = copy.deepcopy(self.rewards); h = histories[0]
            if kind == 'derived': h['slot_word'] = '0x' + '00' * 32
            else:
                method = 'eth_getStorageAt' if kind == 'slot' else 'eth_getCode'
                row = next(r for r in h['records'] if r['request']['method'] == method)
                if kind == 'pin': row['request']['params'][-1]['requireCanonical'] = False
                else: row['response']['result'] = '0x' + '00' * 32
            with self.assertRaises(ValueError): builder.audit(self.profiles, self.outputs, histories, self.tokens)
        for kind in ['slot', 'block']:
            histories = copy.deepcopy(self.tokens)
            if kind == 'block': histories[1]['block']['number'] += 1
            else:
                address = builder.SPECS['second-proxy'][0]
                row = next(r for r in histories[1]['records'] if r['request']['method'] == 'eth_getStorageAt' and r['request']['params'][0] == address)
                row['response']['result'] = '0x' + '00' * 32
            with self.assertRaises(ValueError): builder.audit(self.profiles, self.outputs, self.rewards, histories)

    def test_fixture_covers_both_proxy_families_and_actual_rewards_with_synthetic_state(self):
        self.assertEqual(builder.fixture(), self.fixture)
        self.assertEqual(len(self.fixture['proxy_samples']), 12)
        self.assertEqual(len({s['proxy'] for s in self.fixture['proxy_samples']}), 8)
        self.assertEqual(self.fixture['excluded_proxy_samples'], [])
        self.assertEqual({s['proxy_contract'] for s in self.fixture['proxy_samples']}, {'AuditedDebtProxy', 'AuditedDebtProxy2'})
        for flag in ['proxy_synthetic', 'rewards_controller_synthetic', 'rewards_proxy_synthetic', 'historical_state_authenticated', 'activation_allowed', 'executable_eligibility_verified']:
            self.assertFalse(self.fixture[flag])
        self.assertTrue(self.fixture['rewards_parameters_synthetic']); self.assertTrue(self.fixture['pool_entrypoint_synthetic'])
        self.assertNotIn('RewardsProbe', self.fixture['contracts'])

    def test_packed_nested_controller_layout_matches_explicit_execution_witnesses(self):
        layout = self.fixture['contracts']['RewardsController']['storage_layout']; types = layout['types']
        assets = next(s for s in layout['storage'] if s['label'] == '_assets'); self.assertEqual(assets['slot'], '1')
        asset = types[types[assets['type']]['value']]
        self.assertEqual([(m['label'], m['slot'], m['offset']) for m in asset['members']], [('rewards','0',0),('availableRewards','1',0),('availableRewardsCount','2',0),('decimals','2',16)])
        reward = types[types[asset['members'][0]['type']]['value']]
        self.assertEqual([(m['label'], m['slot'], m['offset']) for m in reward['members']], [('index','0',0),('emissionPerSecond','0',13),('lastUpdateTimestamp','0',24),('distributionEnd','0',28),('usersData','1',0)])
        user = types[types[reward['members'][-1]['type']]['value']]
        self.assertEqual([(m['label'],m['offset']) for m in user['members']], [('index',0),('accrued',13)])

    def run_cli(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.json'; p.write_text(json.dumps(data))
            return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'], 'simulate', '--input', str(p)], capture_output=True, text=True)

    def test_real_rewards_example_reexecutes_through_cli(self):
        data = identity.read_json(EVIDENCE / 'synthetic/input.json'); expected = identity.read_json(EVIDENCE / 'synthetic/output.json')
        result = self.run_cli(data); self.assertEqual(result.returncode, 0, result.stderr); self.assertEqual(json.loads(result.stdout), expected)
        self.assertFalse(expected['canonical_state_authenticated']); self.assertEqual(expected['status'], 'success')
        for address, name in [(capture.REWARDS, 'RealRewardsProxy'), (builder.SPECS['rewards-implementation'][0], 'RewardsController')]:
            account = next(a for a in data['snapshot']['accounts'] if a['address'] == address)
            self.assertEqual(account['runtime_code'], self.fixture['contracts'][name]['runtime_code'])
        old = identity.read_json(identity.MODULE / 'evidence/aave-token-proxy-execution-20261023/synthetic/output.json')
        self.assertEqual(expected['output'], old['output'])
        self.assertEqual([l for l in expected['logs'] if l['address'] != capture.REWARDS], [l for l in old['logs'] if l['address'] != capture.REWARDS])

    def test_cli_rejects_missing_rewards_target_proxy_slot_or_corrupt_code_hash(self):
        original = identity.read_json(EVIDENCE / 'synthetic/input.json')
        for kind in ['target', 'slot', 'code']:
            data = copy.deepcopy(original); a = next(a for a in data['snapshot']['accounts'] if a['address'] == capture.REWARDS)
            if kind == 'target': data['snapshot']['accounts'] = [a for a in data['snapshot']['accounts'] if a['address'] != builder.SPECS['rewards-implementation'][0]]
            elif kind == 'slot': a['storage'].pop(str(int(capture.probe.SLOT,16)))
            else: a['runtime_code'] = '0x00'
            result = self.run_cli(data); self.assertNotEqual(result.returncode,0); self.assertEqual(result.stdout,'')

    def test_explorer_parser_rejects_wrong_compiler_and_duplicate_literals(self):
        raw = gzip.decompress((EVIDENCE / 'sources/second-proxy-explorer.html.gz').read_bytes())
        for changed in [raw.replace(b'v0.8.22+commit.4fc1097e', b'v0.8.21+commit.4fc1097e'), raw + b"\nvar editor_contractJsonData = '{}';"]:
            with self.assertRaises(ValueError): builder.explorer_input(changed)


if __name__ == '__main__': unittest.main()
