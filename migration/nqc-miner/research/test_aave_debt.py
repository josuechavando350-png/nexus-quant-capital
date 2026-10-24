import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import aave_runtime_identity as identity
import build_aave_debt_harness as harness


class AaveDebtTests(unittest.TestCase):
    def test_original_functions_and_compiler_artifacts_are_bound_without_source_edits(self):
        source=identity.read_json(identity.EVIDENCE/'source.json.gz')
        identity.verify_provenance(source)
        directory=identity.MODULE/'evidence/aave-debt-20261023/compiler'
        inp=identity.read_json(directory/'input.json.gz')
        out=identity.read_json(directory/'output.json.gz')
        fixture=identity.read_json(identity.MODULE/'fixtures/aave_debt_harness.json')
        self.assertEqual({k:v for k,v in inp['sources'].items() if k!=harness.NAME},source['sources'])
        self.assertEqual(inp['sources'][harness.NAME]['content'],(identity.MODULE/harness.NAME).read_text())
        expected=identity.compilation_input(source)['settings'];expected.pop('outputSelection')
        actual=copy.deepcopy(inp['settings']);actual.pop('outputSelection');self.assertEqual(actual,expected)
        self.assertEqual(fixture['original_sources'],{k:identity.sha(v['content'].encode()) for k,v in source['sources'].items()})
        for name in ['input','output']:
            self.assertEqual(identity.sha(gzip.decompress((directory/(name+'.json.gz')).read_bytes())),fixture['compiler_'+name+'_sha256'])
        contract=out['contracts'][harness.NAME]['AaveDebtHarness']
        self.assertEqual('0x'+contract['evm']['deployedBytecode']['object'],fixture['runtime_code'])
        self.assertEqual('0x'+contract['evm']['methodIdentifiers'][harness.SIGNATURE],fixture['selector'])
        self.assertEqual(fixture['storage_layout'],contract['storageLayout'])
        self.assertEqual(fixture['compiler_sha256'],identity.COMPILER_SHA)
        self.assertEqual(identity.sha((identity.MODULE/harness.NAME).read_bytes()),fixture['harness_source_sha256'])
        self.assertTrue(fixture['external_outcomes_supplied'])
        self.assertFalse(fixture['token_implementation_verified'])
        self.assertFalse(fixture['rate_strategy_verified'])
        self.assertEqual(fixture['reference_function'], 'LiquidationLogic._burnDebtTokens')
        layout=contract['storageLayout']
        roots=[int(v['slot']) for v in layout['storage'] if layout['types'][v['type']]['encoding']=='bytes']
        self.assertEqual(fixture['dynamic_bytes_slots'],roots)
        self.assertEqual(fixture['dynamic_bytes_zero_words_per_root'],128)
        self.assertIn('LiquidationLogic._burnDebtTokens(cache, reserve, borrowerConfig,',(identity.MODULE/harness.NAME).read_text())
        self.assertFalse(fixture['executable_eligibility_verified'])

    def base_input(self):
        return dict(borrower_reserve_debt="100", actual_debt_to_liquidate="40", has_no_collateral_left=False,
                    next_variable_borrow_index_ray=str(15*10**26), current_scaled_variable_debt="1000",
                    reserve_deficit="5", virtual_underlying_balance="200", reserve_id=1,
                    user_configuration="255", reserve_factor="1000",
                    token_burn=dict(status="return", no_more_debt=False, next_scaled_variable_debt="974"),
                    rate_quote=dict(status="return", liquidity_rate_ray="10", variable_borrow_rate_ray="20"))

    def command(self, command, data):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"input.json";path.write_text(json.dumps(data))
            return subprocess.run([os.environ["NQC_MINER_TEST_BINARY"], command, "--input", str(path)], capture_output=True, text=True)

    def test_cli_has_explicit_outcomes_and_strict_widths_without_execution_authority(self):
        data=self.base_input(); result=self.command("calculate-aave-debt",data)
        self.assertEqual(result.returncode,0,result.stderr);report=json.loads(result.stdout)
        self.assertTrue(report["calculation_passed"]);self.assertTrue(report["external_outcomes_supplied"])
        self.assertEqual(report["amounts"]["scaled_debt_to_burn"],"26")
        self.assertEqual(report["amounts"]["rate_inputs"]["virtual_underlying_balance_before_update"],"200")
        self.assertEqual(report["amounts"]["new_virtual_underlying_balance"],"240")
        for flag in ["token_implementation_verified","rate_strategy_verified","input_state_authenticated","executable_eligibility_verified","activation_allowed"]:
            self.assertFalse(report[flag])
        for key,value in [("borrower_reserve_debt","01"),("reserve_deficit",str(2**128)),("virtual_underlying_balance",str(2**128)),
                          ("reserve_id",65536),("reserve_factor",str(2**256)),("activation_allowed",True)]:
            bad=copy.deepcopy(data);bad[key]=value
            self.assertNotEqual(self.command("calculate-aave-debt",bad).returncode,0)
        for key in ["token_burn","rate_quote"]:
            bad=copy.deepcopy(data);del bad[key]
            self.assertNotEqual(self.command("calculate-aave-debt",bad).returncode,0)
            bad=copy.deepcopy(data);bad[key]["extra"]=True
            self.assertNotEqual(self.command("calculate-aave-debt",bad).returncode,0)
        bad=copy.deepcopy(data);bad["token_burn"]={"status":"return","no_more_debt":True}
        self.assertNotEqual(self.command("calculate-aave-debt",bad).returncode,0)

    def test_external_empty_reverts_skip_branch_and_bad_hex_are_distinct(self):
        data=self.base_input();data["token_burn"]={"status":"revert","data":"0x"}
        result=self.command("calculate-aave-debt",data);self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout);self.assertFalse(report["calculation_passed"])
        self.assertIsNone(report["amounts"]);self.assertEqual(report["revert_data"],"0x")
        data["borrower_reserve_debt"]="0";data["actual_debt_to_liquidate"]="0"
        result=self.command("calculate-aave-debt",data);self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout);self.assertTrue(report["calculation_passed"])
        self.assertFalse(report["amounts"]["burn_called"])
        self.assertEqual(report["amounts"]["next_scaled_variable_debt"],"1000")
        for bad_bytes in ["0xA0","0x1","0xzz","12","0x"+"00"*4097]:
            bad=copy.deepcopy(data);bad["token_burn"]["data"]=bad_bytes
            self.assertNotEqual(self.command("calculate-aave-debt",bad).returncode,0)
        data["rate_quote"]={"status":"revert","data":"0x12345678"}
        result=self.command("calculate-aave-debt",data);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["revert_data"],"0x12345678")

    def test_collateral_cli_flag_drives_deficit_without_inventing_token_return(self):
        collateral=dict(liquidity_index_ray=str(15*10**26),borrower_scaled_collateral_balance="3",
                        collateral_to_liquidator="2",protocol_fee_collateral="1",collateral_price="1",
                        collateral_decimals=0,total_collateral_base="4",post_liquidator_scaled_balance="1")
        result=self.command("calculate-aave-collateral",collateral)
        self.assertEqual(result.returncode,0,result.stderr)
        exhausted=json.loads(result.stdout)["amounts"]["has_no_collateral_left"]
        data=self.base_input();data["has_no_collateral_left"]=exhausted
        # This dependency response is supplied, not inferred or an authenticated token state.
        data["token_burn"]={"status":"return","no_more_debt":True,"next_scaled_variable_debt":"933"}
        result=self.command("calculate-aave-debt",data);self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout);amounts=report["amounts"]
        self.assertEqual(amounts["scaled_debt_to_burn"],"66")
        self.assertEqual(amounts["new_reserve_deficit"],"65")
        self.assertEqual(amounts["rate_inputs"]["unbacked"],"65")
        self.assertEqual(amounts["next_scaled_variable_debt"],"933")
        self.assertEqual(amounts["user_configuration"],"251")
        self.assertFalse(report["executable_eligibility_verified"])
        data["has_no_collateral_left"]=False
        result=self.command("calculate-aave-debt",data);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["amounts"]["new_reserve_deficit"],"5")

if __name__=="__main__":
    unittest.main()
