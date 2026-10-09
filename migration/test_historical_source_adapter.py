"""Offline integration/negative controls. Requires explicitly supplied local bundle."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("historical_adapter", HERE / "materialize_historical_source.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class HistoricalAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = Path(os.environ["NQC_ADAPTER_TEST_BUNDLE"])
        cls.tmp = tempfile.TemporaryDirectory(prefix="nqc-adapter-tests-")
        cls.base = Path(cls.tmp.name)
        cls.env = a.environment(cls.base)
        work = cls.base / "historical-fixture"
        work.mkdir()
        cls.historical, cls.edges = a.import_historical_bundle(cls.bundle.read_bytes(), work, cls.env)
        cls.source_store = Path(os.environ["NQC_ADAPTER_TEST_SOURCE_STORE"])
        cls.source_metadata = Path(os.environ["NQC_ADAPTER_TEST_SOURCE_METADATA"])
        cls.consumer = HERE.parent
        cls.head, cls.tree = a.identity(cls.consumer, cls.env)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(dir=self.base))

    def clone_consumer(self):
        target = self.work / "consumer"
        shutil.copytree(self.consumer, target)
        return target

    def clone_historical(self):
        target = self.work / "historical"
        shutil.copytree(self.historical, target)
        return target

    def commit(self, target, path):
        a.git(target, "add", "--", path, env=self.env)
        a.git(target, "-c", "user.name=Negative control", "-c", "user.email=negative@localhost",
              "commit", "--quiet", "-m", "deliberate negative control", env=self.env)
        return a.identity(target, self.env)

    def check_consumer(self, target, head=None, tree=None):
        return a.verify_consumer(target, head or self.head, tree or self.tree, self.historical, self.env)

    def test_01_real_materialization_preserves_original_identity(self):
        output = self.work / "materialized"
        before = hashlib.sha256(self.bundle.read_bytes()).hexdigest()
        report = a.materialize(self.consumer, self.bundle, output, self.head, self.tree)
        self.assertEqual(report["consumer"]["commit"], self.head)
        self.assertEqual(report["consumer"]["tree"], self.tree)
        self.assertEqual(report["historical_source"]["commit"], a.SOURCE_COMMIT)
        self.assertEqual(len(report["historical_source"]["ancestry_checks"]), 5)
        self.assertEqual(report["original_seed_identity"]["repository"]["full_name"], a.SOURCE_REPOSITORY)
        self.assertEqual(report["original_seed_identity"]["run"]["id"], 36820687233)
        self.assertEqual(report["original_seed_identity"]["artifact"]["id"], 11143129177)
        self.assertEqual(report["original_seed_identity"]["artifact"]["digest"],
                         "sha256:1cdb46fca52ebf1e0e2094b1c14b19384ecb7beceb50229b967592ab7a0308b4")
        receipt = output / "effective-source/MATERIALIZATION.json"
        data = json.loads(receipt.read_text())
        self.assertEqual(data["materializer_head"], a.SOURCE_COMMIT)
        self.assertEqual(report["historical_materialization_receipt"]["sha256"], a.digest(receipt.read_bytes()))
        self.assertEqual(report["network_isolation"]["interfaces"], ["lo"])
        self.assertFalse(report["network_isolation"]["routable_network"])
        self.assertNotEqual(report["network_isolation"]["parent_network_namespace"],
                            report["network_isolation"]["network_namespace"])
        self.assertFalse(report["truth_boundaries"]["canonical_recertification"])
        self.assertFalse(report["truth_boundaries"]["certification_transferred"])
        self.assertFalse(report["truth_boundaries"]["historical_seed_package_authenticated_by_this_adapter"])
        self.assertEqual(before, hashlib.sha256(self.bundle.read_bytes()).hexdigest())
        self.assertFalse((output / ".git").exists())
        self.assertFalse((output / "apps").exists())

    def test_02_historical_sparse_tree_contains_only_nqc(self):
        for path in self.historical.rglob("*"):
            rel = path.relative_to(self.historical).as_posix()
            if path.is_file() and not rel.startswith(".git/"):
                self.assertTrue(any(rel.startswith(root + "/") for root in a.HISTORICAL_PATHS), rel)
        self.assertFalse((self.historical / ".github").exists())
        self.assertEqual(a.verify_historical_authority(self.historical, self.env), self.edges)

    def test_03_altered_bundle_object_rejected(self):
        data = bytearray(self.bundle.read_bytes()); data[-200] ^= 1
        with self.assertRaisesRegex(a.AdapterError, "bundle digest mismatch"):
            a.import_historical_bundle(bytes(data), self.work, self.env)
        self.assertFalse((self.work / "historical-source").exists())

    def test_04_truncated_bundle_rejected(self):
        with self.assertRaisesRegex(a.AdapterError, "bundle digest mismatch"):
            a.import_historical_bundle(self.bundle.read_bytes()[:-20], self.work, self.env)

    def test_05_substituted_source_ref_rejected(self):
        with self.assertRaisesRegex(a.AdapterError, "substituted historical source ref"):
            a.import_historical_bundle(self.bundle.read_bytes(), self.work, self.env, "refs/heads/main")

    def test_06_changed_repository_rejected(self):
        output = self.work / "out"
        with self.assertRaisesRegex(a.AdapterError, "repository identity changed"):
            a.materialize(self.consumer, self.bundle, output, self.head, self.tree,
                          source_repository=a.CONSUMER_REPOSITORY)
        self.assertFalse(output.exists())

    def test_07_changed_repository_id_rejected(self):
        with self.assertRaisesRegex(a.AdapterError, "repository identity changed"):
            a.materialize(self.consumer, self.bundle, self.work / "out", self.head, self.tree,
                          source_repository_id=a.CONSUMER_REPOSITORY_ID)

    def test_08_unsafe_paths_rejected(self):
        for path in ("../outside", "/absolute", "a/../b", "a//b", ".git/config", "a\\b", "a/./b"):
            with self.subTest(path=path), self.assertRaises(a.AdapterError):
                a.safe_repo_path(path)

    def test_09_wrong_consumer_commit_rejected(self):
        with self.assertRaisesRegex(a.AdapterError, "consumer HEAD/tree mismatch"):
            self.check_consumer(self.consumer, "0" * 40)

    def test_10_wrong_consumer_tree_rejected(self):
        with self.assertRaisesRegex(a.AdapterError, "consumer HEAD/tree mismatch"):
            self.check_consumer(self.consumer, tree="0" * 40)

    def test_11_changed_whole_core_committed_path_rejected(self):
        target = self.clone_consumer()
        path = "nqc-census/crates/nqc-census-core/src/keccak.rs"
        with (target / path).open("a") as stream: stream.write("\n// altered frozen whole core\n")
        head, tree = self.commit(target, path)
        with self.assertRaisesRegex(a.AdapterError, "command failed"):
            self.check_consumer(target, head, tree)

    def test_12_dirty_protected_worktree_rejected(self):
        target = self.clone_consumer()
        (target / "ci/nqc-protocol-fork/locks/recovered-2b640cc-Cargo.lock").write_text("altered")
        with self.assertRaisesRegex(a.AdapterError, "not clean"):
            self.check_consumer(target)

    def test_13_relabelled_manifest_rejected(self):
        target = self.clone_consumer()
        path = "migration/source-manifest.json"
        data = json.loads((target / path).read_text()); data["authority"] = "CERTIFIED"
        (target / path).write_text(json.dumps(data))
        head, tree = self.commit(target, path)
        with self.assertRaisesRegex(a.AdapterError, "source manifest changed"):
            self.check_consumer(target, head, tree)

    def test_14_hidden_index_changes_rejected(self):
        target = self.clone_consumer()
        path = "ci/nqc-census/effective-source-profile.json"
        a.git(target, "update-index", "--assume-unchanged", path, env=self.env)
        (target / path).write_text("{}")
        with self.assertRaisesRegex(a.AdapterError, "index hides"):
            self.check_consumer(target)

    def test_15_historical_changed_evidence_ref_rejected(self):
        target = self.clone_historical()
        a.git(target, "update-ref", a.SOURCE_REF, a.D06_BASE, env=self.env)
        with self.assertRaisesRegex(a.AdapterError, "evidence ref changed"):
            a.verify_historical_authority(target, self.env)

    def test_16_historical_shallow_ancestry_rejected(self):
        target = self.clone_historical()
        (target / ".git/shallow").write_text(a.SOURCE_COMMIT + "\n")
        with self.assertRaisesRegex(a.AdapterError, "incomplete history"):
            a.verify_historical_authority(target, self.env)

    def test_17_historical_graft_rejected(self):
        target = self.clone_historical()
        (target / ".git/info/grafts").write_text(a.SOURCE_COMMIT + " " + a.PFT + "\n")
        with self.assertRaisesRegex(a.AdapterError, "alternate or incomplete"):
            a.verify_historical_authority(target, self.env)

    def test_18_historical_replace_ref_rejected(self):
        target = self.clone_historical()
        a.git(target, "update-ref", "refs/replace/" + a.SOURCE_COMMIT, a.D06_BASE, env=self.env)
        with self.assertRaisesRegex(a.AdapterError, "replacement refs"):
            a.verify_historical_authority(target, self.env)

    def test_19_historical_protected_worktree_rejected(self):
        target = self.clone_historical()
        (target / "nqc-census/crates/nqc-census-core/src/keccak.rs").write_text("altered")
        with self.assertRaisesRegex(a.AdapterError, "protected worktree changed"):
            a.verify_historical_authority(target, self.env)

    def test_20_historical_packed_object_corruption_rejected(self):
        target = self.clone_historical()
        pack = next((target / ".git/objects/pack").glob("*.pack"))
        data = bytearray(pack.read_bytes()); data[-200] ^= 1; pack.chmod(0o600); pack.write_bytes(data)
        with self.assertRaises(a.AdapterError):
            a.verify_historical_authority(target, self.env)

    def test_21_original_materializer_still_rejects_independent_root(self):
        output = self.work / "must-not-exist"
        result = subprocess.run(["/usr/bin/python3", "-I", "-B",
                                 str(self.consumer / "ci/nqc-census/materialize_effective_source.py"),
                                 "--output", str(output)], env=self.env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"RMC_EFFECTIVE_SOURCE_FAIL", result.stderr)
        self.assertFalse(output.exists())

    def test_22_output_cannot_overlap_consumer(self):
        with self.assertRaisesRegex(a.AdapterError, "output overlaps consumer"):
            a.materialize(self.consumer, self.bundle, self.consumer / "not-allowed", self.head, self.tree)

    def test_23_symlink_bundle_rejected(self):
        link = self.work / "bundle-link"; link.symlink_to(self.bundle)
        with self.assertRaisesRegex(a.AdapterError, "path aliases"):
            a.materialize(self.consumer, link, self.work / "out", self.head, self.tree)

    def test_24_existing_output_never_overwritten(self):
        output = self.work / "out"; output.mkdir(); sentinel = output / "sentinel"; sentinel.write_text("preserve")
        with self.assertRaisesRegex(a.AdapterError, "output already exists"):
            a.materialize(self.consumer, self.bundle, output, self.head, self.tree)
        self.assertEqual(sentinel.read_text(), "preserve")

    def test_25_environment_cannot_supply_git_or_network_authority(self):
        for key in ("GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GITHUB_TOKEN",
                    "GH_TOKEN", "SSH_AUTH_SOCK", "HTTPS_PROXY", "PYTHONPATH"):
            self.assertNotIn(key, self.env)
        self.assertEqual(self.env["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(self.env["GIT_ALLOW_PROTOCOL"], "")
        self.assertEqual(self.env["GIT_NO_REPLACE_OBJECTS"], "1")

    def test_26_declared_incomplete_bundle_is_not_complete_evidence(self):
        old_bundle = Path(os.environ["NQC_ADAPTER_TEST_INCOMPLETE_BUNDLE"])
        with self.assertRaisesRegex(a.AdapterError, "bundle digest mismatch"):
            a.import_historical_bundle(old_bundle.read_bytes(), self.work, self.env)

    def test_27_missing_historical_evidence_ref_rejected(self):
        target = self.clone_historical()
        a.git(target, "update-ref", "-d", "refs/evidence/d06_original_source", env=self.env)
        with self.assertRaises(a.AdapterError):
            a.verify_historical_authority(target, self.env)

    def test_28_namespace_failure_has_no_fallback_or_receipt(self):
        original_run = a.run
        def fail_namespace(command, **kwargs):
            if command[0] == "unshare":
                raise a.AdapterError("namespace unavailable")
            return original_run(command, **kwargs)
        output = self.work / "out"
        with mock.patch.object(a, "run", side_effect=fail_namespace):
            with self.assertRaisesRegex(a.AdapterError, "namespace unavailable"):
                a.materialize(self.consumer, self.bundle, output, self.head, self.tree)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.work.glob("nqc-historical-source-*")))

    def test_29_changed_seed_identity_rejected(self):
        target = self.clone_consumer()
        path = "ci/nqc-census/rmc006-recertification-source.json"
        pin = json.loads((target / path).read_text()); pin["repository"]["full_name"] = a.CONSUMER_REPOSITORY
        (target / path).write_text(json.dumps(pin))
        head, tree = self.commit(target, path)
        with self.assertRaises(a.AdapterError):
            self.check_consumer(target, head, tree)

    def test_30_changed_profile_destination_rejected(self):
        target = self.clone_consumer()
        path = "ci/nqc-census/effective-source-profile.json"
        pin = json.loads((target / path).read_text()); pin["reimplementations"][0]["destination"] = "../../outside"
        (target / path).write_text(json.dumps(pin))
        head, tree = self.commit(target, path)
        with self.assertRaises(a.AdapterError):
            self.check_consumer(target, head, tree)

    def test_31_weakened_consumer_verifier_rejected(self):
        target = self.clone_consumer()
        path = "migration/verify_isolation.py"
        (target / path).write_text("print('forged PASS')")
        head, tree = self.commit(target, path)
        with self.assertRaisesRegex(a.AdapterError, "isolation verifier changed"):
            self.check_consumer(target, head, tree)

    def test_32_committed_protected_symlink_rejected(self):
        target = self.clone_consumer()
        path = "nqc-census/crates/nqc-census-core/src/keccak.rs"
        (target / path).unlink(); (target / path).symlink_to("lib.rs")
        head, tree = self.commit(target, path)
        with self.assertRaises(a.AdapterError):
            self.check_consumer(target, head, tree)

    def test_33_consumer_clean_filter_cannot_execute(self):
        target = self.clone_consumer()
        marker = self.work / "filter-executed"
        path = "nqc-census/crates/nqc-census-core/src/keccak.rs"
        with (target / ".git/config").open("a") as stream:
            stream.write('\n[filter "unsafe"]\n clean = "touch ' + str(marker) + '; cat"\n')
        (target / ".git/info").mkdir(exist_ok=True)
        (target / ".git/info/attributes").write_text(path + " filter=unsafe\n")
        os.utime(target / path, None)
        with self.assertRaisesRegex(a.AdapterError, "metadata can redirect"):
            self.check_consumer(target)
        self.assertFalse(marker.exists())

    def test_34_consumer_config_include_never_followed(self):
        target = self.clone_consumer()
        with (target / ".git/config").open("a") as stream:
            stream.write('\n[include]\n path = /dev/zero\n')
        with self.assertRaisesRegex(a.AdapterError, "unsafe or unreviewed"):
            self.check_consumer(target)

    def test_35_consumer_filter_config_rejected_without_attributes(self):
        target = self.clone_consumer()
        with (target / ".git/config").open("a") as stream:
            stream.write('\n[filter "unsafe"]\n process = executable-command\n')
        with self.assertRaisesRegex(a.AdapterError, "unsafe or unreviewed"):
            self.check_consumer(target)

    def test_36_consumer_worktree_redirection_rejected(self):
        target = self.clone_consumer()
        with (target / ".git/config").open("a") as stream:
            stream.write('\n[core]\n worktree = /tmp\n')
        with self.assertRaisesRegex(a.AdapterError, "unsafe or unreviewed"):
            self.check_consumer(target)

    def test_37_bundle_parent_alias_rejected(self):
        directory = self.work / "alias"; directory.symlink_to(self.bundle.parent, target_is_directory=True)
        with self.assertRaisesRegex(a.AdapterError, "bundle path aliases"):
            a.materialize(self.consumer, directory / self.bundle.name, self.work / "out", self.head, self.tree)

    def test_38_unreviewed_migration_bundle_rejected(self):
        target = self.clone_consumer()
        path = "migration/hidden-history.bundle"
        (target / path).write_bytes(b"# v2 git bundle\n")
        head, tree = self.commit(target, path)
        with self.assertRaisesRegex(a.AdapterError, "tracked composition payload"):
            self.check_consumer(target, head, tree)

    def test_39_atomic_publish_does_not_replace_concurrent_empty_directory(self):
        stage, output = self.work / "stage", self.work / "out"
        stage.mkdir(); (stage / "receipt").write_text("not published")
        output.mkdir()
        before = output.stat().st_ino
        with self.assertRaises(FileExistsError):
            a.publish_no_replace(stage, output)
        self.assertEqual(output.stat().st_ino, before)
        self.assertEqual(list(output.iterdir()), [])
        self.assertTrue((stage / "receipt").exists())

    def test_40_pre_pft_original_ancestry_cannot_be_transplanted(self):
        target = self.clone_consumer()
        early = a.git(self.historical, "rev-list", "--max-parents=0", a.SOURCE_COMMIT,
                      env=self.env).decode().splitlines()[0]
        self.assertNotIn(early, {a.SOURCE_COMMIT, a.D06_SOURCE, a.PFT, a.D06_BASE, a.RMC003_2})
        shutil.copytree(self.historical / ".git/objects", target / ".git/objects", dirs_exist_ok=True)
        new_head = a.git(target, "-c", "user.name=Negative control", "-c", "user.email=negative@localhost",
                         "commit-tree", self.tree, "-p", early, "-m", "forbidden original-history parent",
                         env=self.env).decode().strip()
        a.git(target, "update-ref", "HEAD", new_head, env=self.env)
        with self.assertRaisesRegex(a.AdapterError, "consumer carries original ancestry"):
            self.check_consumer(target, new_head, self.tree)

    def test_41_real_source_store_mode_no_bundle_dependency(self):
        output = self.work / "source-store-result"
        report = a.materialize(self.consumer, None, output, self.head, self.tree,
                               source_store=self.source_store, source_metadata=self.source_metadata)
        self.assertEqual(report["historical_source"]["input_mode"], "PINNED_PUBLIC_SOURCE_STORE")
        self.assertIsNone(report["historical_source"]["bundle_sha256"])
        self.assertEqual(report["historical_source"]["source_metadata_sha256"], a.digest(self.source_metadata.read_bytes()))
        self.assertEqual(report["consumer"]["commit"], self.head)
        self.assertFalse(report["truth_boundaries"]["canonical_recertification"])

    def source_store_copy(self):
        target = self.work / "source-store"
        shutil.copytree(self.source_store, target)
        return target

    def changed_metadata(self, edit):
        data = json.loads(self.source_metadata.read_text()); edit(data)
        path = self.work / "metadata.json"; path.write_text(json.dumps(data)); return path

    def test_42_source_metadata_wrong_repository_rejected(self):
        path = self.changed_metadata(lambda d: d.update(source_repository=a.CONSUMER_REPOSITORY))
        with self.assertRaisesRegex(a.AdapterError, "repository identity changed"):
            a.load_source_metadata(path)

    def test_43_source_metadata_wrong_tree_rejected(self):
        path = self.changed_metadata(lambda d: d["commit_metadata"][a.SOURCE_REF]["tree"].update(sha="0" * 40))
        with self.assertRaisesRegex(a.AdapterError, "commit/tree mismatch"):
            a.load_source_metadata(path)

    def test_44_source_metadata_moving_ref_rejected(self):
        def change(d): d["commit_metadata"]["refs/heads/main"] = d["commit_metadata"].pop(a.SOURCE_REF)
        with self.assertRaisesRegex(a.AdapterError, "ref inventory changed"):
            a.load_source_metadata(self.changed_metadata(change))

    def test_45_source_metadata_substituted_endpoint_rejected(self):
        path = self.changed_metadata(lambda d: d.update(git_transport_url="https://example.com/repo.git"))
        with self.assertRaisesRegex(a.AdapterError, "Git transport changed"):
            a.load_source_metadata(path)

    def test_46_source_store_extra_ref_rejected(self):
        target = self.source_store_copy()
        a.git(target, "update-ref", "refs/heads/main", a.SOURCE_COMMIT, env=self.env)
        with self.assertRaisesRegex(a.AdapterError, "ref inventory changed"):
            a.verify_source_store(target, self.env)

    def test_47_source_store_missing_seed_ref_rejected(self):
        target = self.source_store_copy()
        a.git(target, "update-ref", "-d", "refs/evidence/d06_original_source", env=self.env)
        with self.assertRaisesRegex(a.AdapterError, "ref inventory changed"):
            a.verify_source_store(target, self.env)

    def test_48_source_store_changed_ref_rejected(self):
        target = self.source_store_copy()
        a.git(target, "update-ref", a.SOURCE_REF, a.D06_BASE, env=self.env)
        with self.assertRaisesRegex(a.AdapterError, "ref inventory changed"):
            a.verify_source_store(target, self.env)

    def test_49_source_store_promisor_marker_rejected(self):
        target = self.source_store_copy()
        (target / (".git/objects/pack/pack-" + "0" * 40 + ".promisor")).write_text("")
        with self.assertRaisesRegex(a.AdapterError, "promisor source object"):
            a.verify_source_store(target, self.env)

    def test_50_source_store_alternates_rejected(self):
        target = self.source_store_copy()
        (target / ".git/objects/info").mkdir(exist_ok=True)
        (target / ".git/objects/info/alternates").write_text(str(self.source_store / ".git/objects"))
        with self.assertRaisesRegex(a.AdapterError, "incomplete or alternate"):
            a.verify_source_store(target, self.env)

    def test_51_source_store_corrupt_loose_object_rejected(self):
        target = self.source_store_copy()
        loose = next(p for p in (target / ".git/objects").glob("[0-9a-f][0-9a-f]/*") if p.is_file())
        loose.chmod(0o600); loose.write_bytes(b"broken object")
        with self.assertRaises(a.AdapterError):
            a.verify_source_store(target, self.env)

    def test_52_source_store_symlink_object_rejected(self):
        target = self.source_store_copy()
        loose = next(p for p in (target / ".git/objects").glob("[0-9a-f][0-9a-f]/*") if p.is_file())
        loose.unlink(); loose.symlink_to("/dev/null")
        with self.assertRaisesRegex(a.AdapterError, "unsafe Git object/ref path"):
            a.verify_source_store(target, self.env)

    def test_53_source_store_requires_metadata(self):
        with self.assertRaisesRegex(a.AdapterError, "requires source metadata"):
            a.materialize(self.consumer, None, self.work / "out", self.head, self.tree,
                          source_store=self.source_store)

    def test_54_arbitrary_bundle_hash_cannot_be_supplied(self):
        with self.assertRaisesRegex(a.AdapterError, "schema fields changed"):
            a.load_source_metadata(self.changed_metadata(lambda d: d.update(bundle_sha256="0" * 64)))

    def test_55_source_object_fifo_rejected_before_git_reads(self):
        target = self.source_store_copy()
        loose = next(p for p in (target / ".git/objects").glob("[0-9a-f][0-9a-f]/*") if p.is_file())
        loose.unlink(); os.mkfifo(loose)
        with self.assertRaisesRegex(a.AdapterError, "unsafe Git object/ref path"):
            a.verify_source_store(target, self.env)

    def test_56_source_ref_fifo_rejected_before_git_reads(self):
        target = self.source_store_copy()
        ref = target / ".git" / a.SOURCE_REF
        ref.parent.mkdir(parents=True, exist_ok=True)
        if ref.exists(): ref.unlink()
        os.mkfifo(ref)
        with self.assertRaisesRegex(a.AdapterError, "unsafe Git object/ref path"):
            a.verify_source_store(target, self.env)

    def test_57_real_actions_checkout_gc_auto_zero_is_supported(self):
        target = self.clone_consumer()
        with (target / ".git/config").open("a") as stream: stream.write("\n[gc]\n auto = 0\n")
        self.assertEqual(self.check_consumer(target)["status"], "STANDALONE_COMPOSITION_PASS")

    def test_58_other_gc_configuration_is_rejected(self):
        target = self.clone_consumer()
        with (target / ".git/config").open("a") as stream: stream.write("\n[gc]\n auto = 1\n")
        with self.assertRaisesRegex(a.AdapterError, "unsupported consumer core"):
            self.check_consumer(target)


if __name__ == "__main__":
    unittest.main()
