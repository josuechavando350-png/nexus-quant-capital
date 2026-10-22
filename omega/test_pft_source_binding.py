"""Adversarial offline fixtures; none are market or certification evidence."""
from __future__ import annotations

import copy
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pft_source_binding as binding
from integrity import canonical, git_blob


class GitFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.call("init", "-q")
        self.call("config", "user.name", "Offline fixture")
        self.call("config", "user.email", "fixture@example.invalid")
        (self.repo / "source.txt").write_text("synthetic source\n")
        self.call("add", "source.txt")
        self.call("commit", "-qm", "synthetic root")
        self.first = self.call("rev-parse", "HEAD").strip()
        self.call("commit", "--allow-empty", "-qm", "synthetic child")
        self.head = self.call("rev-parse", "HEAD").strip()
        self.tree = self.call("rev-parse", "HEAD^{tree}").strip()

    def call(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args],
                                       env=binding.offline_env(), text=True)

    def test_clean_exact_commit_and_bytes_pass(self):
        self.assertEqual(binding.verify_clean_head(self.repo, self.head), self.tree)
        self.assertEqual(binding.verify_checkout_bytes(self.repo, self.head), 1)

    def test_parent_segments_are_normalized_after_symlink_check(self):
        path = self.repo / ".." / "repo"
        self.assertEqual(binding.regular_directory(path), self.repo)

    def test_wrong_expected_head_rejected(self):
        with self.assertRaisesRegex(ValueError, "producer_head_mismatch"):
            binding.verify_clean_head(self.repo, self.first)

    def test_changed_tree_rejected(self):
        with self.assertRaisesRegex(ValueError, "commit_tree_mismatch"):
            binding.verify_commit(self.repo, self.head, "0" * 40)

    def test_dirty_tracked_source_rejected(self):
        (self.repo / "source.txt").write_text("changed\n")
        with self.assertRaisesRegex(ValueError, "dirty_checkout"):
            binding.verify_clean_head(self.repo, self.head)

    def test_untracked_source_rejected(self):
        (self.repo / "extra.txt").write_text("unexpected\n")
        with self.assertRaisesRegex(ValueError, "dirty_checkout"):
            binding.verify_clean_head(self.repo, self.head)

    def test_assume_unchanged_cannot_hide_changed_protected_bytes(self):
        self.call("update-index", "--assume-unchanged", "source.txt")
        (self.repo / "source.txt").write_text("hidden drift\n")
        with self.assertRaisesRegex(ValueError, "checkout_blob_mismatch"):
            binding.verify_checkout_bytes(self.repo, self.head)

    def test_mode_drift_rejected(self):
        (self.repo / "source.txt").chmod(0o755)
        with self.assertRaisesRegex(ValueError, "checkout_mode_mismatch"):
            binding.verify_checkout_bytes(self.repo, self.head)

    def test_symlink_cannot_replace_source(self):
        path = self.repo / "source.txt"
        path.unlink()
        path.symlink_to(self.base / "outside")
        with self.assertRaisesRegex(ValueError, "symlink_input"):
            binding.verify_checkout_bytes(self.repo, self.head)

    def test_missing_original_parent_rejected(self):
        raw = subprocess.check_output(["git", "-C", str(self.repo), "cat-file", "commit", self.head])
        raw = raw.replace(self.first.encode(), b"1" * 40, 1)
        changed = subprocess.check_output(["git", "-C", str(self.repo), "hash-object",
                                          "-t", "commit", "-w", "--stdin"], input=raw).decode().strip()
        with self.assertRaisesRegex(ValueError, "git_check_failed: rev-list"):
            binding.verify_commit(self.repo, changed)

    def test_replacement_history_rejected(self):
        self.call("replace", self.head, self.first)
        with self.assertRaisesRegex(ValueError, "git_replacements_forbidden"):
            binding.verify_git_context(self.repo)

    def test_grafted_history_rejected(self):
        (self.repo / ".git/info/grafts").write_text(self.head + "\n")
        with self.assertRaisesRegex(ValueError, "git_grafts_forbidden"):
            binding.verify_git_context(self.repo)

    def test_shallow_history_rejected(self):
        (self.repo / ".git/shallow").write_text(self.first + "\n")
        with self.assertRaisesRegex(ValueError, "shallow_history_forbidden"):
            binding.verify_git_context(self.repo)

    def test_git_environment_cannot_redirect_checkout(self):
        with patch.dict(os.environ, {"GIT_DIR": "/does-not-exist", "GIT_CONFIG_COUNT": "999",
                                     "PYTHONPATH": "/does-not-exist"}):
            self.assertEqual(binding.verify_clean_head(self.repo, self.head), self.tree)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"source_repository": binding.SOURCE,
                         "source_repository_id": binding.SOURCE_ID,
                         "source_commit": binding.SOURCE_COMMIT,
                         "source_tree": binding.SOURCE_TREE,
                         "proposed_destination": binding.DESTINATION,
                         "destination_repository_id": binding.DESTINATION_ID,
                         "authority": "SOURCE_SNAPSHOT_ONLY_NO_NEW_CERTIFICATION"}

    def test_source_and_destination_are_distinct(self):
        binding.verify_identities(self.manifest)
        self.assertNotEqual(binding.SOURCE_ID, binding.DESTINATION_ID)

    def test_substituted_source_repository_or_commit_rejected(self):
        for key, value in (("source_repository", binding.DESTINATION),
                           ("source_repository_id", binding.DESTINATION_ID),
                           ("source_commit", "0" * 40), ("source_tree", "0" * 40)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "source_identity_mismatch"):
                binding.verify_identities({**self.manifest, key: value})

    def test_substituted_destination_rejected(self):
        for key, value in (("proposed_destination", binding.SOURCE),
                           ("destination_repository_id", binding.SOURCE_ID)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "destination_identity_mismatch"):
                binding.verify_identities({**self.manifest, key: value})

    def test_relabelled_certificate_rejected(self):
        with self.assertRaisesRegex(ValueError, "relabelled_source_certificate"):
            binding.verify_identities({**self.manifest, "authority": "NEW_PRODUCER_CERTIFIED"})

    def test_materializer_and_profile_pins_match_immutable_import(self):
        for path, blob in binding.PINS.items():
            self.assertEqual(git_blob((binding.ROOT / path).read_bytes()), blob)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.effective = self.base / "effective"
        for name in ("recovered-source", "reimplementation"):
            folder = self.effective / name
            folder.mkdir(parents=True)
            (folder / "fixture.txt").write_text("SYNTHETIC_NOT_MARKET_EVIDENCE\n")
        self.receipt = {
            "authority": "NQC_RMC_CERTIFIED_EFFECTIVE_SOURCE_V1",
            "materializer_head": binding.SOURCE_COMMIT,
            "protocol_fork_certified_commit": binding.CERTIFIED_COMMIT,
            "protocol_fork_certified_tree": binding.CERTIFIED_TREE,
            "invariants": {"production_authority": False},
            "truth_boundaries": {"production_authority": False},
            "effective_recovered_source_tree_sha256": binding.tree_digest(self.effective / "recovered-source"),
            "reimplementation_bundle_tree_sha256": binding.tree_digest(self.effective / "reimplementation"),
        }
        self.save(self.receipt)

    def save(self, receipt):
        (self.effective / "MATERIALIZATION.json").write_bytes(canonical(receipt))

    def test_receipt_and_both_effective_trees_verified(self):
        self.assertEqual(binding.verify_receipt(canonical(self.receipt), self.effective), self.receipt)

    def test_source_artifact_mismatch_rejected(self):
        changed = {**self.receipt, "materializer_head": "0" * 40}
        with self.assertRaisesRegex(ValueError, "source_receipt_mismatch"):
            binding.verify_receipt(canonical(changed), self.effective)

    def test_matching_but_relabelled_certificates_rejected(self):
        changed = {**self.receipt, "protocol_fork_certified_commit": "0" * 40}
        self.save(changed)
        with self.assertRaisesRegex(ValueError, "relabelled_materialization_certificate"):
            binding.verify_receipt(canonical(changed), self.effective)

    def test_promoted_authority_rejected_even_with_matching_hashes(self):
        changed = copy.deepcopy(self.receipt)
        changed["invariants"]["production_authority"] = True
        self.save(changed)
        with self.assertRaisesRegex(ValueError, "unexpected_materialization_authority"):
            binding.verify_receipt(canonical(changed), self.effective)

    def test_changed_effective_or_reimplemented_source_rejected(self):
        for name in ("recovered-source", "reimplementation"):
            path = self.effective / name / "fixture.txt"
            previous = path.read_bytes()
            path.write_text("tampered\n")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "effective_tree_mismatch"):
                binding.verify_receipt(canonical(self.receipt), self.effective)
            path.write_bytes(previous)

    def test_extra_effective_source_file_rejected(self):
        (self.effective / "recovered-source/extra.txt").write_text("extra\n")
        with self.assertRaisesRegex(ValueError, "effective_tree_mismatch"):
            binding.verify_receipt(canonical(self.receipt), self.effective)

    def test_symlink_effective_tree_rejected(self):
        (self.effective / "reimplementation/link").symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, "symlink_effective_tree"):
            binding.verify_receipt(canonical(self.receipt), self.effective)

    def test_duplicate_receipt_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate_json_key"):
            binding.verify_receipt(b'{"x":1,"x":2}', self.effective)

    def test_digest_encoding_matches_pinned_original(self):
        from integrity import load_pinned_python
        module = load_pinned_python(binding.ROOT / binding.MATERIALIZER,
                                    binding.PINS[binding.MATERIALIZER], "test_original_pft")
        for name in ("recovered-source", "reimplementation"):
            root = self.effective / name
            self.assertEqual(binding.tree_digest(root), module.tree_digest(root))

    def test_existing_output_or_overlapping_inputs_rejected(self):
        for output, reason in ((self.effective, "output_already_exists"),
                               (self.effective / "new", "output_overlaps_input")):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, reason):
                binding.new_output(output, (self.effective,))

    def test_symlink_output_parent_rejected(self):
        link = self.base / "link"
        link.symlink_to(self.effective, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink_output"):
            binding.new_output(link / "new", ())

    def test_parent_segments_cannot_bypass_output_overlap(self):
        path = self.base / "elsewhere" / ".." / "effective" / "new"
        with self.assertRaisesRegex(ValueError, "output_overlaps_input"):
            binding.new_output(path, (self.effective,))


if __name__ == "__main__":
    unittest.main()
