"""NQC050 process-local RLP encoder for the pinned NQC037 header verification.

This overlay is *not* written into the recovered NQC037 tree. It deliberately
implements only ``rlp.encode`` for immutable integers/bytes/lists/tuples.
"""


def encode(value):
    def pack(prefix, payload):
        length = len(payload)
        if length < 56:
            return bytes((prefix + length,)) + payload
        size = (length.bit_length() + 7) // 8
        if size >= 9:
            raise ValueError('RLP length exceeds fixed maximum')
        return bytes((prefix + 55 + size,)) + length.to_bytes(size, 'big') + payload

    if type(value) is int:
        if not 0 <= value < (1 << 256):
            raise ValueError('RLP integer out of range')
        value = value.to_bytes((value.bit_length() + 7) // 8, 'big')
    if isinstance(value, bytes):
        if len(value) == 1 and value[0] < 128:
            return value
        return pack(0x80, value)
    if isinstance(value, (list, tuple)):
        return pack(0xc0, b''.join(encode(child) for child in value))
    raise TypeError('RLP only accepts bytes, nonnegative integers, lists and tuples')
