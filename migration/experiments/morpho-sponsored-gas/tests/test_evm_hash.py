import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evm_hash import keccak256


class EvmHashTests(unittest.TestCase):
    def test_empty_ethereum_vector(self):
        self.assertEqual(keccak256(b"").hex(),
                         "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")

    def test_abc_ethereum_vector(self):
        self.assertEqual(keccak256(b"abc").hex(),
                         "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")

    def test_not_nist_sha3(self):
        self.assertNotEqual(keccak256(b"abc"), hashlib.sha3_256(b"abc").digest())

    def test_requires_bytes(self):
        for value in ("abc", 123, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                keccak256(value)
