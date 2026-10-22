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


if __name__=='__main__':unittest.main()
