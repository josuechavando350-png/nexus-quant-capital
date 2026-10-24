"""Amount arithmetic composes with updated reserves and complete synthetic payments."""
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import build_aave_sizing_execution as builder

identity = builder.identity
EVIDENCE = builder.DIRECTORY


class SizingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = identity.read_json(EVIDENCE / 'compiler/input.json.gz')
        cls.raw = gzip.decompress((EVIDENCE / 'compiler/output.json.gz').read_bytes())
        cls.fixture = identity.read_json(identity.MODULE / 'fixtures/aave_sizing_execution.json')
        cls.examples = {m: {n: identity.read_json(EVIDENCE / 'synthetic' / m / (n + '.json'))
            for n in ['input', 'output', 'models']} for m in ['atoken', 'underlying']}

    def cli(self, command, data):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.json'; p.write_text(json.dumps(data))
            return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'], command, '--input', str(p)], capture_output=True, text=True)

    def replace_word(self, data, index, value):
        start = 10 + 64*index; old = data['call']['calldata']
        data['call']['calldata'] = old[:start] + f'{value:064x}' + old[start+64:]

    def assert_atomic(self, result, expected):
        self.assertEqual(result.returncode, 0, result.stderr); out = json.loads(result.stdout)
        self.assertEqual(out['status'], 'revert'); self.assertEqual(out['output'], expected)
        self.assertEqual(out['logs'], []); self.assertTrue(all(not a['storage'] for a in out['account_deltas']))

    def test_fixture_rebuild_binds_unchanged_sources_settings_compiler_and_layout(self):
        self.assertEqual(builder.fixture(self.value, self.raw), self.fixture)
        source = identity.read_json(identity.EVIDENCE / 'source.json.gz'); identity.verify_provenance(source)
        self.assertEqual({k: v for k, v in self.value['sources'].items() if k != builder.NAME}, source['sources'])
        settings = copy.deepcopy(self.value['settings']); settings.pop('outputSelection')
        expected = identity.compilation_input(source)['settings']; expected.pop('outputSelection')
        self.assertEqual(settings, expected); self.assertEqual(self.fixture['compiler_sha256'], identity.COMPILER_SHA)
        self.assertEqual(self.fixture['compiler_output_sha256'], identity.sha(self.raw))
        contract = self.fixture['contracts'][builder.CONTRACT]
        self.assertIn(builder.SIGNATURE, contract['selectors'])
        self.assertEqual([(v['label'], v['slot']) for v in contract['storage_layout']['storage']],
            [('debtReserve','0'), ('borrowerConfig','10'), ('collateralReserve','11')])
        value = copy.deepcopy(self.value); value['sources'][builder.NAME]['content'] += '\n'
        with self.assertRaises(ValueError): builder.fixture(value, self.raw)

    def test_amount_segment_constants_helper_and_order_preserve_original_bytes(self):
        value, harness, segments = builder.harness_input()
        self.assertEqual(value, self.value); self.assertEqual(harness, (identity.MODULE / builder.NAME).read_text())
        original = value['sources'][builder.amount.SOURCE_PATH]['content']
        start = original.index('    vars.collateralAssetUnit = 10 **')
        arithmetic = original[start:original.index('    // Determine whether', start)]
        self.assertIn(arithmetic, harness)
        self.assertEqual(segments['unchanged_units_amounts_and_dust'], identity.sha(arithmetic.encode()))
        self.assertLess(harness.index('ValidationLogic.validateLiquidationCall('), harness.index(arithmetic))
        self.assertLess(harness.index(arithmetic), harness.index('LiquidationLogic._burnDebtTokens('))
        self.assertIn('LiquidationLogic._calculateAvailableCollateralToLiquidate(', harness)
        for stale in ['input.amount', 'input.fee', 'input.unit', 'input.repayment']:
            self.assertNotIn(stale, harness)
        self.assertIn('params.debtToCover = input.debtToCover;', harness)

    def test_inherited_dependencies_and_synthetic_limits_remain_explicit(self):
        prior = identity.read_json(identity.MODULE / 'fixtures/aave_prelude_execution.json')
        for name, value in prior['contracts'].items():
            if name != builder.prelude.CONTRACT: self.assertEqual(value, self.fixture['contracts'][name])
        for k in ['liquidation_amount_calculation_executed', 'close_factor_and_dust_executed',
            'bonus_derived_from_reserve_configuration', 'oracle_prices_supplied', 'aggregate_debt_and_collateral_supplied',
            'health_factor_supplied', 'initial_reserve_updates_executed']:
            self.assertTrue(self.fixture[k])
        for k in ['liquidation_amounts_supplied', 'emode_selection_executed', 'aggregate_account_data_calculation_executed',
            'historical_state_authenticated', 'complete_liquidation_verified', 'activation_allowed',
            'same_asset_cache_branch_executed', 'weth_full_source_runtime_match', 'usdc_full_source_runtime_match']:
            self.assertFalse(self.fixture[k])
        self.assertEqual(self.fixture['borrower_emode_category'], 0)

    def test_examples_replay_complete_outputs_and_independent_amount_and_reserve_models(self):
        for example in self.examples.values():
            result = self.cli('simulate', example['input']); self.assertEqual(result.returncode, 0, result.stderr)
            out = json.loads(result.stdout); self.assertEqual(out, example['output'])
            words = [int(out['output'][i:i+64],16) for i in range(2,len(out['output']),64)]
            self.assertEqual(len(words),43); self.assertEqual(words[37:41],[166,40,41,1])
            self.assertEqual(words[22:25],[460,240,460]); self.assertFalse(out['canonical_state_authenticated'])
            for prefix, command in [('amount','calculate-aave-amounts'), ('debt','project-aave-reserve'), ('collateral','project-aave-reserve')]:
                result = self.cli(command,example['models'][prefix+'_input'])
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(json.loads(result.stdout),example['models'][prefix+'_expected'])

    def test_dust_rejection_rolls_back_accrual_and_matches_independent_cli_error(self):
        for example in self.examples.values():
            data=copy.deepcopy(example['input']); self.replace_word(data,7,10**8); self.replace_word(data,8,10**8)
            model=copy.deepcopy(example['models']['amount_input']); model['collateral_price']=model['debt_price']=str(10**8)
            result=self.cli('calculate-aave-amounts',model); self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(result.stdout); self.assertFalse(report['amount_calculation_passed'])
            self.assert_atomic(self.cli('simulate',data),report['revert_data'])

    def test_initial_validation_precedes_division_by_zero_and_sizing_panic_is_atomic(self):
        for example in self.examples.values():
            data=copy.deepcopy(example['input']); self.replace_word(data,7,0)
            model=copy.deepcopy(example['models']['amount_input']); model['collateral_price']='0'
            expected=json.loads(self.cli('calculate-aave-amounts',model).stdout)['revert_data']
            self.assert_atomic(self.cli('simulate',data),expected)
            self.replace_word(data,31,10**18)
            result=self.cli('simulate',data); self.assertEqual(result.returncode,0,result.stderr)
            out=json.loads(result.stdout); self.assertNotEqual(out['output'],expected)
            self.assert_atomic(result,'0x930bb771')  # HealthFactorNotBelowThreshold()

    def test_late_usdc_failure_restores_amount_driven_operations(self):
        for example in self.examples.values():
            data=copy.deepcopy(example['input'])
            token=next(a for a in data['snapshot']['accounts'] if a['address']==builder.prelude.delivery.payment.capture.USDC)
            token['storage']['1']=str(1<<160)
            result=self.cli('simulate',data); self.assertEqual(result.returncode,0,result.stderr)
            expected=json.loads(result.stdout)['output']; self.assertIn(b'Pausable: paused'.hex(),expected)
            self.assert_atomic(result,expected)

    def test_missing_cache_and_payment_accounts_fail_closed_with_no_report(self):
        for example in self.examples.values():
            for address in [builder.prelude.COLLATERAL_DEBT, builder.prelude.delivery.payment.capture.USDC]:
                data=copy.deepcopy(example['input']); data['snapshot']['accounts']=[a for a in data['snapshot']['accounts'] if a['address']!=address]
                result=self.cli('simulate',data); self.assertNotEqual(result.returncode,0); self.assertEqual(result.stdout,'')


if __name__ == '__main__':
    unittest.main()
