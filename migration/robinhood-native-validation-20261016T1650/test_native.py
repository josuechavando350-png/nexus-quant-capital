import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import native_validation as nv
import capture_native as run
from test_validation import abi_result


def trace_for(case):
    if case['case'] == 'invalid_signature':
        trace = nv.read(nv.PREVIOUS/'evidence/pilot/04-debug_traceCall.json')['result']
        pos=next(i for i,c in enumerate(trace['calls']) if c.get('to')==nv.NATIVE)
        trace['calls'][pos+1]['gasUsed']=3000
        return trace
    if case['case'] in ('31s_zero_deposit','31s_zero_budget'):
        marker = 'AA31' if case['case']=='31s_zero_deposit' else 'BUDGET_POLICY'
        return {'calls':[{'type':'REVERT','data':'0x'+marker.encode().hex()}]}
    return {'calls':[{'type':'STATICCALL','to':nv.NATIVE},
                     {'type':'RETURN','gasUsed':3000,'data':'0x'+(123).to_bytes(32,'big').hex()},
                     {'type':'RETURN','data':abi_result(case)}],
            'callsFromEntryPoint':[{'topLevelTargetAddress':nv.PM, 'access':{nv.PM:{
                'reads':{nv.prior.SLOT1:nv.prior.word(case['window']['budget_wei'])},
                'writes':{nv.prior.SLOT1:1}}}, 'opcodes':{'SLOAD':1,'SSTORE':1}}]}


class Clock:
    def __init__(self): self.value=0
    def now(self): return self.value
    def sleep(self,n): self.value+=n


class Response:
    status=200
    def __init__(self,body): self.body=body
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,limit): return self.body[:limit]


class HTTP:
    def __init__(self,body=None,error=None): self.count=0;self.body=body;self.error=error
    def open(self,req,timeout):
        self.count+=1
        if self.error: raise self.error
        n=json.loads(req.data)['id']
        return Response(self.body if self.body is not None else json.dumps({'id':n,'result':'0x1237'}).encode())


class ScriptRPC:
    def __init__(self,fail=None,bad_hash=False): self.count=0;self.fail=fail;self.bad_hash=bad_hash
    def rpc(self,method,params):
        self.count+=1
        if self.count==self.fail: raise ValueError('synthetic RPC interruption')
        if method=='web3_clientVersion': return 'Geth/v1.17.8-fixture'
        if method=='eth_chainId': return hex(4663)
        if method=='eth_getBlockByNumber':
            return {'hash':'0x02' if self.bad_hash and self.count==10 else '0x01',
                    'stateRoot':'0x03','number':'0x0','timestamp':hex(1789786800)}
        return trace_for(nv.fixture(nv.CASES[self.count-4])[0])


class NativeTests(unittest.TestCase):
    def test_six_controls_share_genesis_and_preserve_original_balances(self):
        cases,initial=nv.cases_and_genesis()
        self.assertEqual(len(cases),6)
        self.assertEqual(initial['alloc'][nv.NATIVE[2:]]['balance'],
                         nv.prior.fixture(nv.prior.CASES[0])['stateOverrides'][nv.NATIVE]['balance'])
        for case in cases:
            self.assertFalse(any(1<=int(a,16)<=9 for a in case['stateOverrides']))
            self.assertEqual(case['native_precompile_state_moved_to_genesis'][0]['address'],nv.NATIVE)

    def test_only_signature_bytes_mutate_in_negative_control(self):
        positive,_=nv.fixture(nv.CASES[0]);negative,_=nv.fixture('invalid_signature')
        a=bytes.fromhex(positive['transaction']['data'][2:]);b=bytes.fromhex(negative['transaction']['data'][2:])
        start,end=negative['signature_negative_control'].values()
        self.assertEqual(a[:start],b[:start]);self.assertEqual(a[end:],b[end:])
        self.assertNotEqual(a[start:end],bytes(65));self.assertEqual(b[start:end],bytes(65))
        self.assertEqual(positive['stateOverrides'],negative['stateOverrides'])

    def test_positive_requires_native_execution_not_empty_return(self):
        case,_=nv.fixture(nv.CASES[0]);trace=trace_for(case)
        self.assertTrue(nv.summarize(case,trace)['paymaster_reached'])
        trace['calls'][1]={'type':'RETURN','gasUsed':0,'data':'0x'}
        with self.assertRaises(AssertionError):nv.summarize(case,trace)

    def test_negative_requires_invalid_signature_and_no_paymaster(self):
        case,_=nv.fixture('invalid_signature');trace=trace_for(case)
        self.assertFalse(nv.summarize(case,trace)['paymaster_reached'])
        trace['callsFromEntryPoint'].append({'topLevelTargetAddress':nv.PM})
        with self.assertRaises(AssertionError):nv.summarize(case,trace)

    def test_each_rpc_boundary_stops_with_completed_prefix(self):
        for boundary in range(1,11):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as d:
                rpc=ScriptRPC(fail=boundary);report={'cases':[]}
                with self.assertRaisesRegex(ValueError,'interruption'):run.observe(rpc,Path(d),report)
                self.assertEqual(rpc.count,boundary)
                self.assertEqual(len(report['cases']),min(6,max(0,boundary-4)))

    def test_expected_reverts_complete_without_full_bundler_claim(self):
        with tempfile.TemporaryDirectory() as d:
            rpc=ScriptRPC();report={'cases':[]};run.observe(rpc,Path(d),report)
            self.assertEqual(rpc.count,10);self.assertEqual(len(report['cases']),6)
            self.assertTrue(all(x['full_bundler_admission_proven'] is False for x in report['cases']))
            self.assertEqual(report['status'],'LOCAL_NATIVE_VALIDATION_COMPLETE_FULL_BUNDLER_BLOCKED')

    def test_changed_final_header_stops(self):
        with tempfile.TemporaryDirectory() as d:
            rpc=ScriptRPC(bad_hash=True);report={'cases':[]}
            with self.assertRaises(AssertionError):run.observe(rpc,Path(d),report)
            self.assertNotIn('local_state_unchanged',report)

    def test_unexpected_result_stops_before_next_control(self):
        with tempfile.TemporaryDirectory() as d:
            rpc=ScriptRPC();report={'cases':[]}
            with patch.object(run,'summarize',side_effect=ValueError('unexpected result')):
                with self.assertRaisesRegex(ValueError,'unexpected result'):run.observe(rpc,Path(d),report)
            self.assertEqual(rpc.count,4);self.assertEqual(report['cases'],[])

    def test_global_rate_has_no_accumulated_burst(self):
        with tempfile.TemporaryDirectory() as d:
            c=Clock();j=run.LocalJournal(Path(d),0,c.now,c.sleep);j.http=HTTP()
            j.rpc('eth_chainId',[]);c.value=5;j.rpc('eth_chainId',[]);j.rpc('eth_chainId',[])
            self.assertEqual([r['dispatch_seconds'] for r in j.rows],[0,5,5.35])

    def test_deadline_before_and_after_sleep_no_dispatch(self):
        for oversleep in (False,True):
            with tempfile.TemporaryDirectory() as d:
                c=Clock();c.value=879.9 if oversleep else 880
                sleeper=(lambda n:setattr(c,'value',901)) if oversleep else c.sleep
                j=run.LocalJournal(Path(d),0,c.now,sleeper);j.last=c.value-.3;j.http=HTTP()
                with self.assertRaisesRegex(ValueError,'deadline'):j.rpc('eth_chainId',[])
                self.assertEqual(j.http.count,0);self.assertTrue(j.failed)

    def test_response_error_and_json_error_preserve_and_prevent_retry(self):
        for body in (b'{bad',b'{"id":1,"error":{"code":-32000}}',b'{"id":2,"result":0}'):
            with tempfile.TemporaryDirectory() as d:
                j=run.LocalJournal(Path(d),run.time.monotonic());j.http=HTTP(body)
                with self.assertRaises(ValueError):j.rpc('eth_chainId',[])
                self.assertEqual((Path(d)/'01-eth_chainId.json').read_bytes(),body)
                with self.assertRaises(ValueError):j.rpc('eth_chainId',[])
                self.assertEqual(j.http.count,1)

    def test_http_rejection_preserves_body_and_stops(self):
        with tempfile.TemporaryDirectory() as d:
            j=run.LocalJournal(Path(d),run.time.monotonic())
            j.http=HTTP(error=urllib.error.HTTPError(run.URL,429,'synthetic',{},io.BytesIO(b'denied')))
            with self.assertRaises(urllib.error.HTTPError):j.rpc('eth_chainId',[])
            self.assertEqual((Path(d)/'01-eth_chainId.json').read_bytes(),b'denied')
            with self.assertRaises(ValueError):j.rpc('eth_chainId',[])
            self.assertEqual(j.http.count,1)

    def test_body_limit_keeps_bounded_prefix(self):
        with tempfile.TemporaryDirectory() as d,patch.object(run,'MAX_BYTES',32):
            j=run.LocalJournal(Path(d),run.time.monotonic());j.http=HTTP(b'A'*100)
            with self.assertRaisesRegex(ValueError,'byte limit'):j.rpc('eth_chainId',[])
            self.assertEqual((Path(d)/'01-eth_chainId.json').stat().st_size,33)
            self.assertTrue(j.failed)

    def test_method_budget_loopback_and_no_redirect(self):
        self.assertEqual(run.URL,'http://127.0.0.1:18571')
        self.assertIsNone(run.NoRedirect().redirect_request(None,None,302,'',{},'https://example.com'))
        with tempfile.TemporaryDirectory() as d:
            j=run.LocalJournal(Path(d),run.time.monotonic());j.http=HTTP()
            for name in ('eth_sendRawTransaction','eth_sendTransaction','eth_sign'):
                with self.assertRaises(ValueError):j.rpc(name,[])
            j.rows=[{}]*512
            with self.assertRaises(ValueError):j.rpc('eth_chainId',[])
            self.assertEqual(j.http.count,0)


if __name__=='__main__':unittest.main()
