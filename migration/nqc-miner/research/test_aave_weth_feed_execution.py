"""Real WETH feed proxy code with explicitly artificial downstream price state."""
import copy
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import build_aave_weth_feed_execution as builder

identity, capture, EVIDENCE = builder.identity, builder.capture, builder.DIRECTORY


class WethFeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value=identity.read_json(EVIDENCE/'compiler/input.json.gz')
        cls.raw=gzip.decompress((EVIDENCE/'compiler/output.json.gz').read_bytes())
        cls.pv=identity.read_json(EVIDENCE/'compiler/proxy-input.json.gz')
        cls.praw=gzip.decompress((EVIDENCE/'compiler/proxy-output.json.gz').read_bytes())
        cls.fixture=identity.read_json(identity.MODULE/'fixtures/aave_weth_feed_execution.json')
        cls.history=capture.replay()
        cls.examples={m:{n:identity.read_json(EVIDENCE/'synthetic'/m/(n+'.json')) for n in ['input','output','models']} for m in ['atoken','underlying']}

    def cli(self,data):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json';p.write_text(json.dumps(data))
            return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'],'simulate','--input',str(p)],capture_output=True,text=True)

    def output(self,result):
        self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)

    def acct(self,data,address):return next(a for a in data['snapshot']['accounts'] if a['address']==address)

    def same(self,out,reference):
        self.assertEqual(out['status'],'success');self.assertEqual(out['output'],reference['output']);self.assertEqual(out['logs'],reference['logs'])
        def storage(v):return {a['address']:a['storage'] for a in v['account_deltas'] if a['storage']}
        self.assertEqual(storage(out),storage(reference))

    def atomic(self,result,message=None):
        out=self.output(result);self.assertEqual(out['status'],'revert');self.assertEqual(out['logs'],[])
        self.assertTrue(all(not a['storage'] for a in out['account_deltas']))
        if message is not None:self.assertIn(message.encode().hex(),out['output'])
        return out

    def controller(self,data,example):
        a=copy.deepcopy(example['models']['controller_account']);data['snapshot']['accounts'].append(a)
        self.acct(data,capture.PROXY)['storage']['5']=str(int(a['address'],16));return a

    def fallback(self,data,example):
        a=copy.deepcopy(example['models']['fallback_account']);data['snapshot']['accounts'].append(a)
        self.acct(data,capture.prior.ORACLE)['storage']['1']=str(int(a['address'],16))

    def test_capture_scope_rejects_mutations_unpinned_reads_and_foreign_selectors(self):
        provider=next(iter(capture.PROVIDERS));pin={'blockHash':'0x'+'11'*32,'requireCanonical':True}
        for method,args in [('eth_sendRawTransaction',['0x']),('eth_call',[{'to':capture.PROXY,'data':'0x92eefe9b'+'00'*32},pin]),
            ('eth_getStorageAt',[capture.PROXY,'0x0',pin]),('eth_call',[{'to':capture.PROXY,'data':'0x50d25bcd'},'latest']),
            ('eth_getCode',[capture.PROXY,dict(pin,requireCanonical=False)]),
            ('eth_call',[{'to':capture.prior.ORACLE,'data':'0x245a7bfc'},pin]),
            ('eth_call',[{'to':capture.prior.ORACLE,'data':'0x50d25bcd','from':capture.prior.ORACLE},pin]),
            ('eth_call',[{'to':capture.PROXY,'data':'0x50d25bcd','from':capture.PROXY},pin])]:
            with self.assertRaises(ValueError):capture.validate(provider,method,args)

    def test_capture_binds_three_blocks_two_providers_packed_routes_and_retained_prices(self):
        self.assertEqual(len(self.history),3);self.assertEqual(sum(len(h['records']) for h in self.history),114)
        for h,old in zip(self.history,capture.prior.replay()):
            self.assertEqual(h['block'],old['block']);self.assertEqual(h['phase_id'],2)
            self.assertEqual(int(h['phase_word'],16),2+(int(h['aggregator'],16)<<16))
            self.assertEqual(h['controller'],'0x'+'00'*20);self.assertEqual(h['answer_word'],old['feeds'][1]['answer_word'])
            self.assertEqual(h['answer_word'],h['proxy_caller_answer_word'])
            self.assertEqual({r['provider_id'] for r in h['records']},set(capture.PROVIDERS))
            self.assertFalse(h['historical_state_authenticated']);self.assertFalse(h['price_freshness_verified'])

    def test_capture_semantic_tampering_fails_after_rehashing_files(self):
        for kind in ['phase','controller','runtime','pin','id']:
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'public';shutil.copytree(EVIDENCE/'public',p);path=p/'feed-000.json';h=identity.read_json(path);rows=h['records']
                if kind in ['phase','controller']:
                    slot='0x2' if kind=='phase' else '0x5'
                    row=next(r for r in rows if r['request']['method']=='eth_getStorageAt' and r['request']['params'][1]==slot)
                    row['response']['result']='0x'+f'{int(row["response"]["result"],16)^1:064x}'
                elif kind=='runtime':
                    row=next(r for r in rows if r['provider_id']==list(capture.PROVIDERS)[1] and r['request']['method']=='eth_getCode' and r['request']['params'][0]==h['aggregator'])
                    row['response']['result']='0x00'
                elif kind=='pin':next(r for r in rows if r['request']['method']=='eth_call')['request']['params'][-1]['requireCanonical']=False
                else:rows[0]['response']['id']+=1
                path.write_bytes(identity.encoded(h));manifest=identity.read_json(p/'manifest.json');manifest['observations'][0]['sha256']=identity.sha(path.read_bytes())
                (p/'manifest.json').write_bytes(identity.encoded(manifest))
                with self.assertRaises(ValueError):capture.replay(p)

    def test_fixture_rebuild_binds_unmodified_sources_settings_selectors_and_layout(self):
        self.assertEqual(builder.fixture(self.value,self.raw,self.pv,self.praw),self.fixture)
        source,value=builder.proxy_input();self.assertEqual(value,self.pv);self.assertEqual(value['sources'],source['sources'])
        settings=copy.deepcopy(value['settings']);settings.pop('outputSelection');self.assertEqual(settings,source['compilation']['compilerSettings'])
        self.assertEqual(settings['evmVersion'],'istanbul');self.assertEqual(settings['optimizer'],{'enabled':True,'runs':1000000})
        proxy=self.fixture['contracts']['EACAggregatorProxy'];self.assertEqual(proxy['runtime_bytes'],9571)
        self.assertTrue(proxy['full_runtime_recompiled_match']);self.assertTrue(proxy['metadata_bytes_compared']);self.assertFalse(proxy['canonical_code_proof_verified'])
        self.assertEqual((identity.MODULE/builder.NAME).read_text(),builder.HARNESS)
        layout=self.fixture['contracts'][builder.CONTRACT]['storage_layout']['storage']
        self.assertEqual([(x['label'],x['slot'],x['offset']) for x in layout],[('allowed','0',0),('blocked','1',0),('expectedUser','2',0),('expectedProxy','3',0)])

    def test_metadata_input_and_layout_mutations_are_rejected(self):
        out=json.loads(self.praw)
        for kind in ['metadata','slot','offset']:
            changed=copy.deepcopy(out);c=changed['contracts'][builder.PROXY_PATH]['EACAggregatorProxy']
            if kind=='metadata':
                b=c['evm']['deployedBytecode'];b['object']=b['object'][:-2]+('00' if b['object'][-2:]!='00' else '01')
            elif kind=='slot':next(x for x in c['storageLayout']['storage'] if x['label']=='currentPhase')['slot']='3'
            else:
                f=next(x for x in c['storageLayout']['storage'] if x['label']=='currentPhase')
                c['storageLayout']['types'][f['type']]['members'][1]['offset']=0
            with self.assertRaises(ValueError):builder.audit_proxy(self.pv,identity.encoded(changed),self.history)
        changed=copy.deepcopy(self.pv);changed['sources'][builder.PROXY_PATH]['content']+='\n'
        with self.assertRaises(ValueError):builder.audit_proxy(changed,self.praw,self.history)

    def test_both_cli_examples_preserve_full_effects_and_explicit_synthetic_boundaries(self):
        prior=identity.read_json(identity.MODULE/'fixtures/aave_oracle_execution.json')
        for name,c in prior['contracts'].items():self.assertEqual(c,self.fixture['contracts'][name])
        self.assertTrue(self.fixture['weth_feed_proxy_runtime_executed'])
        for k in ['all_observed_feed_runtimes_executed','weth_aggregator_runtime_executed','usdc_feed_runtime_executed',
            'feed_state_authenticated','price_freshness_verified','historical_state_authenticated','complete_liquidation_verified','activation_allowed']:
            self.assertFalse(self.fixture[k])
        for mode,e in self.examples.items():
            out=self.output(self.cli(e['input']));self.assertEqual(out,e['output'])
            self.same(out,identity.read_json(builder.oracle.DIRECTORY/'synthetic'/mode/'output.json'))
            self.assertEqual((len(out['output'])-2)//64,47);self.assertFalse(out['canonical_state_authenticated'])
            self.assertEqual(self.acct(e['input'],capture.PROXY)['runtime_code'],self.fixture['contracts']['EACAggregatorProxy']['runtime_code'])
            a=self.acct(e['input'],e['models']['aggregator']);self.assertNotEqual(identity.sha(bytes.fromhex(a['runtime_code'][2:])),self.history[0]['aggregator_runtime_sha256'])

    def test_controller_grant_denial_revert_and_caller_binding(self):
        for e in self.examples.values():
            data=copy.deepcopy(e['input']);self.controller(data,e);self.same(self.output(self.cli(data)),e['output'])
            for slot,value,message in [('0','0','No access'),('1','1','synthetic controller blocked'),('2','1','No access'),('3','1','No access')]:
                denied=copy.deepcopy(e['input']);a=self.controller(denied,e);a['storage'][slot]=value;self.atomic(self.cli(denied),message)
            direct=copy.deepcopy(data);direct['call'].update(to=capture.PROXY,calldata='0x50d25bcd');self.atomic(self.cli(direct),'No access')

    def test_proxy_forwards_its_own_identity_to_caller_sensitive_test_double(self):
        for e in self.examples.values():
            data=copy.deepcopy(e['input']);accounts=data['snapshot']['accounts'];accounts.remove(self.acct(data,e['models']['aggregator']))
            accounts.append(copy.deepcopy(e['models']['caller_sensitive_account']))
            self.same(self.output(self.cli(data)),e['output'])
            data['call'].update(to=e['models']['aggregator'],calldata='0x50d25bcd')
            out=self.output(self.cli(data));self.assertEqual(out['status'],'success');self.assertEqual(out['output'],'0x'+f'{17:064x}')
            self.assertEqual(out['logs'],[]);self.assertTrue(all(not a['storage'] for a in out['account_deltas']))

    def test_signed_values_use_oracle_fallback_and_positive_limit_is_returned_exactly(self):
        for e in self.examples.values():
            for value in [0,2**256-1,2**255]:
                data=copy.deepcopy(e['input']);self.fallback(data,e);self.acct(data,e['models']['aggregator'])['storage']['0']=str(value)
                self.same(self.output(self.cli(data)),e['output'])
        e=self.examples['atoken'];data=copy.deepcopy(e['input']);maximum=2**255-1
        self.acct(data,e['models']['aggregator'])['storage']['0']=str(maximum)
        data['call'].update(to=capture.prior.ORACLE,calldata='0xb3596f07'+e['models']['collateral'][2:].rjust(64,'0'))
        out=self.output(self.cli(data));self.assertEqual(out['status'],'success');self.assertEqual(out['output'],'0x'+f'{maximum:064x}')
        self.assertEqual(out['logs'],[]);self.assertTrue(all(not a['storage'] for a in out['account_deltas']))

    def test_missing_proxy_and_downstream_witnesses_and_reverts_fail_closed(self):
        for e in self.examples.values():
            for address,slot in [(capture.PROXY,'2'),(capture.PROXY,'5'),(e['models']['aggregator'],'0')]:
                data=copy.deepcopy(e['input']);self.acct(data,address)['storage'].pop(slot)
                result=self.cli(data);self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,'')
            data=copy.deepcopy(e['input']);data['snapshot']['accounts'].remove(self.acct(data,e['models']['aggregator']))
            result=self.cli(data);self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,'')
            data=copy.deepcopy(e['input']);self.fallback(data,e);self.acct(data,e['models']['aggregator'])['storage']['1']='1'
            self.atomic(self.cli(data),'synthetic feed blocked')

    def test_phase_bits_alternate_routing_and_late_usdc_failure_preserve_atomicity(self):
        for e in self.examples.values():
            for phase in [0,65535]:
                data=copy.deepcopy(e['input']);address='0x'+'44'*20
                self.acct(data,e['models']['aggregator'])['address']=address
                self.acct(data,capture.PROXY)['storage']['2']=str((((1<<80)-1)<<176)|(int(address,16)<<16)|phase)
                self.same(self.output(self.cli(data)),e['output'])
            data=copy.deepcopy(e['input']);self.acct(data,capture.prior.ASSETS[0])['storage']['1']=str(1<<160)
            self.atomic(self.cli(data),'Pausable: paused')


if __name__=='__main__':unittest.main()
