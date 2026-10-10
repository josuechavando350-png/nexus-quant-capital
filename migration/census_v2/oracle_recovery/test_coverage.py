"""Real coverage replay and adversarial gates; synthetic cases never add coverage."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

import collect as c
import verify_coverage as v
import prepare_coverage_inputs as prep


class CoverageChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['NQC_COVERAGE_INPUTS'])
        cls.d08 = Path(os.environ['NQC_ORACLE_D08'])
        cls.plan = v.strict((cls.root / 'closed-prefix/resume-plan.json').read_bytes())
        cls.progress = v.strict((cls.root / 'closed-prefix/progress.json').read_bytes())
        cls.prior = v.WINDOW - set(v.resume.plan_blocks(cls.plan))

    def contract(self, mutate, acquisition=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            doc = copy.deepcopy(self.progress)
            mutate(doc)
            (root / 'progress.json').write_bytes(c.canon(doc))
            (root / 'resume-plan.json').write_bytes(c.canon(self.plan))
            if acquisition:
                (root / 'acquisition.json').write_bytes(c.canon(doc))
            return v.checkpoint_contract(root)

    def test_real_all_sources_replay_twice_identically(self):
        inputs = [self.root / 'original-oracle-evidence.zip', self.d08,
                  self.root / 'pilot-bundle/pilot', self.root / 'partial-bundle/remaining',
                  self.root / 'closed-prefix', self.root / 'original/drpc', self.root / 'full-window']
        first, second = v.verify(*inputs), v.verify(*inputs)
        self.assertEqual(c.canon(first), c.canon(second))
        r = first['report.json']
        self.assertEqual((r['retained_secondary_blocks'], r['earlier_direct_blocks'],
                          r['prior_overlap_not_double_counted']), (4650, 2080, 1560))
        self.assertEqual(r['closed_continuation_blocks'], 55000)
        self.assertEqual(r['closed_continuation_prices_matched'], 3685000)
        self.assertEqual(r['verified_secondary_union_blocks'], 60170)
        self.assertEqual(r['missing_secondary_blocks'], 154866)
        self.assertEqual(r['unique_matched_price_coordinates'], 4031390)
        self.assertEqual(r['captured_but_not_verified_blocks'], 20)
        self.assertEqual((r['executed_events'], r['complete_receipts']), (139, 127))
        self.assertEqual(r['earlier_failure_records_preserved'][0]['http_status'], 429)
        for flag in ['milestone_10_coverage_ready', 'milestone_15_ready', 'milestone_20_ready',
                     'census_closed', 'capture_or_profit_admitted', 'notification_sent']:
            self.assertIs(r[flag], False)

    def test_same_count_different_prior_set_rejected(self):
        prior = set(self.prior)
        prior.remove(min(prior))
        prior.add(v.resume.plan_blocks(self.plan)[0])
        with self.assertRaisesRegex(ValueError, 'exact prior complement'):
            v.exact_partition(prior, self.plan, 55000)

    def test_out_of_window_prior_rejected(self):
        prior = set(self.prior)
        prior.remove(min(prior))
        prior.add(c.END + 1)
        with self.assertRaisesRegex(ValueError, 'prior block set'):
            v.exact_partition(prior, self.plan, 55000)

    def test_partial_and_final_set_arithmetic_only(self):
        covered, missing = v.exact_partition(self.prior, self.plan, 55000)
        self.assertEqual((len(covered), len(missing)), (60170, 154866))
        self.assertEqual(covered | missing, v.WINDOW)
        self.assertTrue(covered.isdisjoint(missing))
        covered, missing = v.exact_partition(self.prior, self.plan, 209866)
        self.assertEqual(covered, v.WINDOW)
        self.assertEqual(missing, set())  # Arithmetic only, not acquisition evidence.

    def test_bool_or_inflated_closed_count_rejected(self):
        for count in [True, 209867, -1, 0]:
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, 'closed count'):
                v.exact_partition(self.prior, self.plan, count)

    def test_exact_real_running_snapshot_passes(self):
        _, terminal = v.checkpoint_contract(self.root / 'closed-prefix')
        self.assertFalse(terminal)

    def test_unknown_status_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unknown acquisition status'):
            self.contract(lambda d: d.update(status='DONE'))

    def test_terminal_label_without_acquisition_rejected(self):
        with self.assertRaisesRegex(ValueError, 'progress/acquisition identity'):
            self.contract(lambda d: d.update(status='COMPLETE_REQUESTED_MISSING_BLOCKS'))

    def test_terminal_counter_without_all_closed_bytes_rejected(self):
        def fake(d):
            d.update(status='COMPLETE_REQUESTED_MISSING_BLOCKS', observed_blocks=209866,
                     finished_at='2026-10-10T01:00:00+00:00')
        with self.assertRaisesRegex(ValueError, 'terminal closed-block conservation'):
            self.contract(fake, acquisition=True)

    def test_running_snapshot_with_terminal_file_rejected(self):
        with self.assertRaisesRegex(ValueError, 'running/final state conflict'):
            self.contract(lambda d: None, acquisition=True)

    def test_stopped_failure_may_not_disappear(self):
        def lost(d):
            d.update(status='STOPPED_INCOMPLETE', finished_at='2026-10-10T01:00:00+00:00')
        with self.assertRaisesRegex(ValueError, 'missing preserved failure'):
            self.contract(lost, acquisition=True)

    def test_broken_worker_rate_or_batch_rejected(self):
        for field, value in [('workers', 2), ('workers', True),
                             ('minimum_request_interval_seconds', 1.0), ('maximum_batch_size', 20)]:
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, 'worker/rate/batch'):
                self.contract(lambda d: d.update({field: value}))

    def test_substituted_asset_identity_rejected(self):
        with self.assertRaisesRegex(ValueError, 'source or authority'):
            self.contract(lambda d: d.update(asset_document_sha256='0' * 64))

    def test_retry_after_cannot_be_backdated(self):
        with self.assertRaisesRegex(ValueError, 'Retry-After not elapsed'):
            self.contract(lambda d: d.update(started_at=self.plan['previous_rate_limit_received_at']))

    def test_nonboolean_complete_flag_rejected(self):
        with self.assertRaisesRegex(ValueError, 'complete flag type'):
            self.contract(lambda d: d['completed_files'][0].update(complete=1))

    def test_bool_counter_rejected(self):
        with self.assertRaisesRegex(ValueError, 'counter bounds/type'):
            self.contract(lambda d: d.update(observed_blocks=True))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            v.strict('{"status":"RUNNING","status":"COMPLETE_REQUESTED_MISSING_BLOCKS"}')

    def test_event_scope_and_operator_substitutions_rejected(self):
        original = json.loads((v.V2 / 'full_window_recovery/evidence/report.json').read_bytes())
        v.event_scope(original)
        for field, value in [('executed_liquidation_events', 138), ('full_semantic_receipt_log_matches', 126),
                             ('new_log_operator', 'Nodies'), ('real_market_census_closed', True)]:
            changed = copy.deepcopy(original)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                v.event_scope(changed)

    def test_corrupted_archive_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(ValueError, 'archive digest'):
            prep.unpack(b'changed', prep.THIRD_SHA, 22, Path(temp) / 'never-created')


if __name__ == '__main__':
    unittest.main()
