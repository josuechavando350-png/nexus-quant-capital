"""One read-only py-trie traversal, reusing strictly validated decoded nodes.

The cache is owned by one packet decoder. Each proof gets a fresh db/used set;
neither another storage path nor an inline sibling can satisfy proof coverage.
No change to py-trie's key/path traversal or Keccak/RLP validation algorithms.
"""
import rlp
from eth_hash.auto import keccak
from trie import HexaryTrie
from trie.constants import BLANK_NODE_HASH
from state_evidence import (Rejected, require, data, _node, MAX_NODE,
                            MAX_PROOF_NODES)


class _ReadOnlyTrie(HexaryTrie):
    def __init__(self, decoded_db, root_hash):
        super().__init__(decoded_db, root_hash=root_hash)
        self.used = set()

    def get_node(self, pointer):
        # py-trie passes embedded children as lists. They are already validated
        # recursively by _node; only traversal, not parsing, marks them as used.
        if type(pointer) is list:
            self.used.add(keccak(rlp.encode(pointer)))
            return pointer
        if pointer == b"" or pointer == BLANK_NODE_HASH:
            return b""
        require(type(pointer) is bytes and len(pointer) == 32, "trie pointer width")
        node = self.db[pointer]  # Missing pointer must reject, never consult cache.
        self.used.add(pointer)
        return node


class ProofDecoder:
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
        result = (keccak(raw), decoded)
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
            digest, decoded = self.decode(item)
            require(digest not in db, "duplicate proof node")
            db[digest] = decoded
        try:
            tree = _ReadOnlyTrie(db, root_hash=root)
            value = tree[key]
        except Exception as e:
            raise Rejected("incomplete or inconsistent trie path") from e
        require(set(db) <= tree.used, "extraneous proof node")
        return value
