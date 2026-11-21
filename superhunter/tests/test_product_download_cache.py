from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest

from superhunter.tools.verified_downloads import acquire


class VerifiedDownloadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.cache = self.root/'cache'
        self.raw = b'pinned public input\n' * 100
        self.digest = hashlib.sha256(self.raw).hexdigest()
        self.calls = 0

    def download(self, path):
        self.calls += 1
        path.write_bytes(self.raw)

    def test_second_session_uses_verified_bytes_without_download(self):
        first, second = self.root/'first', self.root/'second'
        acquire(first, self.digest, self.download, self.cache)
        acquire(second, self.digest, self.download, self.cache)
        self.assertEqual(self.calls, 1)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        first.write_bytes(b'changed session input')
        self.assertEqual((self.cache/self.digest).read_bytes(), self.raw)
        self.assertEqual(second.read_bytes(), self.raw)

    def test_corrupt_or_truncated_cache_never_publishes_a_target(self):
        self.cache.mkdir()
        for bad in (b'wrong bytes', self.raw[:-1]):
            with self.subTest(bytes=len(bad)):
                (self.cache/self.digest).write_bytes(bad)
                with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                    acquire(self.root/'target', self.digest, self.download, self.cache)
                self.assertFalse((self.root/'target').exists())
                self.assertEqual(list(self.root.glob('.verified-*')), [])
        self.assertEqual(self.calls, 0)

    def test_linked_cache_entry_is_rejected(self):
        self.cache.mkdir()
        (self.root/'other').write_bytes(self.raw)
        (self.cache/self.digest).symlink_to(self.root/'other')
        with self.assertRaises(OSError):
            acquire(self.root/'target', self.digest, self.download, self.cache)
        self.assertFalse((self.root/'target').exists())

    def test_wrong_download_is_not_cached_or_published(self):
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            acquire(self.root/'target', self.digest, lambda p: p.write_bytes(b'bad'), self.cache)
        self.assertFalse((self.root/'target').exists())
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_interrupted_download_leaves_no_completed_blob(self):
        def fail(path):
            path.write_bytes(self.raw[:2])
            raise RuntimeError('interrupted')
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            acquire(self.root/'target', self.digest, fail, self.cache)
        self.assertFalse((self.root/'target').exists())
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_concurrent_writers_publish_only_complete_matching_bytes(self):
        barrier = threading.Barrier(2)
        def download(path):
            path.write_bytes(self.raw[:10])
            barrier.wait(timeout=5)
            path.write_bytes(self.raw)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(acquire, self.root/f'target-{i}', self.digest, download, self.cache)
                       for i in range(2)]
            for future in futures:
                future.result()
        for i in range(2):
            self.assertEqual((self.root/f'target-{i}').read_bytes(), self.raw)
        self.assertEqual((self.cache/self.digest).read_bytes(), self.raw)
        self.assertEqual(len(list(self.cache.iterdir())), 1)

    def test_existing_destination_is_not_overwritten(self):
        target = self.root/'target'
        target.write_bytes(b'existing')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            acquire(target, self.digest, self.download, self.cache)
        self.assertEqual(target.read_bytes(), b'existing')

    def test_invalid_digest_and_linked_cache_root_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'invalid download digest'):
            acquire(self.root/'target', '../escape', self.download, self.cache)
        (self.root/'actual-cache').mkdir()
        self.cache.symlink_to(self.root/'actual-cache', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            acquire(self.root/'target', self.digest, self.download, self.cache)
