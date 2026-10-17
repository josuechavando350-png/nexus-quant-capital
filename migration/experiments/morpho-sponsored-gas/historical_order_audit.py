"""Offline transaction-trie reconstruction, without signing or broadcasting.

Verifies inclusion/order against B's pinned header, not execution, receipts,
sender recovery, consensus finality, or the missing pretransaction state.
"""
from collections import Counter
import json
from evm_hash import keccak256
from historical_rpc_audit import data, quantity, rlp, load, verify_header, HASH_B, TX_B, PREFIX_B


def encoded_transaction(tx):
    kind = quantity(tx['type'])
    target = data(tx['to'],20) if tx['to'] else b''
    tail = [quantity(tx['value']),data(tx['input'])]
    if kind == 0:
        values = [quantity(tx[k]) for k in ('nonce','gasPrice','gas')]+[target]+tail
        encoded = rlp(values+[quantity(tx[k]) for k in ('v','r','s')])
    elif kind in (2,3,4):
        values = [quantity(tx[k]) for k in ('chainId','nonce','maxPriorityFeePerGas','maxFeePerGas','gas')]
        access = [[data(a['address'],20),[data(k,32) for k in a['storageKeys']]] for a in tx['accessList']]
        values += [target]+tail+[access]
        if kind == 3:
            values += [quantity(tx['maxFeePerBlobGas']),[data(h,32) for h in tx['blobVersionedHashes']]]
        if kind == 4:
            values += [[[quantity(a['chainId']),data(a['address'],20),quantity(a['nonce']),
                         quantity(a['yParity']),quantity(a['r']),quantity(a['s'])]
                        for a in tx['authorizationList']]]
        parity = quantity(tx['yParity'])
        if parity not in (0,1): raise ValueError('invalid transaction parity')
        encoded = bytes([kind])+rlp(values+[parity,quantity(tx['r']),quantity(tx['s'])])
    else:
        raise ValueError('unsupported transaction type; no guessed encoding')
    if '0x'+keccak256(encoded).hex() != tx['hash']:
        raise ValueError('transaction byte hash mismatch')
    return encoded


def nibbles(raw):
    return tuple(v for b in raw for v in (b >> 4, b & 15))


def compact(path, leaf):
    odd = len(path) % 2
    digits = (2*int(leaf)+odd,) + (() if odd else (0,)) + path
    return bytes(16*digits[i]+digits[i+1] for i in range(0,len(digits),2))


def trie_root(pairs):
    """Batch-only hexary MPT: short children embedded, long children hashed."""
    if len({key for key,value in pairs}) != len(pairs):
        raise ValueError('duplicate trie key')
    if not pairs: return keccak256(rlp(b''))
    rows = [(nibbles(key), value) for key,value in pairs]
    def reference(node):
        encoded = rlp(node)
        return node if len(encoded) < 32 else keccak256(encoded)
    def build(items):
        if len(items) == 1:
            key,value = items[0]
            return [compact(key,True),value]
        common = 0
        while all(len(key)>common and key[common] == items[0][0][common] for key,_ in items):
            common += 1
        if common:
            return [compact(items[0][0][:common],False),
                    reference(build([(key[common:],v) for key,v in items]))]
        node = [b'']*17
        for digit in range(16):
            group = [(key[1:],v) for key,v in items if key and key[0] == digit]
            if group: node[digit] = reference(build(group))
        for key,value in items:
            if not key: node[16] = value
        return node
    return keccak256(rlp(build(rows)))


def audit(block=None):
    block = load('b-block.json.gz')['response']['result'] if block is None else block
    verify_header(block,HASH_B)
    txs = block['transactions']
    pairs = []
    for index,tx in enumerate(txs):
        if (quantity(tx['transactionIndex']) != index or tx['blockHash'] != HASH_B
                or quantity(tx['blockNumber']) != 26190955):
            raise ValueError('transaction index/block metadata mismatch')
        pairs.append((rlp(index),encoded_transaction(tx)))
    root = '0x'+trie_root(pairs).hex()
    if root != block['transactionsRoot']:
        raise ValueError('transaction trie root mismatch: omitted, changed or reordered bytes')
    if len(txs) != 602 or txs[0]['hash'] != PREFIX_B or txs[1]['hash'] != TX_B:
        raise ValueError('unexpected B prefix')
    return {'status':'TRANSACTION_ORDER_COMMITTED_TO_PINNED_HEADER', 'block_hash':HASH_B,
            'transaction_count':len(txs), 'transaction_types':dict(Counter(t['type'] for t in txs)),
            'transactions_root_verified':root, 'preceding_transaction_hashes':[txs[0]['hash']],
            'target_transaction_index':1, 'target_transaction_hash':TX_B,
            'prefix_effects_known':False, 'pretransaction_state_available':False,
            'receipts_trie_checked':False, 'consensus_finality_verified':False,
            'fork_reproduced':False, 'certified_profit':False}


if __name__ == '__main__':
    print(json.dumps(audit(),indent=2))
    raise SystemExit(2)
