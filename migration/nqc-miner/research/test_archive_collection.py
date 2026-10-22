"""Actual Rust + Polars tests using artificial historical-admission fixtures.

The fixture class is historical only to exercise the collector contract; these
invented blocks and empty logs are not evidence about any real market.
"""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import uuid

import archive_collection as archive
from export_parquet import ExportError


def encode(value):
    return json.dumps(value,separators=(",", ":"),ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def block(n):
    return f"0x{n:064x}"


def owner(config):
    return {"schema":"nqc-miner-owner-v2","namespace":"nqc_miner_v1","producer":"nqc-miner",
        "run_id":config["run_id"],"data_class":"historical","config_sha256":digest(encode(config)),
        "code_commit":config["code_commit"],"cargo_lock_sha256":config["cargo_lock_sha256"],
        "build_identity_sha256":config["build_identity_sha256"]}


def journal(path, config, records):
    path.mkdir(exist_ok=True)
    identity=owner(config)
    (path/'owner.json').write_bytes(encode(identity))
    (path/'config.json').write_bytes(encode(config))
    (path/'writer.lock').write_bytes(b'nqc-miner-kernel-lock-v1\n')
    previous='0'*64; owner_hash=digest(encode(identity)); lines=[]
    for seq,record in enumerate(records):
        current=digest(encode([seq,owner_hash,previous,record]))
        lines.append(encode({'sequence':seq,'owner_sha256':owner_hash,'previous_sha256':previous,
                             'record':record,'sha256':current})+b'\n')
        previous=current
    (path/'events.jsonl').write_bytes(b''.join(lines))


def fixture(path,topic,windows=2):
    config={"schema_version":2,"namespace":"nqc_miner_v1","producer":"nqc-miner",
        "run_id":"archive-fixture","data_class":"historical","code_commit":"1"*40,
        "cargo_lock_sha256":"2"*64,"build_identity_sha256":"3"*64,
        "observer_bridge_enabled":False,"signing_enabled":False,"gas_budget_mxn_centavos":0,
        "scopes":[{"id":"fixture","chain_id":1,"protocol":"aave-v3",
            "contract":"0x"+"01"*20,"event_topics":[topic],"from_block":10,"to_block":10,
            "chunk_blocks":1,"providers":[{"id":"fixture-a","url_env":"NQC_MINER_RPC_A"},
                {"id":"fixture-b","url_env":"NQC_MINER_RPC_B"}],
            "deployment_source":"https://example.invalid/artificial-fixture"}]}
    journal(path,config,[])
    plan_hash=owner(config)['config_sha256']
    (path/'collector.json').write_bytes(archive.packed({'schema':'nqc-miner-collector-v1','plan_sha256':plan_hash}))
    for index in range(windows):
        child=copy.deepcopy(config); n=10+index
        child['run_id']='window-'+digest(f'{plan_hash}:{index}'.encode())
        child['scopes'][0].update(from_block=n,to_block=n)
        records=[{'kind':'chunk_completed','scope_id':'fixture','chain_id':1,'from_block':n,'to_block':n,
            'start_block_hash':block(n+1),'start_parent_hash':block(n),'end_block_hash':block(n+1),
            'observed_at':2000,'providers':['fixture-a','fixture-b'],'event_count':0,'logs_sha256':digest(b'[]')},
            {'kind':'scope_completed','scope_id':'fixture','chain_id':1,'from_block':n,'to_block':n,
             'finalized_anchor_number':n,'finalized_anchor_hash':block(n+1),'observed_at':2000,
             'providers':['fixture-a','fixture-b']}]
        journal(path/f'window-{index:020}',child,records)
    return config


class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary=Path(os.environ['NQC_MINER_TEST_BINARY'])
        cls.topic=json.loads(subprocess.check_output([str(cls.binary),'topics']))['aave-v3'][0]

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='nqc-miner-archive-test-')
        self.root=Path(self.temp.name);self.state=self.root/'collection';self.store=self.root/'archive'
        self.config=fixture(self.state,self.topic)
        archive.init_archive(self.store,str(uuid.uuid4()))

    def tearDown(self):
        self.temp.cleanup()

    def capture(self, **kwargs):
        return archive.archive_collection(self.state,self.store,self.binary,**kwargs)

    def resolve(self):
        return archive.resolve_collection(self.store,self.config['run_id'])

    def revoke(self):
        journal(self.state,self.config,[{'kind':'invalidated','chain_id':1,'from_block':10,
                                        'reason':'artificial archive quarantine regression'}])

    def test_real_verifier_parquet_roundtrip_and_source_untouched(self):
        before={p.relative_to(self.state):p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        result=self.capture();published=self.resolve()
        self.assertFalse(result['idempotent'])
        self.assertEqual(published['snapshot']['verification']['completed_windows'],2)
        self.assertEqual(sum(e['records'] for e in published['snapshot']['exports']),4)
        self.assertEqual(published['snapshot']['verification']['canonical_events_in_completed_windows'],0)
        self.assertFalse(published['live_chain_revalidated'])
        self.assertEqual(before,{p.relative_to(self.state):p.read_bytes() for p in self.state.rglob('*') if p.is_file()})

    def test_replay_is_idempotent_and_does_not_append_receipts(self):
        first=self.capture();second=self.capture()
        self.assertEqual(first['receipt'],second['receipt']);self.assertTrue(second['idempotent'])
        self.assertEqual(len(list((self.store/'commits').iterdir())),1)
        self.assertEqual(list((self.store/'staging').iterdir()),[])

    def test_extension_preserves_previous_snapshot_and_advances_receipt(self):
        first=self.capture()['receipt']
        old_files=archive.file_map(self.store/'objects'/first['snapshot_sha256'])
        fixture(self.state,self.topic,windows=3)
        second=self.capture()['receipt']
        self.assertEqual(second['sequence'],1);self.assertEqual(second['previous_sha256'],first['sha256'])
        self.assertEqual(self.resolve()['snapshot']['verification']['completed_windows'],3)
        self.assertEqual(archive.file_map(self.store/'objects'/first['snapshot_sha256']),old_files)

    def test_source_rollback_cannot_replace_published_head(self):
        first=self.capture()['receipt']
        shutil.rmtree(self.state/'window-00000000000000000001')
        with self.assertRaisesRegex(ExportError,'regressed'):self.capture()
        self.assertEqual(self.resolve()['receipt'],first)

    def test_changed_but_valid_prior_window_is_rejected(self):
        self.capture()
        path=self.state/'window-00000000000000000000'
        config=json.loads((path/'config.json').read_bytes())
        records=[json.loads(line)['record'] for line in (path/'events.jsonl').read_bytes().splitlines()]
        records[0]['observed_at']=2001
        journal(path,config,records)
        with self.assertRaisesRegex(ExportError,'changed'):self.capture()
        self.assertEqual(len(list((self.store/'commits').iterdir())),1)

    def test_late_quarantine_revokes_prior_data_and_cannot_be_cleared(self):
        first=self.capture()['receipt'];self.revoke()
        revoked=self.capture()['receipt'];self.assertEqual(revoked['status'],'quarantined')
        self.assertTrue((self.store/'objects'/first['snapshot_sha256']).is_dir())
        with self.assertRaisesRegex(ExportError,'quarantined'):self.resolve()
        self.assertTrue(self.capture()['idempotent'])
        fixture(self.state,self.topic)
        with self.assertRaisesRegex(ExportError,'permanent'):self.capture()

    def test_valid_quarantine_propagates_even_with_missing_child_window(self):
        fixture(self.state,self.topic,windows=3);self.capture();self.revoke()
        shutil.rmtree(self.state/'window-00000000000000000001')
        self.assertEqual(self.capture()['receipt']['status'],'quarantined')
        with self.assertRaisesRegex(ExportError,'quarantined'):self.resolve()

    def test_incomplete_or_empty_collection_has_no_publication(self):
        path=self.state/'window-00000000000000000001'
        lines=(path/'events.jsonl').read_bytes().splitlines(keepends=True)
        (path/'events.jsonl').write_bytes(lines[0])
        with self.assertRaisesRegex(ExportError,'incomplete'):self.capture()
        shutil.rmtree(self.state);fixture(self.state,self.topic,windows=0)
        with self.assertRaisesRegex(ExportError,'empty'):self.capture()
        self.assertEqual(list((self.store/'commits').iterdir()),[])

    def test_torn_journal_is_preserved_and_never_published(self):
        path=self.state/'window-00000000000000000000/events.jsonl'
        raw=path.read_bytes()[:-1];path.write_bytes(raw)
        with self.assertRaises(ExportError):self.capture()
        self.assertEqual(path.read_bytes(),raw)
        self.assertEqual(list((self.store/'commits').iterdir()),[])

    def test_bounded_input_and_record_count_rejected(self):
        for kwargs in ({'maximum_bytes':True},{'maximum_bytes':1},{'maximum_records':3}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ExportError):self.capture(**kwargs)
        self.assertEqual(list((self.store/'commits').iterdir()),[])

    def test_corrupt_sealed_object_fails_resolution_and_future_import(self):
        receipt=self.capture()['receipt']
        obj=self.store/'objects'/receipt['snapshot_sha256']
        path=obj/'source/window-00000000000000000000/events.jsonl'
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ExportError,'changed'):self.resolve()
        with self.assertRaises(ExportError):self.capture()

    def test_receipt_gap_and_hash_tampering_rejected(self):
        self.capture();fixture(self.state,self.topic,windows=3);self.capture()
        first=self.store/'commits/00000000000000000000.json';raw=first.read_bytes()
        first.unlink()
        with self.assertRaisesRegex(ExportError,'gap'):self.resolve()
        first.write_bytes(raw.replace(b'"sequence":0',b'"sequence":2'))
        with self.assertRaisesRegex(ExportError,'integrity'):self.resolve()

    def test_unowned_archive_symlinks_and_overlap_rejected(self):
        foreign=self.root/'foreign';foreign.mkdir();(foreign/'observer.txt').write_text('untouched')
        with self.assertRaises((ExportError,OSError)):archive.archive_collection(self.state,foreign,self.binary)
        self.assertEqual((foreign/'observer.txt').read_text(),'untouched')
        link=self.root/'alias';link.symlink_to(self.store,target_is_directory=True)
        with self.assertRaises(ExportError):archive.archive_collection(self.state,link,self.binary)
        with self.assertRaises(ExportError):archive.archive_collection(self.store,self.store,self.binary)
        with self.assertRaises(FileExistsError):archive.init_archive(self.store,str(uuid.uuid4()))

    def test_exclusive_writer_and_source_locks_prevent_concurrent_mutation(self):
        with archive.archive_lock(self.store):
            with self.assertRaisesRegex(ExportError,'busy'):self.capture()
        for directory in (self.state,self.state/'window-00000000000000000000'):
            with (directory/'writer.lock').open('rb') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaisesRegex(ExportError,'active'):self.capture()
        with archive.shared_source_lock(self.state):
            result=subprocess.run([str(self.binary),'verify-journal','--state',str(self.state)],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b'locked',result.stderr)

    def test_source_change_during_snapshot_rejected(self):
        original=archive.export_journal
        def changing(*args,**kwargs):
            result=original(*args,**kwargs)
            self.revoke()  # Simulated noncooperating local mutation despite kernel locks.
            return result
        with mock.patch.object(archive,'export_journal',side_effect=changing):
            with self.assertRaisesRegex(ExportError,'changed'):self.capture()
        self.assertEqual(list((self.store/'commits').iterdir()),[])

    def test_orphan_object_after_publication_failure_is_invisible_then_recovered(self):
        with mock.patch.object(archive,'publish_receipt',side_effect=OSError('injected disk failure')):
            with self.assertRaises(OSError):self.capture()
        self.assertEqual(len(list((self.store/'objects').iterdir())),1)
        with self.assertRaisesRegex(ExportError,'no published'):self.resolve()
        self.capture()
        self.assertEqual(len(list((self.store/'objects').iterdir())),1)
        self.assertEqual(self.resolve()['receipt']['sequence'],0)

    def test_sigkill_before_receipt_leaves_no_visible_snapshot_and_retry_recovers(self):
        ready=self.root/'ready'
        script="""import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import archive_collection as a
def stop(*args):
 Path(sys.argv[5]).write_text('ready')
 while True: time.sleep(1)
a.publish_receipt=stop
a.archive_collection(Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]))
"""
        child=subprocess.Popen([sys.executable,'-c',script,str(Path(__file__).parent),str(self.state),str(self.store),str(self.binary),str(ready)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+15
            while not ready.exists() and time.monotonic()<deadline and child.poll() is None:time.sleep(.025)
            self.assertTrue(ready.exists())
        finally:
            if child.poll() is None:child.kill()
            child.communicate(timeout=10)
        with self.assertRaisesRegex(ExportError,'no published'):self.resolve()
        self.capture();self.assertEqual(self.resolve()['receipt']['sequence'],0)

    def test_foreign_source_owner_or_lock_never_adopted(self):
        path=self.state/'owner.json';saved=path.read_bytes()
        path.write_bytes(saved.replace(b'nqc_miner_v1',b'observer'))
        with self.assertRaises(ExportError):self.capture()
        path.write_bytes(saved)
        (self.state/'writer.lock').write_text('legacy-pid\n')
        with self.assertRaisesRegex(ExportError,'persistent'):self.capture()
        self.assertEqual(list((self.store/'commits').iterdir()),[])

    def test_numeric_false_is_not_an_archive_permission_flag(self):
        path=self.store/'owner.json';value=json.loads(path.read_bytes())
        value['remote_upload_enabled']=0;path.write_bytes(archive.packed(value))
        with self.assertRaisesRegex(ExportError,'foreign'):self.capture()

    def test_reader_rejects_reactivation_even_with_a_valid_receipt_hash_chain(self):
        original=self.capture()['receipt'];self.revoke();revoked=self.capture()['receipt']
        forged={k:v for k,v in original.items() if k!='sha256'}
        forged.update(sequence=2,previous_sha256=revoked['sha256'])
        forged['sha256']=digest(archive.packed(forged))
        (self.store/'commits/00000000000000000002.json').write_bytes(archive.packed(forged)+b'\n')
        with self.assertRaisesRegex(ExportError,'permanent'):self.resolve()

    def test_dangling_link_cannot_be_replaced_by_a_sealed_object(self):
        with mock.patch.object(archive,'publish_receipt',side_effect=OSError('injected failure')):
            with self.assertRaises(OSError):self.capture()
        target=next((self.store/'objects').iterdir())
        shutil.rmtree(target);target.symlink_to(self.root/'missing',target_is_directory=True)
        with self.assertRaises(ExportError):self.capture()
        self.assertTrue(target.is_symlink())
        self.assertEqual(list((self.store/'commits').iterdir()),[])

    def test_receipts_from_another_archive_cannot_be_adopted(self):
        receipt=self.capture()['receipt']
        other=self.root/'second-archive';other_id=str(uuid.uuid4())
        archive.init_archive(other,other_id)
        self.assertNotEqual(receipt['archive_id'],other_id)
        for name in ('objects','commits'):
            shutil.copytree(self.store/name,other/name,dirs_exist_ok=True)
        with self.assertRaisesRegex(ExportError,'integrity'):
            archive.resolve_collection(other,self.config['run_id'])
