import copy
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import unittest
from unittest.mock import patch

from test_defense import Fixture
from nqc_defense.archive_coverage import ArchiveCoverage
from nqc_defense.archive_inventory import ArchiveInventory, scan_store
from nqc_defense.archive_store import ArchiveStore
from nqc_defense.codec import Rejected, canonical, decode
from nqc_defense.files import create_local, publish_local, sha256
from nqc_defense.witness import Witness


class ArchiveInventoryTests(Fixture):
    def setUp(self):
        super().setUp()
        self.witness_key = secrets.token_bytes(32)
        self.witness = Witness.create(self.root / "witness", self.witness_key, self.key, self.digest)
        self.archive = ArchiveStore.create(self.root / "archive")
        self.coverage = ArchiveCoverage(self.archive, self.witness)
        self.inventory = ArchiveInventory(self.archive, self.witness)
        self.anchors, self.manifests = [self.witness.head()], []

    def capture(self):
        self.engine.admit_bytes(canonical({"asset": "nqc-evidence", "request_id": f"inventory-{len(self.manifests)}"}), self.token())
        result = self.archive.capture(self.engine, self.witness, self.engine.checkpoint(), self.witness.head(), limit=1)
        self.manifests.append(result["manifest_sha256"])
        self.anchors.append(result["witness_receipt"])

    def select(self, start=0, end=None):
        end = len(self.manifests) if end is None else end
        sealed = self.coverage.seal(self.manifests[start:end], self.anchors[start], self.anchors[end])
        return {"catalog_sha256": sealed["catalog_sha256"], "start_receipt": self.anchors[start],
                "target_receipt": self.anchors[end]}

    def populate(self, count=2):
        for _ in range(count):
            self.capture()
        return self.select()

    def page_path(self):
        manifest = json.loads((self.archive.root / "manifests" / (self.manifests[0] + ".json")).read_bytes())
        return self.archive.root / "pages" / (manifest["pages"][0]["sha256"] + ".zip")

    def test_complete_inventory_links_actual_catalog_manifests_and_pages(self):
        selected = self.populate()
        result = self.inventory.inspect([selected])
        self.assertTrue(result["verified"] and result["selected_coverage_complete"])
        self.assertEqual(result["observed_objects"], 9)
        self.assertEqual(len(result["references"]), 8)
        self.assertEqual({key: value["objects"] for key, value in result["summary"].items()},
                         {"catalog": 1, "manifest": 2, "page": 6, "temporary": 0, "unknown": 0})
        actual = sum(path.stat().st_size for path in self.archive.root.rglob("*") if path.is_file())
        self.assertEqual(result["observed_logical_bytes"], actual)
        self.assertTrue(all(item["referenced_by_selected"] for item in result["entries"]))
        self.assertFalse(result["deletion_authorized"])
        self.assertFalse(result["atomic_filesystem_snapshot"])

    def test_overlapping_catalogs_share_objects_without_double_counting_storage(self):
        full = self.populate(3)
        prefix = self.select(end=2)
        result = self.inventory.inspect([full, prefix])
        self.assertEqual(result["observed_objects"], 14)
        self.assertEqual(result["summary"]["manifest"]["objects"], 3)
        self.assertEqual(result["summary"]["page"]["objects"], 9)
        self.assertEqual(len(result["references"]), 14)
        self.assertEqual([item["verified"] for item in result["selections"]], [True, True])

    def test_objects_outside_selection_are_not_called_global_orphans(self):
        old = self.populate(1)
        self.capture()
        newer = self.select()
        result = self.inventory.inspect([old])
        self.assertTrue(result["verified"])
        self.assertEqual(result["summary"]["catalog"]["outside_selected_objects"], 1)
        self.assertEqual(result["summary"]["manifest"]["outside_selected_objects"], 1)
        self.assertEqual(result["summary"]["page"]["outside_selected_objects"], 3)
        excluded = {entry["path"] for entry in result["entries"] if not entry["referenced_by_selected"]}
        self.assertIn("coverage-" + newer["catalog_sha256"] + ".json", excluded)
        self.assertFalse(result["unselected_content_verified"])

    def test_unknown_and_pending_objects_are_counted_without_reading_their_content(self):
        selected = self.populate(1)
        names = ["operator-notes", "pages/pending-" + "a" * 48, "manifests/not-a-hash.json"]
        secret = b"PRIVATE_UNSELECTED_CONTENT_MUST_NOT_APPEAR"
        for name in names:
            create_local(self.archive.root, name, secret)
            (self.archive.root / name).chmod(0o000)
        result = self.inventory.inspect([selected])
        self.assertEqual(result["summary"]["unknown"]["objects"], 2)
        self.assertEqual(result["summary"]["temporary"]["objects"], 1)
        self.assertNotIn(secret, canonical(result))
        self.assertTrue(all((self.archive.root / name).exists() for name in names))

    def test_unselected_catalog_content_is_explicitly_not_certified(self):
        selected = self.populate(1)
        name = "coverage-" + "f" * 64 + ".json"
        create_local(self.archive.root, name, b"not a valid catalog")
        result = self.inventory.inspect([selected])
        self.assertTrue(result["verified"])
        entry = next(item for item in result["entries"] if item["path"] == name)
        self.assertFalse(entry["referenced_by_selected"])
        self.assertEqual(entry["content_verification"], "not_verified")
        self.assertFalse(result["unselected_content_verified"])

    def test_missing_catalog_disables_reference_classification(self):
        selected = self.populate()
        path = "coverage-" + selected["catalog_sha256"] + ".json"
        (self.archive.root / path).unlink()
        result = self.inventory.inspect([selected])
        self.assertFalse(result["verified"] or result["reference_classification_available"])
        self.assertEqual(result["issues"], [{"path": path, "reason": "missing_reference"}])
        self.assertTrue(all(entry["referenced_by_selected"] is None for entry in result["entries"]))

    def test_missing_manifest_reports_exact_reference_without_claiming_pages_unused(self):
        selected = self.populate()
        path = "manifests/" + self.manifests[0] + ".json"
        (self.archive.root / path).unlink()
        result = self.inventory.inspect([selected])
        self.assertFalse(result["verified"])
        self.assertIn({"path": path, "reason": "missing_reference"}, result["issues"])
        self.assertIsNone(result["summary"]["page"]["outside_selected_objects"])

    def test_missing_page_reports_exact_reference(self):
        selected = self.populate()
        path = self.page_path()
        path.unlink()
        result = self.inventory.inspect([selected])
        self.assertFalse(result["verified"])
        self.assertIn({"path": str(path.relative_to(self.archive.root)), "reason": "missing_reference"}, result["issues"])

    def test_corrupt_page_prevents_selected_coverage_success(self):
        selected = self.populate()
        self.page_path().write_bytes(b"local controlled corruption")
        result = self.inventory.inspect([selected])
        self.assertFalse(result["verified"])
        self.assertIn("archive_page_integrity", [item["reason"] for item in result["issues"]])

    def test_corrupt_manifest_prevents_classification(self):
        selected = self.populate()
        (self.archive.root / "manifests" / (self.manifests[0] + ".json")).write_bytes(b"{}")
        result = self.inventory.inspect([selected])
        self.assertFalse(result["verified"])
        self.assertIn("archive_manifest_integrity", [item["reason"] for item in result["issues"]])

    def test_corrupt_catalog_is_not_trusted_to_expand_references(self):
        selected = self.populate()
        (self.archive.root / ("coverage-" + selected["catalog_sha256"] + ".json")).write_bytes(b"{}")
        result = self.inventory.inspect([selected])
        self.assertFalse(result["verified"])
        self.assertEqual(result["references"], [])
        self.assertEqual(result["issues"][0]["reason"], "coverage_catalog_integrity")

    def test_stale_catalog_cannot_choose_new_external_target(self):
        selected = self.populate(1)
        self.capture()
        selected["target_receipt"] = self.witness.head()
        result = self.inventory.inspect([selected])
        self.assertFalse(result["verified"])
        self.assertEqual(result["issues"][0]["reason"], "coverage_catalog_anchor_mismatch")

    def test_mixed_valid_and_missing_selection_disables_all_unused_claims(self):
        valid = self.populate(1)
        missing = {**valid, "catalog_sha256": "f" * 64}
        result = self.inventory.inspect([valid, missing])
        self.assertEqual(sum(item["verified"] for item in result["selections"]), 1)
        self.assertFalse(result["reference_classification_available"])
        self.assertTrue(all(item["outside_selected_bytes"] is None for item in result["summary"].values()))

    def test_selection_schema_hash_count_and_duplicate_bounds(self):
        selected = self.populate(1)
        bad_cases = ([], {}, [selected] * 33, [selected, selected],
                     [{**selected, "extra": True}], [{**selected, "catalog_sha256": "../outside"}],
                     [{**selected, "start_receipt": {}}])
        for value in bad_cases:
            with self.subTest(value=value), self.assertRaises(Rejected):
                self.inventory.inspect(value)

    def test_empty_anchored_catalog_has_valid_zero_page_inventory(self):
        selected = self.select()
        result = self.inventory.inspect([selected])
        self.assertTrue(result["verified"])
        self.assertEqual(result["observed_objects"], 1)
        self.assertEqual(result["references"], [])

    def test_symlinks_are_rejected_even_when_unselected(self):
        selected = self.populate(1)
        link = self.archive.root / "pages" / "outside-link"
        link.symlink_to(self.assets / "evidence.json")
        with self.assertRaisesRegex(Rejected, "inventory_entry_type"):
            self.inventory.inspect([selected])
        self.assertEqual((self.assets / "evidence.json").read_bytes(), self.payload)

    def test_hardlink_aliases_cannot_double_count_storage(self):
        selected = self.populate(1)
        os.link(self.page_path(), self.archive.root / "alias")
        with self.assertRaisesRegex(Rejected, "inventory_hardlink"):
            self.inventory.inspect([selected])

    def test_fifos_and_nested_directories_are_rejected_without_recursing(self):
        selected = self.populate(1)
        path = self.archive.root / "unexpected"
        os.mkfifo(path, mode=0o600)
        with self.assertRaisesRegex(Rejected, "inventory_entry_type"):
            self.inventory.inspect([selected])
        path.unlink()
        path.mkdir(mode=0o700)
        (path / "private-content").write_bytes(b"not part of the archive layout")
        with self.assertRaisesRegex(Rejected, "inventory_entry_type"):
            self.inventory.inspect([selected])

    def test_public_file_permissions_rejected(self):
        selected = self.populate(1)
        self.page_path().chmod(0o644)
        with self.assertRaisesRegex(Rejected, "inventory_file_permissions"):
            self.inventory.inspect([selected])

    def test_failed_scans_close_directory_descriptors(self):
        selected = self.populate(1)
        (self.archive.root / "unexpected").mkdir(mode=0o700)
        before = len(os.listdir("/proc/self/fd"))
        for _ in range(20):
            with self.assertRaisesRegex(Rejected, "inventory_entry_type"):
                self.inventory.inspect([selected])
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_scan_object_and_logical_byte_budgets_enforced(self):
        selected = self.populate(1)
        observed = scan_store(self.archive)["logical_bytes"]
        for name, limit, reason in (("MAX_OBJECTS", 4, "inventory_object_limit"),
                                    ("MAX_OBSERVED_BYTES", observed - 1, "inventory_observed_size_limit")):
            with patch("nqc_defense.archive_inventory." + name, limit):
                with self.assertRaisesRegex(Rejected, reason):
                    self.inventory.inspect([selected])

    def test_aggregate_verification_budgets_include_overlapping_catalog_work(self):
        full = self.populate(2)
        prefix = self.select(end=1)
        sizes = sum(self.archive.verify(digest, self.key, self.digest)["stored_page_bytes"] for digest in self.manifests)
        for name, limit in (("MAX_SELECTED_PAGES", 8), ("MAX_SELECTED_BYTES", sizes)):
            with patch("nqc_defense.archive_inventory." + name, limit):
                with self.assertRaisesRegex(Rejected, "inventory_verification_limit"):
                    self.inventory.inspect([full, prefix])

    def test_reference_and_report_limits_fail_without_partial_success(self):
        selected = self.populate(1)
        for name, limit, reason in (("MAX_REFERENCE_EDGES", 3, "inventory_reference_limit"),
                                    ("MAX_REPORT_BYTES", 128, "inventory_report_limit")):
            with patch("nqc_defense.archive_inventory." + name, limit):
                with self.assertRaisesRegex(Rejected, reason):
                    self.inventory.inspect([selected])

    def test_append_during_scan_is_detected_without_deleting_the_new_object(self):
        selected = self.populate(1)
        original = self.coverage.verify_catalog
        def changed(*args):
            result = original(*args)
            create_local(self.archive.root, "new-object", b"new real object")
            return result
        with patch.object(self.inventory.coverage, "verify_catalog", side_effect=changed):
            with self.assertRaisesRegex(Rejected, "inventory_changed_during_scan"):
                self.inventory.inspect([selected])
        self.assertEqual((self.archive.root / "new-object").read_bytes(), b"new real object")

    def test_same_content_file_replacement_after_verification_is_detected(self):
        selected = self.populate(1)
        original = self.coverage.verify_catalog
        path = self.page_path()
        def changed(*args):
            result = original(*args)
            data = path.read_bytes()
            path.unlink()
            create_local(path.parent, path.name, data)
            return result
        with patch.object(self.inventory.coverage, "verify_catalog", side_effect=changed):
            with self.assertRaisesRegex(Rejected, "inventory_changed_during_scan"):
                self.inventory.inspect([selected])

    def test_witness_tail_removal_after_catalog_verification_is_detected(self):
        selected = self.populate(1)
        original = self.coverage.verify_catalog
        def rollback(*args):
            result = original(*args)
            with self.witness.connection(write=True) as db:
                db.execute("DELETE FROM anchors WHERE revision=?", (selected["target_receipt"]["revision"],))
            return result
        with patch.object(self.inventory.coverage, "verify_catalog", side_effect=rollback):
            result = self.inventory.inspect([selected])
        self.assertFalse(result["verified"])
        self.assertEqual(result["issues"][0]["reason"], "witness_record_missing")

    def test_report_is_deterministic_and_does_not_mutate_archive_engine_or_witness(self):
        full = self.populate(2)
        prefix = self.select(end=1)
        selected = [full, prefix]
        before_input = copy.deepcopy(selected)
        before_files = {str(path.relative_to(self.archive.root)): path.read_bytes()
                        for path in self.archive.root.rglob("*") if path.is_file()}
        checkpoint, anchored = self.engine.checkpoint(), self.witness.head()
        first = self.inventory.inspect(selected)
        self.assertEqual(first, self.inventory.inspect(list(reversed(selected))))
        self.assertEqual(selected, before_input)
        self.assertEqual(self.engine.checkpoint(), checkpoint)
        self.assertEqual(self.witness.head(), anchored)
        after_files = {str(path.relative_to(self.archive.root)): path.read_bytes()
                       for path in self.archive.root.rglob("*") if path.is_file()}
        self.assertEqual(before_files, after_files)
        unsigned = {key: value for key, value in first.items() if key != "report_sha256"}
        self.assertEqual(first["report_sha256"], sha256(canonical(unsigned)))

    def test_cli_reads_pinned_selection_and_returns_failure_for_missing_page(self):
        selected = self.populate(1)
        for name, data in (("audit.key", self.key), ("witness.key", self.witness_key),
                           ("selection.json", canonical([selected]))):
            create_local(self.root, name, data)
        script = Path(__file__).resolve().parents[1] / "tools/archive_audit.py"
        args = [sys.executable, "-B", str(script), "--root", str(self.archive.root), "inventory",
                "--audit-key-file", str(self.root / "audit.key"), "--policy-digest", self.digest,
                "--witness-root", str(self.witness.root), "--witness-key-file", str(self.root / "witness.key"),
                "--selections", str(self.root / "selection.json")]
        result = subprocess.run(args, check=True, capture_output=True)
        self.assertTrue(decode(result.stdout, max_bytes=65536)["verified"])
        self.page_path().unlink()
        result = subprocess.run(args, capture_output=True)
        self.assertEqual(result.returncode, 2)
        report = decode(result.stdout, max_bytes=65536)
        self.assertFalse(report["verified"])
        self.assertEqual(report["issues"][0]["reason"], "missing_reference")


if __name__ == "__main__":
    unittest.main()
