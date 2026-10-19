import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import random
import sys
import threading
import unittest

import rlp
from eth_hash.auto import keccak
from trie.constants import BLANK_NODE_HASH

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from fixtures import encode, hx, make_case, make_trie, policy_from
from gateway import Gateway, MathWorker
from state_evidence import Anchor, Rejected, ProofDecoder, load_packet, verify, verify_header


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet, cls.policy, cls.words = make_case(666301)
        cls.now = cls.policy.anchor.timestamp

    def check_rejected(self, packet=None, policy=None, raw=None, now=None):
        raw = raw if raw is not None else encode(packet or self.packet)
        policy = policy or self.policy
        for shared in (False, True):
            with self.assertRaises(Rejected):
                verify(raw, policy, self.now if now is None else now, shared=shared)

    def test_corpus_and_equivalent_decoding(self):
        records = json.loads((ROOT / "fixtures/synthetic-index.json").read_text())
        for row in records:
            raw = (ROOT / "fixtures" / row["packet"]).read_bytes()
            p = policy_from(row["policy"])
            baseline = verify(raw, p, p.anchor.timestamp, shared=False)
            optimized = verify(raw, p, p.anchor.timestamp, shared=True)
            self.assertEqual(baseline.values(), row["words"])
            self.assertEqual(replace(baseline, nodes_decoded=optimized.nodes_decoded), optimized)
            self.assertLess(optimized.nodes_decoded, baseline.nodes_decoded)
            self.assertIsNone(optimized.observed_eligibility)
            self.assertIsNone(optimized.oracle_price)
            self.assertFalse(optimized.commercial_admission)
            self.assertEqual(optimized.canonicality, "unknown")

    def test_account_and_header_mutations(self):
        mutations = [("nonce", "0x2"), ("balance", "0x1"), ("address", hx(b"\1" * 20)),
                     ("codeHash", hx(b"\1" * 32)), ("storageHash", hx(b"\1" * 32))]
        for key, value in mutations:
            p = copy.deepcopy(self.packet)
            p["account"][key] = value
            with self.subTest(key=key):
                self.check_rejected(p)
        for key in self.packet["header"]:
            p = copy.deepcopy(self.packet)
            value = p["header"][key]
            p["header"][key] = value[:-1] + ("1" if value[-1] != "1" else "2")
            with self.subTest(header=key):
                self.check_rejected(p)

    def test_identity_and_schema(self):
        for key, value in [("chainId", "0x2"), ("blockHash", hx(b"\1" * 32)),
                           ("statePoint", "before_transaction_1"), ("schema", "unknown"),
                           ("code", "0x00")]:
            p = copy.deepcopy(self.packet)
            p[key] = value
            self.check_rejected(p)
        for p in [dict(self.packet, unexpected=True), {k: v for k, v in self.packet.items() if k != "account"}]:
            self.check_rejected(p)
        for field, value in [("market_id", b"\1" * 32), ("borrower", b"\1" * 20),
                             ("code_hash", b"\1" * 32), ("address", b"\1" * 20),
                             ("layout", "unknown"), ("max_age_s", 0), ("max_age_s", True)]:
            self.check_rejected(policy=replace(self.policy, **{field: value}))

    def test_clock_and_anchor(self):
        for now in (self.now - 1, self.now + 31, True, "100"):
            self.check_rejected(now=now)
        for field, value in [("chain", 2), ("chain", True), ("number", 0),
                             ("timestamp", self.now + 1), ("block_hash", b"\1" * 32),
                             ("source", "finalized")]:
            self.check_rejected(policy=replace(self.policy, anchor=replace(self.policy.anchor, **{field: value})))

    def test_missing_zero_and_duplicate_coverage(self):
        # IRM=0 is proved absent; removing its path is not evidence of zero.
        valid = verify(encode(self.packet), self.policy, self.now)
        self.assertEqual(valid.values()["irm"], 0)
        for mode in ("missing_account", "missing_slot", "empty_path", "duplicate_slot", "unexpected_slot", "wrong_value"):
            p = copy.deepcopy(self.packet)
            proof = p["account"]["storageProof"]
            if mode == "missing_account": p["account"]["accountProof"] = []
            elif mode == "missing_slot": proof.pop()
            elif mode == "empty_path": proof[-2]["proof"] = []
            elif mode == "duplicate_slot": proof[-1] = proof[0]
            elif mode == "unexpected_slot": proof[0]["key"] = hx(b"\xff" * 32)
            elif mode == "wrong_value": proof[0]["value"] = "0x0"
            with self.subTest(mode=mode): self.check_rejected(p)

    def test_random_proof_byte_mutations(self):
        rng = random.Random(666302)
        for i in range(256):
            p = copy.deepcopy(self.packet)
            nodes = (p["account"]["accountProof"] if i % 2 else
                     rng.choice(p["account"]["storageProof"])["proof"])
            index = rng.randrange(len(nodes))
            node = bytearray.fromhex(nodes[index][2:])
            node[rng.randrange(len(node))] ^= 1 << rng.randrange(8)
            nodes[index] = hx(node)
            with self.subTest(mutation=i): self.check_rejected(p)

    def test_extraneous_and_duplicate_nodes(self):
        for kind in ("extra", "duplicate"):
            p = copy.deepcopy(self.packet)
            nodes = p["account"]["accountProof"]
            nodes.append(nodes[0] if kind == "duplicate" else p["account"]["storageProof"][0]["proof"][0])
            self.check_rejected(p)

    def test_proof_order_is_not_trusted(self):
        p = copy.deepcopy(self.packet)
        p["account"]["accountProof"].reverse()
        for row in p["account"]["storageProof"]: row["proof"].reverse()
        self.assertEqual(verify(encode(p), self.policy, self.now).values(), self.words)

    def test_empty_trie_absence_and_missing_nonempty(self):
        d = ProofDecoder(True)
        self.assertEqual(d.prove(BLANK_NODE_HASH, b"\0" * 32, []), b"")
        with self.assertRaises(Rejected): d.prove(b"\1" * 32, b"\0" * 32, [])

    def test_rlp_path_and_shape_rejection(self):
        bad = [b"", b"\xc1", b"\x81\x00", rlp.encode([b"\x40", b"v"]),
               rlp.encode([b"\x01", b"v"]), rlp.encode([b"\x00", b"\0" * 32]),
               rlp.encode([b"\x10", b"\1"]), rlp.encode([b"x"] * 3),
               rlp.encode([b"x"] * 17), rlp.encode([b"\x20", []])]
        for value in bad:
            for shared in (False, True):
                with self.assertRaises(Rejected): ProofDecoder(shared).decode(hx(value))

    def test_inline_and_extension_nodes(self):
        # Dense nearby secure keys exercise extension and embedded branch/leaf nodes.
        pairs = {b"\0" * 31 + bytes([x]): bytes([x + 1]) for x in range(8)}
        tree = make_trie(pairs)
        for key in list(pairs) + [b"\0" * 31 + b"\x09", b"\xff" * 32]:
            nodes = [hx(rlp.encode(n)) for n in tree.get_proof(key)]
            for shared in (False, True):
                self.assertEqual(ProofDecoder(shared).prove(tree.root_hash, key, nodes), pairs.get(key, b""))

    def test_input_limits_and_canonical_json(self):
        for raw in [b"{" * 3000, b" " * (2 * 1024 * 1024 + 1), b"{\"x\":1,\"x\":2}",
                    b"{\"x\":NaN}", b"[]", b"\xff", b"[" * 2000 + b"]" * 2000]:
            with self.assertRaises(Rejected): load_packet(raw)
        for invalid in [True, 1, "0x01", "0x", "0X1", "0x" + "f" * 65]:
            p = copy.deepcopy(self.packet)
            p["account"]["nonce"] = invalid
            self.check_rejected(p)
        for value in [None, [self.packet["account"]["accountProof"][0]] * 66, ["0x" + "00" * 2049]]:
            p = copy.deepcopy(self.packet)
            p["account"]["accountProof"] = value
            self.check_rejected(p)

    def test_root_valid_semantic_inconsistency(self):
        cases = [{"position": 2**128 - 1}, {"time_fee": 0},
                 {"time_fee": ((10**18 // 4 + 1) << 128) | self.now},
                 {"time_fee": self.now + 1}, {"lltv": 10**18},
                 {"loan_token": 0}, {"oracle": 2**160}, {"borrow": 2**128 - 1}]
        for overrides in cases:
            p, policy, _ = make_case(666301, overrides)
            with self.subTest(overrides=overrides): self.check_rejected(p, policy)

    def test_real_historical_header_and_missing_witness(self):
        h = json.loads((ROOT / "fixtures/historical-header-26210229.json").read_text())["response"]["result"]
        a = Anchor(1, 26210229, bytes.fromhex(h["hash"][2:]), int(h["timestamp"], 16), "historical_observation")
        self.assertEqual(hx(verify_header(h, a)), h["stateRoot"])
        p = copy.deepcopy(self.packet)
        p.update(header=h, blockHash=h["hash"])
        p["account"]["accountProof"] = []
        self.check_rejected(p, replace(self.policy, anchor=a), now=a.timestamp)

    def test_gateway_invalid_input_revokes_previous_ticket(self):
        g = Gateway(self.policy)
        t = g.ingest(encode(self.packet), self.now)
        self.assertFalse(g.authorize(t, self.now)["commercial_admission"])
        with self.assertRaises(Rejected): g.ingest(b"{}", self.now)
        with self.assertRaises(Rejected): g.facts(t, self.now)

    def test_gateway_reorg_reset_and_stale_ticket(self):
        g = Gateway(self.policy)
        t = g.ingest(encode(self.packet), self.now)
        # Same height with another pinned hash; no implicit canonical selection.
        g.reset(replace(self.policy, anchor=replace(self.policy.anchor, block_hash=b"\1" * 32)))
        with self.assertRaises(Rejected): g.facts(t, self.now)
        with self.assertRaises(Rejected): g.ingest(encode(self.packet), self.now)
        g.reset(self.policy)
        t = g.ingest(encode(self.packet), self.now)
        new = g.ingest(encode(self.packet), self.now)
        self.assertNotEqual(t.epoch, new.epoch)
        with self.assertRaises(Rejected): g.authorize(t, self.now)
        # Conservative: any invalid ticket also drops the current snapshot.
        with self.assertRaises(Rejected): g.authorize(new, self.now)

    def test_gateway_expiry_clock_and_thread_confinement(self):
        g = Gateway(self.policy)
        for when in (self.now + 31, self.now - 1):
            t = g.ingest(encode(self.packet), self.now)
            with self.assertRaises(Rejected): g.facts(t, when)
            with self.assertRaises(Rejected): g.facts(t, self.now)
        caught = []
        def foreign_thread():
            try: g.ingest(encode(self.packet), self.now)
            except Rejected: caught.append(True)
        th = threading.Thread(target=foreign_thread)
        th.start(); th.join()
        self.assertEqual(caught, [True])

    def test_unchanged_rust_math_conditional_only(self):
        path = os.environ.get("NQC_R1_EVAL")
        self.assertTrue(path, "NQC_R1_EVAL is required; this integration must not silently skip")
        worker = MathWorker(path)
        try:
            g = Gateway(self.policy)
            for price in (10**34, 10**36, 10**38):
                t = g.ingest(encode(self.packet), self.now)
                prediction = g.scenario(t, self.now, price, worker)
                v = self.words
                shares = v["position"] % 2**128
                denominator = (v["borrow"] >> 128) + 1000000
                debt = (shares * ((v["borrow"] % 2**128) + 1) + denominator - 1) // denominator
                cap = ((v["position"] >> 128) * price // 10**36) * v["lltv"] // 10**18
                self.assertEqual((prediction.debt, prediction.capacity, prediction.eligible_if_assumptions_hold),
                                 (debt, cap, debt > cap))
                self.assertFalse(prediction.commercial_admission)
                self.assertIsNone(g.authorize(t, self.now)["observed_candidate"])
            p, policy, _ = make_case(666301, {"time_fee": (10**17 << 128) | (self.now - 1)})
            g.reset(policy)
            t = g.ingest(encode(p), self.now)
            with self.assertRaises(Rejected): g.scenario(t, self.now, 10**36, worker)
            with self.assertRaises(Rejected): g.facts(t, self.now)
        finally:
            worker.close()


if __name__ == "__main__":
    unittest.main()
