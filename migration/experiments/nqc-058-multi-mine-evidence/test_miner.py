"""Mutation/regression checks; no synthetic market profits or EVM executions."""
import copy
from decimal import Decimal
import unittest
from miner import (AavePublic, Evidence, MorphoPublished, PUF, compare, core,
                   decode_liquidation, failed_attempt, verify_bytes)


class TestMiner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Evidence()
        cls.raw = cls.e.local('inputs/aave_failed.json')
        cls.ref = cls.e.ref('inputs/aave_failed.json')
        cls.result = compare(cls.e)

    def test_exact_observed_fee_and_participants(self):
        _, bound, book = failed_attempt(self.raw, self.ref, exclude_external_compensation=True)
        # Independent Decimal calculation and displayed explorer fee.
        expected = Decimal(213052) * Decimal('0.086530593') / Decimal(10**9)
        self.assertEqual(expected, Decimal('0.000018435515899836'))
        self.assertEqual(bound['net_upper_raw'], '-18435515899836')
        self.assertIsNone(bound['net_lower_raw'])
        self.assertEqual([f['amount_raw'] for f in book['flows']], ['18435509508276', '6391560'])
        self.assertEqual(sum(int(f['amount_raw']) for f in book['flows']), int(book['gas_cost_raw']))
        self.assertEqual({f['payer'] for f in book['flows']}, {self.raw['sender']})
        self.assertIsNone(book['builder_identity'])

    def test_unknown_reimbursement_does_not_imply_total_loss(self):
        _, bound, _ = failed_attempt(self.raw, self.ref, exclude_external_compensation=False)
        self.assertIsNone(bound['net_upper_raw'])
        self.assertEqual(bound['classification'], 'EVIDENCIA_INSUFICIENTE')
        self.assertIsNone(bound['unrestricted_actor_net_raw'])

    def test_requested_debt_is_not_repaid_debt(self):
        decoded = decode_liquidation(self.raw)
        self.assertEqual(decoded['debt_to_cover_requested_raw'], str(int('c44338548c7', 16)))
        self.assertFalse(decoded['requested_is_actual_transfer'])
        failed = next(c for c in self.result['candidates'] if c['tx_hash'] == self.raw['tx_hash'])
        self.assertNotEqual(decoded['debt_to_cover_requested_raw'], failed['actual_debt_repaid_raw_in_failed_call'])
        self.assertEqual(failed['actual_debt_repaid_raw_in_failed_call'], '0')

    def test_failed_bound_rejects_unknown_success_and_altered_fees(self):
        for field, value in [('status', None), ('status', 'Success'), ('gas_used', 213053),
                             ('fee_eth', '0.000018435515899837'), ('value_wei', '1'),
                             ('gas_used', 213052.0), ('effective_gas_price_gwei', '0.0865305931')]:
            with self.subTest(field=field, value=value):
                raw = copy.deepcopy(self.raw); raw[field] = value
                with self.assertRaises(ValueError):
                    failed_attempt(raw, self.ref, exclude_external_compensation=True)

    def test_bad_abi_and_wrong_chain_rejected(self):
        for field, value in [('chain_id', 4663), ('chain_id', True), ('method_id', '0x00000000'),
                             ('to', '0x' + '0' * 40)]:
            raw = copy.deepcopy(self.raw); raw[field] = value
            with self.assertRaises(ValueError): decode_liquidation(raw)
        raw = copy.deepcopy(self.raw); raw['calldata_words'][4] = '0' * 63 + '2'
        with self.assertRaises(ValueError): decode_liquidation(raw)

    def test_report_sizes_never_become_sale_or_profit(self):
        rows = [c for c in self.result['candidates'] if c['evidence_grade'] == 'PRIMARY_REPORT_NO_RECEIPT']
        self.assertEqual(len(rows), 10)
        self.assertGreater(max(int(c['reported_reference_valuations']['seized_reference_usd_rounded']) for c in rows), 10**7)
        for c in rows:
            self.assertIsNone(c['economic_bounds']['net_upper_raw'])
            self.assertIsNone(c['collateral']['amount_raw'])
            self.assertIsNone(c['tx_index'])
            self.assertFalse(c['valuation_is_sale'])
            self.assertFalse(c['order_bound_to_archived_header'])
            self.assertFalse(c['inventory_sale_verified'])

    def test_previous_decisions_preserved_without_stale_probe(self):
        previous = self.e.git.json('radar055')
        rows = [c for c in self.result['candidates'] if c['protocol'] == 'morpho-blue']
        self.assertEqual(len(rows), 142)
        old = {c['id']: c for c in previous['candidates']}
        for c in rows: self.assertEqual(c['economic_bounds'], old[c['id']]['economic_bounds'])
        puf = next(c for c in rows if c['tx_hash'] == PUF)
        self.assertEqual(puf['research_state'], 'SUSPENDED_NQC056_NO_RETRY')
        self.assertNotIn(puf['id'], self.result['next_information_probe']['equal_evidence_group'])
        self.assertEqual(self.result['inherited_discarded_scenarios'], previous['discarded_scenarios'])
        self.assertEqual(previous['discarded_scenarios'][0]['net_upper_raw'], '-754261612795662')

    def test_duplicate_dossier_and_conflicting_identity(self):
        c = self.result['candidates'][0]
        registry = core.Registry(); registry.add(c); registry.add(copy.deepcopy(c))
        self.assertEqual(registry.duplicates, 1)
        self.assertEqual(len(registry.ordered()), 1)
        changed = copy.deepcopy(c); changed['block'] += 1
        with self.assertRaises(ValueError): registry.add(changed)
        changed = copy.deepcopy(c); changed['id'] += '/fake'
        with self.assertRaises(ValueError): registry.add(changed)

    def test_cross_asset_and_double_gas_rejected_by_reused_kernel(self):
        eth = core.Asset(1, 'native:ETH', 18)
        sale = core.Interval(eth, 0, 0, (self.ref,))
        costs = [core.Cost(k, k, core.Interval(eth, 0, None, (self.ref,)), frozenset({k})) for k in sorted(core.REQUIRED_COSTS)]
        foreign = core.Asset(4663, 'native:ETH', 18)
        costs[0] = core.Cost('debt', 'debt', core.Interval(foreign, 0, None, (self.ref,)), frozenset({'debt'}))
        with self.assertRaises(ValueError): core.bounds(sale, costs)
        costs[0] = core.Cost('debt', 'debt', core.Interval(eth, 0, None, (self.ref,)), frozenset({'debt'}))
        costs.append(core.Cost('tip_again', 'gas', core.Interval(eth, 0, None, (self.ref,)), frozenset({'gas'})))
        with self.assertRaises(ValueError): core.bounds(sale, costs)

    def test_source_tampering_and_duplicate_json_keys_rejected(self):
        pin = self.e.inputs['inputs/aave_failed.json']
        with self.assertRaises(ValueError): verify_bytes(b'{}', pin)
        with self.assertRaises(ValueError): core.parse('{"fee":1,"fee":0}')
        self.assertEqual(self.result['sources_verified'], {'git_pins': 26, 'local_transcriptions_and_review': 4})

    def test_batch_order_and_decisions_are_deterministic(self):
        reversed_result = compare(self.e, [AavePublic(), MorphoPublished()])
        self.assertEqual(reversed_result, self.result)
        for c in self.result['candidates']:
            bare = {k:v for k,v in c.items() if k != 'decision_hash'}
            self.assertEqual(core.digest(bare), c['decision_hash'])

    def test_comparison_does_not_claim_two_strategies_or_financial_admission(self):
        self.assertEqual(len(self.result['candidates']), 153)
        self.assertEqual(self.result['distinct_protocol_mines'], 2)
        self.assertEqual(self.result['distinct_strategy_families'], 1)
        self.assertEqual(self.result['live_protocol_coverage'], 0)
        self.assertEqual(self.result['economic_result'], 'OPORTUNIDAD_RENTABLE_NO_DEMOSTRADA')
        self.assertEqual(self.result['decision']['financial_execution'], 'NO-GO')
        for c in self.result['candidates']:
            self.assertFalse(c['NQC_capture_demonstrated'])
            self.assertFalse(c['commercial_admission'])
            self.assertIsNone(c['economic_rank'])
        self.assertIsNone(self.result['monthly']['forecast'])


if __name__ == '__main__':
    unittest.main()
