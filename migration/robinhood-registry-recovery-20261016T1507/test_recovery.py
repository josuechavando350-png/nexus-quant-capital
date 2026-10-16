"""Offline synthetic tests; never evidence of market opportunity or latency."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from recovery import HERE, ROOT, Reader, Journal, registry, run, safe_stop, sources, canonical
from audit_recovery import audit
from test_paced import Clock
from test_acquisition import Chain, Synthetic
from test_experiment import segment, event, A, B, raw_header, header, rewrite_journal
from merge import merge

POLICY = json.loads((HERE/'policy.json').read_text())
C = '0x'+'3'*40


def fixture():
    chain = Chain()
    existing = segment(1000000, 1000005, [event(1000000,A)], chain.timestamp)
    older = segment(999990, 999999, [event(999995,C)], chain.timestamp)
    raws = [canonical({'state':s,'sha256':registry.digest(s)}) for s in (existing,older)]
    p = dict(POLICY, shard_blocks=10)
    for prefix, raw in zip(('source','older_source'),raws):
        p[prefix+'_file_sha256'] = hashlib.sha256(raw).hexdigest()
        p[prefix+'_root'] = json.loads(raw)['sha256']
    return chain,p,*raws


def execute(path, chain, policy, raw, older_raw, fail=None, kind='http', mutate=None):
    clock = Clock()
    transport = Synthetic(chain,fail,kind,mutate)
    with patch('time.monotonic_ns',clock.monotonic_ns), patch('time.time_ns',clock.wall_ns), patch('time.sleep',clock.sleep), patch('builtins.print'):
        reader = Reader(path,policy,transport)
        journal = Journal(path)
        (path/'source-registry.json').write_bytes(raw)
        (path/'older-source-registry.json').write_bytes(older_raw)
        try:
            run(reader,journal,policy,'1'*40,raw,older_raw)
        except Exception as error:
            reader.stopped = True
            safe_stop(reader,journal,error)
    return reader


def constructed(groups):
    """Build raw structure independently of capacity validation, for boundary tests."""
    state = registry.new(1000)
    for i, logs in enumerate(groups):
        first = 1000+i*10000
        parsed = segment(first,first+9999,logs)['segments'][0]
        parsed['previous_segment_sha256'] = registry.digest(state['segments'][-1]) if i else None
        state['segments'].append(parsed)
        state['through_block'],state['checkpoint'] = parsed['end']['number'],parsed['end']
    return state


class CapacityTests(unittest.TestCase):
    def test_cumulative_128_129_256_257(self):
        for count in (128,129,256,257):
            groups = [[event(1000+i*10000+j,A) for j in range(min(128,count-i*128))]
                      for i in range((count+127)//128)]
            value = constructed(groups)
            before = canonical(value)
            if count <= 256:
                self.assertEqual(len(registry.validate(value,POLICY)),count)
            else:
                with self.assertRaisesRegex(ValueError,'REGISTRY_CAPACITY_NO_TRIMMING'):
                    registry.validate(value,POLICY)
            self.assertEqual(canonical(value),before)

    def test_segment_129_still_rejected(self):
        with self.assertRaisesRegex(ValueError,'COHORT_HEADER_LIMIT'):
            registry.append(registry.new(1000),1000,header(raw_header(999)),header(raw_header(1128)),
                            [event(n,A) for n in range(1000,1129)],
                            [header(raw_header(n)) for n in range(1000,1129)],POLICY)

    def test_cumulative_logs_512_513(self):
        for n in (512,513):
            state = constructed([[event(1000,A,i) for i in range(256)],
                                 [event(11000,A,i) for i in range(n-256)]])
            if n == 512:self.assertEqual(len(registry.validate(state,POLICY)),512)
            else:
                with self.assertRaisesRegex(ValueError,'REGISTRY_CAPACITY_NO_TRIMMING'):registry.validate(state,POLICY)

    def test_cumulative_accounts_64_65(self):
        for n in (64,65):
            accounts = ['0x'+f'{i+1:040x}' for i in range(n)]
            state = constructed([[event(1000+i,account) for i,account in enumerate(accounts[:32])],
                                 [event(11000+i,account) for i,account in enumerate(accounts[32:])]])
            if n == 64:self.assertEqual(len(registry.freeze(state,state['through_block'],POLICY)['addresses']),64)
            else:
                with self.assertRaisesRegex(ValueError,'REGISTRY_CAPACITY_NO_TRIMMING'):registry.validate(state,POLICY)

    def test_explicit_capacity_required_and_bounded(self):
        for value in (None,True,128.0,127,257):
            with self.assertRaisesRegex(ValueError,'REGISTRY_CAPACITY_POLICY'):
                registry.validate(registry.new(1),dict(POLICY,max_registry_event_blocks=value))

    def test_real_sources_merge_145_events_54_accounts_without_mutation(self):
        raw = (ROOT/POLICY['source_path']).read_bytes()
        older_raw = (ROOT/POLICY['older_source_path']).read_bytes()
        existing,older = sources(POLICY,raw,older_raw)
        before = canonical([existing,older])
        combined = merge(older,existing,POLICY)
        self.assertEqual(len(registry.validate(combined,POLICY)),145)
        self.assertEqual(len(registry.freeze(combined,combined['through_block'],POLICY)['addresses']),54)
        self.assertEqual(canonical([existing,older]),before)
        self.assertEqual(combined['segments'][:len(older['segments'])],older['segments'])
        strip = lambda s:{k:v for k,v in s.items() if k!='previous_segment_sha256'}
        self.assertEqual([strip(s) for s in combined['segments'][len(older['segments']):]],
                         [strip(s) for s in existing['segments']])

    def test_old_modules_remain_isolated_and_reject_original_overflow(self):
        import backfill
        import collect
        import history_acquisition
        raw=(ROOT/POLICY['source_path']).read_bytes();older_raw=(ROOT/POLICY['older_source_path']).read_bytes()
        existing,older=sources(POLICY,raw,older_raw)
        self.assertIs(backfill.registry,collect.registry)
        self.assertIs(history_acquisition.registry,collect.registry)
        self.assertIsNot(collect.registry,registry)
        with self.assertRaisesRegex(ValueError,'REGISTRY_CAPACITY_NO_TRIMMING'):
            backfill.merge(older,existing,POLICY)

    def test_copied_updater_and_observation_logic_match_registered_sources(self):
        original=(HERE.parent/'robinhood-borrower-registry-20261016/collect.py').read_text()
        self.assertEqual((HERE/'tail.py').read_text().split('def update_registry(',1)[1].rstrip(),
                         original.split('def update_registry(',1)[1].split('\ndef authenticate(',1)[0].rstrip())
        original=(HERE.parent/'robinhood-paced-history-20261016T1222/history_acquisition.py').read_text()
        marker="    reader.phase = 'observe'"
        self.assertEqual((HERE/'observe.py').read_text().split(marker,1)[1].rstrip(),
                         original.split(marker,1)[1].split('\ndef safe_stop(',1)[0].rstrip())


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.guard = patch('requests.adapters.HTTPAdapter.send',side_effect=AssertionError('OFFLINE_ONLY'))
        self.guard.start()
    def tearDown(self):self.guard.stop()

    def test_complete_preserves_all_sources_no_history_scan_one_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw,older_raw = fixture();path = Path(tmp)/'p'
            reader = execute(path,chain,p,raw,older_raw);result = audit(path,p)
            self.assertEqual(result['status'],'completed')
            self.assertEqual(result['cohort']['addresses'],sorted([A,B,C]))
            self.assertEqual(result['registry']['added_history_blocks'],10)
            self.assertEqual(result['registry']['added_tail_blocks'],31)
            self.assertEqual(result['minimum_start_gap_ms'],350)
            self.assertEqual(len(result['observations']),3)
            self.assertTrue(all(r['connection_epoch']==0 for r in reader.records))
            self.assertEqual((path/'older-registry.json').read_bytes(),older_raw)
            for row in reader.records:
                if row['payload']['method']=='eth_getLogs':
                    self.assertGreater(int(row['payload']['params'][0]['fromBlock'],16),1000005)
            self.assertTrue(all(o['state']['positive_debt_accounts']==2 for o in result['observations']))

    def test_all_http_failure_boundaries_and_permanent_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = execute(Path(tmp)/'base',*fixture())
            for n in range(1,base.count+1):
                with self.subTest(n=n):
                    chain,p,raw,older_raw = fixture();path = Path(tmp)/str(n)
                    reader = execute(path,chain,p,raw,older_raw,fail=n)
                    self.assertEqual(audit(path,p)['status'],'stopped')
                    self.assertEqual(reader.count,n)
                    with self.assertRaises(ValueError):reader.call('eth_chainId',[],'retry')
                    self.assertEqual(reader.count,n)
            print('Recovery synthetic RPC failure boundaries:',base.count)

    def test_stop_after_merge_before_catchup_http_rpc_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = execute(Path(tmp)/'base',*fixture())
            n = next(r['payload']['id'] for r in base.records if r['label']=='catchup-index-head')
            for kind in ('http','rpc','json'):
                chain,p,raw,older_raw = fixture();path = Path(tmp)/kind
                execute(path,chain,p,raw,older_raw,fail=n,kind=kind);result = audit(path,p)
                self.assertTrue(result['history_recovered']);self.assertIsNone(result['cohort'])
                self.assertEqual(result['registry']['added_tail_blocks'],0)
                self.assertEqual((path/'registry.json').read_bytes(),(path/'merged-before-catchup.json').read_bytes())

    def test_budget_shared_at_every_phase_and_after_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = execute(Path(tmp)/'base',*fixture())
            labels = ['verify-source-after-merge','catchup-index-head','authenticate-authenticate-0','observe-r0-head']
            for label in labels:
                count = next(r['payload']['id'] for r in base.records if r['label']==label)-1
                chain,p,raw,older_raw = fixture();p['max_requests']=count;path=Path(tmp)/label
                reader=execute(path,chain,p,raw,older_raw)
                self.assertEqual(reader.count,count);self.assertEqual(audit(path,p)['status'],'stopped')

    def test_time_budget_and_waits_not_reset(self):
        for seconds in (1,2,4,7):
            with tempfile.TemporaryDirectory() as tmp:
                chain,p,raw,older_raw = fixture();p['max_run_seconds']=seconds;path=Path(tmp)/'p'
                reader=execute(path,chain,p,raw,older_raw);result=audit(path,p)
                self.assertEqual(result['status'],'stopped')
                self.assertLessEqual(result['elapsed_seconds'],seconds)
                self.assertEqual(reader.admissions[-1]['reason'],'PACING_TIME_BUDGET')

    def test_reorgs_at_sources_join_tail_and_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = execute(Path(tmp)/'base',*fixture())
            labels=['verify-source-checkpoint','verify-older-start','verify-shared-boundary',
                    'verify-source-after-merge','catchup-resume-checkpoint','observe-r0-canonical']
            for label in labels:
                n=next(r['payload']['id'] for r in base.records if r['label']==label)
                def mutate(q,response):
                    value=json.loads(response)
                    if q['id']==n:value['result']['hash']='0x'+'e'*64
                    return canonical(value)
                chain,p,raw,older_raw=fixture();path=Path(tmp)/label
                execute(path,chain,p,raw,older_raw,mutate=mutate)
                self.assertEqual(audit(path,p)['status'],'stopped')

    def test_tampered_sources_and_partial_files_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw,older_raw=fixture();path=Path(tmp)/'p';execute(path,chain,p,raw,older_raw)
            for name in ('older-source-registry.json','older-registry.json','registry.json','merged-before-catchup.json','cohort.json'):
                f=path/name;before=f.read_bytes();f.write_bytes(before+b' ')
                with self.assertRaises(ValueError):audit(path,p)
                f.write_bytes(before)

    def test_rehashed_metrics_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw,older_raw=fixture();path=Path(tmp)/'p';execute(path,chain,p,raw,older_raw)
            def mutate(rows):next(r for r in rows if r['kind']=='observation_completed')['data']['admission_to_verified_ms']=0
            rewrite_journal(path,mutate)
            with self.assertRaisesRegex(ValueError,'JOURNAL_REPLAY_DIFFERS'):audit(path,p)

    def test_both_source_hashes_and_adjacency_required(self):
        chain,p,raw,older_raw=fixture()
        for r,o in ((raw+b' ',older_raw),(raw,older_raw+b' ')):
            with self.assertRaisesRegex(ValueError,'SOURCE_FILE_HASH'):sources(p,r,o)
        with self.assertRaisesRegex(ValueError,'RECOVERY_ROUNDS'):sources(dict(p,rounds=12),raw,older_raw)


if __name__=='__main__':unittest.main()
