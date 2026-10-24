"""Decodificación ABI mínima (palabras de 32 bytes), sin dependencias."""


def strip0x(h: str) -> str:
    return h[2:] if h.startswith(("0x", "0X")) else h


def words(data: str) -> list:
    raw = strip0x(data or "")
    if len(raw) % 64:
        raise ValueError(f"datos ABI con longitud no múltiplo de 32 bytes: {len(raw)}")
    return [int(raw[i:i + 64], 16) for i in range(0, len(raw), 64)]


def address_from_word(word: int) -> str:
    if word >> 160:
        raise ValueError("palabra no es una dirección (bits altos distintos de cero)")
    return "0x" + format(word, "040x")


def address_from_topic(t: str) -> str:
    return address_from_word(int(strip0x(t), 16))


def to_int(h) -> int:
    if h is None:
        return None
    if isinstance(h, int):
        return h
    return int(h, 16)


def to_signed(word: int, bits: int = 256) -> int:
    return word - (1 << bits) if word >> (bits - 1) else word


def encode_address(addr: str) -> str:
    return strip0x(addr).lower().rjust(64, "0")


def encode_bytes32(b: str) -> str:
    raw = strip0x(b).lower()
    if len(raw) != 64:
        raise ValueError("bytes32 debe tener 32 bytes")
    return raw


def norm(addr: str) -> str:
    return "0x" + strip0x(addr).lower().rjust(40, "0")


def decode_string(data: str) -> str:
    """Decodifica un `string` ABI o un `bytes32` (tokens antiguos como MKR)."""
    raw = strip0x(data or "")
    if not raw:
        return ""
    if len(raw) == 64:
        return bytes.fromhex(raw).rstrip(b"\x00").decode("utf-8", "replace")
    try:
        ws = words(raw)
        offset, length = ws[0], ws[1]
        start = offset * 2 + 64
        return bytes.fromhex(raw[start:start + length * 2]).decode("utf-8", "replace")
    except (ValueError, IndexError):
        return ""
