"""Adversarial checks for bounded historical dependency identities."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import capture_aave_dependencies as capture


class FakeQuery:
    def __init__(self, plan, mutate=None):
        self.plan, self.mutate, self.sequence = plan, mutate, 0

    def __call__(self, provider, method, args):
        self.sequence += 1
        if method == 'eth_chainId':
            value = '0x1'
        elif method == 'eth_getBlockByNumber':
            h = self.plan['block'] if args[0] == hex(self.plan['block']['number']) else self.plan['event_anchor']
            value = {'number': hex(h['number']), 'hash': h['hash'], 'parentHash': h['parent_hash'], 'timestamp': hex(h['timestamp'])}
        elif method == 'eth_getStorageAt':
            value = '0x' + '0' * 24 + '12' * 20
        else:
            value = '0x60006000'
        if self.mutate:
            value = self.mutate(self.sequence, provider, method, args, value)
        return {'request': {'jsonrpc': '2.0', 'id': self.sequence, 'method': method, 'params': args}, 'response': {'jsonrpc': '2.0', 'id': self.sequence, 'result': value}}


class DependencyCaptureTests(unittest.TestCase):
    def setUp(self):
        self.plan = capture.plans()[0]

    def test_bounded_capture_links_original_reserves_and_compares_all_bytes(self):
        query = FakeQuery(self.plan)
        report = capture.capture_one(self.plan, query)
        self.assertEqual(query.sequence, 44)
        self.assertEqual(len(report['tokens']), 4)
        self.assertEqual(len(capture.TOKENS), 8)
        self.assertEqual(report['strategy']['address'], capture.STRATEGY)
        for field in ('state_authenticated', 'transaction_prestate', 'source_match_verified', 'executable_eligibility_verified', 'activation_allowed'):
            self.assertFalse(report[field])

    def test_chain_finality_and_each_header_recheck_fail_closed(self):
        for index in [1,2,3,4,18,19,20,21,22,23,24,38,39,40,41,42,43,44]:
            def mutate(i, provider, method, args, value):
                if i != index:
                    return value
                if method == 'eth_chainId':
                    return '0x2'
                value = copy.deepcopy(value)
                value['number' if args[0] == 'finalized' else 'hash'] = '0x1' if args[0] == 'finalized' else '0x' + 'ff' * 32
                return value
            with self.subTest(index=index), self.assertRaises(ValueError):
                capture.capture_one(self.plan, FakeQuery(self.plan, mutate))

    def test_each_token_proxy_implementation_and_strategy_disagreement_rejected(self):
        for index in range(25, 38):
            def mutate(i, provider, method, args, value):
                return value[:-2] + '99' if i == index else value
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'disagreement'):
                capture.capture_one(self.plan, FakeQuery(self.plan, mutate))

    def test_missing_code_and_noncanonical_proxy_slot_rejected(self):
        for bad, target in [('0x',6),('0x0',7),('0xGG',17),('0x'+'0'*64,5),('0x'+'f'*64,5)]:
            def mutate(i, provider, method, args, value):
                return bad if i == target else value
            with self.subTest(value=bad), self.assertRaises(ValueError):
                capture.capture_one(self.plan, FakeQuery(self.plan, mutate))

    def test_unpinned_foreign_or_mutating_requests_never_reach_network(self):
        token = self.plan['reserves'][0]['a_token']
        pin = {'blockHash': self.plan['block']['hash'], 'requireCanonical': True}
        invalid = [('eth_sendRawTransaction',['0x']), ('eth_getStorageAt',[token,'0x0',pin]), ('eth_getStorageAt',[capture.STRATEGY,capture.probe.SLOT,pin]), ('eth_getCode',[token,'latest']), ('eth_getCode',[token,{**pin,'requireCanonical':False}]), ('eth_getCode',[token,{**pin,'extra':1}])]
        with patch.object(capture.urllib.request, 'build_opener') as network:
            for method, args in invalid:
                with self.assertRaises(ValueError):
                    capture.Rpc()('ethereum-primary', method, args)
            network.assert_not_called()

    def test_retained_capture_replays_and_rehashed_tampering_fails(self):
        reports = capture.replay()
        self.assertEqual(sum(len(r['records']) for r in reports), 132)
        for failure in ('id','pin','derived','extra_record','activation'):
            with tempfile.TemporaryDirectory() as tmp:
                dst = Path(tmp)/'capture'; shutil.copytree(capture.DIRECTORY/'public', dst)
                p = dst/'dependencies-000.json'; value = json.loads(p.read_bytes())
                if failure == 'id':
                    value['records'][4]['response']['id'] += 1
                elif failure == 'pin':
                    value['records'][4]['request']['params'][-1]['requireCanonical'] = False
                elif failure == 'derived':
                    value['tokens'][0]['implementation'] = '0x'+'11'*20
                elif failure == 'activation':
                    value['activation_allowed'] = True
                else:
                    value['records'].append(value['records'][-1])
                p.write_text(json.dumps(value))
                m = dst/'manifest.json'; manifest = json.loads(m.read_bytes()); manifest['observations'][0]['sha256'] = capture.probe.sha(p.read_bytes()); m.write_text(json.dumps(manifest))
                with self.subTest(failure=failure), self.assertRaises(ValueError):
                    capture.replay(dst)


class DependencyCompilationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import audit_aave_dependencies as model
        cls.model = model
        cls.profiles, cls.inputs, cls.outputs = model.retained_inputs()
        cls.histories = capture.replay()

    def test_compiled_full_runtime_equality_and_honest_limitations(self):
        report = self.model.audit(self.histories, self.profiles, self.outputs)
        self.assertEqual(len(report['contracts']), 3)
        self.assertEqual(report['provider_runtime_comparisons'], 30)
        self.assertTrue(all(c['metadata_bytes_compared'] for c in report['contracts']))
        self.assertTrue(report['implementation_runtime_match_verified'])
        for field in ('proxy_dispatch_verified','state_authenticated','transaction_prestate','external_behavior_verified','executable_eligibility_verified','activation_allowed'):
            self.assertFalse(report[field])

    def test_every_implementation_and_provider_runtime_byte_is_checked(self):
        for i, original in enumerate(self.histories):
            for n, record in enumerate(original['records']):
                if record['request']['method'] != 'eth_getCode' or record['request']['params'][0] not in self.outputs:
                    continue
                histories = copy.deepcopy(self.histories)
                histories[i]['records'][n]['response']['result'] += '00'
                with self.subTest(block=i,record=n), self.assertRaisesRegex(ValueError,'provider runtime mismatch'):
                    self.model.audit(histories,self.profiles,self.outputs)

    def test_metadata_is_compared_and_missing_profiles_or_blocks_fail(self):
        p = self.profiles[0]; outputs = copy.deepcopy(self.outputs)
        path, name = p['target'].rsplit(':',1)
        code = outputs[p['address']]['contracts'][path][name]['evm']['deployedBytecode']
        code['object'] = code['object'][:-2] + ('ff' if code['object'][-2:] != 'ff' else '00')
        with self.assertRaisesRegex(ValueError,'runtime mismatch'):
            self.model.audit(self.histories,self.profiles,outputs)
        for histories, profiles, outputs in [(self.histories[:2],self.profiles,self.outputs),(self.histories,self.profiles[:2],self.outputs),(self.histories,self.profiles,{})]:
            with self.assertRaises(ValueError):
                self.model.audit(histories,profiles,outputs)

    def test_source_settings_and_compiler_identity_are_not_relaxed(self):
        p = self.profiles[0]
        original = self.model.READ(capture.DIRECTORY/'sources'/(p['address']+'.json.gz'))
        for failure in ('source','settings','address','compiler','literal'):
            source = copy.deepcopy(original)
            if failure == 'source':
                next(iter(source['sources'].values()))['content'] += '\n'
            elif failure == 'settings':
                source['stdJsonInput']['settings']['optimizer']['runs'] += 1
            elif failure == 'address':
                source['address'] = '0x'+'11'*20
            elif failure == 'compiler':
                source['compilation']['compilerVersion'] = '0.8.28'
            else:
                next(iter(source['sources'].values()))['urls'] = ['file:///tmp/untrusted.sol']
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                self.model.compilation_input(source,p)

    def test_unknown_overlapping_out_of_bounds_and_nonzero_immutables_fail(self):
        p = self.profiles[0]
        path, name = p['target'].rsplit(':',1)
        for failure in ('unknown','overlap','bounds','width','nonzero','links'):
            output = copy.deepcopy(self.outputs[p['address']])
            code = output['contracts'][path][name]['evm']['deployedBytecode']
            refs = code['immutableReferences']; key = next(iter(refs)); first = refs[key][0]
            if failure == 'unknown':
                refs['999999999'] = refs.pop(key)
            elif failure == 'overlap':
                refs[key].append(copy.deepcopy(first))
            elif failure == 'bounds':
                first['start'] = len(code['object'])
            elif failure == 'width':
                first['length'] = 20
            elif failure == 'links':
                code['linkReferences'] = {'foreign.sol':{'Library':[{'start':0,'length':20}]}}
            else:
                offset = first['start'] * 2; code['object'] = code['object'][:offset] + 'ff' + code['object'][offset+2:]
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                self.model.render_runtime(output,p)

    def test_compiler_checksum_precedes_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            compiler = Path(tmp)/'fake-solc';compiler.write_bytes(b'fake')
            with patch.object(self.model.subprocess,'run') as run:
                with self.assertRaisesRegex(ValueError,'compiler checksum'):
                    self.model.compile_source(compiler,self.inputs[self.profiles[0]['address']],self.profiles[0])
                run.assert_not_called()
