"""Independent HexaryTrie synthetic fixtures, never historical evidence."""
import rlp
from trie import HexaryTrie

import account_facts as facts


def fixture(records, address, requested=()):
    accounts = HexaryTrie(db={})
    stores = {}
    for addr, record in records.items():
        storage = HexaryTrie(db={})
        for key, value in record.get('storage', {}).items():
            if value:
                storage[facts.v.k256(key.to_bytes(32, 'big'))] = rlp.encode(value)
        stores[addr] = storage
        accounts[facts.v.k256(bytes.fromhex(addr[2:]))] = rlp.encode([
            record.get('nonce', 1), record.get('balance', 0), storage.root_hash,
            facts.v.k256(record.get('code', b''))])
    record = records.get(address)
    storage = stores.get(address, HexaryTrie(db={}))
    key = facts.v.k256(bytes.fromhex(address[2:]))
    proof = {
        'address': address, 'nonce': hex(record.get('nonce', 1) if record is not None else 0),
        'balance': hex(record.get('balance', 0) if record is not None else 0),
        'storageHash': '0x' + storage.root_hash.hex(),
        'codeHash': '0x' + facts.v.k256(record.get('code', b'') if record is not None else b'').hex(),
        'accountProof': ['0x' + rlp.encode(n).hex() for n in accounts.get_proof(key)],
        'storageProof': [{'key': hex(slot), 'value': hex(record.get('storage', {}).get(slot, 0) if record is not None else 0),
                          'proof': ['0x' + rlp.encode(n).hex() for n in
                                    storage.get_proof(facts.v.k256(slot.to_bytes(32, 'big')))]}
                         for slot in requested],
    }
    return '0x' + accounts.root_hash.hex(), proof


def address(number):
    return '0x' + number.to_bytes(20, 'big').hex()


def absence_shape_fixtures():
    """Deterministically pick addresses giving three real trie non-inclusion paths."""
    target = facts.FILTERED_ACCOUNT
    prefix = facts.v.k256(bytes.fromhex(target[2:]))[0] >> 4
    groups = {}
    for i in range(1, 257):
        addr = address(i)
        digit = facts.v.k256(bytes.fromhex(addr[2:]))[0] >> 4
        if digit != prefix:
            groups.setdefault(digit, []).append(addr)
    keys = sorted(groups)
    assert len(keys) >= 2 and len(groups[keys[0]]) >= 2
    a, b = groups[keys[0]][:2]
    c = groups[keys[1]][0]
    return {
        'leaf_divergence': fixture({a: {'nonce': 1}}, target),
        'empty_branch_child': fixture({a: {'nonce': 1}, c: {'nonce': 1}}, target),
        'extension_divergence': fixture({a: {'nonce': 1}, b: {'nonce': 1}}, target),
    }
