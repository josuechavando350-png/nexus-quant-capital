"""Local fixture regressions for source acquisition; faults are injected explicitly."""
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import repository_boundary as boundary


class RepositoryCaptureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'own-copy'
        self.source = self.root / 'superhunter' / 'fixture.txt'
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'own fixture\n')
        self.source.chmod(0o644)

    def capture(self):
        return boundary._capture(self.root)

    def deny_scan(self, target, error):
        original = os.scandir
        def scan(path):
            if Path(path) == target:
                raise error
            return original(path)
        return patch.object(boundary.os, 'scandir', side_effect=scan)

    def test_root_scan_error_cannot_return_empty_inventory(self):
        with self.deny_scan(self.root, PermissionError(errno.EACCES, 'private-fixture')):
            with self.assertRaisesRegex(boundary.BoundaryError, '^DIRECTORY_READ_FAILED$'):
                self.capture()

    def test_child_scan_error_cannot_omit_source_subtree(self):
        with self.deny_scan(self.source.parent, PermissionError(errno.EACCES, 'private-fixture')):
            with self.assertRaisesRegex(boundary.BoundaryError, '^DIRECTORY_READ_FAILED$'):
                self.capture()

    def test_disappeared_directory_aborts_acquisition(self):
        with self.deny_scan(self.source.parent, FileNotFoundError(errno.ENOENT, 'private-fixture')):
            with self.assertRaisesRegex(boundary.BoundaryError, '^DIRECTORY_READ_FAILED$'):
                self.capture()

    def test_directory_io_error_aborts_acquisition(self):
        with self.deny_scan(self.source.parent, OSError(errno.EIO, 'private-fixture')):
            with self.assertRaisesRegex(boundary.BoundaryError, '^DIRECTORY_READ_FAILED$'):
                self.capture()

    def before_open(self, action):
        original = os.open
        changed = False
        def opened(path, flags, *args, **kwargs):
            nonlocal changed
            if not changed and Path(path) == self.source:
                changed = True
                action()
            return original(path, flags, *args, **kwargs)
        return patch.object(boundary.os, 'open', side_effect=opened)

    def replace_source(self):
        replacement = self.root / 'replacement'
        replacement.write_bytes(self.source.read_bytes())
        replacement.chmod(0o644)
        os.replace(replacement, self.source)

    def test_same_bytes_new_inode_before_open_is_rejected(self):
        with self.before_open(self.replace_source):
            with self.assertRaisesRegex(boundary.BoundaryError, '^FILE_CHANGED_DURING_READ$'):
                self.capture()

    def test_mode_change_before_open_is_rejected(self):
        with self.before_open(lambda: self.source.chmod(0o755)):
            with self.assertRaisesRegex(boundary.BoundaryError, '^FILE_CHANGED_DURING_READ$'):
                self.capture()

    def during_read(self, action, observed=None):
        original = os.fdopen
        class Reader:
            def __init__(inner, *args, **kwargs):
                inner.stream = original(*args, **kwargs)
            def __enter__(inner):
                inner.stream.__enter__()
                return inner
            def __exit__(inner, *args):
                return inner.stream.__exit__(*args)
            def read(inner, size):
                if observed is not None:
                    observed.append(size)
                raw = inner.stream.read(size)
                action()
                return raw
        return patch.object(boundary.os, 'fdopen', Reader)

    def test_content_change_after_read_is_rejected(self):
        def alter():
            self.source.write_bytes(b'new fixture\n')
            info = self.source.stat()
            os.utime(self.source, ns=(info.st_atime_ns, info.st_mtime_ns + 1000000000))
        with self.during_read(alter):
            with self.assertRaisesRegex(boundary.BoundaryError, '^FILE_CHANGED_DURING_READ$'):
                self.capture()

    def test_mode_change_after_read_is_rejected(self):
        with self.during_read(lambda: self.source.chmod(0o755)):
            with self.assertRaisesRegex(boundary.BoundaryError, '^FILE_CHANGED_DURING_READ$'):
                self.capture()

    def test_path_replacement_after_read_is_rejected(self):
        with self.during_read(self.replace_source):
            with self.assertRaisesRegex(boundary.BoundaryError, '^FILE_CHANGED_DURING_READ$'):
                self.capture()

    def test_growth_after_read_is_rejected(self):
        with self.during_read(lambda: self.source.write_bytes(b'larger owned input\n')):
            with self.assertRaisesRegex(boundary.BoundaryError, '^FILE_CHANGED_DURING_READ$'):
                self.capture()

    def test_read_budget_uses_admitted_size_plus_one(self):
        sizes = []
        expected = self.source.read_bytes()
        with self.during_read(lambda: None, sizes):
            files, ignored = self.capture()
        self.assertEqual(sizes, [len(expected) + 1])
        self.assertEqual(files, {'superhunter/fixture.txt': {'mode': '100644', 'bytes': expected}})
        self.assertEqual(ignored, 0)

    def test_stable_empty_file_is_retained(self):
        self.source.write_bytes(b'')
        files, ignored = self.capture()
        self.assertEqual(files['superhunter/fixture.txt'], {'mode': '100644', 'bytes': b''})
        self.assertEqual(ignored, 0)

    def test_read_failure_closes_owned_descriptor(self):
        before = set(os.listdir('/proc/self/fd'))
        with self.during_read(lambda: (_ for _ in ()).throw(OSError(errno.EIO, 'own-error'))):
            with self.assertRaises(OSError):
                self.capture()
        self.assertEqual(set(os.listdir('/proc/self/fd')), before)


if __name__ == '__main__':
    unittest.main()
