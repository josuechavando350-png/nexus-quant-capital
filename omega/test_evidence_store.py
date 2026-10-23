"""Process death, concurrency, replay, hostile inputs, immutable recovery tests."""
import copy
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from evidence_store import (MAX_OBJECT, ZERO, admit, audit_store, connect, create,
    export_store, read_batch, restore_store, revoke)
from integrity import canonical, digest

ROOT = Path(__file__).resolve().parent


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = create(self.root/'vault.sqlite')
        self.objects = {'a.json': b'{"observation":1}\n', 'b.bin': b'authentic bytes are not claimed by this test'}

    def test_empty_store_and_idempotent_admission(self):
        self.assertEqual(audit_store(self.path)['journal_head'], ZERO)
        first = admit(self.path, self.objects)
        before = export_store(self.path)
        self.assertEqual(admit(self.path, self.objects), first)
        self.assertEqual(export_store(self.path), before)
        self.assertEqual(read_batch(self.path, first), self.objects)

    def test_exception_rolls_back_complete_transaction(self):
        for step in ('objects_written','before_commit'):
            def fail(actual):
                if actual == step: raise RuntimeError('injected crash')
            with self.assertRaises(RuntimeError):
                admit(self.path,self.objects,_fault=fail)
            state=audit_store(self.path)
            self.assertEqual((state['object_count'],state['batch_count'],state['event_count']),(0,0,0))

    def crash_process(self, point):
        script = """
import os,sys
sys.path.insert(0,sys.argv[1])
from evidence_store import admit
def fault(point):
    if point==sys.argv[3]:os._exit(73)
admit(sys.argv[2], {'a.bin':b'crash-safe payload'}, _fault=fault)
"""
        return subprocess.run([sys.executable,'-B','-c',script,str(ROOT),str(self.path),point],capture_output=True)

    def test_process_death_before_commit_recovers_without_partial_batch(self):
        for point in ('objects_written','before_commit'):
            result=self.crash_process(point)
            self.assertEqual(result.returncode,73,result.stderr)
            state=audit_store(self.path)
            self.assertEqual((state['object_count'],state['batch_count'],state['event_count']),(0,0,0))

    def test_process_death_after_commit_preserves_complete_batch(self):
        result=self.crash_process('after_commit')
        self.assertEqual(result.returncode,73,result.stderr)
        state=audit_store(self.path)
        self.assertEqual((state['object_count'],state['batch_count'],state['event_count']),(1,1,1))
        self.assertEqual(read_batch(self.path,state['active_batches'][0]),{'a.bin':b'crash-safe payload'})

    def test_concurrent_duplicate_writers_publish_once(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            ids=list(pool.map(lambda _:admit(self.path,self.objects),range(12)))
        self.assertEqual(len(set(ids)),1)
        self.assertEqual(audit_store(self.path)['event_count'],1)

    def test_concurrent_distinct_writers_preserve_all_journal_links(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            ids=list(pool.map(lambda i:admit(self.path,{'row.json':canonical({'i':i})}),range(12)))
        status=audit_store(self.path)
        self.assertEqual(len(set(ids)),12)
        self.assertEqual(status['event_count'],12)
        self.assertEqual(status['active_batches'],sorted(ids))

    def test_revocation_preserves_bytes_excludes_default_queries(self):
        batch=admit(self.path,self.objects)
        revoke(self.path,batch,'CONFLICTING_BLOCK_WITNESS',b'illustrative conflict witness')
        state=audit_store(self.path)
        self.assertEqual(state['active_batches'],[])
        self.assertEqual(state['revoked_batches'],[batch])
        self.assertFalse(state['canonical_chain_verified'])
        with self.assertRaisesRegex(ValueError,'inactive'):
            read_batch(self.path,batch)
        self.assertEqual(read_batch(self.path,batch,include_revoked=True),self.objects)
        with self.assertRaisesRegex(ValueError,'cannot_readmit'):
            admit(self.path,self.objects)
        with self.assertRaisesRegex(ValueError,'inactive'):
            revoke(self.path,batch,'again',b'proof')

    def test_export_restore_retains_revocation_and_exact_inventory(self):
        first=admit(self.path,self.objects)
        second=admit(self.path,{'new.json':b'new payload'})
        revoke(self.path,first,'REVIEW_WITHDRAWN',b'review evidence')
        before=export_store(self.path)
        target=self.root/'restored.sqlite'
        result=restore_store(target,before)
        self.assertEqual(export_store(target),before)
        self.assertEqual(result['active_batches'],[second])
        self.assertEqual(result['revoked_batches'],[first])
        with self.assertRaisesRegex(ValueError,'destination_exists'):
            restore_store(target,before)

    def reseal(self,snapshot):
        snapshot['snapshot_sha256']=digest(canonical({k:v for k,v in snapshot.items() if k!='snapshot_sha256'}))
        return snapshot

    def test_snapshot_corruption_rejected_without_publication(self):
        admit(self.path,self.objects)
        good=export_store(self.path)
        mutations=(lambda x:x['objects'][0].__setitem__('hex','00'),
                   lambda x:x['objects'].pop(),
                   lambda x:x['objects'].append(x['objects'][0]),
                   lambda x:x['journal'][0].__setitem__('previous','1'*64),
                   lambda x:x['journal'][0].__setitem__('sequence',2),
                   lambda x:x['journal'][0].__setitem__('kind','GO'),
                   lambda x:x['batches'][0]['objects'].pop('a.json'))
        for mutate in mutations:
            bad=copy.deepcopy(good);mutate(bad);self.reseal(bad)
            target=self.root/'bad.sqlite'
            with self.assertRaises((ValueError,sqlite3.DatabaseError)):
                restore_store(target,bad)
            self.assertFalse(target.exists())

    def test_external_checkpoint_detects_valid_prefix_rollback(self):
        admit(self.path,self.objects)
        before=export_store(self.path)
        admit(self.path,{'later.bin':b'later evidence'})
        head=audit_store(self.path)['journal_head']
        restore_store(self.root/'old.sqlite',before)
        with self.assertRaisesRegex(ValueError,'external_checkpoint_mismatch'):
            audit_store(self.root/'old.sqlite',expected_head=head)
        self.assertEqual(audit_store(self.path,expected_head=head)['journal_head'],head)

    def test_storage_immutability_triggers_prevent_update_delete(self):
        admit(self.path,self.objects)
        db=connect(self.path)
        try:
            for table in ('objects','batches','journal','metadata'):
                with self.assertRaisesRegex(sqlite3.IntegrityError,'append_only'):
                    db.execute(f'DELETE FROM {table}')
            with self.assertRaisesRegex(sqlite3.IntegrityError,'append_only'):
                db.execute("UPDATE objects SET payload=x'00'")
        finally:db.close()

    def test_bypassed_trigger_corruption_detected_on_read(self):
        batch=admit(self.path,self.objects)
        db=connect(self.path)
        db.execute('DROP TRIGGER immutable_objects_UPDATE')
        db.execute("UPDATE objects SET payload=x'00'");db.close()
        with self.assertRaisesRegex(ValueError,'store_schema_changed'):
            read_batch(self.path,batch)

    def test_symlink_path_parent_and_sidecar_rejected(self):
        link=self.root/'link.sqlite';link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError,'symlink'):
            audit_store(link)
        parent=self.root/'alias';parent.symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'symlink'):
            create(parent/'other.sqlite')
        sidecar=Path(str(self.path)+'-journal');sidecar.symlink_to(self.root/'victim')
        with self.assertRaisesRegex(ValueError,'unsafe_store_sidecar'):
            audit_store(self.path)

    def test_path_traversal_empty_and_oversize_objects_rejected(self):
        for objects in ({'../outside':b'x'}, {}, {'x':b''}, {'x':b'0'*(MAX_OBJECT+1)}, {'x':'text'}):
            with self.assertRaises(ValueError):admit(self.path,objects)
        self.assertEqual(audit_store(self.path)['event_count'],0)

    def test_missing_proof_or_unknown_batch_cannot_revoke(self):
        batch=admit(self.path,self.objects)
        for args in ((batch,'why',b''),(ZERO,'why',b'proof'),(batch,'',b'proof')):
            with self.assertRaises(ValueError):revoke(self.path,*args)
        self.assertEqual(audit_store(self.path)['active_batches'],[batch])

    def test_create_never_overwrites_existing_store(self):
        admit(self.path,self.objects);before=self.path.read_bytes()
        with self.assertRaises(FileExistsError):create(self.path)
        self.assertEqual(self.path.read_bytes(),before)


class DependencyStoreTests(unittest.TestCase):
    setUp = StoreTests.setUp

    def graph(self):
        a=admit(self.path,{'a':b'root A'},parents=[])
        b=admit(self.path,{'b':b'root B'},parents=[])
        c=admit(self.path,{'c':b'derived'},parents=[a,b])
        d=admit(self.path,{'d':b'descendant'},parents=[c])
        u=admit(self.path,{'u':b'unrelated'},parents=[])
        return a,b,c,d,u

    def test_transitive_diamond_revocation_preserves_unrelated_evidence(self):
        a,b,c,d,u=self.graph();before=export_store(self.path)
        revoke(self.path,a,'TEST_ONLY',b'controlled proof')
        s=audit_store(self.path)
        self.assertEqual(s['active_batches'],sorted([b,u]))
        self.assertEqual(s['invalidated_batches'],sorted([c,d]))
        self.assertEqual(s['blocking_revocations'],{a:[a],c:[a],d:[a]})
        self.assertEqual(s['event_count'],6)
        for batch in (a,c,d):
            with self.assertRaisesRegex(ValueError,'inactive'):read_batch(self.path,batch)
            self.assertTrue(read_batch(self.path,batch,include_revoked=True))
        self.assertEqual(export_store(self.path)['batches'],before['batches'])

    def test_multiple_roots_and_explicit_revocation_of_invalidated_batch(self):
        a,b,c,d,u=self.graph()
        for batch in (a,b,c):revoke(self.path,batch,'TEST_ONLY',b'proof')
        s=audit_store(self.path)
        self.assertEqual(s['blocking_revocations'][d],sorted([a,b,c]))
        self.assertEqual(s['revoked_batches'],sorted([a,b,c]))
        self.assertEqual(s['invalidated_batches'],[d])

    def test_revoke_descendant_does_not_revoke_ancestors(self):
        a,b,c,d,u=self.graph();revoke(self.path,c,'TEST',b'proof')
        self.assertEqual(audit_store(self.path)['active_batches'],sorted([a,b,u]))

    def test_parent_set_canonical_and_duplicate_admission_has_no_extra_event(self):
        a,b,_,_,_=self.graph();objects={'x':b'new'}
        x=admit(self.path,objects,parents=[a,b]);snapshot=export_store(self.path)
        self.assertEqual(x,admit(self.path,objects,parents=[b,a]))
        self.assertEqual(snapshot,export_store(self.path))

    def test_same_payload_different_dependencies_has_distinct_identity(self):
        a,b,_,_,_=self.graph()
        self.assertNotEqual(admit(self.path,self.objects,parents=[a]),admit(self.path,self.objects,parents=[b]))
        self.assertNotEqual(admit(self.path,self.objects),admit(self.path,self.objects,parents=[]))

    def test_missing_or_invalid_parent_inventory_cannot_publish(self):
        a,*_=self.graph();before=export_store(self.path)
        for parents in (True,'bad',{},[a,a],[None],[ZERO],[a]*257):
            with self.subTest(parents=parents),self.assertRaises(ValueError):
                admit(self.path,{'new':b'no publish'},parents=parents)
            self.assertEqual(before,export_store(self.path))

    def test_cannot_admit_or_readmit_through_revoked_ancestor(self):
        a,b,c,d,u=self.graph();revoke(self.path,a,'TEST',b'proof');before=export_store(self.path)
        for parent in (a,c,d):
            with self.assertRaisesRegex(ValueError,'dependency_inactive'):
                admit(self.path,{'new':b'rejected'},parents=[parent])
        with self.assertRaisesRegex(ValueError,'cannot_readmit_invalidated'):
            admit(self.path,{'c':b'derived'},parents=[a,b])
        self.assertEqual(before,export_store(self.path))

    def test_legacy_batches_keep_original_identity_and_scope(self):
        a=admit(self.path,{'x':b'one'});b=admit(self.path,{'x':b'one','y':b'two'})
        self.assertNotIn('dependencies',audit_store(self.path))
        revoke(self.path,a,'TEST',b'proof')
        self.assertEqual(read_batch(self.path,b),{'x':b'one','y':b'two'})

    def test_new_dependency_can_bind_legacy_parent(self):
        a=admit(self.path,{'x':b'legacy'});b=admit(self.path,{'y':b'new'},parents=[a])
        revoke(self.path,a,'TEST',b'proof')
        self.assertEqual(audit_store(self.path)['invalidated_batches'],[b])

    def test_restored_graph_preserves_all_causal_revocation_evidence(self):
        a,b,c,d,u=self.graph();revoke(self.path,a,'TEST',b'proof')
        snapshot=export_store(self.path);out=self.root/'restored.sqlite';restore_store(out,snapshot)
        self.assertEqual(audit_store(out),audit_store(self.path))
        self.assertEqual(export_store(out),snapshot)
        for batch in (a,c,d):
            with self.assertRaises(ValueError):read_batch(out,batch)
            self.assertEqual(read_batch(out,batch,include_revoked=True),read_batch(self.path,batch,include_revoked=True))

    def test_old_snapshot_cannot_match_current_external_head(self):
        a,*_=self.graph();old=export_store(self.path);revoke(self.path,a,'TEST',b'proof')
        head=audit_store(self.path)['journal_head'];out=self.root/'old.sqlite';restore_store(out,old)
        with self.assertRaisesRegex(ValueError,'external_checkpoint'):audit_store(out,head)

    def rewrite_order(self,snapshot,events):
        previous=ZERO
        for i,event in enumerate(events,1):
            event.update(sequence=i,previous=previous);previous=digest(canonical(event))
        snapshot['journal']=events
        snapshot['snapshot_sha256']=digest(canonical({k:v for k,v in snapshot.items() if k!='snapshot_sha256'}))

    def test_resealed_forward_admission_and_admission_after_revocation_rejected(self):
        a,b,c,d,u=self.graph();revoke(self.path,a,'TEST',b'proof');base=export_store(self.path)
        for i,order in enumerate(([2,0,1,3,4,5],[0,1,5,2,3,4])):
            s=copy.deepcopy(base);self.rewrite_order(s,[s['journal'][j] for j in order])
            out=self.root/f'reject-{i}.sqlite'
            with self.assertRaisesRegex(ValueError,'dependency_not_active'):restore_store(out,s)
            self.assertFalse(out.exists())

    def test_resealed_invalid_parent_manifest_rejected_without_destination(self):
        self.graph();base=export_store(self.path)
        for i,parents in enumerate(([ZERO],None,True,{},['x'])):
            s=copy.deepcopy(base);m=s['batches'][0];old=digest(canonical(m));m['parents']=parents
            new=digest(canonical(m))
            for event in s['journal']:
                if event['batch']==old:event['batch']=new
            self.rewrite_order(s,s['journal']);out=self.root/f'bad-{i}.sqlite'
            with self.assertRaises(ValueError):restore_store(out,s)
            self.assertFalse(out.exists())

    def revoke_crash(self,batch,point):
        script="""
import os,sys
sys.path.insert(0,sys.argv[1])
from evidence_store import revoke
def fault(point):
    if point==sys.argv[4]:os._exit(73)
revoke(sys.argv[2],sys.argv[3],'TEST',b'proof',_fault=fault)
"""
        r=subprocess.run([sys.executable,'-B','-c',script,str(ROOT),str(self.path),batch,point],capture_output=True)
        self.assertEqual(r.returncode,73,r.stderr)

    def test_process_death_before_revocation_commit_leaves_entire_graph_active(self):
        a,*_=self.graph();before=export_store(self.path)
        for point in ('proof_written','before_commit'):
            self.revoke_crash(a,point);self.assertEqual(export_store(self.path),before)

    def test_process_death_after_revocation_commit_blocks_entire_descendant_set(self):
        a,b,c,d,u=self.graph();self.revoke_crash(a,'after_commit')
        s=audit_store(self.path);self.assertEqual(s['active_batches'],sorted([b,u]))
        self.assertEqual(s['invalidated_batches'],sorted([c,d]))

    def test_competing_admission_and_revocation_cannot_leave_active_descendant(self):
        a=admit(self.path,{'a':b'root'},parents=[])
        def add():
            try:return admit(self.path,{'b':b'child'},parents=[a])
            except ValueError as e:
                self.assertEqual(str(e),'dependency_inactive_or_missing');return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            child=pool.submit(add);rev=pool.submit(revoke,self.path,a,'TEST',b'proof')
            batch=child.result();rev.result()
        self.assertEqual(audit_store(self.path)['active_batches'],[])
        if batch:
            with self.assertRaises(ValueError):read_batch(self.path,batch)

    def test_read_snapshot_never_observes_half_revocation(self):
        a,b,c,d,u=self.graph();db=connect(self.path);self.addCleanup(db.close)
        db.execute('BEGIN');old=db.execute('SELECT count(*) FROM journal').fetchone()[0]
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(revoke,self.path,a,'TEST',b'proof')
            self.assertEqual(db.execute('SELECT count(*) FROM journal').fetchone()[0],old)
            db.execute('COMMIT');future.result()
        with self.assertRaises(ValueError):read_batch(self.path,d)


if __name__=='__main__':unittest.main()
