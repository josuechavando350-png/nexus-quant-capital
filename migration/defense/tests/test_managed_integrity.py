import json
import fcntl
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from nqc_defense.managed_integrity import ManagedIntegrity
from nqc_defense.codec import Rejected


class ManagedIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.json"
        self.original = b'{"configuration":{"enabled":true},"version":1}\n'
        self.source.write_bytes(self.original)
        self.managed = ManagedIntegrity.create(self.source, self.root / "managed")
        self.artifact = self.managed.root / "assets/artifact.json"

    def alter(self):
        self.artifact.write_bytes(b'{"configuration":{"enabled":false},"version":2}')

    def test_database_removed_after_open_is_not_recreated(self):
        database = self.managed.root / "control/state/state.sqlite3"
        database.unlink()
        with self.assertRaises(FileNotFoundError):
            self.managed.inspect()
        self.assertFalse(database.exists())

    def test_cooperating_operation_lock_rejects_overlap(self):
        handle = os.open(self.managed.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(Rejected, "managed_operation_busy"):
                self.managed.inspect()
        finally:
            os.close(handle)
        self.assertFalse(self.managed.inspect()["contained"])

    def test_witness_removed_after_open_is_not_recreated(self):
        database = self.managed.root / "witness/witness.sqlite3"
        database.unlink()
        with self.assertRaises(FileNotFoundError):
            self.managed.read_json()
        self.assertFalse(database.exists())

    def test_real_observation_incident_containment_restore_and_verified_read(self):
        self.assertFalse(self.managed.inspect()["contained"])
        self.assertTrue(self.managed.read_json()["data"]["configuration"]["enabled"])
        self.alter()
        alarm = self.managed.inspect()
        self.assertTrue(alarm["contained"])
        self.assertEqual(alarm["incident"]["status"], "open")
        with self.assertRaisesRegex(Rejected, "asset_quarantined"):
            self.managed.read_json()
        recovered = self.managed.recover()
        self.assertFalse(recovered["contained"])
        self.assertEqual(recovered["incident"]["status"], "resolved")
        self.assertEqual(recovered["recovered_case_id"], alarm["incident"]["case_id"])
        self.assertTrue(recovered["read_after_recovery_verified"])
        self.assertEqual(self.artifact.read_bytes(), self.original)
        self.assertEqual(self.source.read_bytes(), self.original)
        archived = self.managed.archive_evidence()
        self.assertTrue(archived["archived"] and archived["stored_pages_verified"])
        self.assertEqual(self.managed.archive_evidence()["reason"], "no_new_events")

    def test_reopen_preserves_open_and_resolved_incident(self):
        self.alter()
        first = self.managed.inspect()["incident"]
        reopened = ManagedIntegrity(self.managed.root, self.managed.digest)
        self.assertEqual(reopened.status()["incident"], first)
        reopened.recover()
        self.assertEqual(ManagedIntegrity(reopened.root, reopened.digest).status()["incident"]["status"], "resolved")

    def test_contained_poll_is_not_claimed_as_a_new_observation(self):
        self.alter()
        first = self.managed.inspect()
        second = self.managed.inspect()
        self.assertFalse(second["observation_performed"])
        self.assertEqual(first["incident"], second["incident"])
        self.assertEqual(first["checkpoint"], second["checkpoint"])

    def test_direct_consumer_detection_also_opens_incident(self):
        self.alter()
        with self.assertRaisesRegex(Rejected, "artifact_not_admitted"):
            self.managed.read_json()
        self.assertTrue(self.managed.status()["contained"])
        self.assertEqual(self.managed.status()["incident"]["status"], "open")

    def test_changed_canary_is_restored_and_verified(self):
        path = self.managed.root / "assets/canary"
        before = path.read_bytes()
        path.write_bytes(b"controlled alteration")
        self.assertTrue(self.managed.inspect()["contained"])
        self.managed.recover()
        self.assertEqual(path.read_bytes(), before)

    def test_missing_managed_artifact_can_be_restored(self):
        self.artifact.unlink()
        self.assertTrue(self.managed.inspect()["contained"])
        self.managed.recover()
        self.assertEqual(self.artifact.read_bytes(), self.original)

    def test_unverified_baseline_never_replaces_managed_file(self):
        self.alter()
        self.managed.inspect()
        before = self.artifact.read_bytes()
        (self.managed.root / "baseline/artifact.json").write_bytes(b"untrusted backup")
        with self.assertRaisesRegex(Rejected, "managed_baseline_integrity"):
            self.managed.recover()
        self.assertEqual(self.artifact.read_bytes(), before)
        self.assertTrue(self.managed.status()["contained"])

    def test_canary_baseline_checked_before_any_replacement(self):
        self.alter()
        self.managed.inspect()
        before = self.artifact.read_bytes()
        (self.managed.root / "baseline/canary").write_bytes(b"untrusted backup")
        with self.assertRaisesRegex(Rejected, "managed_baseline_integrity"):
            self.managed.recover()
        self.assertEqual(self.artifact.read_bytes(), before)

    def test_restore_never_follows_symlink_to_original_source(self):
        self.artifact.unlink()
        self.artifact.symlink_to(self.source)
        self.managed.inspect()
        with self.assertRaisesRegex(Rejected, "managed_restore_target_type"):
            self.managed.recover()
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_hardlinked_target_is_not_replaced(self):
        self.alter()
        self.managed.inspect()
        os.link(self.artifact, self.root / "alias")
        with self.assertRaisesRegex(Rejected, "managed_restore_target_type"):
            self.managed.recover()
        self.assertEqual(self.artifact.stat().st_nlink, 2)

    def test_failed_restore_write_keeps_incident_open(self):
        self.alter()
        self.managed.inspect()
        with patch("nqc_defense.managed_integrity.os.replace", side_effect=OSError("injected replacement failure")):
            with self.assertRaises(OSError):
                self.managed.recover()
        self.assertTrue(self.managed.status()["contained"])
        self.assertEqual(list((self.managed.root / "assets").glob("restore-*")), [])
        self.assertTrue(self.managed.recover()["read_after_recovery_verified"])

    def test_release_audit_failure_keeps_gate_closed_after_restoration(self):
        self.alter()
        self.managed.inspect()
        with self.managed.engine.state.transaction() as db:
            db.execute("CREATE TRIGGER reject_release BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'controlled audit failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.managed.recover()
        self.assertEqual(self.artifact.read_bytes(), self.original)
        self.assertTrue(self.managed.status()["contained"])
        with self.managed.engine.state.transaction() as db:
            db.execute("DROP TRIGGER reject_release")
        self.assertTrue(self.managed.recover()["read_after_recovery_verified"])

    def test_rate_rejection_is_not_fabricated_as_security_incident(self):
        for _ in range(30):
            self.managed.inspect()
        with self.assertRaisesRegex(Rejected, "managed_inspection_incomplete"):
            self.managed.inspect()
        self.assertIsNone(self.managed.status()["incident"])

    def test_manifest_tampering_and_wrong_pin_rejected(self):
        with self.assertRaisesRegex(Rejected, "managed_manifest_integrity"):
            ManagedIntegrity(self.managed.root, "f" * 64)
        (self.managed.root / "managed.json").write_bytes(b"{}")
        with self.assertRaisesRegex(Rejected, "managed_manifest_integrity"):
            self.managed.inspect()

    def test_missing_database_is_not_silently_recreated(self):
        path = self.managed.root / "control/state/state.sqlite3"
        path.unlink()
        with self.assertRaises(OSError):
            ManagedIntegrity(self.managed.root, self.managed.digest)
        self.assertFalse(path.exists())

    def test_new_incident_after_recovery_has_different_evidence_identity(self):
        self.alter()
        first = self.managed.inspect()["incident"]["case_id"]
        self.managed.recover()
        self.alter()
        second = self.managed.inspect()["incident"]["case_id"]
        self.assertNotEqual(first, second)

    def test_recovery_requires_an_open_incident(self):
        with self.assertRaisesRegex(Rejected, "managed_no_open_incident"):
            self.managed.recover()

    def test_init_never_overwrites_existing_root_or_accepts_invalid_json(self):
        with self.assertRaises(FileExistsError):
            ManagedIntegrity.create(self.source, self.managed.root)
        self.source.write_bytes(b"not JSON")
        target = self.root / "new-managed"
        with self.assertRaises(Rejected):
            ManagedIntegrity.create(self.source, target)
        self.assertFalse(target.exists())

    def test_cli_sample_inspect_recover_and_archive(self):
        script = Path(__file__).resolve().parents[1] / "tools/managed_integrity.py"
        base = [sys.executable, "-B", str(script), "--root", str(self.managed.root), "--manifest-digest", self.managed.digest]
        sample = json.loads(subprocess.run([*base, "monitor", "--samples", "1"], check=True, capture_output=True).stdout)
        self.assertTrue(sample["observation_performed"])
        self.alter()
        alarm = json.loads(subprocess.run([*base, "inspect"], check=True, capture_output=True).stdout)
        self.assertTrue(alarm["contained"])
        recovery = json.loads(subprocess.run([*base, "recover"], check=True, capture_output=True).stdout)
        self.assertTrue(recovery["read_after_recovery_verified"])
        archived = json.loads(subprocess.run([*base, "archive"], check=True, capture_output=True).stdout)
        self.assertTrue(archived["archived"])


if __name__ == "__main__":
    unittest.main()
