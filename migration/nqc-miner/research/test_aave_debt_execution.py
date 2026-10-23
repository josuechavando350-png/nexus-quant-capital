"""Bind combined execution to original code, compiler layouts and the actual CLI."""
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import aave_runtime_identity as identity
import audit_aave_dependencies as dependencies
import build_aave_debt_execution as builder

EVIDENCE = identity.MODULE/'evidence/aave-debt-execution-20261023'


class DebtExecutionTests(unittest.TestCase):
    def test_original_pool_source_and_wrapper_compilation_are_bound(self):
        fixture=identity.read_json(identity.MODULE/'fixtures/aave_debt_execution.json')
        source=identity.read_json(identity.EVIDENCE/'source.json.gz')
        value=identity.read_json(EVIDENCE/'compiler/input.json.gz')
        output=identity.read_json(EVIDENCE/'compiler/output.json.gz')
        self.assertEqual({k:v for k,v in value['sources'].items() if k!=builder.NAME},source['sources'])
        self.assertEqual(value['sources'][builder.NAME]['content'],(identity.MODULE/builder.NAME).read_text())
        expected=identity.compilation_input(source)['settings'];expected.pop('outputSelection')
        actual=copy.deepcopy(value['settings']);actual.pop('outputSelection');self.assertEqual(actual,expected)
        for name in ['input','output']:
            self.assertEqual(identity.sha(gzip.decompress((EVIDENCE/'compiler'/(name+'.json.gz')).read_bytes())),fixture['compiler_'+name+'_sha256'])
        self.assertEqual(fixture['compiler_sha256'],identity.COMPILER_SHA)
        self.assertEqual(fixture['harness_source_sha256'],identity.sha((identity.MODULE/builder.NAME).read_bytes()))
        for name in ['AaveDebtExecutionHarness','SyntheticDebtProxy','RewardsProbe']:
            c=output['contracts'][builder.NAME][name];f=fixture['contracts'][name]
            self.assertEqual(f['runtime_code'],'0x'+c['evm']['deployedBytecode']['object'])
            self.assertEqual(f['runtime_sha256'],identity.sha(bytes.fromhex(f['runtime_code'][2:])))
            self.assertEqual(f['storage_layout'],c['storageLayout'])
            self.assertEqual(f['selectors'],c['evm']['methodIdentifiers'])
        for flag in ['token_burn_outcome_supplied','rate_quote_supplied','historical_state_authenticated','executable_eligibility_verified','activation_allowed']:
            self.assertFalse(fixture[flag])
        for flag in ['rewards_controller_synthetic','proxy_synthetic','pool_entrypoint_synthetic']:
            self.assertTrue(fixture[flag])

    def test_actual_token_and_strategy_code_and_packed_storage_match_audited_outputs(self):
        fixture=identity.read_json(identity.MODULE/'fixtures/aave_debt_execution.json')
        profiles,_,outputs=dependencies.retained_inputs()
        for name,address in [('VariableDebtTokenInstance',builder.TOKEN),('DefaultReserveInterestRateStrategyV2',builder.STRATEGY)]:
            p=next(p for p in profiles if p['address']==address)
            runtime,substitutions=dependencies.render_runtime(outputs[address],p)
            f=fixture['contracts'][name];self.assertEqual(f['runtime_code'],runtime)
            self.assertEqual(f['substitutions'],substitutions)
            self.assertEqual(f['compiler_output_sha256'],p['compiler_output_sha256'])
            path,contract=p['target'].rsplit(':',1)
            self.assertEqual(f['storage_layout'],outputs[address]['contracts'][path][contract]['storageLayout'])
        layout=fixture['contracts']['VariableDebtTokenInstance']['storage_layout']
        fields={v['label']:v for v in layout['storage']}
        self.assertEqual(fields['_userState']['slot'],'56');self.assertEqual(fields['_totalSupply']['slot'],'58')
        struct=layout['types'][layout['types'][fields['_userState']['type']]['value']]
        self.assertEqual([(m['label'],m['offset'],m['type']) for m in struct['members']],[('balance',0,'t_uint120'),('delegationMode',15,'t_enum(DelegationMode)5317'),('additionalData',16,'t_uint128')])
        layout=fixture['contracts']['DefaultReserveInterestRateStrategyV2']['storage_layout']
        field=layout['storage'][0];self.assertEqual((field['label'],field['slot']),('_interestRateData','0'))
        struct=layout['types'][layout['types'][field['type']]['value']]
        self.assertEqual([(m['label'],m['offset']) for m in struct['members']],[('optimalUsageRatio',0),('baseVariableBorrowRate',2),('variableRateSlope1',6),('variableRateSlope2',10)])

    def run_cli(self,data):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json';p.write_text(json.dumps(data))
            return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'],'simulate','--input',str(p)],capture_output=True,text=True)

    def test_retained_combined_example_reexecutes_exactly_through_cli(self):
        data=identity.read_json(EVIDENCE/'synthetic/input.json')
        expected=identity.read_json(EVIDENCE/'synthetic/output.json')
        self.assertEqual(data['snapshot']['kind'],'synthetic_fixture')
        result=self.run_cli(data);self.assertEqual(result.returncode,0,result.stderr)
        actual=json.loads(result.stdout);self.assertEqual(actual,expected)
        self.assertEqual(actual['status'],'success');self.assertFalse(actual['canonical_state_authenticated'])
        self.assertEqual(len(actual['logs']),4)
        contracts=identity.read_json(identity.MODULE/'fixtures/aave_debt_execution.json')['contracts']
        codes={c['runtime_code'] for c in contracts.values()}
        self.assertTrue(codes <= {a['runtime_code'] for a in data['snapshot']['accounts']})

    def test_cli_rejects_missing_dependency_or_slot_and_mismatched_code_hash(self):
        original=identity.read_json(EVIDENCE/'synthetic/input.json')
        for failure in ['dependency','slot','code']:
            data=copy.deepcopy(original)
            if failure=='dependency':
                data['snapshot']['accounts']=[a for a in data['snapshot']['accounts'] if a['address']!=builder.TOKEN]
            else:
                token=next(a for a in data['snapshot']['accounts'] if a['address']=='0x72e95b8931767c79ba4eee721354d6e99a61d004')
                if failure=='slot':token['storage'].pop('58')
                else:token['runtime_code']='0x00'
            result=self.run_cli(data)
            self.assertNotEqual(result.returncode,0,failure)
            self.assertEqual(result.stdout,'')


if __name__=='__main__':
    unittest.main()
