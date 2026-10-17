import copy
import json
import unittest
from BUILDER_BALANCE_GATE import HERE, BASE, evm_layer, evaluate, group_cash, frontier, value_documented
from build_evidence import load, local_gate

class BuilderGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.low=load('A2_C1_zero_cash'); cls.high=load('A2_C1_high_gas')
        cls.good=load('V06_builder_funds_own_refund'); cls.bad=load('V05_builder_funds_external_refund')
        cls.b=cls.low['actors']['simulated_builder']; cls.s=cls.low['actors']['sponsor_and_topup_financier']

    def test_V01_distinct_builder_income_is_not_financed_advance(self):
        g=local_gate(self.low,{self.b})
        self.assertEqual(g['builder_cash_delta_wei'],2*10**15)
        self.assertFalse(g['checks']['funding_from_builder_entity'])
        self.assertEqual(g['classification'],'REFUTED')
        self.assertEqual(evm_layer(self.low)['classification'],'PASS_LOCAL')

    def test_V02_high_gas_separate_financier_loses(self):
        l=evm_layer(self.high)['ledger']
        self.assertEqual(l['sponsor']['cash_margin_wei'],-1123326000000000)
        self.assertEqual(l['builder_cash_margin_wei'],2*10**15)
        self.assertEqual(local_gate(self.high,{self.b})['classification'],'REFUTED')

    def test_V03_explicit_ownership_consolidates_without_erasing_gas(self):
        l=evm_layer(self.low)['ledger']
        self.assertEqual(group_cash(l,[self.s,self.b,self.b]),45321588000000000)
        self.assertEqual(sum(s['gas_used'] for s in l['steps']),2339206)
        self.assertEqual(local_gate(self.low,{self.s,self.b})['classification'],'PASS_LOCAL')

    def test_V04_consolidated_21g_is_only_a_model(self):
        g=local_gate(self.high,{self.s,self.b})
        self.assertEqual(g['builder_after_lab_charge_wei'],846674000000000)
        self.assertEqual(g['classification'],'PASS_LOCAL')
        self.assertEqual(g['commercial_classification'],'UNKNOWN')
        self.assertIsNone(g['founder_max_recourse_wei'])

    def test_V05_successful_liquidation_does_not_imply_builder_profit(self):
        g=local_gate(self.bad,{self.b})
        self.assertEqual(g['EVM']['classification'],'PASS_LOCAL')
        self.assertEqual(g['builder_cash_delta_wei'],-4636412000000000)
        self.assertEqual(g['classification'],'REFUTED')
        l=evm_layer(self.bad)['ledger']
        self.assertEqual(l['balance_delta_by_address'][self.s]['ETH'],5*10**16)

    def test_V06_builder_actual_refund_and_five_transactions(self):
        g=local_gate(self.good,{self.b}); l=evm_layer(self.good)['ledger']
        self.assertEqual(g['builder_cash_delta_wei'],45363588000000000)
        self.assertEqual(g['classification'],'PASS_LOCAL')
        self.assertEqual(sum(t['gas_used'] for t in l['steps']),2318206)
        self.assertEqual(l['nqc']['initial'],{'ETH':0,'WETH':0,'COLLATERAL':0})
        self.assertEqual(l['nqc']['final']['ETH'],0)
        self.assertEqual(l['nqc']['liquidation_generated_WETH'],159365645570551238)
        self.assertEqual(l['sponsor']['U_actually_returned_wei'],25405588000000000)

    def test_V07_partial_topup_preserves_cash_loss_and_no_return(self):
        r=load('V07_partial_topup'); g=local_gate(r,{self.b}); l=evm_layer(r)['ledger']
        self.assertEqual(len(r['transactions']),1)
        self.assertEqual(len(r['accepted_not_included']),4)
        self.assertEqual(g['builder_cash_delta_wei'],-52000000000000)
        self.assertEqual(g['classification'],'REFUTED')
        self.assertEqual(l['sponsor']['U_actually_returned_wei'],0)
        self.assertEqual(l['nqc']['native_retained_advance_wei'],10**13)

    def test_V08_coinbase_unverified_and_fabricated_trace_rejected(self):
        g=local_gate(self.low,{self.s,self.b,self.low['actors']['proposer']})
        self.assertEqual(g['classification'],'UNKNOWN')
        self.assertIsNone(g['checks']['builder_identity_scoped'])
        forged=copy.deepcopy(self.good)
        forged['transactions'][0]['after'][self.b]['ETH']+=1
        with self.assertRaises(AssertionError): evm_layer(forged)

    def test_V09_value_documentation_is_not_acceptance(self):
        self.assertTrue(value_documented('Titan',1))
        self.assertIsNone(value_documented('Quasar',1))
        self.assertTrue(value_documented('Quasar',0))
        self.assertEqual(local_gate(self.good,{self.b},provider='Quasar',extra_sponsored_value_wei=1)['classification'],'UNKNOWN')

    def test_V10_real_identity_loss_limit_and_recourse_unknown(self):
        g=evaluate(self.good,{self.b},scope='UNVERIFIED_EXTERNAL')
        self.assertEqual(g['classification'],'UNKNOWN')
        self.assertIsNone(g['founder_max_recourse_wei'])
        self.assertEqual(g['real_builder_acceptance'],'NOT_TESTED')
        self.assertEqual(evaluate(self.good,{self.b},loss_cap_wei=10**18,founder_model_recourse_wei=1)['classification'],'REFUTED')

    def test_V11_optional_steps_and_existing_failures_fail_closed(self):
        for key in ('reverting_labels','dropping_labels'):
            self.assertEqual(local_gate(self.good,{self.b},**{key:['liquidate']})['classification'],'REFUTED')
        for name in ('A3_deploy_only','A3_omit_deploy','A3_healthy','A3_slippage_one_wei',
                     'A3_return_reject','A3_omit_return','A3_expired','A3_wrong_nonce',
                     'A3_fee_discrepancy','A3_refund_reject','A3_proposer_reject'):
            with self.subTest(prior_scenario=name):
                self.assertEqual(evm_layer(load(name))['classification'],'REFUTED')
        # Prior priority-order and no-inclusion controls, re-read/reconciled, not re-mined.
        self.assertEqual(evm_layer(load('A3_priority_change'))['classification'],'PASS_LOCAL')
        exclusion=json.loads((BASE/'evidence/policy-exclusion.json').read_text())
        for r in exclusion:
            self.assertEqual(r['actual_selected_transaction_count'],0)
            self.assertEqual(r['before']['balances'],r['after']['balances'])

    def test_V12_integer_frontier_and_request_nonce_tampering(self):
        f=frontier(self.good)
        self.assertGreater(f['last_positive']['margin_wei'],0)
        self.assertLessEqual(f['first_nonpositive']['margin_wei'],0)
        self.assertEqual(f['prefix_K'],4411179)
        self.assertEqual(f['first_nonpositive']['effective_fee_wei_per_gas'],f['last_positive']['effective_fee_wei_per_gas']+1)
        # Algebraically minimal advance: executor CREATE is the limiting prefix.
        p=f['last_positive']; price=p['effective_fee_wei_per_gas']
        self.assertEqual(p['minimum_advance_wei'],(411179+4000000)*price)
        forged=copy.deepcopy(self.good); forged['transactions'][2]['request']['nonce']='0x2'
        with self.assertRaises(AssertionError): evm_layer(forged)

if __name__=='__main__': unittest.main()
