"""Offline candidate-source slot mapper, NOT a proof verifier or Nitro replay.

Inputs are hypothetical/diagnostic values. Nothing here authenticates them.
No network, RPC plan changes, credential handling or acquisition side effects.
"""
from Crypto.Hash import keccak

ARBOS = '0xa4b05fffffffffffffffffffffffffffffffffff'
NUM_RESOURCE_KIND = 9  # Includes Unknown=0, as the pinned storage loops do.


def k256(data):
    return keccak.new(digest_bits=256, data=data).digest()


def uint(value, bits=64):
    if type(value) is not int or not 0 <= value < 2 ** bits:
        raise ValueError(f'expected uint{bits}')
    return value


def namespace(*identifiers):
    key = b''
    for identifier in identifiers:
        if type(identifier) is not bytes or not identifier:
            raise ValueError('nonempty bytes identifier required')
        key = k256(key + identifier)
    return key


def slot(path, offset):
    """storage.go mapAddress: hash the first 31 bytes, retain final key byte."""
    key = uint(offset, 256).to_bytes(32, 'big')
    return '0x' + (k256(namespace(*path) + key[:31])[:31] + key[31:]).hex()


L2 = (b'\x01',)
QUEUE = (b'\x02', b'\x00')
BLOCKHASH = (b'\x06',)
SINGLE = L2 + (b'\x00',)
MULTI = L2 + (b'\x01',)
FEES = L2 + (b'\x02',)


def control_slots():
    """Union of branch controls/legacy candidates, not a complete access list."""
    result = {name: slot((), i) for i, name in enumerate(
        ['arbos_version', 'upgrade_version', 'upgrade_timestamp'])}
    result['l1_next_block_number'] = slot(BLOCKHASH, 0)
    result.update({f'queue_{name}': slot(QUEUE, i)
                   for i, name in enumerate(['next_put', 'next_get'])})
    result['single_constraints_length'] = slot(SINGLE, 0)
    result['multi_constraints_length'] = slot(MULTI, 0)
    names = ['speed_limit', 'per_block_gas_limit', 'base_fee', 'min_base_fee',
             'backlog', 'inertia', 'backlog_tolerance', 'per_tx_gas_limit']
    result.update({f'l2_{name}': slot(L2, i) for i, name in enumerate(names)})
    return result


def pricing_model(version, single_length=None, multi_length=None):
    """Mirror pinned selection; missing required length stays unknown, not zero."""
    uint(version)
    for length in (single_length, multi_length):
        if length is not None:
            uint(length)
    if version >= 60:
        if multi_length is None:
            return None
        if multi_length:
            return 'multi'
    if version >= 50:
        if single_length is None:
            return None
        if single_length:
            return 'single'
    return 'legacy'


def constraint_slots(kind, index):
    if kind not in ('single', 'multi'):
        raise ValueError('single or multi required')
    path = (SINGLE if kind == 'single' else MULTI) + (uint(index).to_bytes(8, 'big'),)
    names = ['target', 'adjustment_window', 'backlog']
    if kind == 'multi':
        names += ['max_weight'] + [f'weight_{i}' for i in range(NUM_RESOURCE_KIND)]
    return {name: slot(path, i) for i, name in enumerate(names)}


def queue_entry(index):
    uint(index)
    if index < 2:
        raise ValueError('queue data starts at logical offset 2')
    return slot(QUEUE, index)


def retryable_slots(ticket):
    if type(ticket) is not bytes or len(ticket) != 32:
        raise ValueError('32 byte ticket id required')
    path = (b'\x02', ticket)
    names = ['num_tries', 'from', 'to', 'callvalue', 'beneficiary', 'timeout',
             'timeout_windows_left']
    result = {name: slot(path, i) for i, name in enumerate(names)}
    result['calldata_length'] = slot(path + (b'\x01',), 0)
    return result


def calldata_word_slot(ticket, word_index):
    retryable_slots(ticket)  # Validate id, without treating a missing value as 0.
    uint(word_index)
    if word_index == 2 ** 64 - 1:
        raise ValueError('logical chunk offset overflows uint64')
    return slot((b'\x02', ticket, b'\x01'), word_index + 1)


def escrow_address(ticket):
    retryable_slots(ticket)
    return '0x' + k256(b'retryable escrow' + ticket)[-20:].hex()


def blockhash_slot(l1_number):
    return slot(BLOCKHASH, 1 + uint(l1_number) % 256)


def fee_slots():
    return {f'{period}_{i}': slot(FEES, start + i)
            for period, start in [('next', 0), ('current', NUM_RESOURCE_KIND)]
            for i in range(NUM_RESOURCE_KIND)}
