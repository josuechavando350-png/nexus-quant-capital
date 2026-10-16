"""Offline integration: prepend, join, catch-up and global pacing boundaries."""
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from history_acquisition import HERE,Reader,run,safe_stop,source,canonical,registry,Journal
from audit_history import audit
from test_paced import Clock
from test_acquisition import Chain,Synthetic
from test_experiment import segment,event,A,B,rewrite_journal

POLICY=json.loads((HERE/'policy.json').read_text())
C='0x'+'3'*40

def fixture():
    chain=Chain();chain.events=[event(999985,C),event(1000020,B)]
    state=segment(1000000,1000005,[event(1000000,A)],chain.timestamp)
    raw=canonical({'state':state,'sha256':registry.digest(state)})
    p=dict(POLICY,backfill_from_block=999980,backfill_through_block=999999,backfill_blocks=20,
           shard_blocks=10,source_file_sha256=hashlib.sha256(raw).hexdigest(),source_root=registry.digest(state))
    return chain,p,raw

def execute(path,chain,p,raw,fail=None,kind='http',mutate=None):
    clock=Clock();transport=Synthetic(chain,fail,kind,mutate)
    with patch('time.monotonic_ns',clock.monotonic_ns),patch('time.time_ns',clock.wall_ns),patch('time.sleep',clock.sleep),patch('builtins.print'):
        reader=Reader(path,p,transport,factory=lambda:(_ for _ in ()).throw(AssertionError('NO_ROTATION')))
        journal=Journal(path);(path/'source-registry.json').write_bytes(raw)
        try:run(reader,journal,p,'1'*40,raw)
        except Exception as error:safe_stop(reader,journal,error)
    return reader

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.guard=patch('requests.adapters.HTTPAdapter.send',side_effect=AssertionError('OFFLINE_ONLY'));self.guard.start()
    def tearDown(self):self.guard.stop()
    def test_complete_preserves_accounts_and_segments_and_one_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();path=Path(tmp)/'p';reader=execute(path,chain,p,raw);result=audit(path,p)
            self.assertEqual(result['status'],'completed');self.assertEqual(len(result['observations']),3)
            self.assertEqual(result['cohort']['addresses'],sorted([A,B,C]))
            self.assertEqual(result['registry']['added_history_blocks'],20)
            self.assertEqual(result['registry']['added_tail_blocks'],31)
            self.assertEqual(result['minimum_start_gap_ms'],350)
            self.assertTrue(all(r['connection_epoch']==0 for r in reader.records))
            self.assertEqual({r['label'].split('-')[0] for r in reader.records},{'verify','history','catchup','authenticate','observe'})
            self.assertTrue(all(not r['within_assumed_1000ms'] for r in result['observations']))
    def test_all_http_failures_audit_exact_partial_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();base=execute(Path(tmp)/'base',chain,p,raw)
            for n in range(1,base.count+1):
                with self.subTest(n=n):
                    chain,p,raw=fixture();path=Path(tmp)/str(n);reader=execute(path,chain,p,raw,fail=n)
                    self.assertEqual(audit(path,p)['status'],'stopped');self.assertEqual(reader.count,n)
            print('Synthetic failure boundaries audited:',base.count)
    def test_stop_after_join_before_catchup_preserves_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();base=execute(Path(tmp)/'base',chain,p,raw)
            n=next(r['payload']['id'] for r in base.records if r['label']=='catchup-index-head')
            for kind in ('http','rpc','json'):
                chain,p,raw=fixture();path=Path(tmp)/kind;execute(path,chain,p,raw,fail=n,kind=kind);result=audit(path,p)
                self.assertTrue(result['backfill_merged']);self.assertIsNone(result['cohort'])
                self.assertEqual(result['registry']['added_history_blocks'],20)
                self.assertEqual(result['registry']['added_tail_blocks'],0)
                self.assertEqual((path/'registry.json').read_bytes(),(path/'merged-before-catchup.json').read_bytes())
    def test_single_request_budget_at_each_phase_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();base=execute(Path(tmp)/'base',chain,p,raw)
            labels=['history-registry-start','verify-source-after-history','catchup-index-head','authenticate-authenticate-0','observe-r0-head']
            for label in labels:
                n=next(r['payload']['id'] for r in base.records if r['label']==label)-1
                chain,p,raw=fixture();p['max_requests']=n;path=Path(tmp)/str(n);reader=execute(path,chain,p,raw)
                self.assertEqual(reader.count,n);self.assertEqual(audit(path,p)['status'],'stopped')
    def test_time_budget_not_reset_across_history_join_and_tail(self):
        for seconds in (1,4,5,9,12):
            with tempfile.TemporaryDirectory() as tmp:
                chain,p,raw=fixture();p['max_run_seconds']=seconds;path=Path(tmp)/'p';reader=execute(path,chain,p,raw)
                result=audit(path,p);self.assertEqual(result['status'],'stopped')
                self.assertLessEqual(result['elapsed_seconds'],seconds)
                self.assertEqual(reader.admissions[-1]['reason'],'PACING_TIME_BUDGET')
    def test_reorg_at_source_boundary_join_and_tail(self):
        labels=['verify-backfill-boundary','history-anchor-after-index','verify-source-after-history','catchup-resume-checkpoint','observe-r0-canonical']
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();base=execute(Path(tmp)/'base',chain,p,raw)
            for label in labels:
                n=next(r['payload']['id'] for r in base.records if r['label']==label)
                def mutate(q,response):
                    value=json.loads(response)
                    if q['id']==n:value['result']['hash']='0x'+'e'*64
                    return canonical(value)
                chain,p,raw=fixture();path=Path(tmp)/label;execute(path,chain,p,raw,mutate=mutate)
                self.assertEqual(audit(path,p)['status'],'stopped')
    def test_partial_older_and_merged_file_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();path=Path(tmp)/'p';execute(path,chain,p,raw)
            for name in ('older-registry.json','merged-before-catchup.json','registry.json','cohort.json'):
                file=path/name;before=file.read_bytes();file.write_bytes(before+b' ')
                with self.assertRaisesRegex(ValueError,'PERSISTED_FILE_DIFFERS'):audit(path,p)
                file.write_bytes(before)
    def test_rehashed_metric_and_join_tampering_rejected(self):
        for kind in ('backfill_merged','observation_completed'):
            with tempfile.TemporaryDirectory() as tmp:
                chain,p,raw=fixture();path=Path(tmp)/'p';execute(path,chain,p,raw)
                def mutate(rows):
                    row=next(r for r in rows if r['kind']==kind)
                    row['data']['merged_registry_sha256' if kind=='backfill_merged' else 'admission_to_verified_ms']='wrong'
                rewrite_journal(path,mutate)
                with self.assertRaises(ValueError):audit(path,p)
    def test_source_window_and_hash_fail_before_rpc(self):
        chain,p,raw=fixture()
        for changed in (dict(p,backfill_from_block=999981),dict(p,backfill_through_block=1000000),dict(p,rounds=12)):
            with self.assertRaisesRegex(ValueError,'FIXED_HISTORY_WINDOW'):source(changed,raw)
        with self.assertRaisesRegex(ValueError,'SOURCE_FILE_HASH'):source(p,raw+b' ')
    def test_denial_latches_reader_and_no_rotation_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();reader=execute(Path(tmp)/'p',chain,p,raw,fail=2)
            with self.assertRaises(ValueError):reader.call('eth_chainId',[],'retry')
            self.assertEqual(reader.count,2)
            with self.assertRaisesRegex(ValueError,'NO_ROTATION'):reader.rotate_for_measurement()

if __name__=='__main__':unittest.main()
