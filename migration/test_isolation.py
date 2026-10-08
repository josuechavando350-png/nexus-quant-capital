"""Negative boundary tests for the source migration; no certification claims."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('isolation', ROOT/'migration/verify_isolation.py')
isolation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(isolation)


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'repo'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('.git', '__pycache__'))

    def verify(self):
        return isolation.verify(self.root)

    def edit_manifest(self, update):
        p = self.root/'migration/source-manifest.json'
        data = json.loads(p.read_text())
        update(data)
        p.write_text(json.dumps(data))

    def test_snapshot_is_explicitly_not_certification(self):
        result = self.verify()
        self.assertFalse(result['canonical_recertification'])
        self.assertFalse(result['original_objects_checked'])
        self.assertEqual(result['active_workflows'], 0)

    def test_changed_source_byte_fails(self):
        p = self.root/'nqc-census/Cargo.toml'
        p.write_text(p.read_text()+'\n')
        with self.assertRaises(ValueError): self.verify()

    def test_new_active_workflow_fails(self):
        p = self.root/'.github/workflows/publish.yml'
        p.parent.mkdir(parents=True)
        p.write_text('on: push\n')
        with self.assertRaises(ValueError): self.verify()

    def test_client_application_fails(self):
        p = self.root/'apps/client/package.json'
        p.parent.mkdir(parents=True)
        p.write_text('{}')
        with self.assertRaises(ValueError): self.verify()

    def test_unmapped_extra_nqc_file_fails(self):
        (self.root/'ci/nqc-census/unreviewed.py').write_text('print(1)')
        with self.assertRaises(ValueError): self.verify()

    def test_source_repository_cannot_be_relabelled(self):
        self.edit_manifest(lambda m: m.update(source_repository=isolation.TARGET))
        with self.assertRaises(ValueError): self.verify()

    def test_new_repository_id_is_required(self):
        self.edit_manifest(lambda m: m.update(destination_repository_id=isolation.SOURCE_ID))
        with self.assertRaises(ValueError): self.verify()

    def test_omitted_source_mapping_fails(self):
        self.edit_manifest(lambda m: m['files'].pop())
        with self.assertRaises(ValueError): self.verify()

    def test_symlink_cannot_hide_payload(self):
        p = self.root/'migration/link'
        p.symlink_to(self.root/'nqc-census/Cargo.toml')
        with self.assertRaises(ValueError): self.verify()


if __name__ == '__main__':
    unittest.main()
