"""Own process controls; no third-party PID, executable or native target used."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from superhunter import owned_process as runner
from superhunter import owned_quota_cross_evm as cross, owned_quota_execution as execution


class OwnedProcessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def launch(self, command, timeout=5, **streams):
        return runner.run(command, cwd=self.root, env={'LANG': 'C.UTF-8'}, timeout=timeout,
                          stdout=streams.get('stdout', subprocess.DEVNULL),
                          stderr=streams.get('stderr', subprocess.DEVNULL),
                          pass_fds=streams.get('pass_fds', ()))

    def running(self, pid):
        try:
            os.kill(pid, 0)
            raw = Path(f'/proc/{pid}/stat').read_text()
        except (ProcessLookupError, FileNotFoundError):
            return False
        return raw.split(') ', 1)[1].split()[0] not in ('Z', 'X')

    def child_command(self, mode):
        pidfile = self.root / 'owned-child.pid'
        script = ('import os,sys,time,json\nfrom pathlib import Path\n'
            f'p=Path({str(pidfile)!r})\nchild=os.fork()\n'
            'if child==0:\n p.write_text(str(os.getpid()))\n time.sleep(20)\n os._exit(0)\n'
            'for _ in range(300):\n if p.exists(): break\n time.sleep(.01)\n'
            + ('time.sleep(20)\n' if mode == 'timeout' else
               'print(json.dumps({}),flush=True)\n' if mode == 'eels' else f'sys.exit({mode})\n'))
        return pidfile, [sys.executable, '-I', '-B', '-c', script]

    def assert_child_stopped(self, pidfile):
        pid = int(pidfile.read_text())
        for _ in range(50):
            if not self.running(pid):
                break
            time.sleep(.01)
        self.assertFalse(self.running(pid), 'own child still running')

    def cleanup_child(self, pidfile):
        if pidfile.exists():
            pid = int(pidfile.read_text())
            if self.running(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_leader_is_waitable_during_group_cleanup_then_reaped(self):
        pidfile, command = self.child_command(0)
        killed = []
        original = os.killpg
        def observed(pid, sig):
            info = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            self.assertIsNotNone(info)
            self.assertEqual(info.si_pid, pid)
            self.assertEqual(info.si_status, 0)
            killed.append(pid)
            return original(pid, sig)
        try:
            with patch.object(runner.os, 'killpg', side_effect=observed):
                self.assertEqual(self.launch(command).returncode, 0)
            self.assert_child_stopped(pidfile)
            self.assertEqual(len(killed), 1)
            with self.assertRaises(ChildProcessError):
                os.waitpid(killed[0], os.WNOHANG)
        finally:
            self.cleanup_child(pidfile)

    def test_nonzero_exit_preserved_and_own_child_stopped(self):
        pidfile, command = self.child_command(7)
        try:
            self.assertEqual(self.launch(command).returncode, 7)
            self.assert_child_stopped(pidfile)
        finally:
            self.cleanup_child(pidfile)

    def test_timeout_stops_owned_group_before_reaping(self):
        pidfile, command = self.child_command('timeout')
        try:
            with self.assertRaises(subprocess.TimeoutExpired) as stopped:
                self.launch(command, timeout=1)
            self.assertEqual(stopped.exception.timeout, 1)
            self.assert_child_stopped(pidfile)
        finally:
            self.cleanup_child(pidfile)

    def test_eels_normal_exit_cleans_own_child(self):
        pidfile, command = self.child_command('eels')
        try:
            with patch.object(cross.previous, '_python_command', return_value=command):
                self.assertEqual(cross._run_eels(self.root / 'UNIT-ONLY', '0' * 64), {})
            self.assert_child_stopped(pidfile)
        finally:
            self.cleanup_child(pidfile)

    def fake_process(self):
        process = MagicMock()
        process.pid, process.returncode = 12345, 0
        process.wait.return_value = 0
        return process

    def test_interrupt_kills_group_before_reaping(self):
        process = self.fake_process()
        order = []
        process.wait.side_effect = lambda: order.append('reap') or -9
        with patch.object(runner.subprocess, 'Popen', return_value=process), \
             patch.object(runner.os, 'waitid', return_value=None), \
             patch.object(runner.os, 'getpgid', return_value=12345), \
             patch.object(runner.os, 'getsid', return_value=12345), \
             patch.object(runner.time, 'sleep', side_effect=KeyboardInterrupt()), \
             patch.object(runner.os, 'killpg', side_effect=lambda *_: order.append('kill-group')):
            with self.assertRaises(KeyboardInterrupt):
                self.launch(['UNIT-ONLY'])
        self.assertEqual(order, ['kill-group', 'reap'])

    def test_lost_child_ownership_never_signals_numeric_group(self):
        process = self.fake_process()
        with patch.object(runner.subprocess, 'Popen', return_value=process), \
             patch.object(runner.os, 'waitid', side_effect=ChildProcessError()), \
             patch.object(runner.os, 'killpg') as killed:
            with self.assertRaisesRegex(runner.OwnedProcessError, 'OWNERSHIP_LOST'):
                self.launch(['UNIT-ONLY'])
        killed.assert_not_called()
        process.kill.assert_not_called()
        process.wait.assert_called_once_with()

    def test_wrong_session_does_not_signal_other_group(self):
        for group, session in ((999, 12345), (12345, 999)):
            process = self.fake_process()
            with self.subTest(group=group, session=session), \
                 patch.object(runner.subprocess, 'Popen', return_value=process), \
                 patch.object(runner.os, 'waitid', return_value=SimpleNamespace(si_pid=12345)), \
                 patch.object(runner.os, 'getpgid', return_value=group), \
                 patch.object(runner.os, 'getsid', return_value=session), \
                 patch.object(runner.os, 'killpg') as killed:
                with self.assertRaisesRegex(runner.OwnedProcessError, 'SESSION_IDENTITY'):
                    self.launch(['UNIT-ONLY'])
            killed.assert_not_called()
            process.kill.assert_called_once_with()
            process.wait.assert_called_once_with()

    def test_group_cleanup_failure_cannot_return_success(self):
        process = self.fake_process()
        with patch.object(runner.subprocess, 'Popen', return_value=process), \
             patch.object(runner.os, 'waitid', return_value=SimpleNamespace(si_pid=12345)), \
             patch.object(runner.os, 'getpgid', return_value=12345), \
             patch.object(runner.os, 'getsid', return_value=12345), \
             patch.object(runner.os, 'killpg', side_effect=PermissionError()):
            with self.assertRaises(PermissionError): self.launch(['UNIT-ONLY'])
        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with()

    def test_cleanup_observation_error_stops_only_owned_leader(self):
        process = self.fake_process()
        with patch.object(runner.subprocess, 'Popen', return_value=process), \
             patch.object(runner.os, 'waitid', side_effect=[SimpleNamespace(si_pid=12345), OSError('UNIT-ONLY')]), \
             patch.object(runner.os, 'killpg') as killed:
            with self.assertRaises(OSError): self.launch(['UNIT-ONLY'])
        killed.assert_not_called()
        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with()

    def test_invalid_wall_budget_rejected_before_launch(self):
        with patch.object(runner.subprocess, 'Popen') as launch:
            for value in (0, -1, 181, True, None, '180', float('nan'), float('inf')):
                with self.subTest(value=value), self.assertRaises(runner.OwnedProcessError):
                    self.launch(['UNIT-ONLY'], timeout=value)
        launch.assert_not_called()

    def test_late_observed_exit_does_not_bypass_deadline(self):
        process = self.fake_process()
        with patch.object(runner.subprocess, 'Popen', return_value=process), \
             patch.object(runner.os, 'waitid', return_value=SimpleNamespace(si_pid=12345)), \
             patch.object(runner.os, 'getpgid', return_value=12345), \
             patch.object(runner.os, 'getsid', return_value=12345), \
             patch.object(runner.time, 'monotonic', side_effect=[0, 181]), \
             patch.object(runner.os, 'killpg') as killed:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.launch(['UNIT-ONLY'], timeout=180)
        killed.assert_called_once_with(12345, signal.SIGKILL)
        process.wait.assert_called_once_with()

    def test_unsupported_waitid_platform_rejected_before_launch(self):
        with patch.object(runner.sys, 'platform', 'unsupported'), \
             patch.object(runner.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(runner.OwnedProcessError, 'LINUX_WAITID_REQUIRED'):
                self.launch(['UNIT-ONLY'])
        launch.assert_not_called()

    def test_launch_failure_never_signals_a_group(self):
        with patch.object(runner.subprocess, 'Popen', side_effect=OSError('UNIT-ONLY')), \
             patch.object(runner.os, 'killpg') as killed:
            with self.assertRaises(OSError): self.launch(['UNIT-ONLY'])
        killed.assert_not_called()

    def test_borrowed_descriptor_stays_open_in_caller(self):
        with tempfile.TemporaryFile() as target:
            command = [sys.executable, '-I', '-B', '-c',
                       f'import os; os.write({target.fileno()}, b"OWNED-FD")']
            self.assertEqual(self.launch(command, pass_fds=(target.fileno(),)).returncode, 0)
            os.fstat(target.fileno())
            target.seek(0)
            self.assertEqual(target.read(), b'OWNED-FD')

    def test_streams_remain_owned_by_caller_and_stdin_is_closed(self):
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            command = [sys.executable, '-I', '-B', '-c',
                       'import sys; assert sys.stdin.buffer.read()==b""; print("OWNED-OUT"); print("OWNED-ERR",file=sys.stderr)']
            self.assertEqual(self.launch(command, stdout=out, stderr=err).returncode, 0)
            out.seek(0); err.seek(0)
            self.assertEqual(out.read(), b'OWNED-OUT\n')
            self.assertEqual(err.read(), b'OWNED-ERR\n')

    def test_native_timeout_preserves_typed_diagnostic(self):
        with patch.object(execution.owned_process, 'run',
                          side_effect=subprocess.TimeoutExpired(['UNIT-ONLY'], 15)) as run:
            with self.assertRaisesRegex(execution.EVMError, '^EVM_PROCESS_TIMEOUT$'):
                execution._run_bounded(['UNIT-ONLY'], self.root, None, None, 7)
        self.assertEqual(run.call_args.kwargs['timeout'], 15)
        self.assertEqual(run.call_args.kwargs['pass_fds'], (7,))

    def test_native_transport_preserves_nonzero_return_code(self):
        with patch.object(execution.owned_process, 'run',
                          return_value=subprocess.CompletedProcess(['UNIT-ONLY'], 7)):
            self.assertEqual(execution._run_bounded(['UNIT-ONLY'], self.root, None, None, 7), 7)


if __name__ == '__main__':
    unittest.main()
