import concurrent.futures
import io
import multiprocessing
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading
import unittest

from test_defense import Fixture
from test_audit_pages import rewrite
from nqc_defense.audit import mac
from nqc_defense.audit_pages import verify_page
from nqc_defense.codec import Rejected, canonical, decode
from nqc_defense.consumer import ArtifactReader
from nqc_defense.engine import Engine
from nqc_defense.files import create_local
from nqc_defense.web import Application
from nqc_defense.witness import ORIGIN, Witness


def advance_in_process(args):
    root, witness_key, audit_key, digest, pages, target, expected = args
    try:
        return Witness(root, witness_key, audit_key, digest).advance(pages, target, expected)["revision"]
    except Rejected:
        return None


class WitnessTests(Fixture):
    def setUp(self):
        super().setUp()
        self.witness_key = secrets.token_bytes(32)
        self.witness_root = self.root / "separate-witness"
        self.witness = Witness.create(self.witness_root, self.witness_key, self.key, self.digest)

    def guarded(self):
        return Engine(self.assets, self.store.root, self.root / "state", self.digest, self.key,
                      clock=lambda: self.time, witness=self.witness)

    def consume(self, request_id="consume"):
        token = self.token()
        return ArtifactReader(self.engine).read_json(canonical({"request_id": request_id, "asset": "nqc-evidence"}), token)

    def pages(self, target, start=ORIGIN):
        while True:
            data = self.engine.export_page(start, target, limit=1)
            checked = verify_page(data, self.key, self.digest, start, target)
            yield data
            if checked["complete"]:
                break
            start = checked["checkpoint"]

    def anchor(self):
        expected, target = self.witness.head(), self.engine.checkpoint()
        return self.witness.advance(self.pages(target, expected["checkpoint"]), target, expected)

    def test_new_witness_is_private_pinned_genesis_and_reopens(self):
        self.assertEqual(self.witness.head()["checkpoint"], ORIGIN)
        self.assertEqual(self.witness.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.witness.root.stat().st_mode & 0o777, 0o700)
        reopened = Witness(self.witness_root, self.witness_key, self.key, self.digest)
        self.assertEqual(reopened.head(), self.witness.head())

    def test_initialization_never_overwrites_existing_store(self):
        before = self.witness.path.read_bytes()
        with self.assertRaises(FileExistsError):
            Witness.create(self.witness_root, self.witness_key, self.key, self.digest)
        self.assertEqual(before, self.witness.path.read_bytes())

    def test_witness_requires_separate_key_and_pinned_bindings(self):
        for witness_key, audit_key, digest in ((self.key, self.key, self.digest),
                (secrets.token_bytes(32), self.key, self.digest),
                (self.witness_key, secrets.token_bytes(32), self.digest),
                (self.witness_key, self.key, "f" * 64)):
            with self.subTest(digest=digest), self.assertRaises(Rejected):
                Witness(self.witness_root, witness_key, audit_key, digest)

    def test_verified_pages_advance_once_and_bind_page_transcript(self):
        self.consume()
        anchored = self.anchor()
        self.assertEqual(anchored["revision"], 2)
        self.assertEqual(anchored["checkpoint"], self.engine.checkpoint())
        with self.witness.connection() as db:
            payload = decode(db.execute("SELECT payload FROM anchors WHERE revision=2").fetchone()[0].encode())
        self.assertEqual(payload["records"], 3)
        self.assertEqual(payload["pages"], 3)
        self.assertNotEqual(payload["page_chain_sha256"], "0" * 64)
        self.assertEqual(self.guarded().checkpoint(), anchored["checkpoint"])

    def test_incremental_advance_reuses_verified_previous_checkpoint(self):
        self.consume()
        first = self.anchor()
        self.consume("second")
        second = self.anchor()
        self.assertEqual(second["revision"], 3)
        self.assertEqual(first["checkpoint"]["sequence"], 3)
        self.assertEqual(second["checkpoint"]["sequence"], 6)

    def test_incomplete_pages_leave_witness_unchanged(self):
        self.consume()
        before, target = self.witness.head(), self.engine.checkpoint()
        with self.assertRaisesRegex(Rejected, "audit_pages_incomplete"):
            self.witness.advance(list(self.pages(target))[:-1], target, before)
        self.assertEqual(self.witness.head(), before)

    def test_altered_page_cannot_advance_witness(self):
        self.consume()
        before, target = self.witness.head(), self.engine.checkpoint()
        pages = list(self.pages(target))
        pages[0] = rewrite(pages[0], lambda page: page["records"][0].update(payload="{}"))
        with self.assertRaisesRegex(Rejected, "audit_integrity"):
            self.witness.advance(pages, target, before)
        self.assertEqual(self.witness.head(), before)

    def test_page_input_failure_never_advances(self):
        self.consume()
        before, target = self.witness.head(), self.engine.checkpoint()
        def broken_input():
            yield next(self.pages(target))
            raise OSError("controlled local read failure")
        with self.assertRaises(OSError):
            self.witness.advance(broken_input(), target, before)
        self.assertEqual(self.witness.head(), before)

    def test_stale_compare_and_swap_receipt_rejected(self):
        self.consume()
        before, target = self.witness.head(), self.engine.checkpoint()
        pages = list(self.pages(target))
        self.witness.advance(pages, target, before)
        with self.assertRaisesRegex(Rejected, "witness_receipt_mismatch"):
            self.witness.advance(pages, target, before)

    def test_same_or_older_checkpoint_cannot_replace_latest(self):
        self.consume()
        current = self.anchor()
        for target in (current["checkpoint"], ORIGIN):
            with self.assertRaisesRegex(Rejected, "witness_not_forward"):
                self.witness.advance([], target, current)

    def test_concurrent_verified_updates_have_one_winner(self):
        self.consume()
        before, target = self.witness.head(), self.engine.checkpoint()
        pages = list(self.pages(target))
        barrier = threading.Barrier(2)
        def worker():
            def interleaved():
                yield from pages
                barrier.wait(timeout=5)
            try:
                return self.witness.advance(interleaved(), target, before)
            except Rejected:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sum(x is not None for x in results), 1)
        self.assertEqual(self.witness.head()["revision"], 2)

    def test_separate_processes_cannot_overwrite_an_advanced_witness(self):
        self.consume()
        before, target = self.witness.head(), self.engine.checkpoint()
        args = (str(self.witness_root), self.witness_key, self.key, self.digest, list(self.pages(target)), target, before)
        with concurrent.futures.ProcessPoolExecutor(max_workers=3, mp_context=multiprocessing.get_context("spawn")) as pool:
            results = list(pool.map(advance_in_process, [args] * 3))
        self.assertEqual(results.count(2), 1)
        self.assertEqual(self.witness.head()["revision"], 2)

    def test_insert_failure_rolls_back_witness(self):
        self.consume()
        before, target = self.witness.head(), self.engine.checkpoint()
        with self.witness.connection(write=True) as db:
            db.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON anchors BEGIN SELECT RAISE(ABORT,'failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.witness.advance(self.pages(target), target, before)
        self.assertEqual(self.witness.head(), before)

    def test_commit_failure_cannot_acknowledge_advancement(self):
        self.consume()
        before, target = self.witness.head(), self.engine.checkpoint()
        with self.witness.connection(write=True) as db:
            db.execute("CREATE TABLE parent_fault(id INTEGER PRIMARY KEY)")
            db.execute("CREATE TABLE child_fault(id INTEGER REFERENCES parent_fault(id) DEFERRABLE INITIALLY DEFERRED)")
            db.execute("CREATE TRIGGER fail_commit AFTER INSERT ON anchors BEGIN INSERT INTO child_fault VALUES(999); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.witness.advance(self.pages(target), target, before)
        self.assertEqual(self.witness.head(), before)
        with self.witness.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM child_fault").fetchone()[0], 0)

    def test_guarded_engine_refuses_truncated_history_on_reopen(self):
        self.consume()
        self.anchor()
        with self.engine.state.transaction() as db:
            db.execute("DELETE FROM audit WHERE seq=3")
        self.assertEqual(self.open().checkpoint()["sequence"], 2)
        with self.assertRaisesRegex(Rejected, "audit_anchor_unavailable"):
            self.guarded()

    def test_existing_engine_rechecks_witness_before_each_operation(self):
        guarded = self.guarded()
        self.consume()
        self.anchor()
        token = self.token()
        with self.engine.state.transaction() as db:
            db.execute("DELETE FROM audit WHERE seq>=3")
        raw = canonical({"request_id": "after-rollback", "asset": "nqc-evidence"})
        operations = (lambda: guarded.issue("operator", "nqc-evidence"),
                      lambda: guarded.admit_bytes(raw, token), guarded.checkpoint, guarded.export,
                      lambda: guarded.export_page(ORIGIN, ORIGIN), lambda: guarded.release("nqc-evidence"),
                      lambda: guarded.receipt("f" * 64))
        for operation in operations:
            with self.assertRaisesRegex(Rejected, "audit_anchor_unavailable"):
                operation()
        with self.engine.state.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM tokens WHERE consumed=0").fetchone()[0], 1)

    def test_same_height_rewritten_chain_fails_anchored_hash(self):
        self.consume()
        self.anchor()
        with self.engine.state.transaction() as db:
            row = db.execute("SELECT seq,payload,previous FROM audit WHERE seq=3").fetchone()
            payload = canonical({"kind": "controlled-local-rewrite"}).decode()
            db.execute("UPDATE audit SET payload=?,mac=? WHERE seq=3", (payload, mac(self.key, row[0], row[2], payload)))
        self.assertEqual(self.open().checkpoint()["sequence"], 3)
        with self.assertRaisesRegex(Rejected, "audit_anchor_unavailable"):
            self.guarded()

    def test_missing_witness_fails_closed_without_recreating_database(self):
        guarded = self.guarded()
        self.witness.path.unlink()
        with self.assertRaisesRegex(Rejected, "witness_unavailable"):
            guarded.checkpoint()
        self.assertFalse(self.witness.path.exists())

    def test_witness_content_corruption_rejected(self):
        with self.witness.connection(write=True) as db:
            db.execute("UPDATE anchors SET payload='{}' WHERE revision=1")
        with self.assertRaisesRegex(Rejected, "witness_integrity"):
            self.witness.head()

    def test_witness_tail_rollback_requires_separately_retained_receipt(self):
        self.consume()
        anchored = self.anchor()
        with self.witness.connection(write=True) as db:
            db.execute("DELETE FROM anchors WHERE revision=2")
        # Honest limit: the witness alone cannot detect its own valid-prefix rollback.
        self.assertEqual(self.witness.head()["checkpoint"], ORIGIN)
        with self.assertRaisesRegex(Rejected, "witness_receipt_mismatch"):
            self.witness.head(anchored)

    def test_empty_witness_is_not_silently_reset(self):
        with self.witness.connection(write=True) as db:
            db.execute("DELETE FROM anchors")
        with self.assertRaisesRegex(Rejected, "witness_empty"):
            self.witness.head()

    def test_witness_permissions_symlink_and_hardlink_rejected(self):
        self.witness.path.chmod(0o644)
        with self.assertRaisesRegex(Rejected, "witness_database_permissions"):
            self.witness.head()
        self.witness.path.chmod(0o600)
        other = self.root / "linked.db"
        other.hardlink_to(self.witness.path)
        with self.assertRaisesRegex(Rejected, "witness_database_permissions"):
            self.witness.head()
        other.unlink()
        self.witness.path.rename(other)
        self.witness.path.symlink_to(other)
        with self.assertRaisesRegex(Rejected, "witness_database_permissions"):
            self.witness.head()

    def test_witness_cannot_live_inside_engine_state_or_use_other_engine_key(self):
        with self.assertRaisesRegex(Rejected, "witness_state_overlap"):
            self.witness.bind_engine(self.root, self.digest, self.key)
        with self.assertRaisesRegex(Rejected, "witness_binding"):
            self.witness.bind_engine(self.root / "state", self.digest, secrets.token_bytes(32))

    def test_web_reports_witness_failure_as_unavailable_without_details(self):
        guarded = self.guarded()
        token = guarded.issue("operator", "nqc-evidence")
        self.witness.path.unlink()
        raw = canonical({"request_id": "web", "asset": "nqc-evidence"})
        env = {"PATH_INFO": "/v1/inspect", "REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
               "CONTENT_LENGTH": str(len(raw)), "HTTP_AUTHORIZATION": "Bearer " + token, "wsgi.input": io.BytesIO(raw)}
        statuses = []
        result = b"".join(Application(guarded)(env, lambda status, headers: statuses.append(status)))
        self.assertEqual(statuses, ["503 Service Unavailable"])
        self.assertNotIn(token.encode(), result)
        self.assertNotIn(str(self.witness_root).encode(), result)

    def test_cli_initializes_advances_and_guards_engine(self):
        self.consume()
        target = self.engine.checkpoint()
        create_local(self.root, "audit.key", self.key)
        create_local(self.root, "target.json", canonical(target))
        script = Path(__file__).resolve().parents[1] / "tools/witness_audit.py"
        args = [sys.executable, "-B", str(script), "--root", str(self.root / "cli-witness"),
                "--witness-key-file", str(self.root / "witness.key"), "--audit-key-file", str(self.root / "audit.key"),
                "--policy-digest", self.digest]
        initialized = subprocess.run([*args, "init"], check=True, capture_output=True)
        create_local(self.root, "expected.json", initialized.stdout)
        paths = []
        for i, data in enumerate(self.pages(target)):
            name = f"page-{i}.zip"
            create_local(self.root, name, data)
            paths.append(str(self.root / name))
        advanced = subprocess.run([*args, "advance", "--target", str(self.root / "target.json"),
                                  "--expected", str(self.root / "expected.json"), *paths], check=True, capture_output=True)
        self.assertEqual(decode(advanced.stdout)["revision"], 2)
        engine_args = [sys.executable, "-B", "-m", "nqc_defense", "--assets", str(self.assets),
                       "--configs", str(self.store.root), "--state", str(self.root / "state"), "--policy", self.digest,
                       "--key-file", str(self.root / "audit.key"), "--witness-root", str(self.root / "cli-witness"),
                       "--witness-key-file", str(self.root / "witness.key"), "checkpoint"]
        self.assertEqual(decode(subprocess.run(engine_args, check=True, capture_output=True).stdout), target)
        with self.engine.state.transaction() as db:
            db.execute("DELETE FROM audit WHERE seq=3")
        blocked = subprocess.run(engine_args, capture_output=True)
        self.assertEqual(blocked.returncode, 2)
        self.assertEqual(blocked.stdout, b"")


if __name__ == "__main__":
    unittest.main()
