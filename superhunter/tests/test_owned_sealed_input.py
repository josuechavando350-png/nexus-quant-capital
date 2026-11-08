"""Data parser and actual descriptor controls over generated own inputs only."""
import errno
import fcntl
import os
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_sealed_input as sealed


class SealedInputTests(unittest.TestCase):
    def files(self):
        return {'empty': {'mode': '100644', 'bytes': b''},
                'nested/own.txt': {'mode': '100755', 'bytes': b'own data\x00\xff\n'}}

    def frame(self, entries):
        return sealed.HEADER.pack(sealed.MAGIC, len(entries)) + b''.join(
            sealed.ENTRY.pack(len(name), mode, len(raw)) + name + raw for name, mode, raw in entries)

    def test_binary_empty_executable_and_unicode_roundtrip(self):
        files = self.files()
        files['datos/ñ.txt'] = {'mode': '100644', 'bytes': b'own unicode key'}
        self.assertEqual(sealed.decode(sealed.encode(files)), files)
        self.assertEqual(sealed.encode(dict(reversed(list(files.items())))), sealed.encode(files))

    def test_seeded_distinct_inventories_roundtrip(self):
        rng = random.Random(61108)
        for count in range(1, 35):
            files = {f'own/{i:03}.bin': {'mode': sealed.MODES[rng.randrange(2)],
                     'bytes': rng.randbytes(rng.randrange(257))} for i in range(count)}
            self.assertEqual(sealed.decode(sealed.encode(files)), files)

    def test_every_truncated_prefix_and_appended_suffix_rejected(self):
        raw = sealed.encode(self.files())
        for index in range(len(raw)):
            with self.subTest(index=index), self.assertRaises(sealed.SealedInputError):
                sealed.decode(raw[:index])
        for suffix in (b'\0', b'other data', raw):
            with self.subTest(suffix=suffix[:12]), self.assertRaisesRegex(ValueError, 'TRAILING'):
                sealed.decode(raw+suffix)

    def test_duplicate_and_reversed_keys_rejected(self):
        for names in ((b'own', b'own'), (b'z', b'a')):
            with self.subTest(names=names), self.assertRaisesRegex(ValueError, 'ORDER_OR_DUPLICATE'):
                sealed.decode(self.frame([(name, 0, b'') for name in names]))

    def test_invalid_inventory_keys_never_become_paths(self):
        for name in ('', '/absolute', '../parent', 'a/./b', 'a//b', 'a\\b', 'a:b',
                     'null\0key', 'new\nline', 'x/'*22+'leaf', 'a'*1025, '\ud800'):
            with self.subTest(name=repr(name)), self.assertRaises(sealed.SealedInputError):
                sealed.encode({name: {'mode': '100644', 'bytes': b''}})
            if name and '\ud800' not in name:
                with self.subTest(decoded=repr(name)), self.assertRaises(sealed.SealedInputError):
                    sealed.decode(self.frame([(name.encode(), 0, b'')]))

    def test_invalid_utf8_and_mode_are_rejected(self):
        for row in ((b'\xff', 0, b''), (b'own', 2, b''), (b'own', 255, b'')):
            with self.subTest(row=row), self.assertRaises(sealed.SealedInputError):
                sealed.decode(self.frame([row]))

    def test_claimed_count_and_lengths_rejected_before_allocation(self):
        for count in (0, sealed.MAX_FILES+1, 2**32-1):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, 'FILE_COUNT'):
                sealed.decode(sealed.HEADER.pack(sealed.MAGIC, count))
        for size in (sealed.MAX_FILE_BYTES+1, 2**32-1):
            raw = sealed.HEADER.pack(sealed.MAGIC, 1) + sealed.ENTRY.pack(1, 0, size) + b'a'
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, 'BYTES_BUDGET'):
                sealed.decode(raw)

    def test_total_budget_checked_by_both_producer_and_parser(self):
        files = {'a': {'mode': '100644', 'bytes': b'1234'}, 'b': {'mode': '100644', 'bytes': b'5678'}}
        raw = sealed.encode(files)
        with patch.object(sealed, 'MAX_TOTAL_BYTES', 7):
            with self.assertRaisesRegex(ValueError, 'BYTES_BUDGET'): sealed.encode(files)
            with self.assertRaisesRegex(ValueError, 'BYTES_BUDGET'): sealed.decode(raw)

    def test_closed_types_and_fields(self):
        for files in ({}, [], {1: {}}, {'x': {}}, {'x': {'mode': '100644', 'bytes': bytearray()}},
                      {'x': {'mode': '100644', 'bytes': b'', 'extra': 1}}):
            with self.subTest(files=files), self.assertRaises(sealed.SealedInputError):
                sealed.encode(files)
        for raw in ('text', bytearray(16), b'x'*16):
            with self.subTest(raw=raw), self.assertRaises(sealed.SealedInputError): sealed.decode(raw)

    def test_actual_seals_block_parent_write_grow_and_shrink(self):
        raw = sealed.encode(self.files())
        with sealed.sealed_bytes(raw) as descriptor:
            self.assertEqual(sealed.inspect(descriptor), len(raw))
            writable = os.open(f'/proc/self/fd/{descriptor}', os.O_RDWR)
            try:
                for operation in (lambda: os.write(writable, b'changed'),
                                  lambda: os.ftruncate(writable, 0),
                                  lambda: os.ftruncate(writable, len(raw)+1)):
                    with self.assertRaises(OSError) as caught: operation()
                    self.assertEqual(caught.exception.errno, errno.EPERM)
            finally:
                os.close(writable)
            self.assertEqual(os.read(descriptor, len(raw)+1), raw)
            with self.assertRaisesRegex(ValueError, 'OFFSET'): sealed.inspect(descriptor)
        with self.assertRaises(OSError): os.fstat(descriptor)

    def test_unsealed_readonly_and_writable_descriptors_rejected(self):
        descriptor = os.memfd_create('own-test', os.MFD_ALLOW_SEALING)
        try:
            os.write(descriptor, sealed.encode(self.files()))
            with self.assertRaisesRegex(ValueError, 'READONLY'): sealed.inspect(descriptor)
            readonly = os.open(f'/proc/self/fd/{descriptor}', os.O_RDONLY)
            try:
                with self.assertRaisesRegex(ValueError, 'SEALS'): sealed.inspect(readonly)
            finally:
                os.close(readonly)
        finally:
            os.close(descriptor)

    def test_each_missing_seal_rejected(self):
        full = sealed.required_seals()
        for missing in sealed.SEAL_NAMES:
            descriptor = os.memfd_create('own-test', os.MFD_ALLOW_SEALING)
            try:
                os.write(descriptor, sealed.encode(self.files()))
                fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, full & ~getattr(fcntl, missing))
                readonly = os.open(f'/proc/self/fd/{descriptor}', os.O_RDONLY)
                try:
                    with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, 'SEALS'):
                        sealed.inspect(readonly)
                finally:
                    os.close(readonly)
            finally:
                os.close(descriptor)

    def test_context_closes_descriptor_on_interruption(self):
        descriptor = None
        with self.assertRaises(KeyboardInterrupt):
            with sealed.sealed_bytes(sealed.encode(self.files())) as descriptor:
                raise KeyboardInterrupt()
        with self.assertRaises(OSError): os.fstat(descriptor)

    def test_failed_seal_closes_new_descriptor(self):
        created = []
        original = os.memfd_create
        def tracked(*args):
            descriptor = original(*args)
            created.append(descriptor)
            return descriptor
        with patch.object(sealed.os, 'memfd_create', side_effect=tracked), \
             patch.object(sealed.fcntl, 'fcntl', side_effect=OSError(errno.EPERM, 'OWN-TEST')):
            with self.assertRaises(OSError):
                with sealed.sealed_bytes(sealed.encode(self.files())): self.fail('unexpected yield')
        self.assertEqual(len(created), 1)
        with self.assertRaises(OSError): os.fstat(created[0])


if __name__ == '__main__':
    unittest.main()
