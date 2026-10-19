"""NQC050 offline vectors; no GitHub, provider, secret or network required."""
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'compat'))
import rlp
from Crypto.Hash import keccak


class CompatibilityTests(unittest.TestCase):
    def test_keccak_empty(self):
        self.assertEqual(keccak.new(digest_bits=256, data=b'').hexdigest(),
            'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470')

    def test_keccak_abc(self):
        self.assertEqual(keccak.new(digest_bits=256, data=b'abc').hexdigest(),
            '4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45')

    def test_keccak_not_nist_sha3(self):
        self.assertNotEqual(keccak.new(digest_bits=256, data=b'').digest(),
                            hashlib.sha3_256(b'').digest())

    def test_keccak_disallow_variant(self):
        with self.assertRaises(ValueError): keccak.new(digest_bits=384)

    def test_keccak_disallow_nonbytes(self):
        with self.assertRaises(TypeError): keccak.new(data='abc')

    def test_rlp_strings(self):
        self.assertEqual(rlp.encode(b'dog').hex(), '83646f67')
        self.assertEqual(rlp.encode(b'cat').hex(), '83636174')

    def test_rlp_nested_list(self):
        self.assertEqual(rlp.encode([b'cat', b'dog']).hex(), 'c88363617483646f67')
        self.assertEqual(rlp.encode([[], [[]], [[], [[]]]]).hex(), 'c7c0c1c0c3c0c1c0')

    def test_rlp_empty_and_ints(self):
        pairs = [(b'', '80'), ([], 'c0'), (0, '80'), (1, '01'),
                 (127, '7f'), (128, '8180'), (1024, '820400')]
        for v, expected in pairs:
            with self.subTest(value=v): self.assertEqual(rlp.encode(v).hex(), expected)

    def test_rlp_length_boundaries(self):
        self.assertEqual(rlp.encode(b'a'*55), bytes((0xb7,))+b'a'*55)
        self.assertEqual(rlp.encode(b'a'*56), bytes((0xb8,56))+b'a'*56)
        self.assertEqual(rlp.encode([b'a'*55]), bytes((0xf8,56,0xb7))+b'a'*55)

    def test_rlp_invalid_types(self):
        for v in (-1, True, 1 << 256, 3.14, None, 'str', {'a': 1}):
            with self.subTest(v=v),self.assertRaises((ValueError,TypeError)): rlp.encode(v)

    def test_hash_backend_independence(self):
        self.assertEqual(keccak.new(digest_bits=256, data=b'hello').digest(),
                         hashlib.new('keccak-256',b'hello').digest())


if __name__ == '__main__':
    unittest.main(verbosity=2)
