"""Bounded OpenSSH result parsers; exported host/process fields are claims, not attestation."""
import calendar
from datetime import datetime
import ipaddress
import re

from .codec import Rejected, canonical, decode, integer
from .files import sha256

FORMATS = ("nqc-jsonl", "openssh-syslog-rfc3339", "openssh-journal-json")
HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,252}")
TIMESTAMP = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})")
PREFIX = re.compile(r"(\S+) (\S+) (sshd(?:-session)?)\[([0-9]{1,10})\]: (.+)")
RESULT = re.compile(r"(Accepted|Failed|Partial|Postponed) ([a-zA-Z0-9/-]{1,80}) for (invalid user )?([A-Za-z0-9_.@$-]{1,99}) from ([0-9a-fA-F:.]{1,45}) port ([0-9]{1,5}) ssh2(?:: ([\x20-\x7e]{1,2048}))?(?: \[preauth\])?")
METHODS = {"password", "publickey", "keyboard-interactive", "keyboard-interactive/pam", "gssapi-with-mic", "hostbased", "none"}


class Unclassified(Rejected):
    """An observed message is not a supported final authentication result."""


def source_options(format_name, expected_host):
    if format_name not in FORMATS:
        raise Rejected("auth_source_format")
    if format_name == "nqc-jsonl":
        if expected_host is not None:
            raise Rejected("auth_host_requires_native_format")
        return {}
    if not isinstance(expected_host, str) or not HOST.fullmatch(expected_host):
        raise Rejected("ssh_expected_host")
    return {"format": format_name, "expected_host": expected_host}


def timestamp_ns(text):
    match = TIMESTAMP.fullmatch(text)
    if match is None or match[8] == "-00:00":
        raise Rejected("ssh_timestamp_requires_known_offset")
    try:
        year, month, day, hour, minute, second = map(int, match.groups()[:6])
        utc = calendar.timegm(datetime(year, month, day, hour, minute, second).timetuple())
        offset = match[8]
        if offset != "Z":
            hours, minutes = int(offset[1:3]), int(offset[4:])
            if hours > 23 or minutes > 59:
                raise ValueError()
            utc -= (1 if offset[0] == "+" else -1) * (hours * 3600 + minutes * 60)
        value = utc * 1000000000 + int((match[7] or "").ljust(9, "0"))
        return integer(value, 0, 2**63 - 1)
    except (ValueError, OverflowError) as exc:
        raise Rejected("ssh_timestamp_range") from exc


def _message(message):
    if not isinstance(message, str) or not 1 <= len(message) <= 8192 or any(ord(c) < 32 or ord(c) > 126 for c in message):
        raise Rejected("ssh_message_encoding")
    match = RESULT.fullmatch(message)
    if match is None:
        raise Unclassified("ssh_unclassified_message")
    result, method, invalid, principal, remote, port, extra = match.groups()
    if result in ("Partial", "Postponed"):
        raise Unclassified("ssh_nonfinal_authentication")
    if method not in METHODS:
        raise Unclassified("ssh_unsupported_auth_method")
    if result == "Accepted" and invalid:
        raise Rejected("ssh_inconsistent_result")
    try:
        address = str(ipaddress.ip_address(remote))
    except ValueError as exc:
        raise Rejected("ssh_remote_address") from exc
    integer(int(port), 1, 65535)
    return {"outcome": "success" if result == "Accepted" else "failure", "principal": principal,
            "remote_address": address, "method": method, "invalid_user": bool(invalid),
            "remote_port": int(port), "message_sha256": sha256(message.encode("ascii"))}


def parse_openssh(raw, config):
    if not isinstance(raw, bytes) or len(raw) > 16384 or not raw.endswith(b"\n"):
        raise Rejected("ssh_record_size_or_framing")
    format_name = config["format"]
    if format_name == "openssh-syslog-rfc3339":
        try:
            text = raw[:-1].decode("ascii")
        except UnicodeError as exc:
            raise Rejected("ssh_record_encoding") from exc
        prefix = PREFIX.fullmatch(text)
        if prefix is None:
            raise Rejected("ssh_syslog_prefix")
        stamp, host, process, pid, message = prefix.groups()
        occurred = timestamp_ns(stamp)
        native_id = None
        clock_resolution_ns = 10 ** (9 - len(TIMESTAMP.fullmatch(stamp)[7] or ""))
        metadata = {"time_source": "syslog_declared_rfc3339", "declared_host": host,
                    "process_name": process, "pid": integer(int(pid), 1, 2**31 - 1)}
    elif format_name == "openssh-journal-json":
        value = decode(raw, max_bytes=16384, max_nodes=1024)
        required = ("MESSAGE", "__REALTIME_TIMESTAMP", "__CURSOR", "_BOOT_ID", "_HOSTNAME", "_COMM", "_PID")
        if not isinstance(value, dict) or any(not isinstance(value.get(k), str) for k in required):
            raise Rejected("ssh_journal_fields")
        stamp, host, process, pid, message = (value[k] for k in ("__REALTIME_TIMESTAMP", "_HOSTNAME", "_COMM", "_PID", "MESSAGE"))
        if not re.fullmatch(r"[0-9]{1,16}", stamp) or not re.fullmatch(r"[0-9]{1,10}", pid):
            raise Rejected("ssh_journal_numeric_field")
        if process not in ("sshd", "sshd-session"):
            raise Rejected("ssh_journal_process")
        if not re.fullmatch(r"[0-9a-f]{32}", value["_BOOT_ID"]) or not re.fullmatch(r"[\x21-\x7e]{1,2048}", value["__CURSOR"]):
            raise Rejected("ssh_journal_identity")
        occurred = integer(int(stamp) * 1000, 0, 2**63 - 1)
        native_id = sha256(canonical([value["_BOOT_ID"], value["__CURSOR"]]))
        clock_resolution_ns = 1000
        metadata = {"time_source": "journal_export_realtime", "declared_host": host, "process_name": process,
                    "pid": integer(int(pid), 1, 2**31 - 1), "boot_id": value["_BOOT_ID"],
                    "cursor_sha256": sha256(value["__CURSOR"].encode("ascii"))}
    else:
        raise Rejected("auth_source_format")
    if host != config["expected_host"]:
        raise Rejected("ssh_host_mismatch")
    auth = _message(message)
    metadata.update(format=format_name, time_resolution_ns=clock_resolution_ns, origin_authenticated=False)
    auth.update(time_ns=occurred, native_record_id=native_id, origin=metadata)
    return auth
