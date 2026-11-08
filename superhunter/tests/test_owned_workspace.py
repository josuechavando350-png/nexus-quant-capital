"""Real own-directory lifecycle controls; mocked IO faults are labelled explicitly."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_workspace as workspace, owned_capture as capture
from superhunter import owned_boundary_diagnosis as diagnosis, quality
from superhunter.safe_io import canonical


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.parent = self.root / 'runtime'
        self.parent.mkdir()
        override = patch.object(workspace.tempfile, 'gettempdir', return_value=str(self.parent))
        override.start(); self.addCleanup(override.stop)

    def new(self, purpose='verification', **kwargs):
        return workspace.Workspace(purpose, **kwargs)

    def test_real_nested_cleanup_and_later_absence(self):
        with self.new() as owned:
            (owned.path / 'nested').mkdir()
            (owned.path / 'nested' / 'owned-data').write_bytes(b'own temporary bytes')
            path = owned.path
        owned.confirm_removed()
        result = subprocess.run([sys.executable, '-I', '-B', '-c',
                                 'import os,sys;print(os.path.lexists(sys.argv[1]))', str(path)],
                                capture_output=True, text=True, timeout=5, check=True)
        self.assertEqual(result.stdout, 'False\n')
        self.assertEqual(list(self.parent.iterdir()), [])
        self.assertEqual(owned.state, 'REMOVED')
        record = owned.observation
        self.assertLessEqual(record['created_monotonic_ns'], record['cleanup_started_monotonic_ns'])
        self.assertLessEqual(record['cleanup_started_monotonic_ns'], record['cleanup_finished_monotonic_ns'])
        self.assertTrue(record['path_absent_after_cleanup'])
        self.assertFalse(record['future_absence_proved'])
        self.assertFalse(record['host_isolation_proved'])

    def test_private_root_and_noninheritable_descriptors(self):
        with self.new() as owned:
            self.assertEqual(stat.S_IMODE(owned.path.stat().st_mode), 0o700)
            self.assertEqual(owned.path.stat().st_uid, os.geteuid())
            self.assertFalse(os.get_inheritable(owned._root_fd))
            self.assertFalse(os.get_inheritable(owned._parent_fd))

    def test_body_exception_is_preserved_after_real_cleanup(self):
        with self.assertRaisesRegex(RuntimeError, 'own body failure'):
            with self.new() as owned:
                (owned.path / 'file').write_bytes(b'own')
                raise RuntimeError('own body failure')
        self.assertFalse(owned.path.exists())
        self.assertEqual(owned.state, 'REMOVED')

    def test_symlink_descendants_do_not_touch_own_control_target(self):
        target = self.root / 'control'; target.mkdir()
        (target / 'keep').write_bytes(b'must survive')
        with self.new() as owned:
            (owned.path / 'alias').symlink_to(target, target_is_directory=True)
            (owned.path / 'file-alias').symlink_to(target / 'keep')
        self.assertEqual((target / 'keep').read_bytes(), b'must survive')

    def test_hardlink_unlink_preserves_other_name(self):
        target = self.root / 'keep'; target.write_bytes(b'hardlink control')
        with self.new() as owned:
            os.link(target, owned.path / 'alias')
        self.assertEqual(target.read_bytes(), b'hardlink control')
        self.assertEqual(target.stat().st_nlink, 1)

    def test_fifo_is_removed_without_opening_or_blocking(self):
        with self.new() as owned:
            os.mkfifo(owned.path / 'own-fifo', 0o600)
        self.assertEqual(owned.state, 'REMOVED')

    def test_replaced_root_is_retained_without_deleting_replacement(self):
        with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_IDENTITY_CHANGED'):
            with self.new() as owned:
                (owned.path / 'original').write_bytes(b'original')
                moved = self.parent / 'retained-original'
                owned.path.rename(moved)
                owned.path.mkdir(mode=0o700)
                (owned.path / 'replacement').write_bytes(b'not this instance')
        self.assertEqual((moved / 'original').read_bytes(), b'original')
        self.assertEqual((owned.path / 'replacement').read_bytes(), b'not this instance')
        self.assertIsNone(owned.observation)
        self.assertEqual(owned.state, 'FAILED')

    def test_symlink_root_replacement_is_not_followed(self):
        target = self.root / 'target'; target.mkdir(); (target / 'keep').write_bytes(b'keep')
        with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_IDENTITY_CHANGED'):
            with self.new() as owned:
                owned.path.rename(self.parent / 'retained')
                owned.path.symlink_to(target, target_is_directory=True)
        self.assertEqual((target / 'keep').read_bytes(), b'keep')
        self.assertTrue(owned.path.is_symlink())

    def test_parent_replacement_is_rejected_without_sweeping_either_tree(self):
        with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_PARENT_CHANGED'):
            with self.new() as owned:
                (owned.path / 'keep').write_bytes(b'original')
                self.parent.rename(self.root / 'retained-parent')
                self.parent.mkdir()
                (self.parent / 'keep').write_bytes(b'replacement parent')
        self.assertEqual((self.root / 'retained-parent' / owned.path.name / 'keep').read_bytes(), b'original')
        self.assertEqual((self.parent / 'keep').read_bytes(), b'replacement parent')

    def test_unobserved_external_removal_is_not_claimed_as_own_cleanup(self):
        with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_CLEANUP_FAILED'):
            with self.new() as owned:
                owned.path.rmdir()
        self.assertIsNone(owned.observation)

    def test_changed_root_privacy_is_rejected(self):
        with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_PRIVACY_CHANGED'):
            with self.new() as owned:
                (owned.path / 'keep').write_bytes(b'kept')
                owned.path.chmod(0o755)
        self.assertEqual((owned.path / 'keep').read_bytes(), b'kept')

    def test_declared_unlink_fault_is_not_silenced(self):
        owned = self.new(); owned.__enter__()
        (owned.path / 'keep').write_bytes(b'kept')
        with patch.object(workspace.os, 'unlink', side_effect=PermissionError('declared fault')):
            with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_CLEANUP_FAILED'):
                owned.cleanup()
        self.assertEqual((owned.path / 'keep').read_bytes(), b'kept')
        self.assertIsNone(owned.observation)
        self.assertIsNone(owned._root_fd); self.assertIsNone(owned._parent_fd)

    def test_declared_noop_tree_removal_cannot_approve_cleanup(self):
        owned = self.new(); owned.__enter__(); (owned.path / 'nested').mkdir()
        (owned.path / 'nested' / 'keep').write_bytes(b'kept')
        with patch.object(workspace.shutil, 'rmtree', return_value=None):
            with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_CLEANUP_FAILED'):
                owned.cleanup()
        self.assertIsNone(owned.observation)
        self.assertTrue((owned.path / 'nested' / 'keep').exists())

    def test_reappearance_is_rejected_without_deletion(self):
        with self.new() as owned:
            pass
        owned.path.mkdir(mode=0o700); (owned.path / 'keep').write_bytes(b'recreated')
        with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_REAPPEARED'):
            owned.confirm_removed()
        self.assertEqual((owned.path / 'keep').read_bytes(), b'recreated')

    def test_second_cleanup_never_removes_recreated_path(self):
        with self.new() as owned:
            pass
        owned.path.mkdir(mode=0o700); (owned.path / 'keep').write_bytes(b'recreated')
        owned.cleanup()
        self.assertEqual((owned.path / 'keep').read_bytes(), b'recreated')

    def test_context_is_single_use(self):
        with self.new() as owned:
            pass
        with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_SINGLE_USE'):
            owned.__enter__()
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_invalid_purpose_or_exclusions_do_not_create_directories(self):
        for value in ('../elsewhere', '', 'arbitrary', None, True):
            with self.subTest(value=value), self.assertRaises(workspace.WorkspaceError):
                self.new(value)
        with self.assertRaises(workspace.WorkspaceError):
            self.new(excluded=[self.root])
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_excluded_input_or_output_tree_is_not_used_for_work(self):
        with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_EXCLUDED_TREE'):
            with self.new(excluded=(self.parent,)):
                self.fail('must reject')
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_symlink_temp_parent_is_rejected_before_allocation(self):
        alias = self.root / 'alias'; alias.symlink_to(self.parent, target_is_directory=True)
        with patch.object(workspace.tempfile, 'gettempdir', return_value=str(alias)):
            with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_PARENT_SYMLINK'):
                with self.new():
                    self.fail('must reject')
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_missing_secure_traversal_is_rejected_before_allocation(self):
        with patch.object(workspace.shutil.rmtree, 'avoids_symlink_attacks', False):
            with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_SECURE_IO_REQUIRED'):
                with self.new():
                    self.fail('must reject')
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_no_descriptor_growth_on_success_or_replacement_failure(self):
        before = len(os.listdir('/proc/self/fd'))
        for number in range(8):
            with self.new() as owned:
                (owned.path / 'file').write_bytes(b'own')
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)
        with self.assertRaises(workspace.WorkspaceError):
            with self.new() as owned:
                owned.path.rename(self.parent / 'moved')
                owned.path.mkdir(mode=0o700)
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)

    def _replace_during_cleanup(self, owned, original):
        retained = self.parent / ('retained-' + owned.path.name)
        owned.path.rename(retained); owned.path.mkdir(mode=0o700)
        (owned.path / 'replacement').write_bytes(b'own injected replacement')
        original(owned)

    def test_lost_descriptor_does_not_leak_other_owned_handle(self):
        before = len(os.listdir('/proc/self/fd'))
        owned = self.new(); owned.__enter__()
        os.close(owned._root_fd)  # Explicit loss injection on this test's own FD.
        with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_DESCRIPTOR_OWNERSHIP_LOST'):
            owned.cleanup()
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)
        self.assertIsNone(owned._root_fd); self.assertIsNone(owned._parent_fd)
        self.assertIsNone(owned.observation)
        self.assertEqual(owned.state, 'FAILED')

    def test_reassigned_descriptor_is_not_closed_as_the_original(self):
        before = len(os.listdir('/proc/self/fd'))
        control = self.root / 'descriptor-control'; control.write_bytes(b'new owned descriptor')
        owned = self.new(); owned.__enter__(); reassigned = owned._root_fd
        other = os.open(control, os.O_RDONLY)
        try:
            os.dup2(other, reassigned)  # Explicitly replace our own descriptor.
        finally:
            os.close(other)
        try:
            with self.assertRaisesRegex(workspace.WorkspaceError, 'WORKSPACE_DESCRIPTOR_OWNERSHIP_LOST'):
                owned.cleanup()
            self.assertEqual(os.read(reassigned, 64), b'new owned descriptor')
            self.assertIsNone(owned._parent_fd)
            self.assertIsNone(owned.observation)
            self.assertTrue(owned.path.is_dir())
        finally:
            os.close(reassigned)  # The control, not Workspace, owns this replacement.
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)

    def _consumer_blocks_replacement(self, module, command):
        digest = quality.sha(canonical(quality.source_snapshot()))
        output = self.root / 'rejected-output'
        original = workspace.Workspace.cleanup
        def replaced(owned):
            self._replace_during_cleanup(owned, original)
        console = io.StringIO()
        with patch.object(workspace.Workspace, 'cleanup', replaced), redirect_stdout(console):
            status = module.main([command, '--source-digest', digest, '--out', str(output)])
        self.assertEqual(status, 2)
        self.assertFalse(output.exists())
        self.assertNotIn(str(self.root), console.getvalue())
        self.assertIn('REJECTED', json.loads(console.getvalue())['status'])
        replacements = list(self.parent.glob('superhunter-*/replacement'))
        self.assertEqual(len(replacements), 1)
        self.assertEqual(replacements[0].read_bytes(), b'own injected replacement')

    def test_capture_blocks_publication_after_actual_root_replacement(self):
        self._consumer_blocks_replacement(capture, 'capture-owned-boundary')

    def test_diagnosis_blocks_publication_after_actual_root_replacement(self):
        self._consumer_blocks_replacement(diagnosis, 'diagnose-owned-boundary')

    def test_both_real_consumers_remove_workspace_before_publishing(self):
        digest = quality.sha(canonical(quality.source_snapshot()))
        created = []
        original = workspace.Workspace.__enter__
        def observed(owned):
            result = original(owned); created.append(owned); return result
        with patch.object(workspace.Workspace, '__enter__', observed):
            capture.create(self.root / 'capture', source_digest=digest)
            diagnosis.create(self.root / 'diagnosis', source_digest=digest)
        self.assertEqual([item.purpose for item in created], ['capture', 'diagnosis'])
        for item in created:
            self.assertEqual(item.state, 'REMOVED')
            item.confirm_removed()
        self.assertEqual(list(self.parent.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
