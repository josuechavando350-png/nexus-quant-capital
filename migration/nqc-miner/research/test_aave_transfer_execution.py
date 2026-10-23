"""Bind actual aToken transfer composition to unchanged sources and CLI evidence."""
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import build_aave_transfer_execution as builder

identity = builder.identity
EVIDENCE = builder.DIRECTORY
ATOKEN = '0x4d5f47fa6a74757f35c14fd3a6ef8e3c9bc514e8'
IMPL = '0xadc45df3cf1584624c97338bef33363bf5b97ada'
TREASURY = '0x464c71f6c2f760dda6093dcb91c24c39e5d6e18c'
POOL = '0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2'


class TransferExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = identity.read_json(identity.MODULE / 'fixtures/aave_transfer_execution.json')
        cls.value = identity.read_json(EVIDENCE / 'compiler/input.json.gz')
        cls.raw = gzip.decompress((EVIDENCE / 'compiler/output.json.gz').read_bytes())

    def test_original_sources_compiler_settings_and_exact_excerpts_are_preserved(self):
        source = identity.read_json(identity.EVIDENCE / 'source.json.gz'); identity.verify_provenance(source)
        value, harness, segments = builder.compilation_input()
        self.assertEqual(self.value, value)
        self.assertEqual({k:v for k,v in value['sources'].items() if k != builder.NAME}, source['sources'])
        left = copy.deepcopy(value['settings']); right = identity.compilation_input(source)['settings']
        left.pop('outputSelection'); right.pop('outputSelection'); self.assertEqual(left,right)
        self.assertEqual(harness,(identity.MODULE / builder.NAME).read_text())
        self.assertEqual(segments,self.fixture['extracted_segments']); self.assertEqual(len(segments),4)
        self.assertIn('LiquidationLogic._burnDebtTokens(',harness)
        self.assertNotIn('function transferOnLiquidation(',harness)
        self.assertNotIn('suppliedPostBalance',harness)

    def test_fixture_regenerates_from_compiler_and_audited_real_dependencies(self):
        self.assertEqual(builder.fixture(self.value,self.raw),self.fixture)
        for key,data in [('compiler_input_sha256',identity.encoded(self.value)),('compiler_output_sha256',self.raw),('harness_source_sha256',(identity.MODULE / builder.NAME).read_bytes())]: self.assertEqual(identity.sha(data),self.fixture[key])
        self.assertEqual(self.fixture['compiler_sha256'],identity.COMPILER_SHA)
        old=builder.rewards.fixture()
        for name,c in old['contracts'].items():
            if name!='AaveDebtExecutionHarness': self.assertEqual(c,self.fixture['contracts'][name])
        self.assertNotIn('RewardsProbe',self.fixture['contracts'])
        for flag in ['post_liquidator_balance_supplied','atoken_transfer_outcomes_supplied','underlying_transfer_executed','historical_state_authenticated','executable_eligibility_verified','activation_allowed','initial_health_validation_executed']: self.assertFalse(self.fixture[flag])
        for flag in ['pool_entrypoint_synthetic','rewards_parameters_synthetic','liquidation_amounts_supplied','receive_atoken_only']: self.assertTrue(self.fixture[flag])

    def test_mutated_source_and_compilation_inputs_are_rejected(self):
        source=identity.read_json(identity.EVIDENCE / 'source.json.gz')
        source['sources'][builder.SOURCE_PATH]['content']+='\n'
        with self.assertRaises(ValueError): builder.extracted_harness(source)
        for kind in ['source','optimizer','compiler_target']:
            value=copy.deepcopy(self.value)
            if kind=='source': value['sources'][builder.NAME]['content']+='\n'
            elif kind=='optimizer': value['settings']['optimizer']['runs']+=1
            else: value['settings']['evmVersion']='berlin'
            with self.assertRaises(ValueError): builder.fixture(value,self.raw)

    def test_compiler_harness_runtime_selectors_and_layout_are_exact(self):
        out=json.loads(self.raw);c=out['contracts'][builder.NAME][builder.CONTRACT];f=self.fixture['contracts'][builder.CONTRACT]
        self.assertEqual(f['runtime_code'],'0x'+c['evm']['deployedBytecode']['object'])
        self.assertEqual(f['runtime_sha256'],identity.sha(bytes.fromhex(f['runtime_code'][2:])))
        self.assertEqual(f['selectors'],c['evm']['methodIdentifiers']);self.assertIn(builder.SIGNATURE,f['selectors'])
        self.assertEqual(f['storage_layout'],c['storageLayout'])
        self.assertEqual([(s['label'],s['slot']) for s in c['storageLayout']['storage']],[('debtReserve','0'),('borrowerConfig','10'),('collateralReserve','11')])
        layout=self.fixture['contracts']['ATokenInstance']['storage_layout']; fields={s['label']:s for s in layout['storage']}
        self.assertEqual((fields['_userState']['slot'],fields['_totalSupply']['slot']),('52','54'))
        members=layout['types'][layout['types'][fields['_userState']['type']]['value']]['members']
        self.assertEqual([(m['label'],m['offset']) for m in members],[('balance',0),('delegationMode',15),('additionalData',16)])
        values={s['value'] for s in self.fixture['contracts']['ATokenInstance']['substitutions'] if s['name']=='TREASURY'}
        self.assertEqual(values,{'0x'+'00'*12+TREASURY[2:]})

    def run_cli(self,data):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json';p.write_text(json.dumps(data))
            return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'],'simulate','--input',str(p)],capture_output=True,text=True)

    def test_full_transfer_example_reexecutes_exactly_through_real_cli(self):
        data=identity.read_json(EVIDENCE/'synthetic/input.json');expected=identity.read_json(EVIDENCE/'synthetic/output.json')
        result=self.run_cli(data);self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout),expected)
        self.assertEqual(expected['status'],'success');self.assertFalse(expected['canonical_state_authenticated'])
        self.assertEqual(data['snapshot']['kind'],'synthetic_fixture')
        words=[int(expected['output'][i:i+64],16) for i in range(2,len(expected['output']),64)]
        self.assertEqual(len(words),19)
        self.assertEqual(words[10:14],[66,47,14,1000]);self.assertEqual(words[17:],[10,0])
        self.assertEqual(words[14:17],[15*10**26]*3)
        self.assertEqual(len(expected['logs']),17)
        self.assertEqual(sum(len(d['storage']) for d in expected['account_deltas']),17)
        code={a['address']:a['runtime_code'] for a in data['snapshot']['accounts']}
        self.assertEqual(code[IMPL],self.fixture['contracts']['ATokenInstance']['runtime_code'])
        self.assertEqual(code[ATOKEN],self.fixture['contracts']['AuditedDebtProxy']['runtime_code'])
        self.assertEqual(code[POOL],self.fixture['contracts'][builder.CONTRACT]['runtime_code'])
        # The receive-aToken branch requires no underlying-token code/account.
        self.assertNotIn('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',code)

    def test_cli_rejects_missing_atoken_target_slot_and_code_hash_mismatch(self):
        original=identity.read_json(EVIDENCE/'synthetic/input.json')
        for kind in ['target','slot','hash']:
            data=copy.deepcopy(original);a=next(a for a in data['snapshot']['accounts'] if a['address']==ATOKEN)
            if kind=='target': data['snapshot']['accounts']=[a for a in data['snapshot']['accounts'] if a['address']!=IMPL]
            elif kind=='slot': a['storage'].pop('54')
            else:a['runtime_code']='0x00'
            result=self.run_cli(data);self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,'')

    def test_cli_capped_fee_uses_computed_post_transfer_balance(self):
        data=identity.read_json(EVIDENCE/'synthetic/input.json')
        call=data['call'];words=[call['calldata'][i:i+64] for i in range(10,len(call['calldata']),64)]
        words[12]=f'{148:064x}';words[13]=f'{2:064x}';call['calldata']=call['calldata'][:10]+''.join(words)
        result=self.run_cli(data);self.assertEqual(result.returncode,0,result.stderr);out=json.loads(result.stdout);self.assertEqual(out['status'],'success')
        result_words=[int(out['output'][i:i+64],16) for i in range(2,len(out['output']),64)]
        self.assertEqual(result_words[10:14],[0,119,8,1000]);self.assertEqual(result_words[17:],[1,1])
        self.assertEqual(result_words[2],115);self.assertEqual(result_words[3],219)

    def test_cli_late_fee_failure_rolls_back_all_contract_writes_and_logs(self):
        data=identity.read_json(EVIDENCE/'synthetic/input.json')
        # The explicit synthetic treasury word is identified by its initial balance,
        # delegation byte and previous index, independently of a guessed hash slot.
        token=next(a for a in data['snapshot']['accounts'] if a['address']==ATOKEN)
        original=7+(2<<120)+(10**27<<128)
        slots=[k for k,v in token['storage'].items() if int(v)==original];self.assertEqual(len(slots),1)
        token['storage'][slots[0]]=str((2**120-1)+(2<<120)+(10**27<<128))
        result=self.run_cli(data);self.assertEqual(result.returncode,0,result.stderr);out=json.loads(result.stdout)
        self.assertEqual(out['status'],'revert');self.assertEqual(out['logs'],[])
        self.assertTrue(all(not d['storage'] for d in out['account_deltas']))
        self.assertEqual(out['output'],'0x4e487b71'+f'{0x11:064x}')


if __name__=='__main__': unittest.main()
