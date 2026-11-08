"""Explicit scan-error controls on disposable source fixtures, without execution."""
import errno
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import quality, source_graph


class SourceEnumerationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / '__init__.py').write_bytes(b'OWNED = True\n')
        (self.root / 'model').mkdir()
        (self.root / 'model' / 'fixture.py').write_bytes(b'VALUE = 1\n')

    def denied(self, target, error, visited=None):
        original = os.scandir
        def scan(path):
            if visited is not None:
                visited.append(Path(path))
            if Path(path) == target:
                raise error
            return original(path)
        return patch.object(os, 'scandir', side_effect=scan)

    def test_included_subtree_scan_error_blocks_both_inventories(self):
        for capture in (quality.source_snapshot, source_graph.capture):
            with self.subTest(reader=capture.__module__):
                with self.denied(self.root / 'model', PermissionError(errno.EACCES, 'private-fixture')):
                    with self.assertRaisesRegex(ValueError, '^source directory enumeration failed$'):
                        capture(self.root)

    def test_directory_io_failure_blocks_both_inventories(self):
        for capture in (quality.source_snapshot, source_graph.capture):
            with self.subTest(reader=capture.__module__):
                with self.denied(self.root / 'model', OSError(errno.EIO, 'private-fixture')):
                    with self.assertRaisesRegex(ValueError, '^source directory enumeration failed$'):
                        capture(self.root)

    def test_root_error_is_explicit_and_does_not_expose_path(self):
        for capture in (quality.source_snapshot, source_graph.capture):
            with self.subTest(reader=capture.__module__):
                with self.denied(self.root, PermissionError(errno.EACCES, 'private-fixture')):
                    with self.assertRaisesRegex(ValueError, '^source directory enumeration failed$'):
                        capture(self.root)

    def test_generated_cache_remains_excluded_from_both_inventories(self):
        cache = self.root / '__pycache__'
        cache.mkdir()
        (cache / 'unreviewed.py').write_bytes(b'cache is not source\n')
        for capture in (quality.source_snapshot, source_graph.capture):
            with self.subTest(reader=capture.__module__):
                expected = capture(self.root)
                visited = []
                with self.denied(cache, PermissionError(errno.EACCES, 'private-fixture'), visited):
                    self.assertEqual(capture(self.root), expected)
                self.assertNotIn(cache, visited)

    def test_qa_requires_tests_while_source_graph_preserves_its_exclusion(self):
        tests = self.root / 'tests'
        tests.mkdir()
        (tests / 'test_fixture.py').write_bytes(b'OWNED_TEST = True\n')
        expected_graph = source_graph.capture(self.root)
        with self.denied(tests, PermissionError(errno.EACCES, 'private-fixture')):
            self.assertEqual(source_graph.capture(self.root), expected_graph)
            with self.assertRaisesRegex(ValueError, '^source directory enumeration failed$'):
                quality.source_snapshot(self.root)

    def test_stable_readers_retain_exact_bytes_hashes_and_order(self):
        expected = {'__init__.py': b'OWNED = True\n', 'model/fixture.py': b'VALUE = 1\n'}
        self.assertEqual(source_graph.capture(self.root), expected)
        self.assertEqual(quality.source_snapshot(self.root),
                         {name: hashlib.sha256(raw).hexdigest() for name, raw in expected.items()})
        self.assertEqual(list(source_graph.capture(self.root)), list(expected))


if __name__ == '__main__':
    unittest.main()
