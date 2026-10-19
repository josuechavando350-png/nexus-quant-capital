import unittest
from copy import deepcopy
from decimal import Decimal
from audit import analyze, run, units
import json
from pathlib import Path

CASE = json.loads((Path(__file__).resolve().parent / 'case.json').read_text())

class HistoricalCaseTests(unittest.TestCase):
    def test_exact_weth_trade_delta(self):
        self.assertEqual(run()['WETH_trade_spread'], '14.545268535920242038')
    def test_withdrawal_builder_settlement_once(self):
        self.assertEqual(run()['ETH_builder_transfer_backed_by_WETH_withdrawal'], '12.447536358167279703')
    def test_contract_weth_residual(self):
        self.assertEqual(run()['WETH_retained_in_executor_token_flow'], '2.097732177752962335')
    def test_post_gas_equivalent(self):
        self.assertEqual(run()['ETH_equivalent_post_listed_builder_and_gas_IF_economic_owner_same'], '1.915425887007584330')
    def test_gas_source_in_wei(self):
        self.assertEqual(602029 * units('302.819782345', 9), units('0.182306290745378005', 18))
    def test_usdc_dust_not_eth_profit(self):
        self.assertEqual(run()['USDC_dust_separately'], '0.000001')
    def test_flash_is_counterfactual(self):
        r=run()
        self.assertEqual(r['counterfactual_flash_extra_cost_max_bps_BEFORE_incremental_gas_sponsor_losses'], '71.775811')
        self.assertEqual(r['counterfactual_flash_5bp_fee_only_WETH'], '0.133431155132123430')
        self.assertEqual(r['counterfactual_residual_after_5bp_and_no_other_incremental_costs_ETH_equiv'], '1.781994731875460900')
        self.assertFalse(r['actual_flash_loan_or_sponsor_verified'])
    def test_no_NQC_profit(self):
        self.assertIsNone(run()['NQC_actual_profit'])
        self.assertFalse(run()['commercial_admission'])
    def test_dont_double_count_builder(self):
        r=run()
        self.assertNotEqual(r['ETH_equivalent_post_listed_builder_and_gas_IF_economic_owner_same'], '0')
        self.assertEqual(Decimal(r['WETH_trade_spread'])-Decimal(r['ETH_builder_transfer_backed_by_WETH_withdrawal'])-Decimal(r['ETH_gas_paid_by_different_EOA']),Decimal(r['ETH_equivalent_post_listed_builder_and_gas_IF_economic_owner_same']))
    def test_reject_builder_withdraw_mismatch(self):
        c=deepcopy(CASE); c['weth_withdrawal']='12.000000000000000000'
        with self.assertRaises(ValueError): analyze(c)
    def test_reject_usdc_deficit(self):
        c=deepcopy(CASE); c['usdc_repaid_to_morpho']='700000.000000'
        with self.assertRaises(ValueError): analyze(c)
    def test_reject_non_weth_token(self):
        c=deepcopy(CASE); c['weth_token']='0x123'
        with self.assertRaises(ValueError): analyze(c)
    def test_reject_wrong_gas(self):
        c=deepcopy(CASE); c['effective_gas_paid_eth']='0.182306290745378006'
        with self.assertRaises(ValueError): analyze(c)
    def test_reject_profit_type_overclaim(self):
        c=deepcopy(CASE); c['NQC_executed']=True
        with self.assertRaises(ValueError): analyze(c)
    def test_reject_floating_exponent(self):
        for value in ('1e10', 0.1, '-1', 'NaN', '0.0000000000000000001'):
            with self.assertRaises(ValueError): units(value, 18)
    def test_exact_initial_asset_outflow(self):
        self.assertEqual(run()['WETH_required_at_first_observed_swap_without_same_tx_inbound'], '266.862310264246861824')
    def test_source_scope_kept_conditional(self):
        self.assertIn('missing prestate',run()['scope'])
        self.assertIsNone(run()['historical_bundle_capturable_by_NQC'])

if __name__=='__main__': unittest.main(verbosity=2)
