"""Bounded local event/case store. Logical scope filters are not tenant authentication."""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import stat
import time

from .codec import Rejected, canonical, decode, identifier, integer
from .files import sha256

SCHEMA = "nqc-defensive-event-v1"
MAX_EVENTS = 100000
MAX_CASES = 10000


class OperationsStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.path = self.root / "operations.sqlite3"
        self._check_files()
        with self.transaction() as db:
            if db.execute("SELECT value FROM meta WHERE key='schema'").fetchone() != ("nqc-operations-v1",):
                raise Rejected("operations_schema")

    @classmethod
    def create(cls, root):
        root = Path(root).absolute()
        root.mkdir(mode=0o700, exist_ok=False)
        path = root / "operations.sqlite3"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        db = sqlite3.connect(path)
        try:
            db.executescript("""
                PRAGMA synchronous=FULL;
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta VALUES ('schema','nqc-operations-v1');
                CREATE TABLE streams (id TEXT PRIMARY KEY, config BLOB NOT NULL, cursor BLOB NOT NULL);
                CREATE TABLE events (sequence INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL,
                    tenant TEXT NOT NULL, asset TEXT NOT NULL, source TEXT NOT NULL,
                    kind TEXT NOT NULL, body BLOB NOT NULL, digest TEXT NOT NULL);
                CREATE INDEX event_scope ON events(tenant,asset,sequence);
                CREATE TABLE cases (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, asset TEXT NOT NULL,
                    category TEXT NOT NULL, status TEXT NOT NULL, body BLOB NOT NULL);
                CREATE INDEX case_scope ON cases(tenant,asset,id);
                CREATE TABLE episodes (id TEXT PRIMARY KEY, body BLOB NOT NULL);
            """)
            db.commit()
        finally:
            db.close()
        return cls(root)

    def _check_files(self):
        root, db = self.root.lstat(), self.path.lstat()
        if not stat.S_ISDIR(root.st_mode) or root.st_mode & 0o077:
            raise Rejected("operations_directory_permissions")
        if not stat.S_ISREG(db.st_mode) or db.st_mode & 0o077 or db.st_nlink != 1:
            raise Rejected("operations_database_permissions")

    @contextmanager
    def transaction(self):
        self._check_files()
        db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5, isolation_level=None)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def append(db, event):
        for key in ("tenant", "asset", "source_id"):
            identifier(event[key])
        if event["schema"] != SCHEMA:
            raise Rejected("operations_event_schema")
        body = canonical(event)
        if len(body) > 32768:
            raise Rejected("operations_event_size")
        previous = db.execute("SELECT body FROM events WHERE id=?", (event["event_id"],)).fetchone()
        if previous:
            # Observation time is intentionally excluded from the stable evidence identity.
            old = decode(previous[0]); new = dict(event)
            old.pop("observed_ns"); new.pop("observed_ns")
            if old != new:
                raise Rejected("operations_identity_collision")
            return False
        if db.execute("SELECT count(*) FROM events").fetchone()[0] >= MAX_EVENTS:
            raise Rejected("operations_event_capacity")
        db.execute("INSERT INTO events(id,tenant,asset,source,kind,body,digest) VALUES(?,?,?,?,?,?,?)",
                   (event["event_id"], event["tenant"], event["asset"], event["source_id"], event["kind"], body, sha256(body)))
        return True

    @staticmethod
    def put_case(db, case):
        old = db.execute("SELECT tenant,asset FROM cases WHERE id=?", (case["case_id"],)).fetchone()
        if old and old != (case["tenant"], case["asset"]):
            raise Rejected("operations_case_scope")
        if not old and db.execute("SELECT count(*) FROM cases").fetchone()[0] >= MAX_CASES:
            raise Rejected("operations_case_capacity")
        db.execute("INSERT INTO cases VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,body=excluded.body",
                   (case["case_id"], case["tenant"], case["asset"], case["category"], case["status"], canonical(case)))

    def events(self, tenant, asset, after=0, limit=100):
        identifier(tenant)
        identifier(asset)
        integer(after, 0, 2**63 - 1)
        integer(limit, 1, 200)
        with self.transaction() as db:
            rows = db.execute("SELECT sequence,body,digest FROM events WHERE tenant=? AND asset=? AND sequence>? ORDER BY sequence LIMIT ?",
                              (tenant, asset, after, limit)).fetchall()
            result = []
            for sequence, body, digest in rows:
                if sha256(body) != digest:
                    raise Rejected("operations_event_digest")
                result.append({"sequence": sequence, "event": decode(body)})
            return result

    def cases(self, tenant, asset, after="", limit=100):
        identifier(tenant)
        identifier(asset)
        integer(limit, 1, 200)
        if not isinstance(after, str) or len(after) > 64:
            raise Rejected("operations_case_cursor")
        with self.transaction() as db:
            return [decode(row[0]) for row in db.execute(
                "SELECT body FROM cases WHERE tenant=? AND asset=? AND id>? ORDER BY id LIMIT ?", (tenant, asset, after, limit))]

    def capture_managed(self, managed, tenant, asset):
        """Verified source status projected into the shared view; no inferred causal correlation."""
        identifier(tenant)
        identifier(asset)
        state = managed.status()
        incident = state["incident"]
        if incident is None:
            return {"imported": False, "reason": "no_incident"}
        source = "integrity_" + managed.digest[:32]
        case_id = sha256(canonical([tenant, asset, managed.digest, incident["case_id"]]))
        event_id = sha256(canonical([case_id, incident]))
        event = {"schema": SCHEMA, "event_id": event_id, "tenant": tenant, "asset": asset,
                 "source_id": source, "kind": "integrity.incident", "observed_ns": time.time_ns(),
                 "occurred_ns": None, "evidence": {"receipt_sha256": incident["receipt_sha256"],
                 "manifest_digest": managed.digest, "opened_sequence": incident["opened_sequence"],
                 "closed_sequence": incident["closed_sequence"]}, "attributes": incident}
        status = "open" if state["contained"] else "source_reported_resolved"
        case = {"case_id": case_id, "tenant": tenant, "asset": asset, "category": "managed_integrity",
                "status": status, "source_id": source, "rule": "managed_integrity_v1",
                "source_sequence": incident["closed_sequence"] or incident["opened_sequence"],
                "evidence_event_ids": [event_id], "automatic_response": False,
                "interpretation": "source status; not proof of host recovery or cross-source causality"}
        with self.transaction() as db:
            added = self.append(db, event)
            if added:
                old = db.execute("SELECT body FROM cases WHERE id=?", (case_id,)).fetchone()
                if not old or decode(old[0])["source_sequence"] <= case["source_sequence"]:
                    self.put_case(db, case)
        return {"imported": added, "event_id": event_id, "case_id": case_id}
