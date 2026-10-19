"""Deterministic synthetic witness corpus. No market observations are invented.

Every py-trie root is checked against a separate sorted-key batch MPT builder.
The independent builder uses no trie library; hashing/RLP remain shared primitives.
"""
from dataclasses import asdict
import json
from pathlib import Path
import random
import sys

import rlp
from eth_hash.auto import keccak
from trie import HexaryTrie

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from state_evidence import Anchor, Policy, HEADER_FIELDS, slots


def hx(b):
    return "0x" + b.hex()


def packed_path(path, leaf):
    odd = len(path) % 2
    prefix = [2 * int(leaf) + odd] + ([] if odd else [0])
    n = prefix + list(path)
    return bytes((n[i] << 4) | n[i + 1] for i in range(0, len(n), 2))


def reference_root(pairs):
    """Batch construction, independent of py-trie's incremental insertion/proofs."""
    def ref(node):
        encoded = rlp.encode(node)
        return node if len(encoded) < 32 else keccak(encoded)

    def build(rows):
        if len(rows) == 1:
            return [packed_path(rows[0][0], True), rows[0][1]]
        prefix = 0
        while all(len(k) > prefix and k[prefix] == rows[0][0][prefix] for k, _ in rows):
            prefix += 1
        if prefix:
            return [packed_path(rows[0][0][:prefix], False),
                    ref(build([(k[prefix:], v) for k, v in rows]))]
        node = [b""] * 17
        for i in range(16):
            group = [(k[1:], v) for k, v in rows if k and k[0] == i]
            if group:
                node[i] = ref(build(group))
        for k, v in rows:
            if not k:
                node[16] = v
        return node

    rows = sorted((tuple(n for b in k for n in (b >> 4, b & 15)), v) for k, v in pairs.items())
    return keccak(rlp.encode(build(rows) if rows else b""))


def make_trie(pairs):
    tree = HexaryTrie({})
    for k, v in pairs.items():
        tree[k] = v
    assert tree.root_hash == reference_root(pairs)
    return tree


def make_case(seed, overrides=None, population=64):
    rng = random.Random(seed)
    timestamp = 1792215000 + seed % 1000
    address = rng.randbytes(20)
    borrower = rng.randbytes(20)
    params = [int.from_bytes(rng.randbytes(20), "big") for _ in range(3)] + [0, 86 * 10**16]
    words = dict(zip(("loan_token", "collateral_token", "oracle", "irm", "lltv"), params))
    assets = 1_000_000 * 10**6 + seed % 1000
    shares = assets * 10**6
    words.update(position=(rng.randrange(1, 10000) * 10**6 << 128) | rng.randrange(1, shares),
                 supply=((assets * 2 * 10**6) << 128) | (assets * 2),
                 borrow=(shares << 128) | assets,
                 time_fee=(10**17 << 128) | timestamp)
    words.update(overrides or {})
    market_id = keccak(b"".join(words[n].to_bytes(32, "big") for n in
                               ("loan_token", "collateral_token", "oracle", "irm", "lltv")))
    slot_map = slots(market_id, borrower)
    pairs = {keccak(slot_map[n].to_bytes(32, "big")): rlp.encode(v) for n, v in words.items() if v}
    for _ in range(population):
        pairs[keccak(rng.randbytes(32))] = rlp.encode(rng.getrandbits(256))
    storage = make_trie(pairs)
    # STOP is deliberately NOT Morpho bytecode. Only synthetic storage layout is modeled.
    code = b"\x00" + seed.to_bytes(4, "big")
    account_value = rlp.encode([1, 0, storage.root_hash, keccak(code)])
    accounts = {keccak(address): account_value}
    for _ in range(population):
        accounts[keccak(rng.randbytes(20))] = rlp.encode([0, rng.getrandbits(80),
                                                       keccak(rlp.encode(b"")), keccak(b"")])
    state = make_trie(accounts)
    header = {name: ("0x0" if width is None else hx(b"\0" * (0 if width == -1 else width)))
              for name, width in HEADER_FIELDS}
    header.update(stateRoot=hx(state.root_hash), number=hex(26210229 + seed % 1000),
                  timestamp=hex(timestamp), gasLimit=hex(30_000_000), gasUsed=hex(seed % 30000000),
                  parentHash=hx(rng.randbytes(32)), extraData=hx(b"NQC666_SYNTHETIC_ONLY"))
    encoded_header = [int(header[n], 16) if w is None else bytes.fromhex(header[n][2:])
                      for n, w in HEADER_FIELDS]
    block_hash = keccak(rlp.encode(encoded_header))
    header["hash"] = hx(block_hash)
    account = {"address": hx(address), "nonce": "0x1", "balance": "0x0",
               "storageHash": hx(storage.root_hash), "codeHash": hx(keccak(code)),
               "accountProof": [hx(rlp.encode(n)) for n in state.get_proof(keccak(address))],
               "storageProof": [{"key": hx(slot.to_bytes(32, "big")), "value": hex(words[name]),
                                 "proof": [hx(rlp.encode(n)) for n in storage.get_proof(keccak(slot.to_bytes(32, "big")))]}
                                for name, slot in slot_map.items()]}
    packet = {"schema": "nqc666-eip1186-v1", "chainId": "0x1", "blockHash": hx(block_hash),
              "statePoint": "end_of_block", "header": header, "account": account, "code": hx(code)}
    policy = Policy(Anchor(1, int(header["number"], 16), block_hash, timestamp, "synthetic_fixture"),
                    address, keccak(code), market_id, borrower)
    return packet, policy, words


def encode(packet):
    return json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()


def policy_json(policy):
    d = asdict(policy)
    d["anchor"]["block_hash"] = hx(policy.anchor.block_hash)
    for k in ("address", "code_hash", "market_id", "borrower"):
        d[k] = hx(getattr(policy, k))
    return d


def policy_from(d):
    d = dict(d)
    a = dict(d["anchor"])
    a["block_hash"] = bytes.fromhex(a["block_hash"][2:])
    d["anchor"] = Anchor(**a)
    for k in ("address", "code_hash", "market_id", "borrower"):
        d[k] = bytes.fromhex(d[k][2:])
    return Policy(**d)


def generate(out):
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for i in range(16):
        packet, policy, words = make_case(666301 + i, population=[0, 16, 64, 256][i % 4])
        path = out / f"synthetic-{i:02}.json"
        path.write_bytes(encode(packet) + b"\n")
        records.append({"packet": path.name, "policy": policy_json(policy), "words": words,
                        "seed": 666301 + i, "population": [0, 16, 64, 256][i % 4],
                        "independent_roots_equal": True})
    (out / "synthetic-index.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    generate(Path(sys.argv[1]))
