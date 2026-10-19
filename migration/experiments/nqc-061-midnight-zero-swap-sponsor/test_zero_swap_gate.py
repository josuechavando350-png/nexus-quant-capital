import copy
import unittest
from zero_swap_gate import raw, structural_gate, economic_gate, evaluate, ETHEREUM_WETH

class GateTests(unittest.TestCase):
    def setUp(self):
        self.c = {
            'strategy': 'MORPHO_MIDNIGHT_POST_MATURITY_SAME_LOAN_AS_COLLATERAL',
            'chain_id': 1,
            'market_id': '0x'+'a'*64, 'borrower':'0x'+'b'*40,
            'loan_token': ETHEREUM_WETH,
            'collateral_token': ETHEREUM_WETH.upper().replace('0X', '0x'),
            'maturity_timestamp': '1000', 'canonical_block_timestamp': '1001',
            'borrower_debt_units': '100000', 'liquidator_gate': 'OPEN',
            'canonical_market_proven': True, 'canonical_position_proven': True,
            'block_membership_proven': True,
            'ledger': {'asset_address': ETHEREUM_WETH, 'cash_buckets_disjoint':True,
                 'seized_amount_is_received_in_callback':True,
                 'seized_raw':{'min':'110000','max':'110000'},
                 'repaid_raw':{'min':'100000','max':'100000'},
                 'loan_fee_raw':{'min':'0','max':'0'},
                 'token_bid_raw':{'min':'0','max':'0'}},
            'native': {'native_cost_buckets_disjoint':True,
                       'explicit_WETH_unwrap_and_ownership_proven':True,
                       'gas_actual_wei': {'min':'3000','max':'3000'},
                       'sponsor_remuneration_wei':{'min':'1000','max':'1000'},
                       'separate_inclusion_bid_wei':{'min':'1000','max':'1000'},
                       'sponsor_advance_cap_wei':'100000',
                       'max_gas_reserve_at_signed_prefix_wei':'100000'},
            'fixture_only':True,
        }
    def test_exact_potential_upper(self):
        e = economic_gate(self.c)
        self.assertEqual(e['loan_asset_upper_raw'],'10000')
        self.assertEqual(e['post_native_conditional_upper_wei'],'5000')
        self.assertEqual(e['result'],'CONDITIONAL_POSSIBLE_MARGIN_NOT_PROFIT')
    def test_zero_pnl_claim(self):
        x = evaluate(self.c)
        self.assertFalse(x['profit_authenticated'])
        self.assertFalse(x['commercial_admission'])
        self.assertFalse(x['sponsor_committed'])
    def test_gas_below_reserve_is_not_double_charged(self):
        x = evaluate(self.c)
        self.assertEqual(x['economic']['post_native_conditional_upper_wei'],'5000')
        self.assertFalse(x['economic']['gas_reserve_deducted_from_profit'])
    def test_strict_maturity_boundary(self):
        self.c['canonical_block_timestamp']='1000'
        self.assertEqual(evaluate(self.c)['final_decision'],'NOT_STRICTLY_POST_MATURITY')
    def test_unknown_market_gate(self):
        self.c['liquidator_gate']='UNKNOWN'
        self.assertEqual(evaluate(self.c)['final_decision'],'LIQUIDATOR_GATE_UNKNOWN')
    def test_restricted_market_without_permission(self):
        self.c['liquidator_gate']='RESTRICTED'
        self.assertEqual(evaluate(self.c)['final_decision'],'LIQUIDATOR_GATE_BLOCKED')
    def test_restricted_market_with_verified_permission(self):
        self.c['liquidator_gate']='RESTRICTED'
        self.c['gate_permission_proven']=True
        self.assertEqual(evaluate(self.c)['final_decision'],'CONDITIONAL_POSSIBLE_MARGIN_NOT_PROFIT')
    def test_missing_canonical_proofs_blocks(self):
        self.c['canonical_position_proven']=False
        self.assertEqual(evaluate(self.c)['final_decision'],'MISSING_CANONICAL_PROOFS')
    def test_asset_mismatch_requires_swap(self):
        self.c['collateral_token']='0x'+'c'*40
        self.assertEqual(evaluate(self.c)['final_decision'],'REQUIRES_COLLATERAL_SALE_NOT_SWAP_FREE')
    def test_chain_mismatch(self):
        self.c['chain_id']=8453
        self.assertEqual(evaluate(self.c)['final_decision'],'NOT_ETHEREUM_MAINNET')
    def test_debt_zero(self):
        self.c['borrower_debt_units']='0'
        self.assertEqual(evaluate(self.c)['final_decision'],'NO_BORROWER_DEBT')
    def test_loan_token_upper_nonpositive(self):
        self.c['ledger']['seized_raw']={'min':'90000','max':'90000'}
        self.assertEqual(evaluate(self.c)['final_decision'],'REJECT_LOAN_ASSET_UPPER_NONPOSITIVE')
    def test_after_native_cost_negative_even_if_gross_positive(self):
        self.c['native']['gas_actual_wei']={'min':'9000','max':'9000'}
        self.assertEqual(evaluate(self.c)['final_decision'],'REJECT_AFTER_NATIVE_MINIMUM_UPPER_NONPOSITIVE')
    def test_missing_sponsor_cost_is_unknown(self):
        self.c['native']['sponsor_remuneration_wei']={'min':None,'max':None}
        self.assertEqual(evaluate(self.c)['final_decision'],'NATIVE_COSTS_UNKNOWN')
        self.assertIsNone(evaluate(self.c)['economic']['post_native_conditional_upper_wei'])
    def test_unknown_native_bridge_does_not_sum_eth_usdc(self):
        self.c['native']['explicit_WETH_unwrap_and_ownership_proven']=False
        self.assertEqual(evaluate(self.c)['final_decision'],'NATIVE_GAS_BRIDGE_UNVERIFIED')
    def test_same_asset_usdc_still_needs_eth_bridge(self):
        self.c['loan_token']='0x'+'d'*40
        self.c['collateral_token']='0x'+'d'*40
        self.c['ledger']['asset_address']='0x'+'d'*40
        self.assertEqual(evaluate(self.c)['final_decision'],'NATIVE_GAS_BRIDGE_UNVERIFIED')
    def test_no_valid_sponsor_cap(self):
        self.c['native']['sponsor_advance_cap_wei']='19999'
        self.assertEqual(evaluate(self.c)['final_decision'],'REJECT_SPONSOR_CAP_BELOW_PREFIX_RESERVE')
    def test_missing_max_reserve_is_not_zero(self):
        self.c['native']['max_gas_reserve_at_signed_prefix_wei']=None
        self.assertEqual(evaluate(self.c)['economic']['prefunding_vs_max_gas_reserve'],'UNKNOWN')
        self.assertEqual(evaluate(self.c)['final_decision'],'SPONSOR_PREFUNDING_CAP_UNKNOWN')
    def test_no_false_positive_if_no_bound_on_collateral(self):
        self.c['ledger']['seized_raw']['max']=None
        self.assertEqual(evaluate(self.c)['final_decision'],'INCOMPLETE_LOAN_LEDGER')
    def test_invalid_floats_scientific_and_negative(self):
        for value in (1.23, 1, -1, '-1', '+1', '1e3', '01', True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError): raw(value, 'test')
    def test_error_on_overlapping_cost_buckets(self):
        self.c['native']['native_cost_buckets_disjoint']=False
        with self.assertRaises(ValueError):evaluate(self.c)
    def test_error_on_missing_pre_callback_receipt(self):
        self.c['ledger']['seized_amount_is_received_in_callback']=False
        with self.assertRaises(ValueError): evaluate(self.c)
    def test_error_bad_bounds(self):
        self.c['ledger']['seized_raw']={'min':'110000','max':'10000'}
        with self.assertRaises(ValueError):evaluate(self.c)
    def test_gas_not_implied_zero_if_no_receipt(self):
        self.c['native']['gas_actual_wei']={'min':None,'max':None}
        self.assertEqual(evaluate(self.c)['final_decision'],'NATIVE_COSTS_UNKNOWN')
    def test_no_lender_commitment_implied_by_positive_gross(self):
        self.c['native']['sponsor_advance_cap_wei']=None
        self.assertFalse(evaluate(self.c)['sponsor_committed'])
        self.assertEqual(evaluate(self.c)['economic']['prefunding_vs_max_gas_reserve'],'UNKNOWN')
        self.assertEqual(evaluate(self.c)['final_decision'],'SPONSOR_PREFUNDING_CAP_UNKNOWN')

if __name__ == '__main__': unittest.main()
