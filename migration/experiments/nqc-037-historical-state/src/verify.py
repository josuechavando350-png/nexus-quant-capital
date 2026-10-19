"""Offline, bounded proof intake. A valid proof is relative to its supplied root.

This module cannot certify consensus, execute Nitro, or admit a trading strategy.
NQC031's preserved MPT verifier supplies path inclusion/non-inclusion verification.
"""
import json
import re
import sys
from pathlib import Path

import rlp
from Crypto.Hash import keccak

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor' / 'nqc031'))
from storage_proof import verify as verify_mpt, EMPTY_CODE_HASH  # noqa: E402

CHAIN_ID = 4663
PARENT_NUMBER = 66744161
TARGET_NUMBER = 66744162
ANCHOR_NUMBER = 66753418
PARENT_HASH = '0x53f9d3bedcdd3554f7447343ca03f9c9a5a7b61c692057f431d9225e04e1a917'
TARGET_HASH = '0x8e702487ffdd8f2ff97528407ba671f1a1d1d6f16a812e85fb5cb6625b6886d7'
ANCHOR_HASH = '0xcc02e358c6b11bfeb61182aef188bffffaa49073e666f740f2c2a887abc2c1c1'
PARENT_ROOT = '0xc07bf301da73475b44460226757ddfd1c2ee60a6d7346e3749de6953f78bae4a'
PRIORITY_ADDRESS = '0x929631b33f4070d6f54477fba3fd27566567daca'
PRIORITY_SLOTS = [9, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31]
ARBOS_ADDRESS = '0xa4b05fffffffffffffffffffffffffffffffffff'
HISTORY_ADDRESS = '0x0000f90827f1c53a10cb7a02335b175320002935'
HISTORY_WINDOW = 393168
# Exact Arbitrum runtime, not the Ethereum 8191-slot runtime; pinned source in vendor/.
HISTORY_CODE = bytes.fromhex(
    '3373fffffffffffffffffffffffffffffffffffffffe1460605760203603605c575f3563'
    'a3b1b31d5f5260205f6004601c60645afa15605c575f51600181038211605c57816205ffd0'
    '910311605c576205ffd09006545f5260205ff35b5f5ffd5b5f356205ffd0600163a3b1b31d'
    '5f5260205f6004601c60645afa15605c575f5103065500')
ARBOS_FIELDS = {'version': 0, 'upgrade_version': 1, 'upgrade_timestamp': 2,
                'chain_id': 4, 'genesis_block_number': 5}


class ValidationError(ValueError):
    """Only locally authored messages, with no third-party text or endpoint."""


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def k256(data):
    return keccak.new(digest_bits=256, data=data).digest()


def data_hex(value, size=None):
    require(isinstance(value, str) and re.fullmatch(r'0x(?:[0-9a-fA-F]{2})*', value),
            'Invalid DATA encoding')
    raw = bytes.fromhex(value[2:])
    require(size is None or len(raw) == size, 'Invalid DATA width')
    return raw


def quantity(value):
    require(isinstance(value, str) and re.fullmatch(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)', value),
            'Noncanonical QUANTITY')
    number = int(value, 16)
    require(number < 2**256, 'QUANTITY exceeds uint256')
    return number


def slot(value):
    require(type(value) is int and 0 <= value < 2**256, 'Invalid slot')
    return '0x' + value.to_bytes(32, 'big').hex()


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def read_json(path, limit=16 * 1024 * 1024):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'JSON byte limit')
    return json.loads(raw, object_pairs_hook=no_duplicate_keys)


def validate_header(header, expected_hash=None, expected_number=None):
    """Explicit 16-field Nitro header schema; reject future appended fields."""
    require(isinstance(header, dict), 'Header must be an object')
    for key in ['withdrawalsRoot', 'blobGasUsed', 'excessBlobGas',
                'parentBeaconBlockRoot', 'requestsHash']:
        require(header.get(key) is None, 'Unsupported appended header field')
    widths = {'parentHash': 32, 'sha3Uncles': 32, 'miner': 20, 'stateRoot': 32,
              'transactionsRoot': 32, 'receiptsRoot': 32, 'logsBloom': 256}
    fields = [data_hex(header[k], width) for k, width in widths.items()]
    fields += [quantity(header[k]) for k in ['difficulty', 'number', 'gasLimit', 'gasUsed', 'timestamp']]
    fields += [data_hex(header['extraData'], 32), data_hex(header['mixHash'], 32),
               data_hex(header['nonce'], 8), quantity(header['baseFeePerGas'])]
    calculated = '0x' + k256(rlp.encode(fields)).hex()
    require(data_hex(header['hash'], 32).hex() == calculated[2:], 'Header hash mismatch')
    require(expected_hash is None or calculated == expected_hash, 'Unexpected block hash')
    require(expected_number is None or quantity(header['number']) == expected_number, 'Unexpected block height')
    mix = data_hex(header['mixHash'], 32)
    for key, expected in [('sendCount', int.from_bytes(mix[:8], 'big')),
                          ('l1BlockNumber', int.from_bytes(mix[8:16], 'big'))]:
        if key in header:
            require(quantity(header[key]) == expected, 'Header metadata mismatch')
    if 'sendRoot' in header:
        require(data_hex(header['sendRoot'], 32) == fields[12], 'Send root metadata mismatch')
    return calculated


def arbos_slot(offset, storage_key=b''):
    """Storage.mapAddress: hash a 31-byte page, then append its 1-byte offset."""
    key = data_hex(slot(offset), 32)
    return '0x' + (k256(storage_key + key[:31])[:31] + key[31:]).hex()


def account_proof(root, address, slots, proof, code=None):
    data_hex(root, 32)
    expected_address = data_hex(address, 20)
    require(isinstance(proof, dict), 'Proof must be an object')
    require(data_hex(proof['address'], 20) == expected_address, 'Wrong proof account')
    quantity(proof['nonce'])
    quantity(proof['balance'])
    expected = {slot(int(value, 16)) for value in slots}
    require(len(expected) == len(slots), 'Duplicate requested slot')
    actual = []
    require(isinstance(proof['storageProof'], list), 'Storage proof must be a list')
    for item in proof['storageProof']:
        key = item['key']
        require(isinstance(key, str) and re.fullmatch(r'0x[0-9a-fA-F]{1,64}', key), 'Invalid storage key')
        actual.append(slot(int(key, 16)))
        quantity(item['value'])
    require(len(actual) == len(set(actual)), 'Duplicate returned slot')
    require(set(actual) == expected, 'Missing or extra proof slots')
    checked = verify_mpt(data_hex(root, 32), proof)
    if code is not None:
        require(k256(data_hex(code)) == data_hex(checked['code_hash'], 32), 'Code hash mismatch')
    return checked


def history_bridge(anchor, target, parent, proof, code, expected_anchor_hash=ANCHOR_HASH):
    """Conditional ancestry relative to an observed anchor, never consensus proof."""
    validate_header(anchor, expected_anchor_hash)
    validate_header(target)
    validate_header(parent)
    require(target['parentHash'].lower() == parent['hash'].lower(), 'Broken target parent link')
    height = quantity(anchor['number'])
    target_height = quantity(target['number'])
    parent_height = quantity(parent['number'])
    require(target_height == parent_height + 1, 'Nonconsecutive target and parent')
    require(all(1 <= height - h <= HISTORY_WINDOW for h in [target_height, parent_height]),
            'History entry outside Arbitrum window')
    require(data_hex(code) == HISTORY_CODE, 'Wrong history contract runtime')
    keys = [slot(h % HISTORY_WINDOW) for h in [target_height, parent_height]]
    checked = account_proof(anchor['stateRoot'], HISTORY_ADDRESS, keys, proof, code)
    for key, header in zip(keys, [target, parent]):
        require(int(checked['storage_values'][key]) == int(header['hash'], 16), 'History hash mismatch')
    return {'status': 'HISTORY_LINK_VERIFIED_RELATIVE_TO_OBSERVED_ANCHOR',
            'anchor_hash': anchor['hash'], 'window': HISTORY_WINDOW,
            'block_distances': [height - target_height, height - parent_height],
            'history_slots': keys, 'canonical_anchor_authenticated': False,
            'historical_system_semantics_authenticated': False,
            'exact_pretransaction_state_authenticated': False, 'commercial_admission': False}


def closed_gates():
    return {'l1_receipt_inclusion_verified': False, 'l1_consensus_finality_verified': False,
            'canonical_l2_header_authenticated': False, 'historical_nitro_binary_authenticated': False,
            'historical_fork_schedule_authenticated': False, 'parent_witness_complete': False,
            'prefix_state_transition_executed': False, 'exact_prestate_root': None,
            'authenticated_pretransaction_priority_slots': 0, 'nitro_replayed': False,
            'economic_replay_completed': False, 'funding_terms_accepted': False,
            'commercial_admission': False, 'commercial_readiness_judgment_out_of_10': 2.5,
            'realized_pnl_usd': '0'}
