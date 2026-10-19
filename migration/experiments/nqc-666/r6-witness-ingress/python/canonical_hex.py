"""Equivalent R3 lowercase/even DATA decoding without the regex traversal."""
from state_evidence import Rejected, require, MAX_PACKET


def data(value, size=None):
    require(type(value) is str and len(value) <= MAX_PACKET, "data type/size")
    require(value.startswith("0x") and len(value) % 2 == 0, "noncanonical data hex")
    payload = value[2:]
    try:
        result = bytes.fromhex(payload)
    except ValueError as e:
        raise Rejected("noncanonical data hex") from e
    # fromhex alone permits whitespace and uppercase: round-trip rejects both.
    require(result.hex() == payload, "noncanonical data hex")
    require(size is None or len(result) == size, "data width")
    return result
