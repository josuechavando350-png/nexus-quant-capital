import copy
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cashflow_intake import build_cashflow
from evidence_store import admit, create, export_store, read_batch, restore_store, revoke
from historical_intake import build_ledger
from historical_state_intake import (EVIDENCE, REPORT_NAME, ROOT, STATE_NAMES,
    build_state_report, load_state_sources, percent_mul, query_state_report,
    signed_reference, store_state_report, validate_join, verify_state_report)
from integrity import canonical, digest, strict_json
from liquidator_intake import build_liquidator_report


def reseal(report):
    for r in report['records']:
        r['record_commitment_sha256'] = digest(canonical({k: v for k, v in r.items()
            if k != 'record_commitment_sha256'}))
    report['report_commitment_sha256'] = digest(canonical({k: v for k, v in report.items()
        if k != 'report_commitment_sha256'}))
    return report


class HistoricalStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cashflow = build_cashflow()
        cls.ledger = build_ledger()
        cls.identities = build_liquidator_report()
        cls.sources, cls.provenance = load_state_sources()
        cls.report = build_state_report()

    def join(self, sources=None, cashflow=None, ledger=None, identities=None):
        return validate_join(cashflow or self.cashflow, ledger or self.ledger,
                             identities or self.identities, sources or self.sources)

    def test_real_predecessor_states_reject_all_three_hindsight_winners(self):
        self.assertEqual([r['predecessor_state']['account_data']['health_factor_wad']
            for r in self.report['records'][:3]],
            ['1000000001993818630', '1000701093031081909', '1000489719586999148'])
        self.assertEqual(self.report['summary']['predecessor_not_below_one_count'], 3)
        self.assertEqual(self.report['summary']['predecessor_below_one_count'], 0)
        self.assertTrue(all(not r['executable_candidate'] for r in self.report['records']))

    def test_rank2_price_is_added_without_rewriting_h16_source(self):
        r = self.report['records'][1]
        self.assertIsNone(r['preblock_price_reference'])
        self.assertEqual(r['predecessor_state']['price_reference']['oracle_usd_base_1e8'], '269328000000')
        self.assertEqual(self.cashflow['summary']['priced_ranks'], [1, 3])
        self.assertEqual(self.report['summary']['predecessor_price_count'], 3)

    def test_unknown_remaining_six_are_not_zero_or_eligible(self):
        for r in self.report['records'][3:]:
            self.assertIsNone(r['predecessor_state'])
            self.assertEqual(r['predecessor_threshold_status'], 'UNKNOWN')
            self.assertIn('PREDECESSOR_STATE_UNOBSERVED', r['decision_blockers'])
            self.assertFalse(r['two_operator_receipt_commitment_matched_for_this_transaction'])

    def test_observed_fee_parameter_is_not_an_observed_paid_cost(self):
        for r in self.report['records']:
            self.assertIsNone(r['observed_paid_flash_fee_wei'])
            self.assertIsNone(r['complete_net_profit_wei'])
            self.assertIsNone(r['builder_payment_wei'])
            self.assertIsNone(r['oracle_delay_blocks'])
        self.assertEqual([r['predecessor_state']['observed_pool_premium_bps']
            for r in self.report['records'][:3]], [5, 5, 5])

    def test_actual_half_up_rounding_differs_from_prior_ceil_sensitivity(self):
        r = self.report['records'][1]
        self.assertEqual(r['hypothetical_fee_sensitivity']['fee_wei_ceil'], '913521825008781')
        self.assertEqual(r['predecessor_state']['conditional_flash_fee_wei'], '913521825008780')
        self.assertEqual(r['predecessor_state']['conditional_remaining_wei'], '80780424710773474')
        self.assertEqual(r['predecessor_state']['conditional_remaining_usd_wad'], '217564302265031982054')

    def test_fee_boundaries_and_overflow_fail_without_float_coercion(self):
        self.assertEqual(percent_mul(999, 5), 0)
        self.assertEqual(percent_mul(1000, 5), 1)
        self.assertEqual(percent_mul(1, 10000), 1)
        self.assertEqual(percent_mul(2**256 - 1, 0), 0)
        for amount, bps in [(True, 5), (1, True), (-1, 5), (10, 10001), (1.0, 5), (2**256 - 1, 1)]:
            with self.subTest(amount=amount, bps=bps), self.assertRaises(ValueError):
                percent_mul(amount, bps)

    def test_negative_reference_conversion_does_not_floor_or_clip(self):
        self.assertEqual(signed_reference(-1, '150000000'), '-1')
        self.assertEqual(signed_reference(1, '150000000'), '1')
        for p in ('0', '01', '-1', '1.0', True):
            with self.subTest(price=p), self.assertRaises(ValueError): signed_reference(1, p)

    def test_three_selected_receipts_cannot_become_127_receipt_parity(self):
        self.assertEqual(self.report['summary']['selected_receipt_parity_count'], 3)
        self.assertEqual(self.report['summary']['historical_corpus_transactions'], 127)
        self.assertFalse(self.report['complete_corpus_receipt_parity'])
        self.assertTrue(all(not r['complete_receipt_parity_for_corpus'] for r in self.report['records']))

    def test_authority_remains_false_with_no_oracle_causal_delay(self):
        self.assertTrue(all(v is False for v in self.report['authorities'].values()))
        self.assertFalse(self.report['oracle_cause_observed'])
        self.assertIsNone(self.report['oracle_update_delay_blocks'])
        self.assertFalse(self.report['new_chain_acquisition_performed'])

    def test_source_identity_anchors_and_all_archive_manifests_are_real(self):
        self.assertEqual({p['artifact_id'] for p in self.provenance.values()},
                         {11530582289, 11529984754, 11533556749})
        self.assertEqual({p['repository'] for p in self.provenance.values()},
                         {'josuechavando350-png/nexus-engine'})

    def test_each_source_archive_capture_and_pin_reject_tampering_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for name in STATE_NAMES: shutil.copyfile(EVIDENCE / name, d / name)
            for name in STATE_NAMES:
                original = (d / name).read_bytes()
                (d / name).write_bytes(original + b' ')
                with self.subTest(name=name, mode='changed'), self.assertRaises(ValueError): load_state_sources(d)
                (d / name).unlink(); (d / name).symlink_to(EVIDENCE / name)
                with self.subTest(name=name, mode='symlink'), self.assertRaises(ValueError): load_state_sources(d)
                (d / name).unlink(); (d / name).write_bytes(original)

    def test_missing_source_and_oversized_capture_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            with self.assertRaises(FileNotFoundError): load_state_sources(d)
            for name in STATE_NAMES: shutil.copyfile(EVIDENCE / name, d / name)
            (d / 'top3-health-metadata.json').write_bytes(b'x' * (1048576 + 1))
            with self.assertRaisesRegex(ValueError, 'input_too_large'): load_state_sources(d)

    def test_offline_reproduction_matches_without_any_network(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_state_report(self.report), self.report)

    def test_resealed_fabricated_profit_price_health_and_authority_are_rejected(self):
        for key, value in [('executable_candidate', True), ('observed_paid_flash_fee_wei', '0'),
                ('complete_net_profit_wei', '1'), ('oracle_delay_blocks', 0),
                ('predecessor_threshold_status', 'BELOW_ONE'), ('source_selected_with_hindsight', False)]:
            doc = copy.deepcopy(self.report); doc['records'][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'differs_from_sources'):
                verify_state_report(reseal(doc))

    def test_resealed_missing_duplicated_and_reordered_rows_are_rejected(self):
        for mutation in (lambda r: r.pop(), lambda r: r.append(r[0]), lambda r: r.reverse()):
            doc = copy.deepcopy(self.report); mutation(doc['records'])
            with self.assertRaises(ValueError): verify_state_report(reseal(doc))

    def test_provider_disagreement_or_duplicate_operator_is_rejected(self):
        for key, source in [('two_rpc_operators', 'aave-premium'), ('provider_records', 'top3-health')]:
            for drift in ('operator', 'rows'):
                s = copy.deepcopy(self.sources)
                s[source][key][1][drift] = ('dRPC' if drift == 'operator' else [])
                with self.subTest(source=source, drift=drift), self.assertRaises(ValueError): self.join(s)

    def test_cross_source_predecessor_and_winner_substitution_is_rejected(self):
        for field, value in [('block', 26024990), ('hash', '0x' + 'a' * 64)]:
            s = copy.deepcopy(self.sources); s['rank2-price']['row']['historical_preblock_oracle'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.join(s)
        s = copy.deepcopy(self.sources); s['rank2-price']['row']['transaction_hash'] = self.cashflow['records'][0]['transaction_hash']
        with self.assertRaises(ValueError): self.join(s)

    def test_borrower_or_receipt_commitment_substitution_is_rejected(self):
        for key, value in [('borrower', '0x' + 'a' * 40), ('receipt_evidence_sha256', 'a' * 64)]:
            s = copy.deepcopy(self.sources)
            for provider in s['top3-health']['provider_records']: provider['rows'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.join(s)

    def test_inconsistent_health_classification_and_count_are_rejected(self):
        s = copy.deepcopy(self.sources)
        for p in s['top3-health']['provider_records']: p['rows'][0]['health_factor_below_one_at_predecessor'] = True
        with self.assertRaises(ValueError): self.join(s)
        s = copy.deepcopy(self.sources); s['top3-health']['observed_predecessor_below_one_count'] = 1
        with self.assertRaises(ValueError): self.join(s)

    def test_recomputed_conditional_fee_cannot_use_ceiling_or_false_profit(self):
        for key, value in [('historical_pool_premium_wei_percentmul_half_up', '913521825008781'),
                           ('nexus_net_profit_proven', True), ('historical_pool_fee_is_availability_quote', True)]:
            s = copy.deepcopy(self.sources); s['aave-premium']['network_observed_history'][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.join(s)

    def test_durable_store_restore_preserves_full_sources_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = create(Path(tmp) / 'evidence.sqlite'); stored = store_state_report(db)
            self.assertEqual(query_state_report(db, stored['state_batch']), self.report)
            restored = Path(tmp) / 'restored.sqlite'; restore_store(restored, export_store(db))
            self.assertEqual(query_state_report(restored, stored['state_batch']), self.report)
            self.assertEqual(store_state_report(db)['state_batch'], stored['state_batch'])

    def test_revocation_rejects_query_but_retains_original_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = create(Path(tmp) / 'evidence.sqlite'); s = store_state_report(db)
            revoke(db, s['state_batch'], 'TEST_ONLY_NOT_REAL_REORG', b'synthetic revocation witness')
            with self.assertRaises(ValueError): query_state_report(db, s['state_batch'])
            self.assertIn(REPORT_NAME, read_batch(db, s['state_batch'], include_revoked=True))

    def test_self_consistent_store_cannot_launder_changed_report_or_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = create(Path(tmp) / 'evidence.sqlite'); s = store_state_report(db)
            objects = read_batch(db, s['state_batch'])
            for name in (REPORT_NAME, 'cashflow-report.json', 'historical-ledger.json', 'liquidator-report.json'):
                changed = dict(objects); doc = strict_json(changed[name]); doc['fake_authority'] = True
                changed[name] = canonical(doc); batch = admit(db, changed)
                with self.subTest(name=name), self.assertRaises(ValueError): query_state_report(db, batch)

    def test_store_inventory_cannot_drop_sources_or_add_unaudited_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = create(Path(tmp) / 'evidence.sqlite'); s = store_state_report(db)
            original = read_batch(db, s['state_batch'])
            for kind in ('missing', 'extra'):
                objects = dict(original)
                if kind == 'missing': objects.pop('rank2-price-original.zip')
                else: objects['extra.json'] = b'{}'
                batch = admit(db, objects)
                with self.assertRaisesRegex(ValueError, 'state_batch_inventory'): query_state_report(db, batch)

    def test_cli_output_reproduces_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'report.json'
            cmd = [sys.executable, '-B', str(ROOT / 'omega/historical_state_intake.py'), '--out', str(out)]
            result = subprocess.run(cmd, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(strict_json(out.read_bytes()), self.report)
            before = out.read_bytes(); again = subprocess.run(cmd, capture_output=True)
            self.assertNotEqual(again.returncode, 0); self.assertEqual(out.read_bytes(), before)

    def test_cli_rejects_symlink_parent_and_repository_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); (directory / 'real').mkdir()
            (directory / 'link').symlink_to(directory / 'real', target_is_directory=True)
            cmd = [sys.executable, '-B', str(ROOT / 'omega/historical_state_intake.py'), '--out']
            blocked = subprocess.run(cmd + [str(directory / 'link/report.json')], capture_output=True)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn(b'symlink_store_path', blocked.stderr)
            self.assertFalse((directory / 'real/report.json').exists())
            blocked = subprocess.run(cmd + [str(ROOT / 'omega/AUDIT_H17.md')], capture_output=True)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn(b'output_inside_source', blocked.stderr)


if __name__ == '__main__': unittest.main()
