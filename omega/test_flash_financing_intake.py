import copy
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flash_financing_intake import (CAPTURE_NAME,EVIDENCE,MORPHO,build_cashflow,build_execution_report,
    build_ledger,build_payments,build_report,load_capture,operation_capture,reconcile,seal,verify_report)
from flash_financing_intake import (BINDING_NAME, REPORT_NAME, exercise, exercise_fields,
    query_report, store_report, verify_replay)
from evidence_store import admit, audit_store, create, export_store, read_batch, restore_store, revoke
from integrity import canonical,digest,strict_json


def reseal(report):
    report.pop('report_commitment_sha256', None); return seal(report)


def synthetic_replay(network):
    # Namespace IDs are fixtures, not evidence of a physical disconnected run.
    with tempfile.TemporaryDirectory() as tmp: report = exercise_fields(tmp)
    report['network'] = copy.deepcopy(network); return seal(report)


class FlashFinancingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture=load_capture();cls.cashflow=build_cashflow();cls.payments=build_payments()
        cls.operations=operation_capture();cls.ledger=build_ledger();cls.economics=build_execution_report()
        cls.report=build_report()

    def altered(self,mutate):
        c=copy.deepcopy(self.capture);r=c['record'];body=strict_json(r['raw_body'])
        mutate(body['result']);r['raw_body']=canonical(body).decode();r['raw_sha256']=digest(r['raw_body'].encode())
        return c

    def reject(self,capture,reason,operations=None):
        with self.assertRaisesRegex(ValueError,reason):
            reconcile(capture,self.cashflow,self.payments,operations or self.operations,self.ledger,self.economics)

    def test_exact_principal_and_repayment_zero_weth_premium(self):
        w=self.report['records'][0]['financing_witness']
        self.assertEqual(w['lender_address'],MORPHO)
        self.assertEqual(w['principal_wei'],'10684013854557827871')
        self.assertEqual(w['repayment_wei'],w['principal_wei'])
        self.assertEqual(w['observed_weth_repayment_premium_wei'],'0')
        self.assertIsNone(w['other_financing_costs_wei'])

    def test_normalized_receipt_agreement_is_not_full_parity_or_code_identity(self):
        w=self.report['records'][0]['financing_witness']
        self.assertTrue(w['normalized_receipt_matches_retained_drpc'])
        for k in ('full_receipt_cross_provider_parity','lender_deployed_code_identity_verified','raw_call_ancestry_proven'):
            self.assertFalse(w[k])

    def test_original_aave_simulation_remains_distinct_from_observed_morpho_repayment(self):
        w=self.report['records'][0]['financing_witness']
        self.assertEqual(w['retained_aave_fork_fee_wei'],'5342006927278914')
        for k in ('fork_fee_is_observed_winner_fee','nqc_morpho_route_validated','nqc_cost_saving_proven','current_flash_liquidity_verified'):
            self.assertFalse(w[k])

    def test_all_sample_identities_and_unknown_rows_preserved(self):
        self.assertEqual([r['transaction_hash'] for r in self.report['records']],
                         [r['transaction_hash'] for r in self.cashflow['records']])
        self.assertTrue(all(r['financing_witness'] is None for r in self.report['records'][1:]))
        for r in self.report['records']:
            self.assertFalse(r['complete_costs']);self.assertIsNone(r['complete_net_profit_wei'])
            self.assertFalse(r['nqc_execution']);self.assertFalse(r['titan_coverage_proven'])

    def test_titan_gas_policy_does_not_change_with_principal_lender(self):
        p=self.report['gas_funding_policy'];self.assertEqual(p['payer'],'TITAN')
        self.assertEqual(p['operator_gas_cap_mxn'],0)
        for k in ('operator_prefund_allowed','own_gas_fallback_allowed','execution_coverage_proven'):self.assertFalse(p[k])
        self.assertEqual(self.report['gas_policy_sha256'],digest(canonical(p)))

    def test_report_reproduces_without_network(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_report(self.report),self.report)

    def test_changed_capture_or_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/CAPTURE_NAME;p.write_bytes((EVIDENCE/CAPTURE_NAME).read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'capture_changed'):load_capture(tmp)
            p.unlink();p.symlink_to(EVIDENCE/CAPTURE_NAME)
            with self.assertRaisesRegex(ValueError,'symlink_input'):load_capture(tmp)

    def test_wrong_chain_request_and_raw_hash_rejected(self):
        for mutate,reason in [(lambda c:c.update(chain_id=True),'capture_scope'),
            (lambda c:c['record'].update(url=c['record']['url'].replace('/evm/1/','/evm/8453/')),'request'),
            (lambda c:c['record'].update(raw_sha256='0'*64),'raw_digest')]:
            c=copy.deepcopy(self.capture);mutate(c);self.reject(c,reason)

    def test_receipt_hash_block_index_and_actors_rejected(self):
        for k,v,reason in [('transactionHash','0x'+'0'*64,'receipt_anchor'),('blockHash','0x'+'0'*64,'receipt_anchor'),
                           ('transactionIndex','0x2','receipt_anchor'),('from','0x'+'1'*40,'receipt_actors')]:
            self.reject(self.altered(lambda r:r.update({k:v})),reason)

    def test_failed_or_unsupported_receipt_rejected(self):
        for k,v in [('status','0x0'),('type','0x3'),('contractAddress',MORPHO)]:
            self.reject(self.altered(lambda r:r.update({k:v})),'receipt_status')

    def test_gas_and_aave_log_disagreement_rejected_by_original_normalizer(self):
        self.reject(self.altered(lambda r:r.update(gasUsed='0x1')),'normalized_disagreement')
        self.reject(self.altered(lambda r:r['logs'][14].update(data='0x'+'0'*256)),'logs not equal|data|log')

    def test_missing_or_duplicate_receipt_log_rejected(self):
        self.reject(self.altered(lambda r:r['logs'].pop()),'log_inventory')
        self.reject(self.altered(lambda r:r['logs'][1].update(logIndex='0x7')),'log_inventory')

    def test_removed_log_and_timestamp_drift_rejected(self):
        for k,v in [('removed',True),('blockTimestamp','0x1')]:
            self.reject(self.altered(lambda r:r['logs'][0].update({k:v})),'log_anchor')

    def test_flash_event_caller_token_and_principal_changes_rejected(self):
        for i in (1,2):
            self.reject(self.altered(lambda r:r['logs'][0]['topics'].__setitem__(i,'0x'+'0'*64)),'flash_event')
        self.reject(self.altered(lambda r:r['logs'][0].update(data='0x'+'0'*63+'1')),'principal')

    def test_premium_shortfall_and_repayment_recipient_cannot_be_hidden(self):
        for delta in (-1,1):
            self.reject(self.altered(lambda r:r['logs'][15].update(data='0x'+format(int(r['logs'][15]['data'],16)+delta,'064x'))),'principal_repayment')
        self.reject(self.altered(lambda r:r['logs'][15]['topics'].__setitem__(2,'0x'+'0'*64)),'principal_repayment')

    def test_abi_padding_and_withdrawal_disagreement_rejected(self):
        self.reject(self.altered(lambda r:r['logs'][1]['topics'].__setitem__(1,'0x1'+r['logs'][1]['topics'][1][3:])),'address_padding')
        self.reject(self.altered(lambda r:r['logs'][16].update(data='0x'+'0'*64)),'withdrawal')

    def test_callback_target_selector_or_failure_rejected(self):
        for k,v in [('to','0x'+'1'*40),('methodId','0x00000000'),('status',False)]:
            o=copy.deepcopy(self.operations)
            for record in o['records'][:3]:
                page=strict_json(record['raw_body'])
                for call in page['items']:
                    if call['opIndex']==3:call[k]=v
                record['raw_body']=canonical(page).decode();record['raw_sha256']=digest(record['raw_body'].encode())
            self.reject(self.capture,'flash_call',o)

    def test_resealed_total_zero_cost_route_profit_or_titan_claim_rejected(self):
        for k,v in [('other_financing_costs_wei','0'),('nqc_morpho_route_validated',True),('nqc_cost_saving_proven',True)]:
            r=copy.deepcopy(self.report);r['records'][0]['financing_witness'][k]=v
            r.pop('report_commitment_sha256');seal(r)
            with self.assertRaisesRegex(ValueError,'differs_from_sources'):verify_report(r)
        r=copy.deepcopy(self.report);r['gas_funding_policy']['own_gas_fallback_allowed']=True
        r['gas_policy_sha256']=digest(canonical(r['gas_funding_policy']));r.pop('report_commitment_sha256');seal(r)
        with self.assertRaisesRegex(ValueError,'differs_from_sources'):verify_report(r)


class FlashFinancingStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = create(Path(cls.tmp.name)/'evidence.sqlite')
        cls.result = store_report(cls.db)
        cls.snapshot = export_store(cls.db)
        cls.objects = read_batch(cls.db, cls.result['batch'])

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_authentic_ninth_batch_reconstructs_from_sources(self):
        self.assertEqual(query_report(self.db, self.result['batch']), self.result['report'])
        self.assertEqual(len(self.snapshot['batches']), 9)

    def test_exact_restore_and_ancestor_revocation_preserve_forensic_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            restored = Path(tmp)/'restored.sqlite'; restore_store(restored, self.snapshot)
            self.assertEqual(query_report(restored, self.result['batch']), self.result['report'])
            revoke(restored, self.result['root_batch'], 'TEST_ONLY', b'not a canonical chain reorg')
            after = export_store(restored); again = Path(tmp)/'again.sqlite'; restore_store(again, after)
            self.assertEqual(export_store(again), after)
            self.assertEqual(len(audit_store(again)['invalidated_batches']), 8)
            with self.assertRaisesRegex(ValueError, 'inactive_or_missing'):
                query_report(again, self.result['batch'])
            self.assertEqual(read_batch(again, self.result['batch'], include_revoked=True), self.objects)

    def test_parentless_self_consistent_batch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/'copy.sqlite'; restore_store(db, self.snapshot)
            bad = admit(db, self.objects, parents=[])
            with self.assertRaisesRegex(ValueError, 'missing_declared_parent'): query_report(db, bad)

    def test_resealed_report_and_inherited_evidence_cannot_be_laundered(self):
        for name in (REPORT_NAME, 'direct-payment-report.json'):
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
                    objects[BINDING_NAME] = canonical({'direct_payment_batch': self.result['root_batch']})
                else: parents.append(self.result['root_batch'])
                bad = admit(db, objects, parents=parents)
                with self.assertRaisesRegex(ValueError, 'missing_declared_parent'): query_report(db, bad)

    def test_revoking_immediate_parent_blocks_child_and_readmission(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/'copy.sqlite'; restore_store(db, self.snapshot)
            revoke(db, self.result['parent'], 'TEST_ONLY', b'not a canonical chain reorg')
            status = audit_store(db)
            self.assertEqual(status['invalidated_batches'], [self.result['batch']])
            self.assertEqual(len(status['active_batches']), 7)
            with self.assertRaisesRegex(ValueError, 'inactive_or_missing'): query_report(db, self.result['batch'])
            with self.assertRaisesRegex(ValueError, 'cannot_readmit_invalidated_batch'):
                admit(db, self.objects, parents=[self.result['parent']])


class FlashFinancingReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network = {'interfaces': ['lo'], 'routable_network': False,
                       'network_namespace': 'net:[2]', 'parent_network_namespace': 'net:[1]'}
        cls.report = synthetic_replay(cls.network)

    def test_nine_batch_restore_replay_binds_titan_only_policy_offline(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_replay(self.report), self.report)
        self.assertEqual(self.report['blocked_batches'], 9)
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

    def test_observed_historical_financing_cannot_become_titan_coverage_or_complete_costs(self):
        for key in ('titan_covered_executions', 'complete_paid_cost_rows'):
            r = copy.deepcopy(self.report); report = r['flash_financing_report']
            report['summary'][key] = 1; reseal(report)
            with self.assertRaisesRegex(ValueError, 'differs_from_sources'): verify_replay(reseal(r))

    def test_routable_shared_or_malformed_namespace_rejected(self):
        for key, value in [('routable_network', True), ('interfaces', ['lo', 'eth0']),
                           ('network_namespace', 'net:[1]'), ('network_namespace', 2)]:
            r = copy.deepcopy(self.report); r['network'][key] = value
            with self.assertRaisesRegex(ValueError, 'financing_network'): verify_replay(reseal(r))

    def test_changed_restore_or_parent_commitment_rejected(self):
        for key, value in [('blocked_batches', 8), ('forensic_bytes_preserved', False),
                           ('direct_payment_batch', '0'*64)]:
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
