"""By-value ctypes binding; the caller pins an already built local library.

The hash is checked before loading. Pinning is not provenance or sandboxing: the
library must be built from reviewed sources. No arbitrary path from a packet is used.
"""
import ctypes
import hashlib
from pathlib import Path
import re
import sys

R3 = Path(__file__).resolve().parents[2] / "r3-state-evidence"
sys.path.insert(0, str(R3 / "src"))
from state_evidence import Rejected, require


class Request(ctypes.Structure):
    _fields_ = [("words", ctypes.c_uint64 * 24)]


class Response(ctypes.Structure):
    _fields_ = [("status", ctypes.c_uint64), ("debt", ctypes.c_uint64 * 4),
                ("capacity", ctypes.c_uint64 * 4), ("eligible", ctypes.c_uint64)]


class NativeMath:
    def __init__(self, library, expected_sha256):
        path = Path(library).resolve(strict=True)
        require(type(expected_sha256) is str and
                re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None, "library pin format")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256, "library digest")
        require(ctypes.sizeof(Request) == 192 and ctypes.sizeof(Response) == 80, "host ABI sizes")
        # Local filesystem/code are trusted; hostile concurrent file replacement is out of scope.
        self._library = ctypes.CDLL(str(path))
        version = self._library.nqc666_abi_version
        version.argtypes = []
        version.restype = ctypes.c_uint64
        require(version() == 1, "native ABI version")
        self._health = self._library.nqc666_health
        self._health.argtypes = [Request]
        self._health.restype = Response

    def health(self, args):
        require(type(args) in (list, tuple) and len(args) == 6 and
                all(type(x) is int and 0 <= x < 2**256 for x in args), "math input range")
        # A fresh value per call prevents shared-buffer races; no mutable request cache.
        request = Request()
        for i, value in enumerate(args):
            for j in range(4):
                request.words[i * 4 + j] = (value >> (j * 64)) & (2**64 - 1)
        response = self._health(request)
        require(response.status == 0, "native math rejected: " + str(response.status))
        require(response.eligible in (0, 1), "native result range")
        def integer(limbs):
            return sum(v << (i * 64) for i, v in enumerate(limbs))
        debt, cap = integer(response.debt), integer(response.capacity)
        require(bool(response.eligible) == (debt > cap), "native result consistency")
        return debt, cap, bool(response.eligible)
