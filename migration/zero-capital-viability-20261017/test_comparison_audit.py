import unittest
from comparison_audit import audit, before_cutoff, native_partition, partition_flows, upfront_gap


class ComparisonTests(unittest.TestCase):
    def test_fee_cap_reserve_is_needed_before_future_profit(self):
        self.assertEqual(upfront_gap(0,5089056,3*10**9),15267168000000000)
        self.assertEqual(upfront_gap(20,2,10,1),1)
        with self.assertRaises(ValueError): upfront_gap(False,2,10)
        with self.assertRaises(ValueError): upfront_gap(0,2,1.5)

    def test_internal_paymaster_transfer_not_second_network_fee(self):
        r=native_partition({'network_fee_wei':57601054408000,'sponsor_charge_wei':79616762214000})
        self.assertEqual(sum(x['delta'] for x in r['actor_deltas']),0)
        self.assertEqual(r['beneficiary_and_payer_delta_if_same_entity_wei'],22015707806000)
        self.assertEqual(r['all_three_consolidated_external_cost_wei'],57601054408000)
        self.assertFalse(r['actual_common_ownership_proven'])

    def test_asset_and_chain_boundaries_and_duplicate_flow_rejection(self):
        fs=[dict(id='eth',chain=1,asset='native:ETH',amount=10,**{'from':'a','to':'b'}),
            dict(id='token',chain=4663,asset='USDG',amount=10,**{'from':'b','to':'a'})]
        self.assertEqual(len(partition_flows(fs)),4)
        with self.assertRaisesRegex(ValueError,'duplicate'):partition_flows(fs+[fs[0]])

    def test_missing_or_late_temporal_input_cannot_become_capture(self):
        t='2026-10-17T00:00:00+00:00';later='2026-10-17T00:00:01+00:00'
        self.assertEqual(before_cutoff(t,later,None,later,True),'PENDIENTE')
        self.assertEqual(before_cutoff(t,later,later,later,True),'REFUTADO_FOR_THIS_TIMELINE')
        self.assertEqual(before_cutoff(t,t,later,later,False),'PENDIENTE')
        self.assertEqual(before_cutoff(t,t,later,later,True),'NECESSARY_ORDER_ONLY')
        with self.assertRaises(ValueError):before_cutoff(later,t,later,later,True)

    def test_real_saved_cohort_grouped_by_transaction_without_promotion(self):
        r=audit();c=r['cohort']
        self.assertEqual((c['event_count'],c['transaction_count']),(143,141))
        self.assertEqual(sum(x['event_count'] for x in c['transactions']),143)
        self.assertEqual(c['first_unmet_counts'],{'REPRODUCED':141})
        self.assertEqual(c['receipt_counts'],{'NOT_REQUESTED':118,'UNAVAILABLE':22,'RPC_API_EVENT_CROSSCHECK':1})
        self.assertIsNone(c['eligible_count']);self.assertFalse(r['economic_admission'])
        self.assertEqual(r['robinhood_included_failure']['all_three_consolidated_external_cost_wei'],39639718050000)
        self.assertEqual(r['separate_topup_revert_sensitivity']['sponsor_loss_wei'],420000000000000)


if __name__=='__main__':unittest.main()
