import concurrent.futures
import copy
import io
import json
import multiprocessing
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading
import unittest
import zipfile

from test_defense import Fixture
from nqc_defense import canary, receipts
from nqc_defense.build import archive
from nqc_defense.codec import Rejected, canonical, decode
from nqc_defense.config import controls
from nqc_defense.engine import Engine
from nqc_defense.files import sha256
from nqc_defense.files import create_local
from nqc_defense.web import Application
from nqc_defense.audit import mac
from nqc_defense.verify_export import verify as verify_export


def process_in_new_process(args):
    root, digest, key, token, asset = args
    root = Path(root)
    engine = Engine(root / "assets", root / "configs", root / "budget-state", digest, key, clock=lambda: 1000)
    return engine.process(canonical({"request_id": "process-" + asset, "asset": asset}), token)


def rewrite_export(data, update):
    with zipfile.ZipFile(io.BytesIO(data)) as stream:
        entries = {name: stream.read(name) for name in ("audit.json", "policy.json", "policy.sha3")}
    audit = decode(entries["audit.json"], max_bytes=8 * 1024 * 1024, max_nodes=100000)
    update(audit)
    entries["audit.json"] = canonical(audit)
    return archive(entries)


class ReceiptTests(Fixture):
    def recorded(self):
        result = self.send()
        return result, self.engine.receipt(result["receipt_sha256"])

    def test_receipt_binds_real_bytes_policy_and_response(self):
        result, receipt = self.recorded()
        self.assertEqual(receipt["facts"]["observations"][0]["sha256"], sha256(self.payload))
        self.assertEqual(receipt["policy_digest"], self.digest)
        self.assertEqual(receipt["outcome"]["checks"][-1], {"gate": "integrity", "result": "passed"})
        self.assertEqual(receipts.verify(receipt, self.policy, result["receipt_sha256"])["decision"], "admit")

    def test_modified_receipt_rejected_by_anchored_hash(self):
        result, receipt = self.recorded()
        receipt["outcome"]["decision"] = "denied"
        with self.assertRaisesRegex(Rejected, "receipt_integrity"):
            receipts.verify(receipt, self.policy, result["receipt_sha256"])

    def test_recomputed_hash_cannot_hide_wrong_decision(self):
        _, receipt = self.recorded()
        receipt["outcome"]["decision"] = "quarantined"
        with self.assertRaisesRegex(Rejected, "receipt_replay_mismatch"):
            receipts.verify(receipt, self.policy, receipts.digest(receipt))

    def test_other_policy_cannot_verify_receipt(self):
        result, receipt = self.recorded()
        policy = copy.deepcopy(self.policy)
        policy["rate_limit"] += 1
        with self.assertRaisesRegex(Rejected, "receipt_policy_binding"):
            receipts.verify(receipt, policy, result["receipt_sha256"])

    def test_omitted_canary_is_not_a_clean_scan(self):
        _, receipt = self.recorded()
        receipt["facts"]["observations"].pop()
        with self.assertRaisesRegex(Rejected, "evidence_membership"):
            receipts.verify(receipt, self.policy, receipts.digest(receipt))

    def test_evidence_path_substitution_is_rejected(self):
        _, receipt = self.recorded()
        receipt["facts"]["observations"][1]["path"] = "elsewhere"
        with self.assertRaisesRegex(Rejected, "evidence_membership"):
            receipts.verify(receipt, self.policy, receipts.digest(receipt))

    def test_replay_denial_has_no_fabricated_observations(self):
        self.send()
        result = self.send()
        receipt = self.engine.receipt(result["receipt_sha256"])
        self.assertEqual(receipt["facts"]["observations"], [])
        self.assertEqual(receipt["outcome"]["checks"][-1], {"gate": "replay", "result": "failed"})
        self.assertEqual(receipts.verify(receipt, self.policy, result["receipt_sha256"])["decision"], "denied")

    def test_conflicting_error_and_digest_rejected(self):
        _, receipt = self.recorded()
        receipt["facts"]["observations"][0]["error"] = "file_unavailable"
        with self.assertRaisesRegex(Rejected, "evidence_error"):
            receipts.verify(receipt, self.policy, receipts.digest(receipt))

    def test_unknown_receipt_not_found(self):
        with self.assertRaisesRegex(Rejected, "receipt_not_found"):
            self.engine.receipt("f" * 64)

    def test_legacy_policy_defaults_are_explicit(self):
        before = canonical(self.policy)
        self.assertEqual(controls(self.policy), {"evidence_max_age_seconds": 5, "max_quarantined_assets": 1})
        self.assertEqual(canonical(self.policy), before)


class FreshnessTests(Fixture):
    def timed_request(self, samples):
        token = self.token()
        iterator = iter(samples)
        self.engine.clock = lambda: next(iterator)
        return self.send(token)

    def test_age_boundary_is_inclusive(self):
        result = self.timed_request([1000, 1002, 1004, 1005])
        self.assertEqual(result["decision"], "admit")

    def test_expired_evidence_denied_without_quarantine(self):
        result = self.timed_request([1000, 1002, 1005, 1006])
        self.assertEqual(result["reasons"], ["evidence_expired"])
        with self.engine.state.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM quarantine").fetchone()[0], 0)
        receipt = self.engine.receipt(result["receipt_sha256"])
        self.assertEqual(receipt["outcome"]["checks"][-1]["gate"], "freshness")

    def test_regression_during_observation_denied(self):
        result = self.timed_request([1000, 1002, 1001, 1003])
        self.assertEqual(result["reasons"], ["clock_regressed"])

    def test_regression_at_decision_denied(self):
        result = self.timed_request([1000, 1000, 1000, 999])
        self.assertEqual(result["decision"], "denied")
        self.assertEqual(result["reasons"], ["clock_regressed"])

    def test_clock_floor_survives_restart(self):
        self.time = 2000
        self.token()
        self.time = 1999
        with self.assertRaisesRegex(Rejected, "clock_regressed"):
            self.open().issue("operator", "nqc-evidence")

    def test_token_expires_while_waiting_on_real_sqlite_lock(self):
        token = self.token()
        entered, sampled = threading.Event(), threading.Event()
        def clock():
            sampled.set()
            return self.time
        self.engine.clock = clock
        def worker():
            entered.set()
            return self.send(token)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with self.engine.state.transaction():
                future = pool.submit(worker)
                self.assertTrue(entered.wait(2))
                sampled_while_locked = sampled.wait(0.15)
                self.time += self.policy["token_ttl_seconds"]
            self.assertFalse(sampled_while_locked, "clock was sampled before acquiring SQLite's write lock")
            with self.assertRaisesRegex(Rejected, "invalid_token"):
                future.result(timeout=5)

    def test_release_rechecks_freshness(self):
        self.alter()
        self.send()
        (self.assets / self.canary["path"]).write_bytes(self.canary_bytes)
        samples = iter([1000, 1002, 1004, 1006])
        self.engine.clock = lambda: next(samples)
        with self.assertRaisesRegex(Rejected, "evidence_expired"):
            self.engine.release("nqc-evidence")
        with self.engine.state.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM quarantine").fetchone()[0], 1)

    def test_invalid_v2_bounds_rejected(self):
        for changes in ({"evidence_max_age_seconds": -1}, {"max_quarantined_assets": 2}, {"max_quarantined_assets": True}):
            policy = {**self.policy, "schema": "nqc-defense-policy-v2", "evidence_max_age_seconds": 5,
                      "max_quarantined_assets": 1, **changes}
            with self.subTest(changes=changes), self.assertRaises(Rejected):
                self.store.put(canonical(policy))


class BudgetTests(Fixture):
    def setUp(self):
        super().setUp()
        self.policy.update(schema="nqc-defense-policy-v2", evidence_max_age_seconds=5, max_quarantined_assets=2)
        for n in range(1, 7):
            data = f"real local asset {n}".encode()
            (self.assets / f"asset{n}").write_bytes(data)
            marker = canary.seed(self.assets, f"canaries/guard{n}")
            self.policy["assets"].append({"id": f"asset{n}", "path": f"asset{n}", "sha256": sha256(data), "canaries": [marker]})
        self.digest = self.store.put(canonical(self.policy))
        self.engine = Engine(self.assets, self.store.root, self.root / "budget-state", self.digest, self.key, clock=lambda: self.time)

    def act(self, asset, rid=None):
        token = self.engine.issue("operator", asset)
        return self.engine.process(canonical({"asset": asset, "request_id": rid or "r-" + asset}), token)

    def corrupt(self, asset):
        entry = next(x for x in self.policy["assets"] if x["id"] == asset)
        (self.assets / entry["path"]).write_bytes(b"changed")

    def test_budget_does_not_admit_suspect_or_block_healthy_asset(self):
        for asset in ("asset1", "asset2", "asset3"):
            self.corrupt(asset)
        self.assertEqual(self.act("asset1")["decision"], "quarantined")
        self.assertEqual(self.act("asset2")["decision"], "quarantined")
        result = self.act("asset3")
        self.assertEqual(result["decision"], "denied")
        self.assertIn("quarantine_budget_exhausted", result["reasons"])
        self.assertEqual(self.act("asset6")["decision"], "admit")
        with self.engine.state.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM quarantine").fetchone()[0], 2)

    def test_separate_processes_cannot_exceed_budget(self):
        arguments = []
        for asset in ("asset1", "asset2", "asset3", "asset4", "asset5", "asset6"):
            self.corrupt(asset)
            arguments.append((str(self.root), self.digest, self.key, self.engine.issue("operator", asset), asset))
        with concurrent.futures.ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
            outcomes = list(pool.map(process_in_new_process, arguments))
        self.assertEqual(sum(x["decision"] == "quarantined" for x in outcomes), 2)
        self.assertEqual(sum(x["decision"] == "denied" for x in outcomes), 4)
        for outcome in outcomes:
            self.engine.receipt(outcome["receipt_sha256"])
        with self.engine.state.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM quarantine").fetchone()[0], 2)
        self.assertEqual(self.engine.checkpoint()["sequence"], 12)

    def test_release_frees_one_budget_slot(self):
        for asset in ("asset1", "asset2", "asset3"):
            self.corrupt(asset)
        self.act("asset1")
        self.act("asset2")
        self.assertEqual(self.act("asset3")["decision"], "denied")
        (self.assets / "asset1").write_bytes(b"real local asset 1")
        self.assertTrue(self.engine.release("asset1"))
        self.assertEqual(self.act("asset3", "retry-asset3")["decision"], "quarantined")

    def test_zero_budget_keeps_corrupt_request_denied(self):
        self.policy["max_quarantined_assets"] = 0
        digest = self.store.put(canonical(self.policy))
        self.engine = Engine(self.assets, self.store.root, self.root / "zero-state", digest, self.key, clock=lambda: self.time)
        self.corrupt("asset1")
        self.assertEqual(self.act("asset1")["decision"], "denied")
        self.assertEqual(self.act("asset2")["decision"], "admit")

    def test_audit_failure_rolls_back_quarantine_and_revocation(self):
        self.corrupt("asset1")
        first = self.engine.issue("operator", "asset1")
        second = self.engine.issue("operator", "asset1")
        with self.engine.state.transaction() as db:
            db.execute("CREATE TRIGGER audit_failure BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT, 'failure'); END")
        raw = canonical({"asset": "asset1", "request_id": "transaction-failure"})
        with self.assertRaises(sqlite3.IntegrityError):
            self.engine.process(raw, first)
        with self.engine.state.transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM quarantine").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT sum(consumed) FROM tokens").fetchone()[0], 0)
            db.execute("DROP TRIGGER audit_failure")
        self.assertEqual(self.engine.process(raw, first)["decision"], "quarantined")
        with self.assertRaises(Rejected):
            self.engine.process(raw, second)


class ExportTests(Fixture):
    def test_authenticated_but_incorrect_decision_fails_replay(self):
        self.send()
        checkpoint = {}
        def mutate(audit):
            row = audit["records"][-1]
            event = decode(row["payload"].encode())
            event["receipt"]["outcome"]["decision"] = "quarantined"
            event["receipt_sha256"] = receipts.digest(event["receipt"])
            event["decision"] = "quarantined"
            row["payload"] = canonical(event).decode()
            row["mac"] = mac(self.key, row["sequence"], row["previous"], row["payload"])
            checkpoint.update(sequence=row["sequence"], head=row["mac"])
            audit["checkpoint"] = checkpoint
        changed = rewrite_export(self.engine.export(), mutate)
        with self.assertRaisesRegex(Rejected, "receipt_replay_mismatch"):
            verify_export(changed, self.key, self.digest, checkpoint)

    def test_export_replays_all_decisions(self):
        self.send(request_id="admitted")
        self.alter()
        self.send(request_id="quarantined")
        result = verify_export(self.engine.export(), self.key, self.digest, self.engine.checkpoint())
        self.assertTrue(result["verified"])
        self.assertEqual(result["replayed_decisions"], 2)
        self.assertEqual(result["legacy_unreplayed_decisions"], 0)

    def test_wrong_key_rejected(self):
        self.send()
        with self.assertRaisesRegex(Rejected, "audit_integrity"):
            verify_export(self.engine.export(), secrets.token_bytes(32), self.digest, self.engine.checkpoint())

    def test_wrong_external_policy_digest_rejected(self):
        self.send()
        with self.assertRaisesRegex(Rejected, "export_policy_binding"):
            verify_export(self.engine.export(), self.key, "f" * 64, self.engine.checkpoint())

    def test_edit_with_rebuilt_zip_manifest_still_fails_authentication(self):
        self.send()
        def mutate(audit):
            event = decode(audit["records"][-1]["payload"].encode())
            event["decision"] = "denied"
            audit["records"][-1]["payload"] = canonical(event).decode()
        tampered = rewrite_export(self.engine.export(), mutate)
        with self.assertRaisesRegex(Rejected, "audit_integrity"):
            verify_export(tampered, self.key, self.digest, self.engine.checkpoint())

    def test_rebuilt_truncated_archive_fails_external_checkpoint(self):
        self.send()
        def truncate(audit):
            audit["records"].pop()
            row = audit["records"][-1]
            audit["checkpoint"] = {"sequence": row["sequence"], "head": row["mac"]}
        tampered = rewrite_export(self.engine.export(), truncate)
        with self.assertRaisesRegex(Rejected, "audit_checkpoint_mismatch"):
            verify_export(tampered, self.key, self.digest, self.engine.checkpoint())

    def test_empty_export_requires_genesis_checkpoint(self):
        result = verify_export(self.engine.export(), self.key, self.digest, self.engine.checkpoint())
        self.assertEqual(result["replayed_decisions"], 0)
        self.assertEqual(result["checkpoint"]["sequence"], 0)


class ControlInterfaceTests(Fixture):
    def call(self, token):
        raw = canonical({"asset": "nqc-evidence", "request_id": "http-control"})
        environ = {"PATH_INFO": "/v1/inspect", "REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
                   "CONTENT_LENGTH": str(len(raw)), "HTTP_AUTHORIZATION": "Bearer " + token,
                   "wsgi.input": io.BytesIO(raw)}
        output = {}
        def start(status, headers):
            output.update(status=status, headers=dict(headers))
        output["body"] = decode(b"".join(Application(self.engine)(environ, start)))
        return output

    def test_stale_evidence_is_http_503_with_receipt(self):
        token = self.token()
        samples = iter([1000, 1000, 1000, 1006])
        self.engine.clock = lambda: next(samples)
        result = self.call(token)
        self.assertEqual(result["status"], "503 Service Unavailable")
        self.assertEqual(result["body"]["reasons"], ["evidence_expired"])
        self.assertEqual(self.engine.receipt(result["body"]["receipt_sha256"])["outcome"]["decision"], "denied")

    def test_clock_failure_before_token_use_is_http_503(self):
        token = self.token()
        self.time -= 1
        self.assertEqual(self.call(token)["status"], "503 Service Unavailable")

    def test_budget_denial_is_http_conflict(self):
        policy = {**self.policy, "schema": "nqc-defense-policy-v2", "evidence_max_age_seconds": 5,
                  "max_quarantined_assets": 0}
        digest = self.store.put(canonical(policy))
        self.engine = Engine(self.assets, self.store.root, self.root / "http-state", digest, self.key, clock=lambda: self.time)
        token = self.token()
        self.alter()
        result = self.call(token)
        self.assertEqual(result["status"], "409 Conflict")
        self.assertEqual(result["body"]["decision"], "denied")
        self.assertIn("quarantine_budget_exhausted", result["body"]["reasons"])

    def test_local_receipt_and_export_verifier_cli(self):
        result = self.send()
        create_local(self.root, "ledger.key", self.key)
        create_local(self.root, "checkpoint.json", canonical(self.engine.checkpoint()))
        create_local(self.root, "audit.zip", self.engine.export())
        common = [sys.executable, "-B", "-m", "nqc_defense", "--assets", str(self.assets),
                  "--configs", str(self.store.root), "--state", str(self.root / "state"),
                  "--policy", self.digest, "--key-file", str(self.root / "ledger.key")]
        receipt = subprocess.run([*common, "receipt", result["receipt_sha256"]], check=True, capture_output=True)
        self.assertEqual(decode(receipt.stdout)["outcome"]["decision"], "admit")
        script = Path(__file__).resolve().parents[1] / "tools/verify_export.py"
        checked = subprocess.run([sys.executable, "-B", str(script), str(self.root / "audit.zip"),
                                  "--key-file", str(self.root / "ledger.key"), "--policy-digest", self.digest,
                                  "--checkpoint", str(self.root / "checkpoint.json")], check=True, capture_output=True)
        self.assertTrue(decode(checked.stdout)["verified"])


if __name__ == "__main__":
    unittest.main()
