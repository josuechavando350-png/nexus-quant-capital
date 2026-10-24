"""Observed DualAggregator runtime, round selection and explicit state boundaries."""
import copy
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import build_aave_dual_aggregator_execution as builder

identity,capture,EVIDENCE=builder.identity,builder.capture,builder.DIRECTORY


class DualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value=identity.read_json(EVIDENCE/'compiler/input.json.gz');cls.raw=gzip.decompress((EVIDENCE/'compiler/output.json.gz').read_bytes())
        cls.fixture=identity.read_json(identity.MODULE/'fixtures/aave_dual_aggregator_execution.json');cls.history=capture.replay()
        cls.examples={m:{n:identity.read_json(EVIDENCE/'synthetic'/m/(n+'.json')) for n in ['input','output','models']} for m in ['atoken','underlying']}
    def cli(self,data):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json';p.write_text(json.dumps(data));return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'],'simulate','--input',str(p)],capture_output=True,text=True)
    def output(self,result):
        self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
    def acct(self,data,address=capture.AGGREGATOR):return next(a for a in data['snapshot']['accounts'] if a['address']==address)
    def same(self,out,reference):
        self.assertEqual(out['status'],'success');self.assertEqual(out['output'],reference['output']);self.assertEqual(out['logs'],reference['logs'])
        def storage(v):return {a['address']:a['storage'] for a in v['account_deltas'] if a['storage']}
        self.assertEqual(storage(out),storage(reference))
    def atomic(self,result):
        out=self.output(result);self.assertEqual(out['status'],'revert');self.assertEqual(out['logs'],[]);self.assertTrue(all(not a['storage'] for a in out['account_deltas']));return out
    def hot(self,data,latest,secondary,flag=False):self.acct(data)['storage']['13']=str((latest<<48)|(secondary<<80)|(int(flag)<<240))
    def round(self,data,e,n,answer,recorded):
        self.acct(data)['storage'][e['models']['round_slots'][str(n)]]=str((answer%2**192)|(max(0,recorded-1)<<192)|(recorded<<224))
    def price_call(self,data):data['call'].update(to=capture.prior.prior.ORACLE,calldata='0xb3596f07'+capture.prior.prior.ASSETS[1][2:].rjust(64,'0'))

    def test_request_scope_budget_and_unordered_response_identity_are_closed(self):
        provider=next(iter(capture.PROVIDERS));pin={'blockHash':'0x'+'11'*32,'requireCanonical':True}
        for method,args in [('eth_sendRawTransaction',['0x']),('eth_getCode',[capture.AGGREGATOR,'latest']),
            ('eth_getStorageAt',[capture.AGGREGATOR,'0x0',pin]),('eth_call',[{'to':capture.AGGREGATOR,'data':'0xb17f2a6b'+'00'*32},pin]),
            ('eth_call',[{'to':capture.AGGREGATOR,'data':'0xfeaf968c','from':capture.AGGREGATOR},pin])]:
            with self.assertRaises(ValueError):capture.validate(provider,method,args)
        rpc=capture.Rpc();rpc.sequence=capture.MAX_REQUESTS
        with self.assertRaises(ValueError):rpc(provider,[('eth_chainId',[])])
        q=[{'id':1},{'id':2}];r=[{'jsonrpc':'2.0','id':2,'result':'0x1'},{'jsonrpc':'2.0','id':1,'result':'0x1'}]
        self.assertEqual([x['response']['id'] for x in capture.normalize_batch(q,r)],[1,2])
        for bad in [r[:1],[r[0],r[0]],[dict(r[0],id=True),r[1]],[dict(r[0],error={}),r[1]]]:
            with self.assertRaises(ValueError):capture.normalize_batch(q,bad)

    def test_all_provider_rounds_slots_headers_and_caller_prices_replay(self):
        self.assertEqual(len(self.history),3);self.assertEqual(sum(len(h['records']) for h in self.history),222)
        self.assertEqual([h['block']['number'] for h in self.history],list(identity.BLOCKS))
        for h in self.history:
            self.assertEqual(len(h['transmissions']),20);self.assertEqual(int(h['cutoff_word'],16),60)
            self.assertEqual({r['provider_id'] for r in h['records']},set(capture.PROVIDERS))
            self.assertFalse(h['historical_state_authenticated']);self.assertFalse(h['price_freshness_verified'])
        d=capture.decode_round(self.history[2]['direct_round_data']);s=capture.decode_round(self.history[2]['secondary_round_data'])
        self.assertEqual(d[:2],[25163,239563000000]);self.assertEqual(s[:2],[25162,240029113527])

    def test_capture_tampering_fails_even_when_artifact_hash_is_rewritten(self):
        for kind in ['runtime','slot','from','id','header']:
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'public';shutil.copytree(EVIDENCE/'public',p);path=p/'dual-000.json';h=identity.read_json(path);rows=h['records']
                if kind=='runtime':next(r for r in rows if r['request']['method']=='eth_getCode')['response']['result']='0x00'
                elif kind=='slot':
                    r=next(r for r in rows if r['request']['method']=='eth_getStorageAt' and len(r['request']['params'][1])==66);r['response']['result']='0x'+'00'*32
                elif kind=='from':next(r for r in rows if r['request']['method']=='eth_call' and 'from' in r['request']['params'][0])['request']['params'][0]['from']=capture.AGGREGATOR
                elif kind=='id':rows[0]['response']['id']+=1
                else:next(r for r in rows if r['request']['method']=='eth_getBlockByNumber' and r['request']['params'][0]==hex(h['block']['number']))['response']['result']['hash']='0x'+'33'*32
                path.write_bytes(identity.encoded(h));m=identity.read_json(p/'manifest.json');m['observations'][0]['sha256']=identity.sha(path.read_bytes());(p/'manifest.json').write_bytes(identity.encoded(m))
                with self.assertRaises(ValueError):capture.replay(p)

    def test_full_fixture_original_sources_settings_layout_and_metadata_boundaries(self):
        self.assertEqual(builder.fixture(self.value,self.raw),self.fixture);source,v=builder.compilation_input();self.assertEqual(v,self.value)
        self.assertEqual(v['sources'],source['sources']);settings=copy.deepcopy(v['settings']);settings.pop('outputSelection');self.assertEqual(settings,source['compilation']['compilerSettings'])
        self.assertEqual(settings['metadata']['bytecodeHash'],'none');self.assertEqual(settings['evmVersion'],'cancun')
        c=self.fixture['contracts']['DualAggregator'];self.assertEqual(c['runtime_bytes'],23186);self.assertEqual(len(c['immutable_substitutions']),10)
        self.assertTrue(c['full_runtime_recompiled_match']);self.assertTrue(c['metadata_bytes_compared']);self.assertFalse(c['metadata_source_hash_present']);self.assertFalse(c['original_source_text_authenticated'])
        self.assertEqual(int(c['immutable_words']['i_maxSyncIterations'],16),20);self.assertEqual(int(c['immutable_words']['i_secondaryProxy'],16),int(capture.PROXY,16))

    def test_metadata_immutable_placeholders_and_layout_mutations_fail(self):
        out=json.loads(self.raw)
        for kind in ['metadata','overlap','length','placeholder','layout']:
            changed=copy.deepcopy(out);c=changed['contracts'][builder.SOURCE][builder.CONTRACT];b=c['evm']['deployedBytecode'];refs=next(iter(b['immutableReferences'].values()))
            if kind=='metadata':b['object']=b['object'][:-2]+('00' if b['object'][-2:]!='00' else '01')
            elif kind=='overlap':refs.append(copy.deepcopy(refs[0]))
            elif kind=='length':refs[0]['length']=31
            elif kind=='placeholder':
                i=refs[0]['start']*2;b['object']=b['object'][:i]+'01'+b['object'][i+2:]
            else:next(x for x in c['storageLayout']['storage'] if x['label']=='s_transmissions')['slot']='18'
            with self.assertRaises(ValueError):builder.audit(self.value,identity.encoded(changed),self.history)
        v=copy.deepcopy(self.value);v['sources'][builder.SOURCE]['content']+='\n'
        with self.assertRaises(ValueError):builder.audit(v,self.raw,self.history)

    def test_slot_helper_vectors_and_word_bounds(self):
        for v in self.fixture['slot_vectors']:self.assertEqual(capture.word_pair_slot(int(v['key']),int(v['root'])),v['slot'])
        old=identity.read_json(builder.feed.oracle.DIRECTORY/'synthetic/atoken/models.json')
        self.assertEqual(int(capture.word_pair_slot(0,0),16),int(old['base_currency_slot']))
        for value in [-1,2**256,True,'1']:
            with self.assertRaises(ValueError):capture.word_pair_slot(value,17)
            with self.assertRaises(ValueError):capture.word_pair_slot(1,value)

    def test_both_full_cli_examples_preserve_all_effects_with_real_dual_code(self):
        prior=identity.read_json(identity.MODULE/'fixtures/aave_weth_feed_execution.json')
        for n,c in prior['contracts'].items():self.assertEqual(c,self.fixture['contracts'][n])
        self.assertTrue(self.fixture['weth_aggregator_runtime_executed']);self.assertTrue(self.fixture['round_selection_executed'])
        for k in ['usdc_feed_runtime_executed','feed_state_authenticated','price_freshness_verified','historical_state_authenticated','complete_liquidation_verified','activation_allowed']:
            self.assertFalse(self.fixture[k])
        for mode,e in self.examples.items():
            out=self.output(self.cli(e['input']));self.assertEqual(out,e['output']);self.same(out,identity.read_json(builder.feed.DIRECTORY/'synthetic'/mode/'output.json'))
            self.assertEqual(self.acct(e['input'])['runtime_code'],self.fixture['contracts']['DualAggregator']['runtime_code'])
            self.assertEqual((len(out['output'])-2)//64,47)

    def test_nine_observed_price_path_cli_reads_match_retained_results_without_authentication(self):
        paths=sorted((EVIDENCE/'observed-reads').iterdir());self.assertEqual(len(paths),9)
        for p in paths:
            data=identity.read_json(p/'input.json');out=self.output(self.cli(data));self.assertEqual(out,identity.read_json(p/'output.json'))
            self.assertEqual(out['status'],'success');self.assertFalse(out['canonical_state_authenticated']);self.assertEqual(data['snapshot']['kind'],'synthetic_fixture')
            self.assertEqual(out['logs'],[]);self.assertTrue(all(not a['storage'] for a in out['account_deltas']))
            index=int(p.name[:3]);h=self.history[index]
            if p.name.endswith('direct_round'):self.assertEqual(out['output'],h['direct_round_data'])
            elif p.name.endswith('oracle'):self.assertEqual(int(out['output'],16),capture.decode_round(h['secondary_round_data'])[1])

    def test_strict_cutoff_boundary_preserves_complete_composition(self):
        for e in self.examples.values():
            for age in [59,60,61]:
                d=copy.deepcopy(e['input']);now=d['snapshot']['timestamp'];price=10**11
                self.round(d,e,99,17 if age>60 else price,now-age);self.round(d,e,100,price if age>60 else 17,now-61)
                self.same(self.output(self.cli(d)),e['output'])

    def test_search_bound_includes_twentieth_but_avoids_missing_twenty_first_round(self):
        e=self.examples['atoken']
        for qualifying in [100,81,None]:
            d=copy.deepcopy(e['input']);now=d['snapshot']['timestamp'];self.hot(d,100,7);self.round(d,e,7,12345,now-100)
            for n in range(81,101):self.round(d,e,n,12345 if n==qualifying else 17,now-61 if n==qualifying else now)
            self.assertNotIn(e['models']['round_slots']['80'],self.acct(d)['storage']);self.price_call(d)
            out=self.output(self.cli(d));self.assertEqual(out['status'],'success');self.assertEqual(int(out['output'],16),12345)

    def test_signed_extremes_fallback_missing_state_and_timestamp_overflow(self):
        for e in self.examples.values():
            for value in [0,-1,-2**191]:
                d=copy.deepcopy(e['input']);self.round(d,e,99,value,d['snapshot']['timestamp']-1)
                f=copy.deepcopy(e['models']['fallback_account']);d['snapshot']['accounts'].append(f)
                self.acct(d,capture.prior.prior.ORACLE)['storage']['1']=str(int(f['address'],16));self.same(self.output(self.cli(d)),e['output'])
            for slot in ['13','18',e['models']['round_slots']['99']]:
                d=copy.deepcopy(e['input']);self.acct(d)['storage'].pop(slot);r=self.cli(d);self.assertNotEqual(r.returncode,0);self.assertEqual(r.stdout,'')
            d=copy.deepcopy(e['input']);self.round(d,e,99,1,2**32-1);out=self.atomic(self.cli(d));self.assertEqual(out['output'],'0x4e487b71'+f'{17:064x}')
        d=copy.deepcopy(self.examples['atoken']['input']);self.round(d,self.examples['atoken'],99,2**191-1,d['snapshot']['timestamp']-1);self.price_call(d)
        self.assertEqual(int(self.output(self.cli(d))['output'],16),2**191-1)

    def test_same_block_primary_filter_and_late_usdc_failure(self):
        e=self.examples['atoken'];d=copy.deepcopy(e['input']);now=d['snapshot']['timestamp'];self.hot(d,100,100,True)
        self.round(d,e,100,222,now);self.round(d,e,99,111,now-1);self.price_call(d);self.assertEqual(int(self.output(self.cli(d))['output'],16),222)
        d['call'].update(to=capture.AGGREGATOR,calldata='0x50d25bcd');self.assertEqual(int(self.output(self.cli(d))['output'],16),111)
        d['snapshot']['timestamp']+=1;self.assertEqual(int(self.output(self.cli(d))['output'],16),222)
        for e in self.examples.values():
            d=copy.deepcopy(e['input']);self.acct(d,capture.prior.prior.ASSETS[0])['storage']['1']=str(1<<160);out=self.atomic(self.cli(d));self.assertIn(b'Pausable: paused'.hex(),out['output'])


if __name__=='__main__':unittest.main()
