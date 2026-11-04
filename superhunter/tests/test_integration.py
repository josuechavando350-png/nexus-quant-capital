"""Evidence adapter integration and regressions; no scanner or PoC execution."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_bridge as fixtures
from superhunter.bridge import ContractError, candidate, evaluate, load_json, reconstruction
from superhunter.integration import export_diablo, import_nqc, validate_request
from superhunter.safe_io import canonical, read_artifact, strict_json, write_new_bundle


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        fixtures.BridgeTests.setUp(self)
        self.native = {"id": "NX-001", "title": "Local fixture", "severity": "critical",
                       "target": {"value": self.addr, "kind": "contract", "chain": "local", "label": None},
                       "description": "Synthetic data; no exploit executed", "invariant": self.c["invariant_broken"],
                       "poc_ref": self.c["poc_path"], "created_at": "2026-11-03T00:00:00Z"}
        self.ctx = {"scope_id": "immunefi-demo", "repo": "owner/repo", "commit": self.commit,
                    "chain": "local", "chain_id": 31337, "fork_block": 123,
                    "block_hash": self.block_hash, "family": "vault", "poc_path": self.c["poc_path"]}
        self.request = export_diablo(self.native, self.ctx, self.forge)
        self.c = self.request["candidate"]
        self.r["candidate_id"] = self.c["id"]
        self.a["forge"]["candidate_id"] = self.c["id"]
        self.a["nqc"]["candidate_id"] = self.c["id"]
        self.sync_evidence()
        self.response = {"schema_version": 1, "request_sha256": self.request["request_sha256"],
                         "chain_id": 31337, "reconstruction": self.r}

    def sync_evidence(self):
        raw = canonical(self.r)
        (self.root / "nqc.json").write_bytes(raw)
        self.a["nqc"]["evidence_sha256"] = hashlib.sha256(raw).hexdigest()

    def review(self):
        return import_nqc(self.request, self.response, self.a, evidence_root=self.root, report_path="review.md")

    def legacy(self):
        return evaluate(self.c, self.r, self.a, evidence_root=self.root, report_path="review.md")

    def cli(self, args):
        return subprocess.run([sys.executable, "-m", "superhunter", *map(str, args)],
                              cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)

    def save(self, name, value):
        path = self.root / name
        path.write_bytes(canonical(value))
        return path

    def test_native_roundtrip_always_requires_review(self):
        result = self.review()
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["diablo_feedback"]["native_id"], "NX-001")
        self.assertFalse(result["diablo_feedback"]["confirmed"])
        self.assertFalse(result["execution_verified"])
        self.assertNotIn("finding", result)

    def test_diablo_claimed_severity_not_trusted(self):
        self.assertEqual(self.c["prelim_severity"], "unverified")
        self.assertNotIn("final_severity", self.c)

    def test_idempotent_export(self):
        self.assertEqual(self.request, export_diablo(self.native, self.ctx, self.forge))

    def test_mutations_change_identity(self):
        for field, value in (("chain_id", 1), ("commit", "d" * 40), ("block_hash", "0x" + "d" * 64)):
            with self.subTest(field=field):
                ctx = {**self.ctx, field: value}
                self.assertNotEqual(self.c["id"], export_diablo(self.native, ctx, self.forge)["candidate"]["id"])

    def test_invalid_native_address_is_rejected(self):
        self.native["target"]["value"] = "0xvault01"
        with self.assertRaises(ContractError):
            export_diablo(self.native, self.ctx, self.forge)

    def test_native_chain_mismatch(self):
        self.native["target"]["chain"] = "ethereum"
        with self.assertRaisesRegex(ContractError, "kind/chain"):
            export_diablo(self.native, self.ctx, self.forge)

    def test_native_poc_mismatch(self):
        self.native["poc_ref"] = "unrelated.t.sol"
        with self.assertRaisesRegex(ContractError, "PoC reference"):
            export_diablo(self.native, self.ctx, self.forge)

    def test_native_missing_function_requires_context(self):
        self.native["poc_ref"] = self.ctx["poc_path"].split("::")[0]
        self.assertEqual(export_diablo(self.native, self.ctx, self.forge)["candidate"]["poc_path"], self.ctx["poc_path"])

    def test_native_closeout_not_promoted(self):
        self.response = {"closeout": "PROTOCOL_FORK_TRUTH", "status": "NOT_CLOSED", "required_gates": {"math": "PASS"}}
        result = self.review()
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["nqc_status"], "NOT_CLOSED")
        self.assertNotIn("draft", result)

    def test_even_claimed_closed_not_reconstruction(self):
        self.response = {"closeout": "PROTOCOL_FORK_TRUTH", "status": "CLOSED"}
        self.assertEqual(self.review()["status"], "INCOMPLETE")

    def test_request_tamper(self):
        self.request["context"]["chain_id"] = 1
        with self.assertRaisesRegex(ContractError, "digest mismatch"):
            validate_request(self.request)

    def test_response_must_match_request(self):
        self.response["request_sha256"] = "d" * 64
        with self.assertRaisesRegex(ContractError, "response/request mismatch"):
            self.review()

    def test_response_chain_mismatch(self):
        self.response["chain_id"] = 1
        with self.assertRaisesRegex(ContractError, "chain_id mismatch"):
            self.review()

    def test_boolean_chain_id(self):
        self.response["chain_id"] = True
        with self.assertRaises(ContractError):
            self.review()

    def test_block_hash_mismatch(self):
        self.r["state_anchor"]["block_hash"] = "0x" + "d" * 64
        with self.assertRaisesRegex(ContractError, "anchor mismatch"):
            self.review()

    def test_unbound_confidence_rejected(self):
        self.r["confidence"] = 1.0
        self.assertEqual(self.legacy()["status"], "REJECTED")

    def test_unbound_severity_rejected(self):
        self.r["economic_severity"] = "high"
        self.assertEqual(self.legacy()["status"], "REJECTED")

    def test_malformed_fields_fail_closed(self):
        for section, field in (("scope", "commit"), ("forge", "candidate_id"), ("nqc", "candidate_id")):
            with self.subTest(section=section):
                old = self.a[section][field]
                self.a[section][field] = None
                self.assertEqual(self.legacy()["status"], "REJECTED")
                self.a[section][field] = old

    def test_candidate_unhashable_family(self):
        self.c["family"] = []
        with self.assertRaises(ContractError):
            candidate(self.c)

    def test_unsafe_poc_path(self):
        self.c["poc_path"] = "../test/Foo.t.sol::test_example"
        with self.assertRaisesRegex(ContractError, "unsafe path"):
            candidate(self.c)

    def test_unicode_amount_not_integer(self):
        self.r["funds_at_risk"]["amount_wei"] = "²"
        with self.assertRaises(ContractError):
            reconstruction(self.r)

    def test_uint256_bounds(self):
        self.r["funds_at_risk"]["amount_wei"] = str(2**256)
        with self.assertRaises(ContractError):
            reconstruction(self.r)

    def test_large_number_rejected_cleanly(self):
        self.r["net_profit_usd"] = 10**1000
        with self.assertRaises(ContractError):
            reconstruction(self.r)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            strict_json(b'{"approved": false, "approved": true}')

    def test_infinite_json_rejected(self):
        for raw in (b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                strict_json(raw)

    def test_json_array_root_rejected(self):
        with self.assertRaises(ValueError):
            strict_json(b'[]')

    def test_symlink_leaf_rejected(self):
        (self.root / "alias.log").symlink_to(self.root / "forge.log")
        with self.assertRaises((OSError, ValueError)):
            read_artifact(self.root, "alias.log")

    def test_symlink_directory_rejected(self):
        (self.root / "alias").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            read_artifact(self.root, "alias/forge.log")

    def test_fifo_rejected_without_blocking(self):
        os.mkfifo(self.root / "pipe")
        with self.assertRaises(ValueError):
            read_artifact(self.root, "pipe")

    def test_artifact_limit(self):
        (self.root / "large.json").write_bytes(b' ' * 2_000_001)
        with self.assertRaises((OSError, ValueError)):
            load_json(self.root / "large.json")

    def test_output_private_and_content_committed(self):
        out = self.root / "case"
        write_new_bundle(out, {"review.md": b"synthetic", "decision.json": b'{}'})
        marker = load_json(out / "COMPLETE.json")
        for name, expected in marker["sha256"].items():
            self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(), expected)
            self.assertEqual((out/name).stat().st_mode & 0o777, 0o600)
        self.assertEqual(out.stat().st_mode & 0o777, 0o700)

    def test_no_overwrite_or_stale_success(self):
        out = self.root / "case"
        write_new_bundle(out, {"decision.json": b'{"status":"OLD"}'})
        with self.assertRaises(FileExistsError):
            write_new_bundle(out, {"decision.json": b'{"status":"NEW"}'})
        self.assertEqual(load_json(out / "decision.json")["status"], "OLD")

    def test_no_network_or_process_in_adapters(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
             patch("subprocess.run", side_effect=AssertionError("process forbidden")):
            self.assertEqual(self.review()["status"], "REVIEW_REQUIRED")

    def test_cli_export_then_import(self):
        native = self.save("diablo-native.json", self.native)
        ctx = self.save("context.json", self.ctx)
        first = self.cli(["export-diablo", native, ctx, self.root / "forge.log", "--out", self.root / "request"])
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        self.assertEqual(load_json(self.root / "request/request.json"), self.request)
        response = self.save("response.json", self.response)
        adm = self.save("admission.json", self.a)
        second = self.cli(["import-nqc", self.root / "request/request.json", response, adm,
                           "--evidence-root", self.root, "--out", self.root / "review"])
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        feedback = load_json(self.root / "review/diablo-feedback.json")
        self.assertEqual(feedback["native_id"], "NX-001")
        self.assertFalse(feedback["confirmed"])
        self.assertTrue((self.root / "review/review.md").exists())
        self.assertNotIn("49750", second.stdout)  # economic details not leaked to console

    def test_cli_native_closeout_emits_no_report(self):
        q = self.save("request.json", self.request)
        r = self.save("closeout.json", {"closeout": "PROTOCOL_FORK_TRUTH", "status": "NOT_CLOSED"})
        a = self.save("admission.json", self.a)
        result = self.cli(["import-nqc", q, r, a, "--evidence-root", self.root, "--out", self.root / "incomplete"])
        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        self.assertFalse((self.root / "incomplete/review.md").exists())
        self.assertEqual(load_json(self.root / "incomplete/decision.json")["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
