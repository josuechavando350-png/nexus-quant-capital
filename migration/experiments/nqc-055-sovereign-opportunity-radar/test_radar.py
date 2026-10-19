"""Archived reference regression plus adversarial inputs; no market backtest."""
import copy
from dataclasses import replace
import json
import random
import unittest
from unittest.mock import patch

import core
from core import Asset, Cost, Interval, Registry, Sources, bounds, canonical, digest, units
from morpho import ETH, MorphoArchive, TX_B, b_ledger, normalize_event
import radar


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Sources()
        cls.report = radar.run(cls.s)
        cls.candidates = cls.report['candidates']
        cls.b = next(c for c in cls.candidates if c['tx_hash'] == TX_B)

    def ledger(self):
        return b_ledger(self.s)

    def test_archived_membership_143_events_141_transactions_plus_A(self):
        d = self.report['evaluation']['event_deduplication']
        self.assertEqual((d['original_observation_rows_processed'], d['monthly_unique_events'], d['monthly_unique_transactions']), (145,143,141))
        self.assertEqual(len(self.candidates),142)

    def test_two_authentic_duplicate_events_merged(self):
        self.assertEqual(self.report['evaluation']['event_deduplication']['duplicate_events_merged'],2)
        self.assertEqual(sum(c['tx_hash']==TX_B for c in self.candidates),1)

    def test_duplicate_dossiers_do_not_add_opportunities(self):
        r=Registry()
        for c in self.candidates+self.candidates:r.add(c)
        self.assertEqual(len(r.ordered()),142);self.assertEqual(r.duplicates,142)

    def test_conflicting_duplicate_fails_closed(self):
        r=Registry();r.add(self.b)
        conflict=copy.deepcopy(self.b);conflict['block']+=1
        with self.assertRaisesRegex(ValueError,'conflicting duplicate'):r.add(conflict)

    def test_duplicate_JSON_identifier_rejected(self):
        with self.assertRaises(ValueError):core.parse('{"chain":1,"chain":4663}')

    def test_source_hash_mutation_rejected(self):
        manifest=copy.deepcopy(self.s.manifest);manifest['files']['economics']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'hash mismatch'):Sources(manifest).json('economics')

    def test_source_blob_mutation_rejected(self):
        manifest=copy.deepcopy(self.s.manifest);manifest['files']['economics']['git_blob_sha1']='0'*40
        with self.assertRaisesRegex(ValueError,'blob mismatch'):Sources(manifest).json('economics')

    def test_source_pointer_must_exist(self):
        with self.assertRaises(KeyError):self.s.ref('audit','/invented')

    def test_original_event_chain_cannot_be_robinhood(self):
        r=self.s.json('page0')['response']['data']['marketTransactions']['items'][0]
        r['chain']['id']=4663
        with self.assertRaisesRegex(ValueError,'chain/type'):normalize_event(r)

    def test_float_raw_amount_rejected(self):
        r=self.s.json('page0')['response']['data']['marketTransactions']['items'][0]
        r['data']['repaidAssets']=1.0
        with self.assertRaises(ValueError):normalize_event(r)

    def test_decimal_precision_exact(self):
        self.assertEqual(units('0.001651296044494913',18),1651296044494913)
        self.assertEqual(units('0.513394',6),513394)
        self.assertEqual(units('999999999999999999999.000001',6),999999999999999999999000001)

    def test_decimal_truncation_float_and_exponent_rejected(self):
        for text in ('0.0000001',1.1,'1e6','-1'):
            with self.subTest(text=text),self.assertRaises(ValueError):units(text,6)

    def test_chain_asset_and_scale_mismatch_rejected(self):
        sale,costs=self.ledger()
        for wrong in (Asset(4663,'native:ETH',18),Asset(1,'native:ETH',6),Asset(1,'0x'+'a'*40,18)):
            changed=[replace(costs[0],amount=replace(costs[0].amount,asset=wrong)),*costs[1:]]
            with self.assertRaisesRegex(ValueError,'mismatch'):bounds(sale,changed)

    def test_missing_cost_category_not_zero(self):
        sale,costs=self.ledger()
        with self.assertRaisesRegex(ValueError,'missing cost'):bounds(sale,costs[:-1])

    def test_fee_embedded_in_sale_not_subtracted_twice(self):
        sale,costs=self.ledger()
        costs.append(Cost('dex','venue',Interval(ETH,1,1,('test-only',)),frozenset({'venue_fee'})))
        with self.assertRaisesRegex(ValueError,'double-counted'):bounds(sale,costs,embedded=frozenset({'venue_fee'}))

    def test_gas_tip_in_total_gas_not_subtracted_twice(self):
        sale,costs=self.ledger()
        costs.append(Cost('tip','gas',Interval(ETH,1,1,('test-only',)),frozenset({'gas_priority'})))
        with self.assertRaisesRegex(ValueError,'double-counted'):bounds(sale,costs)

    def test_duplicate_cost_identifier_rejected(self):
        sale,costs=self.ledger()
        with self.assertRaisesRegex(ValueError,'duplicate cost'):bounds(sale,costs+[costs[0]])

    def test_principal_advance_not_income(self):
        sale,costs=self.ledger()
        with self.assertRaisesRegex(ValueError,'not sale income'):bounds(sale,costs,sale_kind='loan_advance')

    def test_unknown_cost_is_not_zero_net(self):
        sale,costs=self.ledger();r=bounds(sale,costs)
        self.assertEqual(r['net_upper_raw'],'1651296044494913')
        self.assertIsNone(r['net_lower_raw']);self.assertIsNone(r['nqc_captured_net'])
        self.assertIn('financing',r['unbounded_costs'])

    def test_lower_and_upper_bounds_use_opposite_cost_endpoints(self):
        sale,costs=self.ledger()
        sale=replace(sale,lower=100,upper=120)
        costs=[replace(c,amount=Interval(ETH,1,2,('SYNTHETIC_UNIT_TEST_NOT_MARKET',))) for c in costs]
        r=bounds(sale,costs,hypothetical=True)
        self.assertEqual((r['net_lower_raw'],r['net_upper_raw']),('86','113'))
        self.assertFalse(r['commercial_admission'])

    def test_unknown_sale_cannot_create_zero_or_positive_margin(self):
        sale,costs=self.ledger();r=bounds(replace(sale,lower=None,upper=None),costs)
        self.assertIsNone(r['net_lower_raw']);self.assertIsNone(r['net_upper_raw'])

    def test_negative_unknown_cost_not_used_to_invent_rebate(self):
        with self.assertRaises(ValueError):Interval(ETH,-1,None,('test',))

    def test_full_debt_1bp_rejection_is_scoped_and_reproduced(self):
        r=self.report['discarded_scenarios'][0]
        self.assertEqual(r['net_upper_raw'],'-754261612795662')
        self.assertEqual(r['decision'],'DESCARTADO_DENTRO_DE_CONDICIONES')
        self.assertFalse(r['financing_offer_exists']);self.assertFalse(r['all_Morpho_discarded'])
        self.assertEqual(self.b['assessment']['research_status'],'REQUIERE_EVIDENCIA_ESPECIFICA')

    def test_large_collateral_does_not_change_priority_or_profit(self):
        changed=copy.deepcopy(self.candidates)
        changed[0]['events'][0]['seized_raw']=str(10**100)
        self.assertEqual(radar.select_probe(changed),radar.select_probe(self.candidates))
        self.assertIsNone(changed[0]['net_profit'])

    def test_external_winner_not_NQC_capture_or_live_opportunity(self):
        self.assertTrue(all(not c['NQC_capture_demonstrated'] and not c['currently_executable'] for c in self.candidates))
        self.assertTrue(all(c['economic_rank'] is None and c['net_profit'] is None for c in self.candidates))

    def test_offline_adapter_cannot_admit_trading(self):
        c=copy.deepcopy(self.b);c['commercial_admission']=True
        with self.assertRaisesRegex(ValueError,'offline adapter'):Registry().add(c)

    def test_B_not_reopened_and_probe_is_conditional(self):
        p=self.report['proposed_next_probe']
        self.assertNotEqual(p['tx_hash'],TX_B);self.assertFalse(p['B_reopened'])
        self.assertEqual(p['block'],26104570);self.assertEqual(p['reported_tx_index'],0)
        self.assertEqual(len(p['reported_zero_prefix_candidates']),4)
        self.assertFalse(p['acquisition_authorized']);self.assertIsNone(p['expected_monetary_value'])

    def test_order_claim_not_authenticated_by_structural_priority(self):
        c=next(c for c in self.candidates if c['id']==self.report['proposed_next_probe']['candidate_id'])
        self.assertFalse(c['order_bound_to_archived_header'])
        self.assertIn('transaction_membership',c['assessment']['criteria']['evidence_burden']['requirements'])
        self.assertIn('fork_and_system_transitions',c['assessment']['criteria']['evidence_burden']['requirements'])

    def test_missing_evidence_costs_remain_unknown(self):
        for c in self.candidates:
            cost=c['assessment']['C_cost_of_missing_evidence']
            self.assertIsNone(cost['money']);self.assertIsNone(cost['hours']);self.assertIsNone(cost['requests'])

    def test_reference_evidence_classification_not_profit_ranking(self):
        self.assertEqual(self.report['evaluation']['status_counts'],{
            'REQUIERE_EVIDENCIA_ESPECIFICA':2,'NO_PUEDE_EVALUARSE_CON_DATOS_ACTUALES':140})
        self.assertEqual(self.report['evaluation']['reference_decisions_matched'],142)
        self.assertEqual(self.report['evaluation']['positive_NQC_profit_claims'],0)

    def test_requirements_reuse_does_not_copy_state(self):
        r=self.report['shared_requirements']
        self.assertEqual(len(r['same_market_groups']),61);self.assertEqual(len(r['same_asset_pair_groups']),54)
        self.assertTrue(r['same_pair_does_not_establish_shared_pool_or_profit'])
        self.assertTrue(all(not c['historical_state_authenticated'] for c in self.candidates))

    def test_determinism_under_input_order_changes(self):
        shuffled=copy.deepcopy(self.candidates);random.Random(55).shuffle(shuffled)
        self.assertEqual(radar.select_probe(shuffled),radar.select_probe(self.candidates))
        self.assertEqual(radar.sharing(shuffled),radar.sharing(self.candidates))
        self.assertEqual(radar.run(self.s)['result_sha256'],self.report['result_sha256'])

    def test_adapter_interface_has_no_B_dependency_in_scan(self):
        # Contract stub using an actual archived A dossier; no new protocol integration.
        row=copy.deepcopy(next(c for c in self.candidates if c['label']=='A'))
        row.pop('assessment');row.pop('decision_hash')
        class Stub:
            def candidates(self,s):return [copy.deepcopy(row)]
            def evaluate(self,s,rows):return []
        result=radar.scan(self.s,[Stub()])
        self.assertEqual(len(result['candidates']),1)
        self.assertEqual(result['discarded_scenarios'],[])

    def test_all_suspended_or_closed_yields_no_probe(self):
        self.assertIsNone(radar.select_probe([self.b])['candidate_id'])

    def test_state_and_budget_are_separate_from_capital_future_policy(self):
        s=self.report['security']
        self.assertEqual((s['Triport_total_known'],s['Triport_lifetime_budget']),(0,8))
        self.assertFalse(s['gas_budget_available_now']);self.assertFalse(s['funding_or_signing_capability'])
        self.assertEqual(s['future_Canary_gas_cap_MXN'],2000)
        self.assertIsNone(self.report['monthly']['forecast'])


if __name__=='__main__':
    unittest.main()
