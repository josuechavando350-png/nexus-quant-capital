"""Authenticated real-source graph tests; fake verifier output is not Rust proof."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import dependency_intake as dep
from evidence_store import admit,audit_store,create,export_store,read_batch,restore_store,revoke
from integrity import canonical,digest
from rust_store_intake import inventory,restore_transport,snapshot_objects,write_transport
from temporal_intake import query_temporal_report


def synthetic_report(network):
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'source.sqlite';prepared=dep.fixture(path)
        fields=dep.expected_fields(path,prepared)
    n=len(fields['inventory'])
    fields.update(network=network,rust_verifier={'format_version':1,'config_id':'a'*64,
        'chunks':125,'artifacts':n,'logical_bytes':sum(fields['inventory'].values()),'stored_bytes':999,
        'orphan_chunks':0,'orphan_artifacts':n,'abandoned_registrations':0,'staging_files':0,
        'streams':0,'ranges_certified':0,'tips_matched':0,'evidence_root':'b'*64})
    fields['report_commitment_sha256']=digest(canonical(fields));return fields


class DependencyIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'source.sqlite'

    def test_authentic_five_stage_chain_declares_every_adjacent_edge(self):
        create(self.path);result=dep.store_chain(self.path);s=audit_store(self.path)
        self.assertEqual(s['batch_count'],5);previous=[]
        for stage in dep.STAGES:
            batch=result['batches'][stage]
            self.assertEqual(s['dependencies'][batch],previous)
            self.assertNotEqual(batch,result['source_batches'][stage]);previous=[batch]
        self.assertEqual(query_temporal_report(self.path,result['batches']['temporal']),result['report'])

    def test_authentic_root_revocation_blocks_temporal_query_and_retains_forensics(self):
        result=dep.fixture(self.path);b=result['chain']['batches']['temporal']
        with self.assertRaisesRegex(ValueError,'inactive'):query_temporal_report(self.path,b)
        self.assertTrue(read_batch(self.path,b,include_revoked=True))
        self.assertEqual(result['status']['active_batches'],[result['unrelated']])
        self.assertEqual(len(result['status']['invalidated_batches']),4)

    def test_authentic_revoked_graph_restore_keeps_exact_status_and_payloads(self):
        result=dep.fixture(self.path);snapshot=export_store(self.path)
        out=self.root/'restore.sqlite';restore_store(out,snapshot)
        self.assertEqual(audit_store(out),result['status']);self.assertEqual(export_store(out),snapshot)
        for b in result['chain']['batches'].values():
            with self.assertRaises(ValueError):read_batch(out,b)
            self.assertEqual(read_batch(out,b,include_revoked=True),read_batch(self.path,b,include_revoked=True))

    def test_authentic_old_snapshot_rejected_against_new_external_head(self):
        prepared=dep.fixture(self.path);old=prepared['before']
        old_head=digest(canonical(old['journal'][-1]));objects=snapshot_objects(old,old_head)
        write_transport(self.root/'old',objects)
        with self.assertRaisesRegex(ValueError,'external_checkpoint'):
            restore_transport(self.root/'old',self.root/'no.sqlite',snapshot_id=digest(canonical(old)),
                expected_inventory=inventory(objects),expected_head=prepared['status']['journal_head'])
        self.assertFalse((self.root/'no.sqlite').exists())

    def test_repeated_chain_is_idempotent_but_revoked_chain_cannot_be_resurrected(self):
        create(self.path);first=dep.store_chain(self.path);before=export_store(self.path)
        self.assertEqual(dep.store_chain(self.path),first);self.assertEqual(export_store(self.path),before)
        revoke(self.path,first['batches']['ledger'],'TEST_ONLY',b'proof')
        with self.assertRaisesRegex(ValueError,'cannot_readmit'):dep.store_chain(self.path)

    def test_interrupted_chain_retains_only_complete_stages_and_resumes(self):
        create(self.path);count=0
        def interrupted(*a,**kw):
            nonlocal count
            count+=1
            if count==3:raise RuntimeError('controlled interruption')
            return admit(*a,**kw)
        with patch('dependency_intake.admit',side_effect=interrupted),self.assertRaises(RuntimeError):
            dep.store_chain(self.path)
        self.assertEqual(audit_store(self.path)['batch_count'],2)
        result=dep.store_chain(self.path)
        self.assertEqual(audit_store(self.path)['batch_count'],5)
        self.assertEqual(query_temporal_report(self.path,result['batches']['temporal']),result['report'])

    def test_source_validation_failure_stops_before_publication(self):
        create(self.path)
        def reject(*args,**kwargs):raise ValueError('controlled source mismatch')
        with patch('dependency_intake.VALIDATORS',(reject,*dep.VALIDATORS[1:])):
            with self.assertRaisesRegex(ValueError,'source mismatch'):dep.store_chain(self.path)
        self.assertEqual(audit_store(self.path)['batch_count'],0)


class DependencyReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=synthetic_report({'interfaces':['lo'],'routable_network':False,
            'network_namespace':'net:[1]','parent_network_namespace':'net:[2]'})

    def seal(self,r):
        r['report_commitment_sha256']=digest(canonical({k:v for k,v in r.items() if k!='report_commitment_sha256'}))

    def test_source_reconstruction_validates_graph_not_only_boolean_claims(self):
        self.assertEqual(dep.verify_report(self.report),self.report)
        for key,value in (('blocked_batches',4),('dependency_edges',3),('canonical_reorg_tested',True),
                          ('remote_replication_tested',True),('forensic_bytes_preserved',False),
                          ('whole_chain_atomic',True),('undeclared_dependencies_inferred',True)):
            r=copy.deepcopy(self.report);r[key]=value;self.seal(r)
            with self.assertRaises(ValueError):dep.verify_report(r)

    def test_resealed_graph_and_external_anchor_substitutions_rejected(self):
        for mutate in (lambda r:r['batches'].__setitem__('ledger','f'*64),
                       lambda r:r.__setitem__('snapshot_id','f'*64),
                       lambda r:r.__setitem__('journal_head','f'*64),
                       lambda r:r['store_status'].__setitem__('invalidated_batches',[]),
                       lambda r:r['source_batches'].__setitem__('state','f'*64)):
            r=copy.deepcopy(self.report);mutate(r);self.seal(r)
            with self.assertRaises(ValueError):dep.verify_report(r)

    def test_fake_network_or_range_authority_rejected(self):
        for mutate in (lambda r:r['network'].__setitem__('routable_network',True),
                       lambda r:r['network'].__setitem__('network_namespace','net:[2]'),
                       lambda r:r['rust_verifier'].__setitem__('ranges_certified',1),
                       lambda r:r['rust_verifier'].__setitem__('orphan_artifacts',0)):
            r=copy.deepcopy(self.report);mutate(r);self.seal(r)
            with self.assertRaises(ValueError):dep.verify_report(r)


if __name__=='__main__':unittest.main()
