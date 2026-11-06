"""SQLite persistence. Each decision, token consumption and audit entry is atomic."""

from contextlib import contextmanager
import os
import sqlite3
import stat

from .codec import Rejected
from .files import private_directory


class State:
    def __init__(self, root, policy_digest):
        self.root = private_directory(root)
        self.path = self.root / "state.sqlite3"
        if self.path.is_symlink():
            raise Rejected("database_symlink")
        if not self.path.exists():
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        mode = self.path.stat().st_mode
        if not stat.S_ISREG(mode):
            raise Rejected("database_not_regular")
        if mode & 0o077:
            raise Rejected("database_permissions")
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tokens (
                    digest TEXT PRIMARY KEY, subject TEXT NOT NULL, asset TEXT NOT NULL,
                    issued INTEGER NOT NULL, expires INTEGER NOT NULL, consumed INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS buckets (
                    subject TEXT PRIMARY KEY, start INTEGER NOT NULL, count INTEGER NOT NULL, last INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS quarantine (asset TEXT PRIMARY KEY, reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (
                    subject TEXT NOT NULL, request_id TEXT NOT NULL, asset TEXT NOT NULL,
                    PRIMARY KEY(subject, request_id));
                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY, payload TEXT NOT NULL, previous TEXT NOT NULL, mac TEXT NOT NULL);
            """)
        with self.transaction() as db:
            db.execute("INSERT OR IGNORE INTO meta VALUES ('policy', ?)", (policy_digest,))
            if db.execute("SELECT value FROM meta WHERE key='policy'").fetchone()[0] != policy_digest:
                raise Rejected("policy_binding_changed")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.rollback()
                raise
            else:
                db.commit()
