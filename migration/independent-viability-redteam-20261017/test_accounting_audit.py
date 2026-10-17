"""Independent adversarial accounting checks; no original NQC test suite."""
import copy
import itertools
import json
import unittest
from fractions import Fraction

import accounting_audit as a


class AccountingAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = a.load_inputs()
        cls.reconciled = a.reconcile_saved_case_b(cls.inputs)
        cls.case = cls.inputs['case_b']
        cls.fixed = [a.uint(cls.case[k]) for k in ['sale_wei','debt_wei','coinbase_wei','gas_units','gas_price_wei']]
        cls.controls = a.falsification_controls(cls.inputs,cls.reconciled)

    def test_t01_zero_principal_needs_real_first_gas_payer(self):
        self.assertEqual(self.controls['T-01']['guardrail_status'],'PASS')
        unpaid = [{'name':'principal','amount':0,'payer':None}, {'name':'gas','amount':50,'payer':None}]
        self.assertIs(a.first_operation_covered(unpaid),a.Truth.UNKNOWN)
        unpaid[1]['payer']='founder'
        self.assertIs(a.first_operation_covered(unpaid),a.Truth.FALSE)
        unpaid[1].update(payer='external_sponsor',commitment=a.Truth.TRUE,nonrecourse=a.Truth.TRUE)
        self.assertIs(a.first_operation_covered(unpaid),a.Truth.TRUE)
        unpaid.append({'name':'deployment','amount':None,'payer':None})
        self.assertIs(a.first_operation_covered(unpaid),a.Truth.UNKNOWN)

    def test_t02_deferred_bill_is_founder_debt(self):
        self.assertEqual(self.controls['T-02']['guardrail_status'],'PASS')
        self.assertIs(a.nonrecourse(0,1,0),a.Truth.FALSE)
        self.assertIs(a.nonrecourse(0,None,0),a.Truth.UNKNOWN)

    def test_t03_isolated_topup_return_does_not_refund_network_gas(self):
        self.assertEqual(self.controls['T-03']['guardrail_status'],'PASS')
        self.assertEqual(a.builder_margin(A=100,U=100,R=0,V=0,F=2,P=0,O=0),-2)
        self.assertIs(a.nonrecourse(None),a.Truth.UNKNOWN)

    def test_t04_coinbase_payment_has_no_verified_builder_or_nqc_owner(self):
        self.assertEqual(self.controls['T-04']['guardrail_status'],'PASS')
        self.assertEqual(self.reconciled['coinbase_wei'],368092735714237547)
        self.assertNotEqual(self.case['executor'],self.case['coinbase'])
        self.assertIs(a.nqc_realization('UNKNOWN',a.Truth.TRUE,a.Truth.TRUE),a.Truth.UNKNOWN)

    def test_t05_gas_boundary_and_three_gwei(self):
        self.assertEqual(self.controls['T-05']['guardrail_status'],'PASS')
        sale,debt,bid,gas,price=self.fixed
        limit=a.gas_frontier(sale,debt,bid,gas,0)
        self.assertEqual(limit,2481140052)
        self.assertGreater(a.residual(sale,debt,bid,gas,limit,0),0)
        self.assertLessEqual(a.residual(sale,debt,bid,gas,limit+1,0),0)
        self.assertEqual(a.residual(sale,debt,bid,gas,3000000000,0),-386814760229962)
        self.assertEqual(a.residual(sale,debt,bid,gas,price,0),1651296044494913)

    def test_t06_paymaster_bundler_consolidation(self):
        self.assertEqual(self.controls['T-06']['guardrail_status'],'PASS')
        pm,network=79616762214000,57601054408000
        flows=[{'id':'p','asset':'ETH','from':'paymaster','to':'bundler','amount':pm},
               {'id':'g','asset':'ETH','from':'bundler','to':'network','amount':network}]
        self.assertEqual(a.transfer_deltas(flows,{'paymaster'},'ETH'),-pm)
        self.assertEqual(a.transfer_deltas(flows,{'bundler'},'ETH'),22015707806000)
        self.assertEqual(a.transfer_deltas(flows,{'paymaster','bundler'},'ETH'),-network)
        self.assertEqual(sum(a.transfer_deltas(flows,{x},'ETH') for x in ['paymaster','bundler','network']),0)
        with self.assertRaises(ValueError):
            a.transfer_deltas(flows+[flows[0]],{'paymaster'},'ETH')

    def test_source_eth_fee_decimals_match_wei_without_scale_loss(self):
        self.assertEqual(a.decimal_units_to_raw('0.000057601054408',18),57601054408000)
        self.assertEqual(a.decimal_units_to_raw('0.000079616762214',18),79616762214000)
        self.assertEqual(a.reconcile_robinhood_reported(self.inputs)['native_network_fee_wei'],57601054408000)
        malformed=copy.deepcopy(self.inputs)
        malformed['robinhood']['native_network_fee_wei']='57601054408'
        with self.assertRaises(ValueError):
            a.reconcile_robinhood_reported(malformed)
        with self.assertRaises(ValueError):
            a.decimal_units_to_raw('0.0000000000000000001',18)

    def test_t07_incoherent_heights_or_hashes_cannot_certify_state(self):
        self.assertEqual(self.controls['T-07']['guardrail_status'],'PASS')
        first,second='0x'+'a'*64,'0x'+'b'*64
        self.assertIs(a.coherent_state([1,1],[first,second]),a.Truth.FALSE)
        self.assertIs(a.coherent_state([1,1],[first,None]),a.Truth.UNKNOWN)
        self.assertIs(a.coherent_state([1,1],[first,first]),a.Truth.TRUE)

    def test_malformed_equal_hashes_cannot_certify_state(self):
        for malformed in ['x','0xabc','0x'+'z'*64,False]:
            with self.assertRaises(ValueError):
                a.coherent_state([1,1],[malformed,malformed])

    def test_t08_saved_getlogs_empty_contradicts_saved_positive_receipt(self):
        self.assertEqual(self.controls['T-08']['guardrail_status'],'PASS')
        env=a.snapshot(self.inputs,'case_b_saved_getlogs')
        self.assertEqual(env['response']['result'],[])
        self.assertIs(a.known_positive_coverage(self.reconciled['known_liquidation_log'],[]),a.Truth.FALSE)
        self.assertIs(a.known_positive_coverage(self.reconciled['known_liquidation_log'],None),a.Truth.UNKNOWN)

    def test_known_positive_identity_does_not_override_changed_log_contents(self):
        expected=self.reconciled['known_liquidation_log']
        self.assertIs(a.known_positive_coverage(expected,[expected]),a.Truth.TRUE)
        for field,value in [('data','0x00'),('address','0x'+'1'*40),('topics',['0x'+'a'*64]),
                            ('blockHash','0x'+'b'*64),('blockNumber','0x1'),('removed',True)]:
            changed=copy.deepcopy(expected);changed[field]=value
            self.assertIs(a.known_positive_coverage(expected,[changed]),a.Truth.FALSE)
        changed=copy.deepcopy(expected);changed['logIndex']='0x09'
        with self.assertRaises(ValueError):
            a.known_positive_coverage(expected,[changed])
        with self.assertRaises(ValueError):
            a.known_positive_coverage(expected,[expected,expected])

    def test_t09_positive_owner_net_still_rejected_when_founder_owes(self):
        self.assertEqual(self.controls['T-09']['guardrail_status'],'PASS')
        terms=dict(initial_assets=0,final_assets=5,initial_direct_liabilities=0,final_direct_liabilities=1,
                   initial_contingent_liabilities=0,final_contingent_liabilities=0,capital_added=0,donations_added=0,distributions=0)
        self.assertEqual(a.owner_margin(**terms),4)
        self.assertIs(a.eligible(4,1,0,a.nonrecourse(1),a.Truth.TRUE,a.Truth.TRUE),a.Truth.FALSE)

    def test_t10_third_party_pnl_is_excluded_from_nqc(self):
        self.assertEqual(self.controls['T-10']['guardrail_status'],'PASS')
        self.assertIs(a.nqc_realization('THIRD_PARTY',a.Truth.TRUE,a.Truth.TRUE),a.Truth.FALSE)

    def test_unknowns_propagate_and_cannot_be_used_as_python_booleans(self):
        for condition in a.Truth:
            with self.assertRaises(TypeError):
                bool(condition)
        self.assertIs(a.tri_and(a.Truth.TRUE,a.Truth.UNKNOWN),a.Truth.UNKNOWN)
        self.assertIs(a.tri_and(a.Truth.FALSE,a.Truth.UNKNOWN),a.Truth.FALSE)
        self.assertIs(a.eligible(1,None,0,a.Truth.TRUE,a.Truth.TRUE,a.Truth.TRUE),a.Truth.UNKNOWN)
        self.assertIsNone(a.residual(*self.fixed,None))
        self.assertIsNone(a.builder_margin(A=1,U=0,R=2,V=None,F=0,P=0,O=0))
        with self.assertRaises(ValueError):
            a.tri_and(True,a.Truth.UNKNOWN)

    def test_every_additional_positive_cost_reduces_residual_exactly(self):
        base=a.residual(*self.fixed,0)
        for extra in [1,2,100,base-1,base,base+1,10**18]:
            self.assertEqual(a.residual(*self.fixed,extra),base-extra)
        self.assertEqual(a.residual(*self.fixed,base),0)
        self.assertEqual(a.residual(*self.fixed,base-1),1)

    def test_gas_frontier_exhaustive_small_integer_independent_enumeration(self):
        for sale,debt,bid,gas,extra in itertools.product(range(0,13),range(0,4),range(0,4),range(1,5),range(0,3)):
            passing=[p for p in range(0,20) if sale-debt-bid-extra-gas*p>0]
            self.assertEqual(a.gas_frontier(sale,debt,bid,gas,extra),max(passing) if passing else None)

    def test_preexisting_balances_and_donations_are_not_earned_margin(self):
        terms=dict(initial_assets=10,final_assets=20,initial_direct_liabilities=0,final_direct_liabilities=0,
                   initial_contingent_liabilities=0,final_contingent_liabilities=0,capital_added=4,donations_added=6,distributions=0)
        self.assertEqual(a.owner_margin(**terms),0)
        terms['initial_assets']=None
        self.assertIsNone(a.owner_margin(**terms))
        terms.update(initial_assets=10,final_contingent_liabilities=None)
        self.assertIsNone(a.owner_margin(**terms))

    def test_paid_reimbursement_is_not_also_terminal_liability(self):
        common=dict(initial_assets=0,initial_direct_liabilities=0,initial_contingent_liabilities=0,
                    final_contingent_liabilities=0,capital_added=0,donations_added=0,distributions=0)
        unpaid=a.owner_margin(**common,final_assets=15,final_direct_liabilities=10)
        settled=a.owner_margin(**common,final_assets=5,final_direct_liabilities=0)
        self.assertEqual(unpaid,settled)
        self.assertEqual(unpaid,5)

    def test_builder_costs_and_unused_advance_are_not_duplicated(self):
        self.assertEqual(a.builder_margin(A=100,U=20,R=90,V=5,F=2,P=3,O=1),9)
        with self.assertRaises(ValueError):
            a.builder_margin(A=100,U=101,R=0,V=0,F=0,P=0,O=0)

    def test_token_peg_is_not_assumed_or_float_rounded(self):
        self.assertIsNone(a.realizable_usd('32.060665',None,None))
        self.assertEqual(a.realizable_usd('32.060665','0.95','0.1'),Fraction('30.35763175'))
        with self.assertRaises(ValueError):
            a.realizable_usd('32.060665',0.95,'0.1')

    def test_exact_ceil_has_integer_boundary_and_rejects_nonpositive_margin(self):
        self.assertEqual(a.required_wins('1000','0','3'),334)
        self.assertEqual(a.required_wins('1000','0','0.1'),10000)
        self.assertEqual(a.required_wins('1000','100','10'),110)
        for m in ['0','-1']:
            with self.assertRaises(ValueError):
                a.required_wins('1000','0',m)
        self.assertIsNone(a.required_wins('1000',None,'1'))

    def test_economic_inputs_reject_lossy_numbers_and_bools(self):
        for value in [True,False,1.0,'1.0','01','1e18','',None]:
            with self.assertRaises(ValueError):
                a.exact_int(value)
        with self.assertRaises(ValueError):
            a.residual(1,0,0,0,1,0)

    def test_immutable_source_blobs_and_duplicate_logs(self):
        digests=a.source_digests(self.inputs)
        self.assertTrue(digests['case_b_saved_receipt']['full_blob_identity_checked'])
        mutated=copy.deepcopy(self.inputs)
        raw=a.snapshot(mutated,'case_b_saved_receipt')
        raw['response']['result']['logs'].append(raw['response']['result']['logs'][0])
        mutated['source_snapshots']['case_b_saved_receipt']['content_utf8']=json.dumps(raw)
        with self.assertRaises(ValueError):
            a.source_digests(mutated)
        with self.assertRaises(ValueError):
            a.reconcile_saved_case_b(mutated)

    def test_wrong_block_context_cannot_be_accounting_match(self):
        mutated=copy.deepcopy(self.inputs)
        mutated['case_b']['block_number']+=1
        with self.assertRaises(ValueError):
            a.reconcile_saved_case_b(mutated)

    def test_saved_flow_deltas_exclude_old_weth_and_keep_unknown_ownership(self):
        self.assertEqual(self.reconciled['executor_native_delta_wei'],0)
        self.assertEqual(self.reconciled['executor_collateral_delta_raw'],0)
        self.assertEqual(self.reconciled['final_weth_inferred_wei']-self.reconciled['initial_weth_wei'],1849712239770038)
        self.assertFalse(self.reconciled['sender_executor_ownership_proved'])
        self.assertFalse(self.reconciled['nqc_profit_certified'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
