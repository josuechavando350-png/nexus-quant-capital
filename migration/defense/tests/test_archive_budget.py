import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

from test_defense import Fixture
from nqc_defense.archive_budget import POLICY_FILE, limits
from nqc_defense.archive_coverage import ArchiveCoverage
from nqc_defense.archive_inventory import ArchiveInventory
from nqc_defense.archive_store import ArchiveStore
from nqc_defense.codec import Rejected, canonical, decode
from nqc_defense.files import create_local, read_local, sha256
from nqc_defense.witness import Witness


class ArchiveBudgetTests(Fixture):
    def setUp(self):
        super().setUp()
        self.archive = ArchiveStore.create(self.root / "archive")
        self.witness_key = secrets.token_bytes(32)
        self.witness = Witness.create(self.root / "witness", self.witness_key, self.key, self.digest)

    def configure(self, byte_limit=1024 * 1024, object_limit=64):
        result = self.archive.configure_budget(byte_limit, object_limit)
        self.archive = ArchiveStore(self.archive.root, result["budget_digest"])
        return result

    def blob(self, data=b"local quota test object"):
        name = "pages/" + sha256(data) + ".zip"
        self.archive._publish(name, data)
        return name

    def admitted(self):
        self.engine.admit_bytes(canonical({"request_id": "budget-source", "asset": "nqc-evidence"}), self.token())
        return self.engine.checkpoint()

    def workers(self, payloads):
        code = """
import sys
from nqc_defense.archive_store import ArchiveStore
from nqc_defense.files import sha256
from nqc_defense.codec import Rejected
store = ArchiveStore(sys.argv[1], sys.argv[2])
data = sys.argv[3].encode()
print('ready', flush=True)
try:
    store._publish('pages/' + sha256(data) + '.zip', data)
    print('stored', flush=True)
except Rejected as exc:
    print(str(exc), flush=True)
"""
        children = []
        handle = os.open(self.archive.root, os.O_RDONLY | os.O_DIRECTORY)
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            for payload in payloads:
                children.append(subprocess.Popen([sys.executable, "-B", "-c", code,
                    str(self.archive.root), self.archive.budget_digest, payload], stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True))
            for child in children:
                self.assertEqual(child.stdout.readline().strip(), "ready")
        finally:
            os.close(handle)
        try:
            outcomes = []
            for child in children:
                out, error = child.communicate(timeout=15)
                self.assertEqual(child.returncode, 0, error)
                outcomes.append(out.strip())
            return outcomes
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)

    def crash_publication(self, after_link=False):
        code = """
import os, sys
from unittest.mock import patch
from nqc_defense.archive_store import ArchiveStore
from nqc_defense.files import sha256
store = ArchiveStore(sys.argv[1], sys.argv[2])
data = b'persisted bytes from interrupted publication'
original = os.link
def interrupted(*args, **kwargs):
    if sys.argv[3] == 'after':
        original(*args, **kwargs)
    os._exit(23)
with patch('nqc_defense.files.os.link', side_effect=interrupted):
    store._publish('pages/' + sha256(data) + '.zip', data)
"""
        result = subprocess.run([sys.executable, "-B", "-c", code, str(self.archive.root),
                                 self.archive.budget_digest, "after" if after_link else "before"],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 23, result.stderr)

    def test_policy_is_canonical_private_pinned_and_reopened(self):
        result = self.configure()
        data = read_local(self.archive.root, POLICY_FILE)
        self.assertEqual(data, canonical(limits(1024 * 1024, 64)))
        self.assertEqual(result["budget_digest"], sha256(data))
        self.assertEqual((self.archive.root / POLICY_FILE).stat().st_mode & 0o777, 0o600)
        status = self.archive.budget_status()
        self.assertEqual((status["used_objects"], status["used_logical_bytes"]), (1, len(data)))
        self.assertTrue(status["within_budget"])

    def test_policy_installation_is_idempotent_without_replacement(self):
        first = self.configure()
        path = self.archive.root / POLICY_FILE
        before = path.stat()
        second = ArchiveStore(self.archive.root).configure_budget(1024 * 1024, 64)
        after = path.stat()
        self.assertEqual(first, second)
        self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))

    def test_policy_cannot_be_changed_by_reconfiguration(self):
        self.configure()
        before = (self.archive.root / POLICY_FILE).read_bytes()
        with self.assertRaisesRegex(Rejected, "archive_budget_already_configured"):
            ArchiveStore(self.archive.root).configure_budget(2048, 12)
        with self.assertRaisesRegex(Rejected, "archive_budget_pin_conflict"):
            self.archive.configure_budget(2048, 12)
        self.assertEqual((self.archive.root / POLICY_FILE).read_bytes(), before)

    def test_failed_policy_directory_sync_recovers_identical_installation(self):
        original = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("injected policy directory sync failure")
            return original(fd)
        with patch("nqc_defense.files.os.fsync", side_effect=fail_directory):
            with self.assertRaises(OSError):
                self.archive.configure_budget(10000, 2)
        path = self.archive.root / POLICY_FILE
        before = path.stat()
        result = self.configure(10000, 2)
        self.assertEqual(result["used_objects"], 1)
        self.assertEqual(path.stat().st_ino, before.st_ino)

    def test_invalid_and_too_small_limits_create_no_policy(self):
        for size, count in ((True, 2), (0, 2), (1000, 0), (2**32 + 1, 2), (1000, 20001), (1, 1)):
            with self.subTest(size=size, count=count), self.assertRaises(Rejected):
                self.archive.configure_budget(size, count)
        self.assertFalse((self.archive.root / POLICY_FILE).exists())

    def test_existing_objects_count_when_installing_policy(self):
        name = self.blob()
        with self.assertRaisesRegex(Rejected, "archive_budget_exceeded"):
            self.archive.configure_budget(1000, 1)
        self.assertFalse((self.archive.root / POLICY_FILE).exists())
        self.configure(1000, 2)
        self.assertEqual(self.archive.budget_status()["used_objects"], 2)
        self.assertTrue((self.archive.root / name).exists())

    def test_previously_opened_unpinned_writer_cannot_ignore_new_policy(self):
        previous = ArchiveStore(self.archive.root)
        self.configure()
        data = b"unpinned operation"
        with self.assertRaisesRegex(Rejected, "archive_budget_pin_required"):
            previous._publish("pages/" + sha256(data) + ".zip", data)
        self.assertEqual(self.archive.budget_status()["used_objects"], 1)

    def test_wrong_missing_or_modified_policy_stops_pinned_writer(self):
        self.configure()
        with self.assertRaisesRegex(Rejected, "archive_budget_integrity"):
            ArchiveStore(self.archive.root, "f" * 64).budget_status()
        path = self.archive.root / POLICY_FILE
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaisesRegex(Rejected, "archive_budget_integrity"):
            self.blob()
        path.unlink()
        with self.assertRaisesRegex(Rejected, "archive_budget_missing"):
            self.blob()

    def test_budget_policy_symlink_and_public_permissions_rejected(self):
        self.configure()
        path = self.archive.root / POLICY_FILE
        path.chmod(0o644)
        with self.assertRaisesRegex(Rejected, "archive_budget_permissions"):
            self.archive.budget_status()
        path.unlink()
        path.symlink_to(self.assets / "evidence.json")
        with self.assertRaisesRegex(Rejected, "archive_budget_permissions"):
            self.archive.budget_status()

    def test_exact_byte_budget_accepts_boundary_and_rejects_growth(self):
        size, count = 1000, 8
        self.configure(size, count)
        data = b"x" * (size - len(canonical(limits(size, count))))
        self.blob(data)
        self.assertEqual(self.archive.budget_status()["remaining_logical_bytes"], 0)
        with self.assertRaisesRegex(Rejected, "archive_budget_exceeded"):
            self.blob(b"new object")
        self.assertEqual(self.archive.budget_status()["used_objects"], 2)

    def test_exact_object_budget_rejects_without_creating_temporary(self):
        self.configure(10000, 2)
        self.blob()
        before = sorted(str(path) for path in self.archive.root.rglob("*"))
        with self.assertRaisesRegex(Rejected, "archive_budget_exceeded"):
            self.blob(b"second object")
        self.assertEqual(before, sorted(str(path) for path in self.archive.root.rglob("*")))

    def test_identical_retry_at_full_budget_does_not_create_temporary_copy(self):
        self.configure(1000, 2)
        data = b"x" * (1000 - len(canonical(limits(1000, 2))))
        name = self.blob(data)
        before = (self.archive.root / name).stat()
        original = os.open
        creations = []
        def observe(path, flags, *args, **kwargs):
            if flags & os.O_CREAT:
                creations.append(path)
            return original(path, flags, *args, **kwargs)
        with patch("nqc_defense.files.os.open", side_effect=observe):
            self.blob(data)
        after = (self.archive.root / name).stat()
        self.assertEqual(creations, [])
        self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))

    def test_corrupt_existing_object_is_never_deduplicated_or_overwritten(self):
        self.configure()
        data = b"original object"
        name = self.blob(data)
        path = self.archive.root / name
        path.write_bytes(b"changed object")
        with self.assertRaisesRegex(Rejected, "existing_file_differs"):
            self.blob(data)
        self.assertEqual(path.read_bytes(), b"changed object")

    def test_unknown_files_and_pending_objects_consume_budget(self):
        self.configure(10000, 3)
        create_local(self.archive.root, "operator-file", b"operator data")
        create_local(self.archive.root, "pages/pending-" + "a" * 48, b"unfinished object")
        with self.assertRaisesRegex(Rejected, "archive_budget_exceeded"):
            self.blob()
        self.assertEqual(self.archive.budget_status()["used_objects"], 3)

    def test_external_growth_is_reported_and_blocks_new_publication(self):
        self.configure(1000, 2)
        create_local(self.archive.root, "external-object", b"x" * 1000)
        self.assertFalse(self.archive.budget_status()["within_budget"])
        with self.assertRaisesRegex(Rejected, "archive_budget_exceeded"):
            self.blob()
        self.assertTrue((self.archive.root / "external-object").exists())

    def test_concurrent_processes_cannot_overbook_last_object_slot(self):
        self.configure(10000, 2)
        outcomes = self.workers([f"process-{index}" for index in range(6)])
        self.assertEqual(outcomes.count("stored"), 1)
        self.assertEqual(outcomes.count("archive_budget_exceeded"), 5)
        self.assertEqual(self.archive.budget_status()["used_objects"], 2)

    def test_concurrent_identical_process_writes_share_one_object(self):
        self.configure(10000, 2)
        self.assertEqual(self.workers(["same object"] * 6), ["stored"] * 6)
        self.assertEqual(self.archive.budget_status()["used_objects"], 2)

    def test_threads_with_separate_store_instances_share_kernel_lock(self):
        self.configure(10000, 2)
        def publish(index):
            store = ArchiveStore(self.archive.root, self.archive.budget_digest)
            data = str(index).encode()
            try:
                store._publish("pages/" + sha256(data) + ".zip", data)
                return "stored"
            except Rejected as exc:
                return str(exc)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(publish, range(8)))
        self.assertEqual(results.count("stored"), 1)
        self.assertEqual(results.count("archive_budget_exceeded"), 7)

    def test_lock_timeout_is_bounded_and_closes_descriptor(self):
        self.configure()
        handle = os.open(self.archive.root, os.O_RDONLY | os.O_DIRECTORY)
        fcntl.flock(handle, fcntl.LOCK_EX)
        before = len(os.listdir("/proc/self/fd"))
        try:
            with patch("nqc_defense.archive_budget.LOCK_WAIT_SECONDS", 0.02):
                with self.assertRaisesRegex(Rejected, "archive_writer_busy"):
                    self.blob()
            self.assertEqual(len(os.listdir("/proc/self/fd")), before)
        finally:
            os.close(handle)
        self.blob()

    def test_process_exit_before_link_retains_budgeted_pending_bytes_and_releases_lock(self):
        self.configure(10000, 2)
        self.crash_publication()
        pending = list((self.archive.root / "pages").glob("pending-*"))
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].read_bytes(), b"persisted bytes from interrupted publication")
        self.assertEqual(self.archive.budget_status()["used_objects"], 2)
        with self.assertRaisesRegex(Rejected, "archive_budget_exceeded"):
            self.blob()
        self.assertTrue(pending[0].exists())

    def test_process_exit_after_link_requires_review_of_aliases_without_auto_cleanup(self):
        self.configure(10000, 3)
        self.crash_publication(after_link=True)
        paths = list((self.archive.root / "pages").iterdir())
        self.assertEqual(len(paths), 2)
        self.assertEqual([path.stat().st_nlink for path in paths], [2, 2])
        with self.assertRaisesRegex(Rejected, "inventory_hardlink"):
            self.archive.budget_status()
        self.assertTrue(all(path.exists() for path in paths))

    def test_failed_file_sync_does_not_consume_an_object_or_keep_lock(self):
        self.configure()
        with patch("nqc_defense.files.os.fsync", side_effect=OSError("injected sync failure")):
            with self.assertRaises(OSError):
                self.blob()
        self.assertEqual(self.archive.budget_status()["used_objects"], 1)
        self.blob()
        self.assertEqual(self.archive.budget_status()["used_objects"], 2)

    def test_directory_sync_failure_is_counted_and_retry_needs_no_extra_space(self):
        self.configure(10000, 2)
        original = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("injected directory sync failure")
            return original(fd)
        with patch("nqc_defense.files.os.fsync", side_effect=fail_directory):
            with self.assertRaises(OSError):
                self.blob()
        self.assertEqual(self.archive.budget_status()["used_objects"], 2)
        self.blob()
        self.assertEqual(self.archive.budget_status()["used_objects"], 2)

    def test_budget_exhaustion_mid_interval_never_advances_witness(self):
        target = self.admitted()
        origin = self.witness.head()
        self.configure(100000, 3)  # Policy and two pages fit; the third page does not.
        with self.assertRaisesRegex(Rejected, "archive_budget_exceeded"):
            self.archive.capture(self.engine, self.witness, target, origin, limit=1)
        self.assertEqual(self.witness.head(), origin)
        self.assertEqual(self.engine.checkpoint(), target)
        self.assertEqual(len(list((self.archive.root / "pages").iterdir())), 2)
        self.assertEqual(list((self.archive.root / "manifests").iterdir()), [])

    def test_manifest_and_catalog_are_also_subject_to_object_budget(self):
        target = self.admitted()
        origin = self.witness.head()
        self.configure(100000, 4)  # Policy plus three pages, with no slot for the manifest.
        with self.assertRaisesRegex(Rejected, "archive_budget_exceeded"):
            self.archive.capture(self.engine, self.witness, target, origin, limit=1)
        self.assertEqual(self.witness.head(), origin)
        # A second independently budgeted archive has room for manifest, but not catalog.
        other = ArchiveStore.create(self.root / "catalog-budget")
        other.configure_budget(100000, 5)
        captured = other.capture(self.engine, self.witness, target, origin, limit=1)
        with self.assertRaisesRegex(Rejected, "archive_budget_exceeded"):
            ArchiveCoverage(other, self.witness).seal([captured["manifest_sha256"]], origin, self.witness.head())
        self.assertEqual(list(other.root.glob("coverage-*.json")), [])
        self.assertEqual(other.budget_status()["used_objects"], 5)

    def test_real_capture_catalog_inventory_and_recovery_share_pinned_budget(self):
        target, origin = self.admitted(), self.witness.head()
        self.configure(100000, 6)
        captured = self.archive.capture(self.engine, self.witness, target, origin, limit=1)
        sealed = ArchiveCoverage(self.archive, self.witness).seal([captured["manifest_sha256"]], origin, self.witness.head())
        result = ArchiveInventory(self.archive, self.witness).inspect([{"catalog_sha256": sealed["catalog_sha256"],
                     "start_receipt": origin, "target_receipt": self.witness.head()}])
        self.assertTrue(result["verified"])
        self.assertEqual(result["summary"]["control"]["objects"], 1)
        self.assertEqual(result["observed_objects"], 6)
        retried = self.archive.capture(self.engine, self.witness, target, origin, limit=1)
        self.assertTrue(retried["recovered_existing_commit"])
        self.assertEqual(self.archive.budget_status()["used_objects"], 6)

    def test_budget_pin_is_required_for_new_catalog_even_when_pages_are_valid(self):
        target, origin = self.admitted(), self.witness.head()
        self.configure()
        captured = self.archive.capture(self.engine, self.witness, target, origin, limit=1)
        checker = ArchiveCoverage(ArchiveStore(self.archive.root), self.witness)
        with self.assertRaisesRegex(Rejected, "archive_budget_pin_required"):
            checker.seal([captured["manifest_sha256"]], origin, self.witness.head())
        self.assertTrue(ArchiveStore(self.archive.root).verify(captured["manifest_sha256"], self.key, self.digest)["verified"])

    def test_cli_configures_reopens_and_requires_pin_for_prepare(self):
        script = Path(__file__).resolve().parents[1] / "tools/archive_audit.py"
        base = [sys.executable, "-B", str(script), "--root", str(self.archive.root)]
        configured = decode(subprocess.run([*base, "configure-budget", "--max-bytes", "100000", "--max-objects", "8"],
                                           check=True, capture_output=True).stdout)
        pin = configured["budget_digest"]
        status = decode(subprocess.run([*base, "--budget-digest", pin, "budget-status"], check=True, capture_output=True).stdout)
        self.assertEqual(status["used_objects"], 1)
        target = self.admitted()
        page = self.engine.export_page({"sequence": 0, "head": "0" * 64}, target)
        for name, data in (("audit.key", self.key), ("target.json", canonical(target)), ("page.zip", page)):
            create_local(self.root, name, data)
        args = ["prepare", str(self.root / "page.zip"), "--audit-key-file", str(self.root / "audit.key"),
                "--policy-digest", self.digest, "--target", str(self.root / "target.json")]
        rejected = subprocess.run([*base, *args], capture_output=True)
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(decode(rejected.stdout)["reason"], "archive_budget_pin_required")
        prepared = decode(subprocess.run([*base, "--budget-digest", pin, *args], check=True, capture_output=True).stdout)
        self.assertTrue(prepared["verified"])

    def test_cli_init_requires_paired_limits_before_creating_directory(self):
        script = Path(__file__).resolve().parents[1] / "tools/archive_audit.py"
        target = self.root / "new-budgeted-archive"
        args = [sys.executable, "-B", str(script), "--root", str(target), "init", "--max-bytes", "100000"]
        failed = subprocess.run(args, capture_output=True)
        self.assertEqual(failed.returncode, 2)
        self.assertFalse(target.exists())
        result = decode(subprocess.run([*args, "--max-objects", "8"], check=True, capture_output=True).stdout)
        self.assertTrue(result["created"] and result["configured"])
        self.assertTrue(ArchiveStore(target, result["budget_digest"]).budget_status()["within_budget"])

    def test_engine_archive_command_enforces_reopened_budget_pin(self):
        target, origin = self.admitted(), self.witness.head()
        self.configure(100000, 5)
        for name, data in (("audit.key", self.key), ("witness.key", self.witness_key),
                           ("target.json", canonical(target)), ("origin.json", canonical(origin))):
            create_local(self.root, name, data)
        args = [sys.executable, "-B", "-m", "nqc_defense", "--assets", str(self.assets),
                "--configs", str(self.store.root), "--state", str(self.engine.state.root),
                "--policy", self.digest, "--key-file", str(self.root / "audit.key"),
                "--witness-root", str(self.witness.root), "--witness-key-file", str(self.root / "witness.key"),
                "archive-audit", "--archive-root", str(self.archive.root), "--target", str(self.root / "target.json"),
                "--expected", str(self.root / "origin.json"), "--limit", "1"]
        rejected = subprocess.run(args, capture_output=True)
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(list((self.archive.root / "pages").iterdir()), [])
        result = decode(subprocess.run([*args, "--archive-budget-digest", self.archive.budget_digest],
                                       check=True, capture_output=True).stdout)
        self.assertEqual(result["witness_receipt"]["checkpoint"], target)
        self.assertEqual(self.archive.budget_status()["used_objects"], 5)


if __name__ == "__main__":
    unittest.main()
