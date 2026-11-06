from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from nqc_defense.auth_log import AuthLogMonitor, MAX_LINE, parse_auth
from nqc_defense.codec import Rejected, canonical
from nqc_defense.managed_integrity import ManagedIntegrity
from nqc_defense.operations import OperationsStore


def record(second, outcome="failure", principal="alice", address="192.0.2.1"):
    return canonical({"schema": "nqc-auth-log-v1", "time_ns": second * 1000000000,
                      "outcome": outcome, "principal": principal, "remote_address": address}) + b"\n"


class AuthLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.log = self.root / "auth.jsonl"
        self.log.write_bytes(b"")
        self.store = OperationsStore.create(self.root / "ops")
        self.monitor = AuthLogMonitor.register(self.store, "auth", "tenant", "host", self.root, self.log.name, 3, 60)

    def add(self, *lines):
        with self.log.open("ab") as output:
            output.write(b"".join(lines))

    def events(self):
        return self.store.events("tenant", "host")

    def cases(self):
        return self.store.cases("tenant", "host")

    def test_failures_open_one_case_with_actual_event_references(self):
        self.add(*(record(i) for i in range(5)))
        result = self.monitor.poll()
        self.assertEqual((result["records_committed"], result["cases_opened"]), (5, 1))
        case = self.cases()[0]
        self.assertEqual(case["evidence_event_ids"], [r["event"]["event_id"] for r in self.events()[:3]])
        self.assertFalse(case["automatic_response"])

    def test_partial_line_only_commits_after_newline(self):
        line = record(1); self.add(line[:-1])
        self.assertEqual(self.monitor.poll()["records_committed"], 0)
        self.add(b"\n"); self.assertEqual(self.monitor.poll()["records_committed"], 1)

    def test_reopen_does_not_duplicate_committed_events(self):
        self.add(record(1)); self.monitor.poll()
        other = AuthLogMonitor(OperationsStore(self.store.root), "auth", self.monitor.digest)
        self.assertEqual(other.poll()["records_committed"], 0)
        self.add(record(2)); self.assertEqual(other.poll()["records_committed"], 1)
        self.assertEqual(len(self.events()), 2)

    def test_success_resets_episode_but_does_not_resolve_existing_case(self):
        self.add(*(record(i) for i in range(3)), record(3, "success"), *(record(i) for i in range(4, 7)))
        self.assertEqual(self.monitor.poll()["cases_opened"], 2)
        self.assertEqual([c["status"] for c in self.cases()], ["open", "open"])

    def test_window_expiry_does_not_combine_old_failures(self):
        self.add(record(0), record(1), record(100))
        self.assertEqual(self.monitor.poll()["cases_opened"], 0)
        self.add(record(101), record(102)); self.assertEqual(self.monitor.poll()["cases_opened"], 1)

    def test_exact_window_boundary_included(self):
        self.add(record(0), record(30), record(60)); self.assertEqual(self.monitor.poll()["cases_opened"], 1)

    def test_late_records_are_stored_and_excluded_explicitly(self):
        self.add(record(10), record(9), record(11)); result = self.monitor.poll()
        self.assertEqual((result["late_records"], result["cases_opened"]), (1, 0))
        self.assertEqual(self.events()[1]["event"]["attributes"]["rule_exclusion"], "out_of_order")

    def test_invalid_line_is_quality_event_without_secret_content(self):
        self.add(b'{"password":"sensitive-test-value"}\n', record(1)); result = self.monitor.poll()
        self.assertEqual((result["records_committed"], result["invalid_records"]), (2, 1))
        self.assertEqual(self.events()[0]["event"]["kind"], "sensor.input_rejected")
        self.assertNotIn("sensitive-test-value", json.dumps(self.events()))

    def test_consumed_prefix_edit_fails_without_advancing(self):
        self.add(record(1)); self.monitor.poll(); self.log.write_bytes(record(2))
        with self.assertRaisesRegex(Rejected, "auth_consumed_prefix_changed"):
            self.monitor.poll()
        self.assertEqual(len(self.events()), 1)

    def test_truncation_fails_explicitly(self):
        self.add(record(1)); self.monitor.poll(); self.log.write_bytes(b"")
        with self.assertRaisesRegex(Rejected, "auth_log_truncated"):
            self.monitor.poll()

    def test_rotation_requires_drain_and_explicit_handoff(self):
        self.add(record(1), record(2)); self.monitor.poll(max_records=1)
        self.log.rename(self.root / "auth.old"); self.log.write_bytes(record(3))
        with self.assertRaisesRegex(Rejected, "auth_rotation_required"):
            self.monitor.poll()
        with self.assertRaisesRegex(Rejected, "auth_previous_not_drained"):
            self.monitor.rotate("auth.old")
        self.assertEqual(self.monitor.poll("auth.old")["records_committed"], 1)
        self.assertTrue(self.monitor.rotate("auth.old")["rotated"])
        reopened = AuthLogMonitor(OperationsStore(self.store.root), "auth", self.monitor.digest)
        self.assertEqual(reopened.poll()["cases_opened"], 1)
        self.assertEqual([x["event"]["kind"] for x in self.events()], ["auth.observation", "auth.observation", "sensor.rotation", "auth.observation"])

    def test_partial_old_tail_blocks_rotation(self):
        self.add(record(1)[:-1]); self.log.rename(self.root / "auth.old"); self.log.write_bytes(b"")
        self.assertEqual(self.monitor.poll("auth.old")["records_committed"], 0)
        with self.assertRaisesRegex(Rejected, "auth_previous_not_drained"):
            self.monitor.rotate("auth.old")

    def test_wrong_previous_file_rejected(self):
        (self.root / "wrong").write_bytes(b"")
        with self.assertRaisesRegex(Rejected, "auth_rotation_required"):
            self.monitor.rotate("wrong")

    def test_rotation_to_same_inode_rejected(self):
        with self.assertRaisesRegex(Rejected, "auth_rotation_identity_unchanged"):
            self.monitor.rotate(self.log.name)

    def test_long_line_rolls_back_entire_batch(self):
        self.add(record(1), b"x" * MAX_LINE)
        with self.assertRaisesRegex(Rejected, "auth_line_too_long"):
            self.monitor.poll()
        self.assertEqual(self.events(), [])
        self.log.write_bytes(record(1)); self.assertEqual(self.monitor.poll()["records_committed"], 1)

    def test_event_capacity_rolls_back_cursor_and_events(self):
        self.add(record(1), record(2))
        with patch("nqc_defense.operations.MAX_EVENTS", 1):
            with self.assertRaisesRegex(Rejected, "operations_event_capacity"):
                self.monitor.poll()
        self.assertEqual(self.events(), []); self.assertEqual(self.monitor.poll()["records_committed"], 2)

    def test_case_failure_rolls_back_cursor_events_and_episode(self):
        self.add(*(record(i) for i in range(3)))
        with self.store.transaction() as db:
            db.execute("CREATE TRIGGER fail_case BEFORE INSERT ON cases BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.monitor.poll()
        self.assertEqual(self.events(), [])
        with self.store.transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM episodes").fetchone()[0], 0)
            db.execute("DROP TRIGGER fail_case")
        self.assertEqual(self.monitor.poll()["cases_opened"], 1)

    def test_competing_pollers_commit_each_line_once(self):
        self.add(*(record(i) for i in range(10)))
        other = AuthLogMonitor(OperationsStore(self.store.root), "auth", self.monitor.digest)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda m: m.poll(), [self.monitor, other]))
        self.assertEqual(sum(r["records_committed"] for r in results), 10)
        self.assertEqual(len(self.events()), 10)

    def test_missing_database_never_recreated(self):
        self.store.path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.monitor.poll()
        self.assertFalse(self.store.path.exists())

    def test_wrong_configuration_pin_rejected(self):
        with self.assertRaisesRegex(Rejected, "auth_source_binding"):
            AuthLogMonitor(self.store, "auth", "0" * 64)

    def test_source_re_registration_rejected(self):
        with self.assertRaisesRegex(Rejected, "auth_source_exists"):
            AuthLogMonitor.register(self.store, "auth", "tenant", "host", self.root, self.log.name)

    def test_distinct_principals_do_not_join_failures(self):
        self.add(record(1), record(2, principal="bob"), record(3)); self.assertEqual(self.monitor.poll()["cases_opened"], 0)

    def test_distinct_addresses_do_not_join_failures(self):
        self.add(record(1), record(2, address="192.0.2.2"), record(3)); self.assertEqual(self.monitor.poll()["cases_opened"], 0)

    def test_scope_filters_and_pagination(self):
        self.add(*(record(i) for i in range(3))); self.monitor.poll()
        self.assertEqual(self.store.events("other", "host"), [])
        self.assertEqual(self.store.cases("tenant", "other"), [])
        page = self.store.events("tenant", "host", limit=1)
        self.assertEqual(len(self.store.events("tenant", "host", after=page[0]["sequence"])), 2)

    def test_symlink_log_rejected(self):
        self.log.unlink(); self.log.symlink_to(self.store.path)
        with self.assertRaises(OSError):
            self.monitor.poll()

    def test_hardlink_log_rejected(self):
        os.link(self.log, self.root / "alias")
        with self.assertRaisesRegex(Rejected, "auth_file_type_or_size"):
            self.monitor.poll()

    def test_fifo_log_rejected_without_blocking(self):
        self.log.unlink(); os.mkfifo(self.log)
        with self.assertRaisesRegex(Rejected, "auth_file_type_or_size"):
            self.monitor.poll()

    def test_record_parser_rejects_bool_time_and_extra_fields(self):
        for change in ({"time_ns": True}, {"extra": "not allowed"}, {"remote_address": "host.example"}):
            obj = json.loads(record(1)); obj.update(change)
            with self.assertRaises(Rejected):
                parse_auth(canonical(obj))

    def test_ipv6_normalization(self):
        self.assertEqual(parse_auth(record(1, address="2001:db8:0:0::1"))["remote_address"], "2001:db8::1")

    def test_batch_limit_resumes_without_skipping(self):
        self.add(*(record(i) for i in range(5)))
        self.assertEqual(self.monitor.poll(max_records=2)["records_committed"], 2)
        self.assertEqual(self.monitor.poll(max_records=2)["records_committed"], 2)
        self.assertEqual(self.monitor.poll()["records_committed"], 1)
        self.assertEqual(len(self.cases()), 1)

    def test_raw_byte_reference_is_exact(self):
        from nqc_defense.files import sha256
        line = record(1); self.add(line); self.monitor.poll()
        evidence = self.events()[0]["event"]["evidence"]
        self.assertEqual((evidence["start"], evidence["end"], evidence["raw_sha256"]), (0, len(line), sha256(line)))

    def test_shared_view_imports_existing_managed_incident_idempotently(self):
        source = self.root / "source.json"; source.write_bytes(b'{"enabled":true}')
        managed = ManagedIntegrity.create(source, self.root / "managed")
        self.assertFalse(self.store.capture_managed(managed, "tenant", "host")["imported"])
        (managed.root / "assets/artifact.json").write_bytes(b"{}"); managed.inspect()
        self.assertTrue(self.store.capture_managed(managed, "tenant", "host")["imported"])
        self.assertFalse(self.store.capture_managed(managed, "tenant", "host")["imported"])
        self.add(*(record(i) for i in range(3))); self.monitor.poll()
        self.assertEqual({c["category"] for c in self.cases()}, {"authentication", "managed_integrity"})
        managed.recover(); self.store.capture_managed(managed, "tenant", "host")
        self.assertEqual(next(c for c in self.cases() if c["category"] == "managed_integrity")["status"], "source_reported_resolved")
        self.assertEqual(len(self.cases()), 2)

    def test_cli_reads_real_log_and_returns_case(self):
        self.add(*(record(i) for i in range(3)))
        tool = Path(__file__).resolve().parents[1] / "tools/operations.py"
        def invoke(*args):
            result = subprocess.run([sys.executable, "-B", str(tool), "--root", str(self.store.root), *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return json.loads(result.stdout)
        self.assertEqual(invoke("poll-auth", "--source", "auth", "--config-digest", self.monitor.digest)["cases_opened"], 1)
        self.assertEqual(len(invoke("cases", "--tenant", "tenant", "--asset", "host")["cases"]), 1)

    def test_event_digest_detects_payload_change(self):
        self.add(record(1)); self.monitor.poll()
        with self.store.transaction() as db:
            db.execute("UPDATE events SET body=?", (b"{}",))
        with self.assertRaisesRegex(Rejected, "operations_event_digest"):
            self.events()

    def test_delayed_managed_snapshot_cannot_reopen_newer_case(self):
        source = self.root / "source.json"; source.write_bytes(b"{}")
        managed = ManagedIntegrity.create(source, self.root / "managed")
        (managed.root / "assets/artifact.json").write_bytes(b"[]")
        managed.inspect(); old = managed.status()
        managed.recover(); self.store.capture_managed(managed, "tenant", "host")
        with patch.object(managed, "status", return_value=old):
            self.store.capture_managed(managed, "tenant", "host")
        self.assertEqual(self.cases()[0]["status"], "source_reported_resolved")

    def test_case_capacity_rolls_back_batch(self):
        self.add(*(record(i) for i in range(3)))
        with patch("nqc_defense.operations.MAX_CASES", 0):
            with self.assertRaisesRegex(Rejected, "operations_case_capacity"):
                self.monitor.poll()
        self.assertEqual(self.events(), [])
        self.assertEqual(self.monitor.poll()["cases_opened"], 1)

    def test_process_exit_before_commit_rolls_back_events_and_cursor(self):
        self.add(record(1), record(2))
        script = '''
import os, sys
from nqc_defense.operations import OperationsStore
from nqc_defense.auth_log import AuthLogMonitor
store = OperationsStore(sys.argv[1])
append = store.append
def crash(db, event):
    append(db, event)
    os._exit(73)
store.append = crash
AuthLogMonitor(store, "auth", sys.argv[2]).poll()
'''
        result = subprocess.run([sys.executable, "-B", "-c", script, str(self.store.root), self.monitor.digest],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True)
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertEqual(self.events(), [])
        self.assertEqual(self.monitor.poll()["records_committed"], 2)

    def test_published_config_pin_detects_config_edit(self):
        with self.store.transaction() as db:
            db.execute("UPDATE streams SET config=?", (b"{}",))
        with self.assertRaisesRegex(Rejected, "auth_source_binding"):
            self.monitor.poll()


if __name__ == "__main__":
    unittest.main()
