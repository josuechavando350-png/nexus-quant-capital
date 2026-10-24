import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import aave_runtime_identity as identity
import build_aave_reserve_harness as harness


class AaveReserveTests(unittest.TestCase):
    def test_original_functions_and_compiler_artifacts_are_bound_without_source_edits(self):
        source=identity.read_json(identity.EVIDENCE/'source.json.gz')
        identity.verify_provenance(source)
        directory=identity.MODULE/'evidence/aave-reserve-20261022/compiler'
        inp=identity.read_json(directory/'input.json.gz')
        out=identity.read_json(directory/'output.json.gz')
        fixture=identity.read_json(identity.MODULE/'fixtures/aave_reserve_harness.json')
        self.assertEqual({k:v for k,v in inp['sources'].items() if k!=harness.NAME},source['sources'])
        self.assertEqual(inp['sources'][harness.NAME]['content'],(identity.MODULE/harness.NAME).read_text())
        expected=identity.compilation_input(source)['settings'];expected.pop('outputSelection')
        actual=copy.deepcopy(inp['settings']);actual.pop('outputSelection');self.assertEqual(actual,expected)
        self.assertEqual(fixture['original_sources'],{k:identity.sha(v['content'].encode()) for k,v in source['sources'].items()})
        for name in ['input','output']:
            self.assertEqual(identity.sha(gzip.decompress((directory/(name+'.json.gz')).read_bytes())),fixture['compiler_'+name+'_sha256'])
        contract=out['contracts'][harness.NAME]['AaveReserveHarness']
        self.assertEqual('0x'+contract['evm']['deployedBytecode']['object'],fixture['runtime_code'])
        self.assertEqual('0x'+contract['evm']['methodIdentifiers'][harness.SIGNATURE],fixture['selector'])
        self.assertEqual(fixture['storage_layout'],contract['storageLayout'])
        self.assertEqual(fixture['compiler_sha256'],identity.COMPILER_SHA)
        self.assertEqual(identity.sha((identity.MODULE/harness.NAME).read_bytes()),fixture['harness_source_sha256'])
        self.assertTrue(fixture['token_supply_is_synthetic'])
        self.assertFalse(fixture['executable_eligibility_verified'])

    def test_cli_exposes_floor_ceil_and_preserves_rejection_vs_bad_input(self):
        ray=10**27
        data=dict(liquidity_index_ray=str(ray+1),variable_borrow_index_ray=str(ray+1),
          liquidity_rate_ray='0',variable_borrow_rate_ray='0',accrued_to_treasury_scaled='0',
          last_update_timestamp=100,reserve_factor_bps=1000,total_scaled_variable_debt='1',
          user_scaled_collateral='1',user_scaled_variable_debt='1',timestamp=100)
        binary=os.environ['NQC_MINER_TEST_BINARY']
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'reserve.json'
            def run(value):
                path.write_text(json.dumps(value))
                return subprocess.run([binary,'project-aave-reserve','--input',str(path)],capture_output=True,text=True)
            result=run(data);self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(result.stdout)
            self.assertTrue(report['projection_passed'])
            self.assertEqual(report['projected']['user_collateral_balance'],'1')
            self.assertEqual(report['projected']['user_variable_debt_balance'],'2')
            for flag in ['input_state_authenticated','token_implementation_verified','executable_eligibility_verified','activation_allowed']:
                self.assertFalse(report[flag])
            for key,value in [('liquidity_index_ray','01'),('timestamp',2**40),('reserve_factor_bps',65536),
                              ('liquidity_rate_ray',str(2**128)),('activation_allowed',True)]:
                bad=data.copy();bad[key]=value;self.assertNotEqual(run(bad).returncode,0)
            bad=data.copy();del bad['total_scaled_variable_debt'];self.assertNotEqual(run(bad).returncode,0)
            bad=data.copy();bad['timestamp']=99
            result=run(bad);self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(result.stdout)
            self.assertFalse(report['projection_passed']);self.assertIsNone(report['projected'])
            self.assertEqual(report['revert_data'],'0x4e487b71'+f'{0x11:064x}')

if __name__=='__main__':
    unittest.main()
