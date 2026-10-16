import concurrent.futures
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from audit_opportunity import HERE, audit
from economics import D, evaluate, required_prefund
from reservation_model import PaperBudget
from shadow_gate import assess


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = audit()

    def test_time_only_projection_and_competition(self):
        r = self.report
        self.assertEqual(r['new_read_only_requests'], 10)
        self.assertEqual(r['time_only_projection_protocol_read_slots_match'], 112)
        self.assertFalse(r['timing']['parent_end']['userop_success'])
        self.assertFalse(r['timing']['actual_block_end']['userop_success'])
        self.assertTrue(r['timing']['parent_time_plus_1']['userop_success'])
        self.assertEqual(r['timing']['parent_time_plus_1']['surplus_usdg_raw'], 32060665)
        self.assertEqual(r['position_block_end']['borrow_shares'], 0)
        self.assertGreater(r['position_block_end']['collateral'], 0)
        self.assertIsNone(r['future_capture_rate'])
        self.assertTrue(r['candidate_and_size_selected_with_hindsight'])

    def test_fee_variant_is_capital_not_profit_improvement(self):
        r = self.report['fee_cap_experiment']
        self.assertEqual(r['original']['required_prefund_wei'], 4880000000000000)
        self.assertEqual(r['variant']['required_prefund_wei'], 249541240000000)
        self.assertEqual(r['variant_nitro']['sponsor_charge_wei'], 79616762214000)
        self.assertEqual(r['variant_nitro']['surplus_usdg_raw'], 32060665)
        self.assertEqual(r['variant_nitro']['network_fee_wei'], 57601662034000)
        self.assertEqual(r['fixture_validation_data'], 0)
        self.assertFalse(r['full_bundler_admission_proven'])

    def test_capture_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'evidence'
            shutil.copytree(HERE / 'evidence', target)
            file = target / 'timing-phase1/02-nqc-selected-end.json'
            file.write_text(file.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'capture hash mismatch'):
                audit(target)

    def test_protocol_override_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'evidence'
            shutil.copytree(HERE / 'evidence', target)
            file = target / 'timing-phase1/requests.json'
            records = json.loads(file.read_text())
            records[1]['request']['params'][2]['stateOverrides']['0xcde9599059f8ae6d6b9f33a0af7877827ec75f16'] = {'code':'0x'}
            file.write_text(json.dumps(records))
            with self.assertRaisesRegex(ValueError, 'fixture or protocol state changed'):
                audit(target)


class EconomicsTests(unittest.TestCase):
    def base(self, **extra):
        args = dict(eth_usdg='3000', capture_probability='0.05', surplus_haircut_bps=1000,
                    provider_markup_bps=0, rpc_per_attempt_usdg='0.02', fixed_period_usdg='250',
                    deployment_period_usdg='25', capital_period_usdg='2', attempts=1000)
        args.update(extra)
        return evaluate('32.060665', 79616762214000, 50201161200000, **args)

    def test_no_capture_loses_money(self):
        r = self.base(capture_probability='0')
        self.assertLess(r['expected_period_usdg'], 0)

    def test_full_overheads_and_break_even_count(self):
        r = self.base()
        self.assertEqual(r['overhead_per_attempt_usdg'], D('.297'))
        self.assertEqual(r['successes_for_strictly_positive_period'], 16)
        self.assertLess(self.base(capture_probability='.015')['expected_period_usdg'], 0)
        self.assertGreater(self.base(capture_probability='.016')['expected_period_usdg'], 0)

    def test_no_double_count_of_native_fee(self):
        self.assertEqual(self.base()['success_fee_usdg'], D('0.238850286642'))

    def test_unpaid_sponsor_is_not_financeable(self):
        r = self.base(revenue_share_bps=0)
        self.assertFalse(r['possible_at_100_percent_capture'])
        self.assertLess(r['expected_period_usdg'], 0)

    def test_bad_probability_price_and_float_rejected(self):
        for kwargs in [{'capture_probability':'1.01'}, {'eth_usdg':'0'}, {'eth_usdg':'NaN'},
                       {'eth_usdg':3000.0}, {'attempts':0}, {'fixed_period_usdg':'-1'}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.base(**kwargs)

    def test_prefund_requires_complete_fields(self):
        with self.assertRaises(ValueError):
            required_prefund({'call':1500000}, 2000000000)


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'paper.sqlite'

    def tearDown(self):
        self.tmp.cleanup()

    def test_zero_funding_cannot_grant(self):
        book = PaperBudget(self.path, 0)
        with self.assertRaisesRegex(ValueError, 'no prepaid capacity'):
            book.reserve('operation', '4663:EP:sender:0', 1)

    def test_parallel_pending_reservations_cannot_overspend(self):
        book = PaperBudget(self.path, 10**16)
        def attempt(i):
            try:
                return book.reserve(f'op{i}', f'4663:EP:sender:{i}', 4880000000000000)
            except ValueError as error:
                if str(error) != 'no prepaid capacity':
                    raise
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            admitted = list(pool.map(attempt, range(20)))
        self.assertEqual(sum(admitted), 2)
        self.assertEqual(book.snapshot()['remaining_wei'], 240000000000000)

    def test_duplicate_operation_and_nonce(self):
        book = PaperBudget(self.path, 100)
        self.assertTrue(book.reserve('a','n',40))
        self.assertFalse(book.reserve('a','n',40))
        with self.assertRaises(ValueError):
            book.reserve('a','n',41)
        with self.assertRaises(ValueError):
            book.reserve('b','n',40)
        self.assertEqual(book.snapshot()['reservations'], 1)

    def test_reconciliation_does_not_recycle_full_prefund(self):
        book = PaperBudget(self.path, 100)
        book.reserve('a','n',100)
        book.reconcile('a',1,'synthetic-final-receipt')
        self.assertEqual(book.snapshot()['remaining_wei'],0)
        self.assertEqual(book.snapshot()['recorded_actual_wei'],1)
        with self.assertRaises(ValueError):
            book.reserve('b','m',1)

    def test_restart_cannot_refill_or_erase_commitments(self):
        book = PaperBudget(self.path, 100)
        book.reserve('a','n',80)
        self.assertEqual(PaperBudget(self.path,100).snapshot()['remaining_wei'],20)
        with self.assertRaises(ValueError):
            PaperBudget(self.path,101)

    def test_conflicting_or_over_cap_settlement_rejected(self):
        book = PaperBudget(self.path,100)
        book.reserve('a','n',80)
        with self.assertRaises(ValueError):
            book.reconcile('a',81,'r')
        book.reconcile('a',60,'r')
        with self.assertRaises(ValueError):
            book.reconcile('a',59,'r2')


class ShadowTests(unittest.TestCase):
    def record(self, **kwargs):
        data = dict(source_block=100, source_hash='0x'+'ab'*32, source_time=1000,
                    received_ns=100, simulation_finished_ns=120, decision_ns=130,
                    prediction_time=1001, input_max_block=100, input_max_time=1000,
                    max_age_ns=50, horizon_seconds=4, history_selected=False,
                    simulation_success=True, expected_net_usdg='1', prepaid_capacity_wei=100,
                    prefund_wei=80, bundler_admission_proven=True, validation_expiry_proven=True,
                    nonrecourse_funding_proven=True, latency_budget_proven=True)
        data.update(kwargs)
        return data

    def test_synthetic_paper_pass_never_authorizes_broadcast(self):
        r = assess(self.record())
        self.assertTrue(r['paper_candidate'])
        self.assertFalse(r['broadcast_enabled'])
        self.assertFalse(r['production_authorization'])

    def test_hindsight_future_and_late_inputs_rejected(self):
        for kwargs, reason in [({'history_selected':True}, 'HINDSIGHT_SELECTED_CASE'),
                               ({'input_max_block':101}, 'FUTURE_INPUT'),
                               ({'input_max_time':1001}, 'FUTURE_INPUT'),
                               ({'simulation_finished_ns':131}, 'DECISION_BEFORE_INPUT_READY')]:
            with self.subTest(kwargs=kwargs):
                self.assertIn(reason, assess(self.record(**kwargs))['reasons'])

    def test_stale_projection_or_bad_finance_rejected(self):
        for kwargs in [{'decision_ns':151}, {'prediction_time':1005}, {'expected_net_usdg':'0'},
                       {'prepaid_capacity_wei':79}, {'bundler_admission_proven':False},
                       {'validation_expiry_proven':False}, {'nonrecourse_funding_proven':False},
                       {'latency_budget_proven':False}]:
            with self.subTest(kwargs=kwargs):
                self.assertFalse(assess(self.record(**kwargs))['paper_candidate'])

    def test_missing_or_ambiguous_inputs_fail_closed(self):
        with self.assertRaises(ValueError):
            assess({})
        with self.assertRaises(ValueError):
            assess(self.record(bundler_admission_proven='true'))


if __name__ == '__main__':
    unittest.main()
