"""Real raw-log captures; mutation tests never serve as economic evidence."""
import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from evidence_store import admit, audit_store, create, export_store, read_batch, restore_store, revoke
from historical_intake import EVIDENCE, build_ledger
from historical_pipeline import LEDGER_NAME
from integrity import canonical, digest, strict_json
from liquidator_intake import (CAPTURE_NAMES, POOL, build_liquidator_report, load_logs,
                               query_identities, reconcile_logs, store_identities)


class LiquidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger=build_ledger();cls.logs,cls.captures=load_logs();cls.report=build_liquidator_report()

    def test_all_real_events_transactions_and_liquidators_reconciled(self):
        s=self.report['summary']
        self.assertEqual((s['event_count'],s['transaction_count'],s['identified_liquidator_transaction_count']),
                         (139,127,127))
        self.assertEqual(s['distinct_liquidator_addresses'],49)
        self.assertEqual(s['distinct_borrower_addresses'],127)
        self.assertEqual(s['execution_gas_wei_once_per_transaction'],'448369976498898050')

    def test_known_raw_liquidator_is_event_argument_not_transaction_sender(self):
        row=next(r for r in self.report['events'] if r['transaction_hash']==
                 '0x26999547ac702620082e73079a77b062336c191773331e85dcd1ab33afc0b1ac')
        self.assertEqual(row['liquidator_address'],'0x1f2f10d1c40777ae1da742455c65828ff36df387')
        self.assertEqual(row['borrower_address'],'0x15b21c0a06faacac1fbbd47666d1980397c63742')
        self.assertEqual(row['liquidator_role'],'AAVE_LIQUIDATION_CALL_EVENT_ARGUMENT')
        self.assertFalse(row['beneficial_owner_identified'])

    def test_oracle_costs_removal_and_new_block_hashes_remain_unknown(self):
        for row in self.report['events']:
            for key in ('oracle_update_block','oracle_to_liquidator_blocks',
                        'builder_payment_usd_wad','complete_net_margin_usd_wad','removed_status'):
                self.assertIsNone(row[key])
            self.assertEqual(row['block_hash_basis'],'PINNED_ORIGINAL_NOT_NEWLY_OBSERVED')
        for key in ('block_hashes_reobserved','full_receipt_parity_complete',
                    'independent_full_window_event_consensus','new_api_query_performed'):
            self.assertIs(self.report[key],False)

    def test_position_locator_is_explicit_and_not_protocol_truth_certificate(self):
        for row in self.report['events']:
            self.assertEqual(row['position_locator']['pool'],POOL)
            self.assertEqual(row['position_locator_sha256'],digest(canonical(row['position_locator'])))
            self.assertFalse(row['protocol_position_truth_certified'])

    def test_no_network_during_reproduction(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            self.assertEqual(build_liquidator_report(),self.report)

    def reject_log(self,mutate):
        logs=copy.deepcopy(self.logs);mutate(logs)
        with self.assertRaises((ValueError,KeyError,TypeError)):
            reconcile_logs(self.ledger,logs)

    def test_missing_extra_duplicate_or_unknown_events_rejected(self):
        for mutate in (lambda r:r.pop(),lambda r:r.append(r[0]),
                       lambda r:r.__setitem__(1,copy.deepcopy(r[0])),
                       lambda r:r[0].__setitem__('transactionHash','0x'+'0'*64)):
            self.reject_log(mutate)

    def test_changed_liquidator_borrower_and_quantities_fail_original_commitment(self):
        for mutate in (lambda r:r[0].__setitem__('data',r[0]['data'][:155]+'1'+r[0]['data'][156:]),
                       lambda r:r[0]['topics'].__setitem__(3,'0x'+'0'*64),
                       lambda r:r[0].__setitem__('data','0x'+'0'*256)):
            self.reject_log(mutate)

    def test_wrong_block_index_and_log_index_rejected(self):
        for key in ('blockNumber','transactionIndex','logIndex'):
            self.reject_log(lambda r:r[0].__setitem__(key,'0x0'))

    def test_missing_or_malformed_hex_quantities_do_not_become_zero(self):
        for key in ('gasUsed','gasPrice','blockNumber','logIndex'):
            for value in (None,True,'0x00','-1','1','0X1','0x1\n'):
                with self.subTest(key=key,value=value):
                    self.reject_log(lambda r:r[0].__setitem__(key,value))

    def test_blockscout_gas_metadata_must_match_original_drpc(self):
        for key in ('gasUsed','gasPrice'):
            self.reject_log(lambda r:r[0].__setitem__(key,'0x1'))

    def test_wrong_pool_topics_abi_length_and_extra_claims_reject(self):
        for mutate in (lambda r:r[0].__setitem__('address','0x'+'0'*40),
                       lambda r:r[0]['topics'].pop(),
                       lambda r:r[0].__setitem__('data','0x00'),
                       lambda r:r[0].__setitem__('blockHash','0x'+'0'*64)):
            self.reject_log(mutate)

    def test_legacy_decoded_fingerprint_disagreement_rejected(self):
        bad=copy.deepcopy(self.ledger)
        row=next(r for r in bad['records'] if r['transaction_hash']==self.logs[0]['transactionHash'])
        row['liquidation_legs'][0]['liquidator_identity_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'original_leg'):
            reconcile_logs(bad,self.logs)

    def test_reordered_logs_have_identical_canonical_output(self):
        self.assertEqual(reconcile_logs(self.ledger,list(reversed(self.logs))),self.report['events'])

    def test_pin_archive_and_symlink_changes_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for name in CAPTURE_NAMES:shutil.copyfile(EVIDENCE/name,p/name)
            (p/'liquidator-capture-pin.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'pin_changed'):load_logs(p)
            shutil.copyfile(EVIDENCE/'liquidator-capture-pin.json',p/'liquidator-capture-pin.json')
            (p/'liquidator-log-capture.zip').write_bytes(b'fake')
            with self.assertRaisesRegex(ValueError,'archive_changed'):load_logs(p)
            (p/'liquidator-log-capture.zip').unlink()
            (p/'liquidator-log-capture.zip').symlink_to(EVIDENCE/'liquidator-log-capture.zip')
            with self.assertRaisesRegex(ValueError,'symlink'):load_logs(p)

    def test_real_identity_store_restore_revalidates_source_and_raw_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);db=create(p/'db');stored=store_identities(db)
            self.assertEqual(query_identities(db,stored['identity_batch']),self.report)
            restored=p/'copy';restore_store(restored,export_store(db))
            self.assertEqual(query_identities(restored,stored['identity_batch']),self.report)
            self.assertEqual(audit_store(restored),audit_store(db))

    def test_resealed_false_identity_in_valid_store_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=create(Path(tmp)/'db');stored=store_identities(db)
            objects=read_batch(db,stored['identity_batch']);fake=copy.deepcopy(self.report)
            fake['events'][0]['liquidator_address']='0x'+'0'*40
            fake['report_commitment_sha256']=digest(canonical({k:v for k,v in fake.items() if k!='report_commitment_sha256'}))
            objects['liquidator-report.json']=canonical(fake);new=admit(db,objects)
            with self.assertRaisesRegex(ValueError,'stored_identity_differs'):query_identities(db,new)

    def test_tampered_base_ledger_not_ignored_by_identity_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=create(Path(tmp)/'db');stored=store_identities(db)
            objects=read_batch(db,stored['identity_batch']);objects[LEDGER_NAME]=b'{}\n'
            new=admit(db,objects)
            with self.assertRaisesRegex(ValueError,'ledger_differs'):query_identities(db,new)

    def test_revoked_identity_batch_never_appears_as_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=create(Path(tmp)/'db');stored=store_identities(db)
            revoke(db,stored['identity_batch'],'CONTROLLED_TEST',b'withdrawal witness')
            with self.assertRaisesRegex(ValueError,'inactive'):query_identities(db,stored['identity_batch'])
            self.assertIn(stored['base_batch'],audit_store(db)['active_batches'])


if __name__=='__main__':unittest.main()
