"""WETH observed-runtime identity, explicit metadata gap and composed burn replay."""
import copy
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import build_aave_underlying_execution as builder
identity=builder.identity
capture=builder.capture
EVIDENCE=builder.DIRECTORY
POOL='0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2'
ATOKEN=capture.ATOKEN


class UnderlyingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source,cls.weth_input=builder.weth_input();cls.weth_raw=gzip.decompress((EVIDENCE/'compiler/weth-output.json.gz').read_bytes());cls.weth_output=json.loads(cls.weth_raw);cls.history=capture.replay();cls.fixture=identity.read_json(identity.MODULE/'fixtures/aave_underlying_execution.json');cls.harness_input=identity.read_json(EVIDENCE/'compiler/harness-input.json.gz');cls.harness_raw=gzip.decompress((EVIDENCE/'compiler/harness-output.json.gz').read_bytes())

    def test_compilers_original_sources_and_settings_are_bound(self):
        self.assertEqual(self.weth_input,identity.read_json(EVIDENCE/'compiler/weth-input.json.gz'))
        self.assertEqual(self.weth_input['sources'],self.source['sources']);settings=copy.deepcopy(self.weth_input['settings']);settings.pop('outputSelection');self.assertEqual(settings,self.source['compilation']['compilerSettings'])
        original=identity.read_json(identity.EVIDENCE/'source.json.gz');identity.verify_provenance(original)
        self.assertEqual({k:v for k,v in self.harness_input['sources'].items() if k!=builder.NAME},original['sources'])
        left=copy.deepcopy(self.harness_input['settings']);right=identity.compilation_input(original)['settings'];left.pop('outputSelection');right.pop('outputSelection');self.assertEqual(left,right)
        self.assertEqual(self.fixture['weth_compiler_sha256'],builder.WETH_COMPILER_SHA);self.assertEqual(self.fixture['weth_compiler_output_sha256'],identity.sha(self.weth_raw));self.assertEqual(self.fixture['compiler_output_sha256'],identity.sha(self.harness_raw))

    def test_complete_weth_runtime_is_observed_while_metadata_mismatch_remains_explicit(self):
        w=builder.audit_weth(self.source,self.weth_output,self.history);self.assertEqual(w,self.fixture['contracts']['WETH9'])
        self.assertFalse(w['full_runtime_recompiled']);self.assertFalse(w['metadata_hash_equal']);self.assertTrue(w['executable_prefix_equal']);self.assertEqual(w['executable_prefix_bytes'],3081)
        compiled=bytes.fromhex(self.weth_output['contracts']['WETH9.sol']['WETH9']['evm']['deployedBytecode']['object']);observed=bytes.fromhex(w['runtime_code'][2:]);self.assertEqual(len(observed),3124)
        self.assertEqual([i for i,(a,b) in enumerate(zip(compiled,observed)) if a!=b],list(range(3090,3122)))
        for h in self.history:self.assertEqual(h['runtime_code'],w['runtime_code'])
        self.assertEqual(sum(len(h['records']) for h in self.history),66)
        self.assertEqual([h['block']['number'] for h in self.history],list(identity.BLOCKS))

    def test_runtime_body_footer_and_declaration_mutations_are_rejected(self):
        for kind in ['body','footer','layout']:
            output=copy.deepcopy(self.weth_output)
            if kind=='layout':
                contract=next(n for n in output['sources']['WETH9.sol']['ast']['nodes'] if n.get('nodeType')=='ContractDefinition');node=next(n for n in contract['nodes'] if n.get('name')=='balanceOf' and n.get('nodeType')=='VariableDeclaration');node['name']='other'
            else:
                code=output['contracts']['WETH9.sol']['WETH9']['evm']['deployedBytecode'];chars=list(code['object']);i=0 if kind=='body' else 3100*2;chars[i]='1' if chars[i]!='1' else '2';code['object']=''.join(chars)
            with self.assertRaises(ValueError):builder.audit_weth(self.source,output,self.history)
        for kind in ['runtime','slot','block']:
            history=copy.deepcopy(self.history)
            if kind=='runtime':history[0]['runtime_code']='0x00'
            elif kind=='slot':history[0]['underlying_slot_word']='0x'+'00'*32
            else:history[0]['block']['number']+=1
            with self.assertRaises(ValueError):builder.audit_weth(self.source,self.weth_output,history)

    def test_read_only_guard_rejects_write_foreign_asset_and_unpinned_reads(self):
        provider=next(iter(capture.PROVIDERS));pin={'blockHash':self.history[0]['block']['hash'],'requireCanonical':True}
        for method,args in [('eth_sendRawTransaction',['0x']),('eth_call',[{},pin]),('eth_getCode',[capture.WETH,'latest']),('eth_getCode',[ATOKEN,pin]),('eth_getStorageAt',[ATOKEN,'0x0',pin]),('eth_getStorageAt',[ATOKEN,'0x3d',{**pin,'requireCanonical':False}])]:
            with self.assertRaises(ValueError):capture.validate(provider,method,args)

    def replay_mutation(self,kind):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'public';shutil.copytree(EVIDENCE/'public',directory);p=directory/'weth-000.json';v=identity.read_json(p);rows=v['records']
            if kind=='chain':rows[0]['response']['result']='0x2'
            elif kind=='id':rows[0]['response']['id']+=1
            elif kind=='finality':rows[1]['response']['result']['number']='0x1'
            elif kind=='missing':rows.pop()
            elif kind=='header':rows[-1]['response']['result']['hash']='0x'+'11'*32
            elif kind=='provider':rows[0]['provider_id']='foreign'
            elif kind=='code':next(r for r in rows if r['request']['method']=='eth_getCode')['response']['result']='0x00'
            else:next(r for r in rows if r['request']['method']=='eth_getStorageAt')['request']['params'][-1]['requireCanonical']=False
            p.write_bytes(identity.encoded(v));mp=directory/'manifest.json';m=identity.read_json(mp);m['observations'][0]['sha256']=identity.sha(p.read_bytes());mp.write_bytes(identity.encoded(m))
            with self.assertRaises((ValueError,StopIteration)):capture.replay(directory)

    def test_rehashed_capture_chain_id_pin_and_provider_changes_are_rejected(self):
        for kind in ['chain','id','pin','provider']:self.replay_mutation(kind)

    def test_rehashed_capture_missing_reads_finality_headers_and_code_disagreement_are_rejected(self):
        for kind in ['missing','finality','header','code']:self.replay_mutation(kind)

    def test_fixture_uses_original_internal_burn_and_observed_weth_with_synthetic_state(self):
        self.assertEqual(builder.fixture(self.harness_input,self.harness_raw,self.weth_raw),self.fixture)
        value,harness,segments=builder.harness_input();self.assertEqual(value,self.harness_input);self.assertEqual(harness,(identity.MODULE/builder.NAME).read_text());self.assertEqual(segments,self.fixture['extracted_segments'])
        self.assertIn('LiquidationLogic._burnCollateralATokens(collateralReserve, params, vars);',harness)
        self.assertNotIn('function _burnCollateralATokens',harness)
        self.assertTrue(self.fixture['underlying_transfer_executed']);self.assertTrue(self.fixture['receive_underlying_only']);self.assertFalse(self.fixture['receive_atoken_only']);self.assertFalse(self.fixture['weth_full_source_runtime_match']);self.assertFalse(self.fixture['initial_health_validation_executed']);self.assertFalse(self.fixture['historical_state_authenticated'])
        for field in ['sources','settings']:
            bad=copy.deepcopy(self.harness_input)
            if field=='sources':bad[field][builder.NAME]['content']+='\n'
            else:bad[field]['optimizer']['runs']+=1
            with self.assertRaises(ValueError):builder.fixture(bad,self.harness_raw,self.weth_raw)

    def test_original_weth_declaration_order_and_underlying_slot_are_not_fabricated_compiler_layout(self):
        ast=self.weth_output['sources']['WETH9.sol']['ast'];contract=next(n for n in ast['nodes'] if n.get('nodeType')=='ContractDefinition')
        names=[n['name'] for n in contract['nodes'] if n.get('nodeType')=='VariableDeclaration' and n.get('stateVariable')];self.assertEqual(names,['name','symbol','decimals','balanceOf','allowance']);self.assertEqual(contract['baseContracts'],[])
        self.assertNotIn('storage_layout',self.fixture['contracts']['WETH9']);self.assertEqual(self.fixture['contracts']['WETH9']['balance_mapping_slot'],3)
        layout=self.fixture['contracts']['ATokenInstance']['storage_layout'];field=next(s for s in layout['storage'] if s['label']=='_underlyingAsset');self.assertEqual((field['slot'],field['offset']),('61',0))
        for h in self.history:self.assertEqual(int(h['underlying_slot_word'],16),int(capture.WETH,16))

    def run_cli(self,data):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json';p.write_text(json.dumps(data));return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'],'simulate','--input',str(p)],capture_output=True,text=True)

    def test_closed_example_replays_all_words_events_and_storage_through_real_cli(self):
        data=identity.read_json(EVIDENCE/'synthetic/input.json');expected=identity.read_json(EVIDENCE/'synthetic/output.json');result=self.run_cli(data);self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout),expected)
        words=[int(expected['output'][i:i+64],16) for i in range(2,len(expected['output']),64)];self.assertEqual(len(words),24);self.assertEqual(words[10:14],[66,20,14,973]);self.assertEqual(words[17:20],[10,0,960]);self.assertEqual(words[22:],[960,53]);self.assertEqual(len(expected['logs']),14);self.assertEqual(sum(len(d['storage']) for d in expected['account_deltas']),21)
        self.assertFalse(expected['canonical_state_authenticated']);a=next(a for a in data['snapshot']['accounts'] if a['address']==capture.WETH);self.assertEqual(a['runtime_code'],self.fixture['contracts']['WETH9']['runtime_code'])
        self.assertEqual(data['snapshot']['kind'],'synthetic_fixture')

    def test_actual_weth_getter_confirms_supplied_slot_and_direct_insufficient_transfer_reverts(self):
        data=identity.read_json(EVIDENCE/'synthetic/input.json');data['call'].update(to=capture.WETH,calldata='0x70a08231'+f'{int(ATOKEN,16):064x}')
        result=self.run_cli(data);self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(int(json.loads(result.stdout)['output'],16),1000)
        data['call']['calldata']='0xa9059cbb'+f'{int(ATOKEN,16):064x}'+f'{14:064x}'
        result=self.run_cli(data);self.assertEqual(result.returncode,0,result.stderr);out=json.loads(result.stdout);self.assertEqual(out['status'],'revert');self.assertEqual(out['output'],'0x');self.assertEqual(out['logs'],[]);self.assertTrue(all(not a['storage'] for a in out['account_deltas']))

    def test_cli_rejects_missing_weth_account_balance_and_bad_code_hash(self):
        original=identity.read_json(EVIDENCE/'synthetic/input.json')
        for kind in ['account','slot','hash']:
            data=copy.deepcopy(original);a=next(a for a in data['snapshot']['accounts'] if a['address']==capture.WETH)
            if kind=='account':data['snapshot']['accounts']=[a for a in data['snapshot']['accounts'] if a['address']!=capture.WETH]
            elif kind=='slot':a['storage'].pop(next(k for k,v in a['storage'].items() if v=='1000'))
            else:a['code_hash']='0x'+'00'*32
            result=self.run_cli(data);self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,'')

    def test_cli_late_treasury_failure_reverts_weth_and_all_previous_storage(self):
        data=identity.read_json(EVIDENCE/'synthetic/input.json');token=next(a for a in data['snapshot']['accounts'] if a['address']==ATOKEN);slot=next(k for k,v in token['storage'].items() if int(v)==7+(2<<120)+(10**27<<128));token['storage'][slot]=str((2**120-1)+(2<<120)+(10**27<<128))
        result=self.run_cli(data);self.assertEqual(result.returncode,0,result.stderr);out=json.loads(result.stdout);self.assertEqual(out['status'],'revert');self.assertEqual(out['output'],'0x4e487b71'+f'{0x11:064x}');self.assertEqual(out['logs'],[]);self.assertTrue(all(not a['storage'] for a in out['account_deltas']))


if __name__=='__main__':unittest.main()
