import concurrent.futures
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

from test_defense import Fixture
from test_audit_pages import rewrite
from nqc_defense.archive_store import ArchiveStore, MAX_PAGES, MAX_TOTAL_BYTES
from nqc_defense.audit_pages import AuditPageVerifier, MAX_ARCHIVE_BYTES
from nqc_defense.codec import Rejected, canonical, decode
from nqc_defense.files import create_local, publish_local, sha256
from nqc_defense.witness import ORIGIN, Witness


class ArchiveStoreTests(Fixture):
    def setUp(self):
        super().setUp()
        self.witness_key = secrets.token_bytes(32)
        self.witness = Witness.create(self.root / "witness", self.witness_key, self.key, self.digest)
        self.archive = ArchiveStore.create(self.root / "archive")

    def consume(self, request_id="consume"):
        self.engine.admit_bytes(canonical({"request_id": request_id, "asset": "nqc-evidence"}), self.token())
        return self.engine.checkpoint()

    def pages(self, target, start=ORIGIN, limit=1):
        cursor = AuditPageVerifier(self.key, self.digest, target, start)
        while not cursor.complete:
            data = self.engine.export_page(cursor.current, target, limit=limit)
            cursor.accept(data)
            yield data

    def prepare(self, target=None, limit=1):
        target = target or self.consume()
        return self.archive.prepare(self.pages(target, limit=limit), self.key, self.digest, ORIGIN, target)

    def manifest(self, digest):
        return json.loads((self.archive.root / "manifests" / (digest + ".json")).read_bytes())

    def changed_manifest(self, digest, change):
        value = self.manifest(digest)
        change(value)
        data = canonical(value)
        updated = sha256(data)
        publish_local(self.archive.root, "manifests/" + updated + ".json", data)
        return updated

    def test_capture_persists_pages_and_advances_matching_witness(self):
        target, expected = self.consume(), self.witness.head()
        result = self.archive.capture(self.engine, self.witness, target, expected, limit=1)
        checked = ArchiveStore(self.archive.root).verify(result["manifest_sha256"], self.key, self.digest)
        self.assertEqual(checked["record_count"], 3)
        self.assertEqual(checked["pages"], 3)
        self.assertEqual(result["witness_receipt"], self.witness.head())
        self.assertFalse(result["recovered_existing_commit"])
        record = self.witness.record(2)
        self.assertEqual(record["event"]["page_chain_sha256"], checked["page_chain_sha256"])

    def test_prepared_archive_does_not_advance_witness(self):
        before = self.witness.head()
        prepared = self.prepare()
        self.assertEqual(self.witness.head(), before)
        manifest = self.manifest(prepared["manifest_sha256"])
        for entry in manifest["pages"]:
            path = self.archive.root / "pages" / (entry["sha256"] + ".zip")
            self.assertEqual(sha256(path.read_bytes()), entry["sha256"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_archive_verification_does_not_require_engine_database(self):
        prepared = self.prepare()
        self.engine.state.path.unlink()
        self.assertTrue(ArchiveStore(self.archive.root).verify(prepared["manifest_sha256"], self.key, self.digest)["verified"])

    def test_prepare_is_deterministic_and_reuses_existing_files(self):
        target = self.consume()
        first = self.prepare(target)
        stats = {p.name: (p.stat().st_ino, p.stat().st_mtime_ns) for p in (self.archive.root / "pages").iterdir()}
        second = self.prepare(target)
        self.assertEqual(first, second)
        self.assertEqual(stats, {p.name: (p.stat().st_ino, p.stat().st_mtime_ns) for p in (self.archive.root / "pages").iterdir()})

    def test_incomplete_interval_never_seals_manifest(self):
        target = self.consume()
        before = self.witness.head()
        with self.assertRaisesRegex(Rejected, "audit_pages_incomplete"):
            self.archive.prepare(list(self.pages(target))[:-1], self.key, self.digest, ORIGIN, target)
        self.assertEqual(list((self.archive.root / "manifests").iterdir()), [])
        self.assertEqual(self.witness.head(), before)

    def test_source_read_failure_leaves_no_complete_manifest(self):
        target = self.consume()
        def interrupted():
            yield next(self.pages(target))
            raise OSError("controlled input interruption")
        with self.assertRaises(OSError):
            self.archive.prepare(interrupted(), self.key, self.digest, ORIGIN, target)
        self.assertEqual(list((self.archive.root / "manifests").iterdir()), [])

    def test_invalid_input_page_is_rejected_before_storage(self):
        target = self.consume()
        page = rewrite(next(self.pages(target)), lambda value: value["records"][0].update(payload="{}"))
        with self.assertRaisesRegex(Rejected, "audit_integrity"):
            self.archive.prepare([page], self.key, self.digest, ORIGIN, target)
        self.assertEqual(list((self.archive.root / "pages").iterdir()), [])

    def test_corrupt_stored_page_blocks_verification_and_witness_advancement(self):
        prepared = self.prepare()
        before = self.witness.head()
        manifest = self.manifest(prepared["manifest_sha256"])
        path = self.archive.root / "pages" / (manifest["pages"][-1]["sha256"] + ".zip")
        path.write_bytes(b"corrupted on disk")
        for operation in (lambda: self.archive.verify(prepared["manifest_sha256"], self.key, self.digest),
                          lambda: self.archive.finalize(self.witness, prepared["manifest_sha256"], before)):
            with self.assertRaisesRegex(Rejected, "archive_page_integrity"):
                operation()
        self.assertEqual(self.witness.head(), before)

    def test_missing_page_is_not_recreated_or_ignored(self):
        prepared = self.prepare()
        manifest = self.manifest(prepared["manifest_sha256"])
        path = self.archive.root / "pages" / (manifest["pages"][0]["sha256"] + ".zip")
        path.unlink()
        with self.assertRaisesRegex(Rejected, "file_unavailable"):
            self.archive.finalize(self.witness, prepared["manifest_sha256"], self.witness.head())
        self.assertFalse(path.exists())

    def test_manifest_hash_and_transcript_are_both_enforced(self):
        prepared = self.prepare()
        digest = prepared["manifest_sha256"]
        noncanonical = canonical(self.manifest(digest)) + b" "
        noncanonical_digest = sha256(noncanonical)
        publish_local(self.archive.root, "manifests/" + noncanonical_digest + ".json", noncanonical)
        with self.assertRaisesRegex(Rejected, "archive_manifest_encoding"):
            self.archive.verify(noncanonical_digest, self.key, self.digest)
        changed = self.changed_manifest(digest, lambda value: value.update(page_chain_sha256="f" * 64))
        before = self.witness.head()
        with self.assertRaisesRegex(Rejected, "archive_transcript_mismatch"):
            self.archive.finalize(self.witness, changed, before)
        self.assertEqual(self.witness.head(), before)
        path = self.archive.root / "manifests" / (digest + ".json")
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(Rejected, "archive_manifest_integrity"):
            self.archive.verify(digest, self.key, self.digest)

    def test_manifest_cannot_substitute_policy_key_or_interval(self):
        digest = self.prepare()["manifest_sha256"]
        for change in (lambda value: value.update(policy_digest="f" * 64),
                       lambda value: value.update(audit_key_id="f" * 64),
                       lambda value: value.update(records=999)):
            altered = self.changed_manifest(digest, change)
            with self.assertRaises(Rejected):
                self.archive.verify(altered, self.key, self.digest)
        with self.assertRaisesRegex(Rejected, "archive_manifest_binding"):
            self.archive.verify(digest, secrets.token_bytes(32), self.digest)

    def test_duplicate_or_reordered_pages_do_not_form_a_complete_archive(self):
        digest = self.prepare()["manifest_sha256"]
        for change in (lambda value: value["pages"].reverse(),
                       lambda value: value["pages"].__setitem__(1, value["pages"][0])):
            altered = self.changed_manifest(digest, change)
            with self.assertRaises(Rejected):
                self.archive.verify(altered, self.key, self.digest)

    def test_manifest_bounds_are_checked_before_reading_pages(self):
        digest = self.prepare()["manifest_sha256"]
        changes = [lambda value: value.update(pages=[value["pages"][0]] * (MAX_PAGES + 1)),
                   lambda value: value.update(pages=[{"sha256": "f" * 64, "size_bytes": MAX_ARCHIVE_BYTES}]
                                             * (MAX_TOTAL_BYTES // MAX_ARCHIVE_BYTES + 1))]
        for change in changes:
            with self.assertRaisesRegex(Rejected, "archive_page_limit|archive_total_size"):
                self.archive.verify(self.changed_manifest(digest, change), self.key, self.digest)

    def test_manifest_paths_are_derived_only_from_valid_hashes(self):
        digest = self.prepare()["manifest_sha256"]
        with self.assertRaises(Rejected):
            self.archive.verify("../outside", self.key, self.digest)
        altered = self.changed_manifest(digest, lambda value: value["pages"][0].update(sha256="../outside"))
        with self.assertRaises(Rejected):
            self.archive.verify(altered, self.key, self.digest)

    def test_store_permissions_symlink_and_missing_directory_fail_closed(self):
        digest = self.prepare()["manifest_sha256"]
        pages = self.archive.root / "pages"
        pages.chmod(0o755)
        with self.assertRaisesRegex(Rejected, "archive_store_permissions"):
            self.archive.verify(digest, self.key, self.digest)
        pages.chmod(0o700)
        moved = self.root / "moved-pages"
        pages.rename(moved)
        pages.symlink_to(moved)
        with self.assertRaisesRegex(Rejected, "archive_store_permissions"):
            self.archive.verify(digest, self.key, self.digest)
        pages.unlink()
        with self.assertRaisesRegex(Rejected, "archive_store_unavailable"):
            self.archive.verify(digest, self.key, self.digest)

    def test_parallel_prepare_deduplicates_without_partial_final_files(self):
        target = self.consume()
        pages = list(self.pages(target))
        def writer(_):
            return self.archive.prepare(pages, self.key, self.digest, ORIGIN, target)["manifest_sha256"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(writer, range(8)))
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(len(list((self.archive.root / "pages").iterdir())), 3)
        self.assertTrue(self.archive.verify(results[0], self.key, self.digest)["verified"])

    def test_concurrent_finalize_acknowledges_one_commit(self):
        digest = self.prepare()["manifest_sha256"]
        before = self.witness.head()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.archive.finalize(self.witness, digest, before), range(4)))
        self.assertTrue(all(value["witness_receipt"] == self.witness.head() for value in results))
        self.assertEqual(self.witness.head()["revision"], 2)

    def test_prepared_archive_can_be_finalized_after_process_reopen(self):
        digest = self.prepare()["manifest_sha256"]
        before = self.witness.head()
        reopened_store = ArchiveStore(self.archive.root)
        reopened_witness = Witness(self.witness.root, self.witness_key, self.key, self.digest)
        result = reopened_store.finalize(reopened_witness, digest, before)
        self.assertEqual(result["witness_receipt"]["revision"], 2)

    def test_lost_ack_is_recovered_even_after_a_later_interval(self):
        first_target, before = self.consume(), self.witness.head()
        first = self.archive.capture(self.engine, self.witness, first_target, before, limit=1)
        second_target = self.consume("second")
        second = self.archive.capture(self.engine, self.witness, second_target, self.witness.head(), limit=1)
        recovered = self.archive.finalize(self.witness, first["manifest_sha256"], before)
        self.assertTrue(recovered["recovered_existing_commit"])
        self.assertEqual(recovered["witness_receipt"], first["witness_receipt"])
        self.assertEqual(self.witness.head(), second["witness_receipt"])

    def test_retry_never_substitutes_a_different_page_transcript(self):
        target = self.consume()
        first, second = self.prepare(target, 1), self.prepare(target, 2)
        before = self.witness.head()
        self.archive.finalize(self.witness, first["manifest_sha256"], before)
        with self.assertRaisesRegex(Rejected, "archive_witness_binding"):
            self.archive.finalize(self.witness, second["manifest_sha256"], before)
        self.assertEqual(self.witness.head()["revision"], 2)

    def test_recovery_still_requires_stored_page_availability(self):
        digest = self.prepare()["manifest_sha256"]
        before = self.witness.head()
        self.archive.finalize(self.witness, digest, before)
        manifest = self.manifest(digest)
        (self.archive.root / "pages" / (manifest["pages"][0]["sha256"] + ".zip")).unlink()
        with self.assertRaises(Rejected):
            self.archive.finalize(self.witness, digest, before)

    def test_witness_commit_failure_preserves_archive_for_retry(self):
        digest = self.prepare()["manifest_sha256"]
        before = self.witness.head()
        with self.witness.connection(write=True) as db:
            db.execute("CREATE TABLE parent_fault(id INTEGER PRIMARY KEY)")
            db.execute("CREATE TABLE child_fault(id INTEGER REFERENCES parent_fault(id) DEFERRABLE INITIALLY DEFERRED)")
            db.execute("CREATE TRIGGER fail_commit AFTER INSERT ON anchors BEGIN INSERT INTO child_fault VALUES(999); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.archive.finalize(self.witness, digest, before)
        self.assertEqual(self.witness.head(), before)
        self.assertTrue(self.archive.verify(digest, self.key, self.digest)["verified"])
        with self.witness.connection(write=True) as db:
            db.execute("DROP TRIGGER fail_commit")
        self.assertEqual(self.archive.finalize(self.witness, digest, before)["witness_receipt"]["revision"], 2)

    def test_file_fsync_failure_never_seals_or_advances(self):
        target = self.consume()
        pages, before = list(self.pages(target)), self.witness.head()
        with patch("nqc_defense.files.os.fsync", side_effect=OSError("injected fsync failure")):
            with self.assertRaises(OSError):
                self.archive.prepare(pages, self.key, self.digest, ORIGIN, target)
        self.assertEqual(list((self.archive.root / "pages").iterdir()), [])
        self.assertEqual(list((self.archive.root / "manifests").iterdir()), [])
        self.assertEqual(self.witness.head(), before)

    def test_directory_fsync_failure_is_retryable_without_false_ack(self):
        target = self.consume()
        pages, before = list(self.pages(target)), self.witness.head()
        real_fsync = os.fsync
        def reject_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("injected directory fsync failure")
            return real_fsync(fd)
        with patch("nqc_defense.files.os.fsync", side_effect=reject_directory):
            with self.assertRaises(OSError):
                self.archive.prepare(pages, self.key, self.digest, ORIGIN, target)
        self.assertEqual(self.witness.head(), before)
        self.assertEqual(list((self.archive.root / "manifests").iterdir()), [])
        prepared = self.archive.prepare(pages, self.key, self.digest, ORIGIN, target)
        self.assertEqual(self.archive.finalize(self.witness, prepared["manifest_sha256"], before)["witness_receipt"]["revision"], 2)

    def test_conflicting_existing_object_is_never_overwritten(self):
        target = self.consume()
        pages = list(self.pages(target))
        path = self.archive.root / "pages" / (sha256(pages[0]) + ".zip")
        path.write_bytes(b"pre-existing bytes")
        with self.assertRaises(Rejected):
            self.archive.prepare(pages, self.key, self.digest, ORIGIN, target)
        self.assertEqual(path.read_bytes(), b"pre-existing bytes")

    def test_cleanup_failure_still_closes_owned_file_descriptors(self):
        opened = []
        real_open = os.open
        def track_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd
        with patch("nqc_defense.files.os.open", side_effect=track_open):
            with patch("nqc_defense.files.os.unlink", side_effect=OSError("injected cleanup failure")):
                with self.assertRaises(OSError):
                    publish_local(self.archive.root, "cleanup.json", b"{}")
        self.assertEqual(len(opened), 2)
        for fd in opened:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_manifest_write_failure_leaves_pages_unacknowledged_and_retryable(self):
        target, before = self.consume(), self.witness.head()
        def interrupted_publish(root, name, data):
            if name.startswith("manifests/"):
                with patch("nqc_defense.files.os.fsync", side_effect=OSError("injected manifest fsync failure")):
                    return publish_local(root, name, data)
            return publish_local(root, name, data)
        with patch("nqc_defense.archive_store.publish_local", side_effect=interrupted_publish):
            with self.assertRaises(OSError):
                self.archive.capture(self.engine, self.witness, target, before, limit=1)
        self.assertEqual(self.witness.head(), before)
        self.assertEqual(len(list((self.archive.root / "pages").iterdir())), 3)
        self.assertEqual(list((self.archive.root / "manifests").iterdir()), [])
        self.assertEqual(self.archive.capture(self.engine, self.witness, target, before, limit=1)["witness_receipt"]["revision"], 2)

    def test_temporary_name_collision_does_not_delete_an_unowned_file(self):
        name = "pending-" + "0" * 48
        create_local(self.archive.root, name, b"existing private file")
        with patch("nqc_defense.files.secrets.token_hex", return_value="0" * 48):
            with self.assertRaises(FileExistsError):
                publish_local(self.archive.root, "new.json", b"{}")
        self.assertEqual((self.archive.root / name).read_bytes(), b"existing private file")
        self.assertFalse((self.archive.root / "new.json").exists())
        with patch("nqc_defense.files.secrets.token_hex", return_value="a" * 48):
            with self.assertRaisesRegex(Rejected, "temporary_name_conflict"):
                publish_local(self.archive.root, "pending-" + "a" * 48, b"{}")

    def test_archive_is_separate_and_does_not_store_artifact_content_or_keys(self):
        target = self.consume()
        nested = ArchiveStore.create(self.engine.state.root / "nested-archive")
        with self.assertRaisesRegex(Rejected, "archive_store_overlap"):
            nested.capture(self.engine, self.witness, target, self.witness.head())
        self.prepare(target)
        for path in self.archive.root.rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                self.assertNotIn(self.payload, data)
                self.assertNotIn(self.key, data)
                self.assertNotIn(self.witness_key, data)

    def test_cli_capture_verify_and_finalize_retry_with_retained_receipt(self):
        target, before = self.consume(), self.witness.head()
        for name, data in (("audit.key", self.key), ("witness.key", self.witness_key),
                           ("target.json", canonical(target)), ("expected.json", canonical(before))):
            create_local(self.root, name, data)
        tool = Path(__file__).resolve().parents[1] / "tools/archive_audit.py"
        archive_root = self.root / "cli-archive"
        args = [sys.executable, "-B", str(tool), "--root", str(archive_root)]
        subprocess.run([*args, "init"], check=True, capture_output=True)
        capture = [sys.executable, "-B", "-m", "nqc_defense", "--assets", str(self.assets),
                   "--configs", str(self.store.root), "--state", str(self.root / "state"), "--policy", self.digest,
                   "--key-file", str(self.root / "audit.key"), "--witness-root", str(self.witness.root),
                   "--witness-key-file", str(self.root / "witness.key"), "archive-audit", "--archive-root", str(archive_root),
                   "--target", str(self.root / "target.json"), "--expected", str(self.root / "expected.json"), "--limit", "1"]
        result = decode(subprocess.run(capture, check=True, capture_output=True).stdout)
        credentials = ["--audit-key-file", str(self.root / "audit.key"), "--policy-digest", self.digest]
        checked = subprocess.run([*args, "verify", result["manifest_sha256"], *credentials], check=True, capture_output=True)
        self.assertTrue(decode(checked.stdout)["verified"])
        finalize = [*args, "finalize", result["manifest_sha256"], *credentials, "--witness-root", str(self.witness.root),
                    "--witness-key-file", str(self.root / "witness.key"), "--expected", str(self.root / "expected.json"),
                    "--receipt-output", str(self.root / "retained.json")]
        for _ in range(2):
            recovered = decode(subprocess.run(finalize, check=True, capture_output=True).stdout)
            self.assertTrue(recovered["recovered_existing_commit"])
        retained = decode((self.root / "retained.json").read_bytes())
        self.assertEqual(retained["witness_receipt"], result["witness_receipt"])
        self.assertEqual(self.witness.head()["revision"], 2)


if __name__ == "__main__":
    unittest.main()
