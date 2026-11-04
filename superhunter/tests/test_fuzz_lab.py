"""Deterministic adversarial checks on real, pinned NQC and DIABLO code."""
from __future__ import annotations
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import fuzz_cli, native_runtime
from superhunter.fuzz_lab import (_invariants, _negative_controls, execute, make_case,
                                  run_fuzz, validate_parameters, verify_fuzz)
from superhunter.safe_io import canonical, strict_json


class FuzzLabTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.native = native_runtime.load_components()

    def bundle(self, seed=45, cases=5):
        out = self.root / "bundle"
        self.assertEqual(run_fuzz(out, seed, cases)["status"], "LOCAL_FUZZ_PASS")
        return out

    def reseal(self, path, filename, change):
        value = strict_json((path / filename).read_bytes())
        change(value)
        raw = canonical(value)
        (path / filename).write_bytes(raw)
        manifest = strict_json((path / "COMPLETE.json").read_bytes())
        manifest["sha256"][filename] = hashlib.sha256(raw).hexdigest()
        (path / "COMPLETE.json").write_bytes(canonical(manifest))

    def cli(self, *arguments):
        return subprocess.run([sys.executable, "-B", "-m", "superhunter", *map(str, arguments)],
                              cwd=Path(__file__).resolve().parents[2],
                              capture_output=True, text=True, timeout=45)

    def test_seed_replay_stable(self):
        self.assertEqual(make_case(42, 7), make_case(42, 7))
        self.assertNotEqual(make_case(42, 7), make_case(43, 7))
        self.assertNotEqual(make_case(42, 7), make_case(42, 8))

    def test_cases_are_valid_and_distinct(self):
        for i in range(20):
            rows = make_case(777, i)
            self.assertEqual(len({r["opportunity_id"] for r in rows}), len(rows))
            self.native.capacity.solve(rows)

    def test_bounds_are_strict(self):
        for seed, count in [(-1, 1), (2**64, 1), (True, 1), (1, 0), (1, 257), (1, True)]:
            with self.subTest(seed=seed, count=count), self.assertRaises(ValueError):
                validate_parameters(seed, count)

    def test_differential_64_cases(self):
        payload = execute(20261103, 64)
        self.assertEqual(strict_json(payload["fuzz-result.json"])["tested"], 64)
        self.assertEqual(strict_json(payload["fuzz-result.json"])["failed"], 0)

    def test_real_nqc_invocation_is_required(self):
        with patch.object(self.native.capacity, "solve", wraps=self.native.capacity.solve) as engine:
            payload = execute(10, 3)
        self.assertGreaterEqual(engine.call_count, 3 * 3 + 7)
        self.assertIn(b'"cases":3', payload["fuzz-result.json"])

    def test_invalid_cases_rejected_by_actual_nqc(self):
        bad = _negative_controls(self.native.capacity.solve)
        self.assertEqual(set(bad), {"duplicate-id", "conflicting-cap", "unsupported-kind",
                                    "negative-value", "zero-interval", "over-capacity", "empty-claims"})

    def test_deliberately_wrong_solver_cannot_pass(self):
        real = self.native.capacity.solve
        def corrupt(rows):
            output = real(rows)
            output["success_path_capacity_usd_wad"] = "999999999"
            return output
        with patch.object(self.native.capacity, "solve", side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "disagreement"):
                run_fuzz(self.root / "bad", 1, 3)
        self.assertFalse((self.root / "bad" / "COMPLETE.json").exists())

    def test_independent_oracle_does_not_call_solver(self):
        from superhunter.local_lab import independent_reference
        rows = make_case(2, 1)
        with patch.object(self.native.capacity, "solve", side_effect=AssertionError("must not call")):
            self.assertIsInstance(independent_reference(rows)["selected_opportunity_ids"], list)

    def test_whole_bundle_recalculated(self):
        result = verify_fuzz(self.bundle(seed=7, cases=8))
        self.assertEqual(result["cases_verified"], 8)
        self.assertFalse(result["vulnerability_confirmed"])

    def test_hash_mismatch_detected(self):
        out = self.bundle()
        with (out / "fuzz-cases.json").open("ab") as stream:
            stream.write(b"x")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            verify_fuzz(out)

    def test_resealed_wrong_numeric_result_detected(self):
        out = self.bundle()
        self.reseal(out, "fuzz-cases.json", lambda value: value["cases"][0]["nqc"].update(
            success_path_capacity_usd_wad="0"))
        with self.assertRaisesRegex(ValueError, "computed result mismatch"):
            verify_fuzz(out)

    def test_resealed_modified_fixture_detected(self):
        out = self.bundle()
        self.reseal(out, "fuzz-cases.json", lambda value: value["cases"][0]["input"][0].update(
            start_order=99))
        with self.assertRaisesRegex(ValueError, "seeded input mismatch"):
            verify_fuzz(out)

    def test_resealed_audit_event_detected(self):
        out = self.bundle()
        self.reseal(out, "diablo-fuzz-audit.json", lambda value: value["entries"][0]["data"].update(
            seed=999))
        with self.assertRaisesRegex(ValueError, "audit chain mismatch"):
            verify_fuzz(out)

    def test_resealed_audit_event_order_rejected(self):
        out = self.bundle()
        self.reseal(out, "diablo-fuzz-audit.json", lambda value: value["entries"].reverse())
        with self.assertRaisesRegex(ValueError, "audit chain mismatch"):
            verify_fuzz(out)

    def test_resealed_forged_production_claim_rejected(self):
        out = self.bundle()
        self.reseal(out, "fuzz-result.json", lambda value: value.update(vulnerability_confirmed=True))
        with self.assertRaisesRegex(ValueError, "synthetic lab"):
            verify_fuzz(out)

    def test_resealed_fake_coverage_rejected(self):
        out = self.bundle()
        self.reseal(out, "fuzz-result.json", lambda value: value.update(oracle_checks=999))
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            verify_fuzz(out)

    def test_resealed_provenance_mismatch(self):
        out = self.bundle()
        self.reseal(out, "fuzz-provenance.json", lambda value: value["sources"][0].update(
            source_commit="0" * 40))
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            verify_fuzz(out)

    def test_resealed_scope_decision_mismatch(self):
        out = self.bundle()
        # Recalculate the audit chain (a fully controlled malicious manifest).
        audit = strict_json((out / "diablo-fuzz-audit.json").read_bytes())
        audit["entries"][1]["data"]["decision"] = "DENY"
        previous = "0" * 64
        for entry in audit["entries"]:
            entry["prev_hash"] = previous
            entry["hash"] = self.native.audit.compute_hash(
                entry["index"], entry["timestamp"], entry["event"], entry["data"], previous)
            previous = entry["hash"]
        (out / "diablo-fuzz-audit.json").write_bytes(canonical(audit))
        self.reseal(out, "fuzz-result.json", lambda value: value.update(audit_head=previous))
        self.reseal(out, "diablo-fuzz-audit.json", lambda _: None)
        with self.assertRaisesRegex(ValueError, "audit case mismatch"):
            verify_fuzz(out)

    def test_no_network_or_external_subprocess_during_calculation(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
             patch("subprocess.run", side_effect=AssertionError("process forbidden")):
            payload = execute(42, 4)
            self.assertFalse(strict_json(payload["fuzz-result.json"])["live_rpc_used"])

    def test_cli_runs_bounded_fuzz_and_reverification(self):
        out = self.root / "cli"
        first = self.cli("fuzz-lab", "--seed", 33, "--cases", 12, "--out", out)
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        second = self.cli("verify-fuzz", "--bundle", out)
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        self.assertEqual(json.loads(second.stdout)["cases_verified"], 12)

    def test_cli_never_accepts_live_target(self):
        for flag in ("--target", "--rpc", "--poc", "--contract"):
            with self.subTest(flag=flag):
                result = self.cli("fuzz-lab", "--out", self.root / "forbidden", flag, "live")
                self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "forbidden").exists())

    def test_cli_existing_directory_rejected(self):
        out = self.root / "cli"
        self.assertEqual(self.cli("fuzz-lab", "--cases", 1, "--out", out).returncode, 0)
        self.assertNotEqual(self.cli("fuzz-lab", "--cases", 1, "--out", out).returncode, 0)

    def test_worker_does_not_get_process_environment(self):
        fake = subprocess.CompletedProcess([], 0, stdout='{"status":"LOCAL_FUZZ_PASS","vulnerability_confirmed":false}')
        with patch("subprocess.run", return_value=fake) as call, redirect_stdout(io.StringIO()):
            fuzz_cli.main(["--out", str(self.root / "out")])
        self.assertEqual(set(call.call_args.kwargs["env"]), {"LANG", "LC_ALL"})
        self.assertEqual(call.call_args.kwargs["timeout"], 45)
        self.assertIn("-I", call.call_args.args[0])

    def test_worker_timeout_is_error(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("fuzz", 45)), \
             redirect_stdout(io.StringIO()) as output:
            status = fuzz_cli.main(["--out", str(self.root / "out")])
        self.assertEqual(status, 2)
        self.assertFalse(json.loads(output.getvalue())["vulnerability_confirmed"])

    def test_worker_fake_success_rejected(self):
        fake = subprocess.CompletedProcess([], 0, stdout='{"status":"LOCAL_FUZZ_PASS","vulnerability_confirmed":true}')
        with patch("subprocess.run", return_value=fake), redirect_stdout(io.StringIO()) as output:
            status = fuzz_cli.main(["--out", str(self.root / "out")])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "LOCAL_FUZZ_ERROR")

    def test_deleting_completion_marker_rejected(self):
        out = self.bundle()
        (out / "COMPLETE.json").unlink()
        with self.assertRaises(OSError):
            verify_fuzz(out)


if __name__ == "__main__":
    unittest.main()
