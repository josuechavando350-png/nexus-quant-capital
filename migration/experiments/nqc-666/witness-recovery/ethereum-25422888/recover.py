"""Recover one published Morpho proof; never certify a block or authorize trading.

Only the observed fixed-width branch-only capsule format is supported. No
upstream TypeScript/Noir code is executed. R5 validates the reconstructed nodes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

NQC = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(NQC / 'r3-state-evidence/src'),
                str(NQC / 'r5-proof-traversal/python')]
import rlp
from eth_hash.auto import keccak
from state_evidence import Rejected, require, exact, data, load_packet, slots
from proof_traversal import ProofDecoder

MAX_CAPSULE = 65536
MAX_RUNTIME_FILE = 2 + 24576 * 2 + 512  # bounded LF wrapping of a hex file
CASE_KEYS = ('schema', 'authority', 'chain_id_claim', 'block_number_claim',
             'state_root_claim', 'address', 'code_hash', 'market_id', 'borrower')


def decimal(value, bits):
    require(type(value) is str and 0 < len(value) <= 78, 'decimal type/size')
    require(re.fullmatch(r'0|[1-9][0-9]*', value) is not None, 'decimal encoding')
    number = int(value)
    require(number < 2**bits, 'integer overflow')
    return number


def array(value, size):
    require(type(value) is list and len(value) == size, 'array shape')
    return value


def limbs(value):
    return b''.join(decimal(v, 64).to_bytes(8, 'little') for v in array(value, 4))


def byte_array(value, size):
    return bytes(decimal(v, 8) for v in array(value, size))


def integer_field(obj, name, size):
    raw = byte_array(obj[name], size)
    length = decimal(obj[name + '_length'], 8)
    require(length <= size and not any(raw[length:]), 'integer padding/length')
    result = raw[:length]
    require(not result or result[0] != 0, 'integer not minimal')
    return result


def leaf_path(key, consumed):
    nibbles = [v for b in key for v in (b >> 4, b & 15)][consumed:]
    prefix = [3] if len(nibbles) % 2 else [2, 0]
    values = prefix + nibbles
    return bytes(values[i] * 16 + values[i + 1] for i in range(0, len(values), 2))


def reconstruct(capsule, kind, capacity, key, value):
    count = decimal(capsule[kind + '_node_length'], 8)
    require(count <= capacity, 'proof path capacity')
    result = []
    for index, node in enumerate(array(capsule[kind + '_nodes'], capacity)):
        exact(node, ('rows', 'row_exist', 'node_type'))
        require(node['node_type'] == '0', 'unsupported non-branch node')
        rows = [limbs(row) for row in array(node['rows'], 16)]
        exists = array(node['row_exist'], 16)
        require(all(type(flag) is bool for flag in exists), 'presence flag type')
        require(all(flag or not any(row) for flag, row in zip(exists, rows)),
                'hidden absent-row bytes')
        if index >= count:
            require(not any(exists) and not any(map(any, rows)), 'hidden padded node')
            continue
        require(sum(exists) >= 2, 'degenerate branch')
        result.append(rlp.encode([row if flag else b'' for row, flag in zip(rows, exists)] + [b'']))
    # The format omits the leaf. Rebuild its preimage and require the parent
    # reference/root to commit to that exact leaf via R5; this is not a new root.
    result.append(rlp.encode([leaf_path(key, count), value]))
    return ['0x' + node.hex() for node in result]


def recover(capsule_raw, runtime_file, case_raw):
    require(type(capsule_raw) is bytes and len(capsule_raw) <= MAX_CAPSULE, 'capsule size/type')
    require(type(case_raw) is bytes and len(case_raw) <= 4096, 'case size/type')
    require(type(runtime_file) is bytes and len(runtime_file) <= MAX_RUNTIME_FILE, 'runtime file size/type')
    capsule, case = load_packet(capsule_raw), load_packet(case_raw)
    exact(case, CASE_KEYS)
    require(case['schema'] == 'nqc666-partial-morpho-case-v1' and
            case['authority'] == 'UNAUTHENTICATED_SOURCE_PIN', 'case authority/schema')
    require(type(case['chain_id_claim']) is int and case['chain_id_claim'] == 1,
            'unsupported chain claim')
    require(type(case['block_number_claim']) is int and 0 < case['block_number_claim'] < 2**64,
            'block number claim')
    exact(capsule, ('account_nodes', 'account_node_length', 'storage_nodes',
                    'storage_node_length', 'account', 'slot', 'slot_key', 'root', 'block_number'))
    require(decimal(capsule['block_number'], 64) == case['block_number_claim'], 'block claim mismatch')
    account = capsule['account']
    exact(account, ('nonce', 'nonce_length', 'balance', 'balance_length',
                    'address', 'storage_hash', 'code_hash'))
    exact(capsule['slot'], ('value', 'value_length'))
    address = byte_array(account['address'], 20)
    require(address == data(case['address'], 20) and any(address), 'account address')
    root = limbs(capsule['root'])
    require(root == data(case['state_root_claim'], 32), 'root claim mismatch')
    storage_root, code_hash = limbs(account['storage_hash']), limbs(account['code_hash'])
    require(code_hash == data(case['code_hash'], 32), 'code hash pin')
    try:
        # The source hex file wraps its lines. Preserve it verbatim on disk;
        # only LF separators are removed for hex decoding (not arbitrary space).
        runtime_text = runtime_file.decode('ascii').replace('\n', '')
    except UnicodeError as error:
        raise Rejected('runtime text') from error
    runtime = data(runtime_text)
    require(0 < len(runtime) <= 24576 and keccak(runtime) == code_hash, 'runtime digest/size')
    market, borrower = data(case['market_id'], 32), data(case['borrower'], 20)
    expected = slots(market, borrower)
    slot_key = byte_array(capsule['slot_key'], 32)
    require(int.from_bytes(slot_key, 'big') == expected['position'], 'position slot identity')
    nonce = integer_field(account, 'nonce', 8)
    balance = integer_field(account, 'balance', 32)
    position_bytes = integer_field(capsule['slot'], 'value', 32)
    require(bool(position_bytes), 'zero inclusion unsupported')
    account_value = rlp.encode([nonce, balance, storage_root, code_hash])
    storage_value = rlp.encode(position_bytes)
    account_nodes = reconstruct(capsule, 'account', 15, keccak(address), account_value)
    storage_nodes = reconstruct(capsule, 'storage', 10, keccak(slot_key), storage_value)
    decoder = ProofDecoder(shared=True)
    require(decoder.prove(root, keccak(address), account_nodes) == account_value, 'account proof')
    require(decoder.prove(storage_root, keccak(slot_key), storage_nodes) == storage_value, 'storage proof')
    position = int.from_bytes(position_bytes, 'big')
    result = {
        'status': 'PARTIAL_ROOT_BINDING_VERIFIED',
        'scope': 'ACCOUNT_CODE_AND_ONE_SLOT_RELATIVE_TO_UNAUTHENTICATED_ROOT',
        'chain_id_claim': case['chain_id_claim'],
        'block_number_claim': case['block_number_claim'],
        'state_root_claim': case['state_root_claim'],
        'block_hash': None, 'canonicality': 'UNKNOWN', 'header_verified': False,
        'account_proof_verified_relative_to_root': True,
        'runtime_hash_matches_proved_code_hash': True,
        'runtime_bytes': len(runtime), 'runtime_sha256': hashlib.sha256(runtime).hexdigest(),
        'market_id_claim': case['market_id'], 'borrower_claim': case['borrower'],
        'slot_matches_R5_derivation': True, 'storage_slots_verified': 1,
        'R5_storage_slots_required': len(expected),
        'missing_slots': {name: '0x' + slot.to_bytes(32, 'big').hex()
                          for name, slot in expected.items() if name != 'position'},
        'position_word_relative_to_root': str(position),
        'layout_attested': False, 'oracle_price': None, 'observed_eligibility': None,
        'full_R5_packet_ready': False, 'authentic_witness_integrated': False,
        'whole_bot_stabilized': False, 'commercial_admission': False,
        'capsule_sha256': hashlib.sha256(capsule_raw).hexdigest(),
    }
    partial_account = {
        'address': case['address'], 'nonce': hex(int.from_bytes(nonce, 'big')),
        'balance': hex(int.from_bytes(balance, 'big')),
        'storageHash': '0x' + storage_root.hex(), 'codeHash': case['code_hash'],
        'accountProof': account_nodes,
        'storageProof': [{'key': '0x' + slot_key.hex(), 'value': hex(position), 'proof': storage_nodes}],
    }
    return result, partial_account


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capsule', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        with args.capsule.open('rb') as stream: capsule = stream.read(MAX_CAPSULE + 1)
        with args.runtime.open('rb') as stream: runtime = stream.read(MAX_RUNTIME_FILE + 1)
        with args.case.open('rb') as stream: case = stream.read(4097)
        result, partial = recover(capsule, runtime, case)
    except (Rejected, OSError) as error:
        result = {'status': 'REJECTED', 'error': str(error), 'commercial_admission': False}
        (args.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
        return 2
    (args.out / 'partial-account-proof.json').write_text(json.dumps(partial, indent=2) + '\n')
    (args.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
