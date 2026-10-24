import copy
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cashflow_intake import build_cashflow
from evidence_store import admit, audit_store, create, export_store, read_batch, restore_store, revoke
from historical_intake import build_ledger
from inclusion_fee_intake import (BINDING_NAME, CAPTURE_NAME, EVIDENCE, REPORT_NAME,
    build_inclusion_report, exercise, exercise_fields, load_capture, query_inclusion_report,
    reconcile, seal, split_execution_fee, store_inclusion_report, verify_inclusion_report,
    verify_replay)
from integrity import canonical, digest, strict_json


def reseal(report):
    report.pop('report_commitment_sha256', None); return seal(report)


def synthetic_replay(network):
    # Namespace IDs are a fixture, never evidence of a physical disconnected run.
    with tempfile.TemporaryDirectory() as tmp: report = exercise_fields(tmp)
    report['network'] = copy.deepcopy(network); return seal(report)


class FeeArithmeticTests(unittest.TestCase):
    def test_nonzero_priority_is_part_of_total_not_an_extra_cost(self):
        r = split_execution_fee('21000', '17', '10')
        self.assertEqual(r, {'execution_gas_paid_wei': '357000',
                            'base_fee_burn_wei': '210000', 'priority_fee_paid_wei': '147000'})
        self.assertEqual(int(r['execution_gas_paid_wei']),
                         int(r['base_fee_burn_wei']) + int(r['priority_fee_paid_wei']))

    def test_exact_integer_arithmetic_above_float_precision(self):
        r = split_execution_fee('1234567', '123456789123456789', '100000000000000000')
        self.assertEqual(int(r['priority_fee_paid_wei']), 1234567 * 23456789123456789)

    def test_invalid_numeric_inputs_and_overflow_rejected(self):
        for args in [('0','10','5'), ('1','5','10'), ('1','01','0'), ('1','1.0','0'),
                     (True,'10','5'), ('1', '-1','0'), ('1',str(2**256),'0'),
                     ('2',str(2**256-1),'0')]:
            with self.subTest(args=args), self.assertRaises(ValueError): split_execution_fee(*args)


class InclusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = load_capture()
        cls.cashflow, cls.ledger = build_cashflow(), build_ledger()
        cls.report = build_inclusion_report()

    def modified_capture(self, rank=1, kind='transaction'):
        c = copy.deepcopy(self.capture)
        item = next(r for r in c['records'] if r['rank'] == rank and r['kind'] == kind)
        return c, item

    def reject(self, c, reason):
        with self.assertRaisesRegex(ValueError, reason): reconcile(self.cashflow, self.ledger, c)

    def test_real_top_three_keep_all_nine_identities(self):
        self.assertEqual([r['transaction_hash'] for r in self.report['records']],
                         [r['transaction_hash'] for r in self.cashflow['records']])
        self.assertEqual(self.report['summary']['execution_fee_split_observations'], 3)
        self.assertEqual(self.report['summary']['execution_gas_paid_wei_observed_subset'], '759296632646672')

    def test_unknown_six_remain_null_not_zero(self):
        for row in self.report['records'][3:]:
            self.assertEqual(row['inclusion_status'], 'UNOBSERVED')
            self.assertIsNone(row['fee_witness'])

    def test_zero_priority_never_means_zero_builder_compensation(self):
        for row in self.report['records'][:3]:
            w = row['fee_witness']
            self.assertEqual(w['priority_fee_paid_wei'], '0')
            self.assertEqual(w['base_fee_burn_wei'], w['execution_gas_paid_wei'])
            for key in ('direct_fee_recipient_transfer_wei', 'total_builder_compensation_wei',
                        'builder_share_of_bonus_wad', 'fee_recipient_builder_identity'):
                self.assertIsNone(w[key])

    def test_transaction_sender_and_protocol_liquidator_are_distinct_roles(self):
        w = self.report['records'][0]['fee_witness']
        self.assertNotEqual(w['transaction_sender'], w['event_liquidator_address'])
        self.assertEqual(w['block_fee_recipient'], '0x6adb3bab5730852eb53987ea89d8e8f16393c200')

    def test_truncated_token_data_and_internal_errors_cannot_certify_costs(self):
        for row in self.report['records']:
            self.assertFalse(row['complete_costs']); self.assertFalse(row['nqc_execution'])
            self.assertFalse(row['titan_coverage_proven']); self.assertIsNone(row['complete_net_profit_wei'])
        self.assertTrue(all(v is False for v in self.report['authorities'].values()))
        self.assertFalse(self.report['records'][0]['fee_witness']['independent_full_receipt_parity'])

    def test_failed_trace_acquisition_retained_not_counted_as_evidence(self):
        failure = self.report['acquisition_failures'][0]
        self.assertTrue(failure['response']['isError'])
        self.assertEqual(failure['continuation']['http_status'], 403)
        self.assertEqual(self.report['summary']['direct_builder_payment_observations'], 0)

    def test_replay_has_no_network(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_inclusion_report(self.report), self.report)

    def test_capture_tampering_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/CAPTURE_NAME; p.write_bytes((EVIDENCE/CAPTURE_NAME).read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError, 'capture_changed'): load_capture(tmp)
            p.unlink(); p.symlink_to(EVIDENCE/CAPTURE_NAME)
            with self.assertRaisesRegex(ValueError, 'symlink_input'): load_capture(tmp)

    def test_duplicate_missing_or_wrong_rank_observations_rejected(self):
        for mutate in (lambda c: c['records'].pop(),
                       lambda c: c['records'].__setitem__(1, c['records'][0]),
                       lambda c: c['records'][0].update(rank=True)):
            c = copy.deepcopy(self.capture); mutate(c)
            with self.assertRaises(ValueError): reconcile(self.cashflow, self.ledger, c)

    def test_wrong_chain_or_transaction_request_rejected(self):
        for key, value in [('chain_id','8453'), ('transaction_hash','0x'+'0'*64)]:
            c, item = self.modified_capture(); item['request'][key] = value
            self.reject(c, 'transaction_request')

    def test_reorg_block_hash_and_transaction_position_rejected(self):
        c, item = self.modified_capture(kind='block'); item['response']['data']['block_details']['hash'] = '0x'+'0'*64
        self.reject(c, 'observed_anchor')
        c, item = self.modified_capture(); item['response']['data']['position'] += 1
        self.reject(c, 'observed_anchor')

    def test_bool_block_number_cannot_pass_as_integer(self):
        c, item = self.modified_capture(); item['response']['data']['block_number'] = True
        self.reject(c, 'anchor_types')

    def test_changed_receipt_gas_and_price_rejected(self):
        for key in ('gas_used', 'gas_price'):
            c, item = self.modified_capture(); item['response']['data'][key] = '1'
            self.reject(c, 'receipt_disagreement')

    def test_base_fee_disagreement_rejected(self):
        c, item = self.modified_capture(kind='block')
        item['response']['data']['block_details']['base_fee_per_gas'] = '1'
        self.reject(c, 'base_fee_disagreement')

    def test_forged_split_total_or_eip1559_caps_rejected(self):
        for key, value, reason in [('priority_fee','1','fee_split_mismatch'),
                                  ('transaction_burnt_fee','1','fee_split_mismatch'),
                                  ('fee',{'type':'actual','value':'1'},'total_fee_mismatch'),
                                  ('max_fee_per_gas','1','effective_price_mismatch')]:
            c, item = self.modified_capture(); item['response']['data'][key] = value
            self.reject(c, reason)

    def test_pending_failed_wrong_type_and_time_rejected(self):
        for key, value, reason in [('status','error','unsettled'), ('is_pending_update',True,'unsettled'),
                                  ('type',3,'unsupported_tx_type'), ('timestamp','2000-01-01T00:00:00Z','observation_time')]:
            c, item = self.modified_capture(); item['response']['data'][key] = value
            self.reject(c, reason)

    def test_resealed_invented_profit_or_builder_zero_rejected(self):
        for key, value in [('complete_net_profit_wei','1'), ('complete_costs',True)]:
            r = copy.deepcopy(self.report); r['records'][0][key] = value
            r['report_commitment_sha256'] = digest(canonical({k:v for k,v in r.items() if k != 'report_commitment_sha256'}))
            with self.assertRaisesRegex(ValueError, 'differs_from_sources'): verify_inclusion_report(r)
        r = copy.deepcopy(self.report); r['records'][0]['fee_witness']['total_builder_compensation_wei'] = '0'
        with self.assertRaisesRegex(ValueError, 'differs_from_sources'): verify_inclusion_report(r)


class InclusionStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = create(Path(cls.tmp.name)/'evidence.sqlite')
        cls.result = store_inclusion_report(cls.db)
        cls.snapshot = export_store(cls.db)
        cls.objects = read_batch(cls.db, cls.result['batch'])

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_authentic_seventh_batch_reconstructs_from_sources(self):
        self.assertEqual(query_inclusion_report(self.db, self.result['batch']), self.result['report'])
        self.assertEqual(len(self.snapshot['batches']), 7)

    def test_exact_restore_and_ancestor_revocation_preserve_forensic_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            restored = Path(tmp)/'restored.sqlite'; restore_store(restored, self.snapshot)
            self.assertEqual(query_inclusion_report(restored, self.result['batch']), self.result['report'])
            revoke(restored, self.result['root_batch'], 'TEST_ONLY', b'not a canonical chain reorg')
            after = export_store(restored); again = Path(tmp)/'again.sqlite'; restore_store(again, after)
            self.assertEqual(export_store(again), after)
            self.assertEqual(len(audit_store(again)['invalidated_batches']), 6)
            with self.assertRaisesRegex(ValueError, 'inactive_or_missing'):
                query_inclusion_report(again, self.result['batch'])
            self.assertEqual(read_batch(again, self.result['batch'], include_revoked=True), self.objects)

    def test_parentless_self_consistent_batch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/'copy.sqlite'; restore_store(db, self.snapshot)
            bad = admit(db, self.objects, parents=[])
            with self.assertRaisesRegex(ValueError, 'missing_declared_parent'): query_inclusion_report(db, bad)

    def test_resealed_report_and_inherited_evidence_cannot_be_laundered(self):
        for name in (REPORT_NAME, 'cashflow-report.json'):
            with tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp)/'copy.sqlite'; restore_store(db, self.snapshot)
                objects = dict(self.objects); v = strict_json(objects[name]); v['records'][0]['complete_costs'] = True
                objects[name] = canonical(v); bad = admit(db, objects, parents=[self.result['parent']])
                with self.assertRaises(ValueError): query_inclusion_report(db, bad)


class InclusionReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network = {'interfaces': ['lo'], 'routable_network': False,
                       'network_namespace': 'net:[2]', 'parent_network_namespace': 'net:[1]'}
        cls.report = synthetic_replay(cls.network)

    def test_seven_batch_restore_replay_binds_titan_only_policy_offline(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_replay(self.report), self.report)
        self.assertEqual(self.report['blocked_batches'], 7)
        self.assertTrue(self.report['forensic_bytes_preserved'])
        self.assertTrue(self.report['restore_byte_identical'])
        policy = self.report['gas_funding_policy']
        self.assertEqual(policy['payer'], 'TITAN')
        self.assertEqual(policy['operator_gas_cap_mxn'], 0)
        self.assertFalse(policy['operator_prefund_allowed'])
        self.assertFalse(policy['own_gas_fallback_allowed'])
        self.assertFalse(policy['execution_coverage_proven'])
        self.assertEqual(self.report['gas_policy_sha256'], digest(canonical(policy)))

    def test_resealed_operator_gas_or_titan_coverage_claims_rejected(self):
        for key, value in [('payer', 'OPERATOR'), ('operator_gas_cap_mxn', 1),
                           ('operator_prefund_allowed', True), ('own_gas_fallback_allowed', True),
                           ('execution_coverage_proven', True)]:
            with self.subTest(key=key):
                r = copy.deepcopy(self.report); r['gas_funding_policy'][key] = value
                r['gas_policy_sha256'] = digest(canonical(r['gas_funding_policy']))
                with self.assertRaisesRegex(ValueError, 'differs_from_sources'): verify_replay(reseal(r))

    def test_observed_competitor_fees_cannot_become_titan_coverage_or_complete_costs(self):
        for key in ('titan_covered_executions', 'complete_paid_cost_rows'):
            r = copy.deepcopy(self.report); report = r['inclusion_report']
            report['summary'][key] = 1; reseal(report)
            with self.assertRaisesRegex(ValueError, 'differs_from_sources'): verify_replay(reseal(r))

    def test_routable_shared_or_malformed_namespace_rejected(self):
        for key, value in [('routable_network', True), ('interfaces', ['lo', 'eth0']),
                           ('network_namespace', 'net:[1]'), ('network_namespace', 2)]:
            r = copy.deepcopy(self.report); r['network'][key] = value
            with self.assertRaisesRegex(ValueError, 'inclusion_network'): verify_replay(reseal(r))

    def test_changed_restore_or_parent_commitment_rejected(self):
        for key, value in [('blocked_batches', 6), ('forensic_bytes_preserved', False),
                           ('execution_report_commitment', '0'*64)]:
            r = copy.deepcopy(self.report); r[key] = value
            with self.assertRaisesRegex(ValueError, 'differs_from_sources'): verify_replay(reseal(r))

    def test_worker_output_is_exact_and_cannot_overwrite_or_follow_symlink(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            p = Path(tmp)/'worker'; r = exercise(p, self.network)
            self.assertEqual(r, self.report)
            self.assertEqual((p/'report.json').read_bytes(), canonical(r))
            with self.assertRaises((FileExistsError, ValueError)): exercise(p, self.network)
            link = Path(tmp)/'link'; link.symlink_to(p, target_is_directory=True)
            with self.assertRaises(ValueError): exercise(link, self.network)


if __name__ == '__main__': unittest.main()
