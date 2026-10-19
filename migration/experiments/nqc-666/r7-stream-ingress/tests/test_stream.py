import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from inputs import cases, chunks, StreamIngress, StableGateway, NativeMath, R6
from state_evidence import Rejected, MAX_PACKET
from fixtures import policy_json


class Clock:
    def __init__(self): self.t = 1_000_000
    def __call__(self): return self.t


class StreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = cases()
        cls.raw, cls.policy = cls.inputs[0]
        cls.now = max(p.anchor.timestamp for _, p in cls.inputs)
        lib = Path(os.environ["NQC_NATIVE_LIB"])
        cls.native = NativeMath(lib, hashlib.sha256(lib.read_bytes()).hexdigest())

    def setUp(self):
        self.clock = Clock()
        self.g = StreamIngress(self.policy, self.native, clock=self.clock)

    def complete(self, g=None, raw=None, policy=None, width=4096):
        g, raw, policy = g or self.g, raw or self.raw, policy or self.policy
        pieces = chunks(raw, width)
        h = g.begin(policy, self.now, pieces[0]); offset = len(pieces[0])
        for part in pieces[1:]:
            g.feed(h, offset, part, self.now); offset += len(part)
        return g.finish(h, self.now)

    def empty(self):
        self.assertIsNone(self.g._buffer)
        self.assertIsNone(self.g._ticket)
        self.assertIsNone(self.g._engine._facts)

    def test_all_corpus_fragmentations_match_r5(self):
        baseline = StableGateway(self.policy, self.native, clock=self.clock)
        for raw, policy in self.inputs:
            for width in (len(raw),4096,257):
                baseline.reset(policy); t = baseline.ingest(raw, self.now)
                r = self.complete(raw=raw, policy=policy, width=width)
                self.assertEqual(self.g.facts(r,self.now), baseline.facts(t,self.now))
                self.assertEqual(r.capture_sha256,hashlib.sha256(raw).hexdigest())
                self.assertEqual(r.bytes_received,len(raw))
                for price in (10**35,10**36,13*10**35):
                    self.assertEqual(self.g.scenario(r,self.now,price),baseline.scenario(t,self.now,price))
                self.assertEqual(self.g.authorize(r,self.now),baseline.authorize(t,self.now))
                self.assertFalse(self.g.authorize(r,self.now)["commercial_admission"])
                self.assertIsNone(self.g.facts(r,self.now).observed_eligibility)

    def test_r5_is_the_only_default_verifier(self):
        from wire_evidence import verify_wire_baseline
        self.assertIs(self.g._engine._verify, verify_wire_baseline)

    def test_update_revokes_prior_receipt_before_completion(self):
        old=self.complete()
        self.g.begin(self.policy,self.now,b"{")
        with self.assertRaises(Rejected):self.g.facts(old,self.now)
        self.empty()

    def test_superseded_and_foreign_capture_rejected(self):
        h=self.g.begin(self.policy,self.now,b"{")
        self.g.begin(self.policy,self.now,b"{")
        with self.assertRaises(Rejected):self.g.feed(h,1,b"}",self.now)
        self.empty()
        with self.assertRaises(Rejected):self.g.finish(object(),self.now)

    def test_duplicate_gap_negative_and_boolean_offsets(self):
        for offset in (0,2,-1,True,None,1.0):
            h=self.g.begin(self.policy,self.now,b"{")
            with self.assertRaises(Rejected):self.g.feed(h,offset,b"}",self.now)
            self.empty()

    def test_chunk_types_size_and_count_are_bounded(self):
        for bad in (b"",bytearray(b"{}"),memoryview(b"{}"),"{}",None):
            with self.assertRaises(Rejected):self.g.begin(self.policy,self.now,bad)
            self.empty()
        with self.assertRaises(Rejected):self.g.begin(self.policy,self.now,b"x"*(MAX_PACKET+1))
        self.empty()
        h=self.g.begin(self.policy,self.now,b" "*MAX_PACKET)
        with self.assertRaises(Rejected):self.g.feed(h,MAX_PACKET,b"x",self.now)
        self.empty()
        g=StreamIngress(self.policy,self.native,clock=self.clock,max_chunks=2)
        h=g.begin(self.policy,self.now,b"{");g.feed(h,1,b" ",self.now)
        with self.assertRaises(Rejected):g.feed(h,2,b"}",self.now)
        self.assertIsNone(g._buffer)

    def test_truncated_invalid_duplicate_json_and_trailing_bytes(self):
        for raw in (self.raw[:-1],b'{"x":1,"x":2}',self.raw+b"x",b'{"x":NaN}'):
            with self.assertRaises(Rejected):self.complete(raw=raw)
            self.empty()

    def test_copied_receipt_and_cross_session_receipt_rejected(self):
        r=self.complete()
        with self.assertRaises(Rejected):self.g.scenario(copy.copy(r),self.now,10**36)
        self.empty()
        other=StreamIngress(self.policy,self.native,clock=self.clock)
        r=self.complete(other)
        with self.assertRaises(Rejected):self.g.authorize(r,self.now)

    def test_abort_and_double_finish_revoke(self):
        h=self.g.begin(self.policy,self.now,self.raw)
        self.g.abort()
        with self.assertRaises(Rejected):self.g.finish(h,self.now)
        h=self.g.begin(self.policy,self.now,self.raw);self.g.finish(h,self.now)
        with self.assertRaises(Rejected):self.g.finish(h,self.now)
        self.empty()

    def test_capture_deadline_includes_inter_fragment_delay(self):
        h=self.g.begin(self.policy,self.now,b"{")
        self.clock.t+=50_000_000
        self.g.feed(h,1,b" ",self.now)  # Exact boundary accepted.
        self.clock.t+=1
        with self.assertRaisesRegex(Rejected,"capture deadline"):
            self.g.feed(h,2,b"}",self.now)
        self.empty()

    def test_capture_deadline_is_not_reset_by_last_fragment(self):
        h=self.g.begin(self.policy,self.now,self.raw[:1])
        self.clock.t+=49_000_000
        self.g.feed(h,1,self.raw[1:],self.now)
        verify=self.g._engine._verify
        def slow(*a):
            result=verify(*a);self.clock.t+=2_000_000;return result
        self.g._engine._verify=slow
        with self.assertRaisesRegex(Rejected,"capture deadline"):
            self.g.finish(h,self.now)
        self.empty()

    def test_expiry_remains_bound_to_first_fragment_with_frozen_wall_time(self):
        policy=replace(self.policy,max_age_s=1)
        now=policy.anchor.timestamp
        h=self.g.begin(policy,now,self.raw)
        self.clock.t+=40_000_000
        r=self.g.finish(h,now)
        self.clock.t+=960_000_001
        with self.assertRaisesRegex(Rejected,"snapshot expired"):self.g.facts(r,now)
        self.empty()

    def test_stale_backwards_future_and_boolean_observation_time(self):
        for now in (self.policy.anchor.timestamp-1,self.policy.anchor.timestamp+31,True):
            with self.assertRaises(Rejected):self.g.begin(self.policy,now,self.raw)
            self.empty()
        self.complete()
        with self.assertRaises(Rejected):self.g.begin(self.policy,self.now-1,self.raw)

    def test_bad_monotonic_clock_revokes(self):
        h=self.g.begin(self.policy,self.now,b"{");self.clock.t-=1
        with self.assertRaises(Rejected):self.g.feed(h,1,b"}",self.now)
        self.empty()

    def test_wrong_thread_cannot_feed_or_abort_owner_capture(self):
        h=self.g.begin(self.policy,self.now,self.raw); errors=[]
        def foreign():
            for f in (lambda:self.g.finish(h,self.now),self.g.abort):
                try:f()
                except Rejected:errors.append(True)
        t=threading.Thread(target=foreign);t.start();t.join()
        self.assertEqual(len(errors),2)
        self.g.finish(h,self.now)

    def test_reentry_even_if_caught_by_callback_revokes_result(self):
        verify=self.g._engine._verify
        def reentrant(*a):
            try:self.g.abort()
            except Rejected:pass
            return verify(*a)
        self.g._engine._verify=reentrant
        with self.assertRaises(Rejected):self.complete()
        self.empty()

    def test_baseexception_during_proof_revokes_and_recovers(self):
        verify=self.g._engine._verify
        def interrupted(*a):raise KeyboardInterrupt()
        self.g._engine._verify=interrupted
        with self.assertRaises(KeyboardInterrupt):self.complete()
        self.empty()
        self.g._engine._verify=verify
        self.complete()

    def test_late_or_inconsistent_math_revokes(self):
        class Slow:
            def health(inner,values):
                answer=self.native.health(values);self.clock.t+=5_000_001;return answer
        g=StreamIngress(self.policy,Slow(),clock=self.clock)
        r=self.complete(g)
        with self.assertRaises(Rejected):g.scenario(r,self.now,10**36)
        self.assertIsNone(g._engine._facts)
        class Bad:
            def health(inner,values):return (1,2,True)
        g=StreamIngress(self.policy,Bad(),clock=self.clock)
        r=self.complete(g)
        with self.assertRaises(Rejected):g.scenario(r,self.now,10**36)
        self.assertIsNone(g._engine._facts)

    def test_new_handoff_has_complete_reads_but_zero_authentication(self):
        raw=(ROOT/"reference/ESTADO_ACTUAL.json").read_bytes();v=json.loads(raw)
        self.assertTrue(v["adapter_storage_coverage"]["capture_read_set_complete"])
        self.assertEqual(v["checkpoint_values_recovered"],11)
        self.assertEqual(v["checkpoint_values_authenticated"],0)
        self.assertEqual(v["target_account_proofs_received"],0)
        self.assertEqual(v["target_storage_proofs_received"],0)
        self.assertIsNone(v["roots"]["exact_pretransaction_authenticated_root"])
        with self.assertRaises(Rejected):self.complete(raw=raw)
        self.empty()

    def test_chain_and_mixed_block_capture_rejected(self):
        wire=json.loads(self.raw)
        wire["responses"][0]["result"]=hex(4663)
        with self.assertRaises(Rejected):self.complete(raw=json.dumps(wire).encode())
        wire=json.loads(self.raw)
        wire["responses"][3]=json.loads(self.inputs[1][0])["responses"][3]
        with self.assertRaises(Rejected):self.complete(raw=json.dumps(wire).encode())
        self.empty()

    def test_cli_preserves_bytes_and_reports_only_relative_verification(self):
        with tempfile.TemporaryDirectory(prefix="nqc666-r7-") as folder:
            tmp=Path(folder);policy=tmp/"policy.json";capture=tmp/"capture.json"
            policy.write_text(json.dumps(policy_json(self.policy)));capture.write_bytes(self.raw)
            lib=Path(os.environ["NQC_NATIVE_LIB"])
            cmd=[sys.executable,str(ROOT/"scripts/replay_capture.py"),"--policy",str(policy),
                 "--capture",str(capture),"--library",str(lib),"--library-sha256",hashlib.sha256(lib.read_bytes()).hexdigest(),
                 "--observed-now",str(self.now),"--chunk-bytes","257","--out",str(tmp/"result")]
            r=subprocess.run(cmd,capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr)
            result=json.loads((tmp/"result/result.json").read_text())
            self.assertEqual(result["status"],"RELATIVE_ROOT_BINDING_VERIFIED")
            self.assertEqual(result["canonicality"],"unknown")
            self.assertFalse(result["commercial_admission"])
            self.assertEqual((tmp/"result/input-capture.json").read_bytes(),self.raw)
            capture.write_bytes((ROOT/"reference/ESTADO_ACTUAL.json").read_bytes())
            cmd[-1]=str(tmp/"bad");r=subprocess.run(cmd,capture_output=True)
            self.assertEqual(r.returncode,2,r.stderr)
            result=json.loads((tmp/"bad/result.json").read_text())
            self.assertEqual(result["status"],"REJECTED")
            self.assertNotIn("words",result)


if __name__=="__main__":unittest.main()
