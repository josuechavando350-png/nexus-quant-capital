"""Negative composition controls keep added workflows/evidence narrowly scoped."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("composition", HERE / "verify_standalone_composition.py")
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nqc-composition-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.repo = self.work / "consumer"
        shutil.copytree(HERE.parent, self.repo)
        self.source = Path(os.environ["NQC_ADAPTER_TEST_SOURCE_STORE"])
        self.env = c.a.environment(self.work)
        self.head, self.tree = c.a.identity(self.repo, self.env)

    def commit(self):
        c.a.git(self.repo, "add", "-A", env=self.env)
        c.a.git(self.repo, "-c", "user.name=Negative control", "-c", "user.email=negative@localhost",
                "commit", "--quiet", "-m", "composition test", env=self.env)
        self.head, self.tree = c.a.identity(self.repo, self.env)

    def verify(self, active=False):
        return c.verify(self.repo, self.source, self.head, self.tree, active)

    def test_inert_reviewed_composition_passes_without_certification(self):
        result = self.verify()
        self.assertEqual(result["baseline_files"], 645)
        self.assertEqual(result["active_workflows"], 0)
        self.assertTrue(result["original_verifier_unchanged"])
        self.assertFalse(result["canonical_recertification"])

    def test_require_active_rejects_inert_proposal(self):
        with self.assertRaisesRegex(c.a.AdapterError, "active reviewed workflow"):
            self.verify(True)

    def test_exact_active_workflow_projection_passes_locally(self):
        target = self.repo / c.WORKFLOW; target.parent.mkdir(parents=True)
        (self.repo / c.INERT_WORKFLOW).rename(target); self.commit()
        self.assertEqual(self.verify(True)["active_workflows"], 1)
        # This writes only a disposable local tree; never a remote workflow.

    def test_unexpected_workflow_rejected(self):
        path = self.repo / ".github/workflows/extra.yml"; path.parent.mkdir(parents=True)
        path.write_text("on: push\njobs: {}\n"); self.commit()
        with self.assertRaisesRegex(c.a.AdapterError, "tracked composition payload"):
            self.verify()

    def test_deployment_workflow_rejected(self):
        path = self.repo / ".github/workflows/deploy.yml"; path.parent.mkdir(parents=True)
        path.write_text("name: deploy\non: push\njobs: {}\n"); self.commit()
        with self.assertRaises(c.a.AdapterError): self.verify()

    def test_added_evidence_rejected(self):
        (self.repo / "migration/evidence/d06/extra.json").write_text("{}"); self.commit()
        with self.assertRaisesRegex(c.a.AdapterError, "tracked composition payload"):
            self.verify()

    def test_changed_seed_rejected_even_with_updated_manifest(self):
        path = self.repo / c.ZIP_PATH
        data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
        manifest = self.repo / c.CONTRACT
        value = json.loads(manifest.read_text()); value["files"][c.ZIP_PATH]["sha256"] = c.a.digest(data)
        manifest.write_text(json.dumps(value)); self.commit()
        with self.assertRaisesRegex(c.a.AdapterError, "original seed ZIP changed"):
            self.verify()

    def test_changed_workflow_rejected_even_with_updated_manifest(self):
        path = self.repo / c.INERT_WORKFLOW
        path.write_text(path.read_text().replace("contents: read", "contents: write"))
        data = path.read_bytes(); manifest = self.repo / c.CONTRACT
        value = json.loads(manifest.read_text()); value["files"][c.WORKFLOW].update(sha256=c.a.digest(data), bytes=len(data))
        manifest.write_text(json.dumps(value)); self.commit()
        with self.assertRaisesRegex(c.a.AdapterError, "reviewed workflow bytes changed"):
            self.verify()

    def test_extra_path_cannot_authorize_itself_in_manifest(self):
        path = self.repo / "migration/unreviewed.py"; path.write_text("print('not allowed')")
        manifest = self.repo / c.CONTRACT; value = json.loads(manifest.read_text())
        value["files"]["migration/unreviewed.py"] = {"sha256": c.a.digest(path.read_bytes()), "bytes": path.stat().st_size, "mode": "100644"}
        manifest.write_text(json.dumps(value)); self.commit()
        with self.assertRaisesRegex(c.a.AdapterError, "addition allowlist changed"):
            self.verify()

    def test_original_verifier_cannot_be_weakened(self):
        path = self.repo / "migration/verify_isolation.py"; path.write_text("print('PASS')"); self.commit()
        with self.assertRaisesRegex(c.a.AdapterError, "original migration metadata changed"):
            self.verify()

    def test_original_core_cannot_be_replaced(self):
        path = self.repo / "nqc-census/crates/nqc-census-core/src/keccak.rs"; path.write_text("altered"); self.commit()
        with self.assertRaises(c.a.AdapterError): self.verify()

    def test_both_inert_and_active_workflow_rejected(self):
        target = self.repo / c.WORKFLOW; target.parent.mkdir(parents=True)
        shutil.copyfile(self.repo / c.INERT_WORKFLOW, target); self.commit()
        with self.assertRaisesRegex(c.a.AdapterError, "exactly one"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
