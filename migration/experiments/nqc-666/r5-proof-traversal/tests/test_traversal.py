import ast
import copy
import importlib.util
import json
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
R3 = ROOT.parent / "r3-state-evidence"
R4 = ROOT.parent / "r4-stable-ingress"
sys.path[:0] = [str(ROOT / "python"), str(R3 / "src"), str(R3 / "scripts"), str(R4 / "python")]
import rlp
from eth_hash.auto import keccak
from trie.constants import BLANK_NODE_HASH
from fixtures import make_trie, hx, policy_from
import state_evidence as baseline
import state_evidence_fast as fast
from proof_traversal import ProofDecoder
from fast_gateway import StableGateway


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def load_tests(loader, tests, pattern):
    # Dependency injection is confined to isolated TEST modules. Runtime module
    # globals and historical test files are never patched or rewritten.
    for suffix, verifier, decoder in (("baseline", baseline.verify, baseline.ProofDecoder),
                                      ("fast", fast.verify, ProofDecoder)):
        m = module("r5_evidence_" + suffix, R3 / "tests/test_evidence.py")
        m.verify, m.ProofDecoder = verifier, decoder
        tests.addTests(loader.loadTestsFromTestCase(m.EvidenceTests))
    from stable_gateway import StableGateway as BaselineGateway
    for suffix, gateway in (("baseline", BaselineGateway), ("fast", StableGateway)):
        m = module("r5_stability_" + suffix, R4 / "tests/test_stability.py")
        m.StableGateway = gateway
        tests.addTests(loader.loadTestsFromTestCase(m.StabilityTests))
    return tests


class TraversalTests(unittest.TestCase):
    def compare(self, root, key, nodes):
        results = []
        for decoder in (baseline.ProofDecoder, ProofDecoder):
            for shared in (False, True):
                try: results.append((True, decoder(shared).prove(root, key, nodes)))
                except baseline.Rejected: results.append((False, None))
        self.assertTrue(all(r == results[0] for r in results), (root.hex(), key.hex(), results))
        return results[0]

    def test_unchanged_semantic_and_guard_bodies(self):
        old = (R3 / "src/state_evidence.py").read_text()
        new = (ROOT / "python/state_evidence_fast.py").read_text()
        self.assertEqual(old[old.index("def verify(raw,"):], new[new.index("def verify(raw,"):])
        def classes(path):
            return [ast.dump(n) for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef)]
        self.assertEqual(classes(R4 / "python/stable_gateway.py"), classes(ROOT / "python/fast_gateway.py"))

    def test_all_facts_identical_including_unknown_fields(self):
        for row in json.loads((R3 / "fixtures/synthetic-index.json").read_text()):
            raw = (R3 / "fixtures" / row["packet"]).read_bytes()
            policy = policy_from(row["policy"])
            for shared in (False, True):
                self.assertEqual(baseline.verify(raw, policy, policy.anchor.timestamp, shared=shared),
                                 fast.verify(raw, policy, policy.anchor.timestamp, shared=shared))

    def test_inline_sibling_is_not_used_by_parsing(self):
        pairs = {b"\0" * 31 + bytes([i]): bytes([i + 1]) for i in range(8)}
        tree = make_trie(pairs)
        key = next(iter(pairs))
        path = [hx(rlp.encode(n)) for n in tree.get_proof(key)]
        sibling = hx(rlp.encode(tree.get_proof(b"\0" * 31 + b"\x07")[-1]))
        self.assertNotIn(sibling, path)
        self.assertLess(len(bytes.fromhex(sibling[2:])), 32)
        self.assertEqual(self.compare(tree.root_hash, key, path), (True, pairs[key]))
        self.assertEqual(self.compare(tree.root_hash, key, path + [sibling]), (False, None))
        # Omitted inline body is still available from its parent, and is valid.
        reduced = [n for n in path if len(bytes.fromhex(n[2:])) >= 32]
        self.assertEqual(self.compare(tree.root_hash, key, reduced), (True, pairs[key]))

    def test_packet_cache_never_supplies_missing_proof(self):
        pairs = {keccak(bytes([i])): b"x" * 40 for i in range(8)}
        tree = make_trie(pairs)
        key = next(iter(pairs))
        path = [hx(rlp.encode(n)) for n in tree.get_proof(key)]
        decoder = ProofDecoder(True)
        decoder.prove(tree.root_hash, key, path)
        for i in range(len(path)):
            with self.assertRaises(baseline.Rejected):
                decoder.prove(tree.root_hash, key, path[:i] + path[i+1:])
        self.assertEqual(decoder.prove(tree.root_hash, key, path), pairs[key])
        with self.assertRaises(baseline.Rejected): decoder.prove(BLANK_NODE_HASH, key, path)

    def test_traversal_does_not_mutate_cached_nodes(self):
        pairs = {b"\0" * 31 + bytes([i]): bytes([i + 1]) for i in range(8)}
        tree = make_trie(pairs)
        decoder = ProofDecoder(True)
        for key in pairs:
            nodes = [hx(rlp.encode(n)) for n in tree.get_proof(key)]
            for n in nodes: decoder.decode(n)
            before = copy.deepcopy(decoder.cache)
            self.assertEqual(decoder.prove(tree.root_hash, key, nodes), pairs[key])
            self.assertEqual(before, decoder.cache)

    def test_generated_tries_differential(self):
        rng = random.Random(666501)
        compared = 0
        for size in (1, 2, 8, 32, 128):
            for shape in ("random", "prefix"):
                pairs = {}
                for i in range(size):
                    key = rng.randbytes(32) if shape == "random" else b"\0" * 30 + i.to_bytes(2, "big")
                    pairs[key] = rng.randbytes((i % 64) + 1)
                tree = make_trie(pairs)
                keys = list(pairs) + [rng.randbytes(32) for _ in range(16)]
                keys += [b"\0" * 30 + (size + 2).to_bytes(2, "big")]
                for key in keys:
                    nodes = [hx(rlp.encode(n)) for n in tree.get_proof(key)]
                    self.assertEqual(self.compare(tree.root_hash, key, nodes), (True, pairs.get(key, b"")))
                    rng.shuffle(nodes)
                    variants = [nodes, nodes + nodes[:1]]
                    variants += [nodes[:j] + nodes[j+1:] for j in range(len(nodes))]
                    for proof in variants:
                        self.compare(tree.root_hash, key, proof)
                        compared += 1
        self.assertGreater(compared, 2000)
        print("deterministic trie differential variants:", compared)


if __name__ == "__main__": unittest.main()
