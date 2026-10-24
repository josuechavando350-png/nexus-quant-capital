"""Observed AaveOracle identity and execution; feed answers remain synthetic."""
import copy
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import build_aave_oracle_execution as builder

identity=builder.identity
capture=builder.capture
EVIDENCE=builder.DIRECTORY


class OracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value=identity.read_json(EVIDENCE/'compiler/input.json.gz')
        cls.raw=gzip.decompress((EVIDENCE/'compiler/output.json.gz').read_bytes())
        cls.ov=identity.read_json(EVIDENCE/'compiler/oracle-input.json.gz')
        cls.oraw=gzip.decompress((EVIDENCE/'compiler/oracle-output.json.gz').read_bytes())
        cls.fixture=identity.read_json(identity.MODULE/'fixtures/aave_oracle_execution.json')
        cls.history=capture.replay()
        cls.examples={m:{n:identity.read_json(EVIDENCE/'synthetic'/m/(n+'.json')) for n in ['input','output','models']} for m in ['atoken','underlying']}

    def cli(self,data):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json'; p.write_text(json.dumps(data))
            return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'],'simulate','--input',str(p)],capture_output=True,text=True)

    def output(self,result):
        self.assertEqual(result.returncode,0,result.stderr); return json.loads(result.stdout)

    def atomic(self,result,error=None):
        out=self.output(result); self.assertEqual(out['status'],'revert'); self.assertEqual(out['logs'],[])
        self.assertTrue(all(not a['storage'] for a in out['account_deltas']))
        if error is not None: self.assertEqual(out['output'],error)
        return out

    def acct(self,data,address): return next(a for a in data['snapshot']['accounts'] if a['address']==address)

    def add_fallback(self,data,example):
        fallback=copy.deepcopy(example['models']['fallback_account']); data['snapshot']['accounts'].append(fallback)
        self.acct(data,capture.ORACLE)['storage']['1']=str(int(fallback['address'],16)); return fallback

    def same_effects(self,out,reference):
        self.assertEqual(out['status'],'success'); self.assertEqual(out['output'],reference['output']); self.assertEqual(out['logs'],reference['logs'])
        def changed(v): return {a['address']:a['storage'] for a in v['account_deltas'] if a['storage']}
        self.assertEqual(changed(out),changed(reference))

    def test_capture_scope_rejects_mutations_latest_pins_and_foreign_getters(self):
        provider=next(iter(capture.PROVIDERS)); pin={'blockHash':'0x'+'11'*32,'requireCanonical':True}
        for method,args in [('eth_sendRawTransaction',['0x00']),('eth_call',[{'to':capture.ORACLE,'data':'0x170aee73'+'00'*32},pin]),
            ('eth_call',[{'to':capture.ORACLE,'data':capture.calldata('base')},'latest']),('eth_getStorageAt',[capture.ORACLE,'0x2',pin]),
            ('eth_getCode',[capture.ORACLE,{'blockHash':pin['blockHash'],'requireCanonical':False}])]:
            with self.assertRaises(ValueError): capture.validate(provider,method,args)
        with self.assertRaises(ValueError): capture.address_word('0x'+'ff'*32)

    def test_three_blocks_and_two_providers_replay_exact_identity_routing_and_positive_answers(self):
        self.assertEqual(len(self.history),3); self.assertEqual(sum(len(h['records']) for h in self.history),144)
        self.assertEqual([h['block']['number'] for h in self.history],list(identity.BLOCKS))
        for h in self.history:
            self.assertEqual({r['provider_id'] for r in h['records']},set(capture.PROVIDERS))
            self.assertEqual(h['runtime_code'],self.fixture['contracts']['AaveOracle']['runtime_code'])
            self.assertEqual(h['fallback_word'],'0x'+'00'*32)
            self.assertEqual([f['asset'] for f in h['feeds']],list(capture.ASSETS))
            for f in h['feeds']: self.assertEqual(f['answer_word'],f['price_word']); self.assertGreater(int(f['price_word'],16),0)
            self.assertFalse(h['historical_state_authenticated']); self.assertFalse(h['price_freshness_verified'])

    def test_capture_semantic_mutations_fail_even_when_file_hash_is_rewritten(self):
        for kind in ['runtime','header','pin','id']:
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'public'; shutil.copytree(EVIDENCE/'public',p)
                path=p/'oracle-000.json'; h=identity.read_json(path)
                rows=h['records']
                if kind=='runtime':
                    r=next(r for r in rows if r['provider_id']==list(capture.PROVIDERS)[1] and r['request']['method']=='eth_getCode' and r['request']['params'][0]==capture.ORACLE)
                    r['response']['result']='0x00'
                elif kind=='header':
                    r=next(r for r in rows if r['request']['method']=='eth_getBlockByNumber' and r['request']['params'][0]==hex(h['block']['number']))
                    r['response']['result']['hash']='0x'+'22'*32
                elif kind=='pin': next(r for r in rows if r['request']['method']=='eth_call')['request']['params'][-1]['requireCanonical']=False
                else: rows[0]['response']['id']+=1
                path.write_bytes(identity.encoded(h)); manifest=identity.read_json(p/'manifest.json'); manifest['observations'][0]['sha256']=identity.sha(path.read_bytes())
                (p/'manifest.json').write_bytes(identity.encoded(manifest))
                with self.assertRaises(ValueError): capture.replay(p)

    def test_fixture_rebuild_and_original_oracle_sources_settings_and_selectors_are_bound(self):
        self.assertEqual(builder.fixture(self.value,self.raw,self.ov,self.oraw),self.fixture)
        s,v=builder.oracle_input(); self.assertEqual(v,self.ov)
        self.assertEqual(v['sources'],s['sources']); settings=copy.deepcopy(v['settings']); settings.pop('outputSelection')
        self.assertEqual(settings,s['compilation']['compilerSettings']); self.assertEqual(settings['evmVersion'],'berlin')
        o=self.fixture['contracts']['AaveOracle']; self.assertEqual(o['runtime_bytes'],3405)
        self.assertTrue(o['full_runtime_recompiled_match']); self.assertTrue(o['metadata_bytes_compared']); self.assertFalse(o['canonical_code_proof_verified'])
        self.assertEqual({e['name'] for e in o['immutable_substitutions']},{'ADDRESSES_PROVIDER','BASE_CURRENCY','BASE_CURRENCY_UNIT'})
        self.assertEqual([(v['label'],v['slot']) for v in o['storage_layout']['storage']],[('assetsSources','0'),('_fallbackOracle','1')])

    def test_metadata_immutable_ranges_and_input_edits_cannot_masquerade_as_exact_runtime(self):
        out=json.loads(self.oraw)
        for kind in ['metadata','length','overlap']:
            mutated=copy.deepcopy(out); code=mutated['contracts'][builder.ORACLE_PATH]['AaveOracle']['evm']['deployedBytecode']
            if kind=='metadata': code['object']=code['object'][:-2]+('00' if code['object'][-2:]!='00' else '01')
            else:
                refs=next(iter(code['immutableReferences'].values()))
                if kind=='length': refs[0]['length']=31
                else: refs.append(copy.deepcopy(refs[0]))
            with self.assertRaises(ValueError): builder.audit_oracle(self.ov,identity.encoded(mutated),self.history)
        changed=copy.deepcopy(self.ov); changed['sources'][builder.ORACLE_PATH]['content']+='\n'
        with self.assertRaises(ValueError): builder.audit_oracle(changed,self.oraw,self.history)

    def test_harness_and_inherited_dependencies_keep_feed_and_state_limits_explicit(self):
        value,harness,_=builder.harness_input(); self.assertEqual(value,self.value); self.assertEqual(harness,(identity.MODULE/builder.NAME).read_text())
        prior=identity.read_json(identity.MODULE/'fixtures/aave_account_execution.json')
        for n,c in prior['contracts'].items():
            if n not in [builder.account.CONTRACT,builder.account.ORACLE_CONTRACT]: self.assertEqual(c,self.fixture['contracts'][n])
        self.assertNotIn('contract SyntheticAccountOracle',harness); self.assertNotIn(builder.account.ORACLE_CONTRACT,self.fixture['contracts'])
        self.assertTrue(self.fixture['oracle_runtime_recompiled_match']); self.assertTrue(self.fixture['oracle_routing_observed'])
        self.assertEqual(self.fixture['feed_kind'],'synthetic_test_double')
        for k in ['oracle_state_authenticated','oracle_runtime_authenticated','observed_feed_runtime_executed','price_freshness_verified',
            'historical_state_authenticated','complete_liquidation_verified','activation_allowed']:
            self.assertFalse(self.fixture[k])

    def test_both_cli_examples_reproduce_full_state_logs_and_previous_account_outputs(self):
        for mode,example in self.examples.items():
            out=self.output(self.cli(example['input'])); self.assertEqual(out,example['output'])
            prior=identity.read_json(builder.account.DIRECTORY/'synthetic'/mode/'output.json'); self.same_effects(out,prior)
            self.assertEqual((len(out['output'])-2)//64,47); self.assertFalse(out['canonical_state_authenticated'])
            oracle=self.acct(example['input'],capture.ORACLE); self.assertEqual(oracle['runtime_code'],self.fixture['contracts']['AaveOracle']['runtime_code'])
            for f in self.history[0]['feeds']:
                feed=self.acct(example['input'],f['source']); self.assertNotEqual(identity.sha(bytes.fromhex(feed['runtime_code'][2:])),f['runtime_sha256'])

    def test_nonpositive_signed_answers_use_fallback_and_preserve_full_execution(self):
        for example in self.examples.values():
            for feed in example['models']['feed_addresses']:
                for value in [0,2**256-1,2**255]:
                    data=copy.deepcopy(example['input']); self.add_fallback(data,example)
                    self.acct(data,feed)['storage']['0']=str(value)
                    self.same_effects(self.output(self.cli(data)),example['output'])

    def test_positive_feed_skips_fallback_and_feed_revert_is_not_recovered(self):
        for example in self.examples.values():
            data=copy.deepcopy(example['input']); self.acct(data,capture.ORACLE)['storage'].pop('1')
            self.same_effects(self.output(self.cli(data)),example['output'])
            data=copy.deepcopy(example['input']); self.add_fallback(data,example)
            self.acct(data,example['models']['feed_addresses'][0])['storage']['1']='1'
            out=self.atomic(self.cli(data)); self.assertIn(b'synthetic feed blocked'.hex(),out['output'])

    def test_fallback_revert_and_missing_oracle_or_feed_state_fail_closed(self):
        for example in self.examples.values():
            data=copy.deepcopy(example['input']); fallback=self.add_fallback(data,example); fallback['storage']['1']='1'
            feed=example['models']['feed_addresses'][0]; self.acct(data,feed)['storage']['0']='0'
            out=self.atomic(self.cli(data)); self.assertIn(b'synthetic fallback blocked'.hex(),out['output'])
            for address in [capture.ORACLE,*example['models']['feed_addresses']]:
                data=copy.deepcopy(example['input']); data['snapshot']['accounts'].remove(self.acct(data,address))
                result=self.cli(data); self.assertNotEqual(result.returncode,0); self.assertEqual(result.stdout,'')
            data=copy.deepcopy(example['input']); self.acct(data,feed)['storage'].pop('0')
            result=self.cli(data); self.assertNotEqual(result.returncode,0); self.assertEqual(result.stdout,'')

    def test_original_base_currency_branch_returns_declared_unit_without_contract_changes(self):
        example=self.examples['atoken']; data=copy.deepcopy(example['input'])
        data['call']['to']=capture.ORACLE; data['call']['calldata']='0x'+self.fixture['contracts']['AaveOracle']['selectors']['getAssetPrice(address)']+'00'*32
        self.acct(data,capture.ORACLE)['storage'][example['models']['base_currency_slot']]='0'
        out=self.output(self.cli(data)); self.assertEqual(out['status'],'success'); self.assertEqual(out['output'],'0x'+f'{10**8:064x}')
        self.assertEqual(out['logs'],[]); self.assertTrue(all(not a['storage'] for a in out['account_deltas']))

    def test_late_usdc_pause_rolls_back_actual_oracle_composition(self):
        for example in self.examples.values():
            data=copy.deepcopy(example['input']); self.acct(data,capture.ASSETS[0])['storage']['1']=str(1<<160)
            out=self.atomic(self.cli(data)); self.assertIn(b'Pausable: paused'.hex(),out['output'])


if __name__=='__main__': unittest.main()
