"""A separate local checkpoint witness. Not an external service or root-resistant store."""

from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import stat

from .audit import GENESIS, key_id
from .audit_pages import AuditPageVerifier, anchored_row
from .audit_verification import checkpoint
from .codec import Rejected, canonical, decode, fields, integer
from .files import create_local
from .receipts import hex_digest

SCHEMA = "nqc-local-witness-v1"
ORIGIN = {"sequence": 0, "head": GENESIS}


def receipt(value):
    fields(value, ("revision", "head", "checkpoint"))
    integer(value["revision"], 1, 2**63 - 1)
    hex_digest(value["head"])
    return {"revision": value["revision"], "head": value["head"], "checkpoint": checkpoint(value["checkpoint"])}


class Witness:
    def __init__(self, root, witness_key, audit_key, policy_digest):
        for key in (witness_key, audit_key):
            if not isinstance(key, bytes) or len(key) != 32:
                raise Rejected("witness_key_size")
        if hmac.compare_digest(witness_key, audit_key):
            raise Rejected("witness_key_must_differ")
        hex_digest(policy_digest)
        self.root = Path(root).absolute()
        self.path = self.root / "witness.sqlite3"
        self.key, self.audit_key = witness_key, audit_key
        self.policy_digest, self.audit_key_id = policy_digest, key_id(audit_key)
        self._check_paths()
        self.head()

    @classmethod
    def create(cls, root, witness_key, audit_key, policy_digest):
        # Validate before creating anything; never adopt or overwrite an existing directory.
        for key in (witness_key, audit_key):
            if not isinstance(key, bytes) or len(key) != 32:
                raise Rejected("witness_key_size")
        if hmac.compare_digest(witness_key, audit_key):
            raise Rejected("witness_key_must_differ")
        hex_digest(policy_digest)
        root = Path(root).absolute()
        root.mkdir(mode=0o700, parents=False, exist_ok=False)
        create_local(root, "witness.sqlite3", b"")
        value = cls.__new__(cls)
        value.root, value.path = root, root / "witness.sqlite3"
        value.key, value.audit_key = witness_key, audit_key
        value.policy_digest, value.audit_key_id = policy_digest, key_id(audit_key)
        with value.connection(write=True) as db:
            db.execute("CREATE TABLE anchors (revision INTEGER PRIMARY KEY, payload TEXT NOT NULL, previous TEXT NOT NULL, mac TEXT NOT NULL)")
            event = value._event(ORIGIN, ORIGIN, 0, 0, GENESIS)
            payload = canonical(event).decode()
            db.execute("INSERT INTO anchors VALUES(?,?,?,?)", (1, payload, GENESIS, value._mac(1, GENESIS, payload)))
        parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        return cls(root, witness_key, audit_key, policy_digest)

    def _check_paths(self):
        try:
            directory, database = self.root.lstat(), self.path.lstat()
        except OSError as exc:
            raise Rejected("witness_unavailable") from exc
        if not stat.S_ISDIR(directory.st_mode) or directory.st_mode & 0o077:
            raise Rejected("witness_directory_permissions")
        if not stat.S_ISREG(database.st_mode) or database.st_mode & 0o077 or database.st_nlink != 1:
            raise Rejected("witness_database_permissions")

    @contextmanager
    def connection(self, write=False):
        self._check_paths()
        # mode=rw cannot silently recreate a witness whose database disappeared.
        db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
        finally:
            db.close()

    def _mac(self, revision, previous, payload):
        return hmac.new(self.key, b"nqc-local-witness-v1\x00" + canonical([revision, previous, payload]), hashlib.sha256).hexdigest()

    def _event(self, start, target, pages, records, transcript):
        return {"schema": SCHEMA, "policy_digest": self.policy_digest, "audit_key_id": self.audit_key_id,
                "start": start, "checkpoint": target, "pages": pages, "records": records,
                "page_chain_sha256": transcript}

    def _verify(self, db):
        revision, previous, current = 0, GENESIS, dict(ORIGIN)
        for number, payload, parent, digest in db.execute("SELECT revision,payload,previous,mac FROM anchors ORDER BY revision"):
            integer(number, 1, 2**63 - 1)
            hex_digest(parent)
            if not isinstance(payload, str) or len(payload) > 4096:
                raise Rejected("witness_payload")
            if number != revision + 1 or parent != previous:
                raise Rejected("witness_sequence")
            hex_digest(digest)
            if not hmac.compare_digest(digest, self._mac(number, parent, payload)):
                raise Rejected("witness_integrity")
            try:
                payload_bytes = payload.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise Rejected("witness_payload") from exc
            event = decode(payload_bytes, max_bytes=4096)
            fields(event, ("schema", "policy_digest", "audit_key_id", "start", "checkpoint", "pages", "records", "page_chain_sha256"))
            start, target = checkpoint(event["start"]), checkpoint(event["checkpoint"])
            integer(event["pages"], 0, 2**63 - 1)
            integer(event["records"], 0, 2**63 - 1)
            hex_digest(event["page_chain_sha256"])
            if (event["schema"] != SCHEMA or event["policy_digest"] != self.policy_digest
                    or event["audit_key_id"] != self.audit_key_id):
                raise Rejected("witness_binding")
            if start != current or event["records"] != target["sequence"] - start["sequence"]:
                raise Rejected("witness_interval")
            if number == 1:
                if event != self._event(ORIGIN, ORIGIN, 0, 0, GENESIS):
                    raise Rejected("witness_genesis")
            elif target["sequence"] <= start["sequence"] or not 1 <= event["pages"] <= event["records"]:
                raise Rejected("witness_not_forward")
            revision, previous, current = number, digest, target
        if revision == 0:
            raise Rejected("witness_empty")
        return {"revision": revision, "head": previous, "checkpoint": current}

    def head(self, expected=None):
        if expected is not None:
            expected = receipt(expected)
        with self.connection() as db:
            actual = self._verify(db)
        if expected is not None and actual != expected:
            raise Rejected("witness_receipt_mismatch")
        return actual

    def advance(self, pages, target, expected):
        """Commit only a complete verified interval, using compare-and-swap on the witness head."""
        expected = receipt(expected)
        self.head(expected)
        target = checkpoint(target)
        start = expected["checkpoint"]
        if target["sequence"] <= start["sequence"]:
            raise Rejected("witness_not_forward")
        verifier = AuditPageVerifier(self.audit_key, self.policy_digest, target, start)
        chain = hashlib.sha256(b"nqc-witness-pages-v1\x00" + canonical([self.policy_digest, self.audit_key_id, start, target])).digest()
        for data in pages:
            verifier.accept(data)
            chain = hashlib.sha256(chain + hashlib.sha256(data).digest()).digest()
        summary = verifier.finish()
        event = self._event(start, target, summary["pages"], summary["record_count"], chain.hex())
        with self.connection(write=True) as db:
            if self._verify(db) != expected:
                raise Rejected("witness_receipt_mismatch")
            number = expected["revision"] + 1
            integer(number, 1, 2**63 - 1)
            payload = canonical(event).decode()
            digest = self._mac(number, expected["head"], payload)
            db.execute("INSERT INTO anchors VALUES(?,?,?,?)", (number, payload, expected["head"], digest))
        return {"revision": number, "head": digest, "checkpoint": target}

    def bind_engine(self, state_root, policy_digest, audit_key):
        state, witness = Path(state_root).resolve(), self.root.resolve()
        if state == witness or state in witness.parents or witness in state.parents:
            raise Rejected("witness_state_overlap")
        if policy_digest != self.policy_digest or key_id(audit_key) != self.audit_key_id:
            raise Rejected("witness_binding")
        self.head()

    def require_history(self, db):
        """Check the anchored prefix inside the caller's already-verified engine transaction."""
        anchored_row(db, self.head()["checkpoint"])
