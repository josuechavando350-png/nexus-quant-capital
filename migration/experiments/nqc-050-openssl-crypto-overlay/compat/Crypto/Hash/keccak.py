"""NQC050: adapt OpenSSL's KECCAK-256 EVP to Crypto.Hash.keccak.new.

No SHA3-256 substitution and no hand-rolled Keccak. Missing OpenSSL provider
support fails closed. Only the digest_bits=256 variant is supported.
"""
import hashlib


def new(*, digest_bits=256, data=b''):
    if type(digest_bits) is not int or digest_bits != 256:
        raise ValueError('only Keccak-256 supported')
    if not isinstance(data, bytes):
        raise TypeError('hash input must be bytes')
    try:
        return hashlib.new('keccak-256', data)
    except ValueError as exc:
        raise RuntimeError('OpenSSL Keccak-256 unavailable; no fallback') from exc
