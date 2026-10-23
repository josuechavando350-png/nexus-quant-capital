import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import aave_runtime_identity as identity
import build_aave_collateral_harness as harness


class AaveCollateralTests(unittest.TestCase):
    def test_reference_uses_pinned_original_segment_and_unchanged_imports(self):
        source=identity.read_json(identity.EVIDENCE/'source.json.gz')
        identity.verify_provenance(source)
        rendered,segments=harness.extracted_harness(source)
        self.assertEqual(rendered,(identity.MODULE/harness.NAME).read_text())
        fixture=identity.read_json(identity.MODULE/'fixtures/aave_collateral_harness.json')
        self.assertEqual(fixture['extracted_segments'],segments)
        self.assertEqual(fixture['harness_source_sha256'],identity.sha(rendered.encode()))
        directory=identity.MODULE/'evidence/aave-collateral-20261023/compiler'
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
        deployed=out['contracts'][harness.NAME]['AaveCollateralHarness']
        self.assertEqual(deployed['storageLayout'],fixture['storage_layout'])
        self.assertEqual(fixture['explicit_zero_slots'],[0,1,2,3])
        self.assertTrue(fixture['post_liquidator_balance_supplied'])
        self.assertFalse(fixture['token_implementation_verified'])
        contract=deployed['evm']
        self.assertEqual('0x'+contract['deployedBytecode']['object'],fixture['runtime_code'])
        self.assertEqual('0x'+contract['methodIdentifiers'][harness.SIGNATURE],fixture['selector'])
        self.assertEqual(fixture['compiler_sha256'],identity.COMPILER_SHA)
        self.assertFalse(fixture['activation_allowed'])

    def test_changed_original_source_is_rejected_before_compilation(self):
        source=identity.read_json(identity.EVIDENCE/'source.json.gz')
        source['sources'][harness.SOURCE_PATH]['content']=source['sources'][harness.SOURCE_PATH]['content'].replace('0.5e4','0.6e4')
        with self.assertRaisesRegex(ValueError,'collateral source identity'):
            harness.extracted_harness(source)

    def test_cli_strict_fields_reverts_and_zero_cap_call(self):
        ray = 10**27
        data = dict(liquidity_index_ray=str(ray*3//2), borrower_scaled_collateral_balance="3",
                    collateral_to_liquidator="2", protocol_fee_collateral="1", collateral_price="1",
                    collateral_decimals=0, total_collateral_base="4", post_liquidator_scaled_balance="0")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"input.json"
            def run(value):
                path.write_text(json.dumps(value))
                return subprocess.run([os.environ["NQC_MINER_TEST_BINARY"], "calculate-aave-collateral",
                                       "--input", str(path)], capture_output=True, text=True)
            result = run(data)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["calculation_passed"])
            self.assertTrue(report["post_liquidator_balance_supplied"])
            self.assertTrue(report["amounts"]["fee_transfer_required"])
            self.assertEqual(report["amounts"]["final_protocol_fee_collateral"], "0")
            for flag in ["token_operations_executed", "input_state_authenticated",
                         "executable_eligibility_verified", "activation_allowed"]:
                self.assertFalse(report[flag])
            for key, value in [("liquidity_index_ray", "01"), ("post_liquidator_scaled_balance", "1e10"),
                               ("collateral_decimals", 256), ("collateral_price", str(2**256)),
                               ("activation_allowed", True)]:
                bad = data.copy(); bad[key] = value
                self.assertNotEqual(run(bad).returncode, 0)
            bad = data.copy(); del bad["post_liquidator_scaled_balance"]
            self.assertNotEqual(run(bad).returncode, 0)
            bad = data.copy(); bad["liquidity_index_ray"] = "0"
            result = run(bad); self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["calculation_passed"])
            self.assertIsNone(report["amounts"])
            self.assertEqual(report["revert_data"], "0x")

    def test_real_cli_composition_uses_projected_balance_then_amounts_then_scaled_consumption(self):
        ray = 10**27
        binary = os.environ["NQC_MINER_TEST_BINARY"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"input.json"
            def run(command, data):
                path.write_text(json.dumps(data))
                result = subprocess.run([binary, command, "--input", str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)
            reserve = dict(liquidity_index_ray=str(ray*3//2), variable_borrow_index_ray=str(ray),
                           liquidity_rate_ray="0", variable_borrow_rate_ray="0", accrued_to_treasury_scaled="0",
                           last_update_timestamp=100, reserve_factor_bps=1000, total_scaled_variable_debt="2",
                           user_scaled_collateral="3", user_scaled_variable_debt="2", timestamp=100)
            projected = run("project-aave-reserve", reserve)["projected"]
            amount_input = dict(collateral_balance=projected["user_collateral_balance"],
                               reserve_debt=projected["user_variable_debt_balance"], total_debt_base="2",
                               health_factor_wad=str(9*10**17), collateral_price="1", debt_price="1",
                               collateral_decimals=0, debt_decimals=0, liquidation_bonus_bps=15000,
                               liquidation_protocol_fee_bps=10000, debt_to_cover="2")
            amounts = run("calculate-aave-amounts", amount_input)["amounts"]
            self.assertEqual(amounts["collateral_to_liquidator"], "2")
            self.assertEqual(amounts["protocol_fee_collateral"], "1")
            self.assertLess(int(amounts["collateral_to_liquidator"])+int(amounts["protocol_fee_collateral"]),
                            int(projected["user_collateral_balance"]))
            collateral = dict(liquidity_index_ray=projected["liquidity_index_ray"],
                              borrower_scaled_collateral_balance=reserve["user_scaled_collateral"],
                              collateral_to_liquidator=amounts["collateral_to_liquidator"],
                              protocol_fee_collateral=amounts["protocol_fee_collateral"],
                              collateral_price="1", collateral_decimals=0, total_collateral_base="4",
                              post_liquidator_scaled_balance="1")  # supplied fixture, not a token execution
            report = run("calculate-aave-collateral", collateral)
            self.assertEqual(report["amounts"]["scaled_collateral_consumed"], "3")
            self.assertTrue(report["amounts"]["has_no_collateral_left"])
            self.assertFalse(report["executable_eligibility_verified"])
            collateral["post_liquidator_scaled_balance"] = "0"
            capped = run("calculate-aave-collateral", collateral)
            self.assertEqual(capped["amounts"]["final_protocol_fee_scaled"], "0")
            self.assertTrue(capped["amounts"]["fee_transfer_required"])

if __name__ == "__main__":
    unittest.main()
