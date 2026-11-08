"""Declared fault scheduling around real filesystem opens, with real FD counts."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_workspace as module


class WorkspaceAdmissionTests(unittest.TestCase):
    def run_admission(self, replacement):
        original_open = os.open
        returned = []
        with tempfile.TemporaryDirectory(prefix='own-admission-regression-') as parent:
            root = Path(parent)
            foreign = root/'foreign-data'
            foreign.mkdir(mode=0o700)
            (foreign/'marker').write_bytes(b'original own control bytes')
            with patch.object(tempfile, 'tempdir', parent):
                workspace = module.Workspace('verification')
                before = len(os.listdir('/proc/self/fd'))
                moved = []
                def scheduled_open(path, flags, *args, **kwargs):
                    if workspace.path is not None and path == workspace.path.name and kwargs.get('dir_fd') is not None:
                        preserved = root/'preserved-created-root'
                        workspace.path.rename(preserved)
                        moved.append(preserved)
                        if replacement == 'directory':
                            workspace.path.mkdir(mode=0o700)
                            (workspace.path/'replacement-marker').write_bytes(b'keep replacement')
                        elif replacement == 'symlink':
                            workspace.path.symlink_to(foreign, target_is_directory=True)
                        elif replacement == 'missing':
                            pass
                        elif replacement == 'file':
                            workspace.path.write_bytes(b'keep replacement file')
                        else:
                            raise AssertionError(replacement)
                        fd = original_open(path, flags, *args, **kwargs)
                        info = os.fstat(fd)
                        returned.append((fd, (info.st_dev, info.st_ino)))
                        return fd
                    return original_open(path, flags, *args, **kwargs)
                supported = set(os.supports_dir_fd) | {scheduled_open}
                try:
                    with patch.object(module.os, 'open', scheduled_open), patch.object(module.os, 'supports_dir_fd', supported):
                        with self.assertRaises((module.WorkspaceError, OSError)) as raised:
                            workspace.__enter__()
                    self.assertEqual(len(os.listdir('/proc/self/fd')), before)
                    self.assertEqual(workspace.state, 'FAILED')
                    self.assertIsNone(workspace.observation)
                    self.assertEqual(len(moved), 1)
                    self.assertTrue(moved[0].is_dir())
                    self.assertEqual((foreign/'marker').read_bytes(), b'original own control bytes')
                    if replacement == 'directory':
                        self.assertEqual(str(raised.exception), 'WORKSPACE_IDENTITY_CHANGED')
                        self.assertEqual((workspace.path/'replacement-marker').read_bytes(), b'keep replacement')
                    elif replacement == 'symlink':
                        self.assertTrue(workspace.path.is_symlink())
                    elif replacement == 'missing':
                        self.assertFalse(os.path.lexists(workspace.path))
                    else:
                        self.assertEqual(workspace.path.read_bytes(), b'keep replacement file')
                finally:
                    # Prevent a deliberately failing regression from leaking its
                    # own returned FD into the shared test runner. Never close a
                    # descriptor whose observed object no longer matches it.
                    for fd, expected in returned:
                        try:
                            info = os.fstat(fd)
                        except OSError:
                            continue
                        if (info.st_dev, info.st_ino) == expected:
                            os.close(fd)

    def test_replaced_directory_open_is_closed_without_deleting_replacement(self):
        self.run_admission('directory')

    def test_symlink_between_stat_and_open_preserves_target_and_closes_parent(self):
        self.run_admission('symlink')

    def test_missing_root_between_stat_and_open_closes_parent(self):
        self.run_admission('missing')

    def test_regular_file_replacement_is_not_deleted(self):
        self.run_admission('file')


if __name__ == '__main__':
    unittest.main()
