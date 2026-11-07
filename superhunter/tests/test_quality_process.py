"""Own forked sleepers verify QA cleanup; no third-party process is signalled."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock,patch

from superhunter import quality
from superhunter import owned_process


class QualityProcessTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)

    def running(self,pid):
        try:
            os.kill(pid,0)
            raw=Path(f'/proc/{pid}/stat').read_text()
        except (ProcessLookupError,FileNotFoundError):return False
        return raw.split(') ',1)[1].split()[0] not in ('Z','X')

    def child_control(self,mode):
        pidfile=self.root/'owned-child.pid'
        script=('import os,sys,time\nfrom pathlib import Path\n'
            f'p=Path({str(pidfile)!r})\nchild=os.fork()\n'
            'if child==0:\n p.write_text(str(os.getpid()))\n time.sleep(20)\n os._exit(0)\n'
            'for _ in range(300):\n'
            ' if p.exists(): break\n time.sleep(.01)\n'
            + ('time.sleep(20)\n' if mode=='timeout' else f'sys.exit({mode})\n'))
        command=[sys.executable,'-I','-B','-c',script]
        try:
            if mode=='timeout':
                with self.assertRaises(subprocess.TimeoutExpired) as stopped:
                    quality._run_qa_process(command,cwd=self.root,env={'LANG':'C.UTF-8'},timeout=1)
                self.assertEqual(stopped.exception.timeout,1)
            else:
                result=quality._run_qa_process(command,cwd=self.root,env={'LANG':'C.UTF-8'},timeout=5)
                self.assertEqual(result.returncode,mode)
            pid=int(pidfile.read_text())
            for _ in range(50):
                if not self.running(pid):break
                time.sleep(.01)
            self.assertFalse(self.running(pid),'own same-group child still running')
        finally:
            if pidfile.exists():
                pid=int(pidfile.read_text())
                if self.running(pid):
                    try:os.kill(pid,signal.SIGKILL)
                    except ProcessLookupError:pass

    def test_timeout_stops_own_same_group_child(self):self.child_control('timeout')

    def test_success_also_stops_own_remaining_child(self):self.child_control(0)

    def test_nonzero_exit_is_preserved_and_child_stopped(self):self.child_control(7)

    def test_console_output_is_not_accumulated(self):
        code='import os; [(os.write(1,b"x"*4096),os.write(2,b"y"*4096)) for _ in range(256)]'
        result=quality._run_qa_process([sys.executable,'-I','-B','-c',code],
            cwd=self.root,env={'LANG':'C.UTF-8'},timeout=5)
        self.assertEqual(result.returncode,0);self.assertIsNone(result.stdout);self.assertIsNone(result.stderr)

    def test_interrupt_cleans_group_and_reaps_before_propagating(self):
        process=MagicMock();process.pid=12345;process.wait.return_value=-9
        with patch.object(owned_process.subprocess,'Popen',return_value=process), \
             patch.object(owned_process.os,'waitid',return_value=None), \
             patch.object(owned_process.os,'getpgid',return_value=12345), \
             patch.object(owned_process.os,'getsid',return_value=12345), \
             patch.object(owned_process.time,'sleep',side_effect=KeyboardInterrupt()), \
             patch.object(owned_process.os,'killpg') as kill:
            with self.assertRaises(KeyboardInterrupt):
                quality._run_qa_process(['fixed'],cwd=self.root,env={},timeout=180)
            kill.assert_called_once_with(12345,signal.SIGKILL)
            self.assertEqual(process.wait.call_count,1)

    def test_failed_group_cleanup_cannot_report_success(self):
        process=MagicMock();process.pid=12345;process.wait.return_value=0
        with patch.object(owned_process.subprocess,'Popen',return_value=process), \
             patch.object(owned_process.os,'waitid',return_value=None), \
             patch.object(owned_process.os,'getpgid',return_value=12345), \
             patch.object(owned_process.os,'getsid',return_value=12345), \
             patch.object(owned_process.time,'sleep',side_effect=KeyboardInterrupt()), \
             patch.object(owned_process.os,'killpg',side_effect=PermissionError()):
            with self.assertRaises(PermissionError):
                quality._run_qa_process(['fixed'],cwd=self.root,env={},timeout=180)
            process.kill.assert_called_once_with()
            self.assertEqual(process.wait.call_count,1)


if __name__ == '__main__':unittest.main()
