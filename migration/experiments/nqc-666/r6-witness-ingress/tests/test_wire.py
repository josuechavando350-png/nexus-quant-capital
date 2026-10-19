import ast
import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import subprocess
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from corpus import cases, wrap, encode, ROOT, R3, R4, R5
from fixtures import make_case
from fixtures import policy_json
import state_evidence as old
from state_evidence_fast import verify as r5_verify
from object_evidence import verify_object
from proof_nodes import ProofDecoder
from canonical_hex import data
from native_math import NativeMath
from witness_gateway import StableGateway
from wire_evidence import (packet_from_wire, request_plan, storage_key,
                           verify_wire, verify_wire_object, verify_wire_baseline)

VERIFIERS = (verify_wire_baseline, verify_wire_object, verify_wire)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m
    spec.loader.exec_module(m); return m


def object_from_raw(raw, policy, now_s, *, shared=True):
    return verify_object(old.load_packet(raw), policy, now_s, shared=shared)


def load_tests(loader, tests, pattern):
    m = module("r6_inherited_evidence", R3 / "tests/test_evidence.py")
    m.verify, m.ProofDecoder = object_from_raw, ProofDecoder
    tests.addTests(loader.loadTestsFromTestCase(m.EvidenceTests))
    m = module("r6_inherited_traversal", R5 / "tests/test_traversal.py")
    m.ProofDecoder = ProofDecoder
    m.fast = types.SimpleNamespace(verify=object_from_raw)
    tests.addTests(loader.loadTestsFromTestCase(m.TraversalTests))
    m = module("r6_inherited_guards", R4 / "tests/test_stability.py")
    # Guard regression with the exact R5 input verifier, plus wire integration below.
    def guard_gateway(*args, **kwargs):
        return StableGateway(*args, **kwargs, verifier=r5_verify)
    m.StableGateway = guard_gateway
    tests.addTests(loader.loadTestsFromTestCase(m.StabilityTests))
    return tests


class WireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet, cls.policy, cls.words = make_case(666301)
        cls.wire = wrap(cls.packet, cls.policy)
        cls.raw, cls.now = encode(cls.wire), cls.policy.anchor.timestamp
        lib = Path(os.environ["NQC_NATIVE_LIB"])
        cls.native = NativeMath(lib, hashlib.sha256(lib.read_bytes()).hexdigest())

    def reject(self, w):
        for verifier in VERIFIERS:
            with self.assertRaises(old.Rejected): verifier(encode(w), self.policy, self.now)

    def test_semantic_and_guard_bodies_preserved(self):
        source = (R5 / "python/state_evidence_fast.py").read_text()
        expected = source[source.index("def _verify(raw,"):].replace(
            "def _verify(raw, policy, now_s, shared):\n    p = load_packet(raw)",
            "def _verify_object(p, policy, now_s, shared, decoder_type):").replace(
            "decoder = ProofDecoder(shared)", "decoder = decoder_type(shared)")
        actual = (ROOT / "python/object_evidence.py").read_text()
        self.assertEqual(expected, actual[actual.index("def _verify_object("):])
        old_guard = (R5 / "python/fast_gateway.py").read_text()
        new_guard = (ROOT / "python/witness_gateway.py").read_text()
        new_guard = new_guard.replace(", verifier=verify_wire_baseline", "").replace(
            "        self._verify = verifier\n", "").replace(
            "self._verify(raw, self._policy, now_s)", "verify(raw, self._policy, now_s, shared=True)")
        classes = lambda s: [ast.dump(n) for n in ast.parse(s).body if isinstance(n, ast.ClassDef)]
        self.assertEqual(classes(old_guard), classes(new_guard))
        self.assertEqual(classes((R5 / "python/proof_traversal.py").read_text()),
                         classes((ROOT / "python/proof_nodes.py").read_text()))

    def test_hex_parser_differential(self):
        rng = random.Random(666601)
        inputs = [None, True, 2, b"0x00", "", "0x", "0Xff", "0x0", "0x00\n", "0x ff", "0xＦＦ", "0xéé"]
        for n in (0,1,2,31,32,255,512,2048):
            s = "0x" + rng.randbytes(n).hex()
            inputs += [s, s.upper()]
        for c in range(512):
            inputs += ["0x" + chr(c) + "0", "0x00" + chr(c) + "0", chr(c) + "x00"]
        inputs += ["0x" + "00" * (old.MAX_PACKET // 2)]
        for s in inputs:
            for size in (None,0,1,32):
                results=[]
                for f in (old.data, data):
                    try: results.append((True, f(s,size)))
                    except old.Rejected: results.append((False,None))
                self.assertEqual(results[0],results[1])

    def test_corpus_and_shuffled_responses(self):
        for raw, policy in cases():
            w=json.loads(raw); w["responses"].reverse(); raw=encode(w)
            results=[f(raw,policy,policy.anchor.timestamp) for f in VERIFIERS]
            self.assertTrue(all(x==results[0] for x in results))
            self.assertFalse(results[0].commercial_admission)
            self.assertIsNone(results[0].observed_eligibility)

    def test_transport_identity_errors(self):
        for field,value in (("jsonrpc","1.0"),("id",True),("id",5),("result",None)):
            w=copy.deepcopy(self.wire);w["responses"][0][field]=value;self.reject(w)
        for mode in ("duplicate", "missing", "error", "result_and_error", "unknown_field"):
            w=copy.deepcopy(self.wire)
            if mode=="duplicate":w["responses"][-1]=w["responses"][0]
            elif mode=="missing":w["responses"].pop()
            elif mode=="error":w["responses"][-1]={"jsonrpc":"2.0","id":4,"error":{"code":-32000,"message":"missing"}}
            elif mode=="result_and_error":w["responses"][-1]["error"]={"code":-32000}
            else:w["authenticated"]=True
            self.reject(w)

    def test_requests_never_change_chain_block_or_state_point(self):
        mutations=[lambda w:w["requests"][2]["params"].__setitem__(1,"latest"),
                   lambda w:w["requests"][3]["params"][2].__setitem__("requireCanonical",False),
                   lambda w:w["requests"][0].__setitem__("id",True),
                   lambda w:w["requests"][1]["params"].__setitem__(1,0),
                   lambda w:w["requests"][3].__setitem__("method","eth_sendRawTransaction"),
                   lambda w:w.__setitem__("statePoint","before_transaction_1"),
                   lambda w:w["responses"][0].__setitem__("result",hex(4663))]
        for mutate in mutations:
            w=copy.deepcopy(self.wire);mutate(w);self.reject(w)
        with self.assertRaises(old.Rejected): request_plan(replace(self.policy,anchor=replace(self.policy.anchor,chain=4663)))

    def test_mixed_roots_and_missing_proofs_are_rejected(self):
        packet,policy,_=make_case(666302)
        for index in (1,2,3):
            w=copy.deepcopy(self.wire);w["responses"][index]=wrap(packet,policy)["responses"][index]
            self.reject(w)
        w=copy.deepcopy(self.wire);w["responses"][3]["result"]["accountProof"]=[];self.reject(w)

    def test_storage_key_width_normalization_and_duplicate_values(self):
        for s in ("0x0","0x00","0x01","0x1", "0x"+"00"*31+"01"):
            self.assertEqual(int(storage_key(s),16),int(s,16))
        for s in ("0x",None,True,"0x-1","0X01","0x"+"11"*33):
            with self.assertRaises(old.Rejected):storage_key(s)
        w=copy.deepcopy(self.wire)
        proof=w["responses"][3]["result"]["storageProof"]
        for row in proof:row["key"]=hex(int(row["key"],16))
        self.assertEqual(verify_wire(encode(w),self.policy,self.now).values(),self.words)
        proof[-1]=dict(proof[0]);self.reject(w)

    def test_wire_integration_and_revocation_for_all_variants(self):
        for verifier in VERIFIERS:
            g=StableGateway(self.policy,self.native,verifier=verifier)
            t=g.ingest(self.raw,self.now)
            s=g.scenario(t,self.now,10**36)
            self.assertFalse(s.commercial_admission)
            self.assertFalse(g.authorize(t,self.now)["commercial_admission"])
            with self.assertRaises(old.Rejected):g.ingest(b"{}",self.now)
            with self.assertRaises(old.Rejected):g.facts(t,self.now)

    def test_wire_processing_included_in_deadline(self):
        ticks=iter((1,50_000_002))
        g=StableGateway(self.policy,self.native,clock=lambda:next(ticks))
        with self.assertRaisesRegex(old.Rejected,"processing deadline"):g.ingest(self.raw,self.now)
        self.assertIsNone(g._facts)

    def test_handoff_is_real_artifact_but_not_authenticated_state(self):
        handoff=json.loads((ROOT / "reference/ESTADO_HISTORICO.json").read_text())
        self.assertFalse(handoff["authenticated_prestate"])
        self.assertIsNone(handoff["exact_pretransaction_state_root"])
        self.assertEqual(handoff["chain_id_claim"],4663)
        for verifier in VERIFIERS:
            with self.assertRaises(old.Rejected):verifier(encode(handoff),self.policy,self.now)

    def test_cli_preserves_inputs_and_never_reports_chain_authentication(self):
        with tempfile.TemporaryDirectory(prefix="nqc666-r6-import-") as folder:
            tmp=Path(folder); packet=tmp/"capture.json";policy=tmp/"policy.json"
            packet.write_bytes(self.raw);policy.write_text(json.dumps(policy_json(self.policy)))
            lib=Path(os.environ["NQC_NATIVE_LIB"])
            cmd=[sys.executable,str(ROOT/"scripts/import_capture.py"),"--policy",str(policy)]
            r=subprocess.run(cmd+["--out",str(tmp/"plan")],capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(json.loads((tmp/"plan/result.json").read_text())["status"],"REQUEST_PLAN_ONLY_NOT_SENT")
            cmd += ["--capture",str(packet),"--library",str(lib),"--library-sha256",
                    hashlib.sha256(lib.read_bytes()).hexdigest(),"--observed-now",str(self.now)]
            for variant in ("baseline","object","optimized"):
                path=tmp/variant
                r=subprocess.run(cmd+["--variant",variant,"--out",str(path)],capture_output=True)
                self.assertEqual(r.returncode,0,r.stderr)
                result=json.loads((path/"result.json").read_text())
                self.assertTrue(result["root_binding_verified"])
                self.assertFalse(result["commercial_admission"])
                self.assertEqual(result["canonicality"],"unknown")
                self.assertEqual((path/"input-capture.json").read_bytes(),self.raw)
            packet.write_bytes((ROOT/"reference/ESTADO_HISTORICO.json").read_bytes())
            r=subprocess.run(cmd+["--out",str(tmp/"rejected")],capture_output=True)
            self.assertEqual(r.returncode,2,r.stderr)
            result=json.loads((tmp/"rejected/result.json").read_text())
            self.assertFalse(result["root_binding_verified"])
            self.assertNotIn("words",result)


if __name__ == "__main__":unittest.main()
