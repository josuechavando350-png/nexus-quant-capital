"""Exercise source boundaries on disposable copies, never legacy originals."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from superhunter import repository_boundary as boundary

SOURCE = Path(__file__).resolve().parents[2]


class RepositoryBoundaryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)/'repo'
        shutil.copytree(SOURCE,self.root,ignore=shutil.ignore_patterns('.git','__pycache__'))

    def review(self):
        return boundary.review(self.root)

    def test_extended_repository_preserves_legacy_without_recertifying(self):
        result = self.review()
        self.assertEqual(result['status'],'REPOSITORY_BOUNDARY_PASS')
        self.assertEqual(result['historical_files_checked'],642)
        self.assertEqual(result['historical_tree_pins'],boundary.HISTORICAL_TREES)
        self.assertGreater(result['superhunter_files_reviewed_for_boundary'],200)
        self.assertEqual(result['active_workflows'],0)
        self.assertTrue(result['legacy_verifier_unchanged'])
        for key in ('canonical_recertification','original_source_objects_checked',
                    'runtime_isolation_proved','full_security_review'):
            self.assertIs(result[key],False)

    def test_changed_legacy_byte_rejected(self):
        path = self.root/'nqc-census/Cargo.toml'
        path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(boundary.BoundaryError,'HISTORICAL_TREE_CHANGED'):
            self.review()

    def test_changed_legacy_mode_rejected(self):
        path = self.root/'migration/source-manifest.json'
        path.chmod(path.stat().st_mode ^ 0o100)
        with self.assertRaisesRegex(boundary.BoundaryError,'HISTORICAL_TREE_CHANGED'):
            self.review()

    def test_extra_or_missing_legacy_file_rejected(self):
        extra = self.root/'ci/unreviewed.py'; extra.write_text('OWNED_TEST = 1\n')
        with self.assertRaises(boundary.BoundaryError): self.review()
        extra.unlink()
        (self.root/'migration/VALIDATION.md').unlink()
        with self.assertRaisesRegex(boundary.BoundaryError,'HISTORICAL_TREE_CHANGED'):
            self.review()

    def test_original_verifier_cannot_be_silently_replaced(self):
        (self.root/'migration/verify_isolation.py').write_text('print("PASS")\n')
        with self.assertRaisesRegex(boundary.BoundaryError,'HISTORICAL_TREE_CHANGED'):
            self.review()

    def test_root_policy_cannot_be_silently_replaced(self):
        (self.root/'AGENTS.md').write_text('Different policy\n')
        with self.assertRaisesRegex(boundary.BoundaryError,'ROOT_POLICY_CHANGED'):
            self.review()

    def test_reviewed_appendix_preserves_original_policy_pin(self):
        result = self.review()
        self.assertTrue(result['original_root_policy_preserved'])
        self.assertEqual(result['reviewed_agents_appendix_sha256'], boundary.AGENTS_APPENDIX_SHA256)
        path = self.root/'AGENTS.md'
        original = path.read_bytes()[:boundary.AGENTS_ORIGINAL_BYTES]
        self.assertEqual(boundary.git_object('blob', original), boundary.ROOT_FILES['AGENTS.md'])
        path.write_bytes(original)
        self.assertIsNone(self.review()['reviewed_agents_appendix_sha256'])

    def test_original_policy_edit_rejected_even_with_reviewed_appendix(self):
        path = self.root/'AGENTS.md'; raw = path.read_bytes()
        path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
        with self.assertRaisesRegex(boundary.BoundaryError, 'ROOT_POLICY_CHANGED'):
            self.review()

    def test_changed_truncated_or_extra_appendix_rejected(self):
        path = self.root/'AGENTS.md'; raw = path.read_bytes()
        n = boundary.AGENTS_ORIGINAL_BYTES
        for changed in (raw[:n] + bytes([raw[n] ^ 1]) + raw[n+1:], raw[:-1], raw+b'\n'):
            with self.subTest(size=len(changed)):
                path.write_bytes(changed)
                with self.assertRaisesRegex(boundary.BoundaryError, 'ROOT_POLICY_CHANGED'):
                    self.review()

    def test_active_workflow_rejected_at_root_and_nested(self):
        for prefix in ('','superhunter/'):
            path = self.root/(prefix+'.github/workflows/new.yml')
            path.parent.mkdir(parents=True); path.write_text('on: push\n')
            with self.assertRaises(boundary.BoundaryError): self.review()
            shutil.rmtree(self.root/(prefix+'.github'))

    def test_client_tree_rejected(self):
        path = self.root/'apps/client/package.json'
        path.parent.mkdir(parents=True); path.write_text('{}')
        with self.assertRaises(boundary.BoundaryError): self.review()

    def test_native_dependency_and_unreviewed_root_rejected(self):
        binary = self.root/'superhunter/engine.so'; binary.write_bytes(b'owned dummy')
        with self.assertRaisesRegex(boundary.BoundaryError,'UNREVIEWED_SUPERHUNTER_PAYLOAD'):
            self.review()
        binary.unlink()
        (self.root/'unreviewed.py').write_text('OWNED_TEST = 1\n')
        with self.assertRaisesRegex(boundary.BoundaryError,'UNREVIEWED_ROOT_FILE'):
            self.review()

    def test_symlink_file_directory_and_cache_rejected(self):
        for relative,target in (('superhunter/link.py',self.root/'README.md'),
                                ('superhunter/link',self.root/'migration'),
                                ('superhunter/__pycache__/hidden.pyc',self.root/'README.md')):
            link = self.root/relative; link.parent.mkdir(parents=True,exist_ok=True)
            link.symlink_to(target)
            with self.assertRaises(boundary.BoundaryError): self.review()
            link.unlink()

    def test_cache_is_explicitly_excluded_from_source_claim(self):
        previous = self.review()
        path = self.root/'superhunter/__pycache__/owned.cpython-312.pyc'
        path.parent.mkdir(); path.write_bytes(b'generated cache fixture')
        result = self.review()
        self.assertEqual(result['ignored_python_cache_files'],1)
        self.assertEqual(result['source_inventory_sha256'],previous['source_inventory_sha256'])
        self.assertIs(result['runtime_isolation_proved'],False)
        (path.parent/'hidden.json').write_text('{}')
        with self.assertRaisesRegex(boundary.BoundaryError,'UNREVIEWED_CACHE_PAYLOAD'):
            self.review()

    def test_reviewed_continuity_document_allowed_but_not_executable(self):
        path = self.root/'SUPERHUNTER_STATUS.md'; path.write_text('# Local status\n')
        self.assertIn(path.name,self.review()['root_documents'])
        path.chmod(0o755)
        with self.assertRaisesRegex(boundary.BoundaryError,'EXECUTABLE_ROOT_DOCUMENT'):
            self.review()

    def test_new_source_mode_requires_review(self):
        path = self.root/'superhunter/owned_extra.py'; path.write_text('OWNED_TEST = 1\n')
        path.chmod(0o755)
        with self.assertRaisesRegex(boundary.BoundaryError,'EXECUTABLE_SOURCE_MODE'):
            self.review()

    def test_concurrent_source_change_rejected(self):
        original = boundary._capture
        count = 0
        def captured(root):
            nonlocal count
            result = original(root); count += 1
            if count == 1:
                (root/'superhunter/changed-during-review.md').write_text('new source boundary\n')
            return result
        with patch.object(boundary,'_capture',side_effect=captured):
            with self.assertRaisesRegex(boundary.BoundaryError,'REPOSITORY_CHANGED_DURING_REVIEW'):
                self.review()

    def test_budgets_fail_closed(self):
        with patch.object(boundary,'MAX_FILES',1):
            with self.assertRaises(boundary.BoundaryError): self.review()
        with patch.object(boundary,'MAX_FILE_BYTES',1):
            with self.assertRaisesRegex(boundary.BoundaryError,'FILE_SIZE_BUDGET'):
                self.review()

    def test_cli_failure_uses_fixed_diagnostic(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = boundary.main(['--root',str(self.root/'private-missing-repo')])
        self.assertEqual(code,2)
        self.assertNotIn('private-missing-repo',output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['status'],'REPOSITORY_BOUNDARY_BLOCKED')


if __name__ == '__main__':
    unittest.main()
