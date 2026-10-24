import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import aave_runtime_identity as identity
import build_aave_amount_harness as harness


class AaveAmountsTests(unittest.TestCase):
    def test_reference_uses_pinned_original_segment_and_unchanged_imports(self):
        source=identity.read_json(identity.EVIDENCE/'source.json.gz')
        identity.verify_provenance(source)
        rendered,segments=harness.extracted_harness(source)
        self.assertEqual(rendered,(identity.MODULE/harness.NAME).read_text())
        fixture=identity.read_json(identity.MODULE/'fixtures/aave_amount_harness.json')
        self.assertEqual(fixture['extracted_segments'],segments)
        self.assertEqual(fixture['harness_source_sha256'],identity.sha(rendered.encode()))
        directory=identity.MODULE/'evidence/aave-amounts-20261022/compiler'
        inp=identity.read_json(directory/'input.json.gz')
        out=identity.read_json(directory/'output.json.gz')
        self.assertEqual({k:v for k,v in inp['sources'].items() if k != harness.NAME},source['sources'])
        self.assertEqual(inp['sources'][harness.NAME]['content'],rendered)
        expected=identity.compilation_input(source)['settings'];expected.pop('outputSelection')
        actual=copy.deepcopy(inp['settings']);actual.pop('outputSelection')
        self.assertEqual(expected,actual)
        self.assertEqual(fixture['original_sources'],{k:identity.sha(v['content'].encode()) for k,v in source['sources'].items()})
        for name in ['input','output']:
            self.assertEqual(identity.sha(gzip.decompress((directory/(name+'.json.gz')).read_bytes())),fixture['compiler_'+name+'_sha256'])
        contract=out['contracts'][harness.NAME]['AaveAmountHarness']['evm']
        self.assertEqual('0x'+contract['deployedBytecode']['object'],fixture['runtime_code'])
        self.assertEqual('0x'+contract['methodIdentifiers'][harness.SIGNATURE],fixture['selector'])
        self.assertEqual(fixture['compiler_sha256'],identity.COMPILER_SHA)
        self.assertFalse(fixture['activation_allowed'])

    def test_changed_original_source_is_rejected_before_compilation(self):
        source=identity.read_json(identity.EVIDENCE/'source.json.gz')
        source['sources'][harness.SOURCE_PATH]['content']=source['sources'][harness.SOURCE_PATH]['content'].replace('0.5e4','0.6e4')
        with self.assertRaisesRegex(ValueError,'amount source identity'):
            harness.extracted_harness(source)

    def test_cli_returns_amounts_but_never_eligibility_and_rejects_ambiguous_inputs(self):
        data=dict(collateral_balance='20000000000',reserve_debt='10000000000',total_debt_base='1000000000000',
            health_factor_wad='970000000000000000',collateral_price='100000000',debt_price='100000000',
            collateral_decimals=6,debt_decimals=6,liquidation_bonus_bps=10500,liquidation_protocol_fee_bps=1000,
            debt_to_cover=str(2**256-1))
        binary=os.environ['NQC_MINER_TEST_BINARY']
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'input.json'
            def run(value):
                path.write_text(json.dumps(value))
                return subprocess.run([binary,'calculate-aave-amounts','--input',str(path)],capture_output=True,text=True)
            result=run(data);self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(result.stdout)
            self.assertEqual(report['amounts']['max_liquidatable_debt'],'5000000000')
            self.assertTrue(report['amount_calculation_passed'])
            for flag in ['activation_allowed','executable_eligibility_verified','input_state_authenticated','initial_conditions_checked']:
                self.assertFalse(report[flag])
            for key,value in [('debt_to_cover','1e18'),('activation_allowed',True),('collateral_decimals',256),('liquidation_bonus_bps',65536)]:
                bad=data.copy();bad[key]=value
                self.assertNotEqual(run(bad).returncode,0)
            bad=data.copy();bad['collateral_price']='0';result=run(bad)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(result.stdout)
            self.assertFalse(report['amount_calculation_passed']);self.assertIsNone(report['amounts'])
            self.assertEqual(report['revert_data'],'0x4e487b71'+f'{0x12:064x}')

if __name__ == '__main__':
    unittest.main()
