"""Synthetic QA receipts and genuine OpenTelemetry in-memory spans when available.

These tests DO NOT prove a complete QA run, collector deployment or scanning.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from unittest.mock import patch
import hashlib
import io
from pathlib import Path
import tempfile
import unittest

from superhunter import otel_qa as ot
from superhunter import quality
from superhunter.safe_io import canonical, strict_json

PASS = {"status": "LOCAL_QA_PASS", "source_digest": "a" * 64, "tests_run": 15}


class OfflineOpenTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.qa = self.root / "qa"
        self.metrics = self.root / "metric"

    def test_metadata_check_and_no_remote_operation(self):
        with patch("socket.socket", side_effect=AssertionError("NETWORK_CALLED")):
            status = ot.readiness()
        self.assertIn(status["status"], ("READY", "BLOCKED_DEPENDENCY"))
        self.assertTrue(status["offline_only"])

    def test_real_sdk_captures_qa_and_verifier_in_memory(self):
        if ot.readiness()["status"] != "READY":
            with self.assertRaisesRegex(ValueError, "DEPENDENCY"):
                ot.profile_owned_qa(self.qa, self.metrics)
            return
        with (patch.object(quality, "run_check", return_value=dict(PASS)) as run,
              patch.object(quality, "verify_bundle", return_value=dict(PASS)) as verify,
              patch("socket.socket", side_effect=AssertionError("NETWORK_CALLED"))):
            out = ot.profile_owned_qa(self.qa, self.metrics)
        self.assertEqual(out["status"], "QA_VERIFIED")
        self.assertEqual(out["tests_run"], 15)
        self.assertTrue(out["qa_passed"])
        self.assertEqual([s["name"] for s in out["spans"]],
                         ["superhunter.qa.run", "superhunter.qa.verify"])
        self.assertTrue(all(s["duration_ns"] >= 0 for s in out["spans"]))
        self.assertFalse(out["network_export"])
        self.assertFalse(out["vulnerability_confirmed"])
        self.assertTrue(out['dependency_files_checked'])
        self.assertFalse(out['process_memory_integrity_proved'])
        self.assertEqual(len(out['dependency_identity']),8)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(verify.call_count, 2)

    def test_failed_qa_is_never_promoted(self):
        if ot.readiness()["status"] != "READY":
            self.assertEqual(ot.readiness()["status"], "BLOCKED_DEPENDENCY")
            return
        with patch.object(quality, "run_check", side_effect=RuntimeError("sensitive message")), \
             patch.object(quality, "verify_bundle", side_effect=AssertionError("must not run")):
            out = ot.profile_owned_qa(self.qa, self.metrics)
        self.assertEqual(out["status"], "QA_FAILED")
        self.assertFalse(out["qa_passed"])
        self.assertEqual(out["error_type"], "RuntimeError")
        self.assertNotIn("sensitive message", (self.metrics / "PROFILE.md").read_text())
        self.assertEqual(len(out["spans"]), 1)

    def test_verifier_exception_is_failure_not_pass(self):
        if ot.readiness()["status"] != "READY":
            self.assertEqual(ot.readiness()["status"], "BLOCKED_DEPENDENCY")
            return
        with (patch.object(quality, "run_check", return_value=dict(PASS)),
              patch.object(quality, "verify_bundle", side_effect=ValueError("secret review"))):
            out = ot.profile_owned_qa(self.qa, self.metrics)
        self.assertEqual(out["status"], "QA_VERIFICATION_FAILED")
        self.assertFalse(out["qa_passed"])
        self.assertEqual(len(out["spans"]), 2)
        self.assertEqual(out["error_type"], "ValueError")
        self.assertNotIn("secret review", (self.metrics / "PROFILE.md").read_text())

    def test_bundle_tampering_rejected(self):
        if ot.readiness()["status"] != "READY":
            self.assertEqual(ot.readiness()["status"], "BLOCKED_DEPENDENCY")
            return
        with patch.object(quality, "run_check", side_effect=ValueError("failure")):
            ot.profile_owned_qa(self.qa, self.metrics)
        evidence = self.metrics / "telemetry.json"
        payload = strict_json(evidence.read_bytes())
        payload["qa_passed"] = True
        evidence.write_bytes(canonical(payload))
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            ot.verify_profile(self.metrics)
        marker = self.metrics / "COMPLETE.json"
        manifest = strict_json(marker.read_bytes())
        manifest["sha256"]["telemetry.json"] = hashlib.sha256(evidence.read_bytes()).hexdigest()
        marker.write_bytes(canonical(manifest))
        with self.assertRaisesRegex(ValueError, "TELEMETRY_SCHEMA|REQUIRES_QA"):
            ot.verify_profile(self.metrics)

    def test_no_output_inside_checkout_and_no_duplicate_output(self):
        if ot.readiness()["status"] != "READY":
            self.assertEqual(ot.readiness()["status"], "BLOCKED_DEPENDENCY")
            return
        with self.assertRaisesRegex(ValueError, "OUTPUT_UNSAFE"):
            ot.profile_owned_qa(ot.CHECKOUT / "private-qa", self.metrics)
        self.assertFalse(self.metrics.exists())
        self.metrics.mkdir()
        with self.assertRaisesRegex(ValueError, "OUTPUT_UNSAFE"):
            ot.profile_owned_qa(self.qa, self.metrics)

    def test_cli_redacts_bad_output_path(self):
        with redirect_stdout(io.StringIO()) as stream:
            code = ot.main(["verify-owned-qa-profile", "--bundle",
                            str(self.root / "SECRET_KEY_12345")])
        self.assertEqual(code, 2)
        self.assertNotIn("SECRET_KEY_12345", stream.getvalue())
        self.assertIn("OTEL_PROFILE_ERROR", stream.getvalue())

    def test_fail_open_resealed_failure_cannot_claim_pass(self):
        if ot.readiness()["status"] != "READY":
            self.assertEqual(ot.readiness()["status"], "BLOCKED_DEPENDENCY")
            return
        with patch.object(quality, "run_check", return_value={"status": "LOCAL_QA_ERROR"}):
            outcome = ot.profile_owned_qa(self.qa, self.metrics)
        self.assertFalse(outcome["qa_passed"])
        artifact = self.metrics / "telemetry.json"
        payload = strict_json(artifact.read_bytes())
        payload.update({"status": "QA_VERIFIED", "qa_passed": True,
                        "qa_reverified_here": True, "tests_run": 15,
                        "source_digest": "a" * 64})
        artifact.write_bytes(canonical(payload))
        marker = self.metrics / "COMPLETE.json"
        seal = strict_json(marker.read_bytes())
        seal["sha256"]["telemetry.json"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        marker.write_bytes(canonical(seal))
        with self.assertRaisesRegex(ValueError, "TELEMETRY_SPANS"):
            ot.verify_profile(self.metrics)

    def rewrite_payload(self, payload):
        from superhunter.safe_io import write_new_bundle
        rebuilt = self.root/'rebuilt'
        write_new_bundle(rebuilt, {'telemetry.json':canonical(payload),
                                  'PROFILE.md':ot._review(payload).encode()})
        return rebuilt

    def test_resealed_dependency_identity_change_is_rejected(self):
        if ot.readiness()['status'] != 'READY':
            self.assertEqual(ot.readiness()['status'],'BLOCKED_DEPENDENCY'); return
        with patch.object(quality,'run_check',side_effect=ValueError('OWNED FAILURE')):
            payload = ot.profile_owned_qa(self.qa,self.metrics)
        payload['dependency_identity']['opentelemetry-sdk']['runtime_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError,'TELEMETRY_DEPENDENCY_IDENTITY'):
            ot.verify_profile(self.rewrite_payload(payload))

    def test_legacy_v1_remains_unpinned_without_silent_promotion(self):
        # A genuine old-format failure report requires no SDK installation.
        payload = {'schema_version':1,'profile':ot.LEGACY_PROFILE,'status':'QA_FAILED',
                   'qa_passed':False,'qa_reverified_here':False,'tests_run':0,
                   'source_digest':None,'elapsed_ns':1,
                   'spans':[{'name':'superhunter.qa.run','duration_ns':1}],
                   'sdk_version':ot.SDK_VERSION,'exporter':'in-memory-only',
                   'network_export':False,'target_scanned':False,
                   'vulnerability_confirmed':False,'error_type':'ValueError'}
        result = ot.verify_profile(self.rewrite_payload(payload))
        self.assertEqual(result,payload)
        self.assertNotIn('dependency_files_checked',result)
        self.assertNotIn('dependency_identity',result)

    def test_dependency_change_after_qa_prevents_completion_marker(self):
        if ot.readiness()['status'] != 'READY':
            self.assertEqual(ot.readiness()['status'],'BLOCKED_DEPENDENCY'); return
        identity = ot.dependencies.expected_identity()
        with (patch.object(quality,'run_check',side_effect=ValueError('OWNED FAILURE')),
              patch.object(ot.dependencies,'verify_dependencies',side_effect=[identity,{}])):
            with self.assertRaisesRegex(ValueError,'DEPENDENCIES_CHANGED'):
                ot.profile_owned_qa(self.qa,self.metrics)
        self.assertFalse((self.metrics/'COMPLETE.json').exists())


if __name__ == "__main__":
    unittest.main()
