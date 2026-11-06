"""Separate native-format conformance corpus; fixtures, not captures from a live SSH service."""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.codec import canonical
from nqc_defense.operations import OperationsStore


def syslog(message, second=0, host="node-a"):
    return f"2026-11-06T12:00:{second:02}Z {host} sshd[514]: {message}\n".encode()


def journal(message, index, **overrides):
    value = {"_HOSTNAME": "node-a", "_COMM": "sshd", "_PID": "514", "_BOOT_ID": "a" * 32,
             "__REALTIME_TIMESTAMP": str(1793966400000000 + index * 1000000),
             "__CURSOR": f"s=fixture;i={index}", "MESSAGE": message}
    value.update(overrides)
    return canonical(value) + b"\n"


def run():
    failed = "Failed password for operator from 192.0.2.50 port 55220 ssh2"
    accepted = failed.replace("Failed", "Accepted")
    partial = failed.replace("Failed", "Partial")
    scenarios = [
        ("syslog_failure_burst", "openssh-syslog-rfc3339", [syslog(failed, i) for i in range(3)], (3, 0, 0, 0, 1)),
        ("journal_failure_burst", "openssh-journal-json", [journal(failed, i) for i in range(3)], (3, 0, 0, 0, 1)),
        ("syslog_successes", "openssh-syslog-rfc3339", [syslog(accepted, i) for i in range(3)], (3, 0, 0, 0, 0)),
        ("nonfinal_results", "openssh-syslog-rfc3339", [syslog(partial, i) for i in range(3)], (0, 0, 3, 0, 0)),
        ("outside_host_scope", "openssh-syslog-rfc3339", [syslog(failed, i, "other") for i in range(3)], (0, 3, 0, 0, 0)),
        ("reexported_journal", "openssh-journal-json", [journal(failed, 1)] * 3, (1, 0, 0, 2, 0)),
        ("conflicting_journal_identity", "openssh-journal-json", [journal(failed, 1), journal(accepted, 1)], (1, 1, 0, 0, 0)),
        ("invalid_user_double_message", "openssh-syslog-rfc3339", [syslog("Invalid user operator from 192.0.2.50 port 55220"), syslog(failed.replace("for operator", "for invalid user operator"))], (1, 0, 1, 0, 0)),
        ("ambiguous_yearless_time", "openssh-syslog-rfc3339", [b"Nov  6 12:00:00 node-a sshd[514]: " + failed.encode() + b"\n"], (0, 1, 0, 0, 0)),
        ("repeated_benign_errors_still_alert", "openssh-syslog-rfc3339", [syslog(failed, i) for i in range(5)], (5, 0, 0, 0, 1)),
        ("distributed_failures_still_missed", "openssh-syslog-rfc3339", [syslog(failed.replace("192.0.2.50", f"192.0.2.{i+1}"), i) for i in range(4)], (4, 0, 0, 0, 0)),
        ("valid_ipv6", "openssh-syslog-rfc3339", [syslog(failed.replace("192.0.2.50", "2001:db8::42"), i) for i in range(3)], (3, 0, 0, 0, 1)),
    ]
    outputs = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for index, (name, format_name, lines, expected) in enumerate(scenarios):
            log = root / f"source-{index}.log"; log.write_bytes(b"".join(lines))
            store = OperationsStore.create(root / f"state-{index}")
            monitor = AuthLogMonitor.register(store, "openssh", "evaluation", "server", root, log.name,
                                              3, 60, format_name=format_name, expected_host="node-a")
            result = monitor.poll()
            events = store.events("evaluation", "server")
            observations = sum(row["event"]["kind"] == "auth.observation" for row in events)
            actual = (observations, result["invalid_records"], result["unclassified_records"],
                      result["duplicate_records"], result["cases_opened"])
            if actual != expected:
                raise AssertionError(f"Native format scenario failed: {name}")
            cases = store.cases("evaluation", "server")
            identities = {r["event"]["event_id"] for r in events}
            for case in cases:
                if not set(case["evidence_event_ids"]) <= identities:
                    raise AssertionError("case references missing evidence")
            reopened = AuthLogMonitor(OperationsStore(store.root), "openssh", monitor.digest)
            if reopened.poll()["records_committed"] != 0:
                raise AssertionError("reopen duplicated records")
            outputs.append({"scenario": name, "format": format_name, "records": len(lines),
                            "observations": observations, "invalid": actual[1], "unclassified": actual[2],
                            "duplicates": actual[3], "cases": actual[4], "expected_result_matched": True})
    return {"verified": True, "corpus": "12 authored native-format fixtures distinct from v0.11 synthetic scenarios",
            "independent_evaluation": False, "live_sshd_capture": False, "production_validation": False,
            "case_evidence_references_checked": True, "reopen_without_duplicates_checked": True,
            "scenarios": outputs, "source_claims_authenticated": False,
            "known_detection_limits_unchanged": ["benign repeated errors can alert", "distributed addresses remain outside this rule"],
            "sources": ["https://github.com/openssh/openssh-portable/blob/master/auth.c",
                        "https://www.freedesktop.org/software/systemd/man/latest/systemd.journal-fields.html",
                        "https://www.rfc-editor.org/rfc/rfc3339"]}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
