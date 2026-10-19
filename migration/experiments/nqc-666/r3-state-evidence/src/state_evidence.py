"""Offline, bounded EIP-1186 verification against an explicitly pinned header.

This module does NOT establish consensus, chain identity, oracle execution,
pre-transaction state, or commercial authorization. No network or signing code.
"""
from dataclasses import dataclass
import json
import re

import rlp
from eth_hash.auto import keccak
from trie import HexaryTrie
from trie.constants import BLANK_NODE_HASH

MAX_PACKET = 2 * 1024 * 1024
MAX_NODE = 2048
MAX_PROOF_NODES = 65
MAX_U256 = 2**256 - 1
WAD = 10**18
LAYOUT = "morpho-blue@9cf6d5b844625ba108e36d1cf911f5d2faf7c136"
HEADER_FIELDS = (
    ("parentHash", 32), ("sha3Uncles", 32), ("miner", 20),
    ("stateRoot", 32), ("transactionsRoot", 32), ("receiptsRoot", 32),
    ("logsBloom", 256), ("difficulty", None), ("number", None),
    ("gasLimit", None), ("gasUsed", None), ("timestamp", None),
    ("extraData", -1), ("mixHash", 32), ("nonce", 8),
    ("baseFeePerGas", None), ("withdrawalsRoot", 32),
    ("blobGasUsed", None), ("excessBlobGas", None),
    ("parentBeaconBlockRoot", 32), ("requestsHash", 32),
)


class Rejected(ValueError):
    """Fail-closed validation error; no partial verified result is returned."""


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def data(value, size=None):
    require(type(value) is str and len(value) <= MAX_PACKET,
            "data type/size")
    require(re.fullmatch(r"0x(?:[0-9a-f]{2})*", value) is not None,
            "noncanonical data hex")
    result = bytes.fromhex(value[2:])
    require(size is None or len(result) == size, "data width")
    return result


def quantity(value):
    require(type(value) is str and len(value) <= 66, "quantity type/size")
    require(re.fullmatch(r"0x(?:0|[1-9a-f][0-9a-f]*)", value) is not None,
            "noncanonical quantity")
    return int(value, 16)


def uint_bytes(value):
    require(type(value) is bytes and len(value) <= 32, "RLP integer width")
    require(not value or value[0] != 0, "nonminimal RLP integer")
    return int.from_bytes(value, "big")


def exact(obj, keys):
    require(type(obj) is dict and set(obj) == set(keys), "schema keys")


def _pairs(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, "duplicate JSON key")
        result[k] = v
    return result


def load_packet(raw):
    require(type(raw) is bytes and len(raw) <= MAX_PACKET, "packet type/size")
    try:
        obj = json.loads(raw, object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(Rejected("JSON constant")))
    except (UnicodeError, ValueError, RecursionError) as e:
        raise Rejected("JSON parse: " + str(e)[:120]) from e
    require(type(obj) is dict, "packet object")
    return obj


def _child(child, depth):
    if type(child) is bytes:
        require(len(child) in (0, 32), "child reference width")
    else:
        require(type(child) is list and len(rlp.encode(child)) < 32,
                "noncanonical embedded child")
        _node(child, depth + 1)


def _node(node, depth=0):
    require(depth <= 64 and type(node) is list, "node type/depth")
    if len(node) == 17:
        for child in node[:16]:
            _child(child, depth)
        require(type(node[16]) is bytes, "branch value type")
    elif len(node) == 2:
        path = node[0]
        require(type(path) is bytes and 1 <= len(path) <= 33, "compact path width")
        flag = path[0] >> 4
        require(flag <= 3 and (flag & 1 or path[0] & 15 == 0), "compact path flag/padding")
        nibbles = (len(path) - 1) * 2 + (flag & 1)
        require(nibbles <= 64, "compact path length")
        if flag < 2:
            require(nibbles > 0 and node[1] != b"", "empty extension")
            _child(node[1], depth)
        else:
            require(type(node[1]) is bytes, "leaf value type")
    else:
        raise Rejected("node arity")


class ProofDecoder:
    """The optimization is packet-local deduplication, never a cross-root cache."""
    def __init__(self, shared):
        self.shared = shared
        self.cache = {}
        self.decoded = 0
        self.references = 0

    def decode(self, encoded):
        require(type(encoded) is str and len(encoded) <= 2 + MAX_NODE * 2,
                "proof node size/type")
        self.references += 1
        if self.shared and encoded in self.cache:
            return self.cache[encoded]
        raw = data(encoded)
        try:
            decoded = rlp.decode(raw, strict=True)
            require(rlp.encode(decoded) == raw, "noncanonical RLP")
            _node(decoded)
        except (ValueError, TypeError, rlp.DecodingError, RecursionError) as e:
            raise Rejected("proof node encoding") from e
        result = (keccak(raw), raw)
        self.decoded += 1
        if self.shared:
            self.cache[encoded] = result
        return result

    def prove(self, root, key, nodes):
        require(type(nodes) is list and len(nodes) <= MAX_PROOF_NODES, "proof length/type")
        require(len(root) == len(key) == 32, "root/key width")
        if not nodes:
            require(root == BLANK_NODE_HASH, "missing proof")
            return b""
        db = {}
        for item in nodes:
            digest, raw = self.decode(item)
            require(digest not in db, "duplicate proof node")
            db[digest] = raw
        try:
            tree = HexaryTrie(db, root_hash=root)
            value = tree[key]
            path = tree.get_proof(key)
        except Exception as e:
            # Dependency traversal/decoding exceptions are data rejection, not an authorization.
            raise Rejected("incomplete or inconsistent trie path") from e
        used = {keccak(rlp.encode(n)) for n in path}
        require(set(db) <= used, "extraneous proof node")
        return value


@dataclass(frozen=True)
class Anchor:
    chain: int
    number: int
    block_hash: bytes
    timestamp: int
    source: str


@dataclass(frozen=True)
class Policy:
    anchor: Anchor
    address: bytes
    code_hash: bytes
    market_id: bytes
    borrower: bytes
    max_age_s: int = 30
    layout: str = LAYOUT


def slots(market_id, borrower):
    require(type(market_id) is bytes and len(market_id) == 32, "market id width")
    require(type(borrower) is bytes and len(borrower) == 20, "borrower width")
    def mapping(key, slot):
        return int.from_bytes(keccak(key + slot.to_bytes(32, "big")), "big")
    position = mapping(borrower.rjust(32, b"\0"), mapping(market_id, 2))
    market = mapping(market_id, 3)
    params = mapping(market_id, 8)
    # Solidity 0.8 addition reverts rather than wrapping at MAX_U256.
    require(position < MAX_U256 and market <= MAX_U256 - 2 and params <= MAX_U256 - 4,
            "slot offset overflow")
    return dict(zip(("position", "supply", "borrow", "time_fee", "loan_token",
                     "collateral_token", "oracle", "irm", "lltv"),
                    (position + 1, market, market + 1, market + 2,
                     params, params + 1, params + 2, params + 3, params + 4)))


def verify_header(header, anchor):
    require(type(header) is dict, "header object")
    require(type(anchor.chain) is int and anchor.chain == 1, "configured chain")
    require(type(anchor.number) is int and anchor.number > 0, "anchor height")
    require(type(anchor.timestamp) is int and anchor.timestamp > 0, "anchor time")
    require(type(anchor.block_hash) is bytes and len(anchor.block_hash) == 32,
            "anchor hash")
    require(anchor.source in ("synthetic_fixture", "historical_observation"), "anchor provenance")
    require("hash" in header and data(header["hash"], 32) == anchor.block_hash, "header hash identity")
    values = []
    for name, width in HEADER_FIELDS:
        require(name in header, "unsupported/incomplete header schema")
        value = quantity(header[name]) if width is None else data(header[name], None if width == -1 else width)
        if name == "extraData":
            require(len(value) <= 32, "extraData width")
        values.append(value)
    require(keccak(rlp.encode(values)) == anchor.block_hash, "header digest")
    require(quantity(header["number"]) == anchor.number and
            quantity(header["timestamp"]) == anchor.timestamp, "anchor number/time")
    require(quantity(header["gasUsed"]) <= quantity(header["gasLimit"]), "gas header consistency")
    # A matching header hash does not prove PoS consensus, ancestry, or chain identity.
    return data(header["stateRoot"], 32)


@dataclass(frozen=True)
class Facts:
    anchor: Anchor
    address: bytes
    market_id: bytes
    borrower: bytes
    code_hash: bytes
    storage_root: bytes
    # Named, immutable words; no mutable dict escapes the verifier.
    words: tuple
    nodes_decoded: int
    node_references: int
    canonicality: str = "unknown"
    layout_assurance: str = "explicit_policy_assumption"
    oracle_price: None = None
    observed_eligibility: None = None
    commercial_admission: bool = False

    def values(self):
        return dict(self.words)


def verify(raw, policy, now_s, *, shared=True):
    """All checks run on both paths; shared=True only deduplicates node decoding."""
    try:
        return _verify(raw, policy, now_s, shared)
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError,
            rlp.DecodingError) as e:
        raise Rejected("malformed evidence") from e


def _verify(raw, policy, now_s, shared):
    p = load_packet(raw)
    exact(p, ("schema", "chainId", "blockHash", "statePoint", "header", "account", "code"))
    a = policy.anchor
    require(type(now_s) is int and type(policy.max_age_s) is int and policy.max_age_s > 0,
            "clock/expiry type")
    require(a.timestamp <= now_s <= a.timestamp + policy.max_age_s, "future/stale evidence")
    require(p["schema"] == "nqc666-eip1186-v1" and p["statePoint"] == "end_of_block",
            "schema/state point")
    require(quantity(p["chainId"]) == a.chain and data(p["blockHash"], 32) == a.block_hash,
            "packet identity")
    require(policy.layout == LAYOUT, "unsupported layout")
    require(type(policy.address) is bytes and len(policy.address) == 20 and any(policy.address),
            "configured account")
    require(type(policy.code_hash) is bytes and len(policy.code_hash) == 32, "configured code hash")
    root = verify_header(p["header"], a)
    account = p["account"]
    exact(account, ("address", "nonce", "balance", "storageHash", "codeHash", "accountProof", "storageProof"))
    require(data(account["address"], 20) == policy.address, "account identity")
    decoder = ProofDecoder(shared)
    leaf = decoder.prove(root, keccak(policy.address), account["accountProof"])
    require(bool(leaf), "account absent")
    acc = rlp.decode(leaf, strict=True)
    require(type(acc) is list and len(acc) == 4, "account RLP schema")
    require(uint_bytes(acc[0]) == quantity(account["nonce"]) and
            uint_bytes(acc[1]) == quantity(account["balance"]), "account metadata")
    require(type(acc[2]) is bytes and len(acc[2]) == 32 and
            type(acc[3]) is bytes and len(acc[3]) == 32, "account roots")
    require(acc[2] == data(account["storageHash"], 32) and
            acc[3] == data(account["codeHash"], 32) == policy.code_hash, "account code/storage identity")
    code = data(p["code"])
    require(0 < len(code) <= 24576 and keccak(code) == policy.code_hash, "runtime code digest/size")
    expected = slots(policy.market_id, policy.borrower)
    require(type(account["storageProof"]) is list and len(account["storageProof"]) == len(expected),
            "storage proof coverage")
    actual = {}
    for row in account["storageProof"]:
        exact(row, ("key", "value", "proof"))
        slot = int.from_bytes(data(row["key"], 32), "big")
        require(slot in expected.values() and slot not in actual, "unexpected/duplicate slot")
        v = decoder.prove(acc[2], keccak(slot.to_bytes(32, "big")), row["proof"])
        value = 0 if not v else uint_bytes(rlp.decode(v, strict=True))
        require(not v or value != 0, "noncanonical stored zero")
        require(value == quantity(row["value"]), "storage value metadata")
        actual[slot] = value
    words = {name: actual[slot] for name, slot in expected.items()}
    for name in ("loan_token", "collateral_token", "oracle", "irm"):
        require(words[name] < 2**160, "address padding")
    require(words["loan_token"] > 0 and words["collateral_token"] > 0 and words["oracle"] > 0,
            "uninitialized market params")
    require(0 < words["lltv"] < WAD, "LLTV range")
    encoded_params = b"".join(words[n].to_bytes(32, "big") for n in
                              ("loan_token", "collateral_token", "oracle", "irm", "lltv"))
    require(keccak(encoded_params) == policy.market_id, "market ID/params mismatch")
    require(words["position"] % 2**128 <= words["borrow"] >> 128, "position shares exceed market")
    require(0 < words["time_fee"] % 2**128 <= a.timestamp and
            words["time_fee"] >> 128 <= WAD // 4, "market time/fee")
    require(words["borrow"] % 2**128 <= words["supply"] % 2**128, "borrow exceeds supply")
    return Facts(a, policy.address, policy.market_id, policy.borrower, policy.code_hash,
                 acc[2], tuple(words.items()), decoder.decoded, decoder.references)
