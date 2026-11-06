import concurrent.futures
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from wsgiref.simple_server import make_server, WSGIRequestHandler

from nqc_defense import canary
from nqc_defense.audit import Ledger
from nqc_defense.build import archive, verify_archive
from nqc_defense.codec import Rejected, canonical, decode, response
from nqc_defense.config import ConfigStore
from nqc_defense.engine import Engine
from nqc_defense.enroll import enroll
from nqc_defense.integration import verify_nqc
from nqc_defense.files import create_local, read_local, sha256
from nqc_defense.web import Application, security_headers


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        (self.assets / "canaries").mkdir()
        self.payload = b'{"producer":"nqc-local-test","observations":3}\n'
        (self.assets / "evidence.json").write_bytes(self.payload)
        self.canary = canary.seed(self.assets, "canaries/guard.txt")
        self.canary_bytes = (self.assets / self.canary["path"]).read_bytes()
        self.policy = {"schema": "nqc-defense-policy-v1", "rate_limit": 100,
                       "rate_window_seconds": 60, "token_ttl_seconds": 120,
                       "assets": [{"id": "nqc-evidence", "path": "evidence.json",
                                   "sha256": sha256(self.payload), "canaries": [self.canary]}]}
        self.store = ConfigStore(self.root / "configs")
        self.digest = self.store.put(canonical(self.policy))
        self.key = secrets.token_bytes(32)
        self.time = 1000
        self.engine = self.open()

    def open(self, checkpoint=None, key=None):
        return Engine(self.assets, self.store.root, self.root / "state", self.digest,
                      key or self.key, clock=lambda: self.time, checkpoint=checkpoint)

    def token(self, subject="operator"):
        return self.engine.issue(subject, "nqc-evidence")

    def send(self, token=None, request_id="request-1", engine=None):
        return (engine or self.engine).process(
            canonical({"request_id": request_id, "asset": "nqc-evidence"}), token or self.token())

    def alter(self):
        (self.assets / self.canary["path"]).write_bytes(b"modified real local file")


class AdmissionTests(Fixture):
    def test_integrated_admit(self):
        result = self.send()
        self.assertEqual(result["decision"], "admit")
        self.assertEqual(result["reasons"], [])
        self.assertEqual(self.engine.checkpoint(), {"sequence": 2, "head": result["audit_head"]})

    def test_single_use_token(self):
        token = self.token()
        self.send(token)
        with self.assertRaises(Rejected):
            self.send(token, "request-2")

    def test_one_winner_under_concurrency(self):
        token = self.token()
        def worker(n):
            try:
                return self.send(token, "parallel-" + str(n))["decision"]
            except Rejected:
                return "rejected"
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(worker, range(24)))
        self.assertEqual(results.count("admit"), 1)
        self.assertEqual(results.count("rejected"), 23)
        self.assertEqual(self.engine.checkpoint()["sequence"], 2)

    def test_replay_id_with_new_token_denied(self):
        self.send()
        result = self.send()
        self.assertEqual(result["reasons"], ["duplicate_request"])

    def test_expiry_boundary(self):
        token = self.token()
        self.time += 120
        with self.assertRaises(Rejected):
            self.send(token)

    def test_before_expiry(self):
        token = self.token()
        self.time += 119
        self.assertEqual(self.send(token)["decision"], "admit")

    def test_clock_before_issuance_rejected(self):
        token = self.token()
        self.time -= 1
        with self.assertRaises(Rejected):
            self.send(token)

    def test_other_asset_cannot_consume_token(self):
        token = self.token()
        with self.assertRaises(Rejected):
            self.engine.process(canonical({"request_id": "r", "asset": "unlisted"}), token)
        self.assertEqual(self.send(token)["decision"], "admit")

    def test_canary_change_quarantines_and_revokes(self):
        a, b = self.token(), self.token()
        self.alter()
        result = self.send(a)
        self.assertEqual(result["decision"], "quarantined")
        self.assertIn("canary_integrity_changed", result["reasons"])
        with self.assertRaises(Rejected):
            self.send(b, "later")
        with self.assertRaises(Rejected):
            self.token()

    def test_asset_change_quarantines(self):
        (self.assets / "evidence.json").write_bytes(b"altered")
        self.assertIn("asset_integrity_changed", self.send()["reasons"])

    def test_missing_canary_quarantines(self):
        (self.assets / self.canary["path"]).unlink()
        self.assertIn("canary_unavailable", self.send()["reasons"])

    def test_missing_asset_quarantines(self):
        (self.assets / "evidence.json").unlink()
        self.assertIn("asset_unavailable", self.send()["reasons"])

    def test_release_requires_restoration(self):
        self.alter()
        self.send()
        with self.assertRaises(Rejected):
            self.engine.release("nqc-evidence")
        (self.assets / self.canary["path"]).write_bytes(self.canary_bytes)
        self.assertTrue(self.engine.release("nqc-evidence"))
        self.assertFalse(self.engine.release("nqc-evidence"))
        self.assertEqual(self.send(request_id="after-release")["decision"], "admit")

    def test_quarantine_survives_restart(self):
        self.alter()
        self.send()
        restarted = self.open()
        with self.assertRaises(Rejected):
            restarted.issue("operator", "nqc-evidence")

    def test_token_consumption_survives_restart(self):
        token = self.token()
        self.send(token)
        with self.assertRaises(Rejected):
            self.send(token, "again", self.open())

    def test_token_never_in_database_bytes(self):
        token = self.token()
        self.send(token)
        self.assertNotIn(token.encode(), self.engine.state.path.read_bytes())

    def test_bearer_not_in_audit_export(self):
        token = self.token()
        self.send(token)
        self.assertNotIn(token.encode(), self.engine.export())

    def test_config_mutation_stops_existing_engine(self):
        token = self.token()
        (self.store.root / (self.digest + ".json")).write_bytes(b"{}")
        with self.assertRaises(Rejected):
            self.send(token)

    def test_audit_change_blocks_decisions(self):
        token = self.token()
        with self.engine.state.transaction() as db:
            db.execute("UPDATE audit SET payload='{}' WHERE seq=1")
        with self.assertRaises(Rejected):
            self.send(token)

    def test_audit_failure_rolls_back_token_use(self):
        token = self.token()
        # Real SQLite trigger causes the audit write to fail after token consumption.
        with self.engine.state.transaction() as db:
            db.execute("CREATE TRIGGER deny_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT, 'write refused'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.send(token)
        with self.engine.state.transaction() as db:
            db.execute("DROP TRIGGER deny_audit")
        self.assertEqual(self.send(token)["decision"], "admit")

    def test_wrong_key_rejected(self):
        with self.assertRaises(Rejected):
            self.open(key=secrets.token_bytes(32))

    def test_truncation_requires_external_checkpoint(self):
        self.send()
        checkpoint = self.engine.checkpoint()
        with self.engine.state.transaction() as db:
            db.execute("DELETE FROM audit WHERE seq=2")
        # A valid prefix alone does not prove there was no truncation.
        self.assertEqual(self.open().checkpoint()["sequence"], 1)
        with self.assertRaises(Rejected):
            self.open(checkpoint=checkpoint)

    def test_internal_audit_gap_rejected(self):
        self.send()
        with self.engine.state.transaction() as db:
            db.execute("DELETE FROM audit WHERE seq=1")
        with self.assertRaises(Rejected):
            self.engine.checkpoint()

    def test_repeat_export_is_byte_identical(self):
        self.send()
        first, second = self.engine.export(), self.engine.export()
        self.assertEqual(first, second)
        self.assertEqual(set(verify_archive(first)), {"audit.json", "policy.sha3", "policy.json"})


class RateTests(Fixture):
    def setUp(self):
        super().setUp()
        self.policy["rate_limit"] = 3
        self.digest = self.store.put(canonical(self.policy))
        self.engine = Engine(self.assets, self.store.root, self.root / "rate-state", self.digest,
                             self.key, clock=lambda: self.time)

    def test_limit_and_window_boundary(self):
        for i in range(3):
            self.assertEqual(self.send(request_id=f"r{i}")["decision"], "admit")
        self.assertEqual(self.send(request_id="r3")["reasons"], ["rate_limited"])
        self.time += 59
        self.assertEqual(self.send(request_id="r4")["decision"], "denied")
        self.time += 1
        self.assertEqual(self.send(request_id="r5")["decision"], "admit")

    def test_concurrent_limit_is_exact(self):
        tokens = [self.token() for _ in range(12)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(lambda pair: self.send(pair[1], f"rate-{pair[0]}")["decision"], enumerate(tokens)))
        self.assertEqual(outcomes.count("admit"), 3)
        self.assertEqual(outcomes.count("denied"), 9)

    def test_independent_subjects(self):
        for i in range(3):
            self.send(request_id=f"r{i}")
        self.assertEqual(self.send(self.token("second"), "second-r")["decision"], "admit")

    def test_backward_clock_cannot_reset_bucket(self):
        self.send(request_id="first")
        self.time -= 1
        with self.assertRaisesRegex(Rejected, "clock_regressed"):
            self.send(request_id="second")

    def test_restart_preserves_quota(self):
        for i in range(3):
            self.send(request_id=f"quota-{i}")
        self.engine = Engine(self.assets, self.store.root, self.root / "rate-state", self.digest,
                             self.key, clock=lambda: self.time)
        self.assertEqual(self.send(request_id="after-restart")["reasons"], ["rate_limited"])


class FileTests(Fixture):
    def test_leaf_symlink_rejected(self):
        path = self.assets / "evidence.json"
        path.unlink()
        path.symlink_to("/etc/passwd")
        with self.assertRaises(Rejected):
            read_local(self.assets, "evidence.json")

    def test_parent_symlink_rejected(self):
        (self.assets / "link").symlink_to(self.root)
        with self.assertRaises(Rejected):
            read_local(self.assets, "link/assets/evidence.json")

    def test_traversal_variants_rejected(self):
        for name in ("../evidence.json", "/etc/passwd", "canaries/../evidence.json", "./evidence.json", "canaries//guard.txt", "a\\b", "x\x00y"):
            with self.subTest(name=name), self.assertRaises(Rejected):
                read_local(self.assets, name)

    def test_canary_never_overwrites_file(self):
        with self.assertRaises(FileExistsError):
            canary.seed(self.assets, "evidence.json")
        self.assertEqual((self.assets / "evidence.json").read_bytes(), self.payload)

    def test_fifo_rejected_without_blocking(self):
        os.mkfifo(self.assets / "pipe")
        with self.assertRaises(Rejected):
            read_local(self.assets, "pipe")

    def test_oversized_file_rejected(self):
        with self.assertRaises(Rejected):
            read_local(self.assets, "evidence.json", 8)

    def test_config_dedup(self):
        self.assertEqual(self.digest, self.store.put(canonical(self.policy)))

    def test_policy_change_cannot_reuse_state(self):
        self.policy["rate_limit"] = 9
        other = self.store.put(canonical(self.policy))
        with self.assertRaises(Rejected):
            Engine(self.assets, self.store.root, self.root / "state", other, self.key)

    def test_duplicate_asset_policy_rejected(self):
        self.policy["assets"].append(self.policy["assets"][0])
        with self.assertRaises(Rejected):
            self.store.put(canonical(self.policy))

    def test_shared_canary_path_rejected(self):
        self.policy["assets"][0]["canaries"].append(self.canary)
        with self.assertRaises(Rejected):
            self.store.put(canonical(self.policy))

    def test_public_state_directory_rejected(self):
        public = self.root / "public"
        public.mkdir(mode=0o755)
        with self.assertRaises(Rejected):
            Engine(self.assets, self.store.root, public, self.digest, self.key)

    def test_fifo_database_is_rejected_before_sqlite_open(self):
        private = self.root / "fifo-state"
        private.mkdir(mode=0o700)
        os.mkfifo(private / "state.sqlite3", mode=0o600)
        with self.assertRaisesRegex(Rejected, "database_not_regular"):
            Engine(self.assets, self.store.root, private, self.digest, self.key)


class CodecTests(unittest.TestCase):
    def test_ambiguous_and_invalid_json_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'"\xff"', b'{"a":', b'1.1', b'18446744073709551616'):
            with self.subTest(raw=raw), self.assertRaises(Rejected):
                decode(raw)

    def test_deep_json_rejected(self):
        for depth in (25, 2000):
            with self.assertRaises(Rejected):
                decode(b"[" * depth + b"0" + b"]" * depth)

    def test_excess_nodes_rejected(self):
        with self.assertRaises(Rejected):
            decode(canonical([0] * 4096))

    def test_body_size_limit(self):
        with self.assertRaises(Rejected):
            decode(b" " * 65537)

    def test_response_extra_secret_rejected(self):
        with self.assertRaises(Rejected):
            response({"request_id": "r", "asset": "a", "decision": "admit", "reasons": [], "audit_head": "0" * 64, "token": "secret"})

    def test_canonical_order_independent(self):
        self.assertEqual(canonical({"z": 1, "a": 2}), canonical({"a": 2, "z": 1}))

    def test_archive_order_independent(self):
        self.assertEqual(archive({"b": b"2", "a": b"1"}), archive({"a": b"1", "b": b"2"}))

    def test_archive_corruption_rejected(self):
        data = archive({"data.txt": b"0123456789-UNIQUE"})
        altered = data.replace(b"0123456789-UNIQUE", b"9876543210-UNIQUE")
        with self.assertRaises(Rejected):
            verify_archive(altered)

    def test_archive_traversal_rejected(self):
        with self.assertRaises(Rejected):
            archive({"../a": b"x"})


class EnrollmentTests(Fixture):
    def test_missing_nqc_checkout_is_rejected(self):
        with self.assertRaises(Rejected):
            verify_nqc(self.root)

    def test_changed_nqc_base_is_rejected(self):
        target = self.root / "wrong-repo"
        target.mkdir()
        subprocess.run(["git", "init", str(target)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "-c", "user.name=Local Test", "-c",
                        "user.email=test@example.invalid", "commit", "--allow-empty", "-m", "Local test"],
                       check=True, capture_output=True)
        with self.assertRaisesRegex(Rejected, "nqc_base_changed_requires_review"):
            verify_nqc(target)

    def test_enrollment_links_actual_bytes_to_decision(self):
        before = (self.assets / "evidence.json").read_bytes()
        control = self.root / "enrolled"
        receipt = enroll(self.assets, "evidence.json", "real-artifact", "new-canary", control)
        self.assertEqual(receipt["artifact_sha256"], sha256(before))
        engine = Engine(self.assets, control / "configs", control / "state", receipt["policy_digest"],
                        read_local(control, "ledger.key", 32))
        token = engine.issue("reader", "real-artifact")
        result = engine.process(canonical({"asset": "real-artifact", "request_id": "check"}), token)
        self.assertEqual(result["decision"], "admit")
        self.assertEqual((self.assets / "evidence.json").read_bytes(), before)

    def test_existing_control_is_not_overwritten(self):
        with self.assertRaises(FileExistsError):
            enroll(self.assets, "evidence.json", "artifact", "new-canary", self.store.root)
        self.assertFalse((self.assets / "new-canary").exists())

    def test_existing_canary_is_not_overwritten(self):
        before = (self.assets / "evidence.json").read_bytes()
        with self.assertRaises(FileExistsError):
            enroll(self.assets, "evidence.json", "artifact", self.canary["path"], self.root / "new-state")
        self.assertEqual((self.assets / self.canary["path"]).read_bytes(), self.canary_bytes)
        self.assertEqual((self.assets / "evidence.json").read_bytes(), before)

    def test_missing_artifact_creates_no_control(self):
        with self.assertRaises(Rejected):
            enroll(self.assets, "missing", "artifact", "new-canary", self.root / "new-state")
        self.assertFalse((self.root / "new-state").exists())

    def test_overlap_rejected_before_write(self):
        with self.assertRaises(Rejected):
            enroll(self.assets, "evidence.json", "artifact", "evidence.json", self.root / "new-state")
        self.assertFalse((self.root / "new-state").exists())


class WebTests(Fixture):
    def call(self, token=None, raw=None, **overrides):
        raw = raw if raw is not None else canonical({"request_id": "http-r", "asset": "nqc-evidence"})
        environ = {"PATH_INFO": "/v1/inspect", "REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
                   "CONTENT_LENGTH": str(len(raw)), "HTTP_AUTHORIZATION": "Bearer " + (token or self.token()),
                   "wsgi.input": io.BytesIO(raw), **overrides}
        result = {}
        def start(status, headers):
            result.update(status=status, headers=dict(headers))
        result["body"] = b"".join(Application(self.engine)(environ, start))
        return result

    def test_http_surface_links_engine_and_headers(self):
        result = self.call()
        self.assertEqual(result["status"], "200 OK")
        self.assertEqual(decode(result["body"])["decision"], "admit")
        self.assertIn("nonce-", result["headers"]["Content-Security-Policy"])
        self.assertEqual(result["headers"]["Cache-Control"], "no-store")

    def test_csp_nonce_unique(self):
        policies = [dict(security_headers())["Content-Security-Policy"] for _ in range(1000)]
        self.assertEqual(len(set(policies)), 1000)

    def test_invalid_token_401_without_echo(self):
        result = self.call(token="a" * 64)
        self.assertEqual(result["status"], "401 Unauthorized")
        self.assertNotIn(b"a" * 64, result["body"])

    def test_unknown_fields_rejected(self):
        result = self.call(raw=canonical({"request_id": "r", "asset": "nqc-evidence", "admin": True}))
        self.assertEqual(result["status"], "400 Bad Request")

    def test_duplicate_request_http_409(self):
        self.assertEqual(self.call()["status"], "200 OK")
        self.assertEqual(self.call()["status"], "409 Conflict")

    def test_routes_and_limits(self):
        cases = [({"REQUEST_METHOD": "GET"}, "405"), ({"PATH_INFO": "/issue"}, "404"),
                 ({"CONTENT_TYPE": "text/plain"}, "415"), ({"CONTENT_LENGTH": "65537"}, "413"),
                 ({"CONTENT_LENGTH": "-1"}, "400"), ({"CONTENT_LENGTH": "100"}, "400"),
                 ({"QUERY_STRING": "token=secret"}, "404")]
        for overrides, status in cases:
            with self.subTest(overrides=overrides):
                self.assertTrue(self.call(**overrides)["status"].startswith(status))

    def test_internal_failure_is_503(self):
        token = self.token()
        self.engine.state.path.unlink()
        result = self.call(token=token)
        self.assertEqual(result["status"], "503 Service Unavailable")
        self.assertNotIn(b"sqlite", result["body"])

    def test_real_loopback_http_lifecycle(self):
        class Quiet(WSGIRequestHandler):
            def log_message(self, *args):
                # Silence the standard request logger to avoid bearer-adjacent diagnostics.
                return None
        server = make_server("127.0.0.1", 0, Application(self.engine), handler_class=Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def post(token, rid):
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/v1/inspect",
                    canonical({"request_id": rid, "asset": "nqc-evidence"}),
                    {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(request, timeout=5) as reply:
                        return reply.status, decode(reply.read())
                except urllib.error.HTTPError as reply:
                    return reply.code, decode(reply.read())
            token = self.token()
            self.assertEqual(post(token, "loopback-1")[0], 200)
            self.assertEqual(post(token, "loopback-replay")[0], 401)
            token = self.token()
            self.alter()
            status, body = post(token, "loopback-2")
            self.assertEqual((status, body["decision"]), (423, "quarantined"))
            (self.assets / self.canary["path"]).write_bytes(self.canary_bytes)
            self.engine.release("nqc-evidence")
            self.assertEqual(post(self.token(), "loopback-3")[0], 200)
            verify_archive(self.engine.export())
            self.open(checkpoint=self.engine.checkpoint())
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_cli_inspects_real_files(self):
        keyfile = self.root / "ledger.key"
        create_local(self.root, keyfile.name, self.key)
        base = [sys.executable, "-m", "nqc_defense", "--assets", str(self.assets), "--configs", str(self.store.root),
                "--state", str(self.root / "state"), "--policy", self.digest, "--key-file", str(keyfile)]
        issuance = subprocess.run([*base, "issue", "cli-user", "nqc-evidence"], capture_output=True, check=True)
        token = decode(issuance.stdout)["token"]
        envelope = canonical({"token": token, "request": {"request_id": "cli-r", "asset": "nqc-evidence"}})
        inspection = subprocess.run([*base, "inspect"], input=envelope, capture_output=True, check=True)
        self.assertEqual(decode(inspection.stdout)["decision"], "admit")


if __name__ == "__main__":
    unittest.main()
