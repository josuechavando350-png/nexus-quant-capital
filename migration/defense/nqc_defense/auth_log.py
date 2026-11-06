"""Read explicitly registered JSONL auth logs with transactional cursors and evidence references."""
import ipaddress
import os
from pathlib import Path
import stat
import time

from .codec import Rejected, canonical, decode, fields, identifier, integer
from .files import open_parent, relative_parts, sha256
from .operations import SCHEMA

MAX_FILE = 16 * 1024 * 1024
MAX_BATCH = 1024 * 1024
MAX_LINE = 16384


def parse_auth(line):
    value = decode(line, max_bytes=MAX_LINE, max_nodes=32)
    fields(value, ("schema", "time_ns", "outcome", "principal", "remote_address"))
    if value["schema"] != "nqc-auth-log-v1" or value["outcome"] not in ("success", "failure"):
        raise Rejected("auth_record_schema")
    integer(value["time_ns"], 0, 2**63 - 1)
    identifier(value["principal"])
    try:
        if not isinstance(value["remote_address"], str) or "%" in value["remote_address"]:
            raise ValueError()
        value["remote_address"] = str(ipaddress.ip_address(value["remote_address"]))
    except ValueError as exc:
        raise Rejected("auth_address") from exc
    return value


class AuthLogMonitor:
    def __init__(self, store, source_id, config_digest):
        self.store = store
        self.source_id = identifier(source_id)
        self.digest = config_digest
        with self.store.transaction() as db:
            self._load(db)

    @classmethod
    def register(cls, store, source_id, tenant, asset, log_root, name, threshold=5, window_seconds=300):
        for value in (source_id, tenant, asset):
            identifier(value)
        relative_parts(name)
        integer(threshold, 2, 100); integer(window_seconds, 1, 86400)
        config = {"schema": "nqc-auth-source-v1", "source_id": source_id, "tenant": tenant, "asset": asset,
                  "root": str(Path(log_root).absolute()), "name": name,
                  "threshold": threshold, "window_ns": window_seconds * 1000000000}
        _, info = cls._snapshot(config, name)
        cursor = {"device": info.st_dev, "inode": info.st_ino, "generation": 0,
                  "offset": 0, "prefix_sha256": sha256(b""), "last_event_ns": -1}
        with store.transaction() as db:
            if db.execute("SELECT 1 FROM streams WHERE id=?", (source_id,)).fetchone():
                raise Rejected("auth_source_exists")
            if db.execute("SELECT count(*) FROM streams").fetchone()[0] >= 1000:
                raise Rejected("auth_source_capacity")
            db.execute("INSERT INTO streams VALUES(?,?,?)", (source_id, canonical(config), canonical(cursor)))
        return cls(store, source_id, sha256(canonical(config)))

    def _load(self, db):
        row = db.execute("SELECT config,cursor FROM streams WHERE id=?", (self.source_id,)).fetchone()
        if row is None or sha256(row[0]) != self.digest:
            raise Rejected("auth_source_binding")
        return decode(row[0]), decode(row[1])

    @staticmethod
    def _snapshot(config, name):
        parent, leaf = open_parent(config["root"], name)
        fd = None
        try:
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_FILE:
                raise Rejected("auth_file_type_or_size")
            parts, size = [], 0
            while True:
                block = os.read(fd, min(65536, MAX_FILE + 1 - size))
                if not block:
                    break
                size += len(block)
                if size > MAX_FILE:
                    raise Rejected("auth_file_size")
                parts.append(block)
            after = os.fstat(fd)
            named = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if stamp(before) != stamp(after) or stamp(after) != stamp(named) or size != after.st_size:
                raise Rejected("auth_file_changed_during_read")
            return b"".join(parts), after
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent)

    @staticmethod
    def _prefix(data, info, cursor):
        if (info.st_dev, info.st_ino) != (cursor["device"], cursor["inode"]):
            raise Rejected("auth_rotation_required")
        if len(data) < cursor["offset"]:
            raise Rejected("auth_log_truncated")
        if sha256(data[:cursor["offset"]]) != cursor["prefix_sha256"]:
            raise Rejected("auth_consumed_prefix_changed")

    def poll(self, previous_name=None, max_records=500):
        integer(max_records, 1, 1000)
        with self.store.transaction() as db:
            config, cursor = self._load(db)
            name = config["name"] if previous_name is None else previous_name
            if previous_name is not None:
                relative_parts(previous_name)
            data, info = self._snapshot(config, name)
            self._prefix(data, info, cursor)
            offset, observed = cursor["offset"], time.time_ns()
            consumed = invalid = late = detections = 0
            first = offset
            while consumed < max_records and offset < len(data):
                end = data.find(b"\n", offset, min(len(data), offset + MAX_LINE + 1))
                if end < 0:
                    if len(data) - offset >= MAX_LINE:
                        raise Rejected("auth_line_too_long")
                    break
                end += 1
                if end - offset > MAX_LINE:
                    raise Rejected("auth_line_too_long")
                if end - first > MAX_BATCH:
                    break
                raw = data[offset:end]
                evidence = {"config_digest": self.digest, "generation": cursor["generation"],
                            "device": cursor["device"], "inode": cursor["inode"], "start": offset,
                            "end": end, "raw_sha256": sha256(raw)}
                event_id = sha256(canonical([config["tenant"], config["asset"], self.source_id, evidence]))
                try:
                    auth = parse_auth(raw)
                    is_late = auth["time_ns"] < cursor["last_event_ns"]
                    attributes = {"outcome": auth["outcome"], "principal": auth["principal"],
                                  "remote_address": auth["remote_address"], "rule_evaluated": not is_late,
                                  "rule_exclusion": "out_of_order" if is_late else None}
                    kind, occurred = "auth.observation", auth["time_ns"]
                    late += int(is_late)
                except Rejected as exc:
                    attributes = {"reason": str(exc), "rule_evaluated": False}
                    kind, occurred, auth = "sensor.input_rejected", None, None
                    invalid += 1
                event = {"schema": SCHEMA, "event_id": event_id, "tenant": config["tenant"],
                         "asset": config["asset"], "source_id": self.source_id, "kind": kind,
                         "observed_ns": observed, "occurred_ns": occurred, "evidence": evidence,
                         "attributes": attributes}
                if not self.store.append(db, event):
                    raise Rejected("auth_cursor_event_conflict")
                if auth is not None and attributes["rule_evaluated"]:
                    detections += self._detect(db, config, event)
                    cursor["last_event_ns"] = occurred
                offset, consumed = end, consumed + 1
            cursor.update(offset=offset, prefix_sha256=sha256(data[:offset]))
            db.execute("UPDATE streams SET cursor=? WHERE id=?", (canonical(cursor), self.source_id))
            return {"records_committed": consumed, "invalid_records": invalid, "late_records": late,
                    "cases_opened": detections, "cursor": cursor,
                    "unconsumed_bytes": len(data) - offset, "at_observed_eof": len(data) == offset,
                    "automatic_response": False}

    def _detect(self, db, config, event):
        attributes, now = event["attributes"], event["occurred_ns"]
        group = sha256(canonical([self.digest, attributes["principal"], attributes["remote_address"]]))
        row = db.execute("SELECT body FROM episodes WHERE id=?", (group,)).fetchone()
        episode = decode(row[0]) if row else {"failures": [], "case_id": None, "last_failure_ns": None}
        if attributes["outcome"] == "success":
            # A success ends this detection episode, but does not resolve an investigation.
            db.execute("DELETE FROM episodes WHERE id=?", (group,))
            return 0
        if episode["last_failure_ns"] is not None and now - episode["last_failure_ns"] > config["window_ns"]:
            episode = {"failures": [], "case_id": None, "last_failure_ns": None}
        episode["failures"] = [pair for pair in episode["failures"] if now - pair[0] <= config["window_ns"]]
        episode["failures"].append([now, event["event_id"]])
        episode["failures"] = episode["failures"][-config["threshold"]:]
        episode["last_failure_ns"] = now
        opened = 0
        if len(episode["failures"]) >= config["threshold"] and episode["case_id"] is None:
            case_id = sha256(canonical(["auth_failure_burst_v1", self.digest, episode["failures"]]))
            case = {"case_id": case_id, "tenant": config["tenant"], "asset": config["asset"],
                    "source_id": self.source_id, "category": "authentication", "status": "open",
                    "rule": "auth_failure_burst_v1", "config_digest": self.digest,
                    "evidence_event_ids": [pair[1] for pair in episode["failures"]],
                    "threshold": config["threshold"], "window_ns": config["window_ns"],
                    "principal": attributes["principal"], "remote_address": attributes["remote_address"],
                    "automatic_response": False,
                    "interpretation": "repeated failures; not proof of intrusion or actor identity"}
            self.store.put_case(db, case)
            episode["case_id"], opened = case_id, 1
        db.execute("INSERT INTO episodes VALUES(?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (group, canonical(episode)))
        return opened

    def rotate(self, previous_name):
        """Explicit handoff after the operator has stopped writes to the previous file."""
        relative_parts(previous_name)
        with self.store.transaction() as db:
            config, cursor = self._load(db)
            old, old_info = self._snapshot(config, previous_name)
            self._prefix(old, old_info, cursor)
            if len(old) != cursor["offset"]:
                raise Rejected("auth_previous_not_drained")
            _, new_info = self._snapshot(config, config["name"])
            if (new_info.st_dev, new_info.st_ino) == (cursor["device"], cursor["inode"]):
                raise Rejected("auth_rotation_identity_unchanged")
            evidence = {"previous_cursor": cursor, "new_device": new_info.st_dev, "new_inode": new_info.st_ino,
                        "config_digest": self.digest}
            event = {"schema": SCHEMA, "event_id": sha256(canonical([self.digest, "rotation", evidence])),
                     "tenant": config["tenant"], "asset": config["asset"], "source_id": self.source_id,
                     "kind": "sensor.rotation", "observed_ns": time.time_ns(), "occurred_ns": None,
                     "evidence": evidence, "attributes": {"operator_declared_previous_sealed": True}}
            self.store.append(db, event)
            next_cursor = {"device": new_info.st_dev, "inode": new_info.st_ino,
                           "generation": cursor["generation"] + 1, "offset": 0,
                           "prefix_sha256": sha256(b""), "last_event_ns": cursor["last_event_ns"]}
            db.execute("UPDATE streams SET cursor=? WHERE id=?", (canonical(next_cursor), self.source_id))
            return {"rotated": True, "cursor": next_cursor}
