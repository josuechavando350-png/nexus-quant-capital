"""Offline synthetic failure injection. No fixture represents market evidence."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from continuation import HERE, PRIOR, canonical, registry, PhaseReader, Journal
from run_continuation import run, source_state
from audit_continuation import audit
from test_experiment import LensChain, segment, event, A, B, rewrite_journal
from run_experiment import run as prior_run
from audit_experiment import audit as prior_audit

POLICY=json.loads((HERE/'policy.json').read_text())


def fixture():
    fake=LensChain();fake.events=[event(999981,B),event(1000000,A)]
    source=segment(1000000,1000005,[event(1000000,A)],fake.timestamp)
    source_bytes=canonical({'state':source,'sha256':registry.digest(source)})
    policy=dict(POLICY,backfill_blocks=20,backfill_from_block=999980,backfill_through_block=999999,
                shard_blocks=10,source_registry_file_sha256=hashlib.sha256(source_bytes).hexdigest())
    return fake,policy,source_bytes


class Fault:
    def __init__(self,fake,index=None,kind='rpc',first_latest=False):
        self.fake,self.index,self.kind,self.first_latest=fake,index,kind,first_latest;self.count=0
    def __call__(self,payload):
        self.count+=1
        fail=self.count==self.index or (self.first_latest and type(payload) is dict and payload['method']=='eth_getBlockByNumber' and payload['params'][0]=='latest')
        if fail:
            if self.kind=='http':raise urllib.error.HTTPError('https://fixture.invalid',429,'fixture',None,None)
            if self.kind=='json':return b'{'
            values=payload if type(payload) is list else [payload]
            errors=[{'jsonrpc':'2.0','id':q['id'],'error':{'code':-32000,'message':'synthetic injected failure'}} for q in values]
            return canonical(errors if type(payload) is list else errors[0])
        return self.fake(payload)


def execute(folder,fake,policy,source_bytes,runner=run,max_requests=512):
    reader=PhaseReader(folder,fake,max_requests=max_requests);journal=Journal(folder)
    with patch('builtins.print'):
        try:runner(reader,journal,policy,'1'*40,source_bytes)
        except Exception as error:
            journal.append('stopped',{'exception':type(error).__name__,'reason':str(error),
                                     'rpc_calls':reader.count,'http_requests':len(reader.records),'realized_profit':None})
    return reader


class PartialAuditTests(unittest.TestCase):
    def test_prior_defect_reproduced_and_new_auditor_preserves_merged_stage(self):
        fake,policy,source_bytes=fixture()
        policy['paired_read_order']=[['creation','batch'],['batch','creation'],['creation','batch']]
        policy.pop('read_mode')
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';execute(folder,Fault(fake,first_latest=True),policy,source_bytes,prior_run)
            with self.assertRaisesRegex(ValueError,'PERSISTED_REGISTRY_DIFFERS'):prior_audit(folder,policy)
            result=audit(folder,policy)
            self.assertTrue(result['backfill_merged']);self.assertEqual(result['last_phase'],'merged')
            self.assertEqual(result['persisted_registry_file'],'merged-before-catchup.json')
            self.assertEqual(result['status'],'stopped');self.assertIsNone(result['cohort'])

    def test_rpc_failure_at_every_http_boundary_preserves_auditable_partial_result(self):
        fake,policy,source_bytes=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);reader=execute(base/'complete',fake,policy,source_bytes)
            count=len(reader.records)
            self.assertEqual(audit(base/'complete',policy)['status'],'completed')
            for index in range(1,count+1):
                with self.subTest(http_request=index):
                    f,p,s=fixture();folder=base/f'failure-{index}'
                    r=execute(folder,Fault(f,index),p,s);result=audit(folder,p)
                    self.assertEqual(result['status'],'stopped');self.assertEqual(result['rpc_errors'],1)
                    self.assertEqual(result['http_requests'],index);self.assertEqual(len(r.records),index)
                    self.assertIsNone(result['realized_profit'])
            print('Synthetic RPC failure boundaries audited:',count)

    def test_http_denial_and_malformed_json_at_initial_and_post_merge_requests(self):
        for kind in ['http','json']:
            for initial in [True,False]:
                with self.subTest(kind=kind,initial=initial),tempfile.TemporaryDirectory() as tmp:
                    fake,p,s=fixture();folder=Path(tmp)/'run'
                    execute(folder,Fault(fake,index=1 if initial else None,first_latest=not initial,kind=kind),p,s)
                    result=audit(folder,p);self.assertEqual(result['rpc_errors'],1);self.assertEqual(result['status'],'stopped')
                    self.assertEqual(result['chain_verified'],not initial)

    def test_request_budget_stop_before_next_post(self):
        fake,p,s=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';reader=execute(folder,fake,p,s,max_requests=4)
            result=audit(folder,p);self.assertEqual(result['status'],'stopped');self.assertEqual(reader.count,4)
            self.assertEqual(result['rpc_errors'],0);self.assertIsNone(result['cohort'])

    def test_stop_before_first_post_has_zero_requests_and_no_promoted_state(self):
        fake,p,s=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';reader=PhaseReader(folder,fake);journal=Journal(folder)
            reader.started_ns-=901*10**9
            with patch('builtins.print'),self.assertRaisesRegex(ValueError,'TIME_BUDGET'):run(reader,journal,p,'1'*40,s)
            journal.append('stopped',{'rpc_calls':0,'http_requests':0,'realized_profit':None})
            result=audit(folder,p);self.assertFalse(result['chain_verified']);self.assertIsNone(result['registry'])
            self.assertEqual(result['http_requests'],0)

    def test_missing_nonempty_request_ledger_cannot_be_silently_accepted(self):
        fake,p,s=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';execute(folder,Fault(fake,index=1),p,s)
            (folder/'requests.json').unlink()
            with self.assertRaisesRegex(ValueError,'TERMINAL_COUNTS'):audit(folder,p)

    def test_wrong_chain_remains_unverified_without_promoting_history(self):
        class WrongChain(LensChain):
            def answer(self,q):return '0x1' if q['method']=='eth_chainId' else super().answer(q)
        fake,p,s=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';execute(folder,WrongChain(),p,s)
            result=audit(folder,p);self.assertFalse(result['chain_verified']);self.assertIsNone(result['registry'])

    def test_backfill_and_catchup_anchor_reorg_invalidate_copy(self):
        for phase in ['backfill','catchup']:
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as tmp:
                fake,p,s=fixture();folder=Path(tmp)/'run';reader=PhaseReader(folder,fake);journal=Journal(folder)
                original=reader.transport
                def changed(payload):
                    raw=original(payload)
                    if reader.records[-1]['label']==phase+'-anchor-after-index':
                        value=json.loads(raw);value['result']['hash']='0x'+'e'*64;return canonical(value)
                    return raw
                reader.transport=changed
                with patch('builtins.print'),self.assertRaises(ValueError):run(reader,journal,p,'1'*40,s)
                journal.append('stopped',{'rpc_calls':reader.count,'http_requests':len(reader.records),'realized_profit':None})
                result=audit(folder,p);self.assertEqual(result['registry']['status'],'invalidated');self.assertIsNone(result['cohort'])

    def test_catchup_resume_reorg_invalidates_merged_copy(self):
        fake,p,s=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';reader=PhaseReader(folder,fake);journal=Journal(folder);original=reader.transport
            def changed(payload):
                raw=original(payload)
                if reader.records[-1]['label']=='catchup-resume-checkpoint':
                    value=json.loads(raw);value['result']['hash']='0x'+'e'*64;return canonical(value)
                return raw
            reader.transport=changed
            with patch('builtins.print'),self.assertRaisesRegex(ValueError,'REORG'):run(reader,journal,p,'1'*40,s)
            journal.append('stopped',{'rpc_calls':reader.count,'http_requests':len(reader.records),'realized_profit':None})
            result=audit(folder,p);self.assertEqual(result['registry']['status'],'invalidated')
            self.assertEqual(result['persisted_registry_file'],'registry.json');self.assertIsNone(result['cohort'])

    def test_partial_registry_tampering_rejected(self):
        fake,p,s=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';execute(folder,Fault(fake,first_latest=True),p,s)
            path=folder/'merged-before-catchup.json';value=json.loads(path.read_text())
            value['state']['segments'][0]['end']['timestamp']+=1;value['sha256']=registry.digest(value['state']);path.write_bytes(canonical(value))
            with self.assertRaises(ValueError):audit(folder,p)


class ObservationTests(unittest.TestCase):
    def test_complete_three_single_reads_and_verified_latency(self):
        fake,p,s=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';reader=execute(folder,fake,p,s);result=audit(folder,p)
            self.assertEqual(result['cohort']['addresses'],[A,B]);self.assertEqual(len(result['snapshots']),3)
            self.assertEqual(result['comparisons'],[]);self.assertEqual(len(result['observations']),3)
            self.assertEqual(sum(r.get('kind')=='fixed_creation_view' for r in reader.records),3)
            for row in result['observations']:
                self.assertGreaterEqual(row['head_to_verified_ms'],row['head_to_inputs_ms'])
                self.assertGreaterEqual(row['header_request_to_verified_ms'],row['head_to_verified_ms'])

    def test_rehashed_verified_latency_tampering_rejected(self):
        fake,p,s=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';execute(folder,fake,p,s)
            def mutate(rows):next(r for r in rows if r['kind']=='observation_completed')['data']['head_to_verified_ms']=0
            rewrite_journal(folder,mutate)
            with self.assertRaisesRegex(ValueError,'OBSERVATION_METRICS'):audit(folder,p)

    def test_invalid_source_and_nonadjacent_window_rejected_before_rpc(self):
        fake,p,s=fixture()
        with self.assertRaisesRegex(ValueError,'SOURCE_FILE_HASH'):source_state(p,s+b' ')
        with self.assertRaisesRegex(ValueError,'FIXED_BACKFILL_WINDOW'):source_state(dict(p,backfill_through_block=999998),s)

    def test_prior_real_capture_reconstructs_exactly_without_network(self):
        previous=json.loads((PRIOR/'evidence/pilot-report.json').read_text())
        result=audit(PRIOR/'evidence/pilot',json.loads((PRIOR/'policy.json').read_text()))
        self.assertEqual({k:result[k] for k in previous},previous)


if __name__=='__main__':unittest.main()
