"""Native controls run only in new dedicated children, never the QA process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from superhunter import owned_compute_guard as guard
from superhunter.safe_io import canonical

ROOT = Path(__file__).resolve().parents[2]


class ComputeGuardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root/'owned-compute-control').write_bytes(guard.MARKER_BYTES)

    def run_child(self, before='', after='', *, stdin=None, pass_fds=()):
        script = ('import ctypes,errno,hashlib,json,os,sys,threading\nfrom pathlib import Path\n'
                  f'sys.path.insert(0,{str(ROOT)!r})\n'
                  'from superhunter import owned_compute_guard as guard\n'
                  'from superhunter.safe_io import canonical\n'+before+'\n'
                  'try:\n proof=guard.install(Path.cwd()/"owned-compute-control")\n'
                  'except (OSError,ValueError) as error:\n'
                  ' print(json.dumps({"error":str(error) if type(error) is guard.ComputeGuardError else "SYSTEM_ERROR"}),flush=True)\n'
                  ' raise SystemExit(2)\n'+after+'\n'
                  'sys.stdout.buffer.write(canonical({"proof":proof}))\n')
        result = subprocess.run([sys.executable, '-I', '-B', '-c', script], cwd=self.root,
            stdin=subprocess.DEVNULL if stdin is None else stdin, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=10, pass_fds=pass_fds,
            env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'})
        self.assertEqual(result.stderr, b'')
        self.assertNotIn(str(self.root).encode(), result.stdout)
        return result.returncode, json.loads(result.stdout)

    def test_actual_filter_controls_and_preloaded_computation(self):
        code, result = self.run_child(after='assert hashlib.sha256(b"fixed own data").hexdigest()=="286f9dc8198694fa60875bead1ebe13068c2ddf5be18f7550bd6dcb47aa4aeec"')
        self.assertEqual(code, 0)
        proof = result['proof']
        self.assertEqual(proof, guard.expected_proof(proof['socket_controls_before_filter']))
        self.assertEqual((self.root/'owned-compute-control').read_bytes(), guard.MARKER_BYTES)
        self.assertFalse((self.root/'owned-compute-directory-control').exists())
        self.assertFalse(proof['input_acquisition_inside_filter'])

    def test_extra_inherited_descriptor_is_rejected(self):
        descriptor = os.open(self.root/'owned-compute-control', os.O_RDONLY)
        try:
            code, result = self.run_child(pass_fds=(descriptor,))
        finally:
            os.close(descriptor)
        self.assertEqual((code, result), (2, {'error': 'COMPUTE_EXTRA_DESCRIPTOR'}))

    def test_regular_file_stdin_is_rejected(self):
        with (self.root/'owned-compute-control').open('rb') as stream:
            code, result = self.run_child(stdin=stream)
        self.assertEqual((code, result), (2, {'error': 'COMPUTE_STDIN'}))

    def test_existing_thread_is_rejected_before_filter(self):
        before = ('event=threading.Event()\n'
                  'thread=threading.Thread(target=event.wait,daemon=True)\nthread.start()')
        code, result = self.run_child(before=before)
        self.assertEqual((code, result), (2, {'error': 'COMPUTE_SINGLE_THREAD_REQUIRED'}))

    def test_changed_control_bytes_are_rejected(self):
        (self.root/'owned-compute-control').write_bytes(b'changed own marker')
        code, result = self.run_child()
        self.assertEqual((code, result), (2, {'error': 'COMPUTE_CONTROL_BYTES'}))

    def test_symlink_control_is_rejected(self):
        marker = self.root/'owned-compute-control'
        marker.rename(self.root/'original')
        marker.symlink_to(self.root/'original')
        code, result = self.run_child()
        self.assertEqual((code, result), (2, {'error': 'COMPUTE_CONTROL_PATH'}))

    def test_real_anonymous_mapping_and_denied_mapping_variants(self):
        before = ('libc=ctypes.CDLL(None,use_errno=True)\n'
                  'libc.mmap.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_long]\n'
                  'libc.mmap.restype=ctypes.c_void_p\n'
                  'libc.mprotect.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]\n'
                  'libc.munmap.argtypes=[ctypes.c_void_p,ctypes.c_size_t]\n')
        after = ('failed=ctypes.c_void_p(-1).value\n'
                 'address=libc.mmap(None,131072,3,0x22,-1,0)\nassert address not in (None,failed)\n'
                 'ctypes.memset(address,65,131072)\nassert ctypes.string_at(address,8)==b"AAAAAAAA"\n'
                 'assert libc.mprotect(address,131072,1)==0\n'
                 'assert libc.mprotect(address,131072,5)==-1 and ctypes.get_errno()==errno.EPERM\n'
                 'assert libc.munmap(address,131072)==0\n'
                 'for protection,flags,descriptor in ((5,0x22,-1),(1,2,0),(1,0x22,0)):\n'
                 ' assert libc.mmap(None,4096,protection,flags,descriptor,0)==failed\n'
                 ' assert ctypes.get_errno()==errno.EPERM\n')
        code, result = self.run_child(before=before, after=after)
        self.assertEqual(code, 0)

    def test_descriptor_duplication_and_new_file_creation_denied(self):
        after = ('for action in (lambda:os.dup(1),lambda:os.open("new-own-file",os.O_WRONLY|os.O_CREAT,0o600)):\n'
                 ' try: action()\n'
                 ' except OSError as error: assert error.errno==errno.EPERM\n'
                 ' else: raise AssertionError("unexpected descriptor acquisition")\n')
        code, result = self.run_child(after=after)
        self.assertEqual(code, 0)
        self.assertFalse((self.root/'new-own-file').exists())

    def test_low_library_loading_limit_does_not_silently_fallback(self):
        code, result = self.run_child(before='import resource\nresource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536))')
        self.assertEqual((code, result), (2, {'error': 'SYSTEM_ERROR'}))

    def test_socket_baseline_has_closed_values_and_scope(self):
        for baseline in ({}, {'unix_socket': 'AVAILABLE', 'ipv4_socket': True},
                         {'unix_socket': 'AVAILABLE', 'ipv4_socket': 'UNKNOWN'}):
            with self.subTest(baseline=baseline), self.assertRaisesRegex(ValueError, 'COMPUTE_SOCKET_BASELINE'):
                guard.expected_proof(baseline)
        proof = guard.expected_proof({'unix_socket': 'AVAILABLE', 'ipv4_socket': 'ALREADY_DENIED_EPERM'})
        self.assertFalse(proof['preexisting_socket_denial_attributed_to_this_filter'])


if __name__ == '__main__':
    unittest.main()
