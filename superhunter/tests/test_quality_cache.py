"""Own cache controls; stale toy values are not third-party payloads."""
import hashlib
import os
from pathlib import Path
import py_compile
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import quality


class QualityCacheTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def check_stale(self, mode):
        module = self.root/'owned_qa_cache_fixture.py'
        module.write_text('VALUE = 2\n')
        os.utime(module,(1700000000,1700000000))
        cached = self.root/'__pycache__'/f'owned_qa_cache_fixture.{sys.implementation.cache_tag}.pyc'
        py_compile.compile(str(module),cfile=str(cached),doraise=True,invalidation_mode=mode)
        original = cached.read_bytes()
        module.write_text('VALUE = 1\n')
        os.utime(module,(1700000000,1700000000))
        source_hash = hashlib.sha256(module.read_bytes()).hexdigest()
        script = ('import sys; sys.path.insert(0,'+repr(str(self.root))+'); '
                  'import owned_qa_cache_fixture; print(owned_qa_cache_fixture.VALUE)')
        old = subprocess.check_output([sys.executable,'-I','-B','-c',script],text=True,timeout=10)
        command = quality._worker_command(self.root/'work',0,self.root/'fresh')
        prefix = command[:command.index(str(quality.ROOT/'quality_worker.py'))]
        fresh = subprocess.check_output(prefix+['-c',script],text=True,timeout=10)
        self.assertEqual(old.strip(),'2')
        self.assertEqual(fresh.strip(),'1')
        self.assertEqual(hashlib.sha256(module.read_bytes()).hexdigest(),source_hash)
        self.assertEqual(cached.read_bytes(),original)
        self.assertEqual(list((self.root/'fresh').rglob('*.pyc')),[])

    def test_timestamp_cache_cannot_replace_verified_source(self):
        self.check_stale(py_compile.PycInvalidationMode.TIMESTAMP)

    def test_unchecked_hash_cache_cannot_replace_verified_source(self):
        self.check_stale(py_compile.PycInvalidationMode.UNCHECKED_HASH)

    def test_existing_and_redirected_cache_are_not_reused(self):
        cache = self.root/'old'; cache.mkdir(); (cache/'old.pyc').write_bytes(b'owned')
        link = self.root/'redirect'; link.symlink_to(cache,target_is_directory=True)
        for path in (cache,link):
            with self.assertRaises(FileExistsError):
                quality._worker_command(self.root/'work',0,path)
        self.assertEqual((cache/'old.pyc').read_bytes(),b'owned')

    def test_partition_rejection_does_not_create_cache(self):
        for index in (-1,8,True,'0'):
            with self.assertRaises(ValueError):
                quality._worker_command(self.root/'work',index,self.root/'cache')
        self.assertFalse((self.root/'cache').exists())

    def test_real_orchestrator_selects_private_cache_and_cleans_on_timeout(self):
        paths = []
        def timeout(command, **kwargs):
            option = command[command.index('-X')+1]
            path = Path(option.removeprefix('pycache_prefix=')); paths.append(path)
            self.assertEqual(command[:3],[sys.executable,'-I','-B'])
            self.assertIn(str(quality.ROOT/'quality_worker.py'),command)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o700)
            self.assertEqual(list(path.iterdir()),[])
            self.assertEqual(kwargs['timeout'],180)
            self.assertEqual(kwargs['env'],{'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'})
            raise subprocess.TimeoutExpired('fixed QA worker',180)
        with patch.object(quality,'_run_qa_process',side_effect=timeout):
            with self.assertRaises(subprocess.TimeoutExpired):
                quality.run_check(self.root/'result')
        self.assertEqual(len(paths),1)
        self.assertFalse(paths[0].exists())
        self.assertFalse((self.root/'result').exists())
        self.assertTrue((self.root/'result.failure/COMPLETE.json').is_file())


if __name__ == '__main__':
    unittest.main()
