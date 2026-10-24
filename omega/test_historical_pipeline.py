"""Full real-artifact intake/store/restore tests, including self-consistent fraud."""
import copy
from pathlib import Path
import tempfile
import unittest

from evidence_store import admit, audit_store, create, export_store, read_batch, revoke
from historical_intake import EVIDENCE
from historical_pipeline import (LEDGER_NAME, SOURCE_NAMES, exercise, ingest, query,
                                  verify_output)
from integrity import canonical, digest, strict_json


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_real_pipeline_restore_and_reverification(self):
        report=exercise(self.root/'run')
        self.assertEqual(report['summary']['event_count'],139)
        self.assertEqual(report['summary']['transaction_count'],127)
        self.assertEqual(verify_output(self.root/'run'),report)
        self.assertTrue(report['replica_ledger_byte_identical'])
        self.assertTrue(report['revoked_query_rejected'])
        for name in ('real_chain_reorg_tested','remote_replication_tested','rust_store_integrated',
                     'new_acquisition_performed','census_closed','phase_advance_authorized'):
            self.assertIs(report[name],False)

    def test_repeated_ingestion_idempotent_and_receipts_once(self):
        store=create(self.root/'store.sqlite')
        first=ingest(store);second=ingest(store)
        self.assertEqual(first,second)
        self.assertEqual(audit_store(store)['event_count'],1)
        self.assertEqual(len(query(store,first['batch'])['records']),127)

    def test_self_consistent_fake_ledger_cannot_pass_content_addressed_storage(self):
        store=create(self.root/'store.sqlite');result=ingest(store)
        objects=read_batch(store,result['batch'])
        ledger=strict_json(objects[LEDGER_NAME]);row=ledger['records'][0]
        row['winner_address']='0x'+'1'*40
        row['record_commitment_sha256']=digest(canonical({k:v for k,v in row.items() if k!='record_commitment_sha256'}))
        ledger['ledger_commitment_sha256']=digest(canonical({k:v for k,v in ledger.items() if k!='ledger_commitment_sha256'}))
        objects[LEDGER_NAME]=canonical(ledger)
        fake=admit(store,objects)
        self.assertIn(fake,audit_store(store)['active_batches'])
        with self.assertRaisesRegex(ValueError,'differs_from_authenticated_sources'):
            query(store,fake)

    def test_stored_original_archive_substitution_rejected(self):
        store=create(self.root/'store.sqlite');result=ingest(store)
        objects=read_batch(store,result['batch']);objects['rmc016-events.zip']=b'fake'
        fake=admit(store,objects)
        with self.assertRaisesRegex(ValueError,'source_archive_changed'):query(store,fake)

    def test_partial_inventory_never_returns_partial_success(self):
        store=create(self.root/'store.sqlite');result=ingest(store)
        objects=read_batch(store,result['batch']);objects.pop('rmc016-receipts.zip')
        fake=admit(store,objects)
        with self.assertRaisesRegex(ValueError,'pipeline_inventory'):query(store,fake)

    def test_revoked_real_evidence_preserved_but_not_admitted(self):
        store=create(self.root/'store.sqlite');result=ingest(store)
        revoke(store,result['batch'],'REVIEW_NEEDED',b'controlled test witness')
        with self.assertRaisesRegex(ValueError,'inactive'):query(store,result['batch'])
        self.assertEqual(read_batch(store,result['batch'],include_revoked=True)[LEDGER_NAME],canonical(result['ledger']))

    def test_modified_report_cannot_claim_reorg_or_certification(self):
        run=self.root/'run';report=exercise(run)
        for key in ('real_chain_reorg_tested','census_closed','remote_replication_tested'):
            fake=copy.deepcopy(report);fake[key]=True
            fake['report_commitment_sha256']=digest(canonical({k:v for k,v in fake.items() if k!='report_commitment_sha256'}))
            (run/'report.json').write_bytes(canonical(fake))
            with self.assertRaisesRegex(ValueError,'report_differs_from_replay'):verify_output(run)

    def test_output_never_overwrites_existing_run(self):
        run=self.root/'run';exercise(run);before=(run/'report.json').read_bytes()
        with self.assertRaises(FileExistsError):exercise(run)
        self.assertEqual((run/'report.json').read_bytes(),before)

    def test_exported_snapshot_and_revocation_probe_are_rechecked(self):
        run=self.root/'run';exercise(run)
        original=(run/'snapshot.json').read_bytes()
        (run/'snapshot.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'exported_snapshot_mismatch'):verify_output(run)
        (run/'snapshot.json').write_bytes(original)
        (run/'revocation-probe.sqlite').unlink()
        create(run/'revocation-probe.sqlite')
        with self.assertRaisesRegex(ValueError,'revocation_probe_mismatch'):verify_output(run)

    def test_source_directory_and_output_symlinks_rejected(self):
        link=self.root/'link';link.symlink_to(EVIDENCE,target_is_directory=True)
        store=create(self.root/'store.sqlite')
        with self.assertRaisesRegex(ValueError,'symlink'):ingest(store,link)
        self.assertEqual(audit_store(store)['event_count'],0)
        with self.assertRaisesRegex(ValueError,'symlink_output'):exercise(link/'somewhere')


if __name__=='__main__':unittest.main()
