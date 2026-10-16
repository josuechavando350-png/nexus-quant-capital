"""No-network gate tests and exact control-flow replay with an injected clock."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from paced_acquisition import HERE, Reader, run, canonical, Journal, safe_stop
from pacing import Pacer, INTERVAL_NS
from audit_paced import audit

PR16=HERE.parent/'robinhood-acquisition-20261016T0922'
sys.path.insert(0,str(PR16))
import test_acquisition as previous

POLICY=json.loads((HERE/'policy.json').read_text())


class Clock:
    def __init__(self):
        self.now=10**15
        self.origin=self.now
        self.wall_origin=time.time_ns()
        self.sleeps=[]
    def monotonic_ns(self):return self.now
    def wall_ns(self):return self.wall_origin+self.now-self.origin
    def sleep(self,seconds):
        self.sleeps.append(seconds)
        self.now+=round(seconds*1e9)


original_execute=previous.execute


def execute(*args,**kwargs):
    clock=Clock()
    with patch('time.monotonic_ns',clock.monotonic_ns), patch('time.time_ns',clock.wall_ns), patch('time.sleep',clock.sleep):
        reader,instances=original_execute(*args,**kwargs)
    reader.test_clock=clock
    return reader,instances


class FullFlowRegression(previous.AcquisitionTests):
    """Run all twelve PR16 behavioral tests against the NEW reader and auditor."""
    def setUp(self):
        self.stack=[]
        for name,value in dict(Reader=Reader,run=run,audit=audit,POLICY=POLICY,execute=execute).items():
            item=patch.object(previous,name,value);item.start();self.stack.append(item)
        guard=patch('requests.adapters.HTTPAdapter.send',side_effect=AssertionError('OFFLINE_ONLY'))
        guard.start();self.stack.append(guard)
    def tearDown(self):
        for item in reversed(self.stack):item.stop()


class PacingTests(unittest.TestCase):
    def setUp(self):
        self.guard=patch('requests.adapters.HTTPAdapter.send',side_effect=AssertionError('OFFLINE_ONLY'))
        self.guard.start()
        self.policy_patch=patch.object(previous,'POLICY',POLICY);self.policy_patch.start()
        self.reader_patch=patch.object(previous,'Reader',Reader);self.reader_patch.start()
        self.run_patch=patch.object(previous,'run',run);self.run_patch.start()
    def tearDown(self):
        self.run_patch.stop();self.reader_patch.stop();self.policy_patch.stop();self.guard.stop()

    def test_minimum_spacing_and_no_idle_credit(self):
        clock=Clock();gate=Pacer(clock.monotonic_ns,clock.sleep);deadline=clock.now+10**12
        for gap in (0,0,10_000_000_000,0,0):
            clock.now+=gap;event={};gate.admit(deadline,event)
            if gate.last_start_ns is not None:self.assertGreaterEqual(clock.now-gate.last_start_ns,INTERVAL_NS)
            gate.record_start(clock.now)
        self.assertEqual(clock.sleeps,[.35,.35,.35])

    def test_sleep_time_inside_deadline_and_no_rpc_when_due_too_late(self):
        clock=Clock();gate=Pacer(clock.monotonic_ns,clock.sleep);gate.record_start(clock.now)
        event={}
        with self.assertRaisesRegex(ValueError,'PACING_TIME_BUDGET'):gate.admit(clock.now+INTERVAL_NS,event)
        self.assertEqual(clock.sleeps,[])
        self.assertEqual(event['due_ns'],event['deadline_ns'])

    def test_early_wake_and_oversleep_fail_closed(self):
        for offset,reason in [(-1,'PACING_EARLY_WAKE'),(2*10**9,'TIME_BUDGET')]:
            clock=Clock()
            def sleep(seconds):clock.now+=round(seconds*1e9)+offset
            gate=Pacer(clock.monotonic_ns,sleep);gate.record_start(clock.now)
            with self.assertRaisesRegex(ValueError,reason):gate.admit(clock.now+10**9,{})

    def test_dispatch_preparation_delay_cannot_shorten_next_gap(self):
        clock=Clock();gate=Pacer(clock.monotonic_ns,clock.sleep);deadline=clock.now+10**12
        gate.admit(deadline,{})
        clock.now+=70_000_000;gate.record_start(clock.now)
        prior=clock.now;gate.admit(deadline,{})
        self.assertEqual(clock.now-prior,INTERVAL_NS)

    def test_full_flow_spacing_includes_rotation_and_primary_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=previous.fixture();path=Path(tmp)/'p'
            reader,instances=execute(path,chain,p,raw);result=audit(path,p)
            self.assertEqual(result['rpc_calls'],59)
            self.assertEqual(result['minimum_start_gap_ms'],350)
            epochs=[r['connection_epoch'] for r in reader.records]
            boundary=epochs.index(1)
            self.assertEqual(reader.records[boundary]['started_ns']-reader.records[boundary-1]['started_ns'],INTERVAL_NS)
            self.assertEqual(result['acquisition_admission_intervals_ms'],[1050]*11)
            for row in result['observations']:
                self.assertEqual(row['header_admission_wait_ms'],350)
                self.assertEqual(row['request_to_verified_ms'],700)
                self.assertEqual(row['admission_to_verified_ms'],1050)
                self.assertFalse(row['within_assumed_1000ms'])
            self.assertEqual(len(instances),2)

    def test_failure_latch_prevents_sleep_rpc_and_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=previous.fixture();reader,instances=execute(Path(tmp)/'p',chain,p,raw,fail=2)
            before=(reader.count,len(reader.admissions),len(reader.test_clock.sleeps),len(instances))
            with self.assertRaisesRegex(ValueError,'REQUEST_BUDGET_OR_STOPPED'):reader.call('eth_chainId',[],'forbidden')
            with self.assertRaisesRegex(ValueError,'ONE_HEALTHY'):reader.rotate_for_measurement()
            self.assertEqual(before,(reader.count,len(reader.admissions),len(reader.test_clock.sleeps),len(instances)))
            self.assertEqual(audit(Path(tmp)/'p',p)['status'],'stopped')

    def test_pacing_deadline_retains_baseline_and_audits_pre_rpc_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=previous.fixture();p['max_run_seconds']=1;path=Path(tmp)/'p'
            reader,_=execute(path,chain,p,raw)
            result=audit(path,p)
            self.assertEqual(reader.count,3)
            self.assertEqual(result['admission_attempts'],4)
            self.assertEqual(result['registry']['added_blocks'],0)
            self.assertIsNone(result['cohort'])
            self.assertEqual(reader.admissions[-1]['reason'],'PACING_TIME_BUDGET')

    def test_deadline_after_rotation_preserves_index_and_partial_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=previous.fixture();p['max_run_seconds']=9;path=Path(tmp)/'p'
            reader,_=execute(path,chain,p,raw);result=audit(path,p)
            self.assertEqual(reader.epoch,1)
            self.assertEqual(result['registry']['added_blocks'],31)
            self.assertIsNotNone(result['cohort'])
            self.assertGreaterEqual(len(result['observations']),1)
            self.assertLess(len(result['observations']),12)
            self.assertEqual(result['status'],'stopped')

    def test_admission_clock_and_metric_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=previous.fixture();path=Path(tmp)/'p';execute(path,chain,p,raw)
            file=path/'admissions.json';original=file.read_bytes();data=json.loads(original)
            data[2]['due_ns']-=1;file.write_bytes(canonical(data))
            with self.assertRaisesRegex(ValueError,'ADMISSION_DUE'):audit(path,p)
            file.write_bytes(original)
            def mutate(rows):next(r for r in rows if r['kind']=='observation_completed')['data']['admission_to_verified_ms']=700
            previous.rewrite_journal(path,mutate)
            with self.assertRaisesRegex(ValueError,'JOURNAL_REPLAY_DIFFERS'):audit(path,p)

    def test_invalid_pacing_policy_rejected_without_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=previous.fixture();p['minimum_start_interval_ns']=0
            with self.assertRaisesRegex(ValueError,'PACING_POLICY'):Reader(Path(tmp)/'p',p)


if __name__=='__main__':unittest.main()
