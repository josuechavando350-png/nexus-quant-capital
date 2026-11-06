"""Offline and adversarial contract tests. No blockchain connection or broadcasts."""

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from superhunter.bridge import ContractError, candidate, evaluate, reconstruction, render_report


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.cid = str(uuid.uuid4())
        self.addr = "0x" + "a" * 40
        self.token = "0x" + "b" * 40
        self.commit = "a" * 40
        self.block_hash = "0x" + "c" * 64
        self.forge = b"Running 1 test for VaultExploit.t.sol\n[PASS] test_PoC_example() (gas: 12345)\nSuite result: ok\n"
        (self.root / "forge.log").write_bytes(self.forge)
        self.c = {
            "id": self.cid, "scope_id": "immunefi-demo", "target": {"repo": "owner/repo", "commit": self.commit, "fork_block": 123},
            "family": "vault", "invariant_broken": "vault_strictAccounting",
            "poc_path": "test/exploits/VaultExploit.t.sol::test_PoC_example", "affected_contracts": [self.addr],
            "prelim_severity": "unverified", "forge_evidence_sha": hashlib.sha256(self.forge).hexdigest(),
        }
        self.r = {
            "candidate_id": self.cid, "state_anchor": {"block": 123, "block_hash": self.block_hash},
            "protocol_model": "aave-v3", "funds_at_risk": {"token": self.token, "amount_wei": "123456", "usd": 50000.0},
            "attacker_cost": {"usd": 250.0}, "net_profit_usd": 49750.0,
            "reproducible": True, "economic_severity": "critical", "confidence": 0.99, "notes": "Synthetic test fixture",
        }
        self.statement = copy.deepcopy(self.r)
        self.evidence_bytes = json.dumps(self.statement, sort_keys=True).encode()
        (self.root / "nqc.json").write_bytes(self.evidence_bytes)
        self.a = {
            "scope": {"scope_id": "immunefi-demo", "repo": "owner/repo", "commit": self.commit,
                      "allowed_contracts": [self.addr], "excluded_contracts": [],
                      "policy_sha256": "1" * 64, "source_url": "https://immunefi.com/bug-bounty/demo/",
                      "reviewed_by": "human", "approved": True},
            "forge": {"candidate_id": self.cid, "repo": "owner/repo", "commit": self.commit,
                      "fork_block": 123, "poc_path": self.c["poc_path"], "affected_contracts": [self.addr],
                      "output_file": "forge.log", "exit_code": 0, "test_pass": True, "target_bound": True},
            "nqc": {"candidate_id": self.cid, "state_anchor": copy.deepcopy(self.r["state_anchor"]),
                    "protocol_model": "aave-v3", "evidence_file": "nqc.json",
                    "evidence_sha256": hashlib.sha256(self.evidence_bytes).hexdigest(), "producer": "NQC", "run_ok": True},
            "duplicate": {"result": "none", "checked_sources": ["public-audits", "program-notices"],
                          "reviewed_by": "human"},
            "severity": {"program_cap": "critical", "impact_review": "high", "reviewed_by": "human"},
        }

    def go(self):
        return evaluate(self.c, self.r, self.a, evidence_root=self.root, report_path="reports/review.md")

    def rejected(self, match):
        result = self.go()
        self.assertEqual(result["status"], "REJECTED")
        self.assertIn(match, " | ".join(result["reasons"]))
        self.assertNotIn("finding", result)

    def test_valid_bridge_and_calibration(self):
        result = self.go()
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        f = result["draft"]
        self.assertEqual(f["id"], self.cid)
        self.assertEqual(f["proposed_severity"], "high")
        self.assertTrue(f["declared_scope_approved"] and f["declared_forge_pass"])
        self.assertFalse(result["execution_verified"])
        self.assertNotIn("finding", result)
        self.assertNotIn("final_severity", f)
        self.assertEqual(f["dup_check"], "none")
        self.assertIn("human review", render_report(f))

    def test_out_of_scope(self):
        self.a["scope"]["allowed_contracts"] = [self.token]
        self.rejected("outside scope")

    def test_excluded_contract_wins(self):
        self.a["scope"]["excluded_contracts"] = [self.addr]
        self.rejected("excluded contract")

    def test_scope_not_approved(self):
        self.a["scope"]["approved"] = False
        self.rejected("not approved")

    def test_scope_commit_mismatch(self):
        self.a["scope"]["commit"] = "d" * 40
        self.rejected("target repo/commit mismatch")

    def test_forge_cannot_assert_unbound_target(self):
        self.a["forge"]["target_bound"] = False
        self.rejected("target binding")

    def test_forge_wrong_target(self):
        self.a["forge"]["commit"] = "d" * 40
        self.rejected("target mismatch")

    def test_forge_wrong_poc(self):
        self.a["forge"]["poc_path"] = "test/exploits/VaultExploit.t.sol::test_Other"
        self.rejected("PoC/fork mismatch")

    def test_forge_wrong_contract(self):
        self.a["forge"]["affected_contracts"] = [self.token]
        self.rejected("contract mismatch")

    def test_forge_tampered_log(self):
        (self.root / "forge.log").write_bytes(b"[PASS] test_PoC_example() tampered\n")
        self.rejected("SHA256 mismatch")

    def test_forge_does_not_contain_named_pass(self):
        payload = b"[PASS] test_PoC_wrong() (gas: 1)\n"
        (self.root / "forge.log").write_bytes(payload)
        self.c["forge_evidence_sha"] = hashlib.sha256(payload).hexdigest()
        self.rejected("named test absent")

    def test_forge_exit_code_failure(self):
        self.a["forge"]["exit_code"] = 1
        self.rejected("did not attest PASS")

    def test_nqc_wrong_block(self):
        self.r["state_anchor"]["block"] = 124
        self.a["nqc"]["state_anchor"]["block"] = 124
        self.rejected("fork block/anchor mismatch")

    def test_nqc_not_reproducible(self):
        self.r["reproducible"] = False
        self.rejected("not sufficiently verified")

    def test_nqc_low_confidence(self):
        self.r["confidence"] = 0.7
        self.rejected("not sufficiently verified")

    def test_nqc_hash_tamper(self):
        (self.root / "nqc.json").write_text('{"wrong": "contents"}')
        self.rejected("evidence SHA256 mismatch")

    def test_nqc_unbound_economics(self):
        self.r["net_profit_usd"] = 100.0
        self.rejected("does not bind economics")

    def test_duplicate_audit(self):
        self.a["duplicate"]["result"] = "audit:123"
        self.rejected("possible duplicate")

    def test_unknown_dup_status(self):
        self.a["duplicate"]["result"] = "unknown"
        self.rejected("possible duplicate")

    def test_unreviewed_duplicates(self):
        self.a["duplicate"]["checked_sources"] = []
        self.rejected("sources missing")

    def test_nonpositive_loss(self):
        self.r["funds_at_risk"]["usd"] = 0.0
        self.rejected("no proven economic impact")

    def test_zero_economic_severity(self):
        self.r["economic_severity"] = "none"
        self.rejected("no proven economic impact")

    def test_severity_cap(self):
        self.a["severity"]["program_cap"] = "medium"
        self.assertEqual(self.go()["draft"]["proposed_severity"], "medium")

    def test_missing_policy_hash(self):
        self.a["scope"]["policy_sha256"] = "bad"
        self.rejected("invalid format")

    def test_path_traversal(self):
        self.a["forge"]["output_file"] = "../forge.log"
        self.rejected("traversal")

    def test_absolute_path(self):
        self.a["nqc"]["evidence_file"] = "/tmp/other.json"
        self.rejected("absolute/traversal")

    def test_candidate_id_mismatch(self):
        self.r["candidate_id"] = str(uuid.uuid4())
        with self.assertRaisesRegex(ContractError, "candidate_id mismatch"):
            self.go()

    def test_reject_extraneous_candidate_field(self):
        self.c["fake_verified"] = True
        with self.assertRaisesRegex(ContractError, "fields mismatch"):
            candidate(self.c)

    def test_reject_nan(self):
        self.r["confidence"] = float("nan")
        with self.assertRaisesRegex(ContractError, "finite number"):
            reconstruction(self.r)

    def test_reject_bool_as_number(self):
        self.r["net_profit_usd"] = True
        with self.assertRaisesRegex(ContractError, "finite number"):
            reconstruction(self.r)

    def test_cli_creates_report_for_valid_case(self):
        for name, value in (("candidate", self.c), ("reconstruction", self.r), ("admission", self.a)):
            (self.root / f"{name}.json").write_text(json.dumps(value))
        base = Path(__file__).resolve().parents[2]
        proc = subprocess.run([sys.executable, "-m", "superhunter", str(self.root / "candidate.json"),
                               str(self.root / "reconstruction.json"), str(self.root / "admission.json"),
                               "--evidence-root", str(self.root), "--out", str(self.root / "reports")],
                              cwd=base, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertTrue((self.root / "reports/review.md").is_file())
        self.assertEqual(json.loads((self.root / "reports/decision.json").read_text())["status"], "REVIEW_REQUIRED")

    def test_cli_never_writes_report_when_rejected(self):
        self.a["forge"]["target_bound"] = False
        for name, value in (("candidate", self.c), ("reconstruction", self.r), ("admission", self.a)):
            (self.root / f"{name}.json").write_text(json.dumps(value))
        base = Path(__file__).resolve().parents[2]
        proc = subprocess.run([sys.executable, "-m", "superhunter", str(self.root / "candidate.json"),
                               str(self.root / "reconstruction.json"), str(self.root / "admission.json"),
                               "--evidence-root", str(self.root), "--out", str(self.root / "reports")],
                              cwd=base, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stderr + proc.stdout)
        self.assertFalse((self.root / "reports/review.md").exists())


if __name__ == "__main__":
    unittest.main()
