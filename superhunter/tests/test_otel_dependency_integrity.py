"""Owned dependency-tree fixtures; never modify installed third-party packages."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from superhunter import otel_dependency_integrity as integrity
from superhunter import otel_qa


class DependencyIntegrityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        members = {'owned_pkg/__init__.py': b'OWNED = True\n',
                   'owned_pkg/control.py': b'VALUE = 1\n',
                   'owned_single.py': b'VALUE = 2\n'}
        metadata = 'owned_fixture-1.0.dist-info/METADATA'
        for name, raw in {**members, metadata:b'Name: owned-fixture\nVersion: 1.0\n'}.items():
            path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        self.pin = {'version':'1.0', 'wheel_sha256':'a'*64, 'runtime_files':sorted(members),
                    'runtime_sha256':integrity._digest({n:hashlib.sha256(b).hexdigest() for n,b in members.items()}),
                    'metadata_path':metadata,
                    'metadata_sha256':hashlib.sha256((self.root/metadata).read_bytes()).hexdigest()}
        self.pins = {'owned-fixture':self.pin}
        self.dist = SimpleNamespace(version='1.0', locate_file=lambda name:self.root/name)
        p = patch.object(integrity,'PINS',self.pins); p.start(); self.addCleanup(p.stop)
        d = patch.object(integrity,'distribution',return_value=self.dist); d.start(); self.addCleanup(d.stop)

    def check(self):
        return integrity.verify_dependencies()

    def test_exact_owned_bytes_pass_without_trusting_record(self):
        # There is deliberately no installed RECORD file in this fixture.
        self.assertEqual(self.check(), integrity.expected_identity())

    def test_modified_runtime_bytes_rejected_with_unchanged_metadata(self):
        (self.root/'owned_pkg/control.py').write_bytes(b'VALUE = 9\n')
        with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_BYTES'):
            self.check()

    def test_unrecorded_native_shadow_rejected(self):
        (self.root/'owned_single.so').write_bytes(b'OWNED NONEXECUTABLE SHADOW FIXTURE')
        with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_UNEXPECTED_FILE'):
            self.check()

    def test_unrecorded_nested_module_rejected(self):
        (self.root/'owned_pkg/extra.py').write_bytes(b'OWNED = True\n')
        with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_UNEXPECTED_FILE'):
            self.check()

    def test_missing_runtime_file_rejected(self):
        (self.root/'owned_pkg/control.py').unlink()
        with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_INVENTORY'):
            self.check()

    def test_symlinked_file_or_package_directory_rejected(self):
        path = self.root/'owned_pkg/control.py'; raw = path.read_bytes(); path.unlink()
        other = self.root/'outside'; other.write_bytes(raw); path.symlink_to(other)
        with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_SYMLINK'):
            self.check()
        path.unlink(); path.write_bytes(raw)
        package = self.root/'owned_pkg'; moved = self.root/'elsewhere'; package.rename(moved)
        package.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_SYMLINK'):
            self.check()

    def test_metadata_tampering_is_rejected(self):
        (self.root/self.pin['metadata_path']).write_bytes(b'Name: owned-fixture\nVersion: forged\n')
        with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_BYTES'):
            self.check()

    def test_wrong_version_and_platform_are_rejected(self):
        self.dist.version = '1.1'
        with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_VERSION'):
            self.check()
        with patch.object(integrity.platform,'system',return_value='Windows'):
            with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_PLATFORM'):
                self.check()

    def test_mixed_distribution_roots_are_rejected(self):
        other = self.root/'other'; other.mkdir()
        self.pins['owned-other'] = deepcopy(self.pin)
        second = SimpleNamespace(version='1.0', locate_file=lambda name:other/name)
        with patch.object(integrity,'distribution',side_effect=[self.dist,second]):
            with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_MIXED_ROOTS'):
                self.check()

    def test_pin_path_cannot_escape_the_environment(self):
        self.pin['runtime_files'].append('../private.py')
        with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_PIN_PATH'):
            self.check()

    def test_byte_and_file_budgets_fail_closed(self):
        for name, value in (('MAX_FILE_BYTES',1),('MAX_TOTAL_BYTES',1),('MAX_FILES',1)):
            with self.subTest(limit=name), patch.object(integrity,name,value):
                with self.assertRaises(ValueError): self.check()

    def test_cache_payload_is_limited_to_nonexecuted_bytecode(self):
        cache = self.root/'owned_pkg/__pycache__'; cache.mkdir()
        (cache/'control.cpython-312.pyc').write_bytes(b'NOT EXECUTED')
        self.assertEqual(self.check(), integrity.expected_identity())
        (cache/'hidden.py').write_bytes(b'OWNED = True\n')
        with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_CACHE_PAYLOAD'):
            self.check()

    def test_changed_files_during_review_rejected(self):
        original = integrity._inventory; calls = 0
        def inventory(root):
            nonlocal calls
            result = original(root); calls += 1
            if calls == 1:
                (self.root/'owned_pkg/control.py').write_bytes(b'VALUE = 8\n')
            return result
        with patch.object(integrity,'_inventory',side_effect=inventory):
            with self.assertRaisesRegex(ValueError,'OTEL_DEPENDENCY_CHANGED_DURING_REVIEW'):
                self.check()

    def test_failed_byte_integrity_blocks_sdk_admission(self):
        with patch.object(otel_qa,'version',return_value=otel_qa.SDK_VERSION), \
             patch.object(integrity,'verify_dependencies',side_effect=ValueError('private path')):
            result = otel_qa.readiness()
            self.assertEqual(result['status'],'BLOCKED_DEPENDENCY')
            self.assertEqual(result['reason'],'PINNED_DEPENDENCY_INTEGRITY_FAILED')
            self.assertNotIn('private path',repr(result))
            with self.assertRaisesRegex(ValueError,'DEPENDENCY'):
                otel_qa.profile_owned_qa(self.root/'qa',self.root/'telemetry')


if __name__ == '__main__':
    unittest.main()
