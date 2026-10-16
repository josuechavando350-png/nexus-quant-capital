"""Offline faults across indexing, cold rotation and full acquisition."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from acquisition import HERE, PRIOR, Reader, run, safe_stop, source, canonical, registry, Journal
from audit_acquisition import audit
from test_experiment import LensChain, segment, event, A, B, rewrite_journal
from common import encode, words

POLICY=json.loads((HERE/'policy.json').read_text())


class Chain(LensChain):
    def __init__(self):
        super().__init__()
        self.events=[event(1000020,B)]
    def answer(self,q):
        result=super().answer(q)
        if q['method']=='eth_call' and 'to' not in q['params'][0]:
            values=words(result,len(result[2:])//64)
            values[11]=0  # Keep the original account even after its debt becomes zero.
            result=encode('0x',*values)
        return result


class Synthetic:
    def __init__(self,chain,fail=None,kind='http',mutate=None):
        self.chain,self.fail,self.kind,self.mutate=chain,fail,kind,mutate
        self.last,self.prefix,self.local_count,self.closed={},b'',0,False
    def close(self):self.closed=True
    def __call__(self,mode,payload,seconds):
        assert mode=='persistent' and not self.closed
        self.local_count+=1
        self.last={'mode':mode,'status':200,'session_request_number':self.local_count,
                   'client_socket_tag':1,'client_socket_reused':self.local_count>1}
        self.prefix=b''
        if payload['id']==self.fail:
            if self.kind=='http':
                self.last['status']=429;self.prefix=b'quota';raise OSError('synthetic quota')
            if self.kind=='json':self.prefix=b'{';return self.prefix
            self.prefix=canonical({'jsonrpc':'2.0','id':payload['id'],'error':{'code':-32000,'message':'synthetic'}})
            return self.prefix
        self.prefix=self.chain(payload)
        if self.mutate:self.prefix=self.mutate(payload,self.prefix)
        return self.prefix


def fixture():
    chain=Chain()
    state=segment(1000000,1000005,[event(1000000,A)],chain.timestamp)
    raw=canonical({'state':state,'sha256':registry.digest(state)})
    policy=dict(POLICY,shard_blocks=10,source_file_sha256=hashlib.sha256(raw).hexdigest(),source_root=registry.digest(state))
    return chain,policy,raw


def execute(path,chain,policy,raw,fail=None,kind='http',mutate=None,expire=False):
    instances=[]
    def factory():
        transport=Synthetic(chain,fail,kind,mutate);instances.append(transport);return transport
    reader=Reader(path,policy,factory(),factory)
    if expire:reader.started_ns-=901*10**9
    journal=Journal(reader.folder)
    (reader.folder/'source-registry.json').write_bytes(raw)
    with patch('builtins.print'):
        try:run(reader,journal,policy,'1'*40,raw)
        except Exception as error:safe_stop(reader,journal,error)
    return reader,instances


class AcquisitionTests(unittest.TestCase):
    def test_complete_tail_freeze_cold_and_warm(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();path=Path(tmp)/'p'
            reader,instances=execute(path,chain,p,raw)
            result=audit(path,p)
            self.assertEqual(result['status'],'completed')
            self.assertEqual(result['cohort']['addresses'],[A,B])
            self.assertEqual(result['registry']['added_blocks'],31)
            self.assertEqual(result['registry']['added_events'],1)
            self.assertEqual(len(result['observations']),12)
            self.assertEqual(len(instances),2);self.assertTrue(instances[0].closed)
            self.assertFalse(result['observations'][0]['head_transport']['client_socket_reused'])
            for observation in result['observations']:
                self.assertEqual(observation['state']['positive_debt_accounts'],1)
                self.assertGreaterEqual(observation['request_to_verified_ms'],observation['request_to_inputs_ms'])
                self.assertGreaterEqual(observation['request_to_inputs_ms'],observation['header_ms'])
            self.assertTrue(all(o['head_transport']['client_socket_reused'] for o in result['observations'][1:]))
            self.assertEqual(reader.count,len(reader.records))
    def test_all_http_failure_boundaries_preserve_exact_partial_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();reader,_=execute(Path(tmp)/'complete',chain,p,raw)
            count=reader.count
            self.assertEqual(audit(Path(tmp)/'complete',p)['status'],'completed')
            for index in range(1,count+1):
                with self.subTest(fault=index):
                    chain,p,raw=fixture();path=Path(tmp)/str(index)
                    reader,instances=execute(path,chain,p,raw,fail=index)
                    result=audit(path,p)
                    self.assertEqual(result['status'],'stopped');self.assertEqual(reader.count,index)
                    self.assertLessEqual(len(instances),2)
            print('Synthetic HTTP failure boundaries audited:',count)
    def test_rpc_and_json_failures_before_and_after_rotation(self):
        for kind in ('rpc','json'):
            for index in (1,30):
                with self.subTest(kind=kind,index=index),tempfile.TemporaryDirectory() as tmp:
                    chain,p,raw=fixture();path=Path(tmp)/'p'
                    execute(path,chain,p,raw,fail=index,kind=kind)
                    self.assertEqual(audit(path,p)['status'],'stopped')
    def test_single_request_budget_survives_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();path=Path(tmp)/'base'
            execute(path,chain,p,raw)
            journal=[json.loads(x) for x in (path/'journal.jsonl').read_text().splitlines()]
            boundary=next(r['data']['rpc_calls_before'] for r in journal if r['kind']=='measurement_session_started')
            for count in (1,boundary-1,boundary,boundary+1):
                chain,p,raw=fixture();p['max_requests']=count;path=Path(tmp)/str(count)
                reader,_=execute(path,chain,p,raw)
                self.assertEqual(audit(path,p)['status'],'stopped');self.assertEqual(reader.count,count)
    def test_expired_time_has_no_rpc_and_no_frozen_cohort(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();path=Path(tmp)/'p';reader,_=execute(path,chain,p,raw,expire=True)
            result=audit(path,p)
            self.assertEqual(reader.count,0);self.assertIsNone(result['cohort'])
            self.assertEqual(result['status'],'stopped')
    def test_rotation_cannot_reset_bytes_time_or_count_or_follow_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();factory=lambda:Synthetic(chain)
            reader=Reader(Path(tmp)/'p',p,factory(),factory)
            reader.call('eth_chainId',[],'chain')
            before=(reader.count,reader.total,reader.started_ns)
            reader.rotate_for_measurement()
            self.assertEqual((reader.count,reader.total,reader.started_ns),before)
            with self.assertRaisesRegex(ValueError,'ONE_HEALTHY'):reader.rotate_for_measurement()
            other=Reader(Path(tmp)/'q',p,Synthetic(chain,1),factory)
            with self.assertRaises(OSError):other.call('eth_chainId',[],'chain')
            with self.assertRaisesRegex(ValueError,'ONE_HEALTHY'):other.rotate_for_measurement()
    def test_time_and_byte_caps_still_apply_after_rotation(self):
        from transport import MAX_TOTAL
        with tempfile.TemporaryDirectory() as tmp:
            for kind in ('time','bytes'):
                chain,p,raw=fixture();factory=lambda:Synthetic(chain)
                reader=Reader(Path(tmp)/kind,p,factory(),factory)
                reader.call('eth_chainId',[],'chain');reader.rotate_for_measurement()
                if kind=='time':
                    reader.started_ns-=901*10**9
                    with self.assertRaisesRegex(ValueError,'TIME_BUDGET'):reader.call('eth_chainId',[],'next')
                    self.assertEqual(reader.count,1)
                else:
                    reader.total=MAX_TOTAL
                    with self.assertRaisesRegex(ValueError,'RESPONSE_BYTE_BUDGET'):reader.call('eth_chainId',[],'next')
                    self.assertTrue(reader.stopped);self.assertEqual(reader.count,2)
    def test_repeated_head_retained_but_regression_rejected(self):
        for regression in (False,True):
            with self.subTest(regression=regression),tempfile.TemporaryDirectory() as tmp:
                chain,p,raw=fixture();original=chain.answer;latest_calls=0;prior=None
                def answer(q):
                    nonlocal latest_calls,prior
                    if q['method']=='eth_getBlockByNumber' and q['params'][0]=='latest':
                        latest_calls+=1
                        if latest_calls==3:
                            height=int(prior['number'],16)-(1 if regression else 0)
                            return original(dict(q,params=[hex(height),False]))
                        result=original(q);prior=result;return result
                    return original(q)
                chain.answer=answer;path=Path(tmp)/'p';execute(path,chain,p,raw)
                result=audit(path,p)
                if regression:self.assertEqual(result['status'],'stopped')
                else:
                    self.assertEqual(result['status'],'completed')
                    self.assertTrue(result['observations'][1]['repeated_head'])
    def test_resume_and_anchor_reorg_stop_without_promoting_cohort(self):
        for target in ('resume-checkpoint','anchor-after-index'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as tmp:
                chain,p,raw=fixture();base=Path(tmp)/'base';reader,_=execute(base,chain,p,raw)
                index=next(r['payload']['id'] for r in reader.records if r['label']==target)
                chain,p,raw=fixture();path=Path(tmp)/'p'
                def mutate(q,response):
                    value=json.loads(response)
                    if q['id']==index:value['result']['hash']='0x'+'e'*64
                    return canonical(value)
                execute(path,chain,p,raw,mutate=mutate)
                result=audit(path,p)
                self.assertEqual(result['registry']['status'],'invalidated');self.assertIsNone(result['cohort'])
    def test_canonical_observation_reorg_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();base=Path(tmp)/'base';reader,_=execute(base,chain,p,raw)
            index=next(r['payload']['id'] for r in reader.records if r['label']=='r0-canonical')
            chain,p,raw=fixture();path=Path(tmp)/'p'
            def mutate(q,response):
                value=json.loads(response)
                if q['id']==index:value['result']['hash']='0x'+'e'*64
                return canonical(value)
            execute(path,chain,p,raw,mutate=mutate)
            result=audit(path,p)
            self.assertEqual(result['status'],'stopped');self.assertEqual(result['observations'],[])
    def test_persisted_registry_and_rehashed_metrics_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain,p,raw=fixture();path=Path(tmp)/'p';execute(path,chain,p,raw)
            original=(path/'registry.json').read_bytes()
            (path/'registry.json').write_bytes(original+b' ')
            with self.assertRaisesRegex(ValueError,'PERSISTED_FILE_DIFFERS'):audit(path,p)
            (path/'registry.json').write_bytes(original)
            def mutate(rows):next(r for r in rows if r['kind']=='observation_completed')['data']['request_to_verified_ms']=0
            rewrite_journal(path,mutate)
            with self.assertRaisesRegex(ValueError,'JOURNAL_REPLAY_DIFFERS'):audit(path,p)
    def test_source_and_oversized_budgets_rejected_before_network(self):
        chain,p,raw=fixture()
        with self.assertRaisesRegex(ValueError,'SOURCE_FILE_HASH'):source(p,raw+b' ')
        with tempfile.TemporaryDirectory() as tmp:
            for field,value in [('max_requests',513),('max_run_seconds',901)]:
                with self.assertRaisesRegex(ValueError,'BOUNDED_BUDGET'):Reader(Path(tmp)/field,dict(p,**{field:value}))


if __name__=='__main__':unittest.main()
