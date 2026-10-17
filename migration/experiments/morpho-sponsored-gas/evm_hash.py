"""Ethereum Keccak-256 using a pinned dependency, never NIST SHA3-256."""


def keccak256(data: bytes) -> bytes:
    if not isinstance(data, bytes):
        raise ValueError("Keccak input must be bytes")
    try:
        from Crypto.Hash import keccak
    except ImportError as exc:
        raise RuntimeError("install this experiment's requirements.txt in a virtualenv") from exc
    return keccak.new(data=data, digest_bits=256).digest()
