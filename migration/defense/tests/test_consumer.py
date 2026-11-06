import concurrent.futures
import io
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest

from test_defense import Fixture
from test_decision_controls import rewrite_export
from nqc_defense.audit import mac
from nqc_defense.codec import Rejected, canonical, decode
from nqc_defense.consumer import ArtifactReader
from nqc_defense.engine import Engine
from nqc_defense.files import create_local, sha256
from nqc_defense.verify_export import verify as verify_export
from nqc_defense.web import Application


class ConsumerTests(Fixture):
    def raw(self, request_id="snapshot"):
        return canonical({"request_id": request_id, "asset": "nqc-evidence"})

    def consume(self, token=None, request_id="snapshot"):
        return ArtifactReader(self.engine).read_json(self.raw(request_id), token or self.token())

    def replace_baseline(self, data, rate_limit=100):
        (self.assets / "evidence.json").write_bytes(data)
        self.policy["assets"][0]["sha256"] = sha256(data)
        self.policy["rate_limit"] = rate_limit
        self.digest = self.store.put(canonical(self.policy))
        self.engine = Engine(self.assets, self.store.root, self.root / "consumer-state", self.digest,
                             self.key, clock=lambda: self.time)

    def verified_export(self):
        return verify_export(self.engine.export(), self.key, self.digest, self.engine.checkpoint())

    def test_consumer_reads_admitted_bytes_and_receipt(self):
        result = self.consume()
        self.assertEqual(result["data"], decode(self.payload))
        self.assertEqual(result["content_sha256"], sha256(self.payload))
        self.assertEqual(result["size_bytes"], len(self.payload))
        receipt = self.engine.receipt(result["admission"]["receipt_sha256"])
        self.assertEqual(receipt["facts"]["observations"][0]["sha256"], result["content_sha256"])
        self.assertEqual(self.engine.checkpoint()["head"], result["admission"]["audit_head"])
        self.assertEqual(self.verified_export()["authorized_snapshots"], 1)

    def test_path_changed_after_capture_cannot_change_consumed_bytes(self):
        token = self.token()
        calls = [0]
        replacement = b'{"producer":"changed-after-capture"}'
        def clock():
            calls[0] += 1
            if calls[0] == 2:  # The artifact has already been read and hashed.
                (self.assets / "evidence.json").write_bytes(replacement)
            return self.time
        self.engine.clock = clock
        result = self.consume(token)
        self.assertEqual(result["data"], decode(self.payload))
        self.assertEqual((self.assets / "evidence.json").read_bytes(), replacement)
        self.assertEqual(result["content_sha256"], sha256(self.payload))
        self.assertEqual(self.verified_export()["authorized_snapshots"], 1)

    def test_changed_asset_returns_no_snapshot(self):
        token = self.token()
        (self.assets / "evidence.json").write_bytes(b"changed before capture")
        with self.assertRaisesRegex(Rejected, "artifact_not_admitted"):
            self.engine.admit_bytes(self.raw(), token)
        self.assertEqual(self.verified_export()["authorized_snapshots"], 0)

    def test_changed_canary_returns_no_snapshot(self):
        self.alter()
        with self.assertRaisesRegex(Rejected, "artifact_not_admitted"):
            self.consume()
        self.assertEqual(self.verified_export()["authorized_snapshots"], 0)

    def test_symlink_target_never_reaches_consumer(self):
        (self.assets / "outside.txt").write_text("unapproved data")
        (self.assets / "evidence.json").unlink()
        (self.assets / "evidence.json").symlink_to(self.assets / "outside.txt")
        with self.assertRaisesRegex(Rejected, "artifact_not_admitted"):
            self.consume()

    def test_consumption_is_still_single_use(self):
        token = self.token()
        self.consume(token)
        with self.assertRaisesRegex(Rejected, "invalid_token"):
            self.consume(token, "again")

    def test_quota_denies_without_an_extra_snapshot(self):
        self.replace_baseline(self.payload, rate_limit=1)
        self.consume(request_id="first")
        with self.assertRaisesRegex(Rejected, "artifact_not_admitted"):
            self.consume(request_id="second")
        self.assertEqual(self.verified_export()["authorized_snapshots"], 1)

    def test_json_parse_failure_does_not_claim_delivery(self):
        self.replace_baseline(b"not valid json")
        with self.assertRaisesRegex(Rejected, "invalid_json"):
            self.consume()
        # Authorization happened, parsing did not: the audit event does not claim delivery.
        self.assertEqual(self.verified_export()["authorized_snapshots"], 1)

    def test_json_consumer_has_its_own_size_bound(self):
        self.replace_baseline(b" " * (1024 * 1024) + b"{}")
        with self.assertRaisesRegex(Rejected, "input_size"):
            self.consume()

    def test_snapshot_audit_failure_rolls_back_token_and_decision(self):
        token = self.token()
        with self.engine.state.transaction() as db:
            db.execute('''CREATE TRIGGER snapshot_failure BEFORE INSERT ON audit
                WHEN instr(NEW.payload, '"kind":"snapshot_authorized"') > 0
                BEGIN SELECT RAISE(ABORT, 'snapshot audit refused'); END''')
        with self.assertRaises(sqlite3.IntegrityError):
            self.consume(token)
        with self.engine.state.transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM requests").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT sum(consumed) FROM tokens").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM audit").fetchone()[0], 1)
            db.execute("DROP TRIGGER snapshot_failure")
        self.assertEqual(self.consume(token)["data"], decode(self.payload))

    def test_commit_failure_cannot_release_payload(self):
        token = self.token()
        with self.engine.state.transaction() as db:
            db.execute("CREATE TABLE parent_fault(id INTEGER PRIMARY KEY)")
            db.execute("CREATE TABLE child_fault(id INTEGER REFERENCES parent_fault(id) DEFERRABLE INITIALLY DEFERRED)")
            db.execute('''CREATE TRIGGER commit_failure AFTER INSERT ON audit
                WHEN instr(NEW.payload, '"kind":"snapshot_authorized"') > 0
                BEGIN INSERT INTO child_fault VALUES(999); END''')
        with self.assertRaises(sqlite3.IntegrityError):
            self.engine.admit_bytes(self.raw(), token)
        with self.engine.state.transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM child_fault").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT sum(consumed) FROM tokens").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM audit").fetchone()[0], 1)
            db.execute("DROP TRIGGER commit_failure")
        self.assertEqual(self.engine.admit_bytes(self.raw(), token)[1], self.payload)

    def test_concurrent_token_has_one_payload_recipient(self):
        token = self.token()
        def worker(i):
            try:
                return self.engine.admit_bytes(self.raw(f"concurrent-{i}"), token)[1]
            except Rejected:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(worker, range(16)))
        self.assertEqual(sum(item is not None for item in results), 1)
        self.assertIn(self.payload, results)
        self.assertEqual(self.verified_export()["authorized_snapshots"], 1)

    def test_stale_snapshot_returns_no_payload(self):
        token = self.token()
        times = iter([1000, 1000, 1000, 1006])
        self.engine.clock = lambda: next(times)
        with self.assertRaisesRegex(Rejected, "artifact_not_admitted"):
            self.consume(token)
        self.assertEqual(self.verified_export()["authorized_snapshots"], 0)

    def test_raw_content_is_not_copied_to_audit(self):
        marker = b"private-consumer-content-7812"
        self.replace_baseline(b'{"value":"' + marker + b'"}')
        self.consume()
        self.assertNotIn(marker, self.engine.export())

    def test_web_inspection_does_not_deliver_content(self):
        raw = self.raw()
        env = {"PATH_INFO": "/v1/inspect", "REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
               "CONTENT_LENGTH": str(len(raw)), "HTTP_AUTHORIZATION": "Bearer " + self.token(),
               "wsgi.input": io.BytesIO(raw)}
        status = []
        body = b"".join(Application(self.engine)(env, lambda s, h: status.append(s)))
        self.assertEqual(status, ["200 OK"])
        self.assertNotIn("data", decode(body))
        self.assertEqual(self.verified_export()["authorized_snapshots"], 0)

    def test_cli_consumes_through_admission(self):
        # The CLI uses the real clock; issue its token with that same clock.
        self.engine = Engine(self.assets, self.store.root, self.root / "state", self.digest, self.key)
        token = self.token()
        create_local(self.root, "ledger.key", self.key)
        args = [sys.executable, "-B", "-m", "nqc_defense", "--assets", str(self.assets), "--configs", str(self.store.root),
                "--state", str(self.root / "state"), "--policy", self.digest, "--key-file", str(self.root / "ledger.key"), "read-json"]
        envelope = canonical({"token": token, "request": decode(self.raw())})
        result = subprocess.run(args, input=envelope, check=True, capture_output=True)
        self.assertEqual(decode(result.stdout)["data"], decode(self.payload))

    def test_actual_nqc_manifest_can_be_consumed(self):
        repository = Path(__file__).resolve().parents[3]
        source = (repository / "migration/source-manifest.json").read_bytes()
        self.replace_baseline(source)
        result = self.consume()
        self.assertEqual(result["data"]["schema"], "nqc-isolated-import-v1")
        self.assertEqual(len(result["data"]["files"]), 637)
        self.assertEqual(result["content_sha256"], sha256(source))

    def test_verifier_rejects_snapshot_bound_to_another_receipt(self):
        self.consume()
        checkpoint = {}
        def mutate(audit):
            row = audit["records"][-1]
            event = decode(row["payload"].encode())
            event["receipt_sha256"] = "f" * 64
            row["payload"] = canonical(event).decode()
            row["mac"] = mac(self.key, row["sequence"], row["previous"], row["payload"])
            checkpoint.update(sequence=row["sequence"], head=row["mac"])
            audit["checkpoint"] = checkpoint
        tampered = rewrite_export(self.engine.export(), mutate)
        with self.assertRaisesRegex(Rejected, "snapshot_receipt_binding"):
            verify_export(tampered, self.key, self.digest, checkpoint)

    def test_verifier_rejects_snapshot_hash_not_in_evidence(self):
        self.consume()
        checkpoint = {}
        def mutate(audit):
            row = audit["records"][-1]
            event = decode(row["payload"].encode())
            event["sha256"] = "0" * 64
            row["payload"] = canonical(event).decode()
            row["mac"] = mac(self.key, row["sequence"], row["previous"], row["payload"])
            checkpoint.update(sequence=row["sequence"], head=row["mac"])
            audit["checkpoint"] = checkpoint
        tampered = rewrite_export(self.engine.export(), mutate)
        with self.assertRaisesRegex(Rejected, "snapshot_content_binding"):
            verify_export(tampered, self.key, self.digest, checkpoint)


if __name__ == "__main__":
    unittest.main()
