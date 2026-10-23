"""Transport/adversarial tests; synthetic verifier output is not Rust execution."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evidence_store import admit, audit_store, create, export_store, read_batch, revoke
from integrity import canonical, digest
import rust_store_intake as transport


class RustTransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = create(self.root/'source.sqlite')
        self.batch = admit(self.db, {'one': b'authentic bytes', 'two': b'other bytes'})
        revoke(self.db, self.batch, 'CONTROLLED_TEST', b'revocation evidence')
        self.snapshot = export_store(self.db)
        self.head = audit_store(self.db)['journal_head']
        self.objects = transport.snapshot_objects(self.snapshot, self.head)
        self.index = transport.inventory(self.objects)
        self.sid = digest(canonical(self.snapshot))
        self.directory = self.root/'objects'
        transport.write_transport(self.directory, self.objects)

    def restore(self, **kw):
        args = {'snapshot_id':self.sid,'expected_inventory':self.index,'expected_head':self.head}
        args.update(kw)
        return transport.restore_transport(self.directory, self.root/'restore.sqlite', **args)

    def verifier(self, **kw):
        row = {'RMC_004_OFFLINE_VERIFY':'PASS','format_version':1,'config_id':'a'*64,
            'chunks':4,'artifacts':len(self.index),'logical_bytes':sum(self.index.values()),
            'stored_bytes':999,'orphan_chunks':0,'orphan_artifacts':len(self.index),
            'abandoned_registrations':0,'staging_files':0,'streams':0,'ranges_certified':0,
            'tips_matched':0,'evidence_root':'b'*64}
        row.update(kw)
        return ''.join(f'{k}={v}\n' for k,v in row.items()).encode()

    def test_snapshot_and_revoked_bytes_roundtrip(self):
        result=self.restore()
        self.assertEqual(result['revoked_batches'], [self.batch])
        self.assertEqual(export_store(self.root/'restore.sqlite'), self.snapshot)
        self.assertEqual(read_batch(self.root/'restore.sqlite',self.batch,include_revoked=True),
                         read_batch(self.db,self.batch,include_revoked=True))
        with self.assertRaisesRegex(ValueError,'inactive'):read_batch(self.root/'restore.sqlite',self.batch)

    def test_external_journal_head_is_required_and_rejects_rollback(self):
        for head in (None, True, '', 'f'*64):
            with self.subTest(head=head), self.assertRaises(ValueError):self.restore(expected_head=head)
        self.assertFalse((self.root/'restore.sqlite').exists())

    def test_missing_snapshot_rejects_before_publication(self):
        (self.directory/self.sid).unlink()
        with self.assertRaisesRegex(ValueError,'external_inventory'):self.restore()
        self.assertFalse((self.root/'restore.sqlite').exists())

    def test_missing_payload_rejects(self):
        (self.directory/next(s for s in self.objects if s!=self.sid)).unlink()
        with self.assertRaisesRegex(ValueError,'external_inventory'):self.restore()

    def test_added_valid_object_rejects(self):
        raw=b'injected';(self.directory/digest(raw)).write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'external_inventory'):self.restore()

    def test_corrupt_object_rejects(self):
        (self.directory/self.sid).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'digest'):self.restore()

    def test_invalid_hash_name_rejects(self):
        (self.directory/'unknown').write_bytes(b'unknown')
        with self.assertRaisesRegex(ValueError,'object_name'):self.restore()

    def test_symlink_object_rejects(self):
        raw=(self.directory/self.sid).read_bytes();(self.directory/self.sid).unlink()
        (self.root/'target').write_bytes(raw);(self.directory/self.sid).symlink_to(self.root/'target')
        with self.assertRaisesRegex(ValueError,'symlink'):self.restore()

    def test_directory_object_rejects(self):
        (self.directory/('c'*64)).mkdir()
        with self.assertRaisesRegex(ValueError,'nonregular'):self.restore()

    def test_resealed_snapshot_cannot_replace_external_snapshot_id(self):
        changed=copy.deepcopy(self.snapshot);changed['journal'][0]['reason']='altered'
        raw=canonical(changed);(self.directory/self.sid).unlink();(self.directory/digest(raw)).write_bytes(raw)
        with self.assertRaises(ValueError):self.restore()

    def test_self_consistent_new_store_cannot_replace_external_head(self):
        db=create(self.root/'other.sqlite');admit(db,{'x':b'substitute'})
        snap=export_store(db)
        with self.assertRaisesRegex(ValueError,'external_checkpoint'):
            transport.snapshot_objects(snap,self.head)

    def test_snapshot_digest_and_duplicate_payloads_reject(self):
        for mutation in ('digest','duplicate'):
            snap=copy.deepcopy(self.snapshot)
            if mutation=='digest':snap['snapshot_sha256']='a'*64
            else:
                snap['objects'].append(snap['objects'][0])
                snap['snapshot_sha256']=digest(canonical({k:v for k,v in snap.items() if k!='snapshot_sha256'}))
            with self.assertRaises(ValueError):transport.snapshot_objects(snap,self.head)

    def test_existing_destination_never_overwritten(self):
        dest=self.root/'restore.sqlite';dest.write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError,'destination_exists'):self.restore()
        self.assertEqual(dest.read_bytes(),b'preserve')

    def test_output_symlink_and_existing_directory_reject(self):
        link=self.root/'link';link.symlink_to(self.directory,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'symlink'):transport.write_transport(link,self.objects)
        with self.assertRaises(FileExistsError):transport.write_transport(self.directory,self.objects)

    def test_repository_output_rejects(self):
        with self.assertRaisesRegex(ValueError,'unsafe_transport'):
            transport.new_directory(transport.ROOT/'omega/forbidden-output')

    def test_bridge_source_requires_reviewed_python_pin_update(self):
        raw=transport.read_bridge_source()
        self.assertEqual(digest(raw),transport.BRIDGE_SOURCE_SHA256)
        path=self.root/transport.BRIDGE_SOURCE;path.parent.mkdir();path.write_bytes(raw+b'\n')
        with self.assertRaisesRegex(ValueError,'bridge_source_pin_mismatch'):
            transport.read_bridge_source(self.root)

    def test_valid_orphan_inventory_is_exposed_without_range_claim(self):
        v=transport.parse_verifier(self.verifier(),self.index)
        self.assertEqual(v['orphan_artifacts'],len(self.index))
        self.assertEqual(v['ranges_certified'],0)

    def test_verifier_duplicate_missing_or_unknown_keys_reject(self):
        good=self.verifier()
        for raw in (good+b'artifacts=4\n',good.replace(b'streams=0\n',b''),good+b'unknown=0\n'):
            with self.assertRaises(ValueError):transport.parse_verifier(raw,self.index)

    def test_verifier_failed_or_truncated_result_rejects(self):
        for raw in (self.verifier(RMC_004_OFFLINE_VERIFY='FAIL'),b'',b'PASS',b'bad=shape=x\n'):
            with self.assertRaises(ValueError):transport.parse_verifier(raw,self.index)

    def test_verifier_range_and_hidden_orphan_claims_reject(self):
        for key in ('streams','ranges_certified','tips_matched','staging_files','orphan_chunks','abandoned_registrations'):
            with self.subTest(key=key),self.assertRaises(ValueError):
                transport.parse_verifier(self.verifier(**{key:1}),self.index)
        with self.assertRaises(ValueError):transport.parse_verifier(self.verifier(orphan_artifacts=0),self.index)

    def test_verifier_wrong_size_and_count_reject(self):
        for key in ('artifacts','logical_bytes'):
            with self.assertRaises(ValueError):transport.parse_verifier(self.verifier(**{key:1}),self.index)

    def test_verifier_noncanonical_numbers_and_digest_reject(self):
        for value in ('-1','01','1.0','True','NaN'):
            with self.assertRaises(ValueError):transport.parse_verifier(self.verifier(chunks=value),self.index)
        with self.assertRaises(ValueError):transport.parse_verifier(self.verifier(evidence_root='z'*64),self.index)

    def test_no_physical_run_admitted_on_connected_network(self):
        with self.assertRaisesRegex(ValueError,'network_not_isolated'):
            transport.exercise(self.root/'exercise','unused','unused',{'interfaces':['eth0']})

    def test_subprocess_failure_is_propagated_and_tokens_are_removed(self):
        import os
        from subprocess import CompletedProcess
        with patch.dict(os.environ,{'GH_TOKEN':'fixture','GITHUB_TOKEN':'fixture'}), \
             patch('rust_store_intake.subprocess.run',return_value=CompletedProcess([],1,b'',b'failed')) as called:
            with self.assertRaisesRegex(ValueError,'bridge_command_failed'):transport.call(['fixture'])
        self.assertNotIn('GH_TOKEN',called.call_args.kwargs['env'])
        self.assertNotIn('GITHUB_TOKEN',called.call_args.kwargs['env'])


def synthetic_report(network=None):
    """Fixture only. No process or physical bridge success is claimed by this helper."""
    with tempfile.TemporaryDirectory() as tmp:
        db=Path(tmp)/'source.sqlite';result=transport.fixture(db)
        head=audit_store(db)['journal_head'];snapshot=export_store(db)
        index=transport.inventory(transport.snapshot_objects(snapshot,head))
    verifier={'format_version':1,'config_id':'a'*64,'chunks':4,'artifacts':len(index),
        'logical_bytes':sum(index.values()),'stored_bytes':999,'orphan_chunks':0,
        'orphan_artifacts':len(index),'abandoned_registrations':0,'staging_files':0,
        'streams':0,'ranges_certified':0,'tips_matched':0,'evidence_root':'b'*64}
    report={'schema':transport.SCHEMA,'status':'RUST_ARTIFACT_TRANSPORT_PASS',
        'snapshot_sha256':digest(canonical(snapshot)),'journal_head':head,
        'inventory':index,'inventory_sha256':digest(canonical(index)),
        'temporal_report_commitment':result['report']['report_commitment_sha256'],
        'bridge_source_sha256':digest((transport.ROOT/transport.BRIDGE_SOURCE).read_bytes()),
        'rust_verifier':verifier,'network':network or {'interfaces':['lo'],'routable_network':False,
            'network_namespace':'net:[2]','parent_network_namespace':'net:[1]'},
        'rejection_cases':transport.REJECTION_CASES,
        'byte_identical_restore':True,'corruption_rejected':True,'missing_object_rejected':True,
        'revoked_bytes_preserved':True,'revoked_batch_query_rejected':True,'revocation_scope':'BATCH_LOCAL',
        'remote_replication_tested':False,'real_chain_reorg_tested':False,'certified_components':0,'census_closed':False}
    report['report_commitment_sha256']=digest(canonical(report))
    return report


class RustTransportReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.report=synthetic_report()

    def reseal(self, report):
        report['report_commitment_sha256']=digest(canonical({k:v for k,v in report.items()
                                                           if k!='report_commitment_sha256'}))

    def test_source_bound_report_shape_preserves_zero_certification(self):
        self.assertEqual(transport.verify_report(self.report),self.report)

    def test_resealed_false_success_or_extra_authority_rejects(self):
        for key,value in (('byte_identical_restore',False),('corruption_rejected',False),
                          ('certified_components',1),('census_closed',True),('can_sign',True),
                          ('revocation_scope','CROSS_BATCH'),('rejection_cases',[])):
            r=copy.deepcopy(self.report);r[key]=value;self.reseal(r)
            with self.subTest(key=key),self.assertRaises(ValueError):transport.verify_report(r)

    def test_resealed_foreign_snapshot_source_and_inventory_rejects(self):
        for key in ('snapshot_sha256','journal_head','bridge_source_sha256','temporal_report_commitment'):
            r=copy.deepcopy(self.report);r[key]='0'*64;self.reseal(r)
            with self.subTest(key=key),self.assertRaises(ValueError):transport.verify_report(r)

    def test_shared_network_namespace_rejects(self):
        r=copy.deepcopy(self.report);r['network']['network_namespace']=r['network']['parent_network_namespace'];self.reseal(r)
        with self.assertRaisesRegex(ValueError,'transport_namespace'):transport.verify_report(r)


if __name__ == '__main__': unittest.main()
