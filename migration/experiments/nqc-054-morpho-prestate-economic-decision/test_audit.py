import copy
from fractions import Fraction
import unittest
import audit as a


class ModifiedSources:
    def __init__(self, source, name, value):
        self.source,self.name,self.value=source,name,value
    def json(self,name):
        return copy.deepcopy(self.value) if name==self.name else self.source.json(name)
    def raw(self,name):
        return self.source.raw(name)


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources=a.Sources()
        cls.result=a.analyze(cls.sources)
        cls.trace=cls.sources.json('evidence/2026-10-17/case_b_trace.json')

    def test_delegatecode_uses_callers_storage_context(self):
        tree,contexts=a.trace_contexts(self.trace)
        separated=[p for p,r in tree.items() if r['action']['callType']=='delegatecall'
                   and contexts[p]!=r['action']['to']]
        self.assertTrue(separated)
        for p in separated:self.assertEqual(contexts[p],contexts[p[:-1]])
        self.assertEqual(len(tree),158)
        self.assertEqual(len(set(contexts.values())),28)
        self.assertEqual(len({r['action']['to'] for r in tree.values()}),47)

    def test_missing_subcall_cannot_shrink_witness_requirement(self):
        trace=copy.deepcopy(self.trace);trace['data']['items'].pop()
        with self.assertRaises(ValueError):a.trace_contexts(trace)

    def test_wrong_delegate_sender_is_rejected(self):
        trace=copy.deepcopy(self.trace)
        row=next(t for t in trace['data']['items'] if t['action']['callType']=='delegatecall')
        row['action']['from']='0x'+'1'*40
        with self.assertRaisesRegex(ValueError,'caller context'):a.trace_contexts(trace)

    def test_robinhood_trace_cannot_enter_ethereum_analysis(self):
        trace=copy.deepcopy(self.trace);trace['request']['chain_id']='4663'
        with self.assertRaisesRegex(ValueError,'trace identity'):a.trace_contexts(trace)

    def test_pagination_prevents_complete_call_graph_claim(self):
        trace=copy.deepcopy(self.trace);trace['pagination']={'next':'unknown'}
        with self.assertRaises(ValueError):a.trace_contexts(trace)

    def test_parent_end_root_cannot_be_called_pretransaction_state(self):
        p=self.result['prestate']
        self.assertFalse(p['historical_replay_attempted'])
        self.assertFalse(p['complete_storage_access_set_known'])
        self.assertTrue(all(r['authenticated_pre_tx1_value'] is None and r['proof'] is None
                            for r in p['exact_known_slot_requirements']))
        self.assertEqual(len(p['exact_known_slot_requirements']),14)
        self.assertEqual(len(p['account_inventory']),50)

    def test_exact_slot_keys_are_delimited_by_account(self):
        slots=self.result['prestate']['exact_known_slot_requirements']
        self.assertEqual(len({(r['account'],r['slot']) for r in slots}),14)
        by_name={r['meaning']:r for r in slots}
        self.assertEqual(by_name['borrower.borrowShares/collateral']['slot'],
            '0xd23fc2386c6cfb569ad04c9a083d19ed21cabfeaf9d188c89af9ba0ba2cc698c')
        self.assertEqual(by_name['exchangePriceToken0Slot']['account'],a.LIQUIDITY)
        self.assertFalse(by_name['marketParams.oracle']['layout_runtime_binding_verified'])

    def test_packing_does_not_silently_truncate_overflow(self):
        with self.assertRaisesRegex(ValueError,'uint128'):
            a.derive_morpho_slots('0x'+'0'*64,'0x'+'0'*40,[2**128,0,0,0,0,0],[0,0,0],[0]*5)

    def test_prefix_gas_is_only_a_cumulative_receipt_inference(self):
        prefix=self.result['prestate']['prefix'][0]
        self.assertEqual(prefix['inferred_gas_from_B_receipt'],243495)
        self.assertEqual(prefix['input_bytes'],740)
        self.assertIsNone(prefix['receipt']);self.assertIsNone(prefix['state_diff'])
        self.assertFalse(prefix['executed'])

    def test_wrong_prefix_cannot_be_omitted(self):
        name='evidence/2026-10-17-profitability/b-block.json.gz'
        block=self.sources.json(name);block['response']['result']['transactions'][0]['hash']='0x'+'0'*64
        with self.assertRaisesRegex(ValueError,'prefix order'):
            a.witness_boundary(ModifiedSources(self.sources,name,block))

    def test_cross_market_position_read_is_rejected(self):
        trace=copy.deepcopy(self.trace)
        row=next(t for t in trace['data']['items'] if t['traceAddress']==[0,0])
        row['action']['input']=row['action']['input'][:10]+'0'*64+row['action']['input'][74:]
        with self.assertRaisesRegex(ValueError,'position identity'):
            a.witness_boundary(ModifiedSources(self.sources,'evidence/2026-10-17/case_b_trace.json',trace))

    def test_positive_upper_bound_does_not_prove_viability(self):
        self.assertEqual(a.classify_upper_bound(1),a.INSUFFICIENT)
        self.assertEqual(a.classify_upper_bound(0),a.DISCARDED)
        self.assertEqual(self.result['economics']['case_B_decision'],a.INSUFFICIENT)

    def test_one_basis_point_cannot_be_saved_by_gas_optimization(self):
        scenario=self.result['economics']['scenarios'][2]
        self.assertEqual(scenario['upper_bound_even_if_gas_zero_wei'],-754261612795662)
        self.assertEqual(scenario['decision'],a.DISCARDED)
        self.assertFalse(scenario['all_Morpho_liquidations_discarded'])
        self.assertFalse(scenario['real_financing_offer_evidenced'])
        for rate in (1,2,10,100):
            self.assertGreaterEqual(a.fee_ceiling(26039738525656992415,rate),scenario['fee_wei'])

    def test_zero_financing_is_not_assumed_available(self):
        scenario=self.result['economics']['scenarios'][0]
        self.assertEqual(scenario['decision'],a.INSUFFICIENT)
        self.assertIsNone(self.result['economics']['funding']['sponsor_premium'])
        self.assertIsNone(self.result['economics']['funding']['gas_sponsor_commitment'])
        with self.assertRaises(ValueError):a.fee_ceiling(1,-1)

    def test_allowance_of_another_spender_is_not_executor_readiness(self):
        trace=copy.deepcopy(self.trace)
        row=next(t for t in trace['data']['items'] if t['traceAddress']==[0,1,1])
        row['action']['input']=row['action']['input'][:74]+'0'*64
        with self.assertRaisesRegex(ValueError,'funding read identity'):
            a.economics(ModifiedSources(self.sources,'evidence/2026-10-17/case_b_trace.json',trace))

    def test_competitive_bid_cannot_be_claimed_as_nqc_income(self):
        e=self.result['economics'];c=e['competition_boundary']
        self.assertEqual(c['required_bid_reduction_for_double_residual_wei'],1651296044494913)
        self.assertIsNone(c['acceptance_of_lower_bid']);self.assertIsNone(c['capture_probability'])
        self.assertLess(Fraction(e['max_gain_fraction_of_observed_residual']),Fraction(13,100))

    def test_case_C_is_counted_once_and_receipt_gaps_not_zero_cost(self):
        c=self.result['candidates'];tx=c['case_C']['tx_hash']
        self.assertEqual(sum(r['tx_hash']==tx for r in c['monthly_transactions']),1)
        self.assertEqual(c['monthly_receipt_coverage'],{'AVAILABLE':1,'OBSERVED_NULL':23,'NO_ARCHIVED_RECEIPT_IDENTIFIED':117})
        self.assertTrue(all(r['net_margin'] is None for r in c['monthly_transactions']))
        self.assertEqual(c['older_case_A']['prefix_transactions_required'],226)
        self.assertEqual(c['case_C']['decision'],a.INSUFFICIENT)

    def test_later_mixed_state_and_other_market_proof_are_excluded(self):
        excluded=self.result['candidates']['excluded_state_sources']
        self.assertEqual(set(excluded[0]['indexed_blocks'].values()),{26210229,26210230,26210231})
        self.assertNotEqual(excluded[1]['market_id'],self.result['prestate']['market_id'])
        self.assertNotEqual(excluded[1]['block'],26190954)

    def test_monthly_targets_have_no_invented_forecast(self):
        m=self.result['monthly_evidence']
        self.assertEqual(m['targets_usd'],[5000,15000,45000])
        self.assertIsNone(m['forecast_usd']);self.assertIsNone(m['demonstrated_NQC_net_per_capture'])
        self.assertIsNone(m['demonstrated_capturable_frequency'])
        self.assertEqual(self.result['status']['triport_total_known'],0)
        self.assertFalse(self.result['status']['commercial_admission'])


if __name__=='__main__':
    unittest.main()
