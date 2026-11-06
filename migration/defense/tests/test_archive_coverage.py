import copy
import json
from pathlib import Path
import secrets
import subprocess
import sys
import unittest
from unittest.mock import patch

from test_defense import Fixture
from nqc_defense.archive_coverage import ArchiveCoverage
from nqc_defense.archive_store import ArchiveStore
from nqc_defense.audit_pages import AuditPageVerifier
from nqc_defense.codec import Rejected, canonical, decode
from nqc_defense.files import create_local, publish_local, sha256
from nqc_defense.witness import MAX_WITNESS_INTERVAL, ORIGIN, Witness


class ArchiveCoverageTests(Fixture):
    def setUp(self):
        super().setUp()
        self.witness_key = secrets.token_bytes(32)
        self.witness = Witness.create(self.root / "witness", self.witness_key, self.key, self.digest)
        self.archive = ArchiveStore.create(self.root / "archive")
        self.coverage = ArchiveCoverage(self.archive, self.witness)
        self.origin = self.witness.head()
        self.manifests, self.anchors = [], [self.origin]

    def capture(self):
        index = len(self.manifests)
        self.engine.admit_bytes(canonical({"request_id": f"coverage-{index}", "asset": "nqc-evidence"}), self.token())
        result = self.archive.capture(self.engine, self.witness, self.engine.checkpoint(), self.witness.head(), limit=1)
        self.manifests.append(result["manifest_sha256"])
        self.anchors.append(result["witness_receipt"])
        return result

    def populate(self, count=3):
        for _ in range(count):
            self.capture()
        return self.anchors[-1]

    def alternative(self, start, target, limit=3):
        def pages():
            cursor = AuditPageVerifier(self.key, self.digest, target, start)
            while not cursor.complete:
                data = self.engine.export_page(cursor.current, target, limit)
                cursor.accept(data)
                yield data
        return self.archive.prepare(pages(), self.key, self.digest, start, target)["manifest_sha256"]

    def manifest(self, digest):
        return json.loads((self.archive.root / "manifests" / (digest + ".json")).read_bytes())

    def changed_manifest(self, digest, change):
        value = self.manifest(digest)
        change(value)
        data = canonical(value)
        changed = sha256(data)
        publish_local(self.archive.root, "manifests/" + changed + ".json", data)
        return changed

    def changed_catalog(self, digest, change):
        value = json.loads((self.archive.root / ("coverage-" + digest + ".json")).read_bytes())
        change(value)
        data = canonical(value)
        changed = sha256(data)
        publish_local(self.archive.root, "coverage-" + changed + ".json", data)
        return changed

    def test_contiguous_intervals_replay_all_stored_pages_without_double_counting(self):
        target = self.populate()
        result = self.coverage.verify(self.manifests, self.origin, target)
        self.assertTrue(result["verified"] and result["complete"] and result["from_genesis"])
        self.assertEqual((result["interval_count"], result["page_count"], result["record_count"]), (3, 9, 9))
        self.assertEqual([item["witness_revision"] for item in result["intervals"]], [2, 3, 4])
        sizes = sum(self.archive.verify(digest, self.key, self.digest)["stored_page_bytes"] for digest in self.manifests)
        self.assertEqual(result["stored_page_bytes"], sizes)

    def test_suffix_is_explicitly_not_verified_from_genesis(self):
        target = self.populate()
        result = self.coverage.verify(self.manifests[1:], self.anchors[1], target)
        self.assertFalse(result["from_genesis"])
        self.assertEqual(result["record_count"], 6)
        self.assertEqual(result["start_receipt"], self.anchors[1])

    def test_empty_interval_only_certifies_its_equal_pinned_receipts(self):
        result = self.coverage.verify([], self.origin, self.origin)
        self.assertEqual(result["record_count"], 0)
        target = self.populate(1)
        result = self.coverage.verify([], target, target)
        self.assertFalse(result["from_genesis"])
        with self.assertRaisesRegex(Rejected, "coverage_incomplete"):
            self.coverage.verify([], self.origin, target)

    def test_missing_first_or_middle_interval_is_a_gap(self):
        target = self.populate()
        for manifests in (self.manifests[1:], [self.manifests[0], self.manifests[2]]):
            with self.assertRaisesRegex(Rejected, "coverage_gap"):
                self.coverage.verify(manifests, self.origin, target)

    def test_missing_tail_cannot_be_sealed_as_complete(self):
        target = self.populate()
        with self.assertRaisesRegex(Rejected, "coverage_incomplete"):
            self.coverage.seal(self.manifests[:-1], self.origin, target)
        self.assertEqual(list(self.archive.root.glob("coverage-*.json")), [])
        self.assertEqual(self.witness.head(), target)

    def test_duplicates_and_reordered_intervals_rejected(self):
        target = self.populate()
        for manifests, reason in (([self.manifests[0]] * 3, "coverage_duplicate_manifest"),
                                  (list(reversed(self.manifests)), "coverage_gap")):
            with self.assertRaisesRegex(Rejected, reason):
                self.coverage.verify(manifests, self.origin, target)

    def test_valid_but_overlapping_archive_rejected(self):
        target = self.populate()
        overlapping = self.alternative(ORIGIN, self.anchors[2]["checkpoint"])
        self.assertTrue(self.archive.verify(overlapping, self.key, self.digest)["verified"])
        with self.assertRaisesRegex(Rejected, "coverage_overlap"):
            self.coverage.verify([self.manifests[0], overlapping, self.manifests[2]], self.origin, target)

    def test_same_sequence_with_conflicting_hash_rejected(self):
        target = self.populate()
        changed = self.changed_manifest(self.manifests[1], lambda value: value["start"].update(head="f" * 64))
        with self.assertRaisesRegex(Rejected, "coverage_checkpoint_conflict"):
            self.coverage.verify([self.manifests[0], changed, self.manifests[2]], self.origin, target)

    def test_witness_binding_rejects_alternate_pagination(self):
        target = self.populate(1)
        alternative = self.alternative(ORIGIN, target["checkpoint"])
        self.assertTrue(self.archive.verify(alternative, self.key, self.digest)["verified"])
        with self.assertRaisesRegex(Rejected, "archive_witness_binding"):
            self.coverage.verify([alternative], self.origin, target)

    def test_merged_archive_cannot_hide_multiple_witness_revisions(self):
        target = self.populate(2)
        combined = self.alternative(ORIGIN, target["checkpoint"])
        with self.assertRaisesRegex(Rejected, "archive_witness_binding"):
            self.coverage.verify([combined], self.origin, target)

    def test_target_cannot_be_exceeded(self):
        self.populate()
        with self.assertRaisesRegex(Rejected, "coverage_target_exceeded"):
            self.coverage.verify(self.manifests, self.origin, self.anchors[2])

    def test_pinned_witness_receipts_and_direction_are_enforced(self):
        target = self.populate()
        for endpoint in ("start", "target"):
            start, stop = copy.deepcopy(self.origin), copy.deepcopy(target)
            (start if endpoint == "start" else stop)["head"] = "f" * 64
            with self.assertRaisesRegex(Rejected, "witness_receipt_mismatch"):
                self.coverage.verify(self.manifests, start, stop)
        with self.assertRaises(Rejected):
            self.coverage.verify([], target, self.origin)

    def test_input_count_type_and_hash_bounds(self):
        for manifests in ((self.manifests,), ["../outside"], ["f" * 64] * (MAX_WITNESS_INTERVAL + 1)):
            with self.assertRaises(Rejected):
                self.coverage.verify(manifests, self.origin, self.origin)
        far = {**self.origin, "revision": self.origin["revision"] + MAX_WITNESS_INTERVAL + 1}
        with self.assertRaisesRegex(Rejected, "integer_range"):
            self.witness.interval(self.origin, far)

    def test_aggregate_resource_budget_cannot_be_bypassed_by_small_intervals(self):
        target = self.populate()
        with patch("nqc_defense.archive_coverage.MAX_COVERAGE_PAGES", 8):
            with self.assertRaisesRegex(Rejected, "coverage_size_limit"):
                self.coverage.verify(self.manifests, self.origin, target)
        actual = self.coverage.verify(self.manifests, self.origin, target)["stored_page_bytes"]
        with patch("nqc_defense.archive_coverage.MAX_COVERAGE_BYTES", actual - 1):
            with self.assertRaisesRegex(Rejected, "coverage_size_limit"):
                self.coverage.verify(self.manifests, self.origin, target)

    def test_sealed_catalog_is_reopened_and_deterministic(self):
        target = self.populate()
        first = self.coverage.seal(self.manifests, self.origin, target)
        path = self.archive.root / ("coverage-" + first["catalog_sha256"] + ".json")
        stamp = (path.stat().st_ino, path.stat().st_mtime_ns)
        self.assertEqual(first, self.coverage.seal(self.manifests, self.origin, target))
        self.assertEqual(stamp, (path.stat().st_ino, path.stat().st_mtime_ns))
        reopened = ArchiveCoverage(ArchiveStore(self.archive.root), Witness(self.witness.root, self.witness_key, self.key, self.digest))
        self.assertEqual(first, reopened.verify_catalog(first["catalog_sha256"], self.origin, target))

    def test_historical_catalog_does_not_satisfy_a_newer_target(self):
        target = self.populate()
        first = self.coverage.seal(self.manifests, self.origin, target)
        self.capture()
        current = self.witness.head()
        historical = self.coverage.verify_catalog(first["catalog_sha256"], self.origin, target)
        self.assertEqual(first, historical)
        with self.assertRaisesRegex(Rejected, "coverage_catalog_anchor_mismatch"):
            self.coverage.verify_catalog(first["catalog_sha256"], self.origin, current)

    def test_catalog_cannot_choose_its_own_shorter_target(self):
        target = self.populate()
        first = self.coverage.seal(self.manifests, self.origin, target)
        changed = self.changed_catalog(first["catalog_sha256"], lambda value: value.update(
            target_receipt=self.anchors[2], manifests=self.manifests[:2]))
        with self.assertRaisesRegex(Rejected, "coverage_catalog_anchor_mismatch"):
            self.coverage.verify_catalog(changed, self.origin, target)

    def test_catalog_integrity_canonical_encoding_and_schema_are_enforced(self):
        target = self.populate(1)
        first = self.coverage.seal(self.manifests, self.origin, target)
        digest = first["catalog_sha256"]
        for change in (lambda value: value.update(verified=True),
                       lambda value: value.update(schema="unsupported"),
                       lambda value: value.update(policy_digest="f" * 64),
                       lambda value: value.update(audit_key_id="f" * 64)):
            with self.assertRaises(Rejected):
                self.coverage.verify_catalog(self.changed_catalog(digest, change), self.origin, target)
        path = self.archive.root / ("coverage-" + digest + ".json")
        noncanonical = path.read_bytes() + b" "
        new_digest = sha256(noncanonical)
        publish_local(self.archive.root, "coverage-" + new_digest + ".json", noncanonical)
        with self.assertRaisesRegex(Rejected, "coverage_catalog_encoding"):
            self.coverage.verify_catalog(new_digest, self.origin, target)
        path.write_bytes(noncanonical)
        with self.assertRaisesRegex(Rejected, "coverage_catalog_integrity"):
            self.coverage.verify_catalog(digest, self.origin, target)

    def test_catalog_verification_rereads_manifest_and_page_files(self):
        target = self.populate()
        sealed = self.coverage.seal(self.manifests, self.origin, target)
        manifest_path = self.archive.root / "manifests" / (self.manifests[1] + ".json")
        data = manifest_path.read_bytes()
        manifest_path.unlink()
        with self.assertRaisesRegex(Rejected, "file_unavailable"):
            self.coverage.verify_catalog(sealed["catalog_sha256"], self.origin, target)
        manifest_path.write_bytes(data)
        item = self.manifest(self.manifests[1])["pages"][0]
        (self.archive.root / "pages" / (item["sha256"] + ".zip")).write_bytes(b"controlled corruption")
        with self.assertRaisesRegex(Rejected, "archive_page_integrity"):
            self.coverage.verify_catalog(sealed["catalog_sha256"], self.origin, target)

    def test_later_append_during_scan_preserves_pinned_interval(self):
        target = self.populate()
        manifests = list(self.manifests)
        original = self.archive._verified_pages
        appended = [False]
        def append_during_read(manifest, key):
            for page in original(manifest, key):
                yield page
                if not appended[0]:
                    appended[0] = True
                    self.capture()
        with patch.object(self.archive, "_verified_pages", side_effect=append_during_read):
            checked = self.coverage.verify(manifests, self.origin, target)
        self.assertEqual(checked["record_count"], 9)
        self.assertEqual(self.witness.head()["checkpoint"]["sequence"], 12)

    def test_witness_rollback_during_scan_prevents_success(self):
        target = self.populate()
        original = self.archive._verified_pages
        changed = [False]
        def rollback_during_read(manifest, key):
            for page in original(manifest, key):
                yield page
                if not changed[0]:
                    changed[0] = True
                    with self.witness.connection(write=True) as db:
                        db.execute("DELETE FROM anchors WHERE revision=?", (target["revision"],))
        with patch.object(self.archive, "_verified_pages", side_effect=rollback_during_read):
            with self.assertRaisesRegex(Rejected, "witness_record_missing"):
                self.coverage.verify(self.manifests, self.origin, target)

    def test_witness_corruption_before_snapshot_is_rejected(self):
        target = self.populate()
        with self.witness.connection(write=True) as db:
            db.execute("UPDATE anchors SET payload='{}' WHERE revision=2")
        with self.assertRaisesRegex(Rejected, "witness_integrity"):
            self.coverage.verify(self.manifests, self.origin, target)

    def test_read_only_verification_does_not_change_witness_or_engine(self):
        target = self.populate()
        before = sorted(str(path.relative_to(self.archive.root)) for path in self.archive.root.rglob("*"))
        checkpoint = self.engine.checkpoint()
        self.coverage.verify(self.manifests, self.origin, target)
        self.assertEqual(self.witness.head(), target)
        self.assertEqual(self.engine.checkpoint(), checkpoint)
        self.assertEqual(before, sorted(str(path.relative_to(self.archive.root)) for path in self.archive.root.rglob("*")))

    def test_cli_seals_reverifies_and_rejects_missing_interval(self):
        target = self.populate()
        for name, data in (("audit.key", self.key), ("witness.key", self.witness_key),
                           ("start.json", canonical(self.origin)), ("target.json", canonical(target))):
            create_local(self.root, name, data)
        script = Path(__file__).resolve().parents[1] / "tools/archive_audit.py"
        args = [sys.executable, "-B", str(script), "--root", str(self.archive.root)]
        options = ["--audit-key-file", str(self.root / "audit.key"), "--policy-digest", self.digest,
                   "--witness-root", str(self.witness.root), "--witness-key-file", str(self.root / "witness.key"),
                   "--start-receipt", str(self.root / "start.json"), "--target-receipt", str(self.root / "target.json")]
        sealed = decode(subprocess.run([*args, "coverage", "--seal", *options, *self.manifests], check=True, capture_output=True).stdout)
        checked = decode(subprocess.run([*args, "verify-coverage", sealed["catalog_sha256"], *options], check=True, capture_output=True).stdout)
        self.assertEqual(sealed, checked)
        bad = subprocess.run([*args, "coverage", *options, self.manifests[0], self.manifests[2]], capture_output=True)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(decode(bad.stdout)["reason"], "coverage_gap")


if __name__ == "__main__":
    unittest.main()
