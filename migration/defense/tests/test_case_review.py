from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.case_evidence import capture_case
from nqc_defense.case_review import CaseReview, ORIGIN
from nqc_defense.codec import Rejected, canonical
from nqc_defense.files import sha256
from nqc_defense.operations import OperationsStore
from nqc_defense.review_policy import ReviewPolicy, read_credential


class CaseReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.log = self.root / "auth.jsonl"
        self.log.write_bytes(b"".join(canonical({"schema":"nqc-auth-log-v1","time_ns":i*1000000000,
            "outcome":"failure","principal":"alice","remote_address":"192.0.2.1"}) + b"\n" for i in range(3)))
        self.store = OperationsStore.create(self.root / "ops")
        self.monitor = AuthLogMonitor.register(self.store, "auth", "tenant", "host", self.root, self.log.name, 3, 60)
        self.monitor.poll(); self.case = self.store.cases("tenant", "host")[0]
        self.case_digest = sha256(canonical(self.case)); self.bundle_path = self.root / "evidence.json"
        receipt = capture_case(self.store, "tenant", "host", self.case["case_id"], self.case_digest, self.monitor.digest,
                               [{"generation":0,"name":self.log.name}], self.bundle_path)
        self.bundle = self.bundle_path.read_bytes(); self.bundle_digest = receipt["bundle_digest"]
        self.grants = [{"actor":actor,"tenant":"tenant","assets":["host"],"permissions":permissions}
            for actor,permissions in [("ana",["read","start","note","assess","close","reopen"]),
                                      ("boris",["read","close","reopen"]),("reader",["read"])]]
        self.policy = ReviewPolicy.create(self.root / "policy", self.grants)
        self.tokens = {g["actor"]:read_credential(self.policy.root / "credentials" / (g["actor"] + ".key")) for g in self.grants}
        self.review = CaseReview(self.store, self.policy); self.head = dict(ORIGIN); self.serial = 0

    def apply(self, action="start", actor="ana", verdict=None, **changes):
        self.serial += 1
        args = dict(actor=actor,credential=self.tokens[actor],tenant="tenant",asset="host",case_id=self.case["case_id"],
                    action=action,reason="Revisión local documentada",request_id=f"request_{self.serial}",expected=self.head,
                    bundle=self.bundle,bundle_digest=self.bundle_digest,case_digest=self.case_digest,
                    config_digest=self.monitor.digest,verdict=verdict)
        args.update(changes); result = self.review.apply(**args); self.head = result["checkpoint"]
        return result

    def view(self, **changes):
        args = dict(actor="reader",credential=self.tokens["reader"],tenant="tenant",asset="host",case_id=self.case["case_id"])
        args.update(changes); return self.review.view(**args)

    def test_full_review_benign_confirmation_and_reopen_preserve_history(self):
        self.assertEqual(self.view()["review"]["stage"], "unreviewed")
        self.apply(); self.apply("note"); self.apply("assess", verdict="benign")
        self.assertEqual(self.apply("close", actor="boris")["review"]["stage"], "closed")
        self.assertEqual(self.view()["detection_status"], "open")
        self.assertEqual(self.apply("reopen", actor="boris")["review"]["stage"], "investigating")
        self.assertEqual(len(self.view()["history"]), 5)
        self.assertIsNone(self.view()["review"]["assessment"])

    def test_reopen_process_retains_authenticated_state(self):
        self.apply(); self.apply("note")
        reopened = CaseReview(OperationsStore(self.store.root), ReviewPolicy(self.policy.root, self.policy.digest))
        result = reopened.view("reader", self.tokens["reader"], "tenant", "host", self.case["case_id"], expected=self.head)
        self.assertEqual(result["review"]["notes_count"], 1)

    def test_wrong_credential_rejected_before_bundle_processing(self):
        with self.assertRaisesRegex(Rejected, "review_unauthorized"):
            self.apply(credential=b"x" * 32, bundle=b"malformed")
        self.assertEqual(self.view()["checkpoint"], ORIGIN)

    def test_reader_cannot_start_review(self):
        with self.assertRaisesRegex(Rejected, "review_unauthorized"):
            self.apply(actor="reader")

    def test_unknown_actor_cannot_read(self):
        with self.assertRaisesRegex(Rejected, "review_unauthorized"):
            self.view(actor="unknown")

    def test_cross_tenant_and_asset_permissions_rejected(self):
        for change in ({"tenant":"other"},{"asset":"other"}):
            with self.assertRaisesRegex(Rejected, "review_unauthorized"):
                self.view(**change)

    def test_closure_requires_assessment(self):
        self.apply()
        with self.assertRaisesRegex(Rejected, "review_closure_requires_benign_assessment"):
            self.apply("close", actor="boris")

    def test_assessor_cannot_confirm_own_benign_assessment(self):
        self.apply(); self.apply("assess", verdict="benign")
        with self.assertRaisesRegex(Rejected, "review_closure_requires_other_actor"):
            self.apply("close")

    def test_response_needed_and_inconclusive_cannot_be_closed(self):
        self.apply()
        for verdict in ("needs_response", "inconclusive"):
            self.apply("assess", verdict=verdict)
            with self.assertRaisesRegex(Rejected, "review_closure_requires_benign_assessment"):
                self.apply("close", actor="boris")

    def test_new_note_invalidates_previous_assessment(self):
        self.apply(); self.apply("assess", verdict="benign"); self.apply("note")
        self.assertIsNone(self.view()["review"]["assessment"])
        with self.assertRaises(Rejected):
            self.apply("close", actor="boris")

    def test_closed_case_requires_reopen_before_notes(self):
        self.apply(); self.apply("assess", verdict="benign"); self.apply("close", actor="boris")
        with self.assertRaisesRegex(Rejected, "review_not_investigating"):
            self.apply("note")

    def test_cannot_note_or_reopen_unstarted_case(self):
        for action in ("note","reopen"):
            with self.assertRaises(Rejected):
                self.apply(action)

    def test_cannot_start_twice(self):
        self.apply()
        with self.assertRaisesRegex(Rejected, "review_already_started"):
            self.apply()

    def test_missing_reason_and_unknown_verdict_rejected(self):
        for reason in ("", " ", "x\x00", "x" * 4097):
            with self.assertRaisesRegex(Rejected, "review_reason"):
                self.apply(reason=reason)
        self.apply()
        with self.assertRaisesRegex(Rejected, "review_verdict"):
            self.apply("assess", verdict="perfect")

    def test_nonassessment_cannot_smuggle_verdict(self):
        with self.assertRaisesRegex(Rejected, "review_unexpected_verdict"):
            self.apply(verdict="benign")

    def test_invalid_unicode_note_is_rejected_without_traceback(self):
        with self.assertRaisesRegex(Rejected, "review_reason"):
            self.apply(reason="bad\ud800")
        self.assertEqual(self.view()["checkpoint"], ORIGIN)

    def test_stale_checkpoint_rejects_lost_update(self):
        self.apply()
        with self.assertRaisesRegex(Rejected, "review_checkpoint_mismatch"):
            self.apply("note", expected=dict(ORIGIN))
        self.assertEqual(self.view()["checkpoint"]["revision"], 1)

    def test_exact_retry_does_not_duplicate_note(self):
        self.apply(); before = dict(self.head)
        first = self.apply("note", request_id="stable")
        retry = self.apply("note", request_id="stable", expected=before)
        self.assertFalse(retry["applied"]); self.assertTrue(retry["idempotent_retry"])
        self.assertEqual(first["checkpoint"], retry["operation_checkpoint"])
        self.assertEqual(self.view()["review"]["notes_count"], 1)

    def test_retry_after_newer_action_reports_current_state(self):
        self.apply(); before = dict(self.head); self.apply("note", request_id="stable")
        self.apply("assess", verdict="benign")
        retry = self.apply("note", request_id="stable", expected=before)
        self.assertEqual(retry["checkpoint"]["revision"], 3)
        self.assertEqual(retry["operation_checkpoint"]["revision"], 2)

    def test_reused_request_id_with_changed_reason_rejected(self):
        self.apply(); before = dict(self.head); self.apply("note", request_id="stable")
        with self.assertRaisesRegex(Rejected, "review_request_conflict"):
            self.apply("note", request_id="stable", expected=before, reason="different")

    def test_corrupt_bundle_rejected_even_after_start(self):
        self.apply()
        with self.assertRaisesRegex(Rejected, "evidence_bundle_digest"):
            self.apply("note", bundle=self.bundle + b" ")
        self.assertEqual(self.view()["checkpoint"]["revision"], 1)

    def test_different_valid_bundle_cannot_replace_review_basis(self):
        self.apply()
        value = json.loads(self.bundle); value["captured_ns"] += 1; other = canonical(value)
        with self.assertRaisesRegex(Rejected, "review_evidence_binding"):
            self.apply("note", bundle=other, bundle_digest=sha256(other))

    def test_case_change_in_store_rejected(self):
        self.apply()
        with self.store.transaction() as db:
            modified = dict(self.case); modified["interpretation"] = "changed"
            db.execute("UPDATE cases SET body=? WHERE id=?", (canonical(modified),self.case["case_id"]))
        with self.assertRaisesRegex(Rejected, "review_case_snapshot_changed"):
            self.view()

    def test_history_payload_change_detected(self):
        self.apply()
        with self.store.transaction() as db:
            db.execute("UPDATE case_reviews SET payload='{}'")
        with self.assertRaisesRegex(Rejected, "review_history_integrity"):
            self.view()

    def test_history_gap_detected(self):
        self.apply(); self.apply("note")
        with self.store.transaction() as db:
            db.execute("DELETE FROM case_reviews WHERE revision=1")
        with self.assertRaisesRegex(Rejected, "review_history_sequence"):
            self.view()

    def test_malformed_history_mac_is_controlled_rejection(self):
        self.apply()
        for value in ("é" * 64, "x", b"x" * 64):
            with self.subTest(value_type=type(value).__name__):
                with self.store.transaction() as db:
                    db.execute("UPDATE case_reviews SET mac=?", (value,))
                with self.assertRaisesRegex(Rejected, "review_history_integrity"):
                    self.view()

    def test_tail_deletion_detected_against_external_checkpoint(self):
        self.apply(); self.apply("note"); retained = dict(self.head)
        with self.store.transaction() as db:
            db.execute("DELETE FROM case_reviews WHERE revision=2")
        with self.assertRaisesRegex(Rejected, "review_checkpoint_mismatch"):
            self.view(expected=retained)
        with self.assertRaisesRegex(Rejected, "review_checkpoint_mismatch"):
            self.apply("note", expected=retained)

    def test_database_failure_does_not_change_state(self):
        self.apply()
        with self.store.transaction() as db:
            db.execute("CREATE TRIGGER fail_review BEFORE INSERT ON case_reviews BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.apply("note")
        self.assertEqual(self.view()["checkpoint"]["revision"], 1)

    def test_competing_reviews_cannot_overwrite_each_other(self):
        self.apply(); before = dict(self.head)
        def worker(index):
            try:
                return self.review.apply("ana",self.tokens["ana"],"tenant","host",self.case["case_id"],"note","parallel",f"parallel_{index}",before,
                    self.bundle,self.bundle_digest,self.case_digest,self.monitor.digest)["applied"]
            except Rejected as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(worker, range(2)))
        self.assertCountEqual(result, [True,"review_checkpoint_mismatch"])

    def test_clock_regression_rejects_write(self):
        with patch("nqc_defense.case_review.time.time_ns", return_value=100):
            self.apply()
        with patch("nqc_defense.case_review.time.time_ns", return_value=99):
            with self.assertRaisesRegex(Rejected, "review_clock_regressed"):
                self.apply("note")

    def test_review_capacity_rejects_write(self):
        self.apply()
        with patch("nqc_defense.case_review.MAX_TOTAL_REVISIONS", 1):
            with self.assertRaisesRegex(Rejected, "review_capacity"):
                self.apply("note")
        self.assertEqual(self.view()["checkpoint"]["revision"], 1)

    def test_history_pagination_and_credentials_not_logged(self):
        self.apply(); self.apply("note"); self.apply("assess", verdict="inconclusive")
        result = self.view(after=1, limit=1)
        self.assertEqual([r["revision"] for r in result["history"]], [2])
        encoded = canonical(result)
        self.assertNotIn(self.tokens["ana"].hex().encode(),encoded)
        self.assertNotIn(self.policy.key.hex().encode(),encoded)

    def test_policy_digest_and_key_changes_fail_closed(self):
        self.apply()
        (self.policy.root / "audit.key").write_bytes(b"x" * 32)
        with self.assertRaisesRegex(Rejected, "review_audit_key_digest"):
            self.view()

    def test_policy_edit_invalidates_authorization(self):
        (self.policy.root / "policy.json").write_bytes(b"{}")
        with self.assertRaisesRegex(Rejected, "review_policy_digest"):
            self.apply()

    def test_credential_file_symlink_and_public_mode_rejected(self):
        path = self.policy.root / "credentials/ana.key"
        os.chmod(path,0o644)
        with self.assertRaisesRegex(Rejected, "review_credential_permissions"):
            read_credential(path)
        os.chmod(path,0o600); linked = self.root / "linked"; linked.symlink_to(path)
        with self.assertRaisesRegex(Rejected, "review_credential_permissions"):
            read_credential(linked)

    def test_invalid_grant_never_initializes_policy(self):
        path = self.root / "invalid-policy"
        bad = [{"actor":"ana","tenant":"tenant","assets":["host"],"permissions":["execute_anything"]}]
        with self.assertRaisesRegex(Rejected, "review_permissions"):
            ReviewPolicy.create(path,bad)
        self.assertFalse(path.exists())

    def test_existing_policy_directory_never_overwritten(self):
        with self.assertRaises(FileExistsError):
            ReviewPolicy.create(self.policy.root,self.grants)

    def test_oversized_valid_grants_rejected_before_creation(self):
        assets = ["asset_" + "x" * 70 + f"{i:03}" for i in range(64)]
        grants = [{"actor":f"actor_{i}","tenant":"tenant","assets":assets,"permissions":["read"]} for i in range(32)]
        with self.assertRaisesRegex(Rejected, "review_policy_size"):
            ReviewPolicy.create(self.root / "too_large", grants)
        self.assertFalse((self.root / "too_large").exists())

    def test_malformed_case_has_controlled_rejection(self):
        with self.store.transaction() as db:
            case = dict(self.case); case.pop("threshold")
            db.execute("UPDATE cases SET body=? WHERE id=?", (canonical(case),self.case["case_id"]))
        with self.assertRaisesRegex(Rejected, "schema_fields"):
            self.view()

    def test_valid_mac_cannot_be_grafted_onto_another_case(self):
        self.apply()
        with self.log.open("ab") as stream:
            for i,outcome in enumerate(["success","failure","failure","failure"], start=3):
                stream.write(canonical({"schema":"nqc-auth-log-v1","time_ns":i*1000000000,"outcome":outcome,
                    "principal":"alice","remote_address":"192.0.2.1"}) + b"\n")
        self.monitor.poll()
        other = next(c for c in self.store.cases("tenant","host") if c["case_id"] != self.case["case_id"])
        with self.store.transaction() as db:
            row = db.execute("SELECT tenant,asset,revision,payload,previous,mac FROM case_reviews").fetchone()
            db.execute("INSERT INTO case_reviews VALUES(?,?,?,?,?,?,?)", (row[0],row[1],other["case_id"],*row[2:]))
        with self.assertRaisesRegex(Rejected, "review_history_binding"):
            self.view(case_id=other["case_id"])

    def test_process_death_before_commit_preserves_prior_review(self):
        self.apply()
        parameters = self.root / "crash-parameters.json"
        parameters.write_bytes(canonical({"case_id":self.case["case_id"],"case_digest":self.case_digest,
            "config_digest":self.monitor.digest,"bundle_digest":self.bundle_digest,"expected":self.head,
            "policy_digest":self.policy.digest}))
        script = '''
from contextlib import contextmanager
import json,os,sys
from pathlib import Path
from nqc_defense.operations import OperationsStore
from nqc_defense.review_policy import ReviewPolicy,read_credential
from nqc_defense.case_review import CaseReview
root=Path(sys.argv[1]); p=json.loads((root/"crash-parameters.json").read_bytes())
store=OperationsStore(root/"ops"); policy=ReviewPolicy(root/"policy",p["policy_digest"])
review=CaseReview(store,policy); original=store.transaction
@contextmanager
def transaction():
    with original() as db:
        db.create_function("terminate_test_process",0,lambda:os._exit(77))
        db.execute("CREATE TEMP TRIGGER test_death AFTER INSERT ON case_reviews BEGIN SELECT terminate_test_process(); END")
        yield db
store.transaction=transaction
review.apply("ana",read_credential(root/"policy/credentials/ana.key"),"tenant","host",p["case_id"],"note",
    "crash test","crash_note",p["expected"],(root/"evidence.json").read_bytes(),p["bundle_digest"],p["case_digest"],p["config_digest"])
'''
        result = subprocess.run([sys.executable,"-B","-c",script,str(self.root)],
                                cwd=Path(__file__).resolve().parents[1],capture_output=True)
        self.assertEqual(result.returncode,77,result.stderr)
        self.assertEqual(self.view()["checkpoint"], self.head)
        self.assertEqual(self.view()["review"]["notes_count"], 0)
        self.assertTrue(self.apply("note",request_id="crash_note")["applied"])

    def test_missing_operations_database_not_recreated(self):
        self.store.path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.view()
        self.assertFalse(self.store.path.exists())

    def test_cli_real_start_and_view(self):
        tool = Path(__file__).resolve().parents[1] / "tools/case_review.py"
        request = self.root / "request.json"
        request.write_bytes(canonical({"action":"start","reason":"CLI review","request_id":"cli_1","expected":ORIGIN,"verdict":None}))
        common = ["--operations-root",str(self.store.root),"--policy-root",str(self.policy.root),"--policy-digest",self.policy.digest,
                  "--actor","ana","--credential-file",str(self.policy.root / "credentials/ana.key"),"--tenant","tenant","--asset","host","--case-id",self.case["case_id"]]
        result = subprocess.run([sys.executable,"-B",str(tool),"act",*common,"--request-file",str(request),"--bundle-file",str(self.bundle_path),
                                 "--bundle-digest",self.bundle_digest,"--case-digest",self.case_digest,"--config-digest",self.monitor.digest],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        viewed = subprocess.run([sys.executable,"-B",str(tool),"view",*common],capture_output=True,text=True)
        self.assertEqual(viewed.returncode,0,viewed.stdout+viewed.stderr)
        self.assertEqual(json.loads(viewed.stdout)["review"]["stage"],"investigating")


if __name__ == "__main__":
    unittest.main()
