import copy
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from evidence_store import admit, create, export_store, read_batch, restore_store, revoke
from historical_state_intake import build_state_report
from integrity import canonical, digest, strict_json
from temporal_intake import (EVIDENCE, REPORT_NAME, ROOT, SOURCE_CONFIG, SOURCE_INPUT,
    SOURCE_TEST, TEMPORAL_NAMES, build_temporal_report, load_temporal_source,
    query_temporal_report, read_measurement, store_temporal_report,
    validate_temporal_join, verify_temporal_report)


def reseal(doc):
    for row in doc['records']:
        row['record_commitment_sha256'] = digest(canonical({k: v for k, v in row.items()
            if k != 'record_commitment_sha256'}))
    doc['report_commitment_sha256'] = digest(canonical({k: v for k, v in doc.items()
        if k != 'report_commitment_sha256'}))
    return doc


class TemporalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = build_state_report()
        cls.anchors, cls.conclusion, cls.members, cls.provenance = load_temporal_source()
        cls.report = build_temporal_report()

    def join(self, anchors=None, conclusion=None, members=None):
        return validate_temporal_join(self.state, anchors or self.anchors,
            conclusion or self.conclusion, members or self.members)

    def test_real_endpoints_keep_one_crossing_and_two_non_crossings(self):
        witnesses = [r['temporal_witness'] for r in self.report['records'][:3]]
        self.assertEqual([w['time_only_after_hf_wad'] for w in witnesses],
            ['999999999704293538', '1000701096098308225', '1000489713637144623'])
        self.assertEqual([w['time_only_below_one'] for w in witnesses], [True, False, False])
        self.assertEqual([w['elapsed_seconds'] for w in witnesses], [12, 12, 12])

    def test_rank_two_increases_so_time_does_not_always_decrease_health(self):
        deltas = [int(r['temporal_witness']['time_only_hf_delta_wad']) for r in self.report['records'][:3]]
        self.assertLess(deltas[0], 0); self.assertGreater(deltas[1], 0); self.assertLess(deltas[2], 0)
        self.assertEqual(deltas, [-2289525092, 3067226316, -5949854525])

    def test_six_unobserved_cases_remain_unknown_and_nonexecutable(self):
        for r in self.report['records'][3:]:
            self.assertIsNone(r['temporal_witness'])
            self.assertEqual(r['temporal_status'], 'UNOBSERVED')
            self.assertFalse(r['executable_candidate'])
        self.assertEqual(self.report['summary']['temporal_unknown_count'], 6)

    def test_crossing_is_not_a_paid_capture_or_causal_oracle_signal(self):
        self.assertTrue(all(v is False for v in self.report['authorities'].values()))
        for r in self.report['records']:
            self.assertFalse(r['executable_candidate']); self.assertFalse(r['prospective_signal_proven'])
            self.assertIsNone(r['complete_net_profit_wei']); self.assertIsNone(r['observed_paid_flash_fee_wei'])
            self.assertIsNone(r['oracle_delay_blocks']); self.assertIsNone(r['builder_payment_wei'])
        self.assertFalse(self.report['oracle_cause_observed'])

    def test_two_timestamp_operators_are_not_two_fork_operators(self):
        p = self.report['temporal_source_provenance']
        self.assertEqual(p['timestamp_operator_count'], 2)
        self.assertEqual(p['original_fork_provider_ids'], ['drpc'])
        self.assertEqual(p['original_fork_provider_count'], 1)
        self.assertFalse(self.report['original_fork_two_operator_agreement'])
        self.assertFalse(self.report['new_temporal_fork_execution_performed'])

    def test_endpoint_does_not_locate_first_crossing_or_prove_interest_cause(self):
        for r in self.report['records'][:3]:
            w = r['temporal_witness']
            self.assertIsNone(w['first_crossing_timestamp'])
            for key in ('intrablock_transactions_replayed', 'actual_cause_proven',
                        'interest_accrual_cause_proven', 'prospective_prediction_proven'):
                self.assertFalse(w[key])

    def test_upstream_state_is_preserved_without_reclassifying_predecessor(self):
        self.assertEqual(self.report['predecessor_report_commitment'], self.state['report_commitment_sha256'])
        for before, after in zip(self.state['records'], self.report['records']):
            for key, value in before.items():
                if key not in ('decision_blockers', 'record_commitment_sha256'):
                    self.assertEqual(after[key], value)
        self.assertEqual(self.report['records'][0]['predecessor_threshold_status'], 'NOT_BELOW_ONE')

    def test_authenticated_original_source_identity_and_logs_are_bound(self):
        self.assertEqual(self.provenance['run_id'], 37740704145)
        self.assertEqual(self.provenance['artifact_id'], 11533288894)
        for rank, row in enumerate(self.report['records'][:3], 1):
            self.assertEqual(row['temporal_witness']['retained_fork_log_sha256'],
                             digest(self.members[f'rank-{rank}.txt']))

    def test_each_source_pin_capture_archive_rejects_tampering_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for name in TEMPORAL_NAMES: shutil.copyfile(EVIDENCE / name, d / name)
            for name in TEMPORAL_NAMES:
                raw = (d / name).read_bytes(); (d / name).write_bytes(raw + b' ')
                with self.subTest(name=name), self.assertRaises(ValueError): load_temporal_source(d)
                (d / name).unlink(); (d / name).symlink_to(EVIDENCE / name)
                with self.assertRaises(ValueError): load_temporal_source(d)
                (d / name).unlink(); (d / name).write_bytes(raw)

    def test_imported_original_source_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for p in (SOURCE_INPUT, SOURCE_TEST, SOURCE_CONFIG):
                (d / p).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / p, d / p)
            for p in (SOURCE_INPUT, SOURCE_TEST, SOURCE_CONFIG):
                raw = (d / p).read_bytes(); (d / p).write_bytes(raw + b'\n')
                with self.subTest(path=p), self.assertRaisesRegex(ValueError, 'original_source_changed'):
                    load_temporal_source(root=d)
                (d / p).write_bytes(raw)

    def test_reproduction_needs_no_network(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_temporal_report(self.report), self.report)

    def test_resealed_fake_profit_execution_and_first_crossing_are_rejected(self):
        for key, value in [('executable_candidate', True), ('complete_net_profit_wei', '1'),
                           ('oracle_delay_blocks', 0), ('temporal_status', 'EXECUTABLE')]:
            doc = copy.deepcopy(self.report); doc['records'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): verify_temporal_report(reseal(doc))
        for key, value in [('first_crossing_timestamp', 1788935614), ('actual_cause_proven', True),
                           ('interest_accrual_cause_proven', True), ('time_only_after_hf_wad', '0')]:
            doc = copy.deepcopy(self.report); doc['records'][0]['temporal_witness'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): verify_temporal_report(reseal(doc))

    def test_missing_duplicate_reordered_or_resealed_rows_fail(self):
        for mutate in (lambda r: r.pop(), lambda r: r.reverse(), lambda r: r.append(r[0])):
            doc = copy.deepcopy(self.report); mutate(doc['records'])
            with self.assertRaises(ValueError): verify_temporal_report(reseal(doc))

    def test_provider_disagreement_and_duplicate_identity_fail(self):
        for key, value in [('operator', 'dRPC'), ('provider_id', 'drpc'), ('time_records', [])]:
            a = copy.deepcopy(self.anchors); a['operator_progress'][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.join(anchors=a)

    def test_transaction_borrower_predecessor_and_winner_substitutions_fail(self):
        for key, value in [('historical_winner_tx', '0x' + 'a' * 64),
                ('borrower', '0x' + 'a' * 40), ('source_borrower_identity_sha256', 'a' * 64),
                ('previous_block_number', 25938046), ('previous_block_hash', '0x' + 'a' * 64),
                ('winning_block_number', 25938049), ('winning_block_hash', '0x' + 'a' * 64)]:
            a = copy.deepcopy(self.anchors); a['canonical_time_anchors'][0][key] = value
            for p in a['operator_progress']: p['time_records'] = copy.deepcopy(a['canonical_time_anchors'])
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'temporal_identity'):
                self.join(anchors=a)

    def test_timestamp_types_order_and_bounded_interval_fail_closed(self):
        for t0, t1 in [(True, 2), (1, 2.0), (1, '2'), (-1, 2), (2, 2), (3, 2),
                       (1, 122), (2**64 - 1, 2**64)]:
            a = copy.deepcopy(self.anchors)
            a['canonical_time_anchors'][0].update(previous_block_timestamp=t0, winning_block_timestamp=t1)
            for p in a['operator_progress']: p['time_records'] = copy.deepcopy(a['canonical_time_anchors'])
            with self.subTest(t0=t0, t1=t1), self.assertRaisesRegex(ValueError, 'timestamp_window'):
                self.join(anchors=a)

    def test_health_anchor_cannot_point_to_a_different_source_report(self):
        for key in ('source_artifact_sha256', 'source_report_sha256'):
            a = copy.deepcopy(self.anchors); a[key] = 'a' * 64
            with self.assertRaises(ValueError): self.join(anchors=a)

    def test_conclusion_counts_authority_and_measurement_drift_fail(self):
        for key, value in [('time_only_below_one_count', 2), ('selected_using_future_winners', False),
                ('intrablack_original_transactions_replayed', True), ('nexus_execution_or_capture_proven', True)]:
            c = copy.deepcopy(self.conclusion); c[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.join(conclusion=c)
        for key, value in [('rank', 2), ('previous_hf_wad', '1'),
                           ('winner_time_only_hf_wad', '1'), ('time_only_below_one', False)]:
            c = copy.deepcopy(self.conclusion); c['measurements'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.join(conclusion=c)

    def test_swapped_truncated_duplicate_or_failed_fork_logs_fail(self):
        raw = self.members['rank-1.txt']
        changes = [self.members['rank-2.txt'], raw.replace(b'[PASS]', b'[FAIL]'),
            raw.replace(b'0 skipped;', b'1 skipped;'), raw.replace(b'HF_AFTER_WAD', b'MISSING'),
            raw + b'\n  NQC_TIME_ONLY_HF_AFTER_WAD: 1\n']
        for changed in changes:
            m = dict(self.members); m['rank-1.txt'] = changed
            with self.assertRaises(ValueError): self.join(members=m)

    def test_log_numbers_reject_noncanonical_uints_and_zero_accounts(self):
        raw = self.members['rank-1.txt']
        for value in (b'0', b'-1', b'01', b'1.0', str(2**256).encode()):
            changed = raw.replace(b'999999999704293538', value)
            with self.subTest(value=value), self.assertRaises(ValueError): read_measurement(changed)
        with self.assertRaises(ValueError):
            read_measurement(raw.replace(b'DEBT_BASE_AFTER: 5352267213144', b'DEBT_BASE_AFTER: 0'))

    def test_exactly_one_is_not_below_threshold(self):
        raw = self.members['rank-1.txt'].replace(b'999999999704293538', b'1000000000000000000')
        with self.assertRaisesRegex(ValueError, 'crossing_marker'): read_measurement(raw)
        checked = read_measurement(raw.replace(b'CROSSED_BELOW_ONE: 1', b'CROSSED_BELOW_ONE: 0'))
        self.assertEqual(checked['CROSSED_BELOW_ONE'], 0)

    def test_store_restore_and_idempotence_keep_full_temporal_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = create(Path(tmp) / 'evidence.sqlite'); s = store_temporal_report(db)
            self.assertEqual(query_temporal_report(db, s['temporal_batch']), self.report)
            restored = Path(tmp) / 'restored.sqlite'; restore_store(restored, export_store(db))
            self.assertEqual(query_temporal_report(restored, s['temporal_batch']), self.report)
            self.assertEqual(store_temporal_report(db)['temporal_batch'], s['temporal_batch'])

    def test_revocation_blocks_query_and_keeps_source_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = create(Path(tmp) / 'evidence.sqlite'); s = store_temporal_report(db)
            revoke(db, s['temporal_batch'], 'TEST_ONLY_NOT_REAL_REORG', b'synthetic test')
            with self.assertRaises(ValueError): query_temporal_report(db, s['temporal_batch'])
            saved = read_batch(db, s['temporal_batch'], include_revoked=True)
            self.assertEqual(saved['temporal-original.zip'], (EVIDENCE / 'temporal-original.zip').read_bytes())

    def test_coherent_store_cannot_launder_fabricated_temporal_or_upstream_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = create(Path(tmp) / 'evidence.sqlite'); s = store_temporal_report(db)
            original = read_batch(db, s['temporal_batch'])
            for name in (REPORT_NAME, 'historical-state-report.json', 'cashflow-report.json',
                         'liquidator-report.json', 'historical-ledger.json'):
                objects = dict(original); doc = strict_json(objects[name]); doc['fake_authority'] = True
                objects[name] = canonical(doc); batch = admit(db, objects)
                with self.subTest(name=name), self.assertRaises(ValueError): query_temporal_report(db, batch)

    def test_store_cannot_drop_sources_or_add_unreviewed_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = create(Path(tmp) / 'evidence.sqlite'); s = store_temporal_report(db)
            for kind in ('missing', 'extra'):
                objects = read_batch(db, s['temporal_batch'])
                if kind == 'missing': objects.pop('temporal-original.zip')
                else: objects['extra.json'] = b'{}'
                batch = admit(db, objects)
                with self.assertRaisesRegex(ValueError, 'temporal_batch_inventory'): query_temporal_report(db, batch)

    def test_cli_reproduces_report_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'report.json'
            cmd = [sys.executable, '-B', str(ROOT / 'omega/temporal_intake.py'), '--out', str(out)]
            r = subprocess.run(cmd, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(strict_json(out.read_bytes()), self.report)
            before = out.read_bytes(); self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(out.read_bytes(), before)

    def test_cli_rejects_symlink_parent_and_repository_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp); (d / 'real').mkdir(); (d / 'link').symlink_to(d / 'real', target_is_directory=True)
            cmd = [sys.executable, '-B', str(ROOT / 'omega/temporal_intake.py'), '--out']
            for out, message in [(d / 'link/report.json', b'symlink_store_path'),
                                 (ROOT / 'omega/AUDIT_H17.md', b'output_inside_source')]:
                r = subprocess.run(cmd + [str(out)], capture_output=True)
                self.assertNotEqual(r.returncode, 0); self.assertIn(message, r.stderr)
            self.assertFalse((d / 'real/report.json').exists())


if __name__ == '__main__': unittest.main()
