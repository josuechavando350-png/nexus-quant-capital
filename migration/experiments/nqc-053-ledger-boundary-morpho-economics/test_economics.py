import copy
import unittest
from fractions import Fraction
import economics as e


class EconomicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = e.Sources()
        cls.report = e.analyze(cls.s)
        cls.rows = list(e.event_map(sum((e.events(cls.s.load(f'page-{i:03}.json'))
                                      for i in range(3)), [])).values())
        cls.case_inputs = [cls.rows] + [cls.s.load(name) for name in
            ('b-receipt.json','case_b_trace.json','case_b_block.json','case_b.json')]

    def test_observations_are_not_admitted_opportunities(self):
        r = self.report
        self.assertEqual((r['observed_sample']['events'],r['observed_sample']['distinct_transactions']), (143,141))
        self.assertEqual(r['observed_sample']['null_receipts'],22)
        self.assertEqual(r['observed_sample']['bad_debt_events'],43)
        self.assertEqual(len(r['sources_verified']),33)
        self.assertIsNone(r['monthly_nqc_net_forecast_usd'])
        self.assertFalse(r['commercial_admission'])
        self.assertIsNone(r['case_b']['nqc_captured_net'])

    def test_duplicate_identity_is_not_extra_volume(self):
        with self.assertRaisesRegex(ValueError,'duplicate event'):
            e.event_map([self.rows[0],self.rows[0]])

    def test_robinhood_state_cannot_enter_morpho_census(self):
        row = copy.deepcopy(self.rows[0]); row['chain']['id']=4663
        with self.assertRaisesRegex(ValueError,'wrong chain'): e.event_map([row])

    def test_float_or_boolean_cannot_change_debt_precision(self):
        for amount in (26039738525656992415.0, True, '1e18', '-1', '01'):
            row = copy.deepcopy(self.rows[0]); row['data']['repaidAssets']=amount
            with self.assertRaises(ValueError): e.event_map([row])

    def test_exact_integer_strings_supported_without_modifying_source(self):
        row = copy.deepcopy(self.rows[0]); row['data']['repaidAssets']='26039738525656992415'
        value = next(iter(e.event_map([row]).values()))['data']['repaidAssets']
        self.assertEqual(value,26039738525656992415)
        self.assertIsInstance(row['data']['repaidAssets'],str)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError): e.parse('{"amount":1,"amount":2}')

    def test_receipt_mutation_breaks_flow_reconciliation(self):
        inputs=copy.deepcopy(self.case_inputs)
        receipt=inputs[1]['response']['result']
        log=next(x for x in receipt['logs'] if x['topics'][0]==e.LIQUIDATE_TOPIC)
        log['data']='0x'+format(1,'064x')+log['data'][66:]
        with self.assertRaisesRegex(ValueError,'event amount'): e.audit_case(*inputs)

    def test_receipt_from_another_block_rejected(self):
        inputs=copy.deepcopy(self.case_inputs)
        inputs[1]['response']['result']['blockHash']='0x'+'0'*64
        with self.assertRaisesRegex(ValueError,'block identity'): e.audit_case(*inputs)

    def test_independent_usd_price_is_not_invented(self):
        self.assertIsNone(self.report['case_b']['historical_eth_usd'])
        self.assertIsNone(self.report['case_b']['external_financing_premium'])

    def test_financing_one_basis_point_exceeds_remaining_margin(self):
        c = self.report['case_b']
        self.assertEqual(c['residual_upper_bound_before_unknown_obligations_wei'],1651296044494913)
        self.assertEqual(e.repayment_fee(c['repaid_debt_weth_wei'],1),2603973852565700)
        self.assertLess(c['hypothetical_financing_sweep'][2]['residual_before_other_unknown_costs_wei'],0)
        self.assertGreater(c['hypothetical_financing_sweep'][1]['residual_before_other_unknown_costs_wei'],0)

    def test_loss_budget_does_not_round_break_even_into_profit(self):
        self.assertEqual(e.strict_failures_budget(20,10),1)
        self.assertIsNone(e.strict_failures_budget(0,10))
        c=self.report['case_b'];r=c['residual_upper_bound_before_unknown_obligations_wei'];g=c['gas_cost_wei']
        self.assertGreater(r-8*g,0); self.assertLess(r-9*g,0)

    def test_monthly_targets_include_failures_and_overhead(self):
        self.assertEqual(e.usd_per_capture(5000,14),'7143/20')
        self.assertEqual(Fraction(e.usd_per_capture(5000,14,overhead=600,failed_cost=700)),450)
        self.assertEqual(e.usd_per_capture(45000,141),'6383/20')
        with self.assertRaises(ValueError): e.usd_per_capture(5000,0)

    def test_scope_does_not_assume_all_transactions_profitable(self):
        observed=self.report['observed_sample']
        self.assertEqual(observed['independent_profit_opportunities_demonstrated'],0)
        for row in self.report['monthly_required_volume_scenarios']:
            self.assertEqual(row['required_successes'],e.ceil(Fraction(row['target_net_usd'],
                row['net_usd_per_captured_success_ASSUMED'])))


if __name__ == '__main__':
    unittest.main()
