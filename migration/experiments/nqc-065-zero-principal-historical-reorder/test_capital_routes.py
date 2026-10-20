import unittest, copy, json
from pathlib import Path
from capital_routes import analyze, run, to_units, fixed

HERE=Path(__file__).resolve().parent
CASE=json.loads((HERE/'case.json').read_text(encoding='utf-8'))

class TestExactCapitalCases(unittest.TestCase):
    def test_source_linked(self):
        o=run(); self.assertEqual(o['historical_tx_hash'],CASE['tx_hash'])
    def test_first_capital_required_original(self):
        self.assertEqual(run()['original_prefunded_WETH_leg'],'266.862310264246861824')
    def test_c1_sale_proceeds_cover_same_amount(self):
        self.assertEqual(run()['hypothesis_C1_collateral_first']['first_WETH_from_reordered_sale_if_same_V3_fill'],'281.407578800167103862')
    def test_c1_debt_cover_under_fixed_quotes(self):
        self.assertTrue(run()['hypothesis_C1_collateral_first']['USDC_cover_at_same_V2_swap_fill'])
    def test_c1_dust_precise(self):
        self.assertEqual(run()['observed_USDC_dust'],'0.000001')
    def test_c1_unproven(self):
        self.assertFalse(run()['hypothesis_C1_collateral_first']['proof_of_executable_historical_reorder'])
    def test_flash_zero_fee_documentary(self):
        self.assertEqual(run()['hypothesis_Morpho_zero_fee_flash_WETH']['protocol_flash_premium_as_documented'],'0')
    def test_flash_liquidity_unknown(self):
        self.assertFalse(run()['hypothesis_Morpho_zero_fee_flash_WETH']['contract_balance_at_historical_prestate_verified'])
    def test_flash_margin_conditional(self):
        self.assertEqual(run()['hypothesis_Morpho_zero_fee_flash_WETH']['remaining_margin_before_incremental_flash_gas_sponsor'],'1.915425887007584330')
    def test_historical_pnl_reconciles(self):
        self.assertEqual(run()['conditional_same_economic_owner_post_historical_gas_ETH_equiv'],'1.915425887007584330')
    def test_5bp_is_sensitivity_not_quote(self):
        self.assertEqual(run()['illustrative_Aave_initial_5bp_premium_only'],'0.133431155132123430')
    def test_margin_5bp(self):
        self.assertEqual(run()['margin_with_illustrative_Aave_5bp_before_incremental_costs'],'1.781994731875460900')
    def test_price_haircut_zero(self):
        self.assertEqual(run()['haircut_sensitivity_bp']['0']['after_original_bid_gas_conditional_ETH_equivalent'],'1.915425887007584330')
    def test_price_haircut_100bp_is_negative(self):
        self.assertTrue(run()['haircut_sensitivity_bp']['100']['after_original_bid_gas_conditional_ETH_equivalent'].startswith('-'))
    def test_price_haircut_75bp_is_negative(self):
        self.assertTrue(run()['haircut_sensitivity_bp']['75']['after_original_bid_gas_conditional_ETH_equivalent'].startswith('-'))
    def test_threshold_less_than_100bp(self):
        self.assertLess(float(run()['max_synthetic_UNI_exit_haircut_bp_if_all_else_unchanged_no_flash']),100)
    def test_asset_identity_rejected(self):
        c=copy.deepcopy(CASE);c['weth_token']='0x'+'0'*40
        with self.assertRaises(ValueError):analyze(c)
    def test_mainnet_only(self):
        c=copy.deepcopy(CASE);c['chain_id']=8453
        with self.assertRaises(ValueError):analyze(c)
    def test_unproven_flash_disallowed(self):
        c=copy.deepcopy(CASE);c['flash_loan_verified']=True
        with self.assertRaises(ValueError):analyze(c)
    def test_wrong_builder_backed_payout_rejected(self):
        c=copy.deepcopy(CASE);c['eth_transfer_to_beaverbuild']='12.44'
        with self.assertRaises(ValueError):analyze(c)
    def test_bad_gas_rejected(self):
        c=copy.deepcopy(CASE);c['effective_gas_paid_eth']='0.182'
        with self.assertRaises(ValueError):analyze(c)
    def test_unrealistic_debt_repay_rejected(self):
        c=copy.deepcopy(CASE);c['usdc_repaid_to_morpho']='616688'
        with self.assertRaises(ValueError):analyze(c)
    def test_wrong_uni_balance_rejected(self):
        c=copy.deepcopy(CASE);c['uni_seized_from_morpho']='94718'
        with self.assertRaises(ValueError):analyze(c)
    def test_non_decimal_precision_rejected(self):
        for v in ('nan','-1','1e20','0.0000000000000000001'):
            with self.assertRaises(ValueError):to_units(v,18)
    def test_actor_ownership_not_inferred(self):
        o=run();self.assertFalse(o['financier_committed']);self.assertIsNone(o['NQC_realized_profit']);self.assertFalse(o['commercial_admission'])
    def test_no_canary(self):
        self.assertFalse(run()['canary_enabled'])

if __name__=='__main__':unittest.main()
