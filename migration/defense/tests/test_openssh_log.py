import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.codec import Rejected, canonical
from nqc_defense.openssh_log import Unclassified, parse_openssh, source_options, timestamp_ns
from nqc_defense.operations import OperationsStore

CONFIG = {"format": "openssh-syslog-rfc3339", "expected_host": "host-a"}
MESSAGE = "Failed password for alice from 192.0.2.10 port 45500 ssh2"


def syslog(message=MESSAGE, stamp="2026-11-06T12:00:00Z", host="host-a", process="sshd", pid=123):
    return f"{stamp} {host} {process}[{pid}]: {message}\n".encode()


def journal(cursor="s=one;i=1", message=MESSAGE, time="1793966400000000", **extra):
    fields = {"MESSAGE": message, "__REALTIME_TIMESTAMP": time, "__CURSOR": cursor,
              "_BOOT_ID": "a" * 32, "_HOSTNAME": "host-a", "_COMM": "sshd", "_PID": "123"}
    fields.update(extra)
    return canonical(fields) + b"\n"


class OpenSSHParserTests(unittest.TestCase):
    def test_failure_and_invalid_user(self):
        result = parse_openssh(syslog(MESSAGE.replace("for alice", "for invalid user alice")), CONFIG)
        self.assertEqual(result["outcome"], "failure")
        self.assertTrue(result["invalid_user"])
        self.assertFalse(result["origin"]["origin_authenticated"])

    def test_accepted_public_key_with_detail_preserves_only_message_digest(self):
        value = parse_openssh(syslog("Accepted publickey for alice from 192.0.2.10 port 45500 ssh2: ED25519 SHA256:testdetail"), CONFIG)
        self.assertEqual(value["outcome"], "success")
        self.assertNotIn("testdetail", json.dumps(value))

    def test_ipv6_and_new_session_process(self):
        value = parse_openssh(syslog(MESSAGE.replace("192.0.2.10", "2001:db8:0:0::1"), process="sshd-session"), CONFIG)
        self.assertEqual(value["remote_address"], "2001:db8::1")
        self.assertEqual(value["origin"]["process_name"], "sshd-session")

    def test_principal_with_dot_at_and_machine_suffix(self):
        for name in ("alice.smith", "alice@example", "machine$"):
            self.assertEqual(parse_openssh(syslog(MESSAGE.replace("alice", name)), CONFIG)["principal"], name)

    def test_keyboard_interactive_pam_and_preauth(self):
        value = parse_openssh(syslog(MESSAGE.replace("password", "keyboard-interactive/pam") + " [preauth]"), CONFIG)
        self.assertEqual(value["method"], "keyboard-interactive/pam")

    def test_partial_and_postponed_are_not_final_success_or_failure(self):
        for status in ("Partial", "Postponed"):
            with self.assertRaisesRegex(Unclassified, "ssh_nonfinal_authentication"):
                parse_openssh(syslog(MESSAGE.replace("Failed", status)), CONFIG)

    def test_invalid_user_pam_and_disconnect_messages_are_unclassified(self):
        for message in ("Invalid user alice from 192.0.2.10 port 45500", "pam_unix(sshd:auth): authentication failure", "Disconnected from 192.0.2.10 port 45500"):
            with self.assertRaises(Unclassified):
                parse_openssh(syslog(message), CONFIG)

    def test_unknown_method_does_not_become_success(self):
        with self.assertRaisesRegex(Unclassified, "ssh_unsupported_auth_method"):
            parse_openssh(syslog(MESSAGE.replace("Failed password", "Accepted futuremethod")), CONFIG)

    def test_host_mismatch_rejected(self):
        with self.assertRaisesRegex(Rejected, "ssh_host_mismatch"):
            parse_openssh(syslog(host="other"), CONFIG)

    def test_spoofed_process_name_rejected(self):
        with self.assertRaises(Rejected):
            parse_openssh(syslog(process="app-sshd"), CONFIG)

    def test_missing_year_timezone_and_unknown_offset_rejected(self):
        for stamp in ("Nov  6 12:00:00", "2026-11-06T12:00:00", "2026-11-06T12:00:00-00:00"):
            with self.assertRaises(Rejected):
                parse_openssh(syslog(stamp=stamp), CONFIG)

    def test_timestamp_nanoseconds_and_offset_are_exact(self):
        expected = timestamp_ns("2026-11-06T12:00:00Z")
        self.assertEqual(timestamp_ns("2026-11-06T06:00:00.123456789-06:00"), expected + 123456789)
        self.assertEqual(parse_openssh(syslog(stamp="2026-11-06T12:00:00.123Z"), CONFIG)["origin"]["time_resolution_ns"], 1000000)

    def test_impossible_timestamp_leap_second_and_range_rejected(self):
        for stamp in ("2026-02-30T12:00:00Z", "2026-11-06T12:00:60Z", "1960-01-01T00:00:00Z", "9999-01-01T00:00:00Z", "2026-11-06T12:00:00+24:00"):
            with self.assertRaises(Rejected):
                timestamp_ns(stamp)

    def test_invalid_ip_port_and_pid(self):
        for line in (syslog(MESSAGE.replace("192.0.2.10", "999.0.2.10")), syslog(MESSAGE.replace("45500", "65536")), syslog(pid=0)):
            with self.assertRaises(Rejected):
                parse_openssh(line, CONFIG)

    def test_control_characters_and_multiple_lines_rejected(self):
        for message in (MESSAGE + "\x1b", MESSAGE + "\r", MESSAGE + "\n" + MESSAGE):
            with self.assertRaises(Rejected):
                parse_openssh(syslog(message), CONFIG)

    def test_inconsistent_accepted_invalid_user_rejected(self):
        with self.assertRaisesRegex(Rejected, "ssh_inconsistent_result"):
            parse_openssh(syslog(MESSAGE.replace("Failed password for", "Accepted password for invalid user")), CONFIG)

    def test_journal_fields_microseconds_and_opaque_identity(self):
        value = parse_openssh(journal(), {**CONFIG, "format": "openssh-journal-json"})
        self.assertEqual(value["time_ns"], 1793966400000000000)
        self.assertEqual(len(value["native_record_id"]), 64)
        self.assertNotIn("s=one;i=1", json.dumps(value))

    def test_journal_required_scalar_fields(self):
        for field in ("MESSAGE", "__REALTIME_TIMESTAMP", "_PID", "__CURSOR"):
            for replacement in (None, [], 3):
                with self.assertRaises(Rejected):
                    parse_openssh(journal(**{field: replacement}), {**CONFIG, "format": "openssh-journal-json"})

    def test_journal_wrong_host_process_and_boot_identity(self):
        for change in ({"_HOSTNAME": "other"}, {"_COMM": "sudo"}, {"_BOOT_ID": "invalid"}, {"__CURSOR": "bad\nvalue"}):
            with self.assertRaises(Rejected):
                parse_openssh(journal(**change), {**CONFIG, "format": "openssh-journal-json"})

    def test_duplicate_json_keys_rejected(self):
        line = journal().replace(b'"MESSAGE":', b'"MESSAGE":"duplicate","MESSAGE":')
        with self.assertRaises(Rejected):
            parse_openssh(line, {**CONFIG, "format": "openssh-journal-json"})

    def test_source_options_require_host_and_preserve_legacy(self):
        self.assertEqual(source_options("nqc-jsonl", None), {})
        for fmt, host in (("unknown", "host-a"), ("openssh-journal-json", None), ("nqc-jsonl", "host-a")):
            with self.assertRaises(Rejected):
                source_options(fmt, host)


class OpenSSHPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.log = self.root / "auth.log"; self.log.write_bytes(b"")
        self.store = OperationsStore.create(self.root / "ops")

    def monitor(self, fmt="openssh-journal-json"):
        return AuthLogMonitor.register(self.store, "native", "tenant", "server", self.root, self.log.name,
                                       3, 60, format_name=fmt, expected_host="host-a")

    def events(self):
        return [r["event"] for r in self.store.events("tenant", "server")]

    def test_native_syslog_opens_existing_rule_case(self):
        self.log.write_bytes(b"".join(syslog(stamp=f"2026-11-06T12:00:0{i}Z") for i in range(3)))
        result = self.monitor("openssh-syslog-rfc3339").poll()
        self.assertEqual((result["records_committed"], result["cases_opened"]), (3, 1))
        case = self.store.cases("tenant", "server")[0]
        self.assertEqual(case["rule"], "auth_failure_burst_v1")
        self.assertEqual(case["evidence_event_ids"], [e["event_id"] for e in self.events()])

    def test_reexported_journal_record_is_not_another_failure(self):
        self.log.write_bytes(journal() * 3)
        result = self.monitor().poll()
        self.assertEqual((result["duplicate_records"], result["cases_opened"]), (2, 0))
        self.assertEqual([e["kind"] for e in self.events()], ["auth.observation", "sensor.duplicate", "sensor.duplicate"])

    def test_duplicate_identity_with_changed_message_is_quality_error(self):
        self.log.write_bytes(journal() + journal(message=MESSAGE.replace("Failed", "Accepted")))
        result = self.monitor().poll()
        self.assertEqual(result["invalid_records"], 1)
        self.assertEqual(self.events()[1]["attributes"]["reason"], "ssh_native_identity_conflict")

    def test_deduplication_survives_rotation_and_restart(self):
        self.log.write_bytes(journal()); monitor = self.monitor(); monitor.poll()
        self.log.rename(self.root / "auth.old"); self.log.write_bytes(journal())
        monitor.rotate("auth.old")
        reopened = AuthLogMonitor(OperationsStore(self.store.root), "native", monitor.digest)
        self.assertEqual(reopened.poll()["duplicate_records"], 1)

    def test_native_id_insert_failure_rolls_back_cursor_and_event(self):
        self.log.write_bytes(journal()); monitor = self.monitor()
        with self.store.transaction() as db:
            db.execute("CREATE TRIGGER native_fail BEFORE INSERT ON native_records BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            monitor.poll()
        self.assertEqual(self.events(), [])
        with self.store.transaction() as db:
            db.execute("DROP TRIGGER native_fail")
        self.assertEqual(monitor.poll()["records_committed"], 1)

    def test_partial_messages_do_not_reset_failure_episode(self):
        self.log.write_bytes(journal("1") + journal("2") + journal("3", MESSAGE.replace("Failed", "Partial")) + journal("4"))
        result = self.monitor().poll()
        self.assertEqual((result["unclassified_records"], result["cases_opened"]), (1, 1))

    def test_wrong_host_cannot_contribute_to_case(self):
        self.log.write_bytes(journal("1") + journal("2", _HOSTNAME="other") + journal("3"))
        result = self.monitor().poll()
        self.assertEqual((result["invalid_records"], result["cases_opened"]), (1, 0))

    def test_case_failure_rolls_back_native_deduplication_rows(self):
        self.log.write_bytes(b"".join(journal(str(i)) for i in range(3))); monitor = self.monitor()
        with self.store.transaction() as db:
            db.execute("CREATE TRIGGER case_fail BEFORE INSERT ON cases BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            monitor.poll()
        with self.store.transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM native_records").fetchone()[0], 0)
            db.execute("DROP TRIGGER case_fail")
        self.assertEqual(monitor.poll()["cases_opened"], 1)

    def test_additive_migration_preserves_legacy_config_and_cursor(self):
        legacy = AuthLogMonitor.register(self.store, "legacy", "tenant", "host", self.root, self.log.name)
        with self.store.transaction() as db:
            before = db.execute("SELECT config,cursor FROM streams WHERE id='legacy'").fetchone()
            db.execute("DROP TABLE native_records")
        reopened = OperationsStore(self.store.root)
        AuthLogMonitor(reopened, "legacy", legacy.digest).poll()
        with reopened.transaction() as db:
            self.assertEqual(db.execute("SELECT config,cursor FROM streams WHERE id='legacy'").fetchone(), before)

    def test_cli_registers_native_format_and_polls_it(self):
        self.log.write_bytes(syslog())
        tool = Path(__file__).resolve().parents[1] / "tools/operations.py"
        command = [sys.executable, "-B", str(tool), "--root", str(self.store.root)]
        registered = subprocess.run(command + ["register-auth", "--source", "cli", "--tenant", "tenant", "--asset", "server", "--log-root", str(self.root), "--name", self.log.name, "--format", "openssh-syslog-rfc3339", "--expected-host", "host-a"], capture_output=True, text=True)
        self.assertEqual(registered.returncode, 0, registered.stdout + registered.stderr)
        digest = json.loads(registered.stdout)["config_digest"]
        polled = subprocess.run(command + ["poll-auth", "--source", "cli", "--config-digest", digest], capture_output=True, text=True)
        self.assertEqual(polled.returncode, 0, polled.stdout + polled.stderr)
        self.assertEqual(json.loads(polled.stdout)["records_committed"], 1)


if __name__ == "__main__":
    unittest.main()
