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


class AcceptanceInventoryTests(unittest.TestCase):
    def setUp(self):
        from superhunter import acceptance_paths
        self.layout = acceptance_paths
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'quality.py').write_bytes(b'# fixture')

    def publish(self, profile):
        directory = self.root / self.layout.PROFILE_DIRECTORIES[profile]
        for name in self.layout.DOSSIER_FILES:
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name)
        return directory

    def test_every_enabled_renderer_directory_uses_the_qa_layout(self):
        from superhunter.tools.render_product_matrix import PROFILES
        for name, (path, _, _) in PROFILES.items():
            self.assertEqual(path, 'superhunter/' + self.layout.PROFILE_DIRECTORIES[name])

    def test_absent_dossiers_are_optional_and_every_present_member_has_one_owner(self):
        self.assertEqual(set(quality.source_snapshot(self.root)), {'quality.py'})
        for name in self.layout.PROFILE_DIRECTORIES:
            self.publish(name)
        snap = quality.source_snapshot(self.root)
        self.assertEqual(set(snap) - {'quality.py'}, self.layout.ALL_FILES)
        for path in self.layout.ALL_FILES:
            self.assertEqual(snap[path], hashlib.sha256((self.root / path).read_bytes()).hexdigest())
        owners = [path for component in quality.COMPONENTS.values()
                  for path in quality.component_files(component, snap) if path in self.layout.ALL_FILES]
        self.assertCountEqual(owners, self.layout.ALL_FILES)
        removed = self.layout.PATH_GROUPS[0][0]
        snap.pop(removed)
        self.assertIn('product_review: missing source ' + removed, quality.validate_components(snap))

    def test_partial_dossier_and_unexpected_contents_cannot_represent_a_profile(self):
        directory = self.publish('core-eight')
        (directory / 'first/session.json').unlink()
        with self.assertRaisesRegex(ValueError, 'incomplete acceptance replay'):
            quality.source_snapshot(self.root)
        (directory / 'first/session.json').write_text('original')
        (directory / 'extra.txt').touch()
        with self.assertRaisesRegex(ValueError, 'incomplete acceptance dossier'):
            quality.source_snapshot(self.root)
        (directory / 'extra.txt').unlink()
        (directory / 'second').rename(self.root / 'other')
        with self.assertRaisesRegex(ValueError, 'incomplete acceptance dossier'):
            quality.source_snapshot(self.root)

    def test_symlink_leaf_missing_directory_and_dangling_profile_cannot_replace_bytes(self):
        directory = self.publish('accounting')
        member = directory / 'first/session.json'
        member.unlink()
        member.symlink_to(directory / 'second/session.json')
        with self.assertRaises((ValueError, OSError)):
            quality.source_snapshot(self.root)
        member.unlink()
        member.touch()
        future = self.root / self.layout.PROFILE_DIRECTORIES['canonical-header']
        future.symlink_to(self.root / 'missing')
        with self.assertRaisesRegex(ValueError, 'not a directory'):
            quality.source_snapshot(self.root)
        future.unlink()
        future.write_text('not a directory')
        with self.assertRaisesRegex(ValueError, 'not a directory'):
            quality.source_snapshot(self.root)

    def test_newly_tracked_input_changes_snapshot_and_global_limit_still_applies(self):
        self.publish('grpc-schema')
        fixed = self.root / 'product_supply/fixed-cdxgen-guac-inputs.json'
        fixed.write_text('first'); before = quality.source_snapshot(self.root)
        fixed.write_text('other'); after = quality.source_snapshot(self.root)
        self.assertNotEqual(before['product_supply/fixed-cdxgen-guac-inputs.json'],
                            after['product_supply/fixed-cdxgen-guac-inputs.json'])
        for i in range(quality.MAX_SOURCE_FILES - len(after)):
            (self.root / f'case_{i}.py').touch()
        self.assertEqual(len(quality.source_snapshot(self.root)), quality.MAX_SOURCE_FILES)
        (self.root / 'one_more.py').touch()
        with self.assertRaisesRegex(ValueError, 'source inventory limit exceeded'):
            quality.source_snapshot(self.root)


if __name__ == '__main__':
    unittest.main()
