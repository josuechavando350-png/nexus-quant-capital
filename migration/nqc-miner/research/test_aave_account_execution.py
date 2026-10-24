"""Original account health and eMode; all prices/state and Pool entry are synthetic."""
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import build_aave_account_execution as builder

identity = builder.identity
EVIDENCE = builder.DIRECTORY


class AccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = identity.read_json(EVIDENCE / 'compiler/input.json.gz')
        cls.raw = gzip.decompress((EVIDENCE / 'compiler/output.json.gz').read_bytes())
        cls.fixture = identity.read_json(identity.MODULE / 'fixtures/aave_account_execution.json')
        cls.examples = {m: {n: identity.read_json(EVIDENCE / 'synthetic' / m / (n + '.json'))
            for n in ['input', 'output', 'models']} for m in ['atoken', 'underlying']}

    def cli(self, command, data):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.json'; p.write_text(json.dumps(data))
            return subprocess.run([os.environ['NQC_MINER_TEST_BINARY'],command,'--input',str(p)],capture_output=True,text=True)

    def words(self, output):
        return [int(output[i:i+64],16) for i in range(2,len(output),64)]

    def replace_word(self, data, index, value):
        start=10+64*index; old=data['call']['calldata']
        data['call']['calldata']=old[:start]+f'{value:064x}'+old[start+64:]

    def atomic(self, result, expected):
        self.assertEqual(result.returncode,0,result.stderr); out=json.loads(result.stdout)
        self.assertEqual(out['status'],'revert'); self.assertEqual(out['output'],expected)
        self.assertEqual(out['logs'],[]); self.assertTrue(all(not a['storage'] for a in out['account_deltas']))

    def test_rebuild_binds_unchanged_original_sources_settings_and_layout(self):
        self.assertEqual(builder.fixture(self.value,self.raw),self.fixture)
        original=identity.read_json(identity.EVIDENCE/'source.json.gz'); identity.verify_provenance(original)
        self.assertEqual({k:v for k,v in self.value['sources'].items() if k!=builder.NAME},original['sources'])
        actual=copy.deepcopy(self.value['settings']); actual.pop('outputSelection')
        expected=identity.compilation_input(original)['settings']; expected.pop('outputSelection'); self.assertEqual(actual,expected)
        self.assertEqual(self.fixture['compiler_sha256'],identity.COMPILER_SHA)
        c=self.fixture['contracts'][builder.CONTRACT]
        self.assertIn(builder.SIGNATURE,c['selectors'])
        self.assertEqual([(v['label'],v['slot']) for v in c['storage_layout']['storage']],
            [('debtReserve','0'),('borrowerConfig','10'),('collateralReserve','11'),('reservesData','21'),('reservesList','22'),('eModeCategories','23')])
        value=copy.deepcopy(self.value); value['sources'][builder.NAME]['content']+='\n'
        with self.assertRaises(ValueError): builder.fixture(value,self.raw)

    def test_original_account_call_emode_selection_price_calls_and_order_are_exact(self):
        value,harness,segments=builder.harness_input(); self.assertEqual(value,self.value)
        self.assertEqual(harness,(identity.MODULE/builder.NAME).read_text())
        original=value['sources'][builder.sizing.amount.SOURCE_PATH]['content']
        start=original.index('    (\n      vars.totalCollateralInBaseCurrency')
        account=original[start:original.index('    vars.borrowerScaledCollateralBalance',start)]
        start=original.index('    if (\n      params.borrowerEModeCategory')
        prices=original[start:original.index('    vars.collateralAssetUnit',start)]
        self.assertIn(account,harness); self.assertIn(prices,harness)
        self.assertEqual(segments['unchanged_account_data_call'],identity.sha(account.encode()))
        self.assertEqual(segments['unchanged_emode_selection_and_price_calls'],identity.sha(prices.encode()))
        self.assertLess(harness.index('collateralReserve.updateState('),harness.index(account))
        self.assertLess(harness.index(account),harness.index('ValidationLogic.validateLiquidationCall('))
        self.assertLess(harness.index('ValidationLogic.validateLiquidationCall('),harness.index(prices))
        self.assertLess(harness.index(prices),harness.index('LiquidationLogic._burnDebtTokens('))
        for stale in ['input.health','input.totalBase','input.totalDebtBase','input.price','input.debtPrice']:
            self.assertNotIn(stale,harness)

    def test_dependencies_and_explicit_oracle_and_historical_limits_are_preserved(self):
        prior=identity.read_json(identity.MODULE/'fixtures/aave_sizing_execution.json')
        for name,c in prior['contracts'].items():
            if name!=builder.sizing.CONTRACT: self.assertEqual(c,self.fixture['contracts'][name])
        for key in ['aggregate_account_data_calculation_executed','emode_selection_executed','oracle_calls_executed',
                    'oracle_prices_supplied','bonus_derived_from_reserve_or_emode_configuration']:
            self.assertTrue(self.fixture[key])
        for key in ['health_factor_supplied','aggregate_debt_and_collateral_supplied','oracle_runtime_authenticated',
                    'oracle_state_authenticated','historical_state_authenticated','complete_liquidation_verified','activation_allowed',
                    'same_asset_cache_branch_executed','usdc_full_source_runtime_match','weth_full_source_runtime_match']:
            self.assertFalse(self.fixture[key])
        self.assertEqual(self.fixture['oracle_kind'],'synthetic_test_double')

    def test_complete_cli_replays_and_independent_integer_health_matches_reserve_reports(self):
        for example in self.examples.values():
            result=self.cli('simulate',example['input']); self.assertEqual(result.returncode,0,result.stderr)
            out=json.loads(result.stdout); self.assertEqual(out,example['output'])
            words=self.words(out['output']); self.assertEqual(len(words),47)
            models=example['models']; account=list(map(int,models['account_expected']))
            projections={}
            for prefix in ['debt','collateral']:
                result=self.cli('project-aave-reserve',models[prefix+'_input']); self.assertEqual(result.returncode,0,result.stderr)
                projections[prefix]=json.loads(result.stdout)['projected']
            amount=models['amount_input']; collateral=int(projections['collateral']['user_collateral_balance'])*int(amount['collateral_price'])//10**amount['collateral_decimals']
            product=int(projections['debt']['user_variable_debt_balance'])*int(amount['debt_price']); unit=10**amount['debt_decimals']
            debt=(product+unit-1)//unit
            config=self.words('0x'+example['input']['call']['calldata'][10:])[25]
            threshold=(config>>16)&65535
            health=((collateral*threshold*10**18+debt//2)//debt)//10000
            self.assertEqual(account,[health,collateral,debt,(config>>32)&65535]); self.assertEqual(words[43:],account)
            result=self.cli('calculate-aave-amounts',amount); self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),models['amount_expected']); self.assertEqual(words[22:25],[460,240,460])

    def test_emode_changes_health_bonus_and_amounts_before_both_payments(self):
        for example in self.examples.values():
            data=copy.deepcopy(example['input'])
            # Synthetic category 7 starts empty. Its mapping key is independently checked in Rust.
            base=113479202300186194305725673295787536031689033807992212058168757665848295403366
            pool=next(a for a in data['snapshot']['accounts'] if a['address']=='0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2')
            for offset in range(3): pool['storage'][str(base+offset)]='0'
            for index,value in {27:7,28:7500,29:9000,30:11000,31:4,32:1,33:4}.items(): self.replace_word(data,index,value)
            result=self.cli('simulate',data); self.assertEqual(result.returncode,0,result.stderr)
            out=json.loads(result.stdout); self.assertEqual(out['status'],'success')
            words=self.words(out['output']); collateral,debt=words[44:46]
            expected_health=((collateral*9000*10**18+debt//2)//debt)//10000
            self.assertEqual(words[43],expected_health); self.assertEqual(words[46],11000)
            amount=copy.deepcopy(example['models']['amount_input']); amount['health_factor_wad']=str(expected_health); amount['liquidation_bonus_bps']=11000
            expected=json.loads(self.cli('calculate-aave-amounts',amount).stdout)['amounts']
            self.assertEqual(words[37:43],[int(expected[k]) for k in ['max_liquidatable_debt','debt_to_liquidate','collateral_to_liquidator','protocol_fee_collateral','reserve_debt_base','reserve_collateral_base']])
            self.replace_word(data,29,11000); self.atomic(self.cli('simulate',data),'0x930bb771')

    def test_oracle_error_and_zero_prices_revert_all_initialized_reserves_and_copies(self):
        for example in self.examples.values():
            data=copy.deepcopy(example['input']); oracle=next(a for a in data['snapshot']['accounts'] if a['address']==builder.ORACLE)
            oracle['storage']['1']='1'; result=self.cli('simulate',data); self.assertEqual(result.returncode,0,result.stderr)
            error=json.loads(result.stdout)['output']; self.assertIn(b'synthetic oracle blocked'.hex(),error); self.atomic(result,error)
            oracle['storage']['1']='0'
            for k in oracle['storage']:
                if k!='1': oracle['storage'][k]='0'
            self.atomic(self.cli('simulate',data),'0x930bb771')

    def test_late_payment_failure_rolls_back_computed_account_and_all_transfers(self):
        for example in self.examples.values():
            data=copy.deepcopy(example['input'])
            token=next(a for a in data['snapshot']['accounts'] if a['address']==builder.sizing.prelude.delivery.payment.capture.USDC)
            token['storage']['1']=str(1<<160); result=self.cli('simulate',data); self.assertEqual(result.returncode,0,result.stderr)
            error=json.loads(result.stdout)['output']; self.assertIn(b'Pausable: paused'.hex(),error); self.atomic(result,error)

    def test_missing_oracle_and_price_storage_fail_closed_without_simulation_report(self):
        for example in self.examples.values():
            original=example['input']; oracle=next(a for a in original['snapshot']['accounts'] if a['address']==builder.ORACLE)
            for missing in [None]+[k for k in oracle['storage'] if k!='1']:
                data=copy.deepcopy(original); o=next(a for a in data['snapshot']['accounts'] if a['address']==builder.ORACLE)
                if missing is None: data['snapshot']['accounts'].remove(o)
                else: o['storage'].pop(missing)
                result=self.cli('simulate',data); self.assertNotEqual(result.returncode,0); self.assertEqual(result.stdout,'')


if __name__=='__main__': unittest.main()
