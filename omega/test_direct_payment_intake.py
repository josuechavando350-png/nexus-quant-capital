import copy
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cashflow_intake import build_cashflow
from direct_payment_intake import (CAPTURE_NAME, EVIDENCE, build_report, inclusion_capture,
    load_capture, reconcile, seal, verify_report, BINDING_NAME, REPORT_NAME,
    exercise, exercise_fields, query_report, store_report, verify_replay)
from evidence_store import admit, audit_store, create, export_store, read_batch, restore_store, revoke
from historical_intake import build_ledger
from inclusion_fee_intake import build_inclusion_report
from integrity import canonical, digest, strict_json


def reseal(report):
    report.pop('report_commitment_sha256', None); return seal(report)


def synthetic_replay(network):
    # Namespace IDs are a fixture, never evidence of a physical disconnected run.
    with tempfile.TemporaryDirectory() as tmp: report = exercise_fields(tmp)
    report['network'] = copy.deepcopy(network); return seal(report)


class DirectPaymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = load_capture(); cls.cashflow = build_cashflow()
        cls.fees = build_inclusion_report(); cls.ledger = build_ledger()
        cls.observed = next(r for r in inclusion_capture()['records'] if r['rank']==1
                           and r['kind']=='transaction')['response']['data']
        cls.report = build_report()

    def altered(self, name, mutate):
        c = copy.deepcopy(self.capture); record = next(r for r in c['records'] if r['name']==name)
        body = strict_json(record['raw_body']); mutate(body)
        record['raw_body'] = canonical(body).decode(); record['raw_sha256'] = digest(record['raw_body'].encode())
        return c

    def reject(self, capture, reason):
        with self.assertRaisesRegex(ValueError, reason):
            reconcile(capture, self.cashflow, self.fees, self.ledger, self.observed)

    def test_authentic_payment_and_all_sample_identities_preserved(self):
        self.assertEqual([r['transaction_hash'] for r in self.report['records']],
                         [r['transaction_hash'] for r in self.cashflow['records']])
        w=self.report['records'][0]['direct_payment_witness']
        self.assertEqual(w['direct_fee_recipient_payment_wei'],'95915734379292898')
        self.assertEqual(w['indexed_operation_count'],57)
        self.assertEqual(w['indexed_pages'],3)
        self.assertTrue(all(r['direct_payment_witness'] is None for r in self.report['records'][1:]))

    def test_native_unwrap_split_and_payment_ratio_recompute_exactly(self):
        w=self.report['records'][0]['direct_payment_witness']
        total, payment, rest=map(int,(w['unwrap_native_transfer_wei'],w['direct_fee_recipient_payment_wei'],
                                     w['residual_native_transfer_wei']))
        self.assertEqual(payment+rest,total)
        self.assertEqual(total,int(self.cashflow['records'][0]['same_asset_gross_delta_wei']))
        self.assertEqual(w['payment_to_gross_delta_wad'],str(payment*10**18//total))
        self.assertEqual(payment,total*9975//10000)

    def test_root_value_is_separate_from_internal_payments_and_gas(self):
        w=self.report['records'][0]['direct_payment_witness']
        self.assertEqual(w['transaction_native_value_wei'],'9975')
        self.assertEqual(w['execution_gas_paid_wei'],'19694395579376')
        self.assertTrue(w['direct_payment_is_separate_from_execution_gas'])
        self.assertNotEqual(w['transaction_sender'],w['residual_recipient'])
        self.assertIsNone(w['residual_recipient_control']); self.assertFalse(w['residual_is_realized_profit'])

    def test_indexer_listing_is_not_trace_proof_or_total_builder_compensation(self):
        w=self.report['records'][0]['direct_payment_witness']
        for k in ('raw_trace_available','full_call_ancestry_proven','native_balance_reconciliation_complete',
                  'independent_trace_provider_agreement','exclusive_liquidation_cost_attribution_proven'):
            self.assertFalse(w[k])
        self.assertIsNone(w['total_builder_compensation_wei']); self.assertIsNone(w['fee_recipient_builder_identity'])

    def test_titan_policy_does_not_attribute_competitor_payment_to_titan(self):
        p=self.report['gas_funding_policy']; self.assertEqual(p['payer'],'TITAN')
        self.assertEqual(p['operator_gas_cap_mxn'],0); self.assertFalse(p['own_gas_fallback_allowed'])
        self.assertEqual(self.report['summary']['titan_covered_executions'],0)
        for r in self.report['records']:
            self.assertFalse(r['complete_costs']); self.assertFalse(r['titan_coverage_proven'])
            self.assertIsNone(r['complete_net_profit_wei']); self.assertFalse(r['nqc_execution'])

    def test_reader_reproduces_without_network(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_report(self.report),self.report)

    def test_capture_changed_bytes_or_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/CAPTURE_NAME; p.write_bytes((EVIDENCE/CAPTURE_NAME).read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'capture_changed'):load_capture(tmp)
            p.unlink();p.symlink_to(EVIDENCE/CAPTURE_NAME)
            with self.assertRaisesRegex(ValueError,'symlink_input'):load_capture(tmp)

    def test_missing_page_and_wrong_cursor_rejected(self):
        c=copy.deepcopy(self.capture);c['records'].pop(1);self.reject(c,'capture_inventory')
        c=copy.deepcopy(self.capture);c['records'][1]['url']+='x';self.reject(c,'cursor_disagreement')

    def test_truncated_nonterminal_and_unreliable_initial_count_rejected(self):
        for name, mutate, reason in (
            ('operations-0',lambda p:p.update(countType='lowerBound'),'page_coverage'),
            ('operations-0',lambda p:p.update(count=True),'page_coverage'),
            ('operations-2',lambda p:p['items'].pop(),'page_coverage'),
            ('operations-2',lambda p:p['link'].update(next='/unexpected'),'page_not_terminal')):
            self.reject(self.altered(name,mutate),reason)

    def test_duplicate_or_bool_operation_indices_rejected(self):
        for value in (True,55,900):
            self.reject(self.altered('operations-0',lambda p:p['items'][0].update(opIndex=value)),
                        'operation_inventory')

    def test_chain_hash_index_and_block_drift_rejected(self):
        for k,v in [('chainId','8453'),('id','0x'+'0'*64),('blockHash','0x'+'0'*64),('index',2),('blockNumber',True)]:
            self.reject(self.altered('transaction',lambda t:t.update({k:v})),
                        'transaction_identity' if k in ('chainId','id') else 'transaction_anchor')
        self.reject(self.altered('operations-1',lambda p:p['items'][0].update(txHash='0x'+'0'*64)),
                    'operation_anchor')

    def test_gas_and_initial_native_value_disagreement_rejected(self):
        self.reject(self.altered('transaction',lambda t:t.update(gasUsed='1')),'gas_disagreement')
        self.reject(self.altered('transaction',lambda t:t.update(value='0')),'native_value_disagreement')

    def test_failed_operation_or_noncall_value_cannot_count_as_transfer(self):
        self.reject(self.altered('operations-1',lambda p:p['items'][0].update(status=False)),
                    'operation_failed_or_unsupported')
        self.reject(self.altered('operations-0',lambda p:p['items'][1].update(type='DELEGATECALL')),
                    'transfer_inventory')

    def test_payment_recipient_and_transfer_amount_rejected_when_changed(self):
        self.reject(self.altered('operations-0',lambda p:p['items'][1].update(to='0x'+'1'*40)),
                    'transfer_role')
        self.reject(self.altered('operations-0',lambda p:p['items'][1].update(value='1')),
                    'native_split_disagreement')

    def test_same_provider_other_api_disagreement_rejected(self):
        self.reject(self.altered('value-transfers',lambda p:p['result'][1].update(value='1')),
                    'same_provider_api_disagreement')
        self.reject(self.altered('value-transfers',lambda p:p['result'][1].update(isError='1')),
                    'compat_anchor')

    def test_resealed_zero_builder_total_profit_or_titan_coverage_rejected(self):
        for key,value in [('total_builder_compensation_wei','0'),('residual_is_realized_profit',True)]:
            r=copy.deepcopy(self.report);r['records'][0]['direct_payment_witness'][key]=value
            r.pop('report_commitment_sha256');seal(r)
            with self.assertRaisesRegex(ValueError,'differs_from_sources'):verify_report(r)
        r=copy.deepcopy(self.report);r['gas_funding_policy']['execution_coverage_proven']=True
        r['gas_policy_sha256']=digest(canonical(r['gas_funding_policy']));r.pop('report_commitment_sha256');seal(r)
        with self.assertRaisesRegex(ValueError,'differs_from_sources'):verify_report(r)


class DirectPaymentStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = create(Path(cls.tmp.name)/'evidence.sqlite')
        cls.result = store_report(cls.db)
        cls.snapshot = export_store(cls.db)
        cls.objects = read_batch(cls.db, cls.result['batch'])

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_authentic_eighth_batch_reconstructs_from_sources(self):
        self.assertEqual(query_report(self.db, self.result['batch']), self.result['report'])
        self.assertEqual(len(self.snapshot['batches']), 8)

    def test_exact_restore_and_ancestor_revocation_preserve_forensic_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            restored = Path(tmp)/'restored.sqlite'; restore_store(restored, self.snapshot)
            self.assertEqual(query_report(restored, self.result['batch']), self.result['report'])
            revoke(restored, self.result['root_batch'], 'TEST_ONLY', b'not a canonical chain reorg')
            after = export_store(restored); again = Path(tmp)/'again.sqlite'; restore_store(again, after)
            self.assertEqual(export_store(again), after)
            self.assertEqual(len(audit_store(again)['invalidated_batches']), 7)
            with self.assertRaisesRegex(ValueError, 'inactive_or_missing'):
                query_report(again, self.result['batch'])
            self.assertEqual(read_batch(again, self.result['batch'], include_revoked=True), self.objects)

    def test_parentless_self_consistent_batch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/'copy.sqlite'; restore_store(db, self.snapshot)
            bad = admit(db, self.objects, parents=[])
            with self.assertRaisesRegex(ValueError, 'missing_declared_parent'): query_report(db, bad)

    def test_resealed_report_and_inherited_evidence_cannot_be_laundered(self):
        for name in (REPORT_NAME, 'cashflow-report.json'):
            with tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp)/'copy.sqlite'; restore_store(db, self.snapshot)
                objects = dict(self.objects); v = strict_json(objects[name]); v['records'][0]['complete_costs'] = True
                objects[name] = canonical(v); bad = admit(db, objects, parents=[self.result['parent']])
                with self.assertRaises(ValueError): query_report(db, bad)

    def test_extra_objects_or_changed_capture_rejected_after_readmission(self):
        for name, value in [('unexpected.json', b'{}\n'),
                            (CAPTURE_NAME, self.objects[CAPTURE_NAME]+b' ')]:
            with tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp)/'copy.sqlite'; restore_store(db, self.snapshot)
                objects = dict(self.objects); objects[name] = value
                bad = admit(db, objects, parents=[self.result['parent']])
                with self.assertRaisesRegex(ValueError, 'batch_inventory|capture_changed'):
                    query_report(db, bad)

    def test_binding_retarget_or_extra_parent_rejected(self):
        for change_binding in (True, False):
            with tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp)/'copy.sqlite'; restore_store(db, self.snapshot)
                objects = dict(self.objects); parents = [self.result['parent']]
                if change_binding:
                    objects[BINDING_NAME] = canonical({'inclusion_batch': self.result['root_batch']})
                else: parents.append(self.result['root_batch'])
                bad = admit(db, objects, parents=parents)
                with self.assertRaisesRegex(ValueError, 'missing_declared_parent'): query_report(db, bad)

    def test_revoking_immediate_parent_blocks_child_and_readmission(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/'copy.sqlite'; restore_store(db, self.snapshot)
            revoke(db, self.result['parent'], 'TEST_ONLY', b'not a canonical chain reorg')
            status = audit_store(db)
            self.assertEqual(status['invalidated_batches'], [self.result['batch']])
            self.assertEqual(len(status['active_batches']), 6)
            with self.assertRaisesRegex(ValueError, 'inactive_or_missing'): query_report(db, self.result['batch'])
            with self.assertRaisesRegex(ValueError, 'cannot_readmit_invalidated_batch'):
                admit(db, self.objects, parents=[self.result['parent']])


class DirectPaymentReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network = {'interfaces': ['lo'], 'routable_network': False,
                       'network_namespace': 'net:[2]', 'parent_network_namespace': 'net:[1]'}
        cls.report = synthetic_replay(cls.network)

    def test_eight_batch_restore_replay_binds_titan_only_policy_offline(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_replay(self.report), self.report)
        self.assertEqual(self.report['blocked_batches'], 8)
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
            r = copy.deepcopy(self.report); report = r['direct_payment_report']
            report['summary'][key] = 1; reseal(report)
            with self.assertRaisesRegex(ValueError, 'differs_from_sources'): verify_replay(reseal(r))

    def test_routable_shared_or_malformed_namespace_rejected(self):
        for key, value in [('routable_network', True), ('interfaces', ['lo', 'eth0']),
                           ('network_namespace', 'net:[1]'), ('network_namespace', 2)]:
            r = copy.deepcopy(self.report); r['network'][key] = value
            with self.assertRaisesRegex(ValueError, 'direct_network'): verify_replay(reseal(r))

    def test_changed_restore_or_parent_commitment_rejected(self):
        for key, value in [('blocked_batches', 7), ('forensic_bytes_preserved', False),
                           ('inclusion_batch', '0'*64)]:
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


if __name__=='__main__':unittest.main()
