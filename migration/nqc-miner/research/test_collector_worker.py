"""Actual verifier/Parquet/storage; explicit fakes only for RPC poll and psql."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import archive_collection as archive
import collector_worker as worker
import test_archive_collection as fixtures
from test_collection_transport import LocalClient, response
import collection_transport as transport

class CollectorWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary=Path(os.environ['NQC_MINER_TEST_BINARY'])
        cls.about=json.loads(subprocess.check_output([str(cls.binary),'about']))
        cls.topic=json.loads(subprocess.check_output([str(cls.binary),'topics']))['aave-v3'][0]
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='miner-worker-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.state=self.root/'state';self.store=self.root/'archive';self.workspace=self.root/'worker'
        self.client=LocalClient(self.root);self.addCleanup(self.client.socket_patch.stop)
        self.make_fixture(1);archive.init_archive(self.store,self.client.target['archive_id'])
        self.calls=[];self.poll_status=0;self.revoke_on_poll=False;self.unknown_at=None;self.submissions=0;self.windows=1
        real_command=worker.command;submit=transport.apply_bundle
        def command(args,**kwargs):
            if args[1]!='follow':return real_command(args,**kwargs)
            self.calls.append('poll')
            if self.revoke_on_poll:self.revoke()
            else:self.windows+=1;self.make_fixture(self.windows)
            result={'exit_code':self.poll_status,'limited':False};archive.new_json(kwargs['output'],result)
            return result,b''
        def deliver(bundle,target,output):
            self.calls.append('sync');self.submissions+=1
            request,manifest,_=transport.load_bundle(bundle,target);revoked=manifest['status']=='quarantined'
            messages=response(request,manifest,status='quarantined' if revoked else 'imported',quarantined=revoked)
            if self.submissions==self.unknown_at:messages=messages[:1]
            self.client.configure(b'\n'.join(transport.packed(v) for v in messages)+b'\n')
            return submit(bundle,target,output)
        for patch in [mock.patch.object(worker,'command',side_effect=command),mock.patch.object(transport,'apply_bundle',side_effect=deliver)]:
            patch.start();self.addCleanup(patch.stop)
    def make_fixture(self,windows):
        config=fixtures.fixture(self.state,self.topic,windows=windows,run_id='worker-fixture')
        fields=['code_commit','cargo_lock_sha256','build_identity_sha256'];config.update({k:self.about[k] for k in fields})
        fixtures.journal(self.state,config,[]);plan_hash=fixtures.owner(config)['config_sha256']
        (self.state/'collector.json').write_bytes(archive.packed({'schema':'nqc-miner-collector-v1','plan_sha256':plan_hash}))
        for index in range(windows):
            path=self.state/f'window-{index:020}';child=json.loads((path/'config.json').read_bytes())
            child.update({k:config[k] for k in fields});child['run_id']='window-'+fixtures.digest(f'{plan_hash}:{index}'.encode())
            records=[json.loads(line)['record'] for line in (path/'events.jsonl').read_bytes().splitlines()]
            fixtures.journal(path,child,records)
        self.config=config
    def revoke(self):
        fixtures.journal(self.state,self.config,[{'kind':'invalidated','chain_id':1,'from_block':10,'reason':'artificial worker test'}])
    def run_worker(self,cycles=1):
        return worker.run(self.state,self.store,self.binary,self.workspace,self.client.target,cycles=cycles)
    def test_two_cycles_reconcile_before_poll_then_store_current_source(self):
        r=self.run_worker(2);self.assertEqual(r['outcome'],'applied');self.assertEqual(r['cycles_applied'],2)
        self.assertEqual(self.calls,['sync','poll','sync','poll','sync'])
        self.assertEqual(archive.resolve_collection(self.store,self.config['run_id'])['snapshot']['verification']['completed_windows'],3)
        self.assertEqual(len(list((self.store/'commits').glob('*.json'))),3)
    def test_restart_reconciles_again_in_new_session(self):
        first=self.run_worker();before=(Path(first['session'])/'result.json').read_bytes();self.calls=[];second=self.run_worker()
        self.assertEqual(self.calls,['sync','poll','sync']);self.assertNotEqual(first['session'],second['session'])
        self.assertEqual(before,(Path(first['session'])/'result.json').read_bytes())
        self.assertEqual(len(list((self.store/'commits').glob('*.json'))),3)
    def test_unknown_recovery_stops_poll_then_retry_reverifies(self):
        self.unknown_at=1;first=self.run_worker(2)
        self.assertEqual(first['outcome'],'unknown');self.assertEqual(self.calls,['sync']);self.assertEqual(first['polls_started'],0)
        self.assertEqual(self.run_worker()['outcome'],'applied')
    def test_unknown_after_poll_stops_remaining_cycles(self):
        self.unknown_at=2;r=self.run_worker(3)
        self.assertEqual(r['outcome'],'unknown');self.assertEqual(r['polls_started'],1)
        self.assertEqual(r['cycles_applied'],0);self.assertFalse(r['last_sync_commit_confirmed'])
    def test_revoked_parent_delivered_before_any_new_poll(self):
        self.revoke();r=self.run_worker(3)
        self.assertEqual(r['outcome'],'quarantined');self.assertEqual(self.calls,['sync']);self.assertTrue(r['last_sync_commit_confirmed'])
    def test_failed_poll_propagates_revocation(self):
        self.revoke_on_poll=True;self.poll_status=1;r=self.run_worker(3)
        self.assertEqual(r['outcome'],'quarantined');self.assertEqual(self.calls,['sync','poll','sync'])
        self.assertEqual(r['polls_started'],1)
    def test_failed_poll_with_valid_archive_stays_unknown(self):
        self.poll_status=1;r=self.run_worker(3)
        self.assertEqual(r['outcome'],'unknown');self.assertTrue(r['last_sync_commit_confirmed']);self.assertEqual(r['polls_started'],1)
    def test_other_worker_lock_blocks_before_source_changes(self):
        self.run_worker();self.calls=[]
        with (self.workspace/'worker.lock').open('rb') as stream:
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(transport.DeliveryError,'already running'):self.run_worker()
        self.assertEqual(self.calls,[])
    def test_missing_result_is_not_adopted_as_success(self):
        first=self.run_worker();path=Path(first['session'])/'result.json';path.unlink();self.calls=[]
        self.assertEqual(self.run_worker()['outcome'],'applied');self.assertFalse(path.exists());self.assertEqual(self.calls[0],'sync')
    def test_foreign_workspace_target_and_numeric_flags_refused(self):
        self.run_worker();owner=self.workspace/'owner.json';original=owner.read_bytes()
        for change in [{'namespace':'observer'},{'observer_bridge_enabled':0},{'target_sha256':'0'*64}]:
            value=json.loads(original);value.update(change);owner.write_text(json.dumps(value))
            with self.assertRaises(transport.DeliveryError):self.run_worker()
        owner.write_bytes(original)
    def test_foreign_build_and_nested_workspace_refused(self):
        config=self.state/'config.json';value=json.loads(config.read_bytes());value['code_commit']='a'*40;config.write_text(json.dumps(value))
        with self.assertRaises(transport.DeliveryError):self.run_worker()
        self.make_fixture(1);self.workspace=self.state/'worker'
        with self.assertRaises(transport.DeliveryError):self.run_worker()
    def test_bounded_cycles_and_active_source_writer(self):
        for n in [0,17,True]:
            with self.assertRaises(transport.DeliveryError):self.run_worker(n)
        with (self.state/'writer.lock').open('rb') as stream:
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            r=self.run_worker();self.assertEqual(r['outcome'],'unknown');self.assertEqual(self.calls,[])

    def test_capacity_stops_before_unimportable_window(self):
        with mock.patch.object(worker.sync,'sync_collection',return_value={'outcome':'applied','commit_confirmed':True,'windows':64}):
            r=self.run_worker(2)
        self.assertEqual(r['outcome'],'capacity_reached');self.assertEqual(r['polls_started'],0)
        self.assertEqual(self.calls,[])
    def test_sigkill_releases_worker_lock_and_preserves_incomplete_session(self):
        self.run_worker();identity=json.loads((self.workspace/'owner.json').read_bytes())
        code="""import json,sys,time
from pathlib import Path
import collector_worker as w
root=Path(sys.argv[1]);identity=json.loads((root/'owner.json').read_bytes())
with w.workspace_lock(root,identity):
 p=root/'sessions'/'interrupted';p.mkdir(mode=0o700)
 w.archive.new_json(p/'attempt.json',{'outcome':'unknown'})
 w.archive.sync_dir(p);w.archive.sync_dir(p.parent)
 print('ready',flush=True)
 time.sleep(30)
"""
        env={**os.environ,'PYTHONPATH':str(Path(worker.__file__).parent)}
        child=subprocess.Popen([sys.executable,'-c',code,str(self.workspace)],env=env,stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'ready');child.kill();child.wait(timeout=5)
        finally:
            if child.poll() is None:child.kill();child.wait()
            child.stdout.close()
        before=(self.workspace/'sessions/interrupted/attempt.json').read_bytes();self.calls=[]
        self.assertEqual(self.run_worker()['outcome'],'applied');self.assertEqual(self.calls[0],'sync')
        self.assertEqual(before,(self.workspace/'sessions/interrupted/attempt.json').read_bytes())
        self.assertFalse((self.workspace/'sessions/interrupted/result.json').exists())

class WorkerProcessTests(unittest.TestCase):
    def test_real_process_timeout_and_output_limits(self):
        with self.assertRaises(transport.DeliveryError):worker.command([sys.executable,'-c','import time;time.sleep(30)'],timeout=0.1)
        with self.assertRaises(transport.DeliveryError):worker.command([sys.executable,'-c','import sys;sys.stdout.write("x"*2000000)'],timeout=5)
    def test_stderr_is_only_retained_as_hash(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'result.json'
            r,out=worker.command([sys.executable,'-c','import sys;sys.stderr.write("private-token");print("ok")'],timeout=5,output=path)
            self.assertEqual(out,b'ok\n');self.assertEqual(r['exit_code'],0);self.assertNotIn('private-token',path.read_text())

if __name__=='__main__':unittest.main()
