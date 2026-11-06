import base64
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.case_evidence import capture_case, describe_case, verify_bundle
from nqc_defense.codec import Rejected, canonical
from nqc_defense.files import sha256
from nqc_defense.operations import OperationsStore


def record(second):
    return canonical({"schema": "nqc-auth-log-v1", "time_ns": second * 1000000000,
                      "outcome": "failure", "principal": "alice", "remote_address": "192.0.2.4"}) + b"\n"


class CaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / "auth.jsonl"
        self.lines = [record(i) for i in range(3)]
        self.log.write_bytes(b'{"unrelated":"private-outside-case"}\n' + b"".join(self.lines))
        self.store = OperationsStore.create(self.root / "ops")
        self.monitor = AuthLogMonitor.register(self.store, "auth", "tenant", "host", self.root, self.log.name, 3, 60)
        self.monitor.poll()
        self.case = self.store.cases("tenant", "host")[0]
        self.pin = sha256(canonical(self.case))
        self.output = self.root / "bundle.json"
        self.selection = [{"generation": 0, "name": self.log.name}]

    def capture(self, **changes):
        args = dict(store=self.store, tenant="tenant", asset="host", case_id=self.case["case_id"],
                    case_digest=self.pin, config_digest=self.monitor.digest, source_map=self.selection, output=self.output)
        args.update(changes)
        return capture_case(**args)

    def verify(self, data, digest=None):
        return verify_bundle(data, digest or sha256(data), "tenant", "host", self.case["case_id"], self.pin, self.monitor.digest)

    def altered(self, mutate):
        self.capture()
        value = json.loads(self.output.read_bytes()); mutate(value)
        return canonical(value)

    def test_capture_preserves_exact_trigger_bytes_and_can_verify_without_source(self):
        receipt = self.capture(); data = self.output.read_bytes()
        bundle = json.loads(data)
        self.assertEqual([base64.b64decode(r["raw_base64"]) for r in bundle["records"]], self.lines)
        self.assertNotIn(b"private-outside-case", b"".join(base64.b64decode(r["raw_base64"]) for r in bundle["records"]))
        self.log.unlink(); self.store.path.unlink()
        verified = self.verify(data, receipt["bundle_digest"])
        self.assertTrue(verified["trigger_conditions_verified"])
        self.assertFalse(verified["origin_authenticated"])
        self.assertFalse(verified["full_episode_history_included"])
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_description_exposes_pins_and_required_generations(self):
        result = describe_case(self.store, "tenant", "host", self.case["case_id"])
        self.assertEqual(result["case_digest"], self.pin)
        self.assertEqual(result["config_digest"], self.monitor.digest)
        self.assertEqual(result["generations"], [0])
        self.assertEqual(result["records"], 3)

    def test_integrity_case_cannot_be_exported_as_empty_auth_evidence(self):
        from nqc_defense.managed_integrity import ManagedIntegrity
        source = self.root / "config.json"; source.write_bytes(b"{}")
        managed = ManagedIntegrity.create(source, self.root / "managed")
        (managed.root / "assets/artifact.json").write_bytes(b"[]"); managed.inspect()
        case_id = self.store.capture_managed(managed, "tenant", "host")["case_id"]
        with self.assertRaisesRegex(Rejected, "evidence_case_unsupported"):
            self.capture(case_id=case_id)
        self.assertFalse(self.output.exists())

    def test_source_mutation_rejected_before_output(self):
        self.log.write_bytes(self.log.read_bytes().replace(b"alice", b"bobby"))
        with self.assertRaisesRegex(Rejected, "evidence_source_record_changed"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_source_changed_during_read_rejects_complete_acquisition(self):
        original_read = os.read
        changed = False
        def changing_read(fd, size):
            nonlocal changed
            data = original_read(fd, size)
            if not changed:
                changed = True
                with self.log.open("ab") as stream:
                    stream.write(b"changed-during-read\n")
            return data
        with patch("nqc_defense.auth_log.os.read", side_effect=changing_read):
            with self.assertRaisesRegex(Rejected, "auth_file_changed_during_read"):
                self.capture()
        self.assertFalse(self.output.exists())

    def test_missing_source_fails_without_output(self):
        self.log.unlink()
        with self.assertRaises(FileNotFoundError):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_missing_case_event_rejected(self):
        with self.store.transaction() as db:
            db.execute("DELETE FROM events WHERE id=?", (self.case["evidence_event_ids"][0],))
        with self.assertRaisesRegex(Rejected, "evidence_event_missing"):
            self.capture()

    def test_changed_stored_event_body_rejected(self):
        with self.store.transaction() as db:
            db.execute("UPDATE events SET body=? WHERE id=?", (b"{}", self.case["evidence_event_ids"][0]))
        with self.assertRaisesRegex(Rejected, "evidence_event_digest"):
            self.capture()

    def test_invalid_sqlite_payload_type_has_controlled_rejection(self):
        with self.store.transaction() as db:
            db.execute("UPDATE events SET body=? WHERE id=?", ("text-not-blob", self.case["evidence_event_ids"][0]))
        with self.assertRaisesRegex(Rejected, "evidence_event_storage_type"):
            self.capture()

    def test_changed_case_pin_rejected_before_source_read(self):
        with patch.object(AuthLogMonitor, "_snapshot", side_effect=AssertionError("must not read")):
            with self.assertRaisesRegex(Rejected, "evidence_case_digest"):
                self.capture(case_digest="0" * 64)

    def test_changed_registration_pin_rejected_before_source_read(self):
        with patch.object(AuthLogMonitor, "_snapshot", side_effect=AssertionError("must not read")):
            with self.assertRaisesRegex(Rejected, "evidence_config_binding"):
                self.capture(config_digest="0" * 64)

    def test_cross_tenant_case_lookup_rejected(self):
        with self.assertRaisesRegex(Rejected, "evidence_case_not_found"):
            self.capture(tenant="other")
        self.assertFalse(self.output.exists())

    def test_cross_asset_case_lookup_rejected(self):
        with self.assertRaisesRegex(Rejected, "evidence_case_not_found"):
            self.capture(asset="other")

    def test_wrong_inode_with_identical_bytes_rejected(self):
        (self.root / "copied.log").write_bytes(self.log.read_bytes())
        with self.assertRaisesRegex(Rejected, "evidence_file_identity"):
            self.capture(source_map=[{"generation": 0, "name": "copied.log"}])
        self.assertFalse(self.output.exists())

    def test_symlink_source_rejected(self):
        (self.root / "link").symlink_to(self.log)
        with self.assertRaises(OSError):
            self.capture(source_map=[{"generation": 0, "name": "link"}])

    def test_hardlinked_source_rejected(self):
        os.link(self.log, self.root / "linked")
        with self.assertRaisesRegex(Rejected, "auth_file_type_or_size"):
            self.capture()

    def test_source_selection_cannot_escape_registered_root(self):
        with self.assertRaisesRegex(Rejected, "unsafe_path"):
            self.capture(source_map=[{"generation": 0, "name": "../outside"}])

    def test_extra_generation_rejected_before_file_access(self):
        with self.assertRaisesRegex(Rejected, "evidence_source_selection"):
            self.capture(source_map=self.selection + [{"generation": 1, "name": "missing"}])

    def test_repeated_generation_rejected(self):
        with self.assertRaisesRegex(Rejected, "evidence_duplicate_generation"):
            self.capture(source_map=self.selection * 2)

    def test_public_output_directory_rejected(self):
        public = self.root / "public"; public.mkdir(mode=0o755)
        with self.assertRaisesRegex(Rejected, "evidence_output_permissions"):
            self.capture(output=public / "bundle.json")
        self.assertFalse((public / "bundle.json").exists())

    def test_existing_destination_not_overwritten(self):
        self.output.write_bytes(b"existing")
        with self.assertRaisesRegex(Rejected, "existing_file_differs"):
            self.capture()
        self.assertEqual(self.output.read_bytes(), b"existing")

    def test_storage_error_does_not_return_success(self):
        with patch("nqc_defense.case_evidence.publish_local", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                self.capture()
        self.assertFalse(self.output.exists())

    def test_readback_corruption_detected(self):
        from nqc_defense.files import publish_local
        def corrupt(root, name, data):
            publish_local(root, name, data)
            (Path(root) / name).write_bytes(b"{}")
        with patch("nqc_defense.case_evidence.publish_local", side_effect=corrupt):
            with self.assertRaisesRegex(Rejected, "evidence_bundle_digest"):
                self.capture()

    def test_wrong_external_bundle_pin_rejected(self):
        self.capture()
        with self.assertRaisesRegex(Rejected, "evidence_bundle_digest"):
            self.verify(self.output.read_bytes(), "0" * 64)

    def test_rehashed_raw_corruption_rejected(self):
        data = self.altered(lambda v: v["records"][0].update(raw_base64=base64.b64encode(record(99)).decode()))
        with self.assertRaisesRegex(Rejected, "evidence_raw_digest"):
            self.verify(data)

    def test_rehashed_event_change_rejected(self):
        data = self.altered(lambda v: v["records"][0]["event"].update(observed_ns=0))
        with self.assertRaisesRegex(Rejected, "evidence_event_digest"):
            self.verify(data)

    def test_normalized_attribute_change_fails_even_with_recomputed_event_hash(self):
        def mutate(value):
            item = value["records"][0]
            item["event"]["attributes"]["principal"] = "different"
            item["event_sha256"] = sha256(canonical(item["event"]))
        data = self.altered(mutate)
        with self.assertRaisesRegex(Rejected, "evidence_normalization"):
            self.verify(data)

    def test_case_snapshot_change_fails_against_external_pin(self):
        data = self.altered(lambda v: v["case"].update(status="closed"))
        with self.assertRaisesRegex(Rejected, "evidence_case_digest"):
            self.verify(data)

    def test_stored_configuration_change_fails_against_registration(self):
        with self.store.transaction() as db:
            config = json.loads(db.execute("SELECT config FROM streams WHERE id='auth'").fetchone()[0])
            config["root"] = "/unrelated"
            db.execute("UPDATE streams SET config=? WHERE id='auth'", (canonical(config),))
        with self.assertRaisesRegex(Rejected, "evidence_config_digest"):
            self.capture()

    def test_repeated_evidence_reference_in_case_rejected(self):
        with self.store.transaction() as db:
            case = dict(self.case)
            case["evidence_event_ids"] = [case["evidence_event_ids"][0]] * 3
            db.execute("UPDATE cases SET body=? WHERE id=?", (canonical(case), self.case["case_id"]))
        with self.assertRaisesRegex(Rejected, "evidence_duplicate_reference"):
            self.capture()

    def test_missing_record_rejected(self):
        data = self.altered(lambda v: v["records"].pop())
        with self.assertRaisesRegex(Rejected, "evidence_record_count"):
            self.verify(data)

    def test_reordered_records_rejected(self):
        data = self.altered(lambda v: v["records"].reverse())
        with self.assertRaises(Rejected):
            self.verify(data)

    def test_invalid_base64_rejected(self):
        data = self.altered(lambda v: v["records"][0].update(raw_base64="@@@"))
        with self.assertRaisesRegex(Rejected, "evidence_record_encoding"):
            self.verify(data)

    def test_noncanonical_bundle_rejected_even_with_matching_digest(self):
        self.capture(); data = json.dumps(json.loads(self.output.read_bytes()), indent=2).encode()
        with self.assertRaisesRegex(Rejected, "evidence_bundle_format"):
            self.verify(data)

    def test_verifier_does_not_follow_paths_from_bundle(self):
        self.capture()
        with patch.object(AuthLogMonitor, "_snapshot", side_effect=AssertionError("offline only")):
            self.assertTrue(self.verify(self.output.read_bytes())["verified"])

    def test_source_budget_exhaustion_prevents_publication(self):
        with patch("nqc_defense.case_evidence.MAX_SOURCE_BYTES", 1):
            with self.assertRaisesRegex(Rejected, "evidence_source_budget"):
                self.capture()
        self.assertFalse(self.output.exists())

    def test_bundle_size_exhaustion_prevents_publication(self):
        with patch("nqc_defense.case_evidence.MAX_BUNDLE", 128):
            with self.assertRaisesRegex(Rejected, "evidence_bundle_size"):
                self.capture()
        self.assertFalse(self.output.exists())

    def test_capture_case_across_explicit_rotation(self):
        log = self.root / "rotated.log"; log.write_bytes(record(0) + record(1))
        mon = AuthLogMonitor.register(self.store, "rotated", "tenant", "rotated", self.root, log.name, 3, 60)
        mon.poll(); log.rename(self.root / "rotated.old"); log.write_bytes(record(2))
        mon.rotate("rotated.old"); mon.poll()
        case = self.store.cases("tenant", "rotated")[0]; pin = sha256(canonical(case))
        receipt = capture_case(self.store, "tenant", "rotated", case["case_id"], pin, mon.digest,
                               [{"generation": 0, "name": "rotated.old"}, {"generation": 1, "name": log.name}], self.output)
        self.assertEqual(receipt["records"], 3)
        self.assertEqual(len(json.loads(self.output.read_bytes())["files"]), 2)

    def test_native_journal_record_normalization_is_rechecked(self):
        native = self.root / "journal.jsonl"
        messages = []
        for index in range(3):
            messages.append(canonical({"MESSAGE": "Failed password for alice from 192.0.2.4 port 44100 ssh2",
                "__REALTIME_TIMESTAMP": str(1793966400000000 + index * 1000000), "__CURSOR": f"s=test;i={index}",
                "_BOOT_ID": "a" * 32, "_HOSTNAME": "host-a", "_COMM": "sshd", "_PID": "15"}) + b"\n")
        native.write_bytes(b"".join(messages))
        mon = AuthLogMonitor.register(self.store, "journal", "tenant", "native", self.root, native.name,
                                       3, 60, format_name="openssh-journal-json", expected_host="host-a")
        mon.poll(); case = self.store.cases("tenant", "native")[0]
        result = capture_case(self.store, "tenant", "native", case["case_id"], sha256(canonical(case)), mon.digest,
                              [{"generation": 0, "name": native.name}], self.output)
        self.assertTrue(result["trigger_conditions_verified"])

    def test_cli_capture_and_offline_verify(self):
        tool = Path(__file__).resolve().parents[1] / "tools/case_evidence.py"
        selection = self.root / "selection.json"; selection.write_bytes(canonical(self.selection))
        common = ["--tenant", "tenant", "--asset", "host", "--case-id", self.case["case_id"],
                  "--case-digest", self.pin, "--config-digest", self.monitor.digest]
        result = subprocess.run([sys.executable, "-B", str(tool), "capture", "--store-root", str(self.store.root),
                                  "--source-map", str(selection), "--output", str(self.output), *common], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = json.loads(result.stdout); self.log.unlink(); self.store.path.unlink()
        verified = subprocess.run([sys.executable, "-B", str(tool), "verify", "--input", str(self.output),
                                    "--digest", receipt["bundle_digest"], *common], capture_output=True, text=True)
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertTrue(json.loads(verified.stdout)["verified"])


if __name__ == "__main__":
    unittest.main()
