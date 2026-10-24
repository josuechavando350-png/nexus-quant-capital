"""Composed reserve prelude and original initial validation; aggregate health stays supplied."""
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import build_aave_prelude_execution as builder

identity = builder.identity
EVIDENCE = builder.DIRECTORY


class PreludeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = identity.read_json(EVIDENCE / 'compiler/input.json.gz')
        cls.raw = gzip.decompress((EVIDENCE / 'compiler/output.json.gz').read_bytes())
        cls.fixture = identity.read_json(identity.MODULE / 'fixtures/aave_prelude_execution.json')
        cls.examples = {m: {n: identity.read_json(EVIDENCE / 'synthetic' / m / (n + '.json'))
            for n in ['input', 'output', 'models']} for m in ['atoken', 'underlying']}

    def cli(self, command, data):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.json'; p.write_text(json.dumps(data))
            return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'], command, '--input', str(p)], capture_output=True, text=True)

    def test_fixture_rebuild_binds_unchanged_sources_settings_and_compiler(self):
        self.assertEqual(builder.fixture(self.value, self.raw), self.fixture)
        source = identity.read_json(identity.EVIDENCE / 'source.json.gz'); identity.verify_provenance(source)
        self.assertEqual({k: v for k, v in self.value['sources'].items() if k != builder.NAME}, source['sources'])
        settings = copy.deepcopy(self.value['settings']); settings.pop('outputSelection')
        expected = identity.compilation_input(source)['settings']; expected.pop('outputSelection')
        self.assertEqual(settings, expected)
        self.assertEqual(self.fixture['compiler_sha256'], identity.COMPILER_SHA)
        self.assertEqual(self.fixture['compiler_output_sha256'], identity.sha(self.raw))
        self.assertIn(builder.SIGNATURE, self.fixture['contracts'][builder.CONTRACT]['selectors'])
        value = copy.deepcopy(self.value); value['sources'][builder.NAME]['content'] += '\n'
        with self.assertRaises(ValueError): builder.fixture(value, self.raw)

    def test_original_cache_balance_and_validation_excerpts_preserve_order(self):
        value, harness, segments = builder.harness_input()
        self.assertEqual(value, self.value); self.assertEqual(harness, (identity.MODULE / builder.NAME).read_text())
        original = value['sources'][builder.delivery.payment.underlying.transfer.SOURCE_PATH]['content']
        a = original.index('    vars.debtReserveCache = debtReserve.cache();')
        cache = original[a:original.index('\n    (\n      vars.totalCollateralInBaseCurrency', a)]
        a = original.index('    vars.borrowerScaledCollateralBalance = IAToken(')
        validation = original[a:original.index('\n    if (\n      params.borrowerEModeCategory', a)]
        self.assertIn(cache, harness); self.assertIn(validation, harness)
        self.assertEqual(segments['unchanged_cache_and_update_order'], identity.sha(cache.encode()))
        self.assertEqual(segments['unchanged_derived_balances_and_validation'], identity.sha(validation.encode()))
        self.assertLess(harness.index(cache), harness.index(validation))
        self.assertLess(harness.index(validation), harness.index('LiquidationLogic._burnDebtTokens('))
        for stale in ['input.debt,', 'input.debtIndex', 'input.cached', 'input.index', 'input.collateralScaledDebt']:
            self.assertNotIn(stale, harness)
        self.assertIn('vars.healthFactor = input.health;', harness)

    def test_prior_dependencies_layout_and_historical_limits_remain_explicit(self):
        prior = identity.read_json(identity.MODULE / 'fixtures/aave_delivery_execution.json')
        for name, c in prior['contracts'].items():
            if name != builder.delivery.CONTRACT: self.assertEqual(c, self.fixture['contracts'][name])
        samples = [p for p in self.fixture['proxy_samples'] if p['proxy'] == builder.COLLATERAL_DEBT]
        self.assertEqual(len(samples), 2); self.assertTrue(all(p['proxy_contract'] == 'AuditedDebtProxy' for p in samples))
        for k in ['health_factor_supplied', 'initial_reserve_updates_executed', 'initial_health_validation_executed',
            'selected_debt_derived_from_scaled_balance', 'scaled_totals_read_from_observed_token_code']:
            self.assertTrue(self.fixture[k])
        for k in ['aggregate_account_data_calculation_executed', 'historical_state_authenticated',
            'complete_liquidation_verified', 'same_asset_cache_branch_executed', 'activation_allowed',
            'usdc_full_source_runtime_match', 'weth_full_source_runtime_match']:
            self.assertFalse(self.fixture[k])
        layout = self.fixture['contracts'][builder.CONTRACT]['storage_layout']
        reserve = layout['types'][layout['storage'][0]['type']]
        fields = {x['label']: (x['slot'], x['offset']) for x in reserve['members']}
        self.assertEqual({k: fields[k] for k in ['liquidityIndex','variableBorrowIndex','lastUpdateTimestamp',
            'liquidationGracePeriodUntil','accruedToTreasury']},
            {'liquidityIndex': ('1',0), 'variableBorrowIndex': ('2',0), 'lastUpdateTimestamp': ('3',16),
             'liquidationGracePeriodUntil': ('3',23), 'accruedToTreasury': ('8',0)})

    def test_both_cli_examples_replay_all_words_events_and_storage(self):
        for example in self.examples.values():
            result = self.cli('simulate', example['input']); self.assertEqual(result.returncode, 0, result.stderr)
            out = json.loads(result.stdout); self.assertEqual(out, example['output'])
            words = [int(out['output'][i:i+64],16) for i in range(2,len(out['output']),64)]
            self.assertEqual(len(words),37); self.assertFalse(out['canonical_state_authenticated'])
            self.assertEqual(words[33], int(example['models']['debt_expected']['projected']['user_variable_debt_balance']))
            self.assertEqual(words[34], int(example['models']['collateral_expected']['projected']['user_collateral_balance']))
            self.assertEqual(words[35:], [1000,2000]); self.assertEqual(words[22:25], [60,240,60])
            self.assertGreater(words[27],7); self.assertGreater(words[31],11)

    def test_independent_reserve_and_condition_clis_reproduce_composition_inputs(self):
        model = self.examples['atoken']['models']
        for prefix, command in [('debt','project-aave-reserve'), ('collateral','project-aave-reserve'),
            ('conditions','check-aave-conditions')]:
            result = self.cli(command,model[prefix+'_input']); self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),model[prefix+'_expected'])
        self.assertTrue(model['conditions_expected']['initial_conditions_passed'])
        self.assertFalse(model['conditions_expected']['executable_eligibility_verified'])

    def replace_word(self, data, index, value):
        start = 10 + 64*index; old = data['call']['calldata']
        data['call']['calldata'] = old[:start] + f'{value:064x}' + old[start+64:]

    def assert_atomic(self, result, expected=None):
        self.assertEqual(result.returncode,0,result.stderr); out=json.loads(result.stdout)
        self.assertEqual(out['status'],'revert'); self.assertEqual(out['logs'],[])
        self.assertTrue(all(not a['storage'] for a in out['account_deltas']))
        if expected is not None: self.assertEqual(out['output'],expected)

    def test_supplied_health_rejection_rolls_back_accrual_before_any_delivery(self):
        for example in self.examples.values():
            data=copy.deepcopy(example['input']); self.replace_word(data,32,10**18)
            condition=copy.deepcopy(example['models']['conditions_input']); condition['health_factor_wad']=str(10**18)
            expected=json.loads(self.cli('check-aave-conditions',condition).stdout)['revert_selector']
            self.assert_atomic(self.cli('simulate',data),expected)

    def test_update_failure_precedes_health_and_late_payment_failure_is_atomic(self):
        for example in self.examples.values():
            data=copy.deepcopy(example['input']); self.replace_word(data,20,2**128-1); self.replace_word(data,32,10**18)
            self.assert_atomic(self.cli('simulate',data),'0x4e487b71'+f'{0x11:064x}')
            data=copy.deepcopy(example['input'])
            token=next(a for a in data['snapshot']['accounts'] if a['address']==builder.delivery.payment.capture.USDC)
            token['storage']['1']=str(1<<160); result=self.cli('simulate',data); self.assert_atomic(result)
            self.assertIn(b'Pausable: paused'.hex(),json.loads(result.stdout)['output'])

    def test_missing_actual_collateral_debt_cache_witnesses_fail_closed_in_both_modes(self):
        for example in self.examples.values():
            for kind in ['account','total','routing']:
                data=copy.deepcopy(example['input'])
                token=next(a for a in data['snapshot']['accounts'] if a['address']==builder.COLLATERAL_DEBT)
                if kind=='account': data['snapshot']['accounts'].remove(token)
                elif kind=='total': token['storage'].pop('58')
                else: token['storage'].pop(next(k for k in token['storage'] if k!='58'))
                result=self.cli('simulate',data); self.assertNotEqual(result.returncode,0); self.assertEqual(result.stdout,'')


if __name__ == '__main__':
    unittest.main()
