"""Offline raw-trie write-coverage experiment. NOT an EVM/Nitro replay engine.

All published cases are synthetic. No network, automatic node retrieval, RPC
requests, credential handling, signing, broadcasting or account-state admission.
"""
from pathlib import Path
import sys

import rlp
from trie import HexaryTrie
from trie.exceptions import MissingTrieNode

PREVIOUS = Path(__file__).resolve().parent.parent / 'nqc-037-historical-state'
sys.path.insert(0, str(PREVIOUS / 'src'))
import verify as v
import storage_proof as mpt


def key_for_slot(slot):
    return v.k256(v.data_hex(v.slot(slot), 32))


def build(records):
    db = {}
    trie = HexaryTrie(db)
    for key, value in records.items():
        trie[key] = value
    return trie, db


def read_proof(trie, key):
    return [rlp.encode(node) for node in trie.get_proof(key)]


def trial(root, key, proof, operation, value=None, extra_nodes=()):
    """Try ONE raw-trie operation in a disposable DB after validating its read.

Missing update nodes are returned as blockers, never fetched or treated as 0.
`extra_nodes` contains (expected_hash, encoded_node) pairs from a separate source.
Hash matching binds their bytes, not that source's chain identity or finality.
No mutated DB or tentative root is returned if the attempt is incomplete.
"""
    v.require(operation in ('set', 'delete'), 'Unknown operation')
    v.require(value is None if operation == 'delete' else isinstance(value, bytes) and bool(value),
              'Set needs nonempty bytes; delete takes no value')
    old = mpt.trie_value(root, key, proof)
    db = {v.k256(node): node for node in proof}
    for expected_hash, node in extra_nodes:
        v.require(isinstance(expected_hash, bytes) and len(expected_hash) == 32
                  and isinstance(node, bytes) and v.k256(node) == expected_hash,
                  'Extra node hash mismatch')
        db[expected_hash] = node
    trie = HexaryTrie(db, root_hash=root)
    result = {
        'read_verified_relative_to_root': True,
        'old_value': None if old is None else '0x' + old.hex(),
        'new_root': None, 'missing_node_hash': None,
        'scope': 'one raw-trie operation only; no EVM or account/storage cascade',
        'historical_position_authenticated': False, 'nitro_replayed': False,
        'complete_parent_witness': False, 'commercial_admission': False,
    }
    try:
        if operation == 'delete':
            trie.delete(key)
        else:
            trie[key] = value
    except MissingTrieNode as exc:
        result.update(status='WRITE_BLOCKED_MISSING_NODE',
                      missing_node_hash='0x' + bytes(exc.missing_node_hash).hex())
        return result
    result.update(status='RAW_TRIE_OPERATION_COMPLETED', new_root='0x' + trie.root_hash.hex())
    return result


def demonstration():
    # Real storage-key hashing, but entirely invented values and trie root.
    a, b = key_for_slot(9), key_for_slot(13)
    records = {a: rlp.encode(77), b: rlp.encode(88)}
    full, db = build(records)
    root = full.root_hash
    proof = read_proof(full, a)
    blocked = trial(root, a, proof, 'delete')
    v.require(blocked['status'] == 'WRITE_BLOCKED_MISSING_NODE', 'Fixture did not require extra node')
    missing = bytes.fromhex(blocked['missing_node_hash'][2:])
    # Available ONLY because this experiment generated the complete synthetic trie.
    extra = db[missing]
    completed = trial(root, a, proof, 'delete', extra_nodes=[(missing, extra)])
    reference, _ = build({b: records[b]})
    # Independent one-leaf root: even 64-nibble path, leaf prefix 0x20.
    direct_root = v.k256(mpt.rlp_encode([b'\x20' + b, records[b]]))
    v.require(completed['new_root'] == '0x' + reference.root_hash.hex() == '0x' + direct_root.hex(),
              'Partial/full/direct single-leaf roots disagree')
    updated = trial(root, a, proof, 'set', rlp.encode(99))
    updated_reference, _ = build({a: rlp.encode(99), b: records[b]})
    v.require(updated['new_root'] == '0x' + updated_reference.root_hash.hex(), 'Update root mismatch')
    return {
        'evidence_class': 'SYNTHETIC; not historical Robinhood state',
        'synthetic_root': '0x' + root.hex(), 'synthetic_slot_values': {'9': 77, '13': 88},
        'read_proof': ['0x' + node.hex() for node in proof],
        'read_proof_nodes': len(proof), 'delete_with_read_proof_only': blocked,
        'additional_node_hash': '0x' + missing.hex(), 'additional_node_bytes': '0x' + extra.hex(),
        'additional_node_was_in_read_proof': extra in proof,
        'delete_with_added_node': completed,
        'full_reference_root': '0x' + reference.root_hash.hex(),
        'direct_single_leaf_root': '0x' + direct_root.hex(),
        'replace_value_with_read_proof_only': updated,
        'rpc_requests_sent': 0, 'historical_proofs_acquired': 0, 'commercial_admission': False,
    }
