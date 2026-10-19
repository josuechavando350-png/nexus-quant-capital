"""Verbatim NQC037 function slice for offline test only (NOT proof verifier replacement).
Each definition below is copied from GitHub-pinned verify.py and intake.py.
Original Git blob SHA-1 values documented separately; compare extracted SHA-256
with GitHub source before interpreting these tests as source-fidelity tests.
"""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'nqc-050-openssl-crypto-overlay' / 'compat'))
import rlp
from Crypto.Hash import keccak
CHAIN_ID=4663
PARENT_NUMBER=66744161
PARENT_HASH='0x53f9d3bedcdd3554f7447343ca03f9c9a5a7b61c692057f431d9225e04e1a917'
PARENT_ROOT='0xc07bf301da73475b44460226757ddfd1c2ee60a6d7346e3749de6953f78bae4a'

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


def envelope(response, request_id):
    require(isinstance(response, dict) and response.get('jsonrpc') == '2.0', 'Invalid RPC envelope')
    require(type(response.get('id')) is int and response['id'] == request_id, 'RPC id mismatch')
    if 'error' in response:
        err = response['error']
        code = err.get('code') if isinstance(err, dict) else None
        raise ValidationError('RPC error code ' + (str(code) if type(code) is int else 'unknown'))
    require('result' in response and response['result'] is not None, 'Missing RPC result')
    return response['result']


def validate_step(operation, response, state):
    result = envelope(response, operation['request']['id'])
    purpose = operation['purpose']
    if purpose == 'chain':
        require(quantity(result) == CHAIN_ID, 'Wrong chain')
    elif purpose == 'parent':
        validate_header(result, PARENT_HASH, PARENT_NUMBER)
        require(result['stateRoot'] == PARENT_ROOT, 'Parent state root mismatch')
    elif purpose == 'priority_proof':
        checked = account_proof(PARENT_ROOT, PRIORITY_ADDRESS, [slot(s) for s in PRIORITY_SLOTS], result)
        require(checked['code_hash'] != '0x' + EMPTY_CODE_HASH.hex(), 'Priority contract has no code')
        state['priority_checked'] = checked
    elif purpose == 'priority_code':
        account_proof(PARENT_ROOT, PRIORITY_ADDRESS, [slot(s) for s in PRIORITY_SLOTS],
                      state['priority_proof'], result)
    elif purpose == 'arbos_proof':
        checked = account_proof(PARENT_ROOT, ARBOS_ADDRESS, [arbos_slot(s) for s in ARBOS_FIELDS.values()], result)
        values = {name: int(checked['storage_values'][arbos_slot(s)]) for name, s in ARBOS_FIELDS.items()}
        require(values['version'] == 61 and values['chain_id'] == CHAIN_ID and values['genesis_block_number'] == 0,
                'ArbOS context differs from captured context')
        require(all(values[k] < 2**64 for k in ['version', 'upgrade_version', 'upgrade_timestamp', 'genesis_block_number']),
                'ArbOS uint64 overflow')
        state['arbos_checked'] = values
    elif purpose == 'anchor':
        validate_header(result, ANCHOR_HASH, ANCHOR_NUMBER)
        observed = read_json(ROOT / 'inputs/l1-observations.json')['confirmation']
        require(result['extraData'].lower() == observed['confirmed_send_root_field'], 'Anchor send root mismatch')
    elif purpose == 'history_proof':
        account_proof(state['anchor']['stateRoot'], HISTORY_ADDRESS,
                      [slot(s % HISTORY_WINDOW) for s in [TARGET_NUMBER, PARENT_NUMBER]], result)
    elif purpose == 'history_code':
        target = read_json(ROOT / 'inputs/target-header.json')['result']
        state['history_checked'] = history_bridge(state['anchor'], target, state['parent'],
                                                   state['history_proof'], result)
    else:
        raise ValidationError('Unknown acquisition purpose')
    state[purpose] = result
