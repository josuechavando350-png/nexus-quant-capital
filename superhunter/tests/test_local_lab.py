"""Native component tests on fixed benign data; no vulnerabilities or PoCs."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import lab_cli, native_runtime
from superhunter.lab_worker import deny_external_execution
from superhunter.local_lab import (WAD, _check_native_result, execute_local, fixture_cases,
                                    independent_reference, run_local, verify_local_bundle)
from superhunter.safe_io import canonical, strict_json, write_new_bundle


class LocalLabTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.native = native_runtime.load_components()

    def bundle(self):
        out = self.root / "run"
        result = run_local(out)
        self.assertEqual(result["status"], "LOCAL_INTEGRATION_PASS")
        return out

    def alter(self, out, name, fn):
        value = strict_json((out/name).read_bytes())
        fn(value)
        raw = canonical(value)
        (out/name).write_bytes(raw)
        marker = strict_json((out/"COMPLETE.json").read_bytes())
        marker["sha256"][name] = hashlib.sha256(raw).hexdigest()
        (out/"COMPLETE.json").write_bytes(canonical(marker))

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", "-m", "superhunter", *map(str,args)],
                              cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=40)

    def test_source_pins_are_exact(self):
        inventory = native_runtime.source_inventory()
        self.assertEqual(len(inventory), 5)
        self.assertEqual(inventory[-1]["git_blob"], "bbdcc5373adde03f0cad090e88bb9044aca8432a")
        self.assertIn("native_sources/diablo/scope.py", self.native.scope.__file__)
        self.assertIn("native_sources/nqc/capacity.py", self.native.capacity.__file__)

    def test_changed_native_bytes_rejected_before_import(self):
        source = self.root/"sources"
        shutil.copytree(native_runtime.ROOT, source)
        (source/"nqc/capacity.py").write_text("raise RuntimeError('must not execute')\n")
        with patch.object(native_runtime,"ROOT",source), self.assertRaisesRegex(ValueError,"source mismatch"):
            native_runtime.load_components()

    def test_missing_native_source_rejected(self):
        with patch.object(native_runtime,"ROOT",self.root), self.assertRaises(OSError):
            native_runtime.load_components()

    def test_real_nqc_and_diablo_functions_are_called(self):
        with patch.object(self.native.capacity, "solve", wraps=self.native.capacity.solve) as solve, \
             patch.object(self.native.scope.ScopeGuard, "assert_allowed", autospec=True,
                          side_effect=self.native.scope.ScopeGuard.assert_allowed) as scope:
            files = execute_local()
        self.assertEqual(solve.call_count, 6)  # five valid cases, one expected duplicate rejection
        self.assertEqual(scope.call_count, 5)
        self.assertEqual(strict_json(files["lab-result.json"])["audit_count"], 18)

    def test_expected_values_not_just_engine_agreement(self):
        expected = {"overlap": (["b","c"],150*WAD), "adjacent": (["a","b"],16*WAD),
                    "tie": (["a"],5*WAD), "large-integers": (["b"],10**36+18),
                    "resources": (["a","b"],5*WAD)}
        for name, rows in fixture_cases().items():
            with self.subTest(case=name):
                oracle = independent_reference(rows)
                self.assertEqual(oracle["selected_opportunity_ids"], expected[name][0])
                self.assertEqual(oracle["success_path_capacity_usd_wad"], str(expected[name][1]))

    def test_integer_precision_preserved(self):
        rows=fixture_cases()["large-integers"]
        result=self.native.capacity.solve(rows)
        self.assertEqual(result["success_path_capacity_usd_wad"],str(10**36+18))
        self.assertIsInstance(result["success_path_capacity_usd_wad"],str)

    def test_reference_does_not_call_native_solver(self):
        with patch.object(self.native.capacity,"solve",side_effect=AssertionError), \
             patch.object(self.native.capacity,"feasible",side_effect=AssertionError):
            self.assertEqual(independent_reference(fixture_cases()["tie"])["selected_opportunity_ids"],["a"])

    def test_reference_limits(self):
        for rows in ([], fixture_cases()["tie"]*5):
            with self.subTest(count=len(rows)), self.assertRaises(ValueError):
                independent_reference(rows)

    def test_boolean_integers_rejected_by_reference(self):
        rows=fixture_cases()["tie"]
        rows[0]["start_order"]=True
        with self.assertRaises(ValueError):
            independent_reference(rows)

    def test_reference_rejects_duplicate_ids(self):
        rows=fixture_cases()["tie"]
        rows[1]["opportunity_id"]="a"
        with self.assertRaises(ValueError):
            independent_reference(rows)

    def test_reference_capacity_mismatch_rejected(self):
        rows=fixture_cases()["tie"]
        rows[1]["claims"][0]["capacity"]=11
        with self.assertRaises(ValueError):
            independent_reference(rows)

    def test_nqc_disagreement_prevents_any_success_bundle(self):
        original=self.native.capacity.solve
        def incorrect(rows):
            result=original(rows)
            result["success_path_capacity_usd_wad"]="0"
            return result
        with patch.object(self.native.capacity,"solve",side_effect=incorrect), self.assertRaisesRegex(ValueError,"disagreement"):
            run_local(self.root/"bad")
        self.assertFalse((self.root/"bad/COMPLETE.json").exists())

    def test_bad_commitment_rejected(self):
        rows=fixture_cases()["tie"]
        result=self.native.capacity.solve(rows)
        result["commitment"]="0x"+"0"*64
        with self.assertRaisesRegex(ValueError,"commitment"):
            _check_native_result(result,independent_reference(rows))

    def test_native_scope_default_deny(self):
        guard=self.native.scope.ScopeGuard(in_scope=["*.lab.invalid"], out_scope=["blocked.lab.invalid"])
        for name in ("blocked.lab.invalid","lab.invalid","other.invalid","a.lab.invalid.other.invalid"):
            with self.subTest(name=name), self.assertRaises(PermissionError):
                guard.assert_allowed(name)

    def test_native_scope_check_is_audited(self):
        audit=self.native.audit.AuditLog()
        guard=self.native.scope.ScopeGuard(in_scope=["ok.lab.invalid"],audit_log=audit)
        guard.assert_allowed("ok.lab.invalid")
        self.assertEqual(len(audit),1)
        self.assertTrue(audit.verify().ok)

    def test_execution_without_sockets_or_child_processes(self):
        with patch("socket.socket",side_effect=AssertionError("network")), \
             patch("subprocess.run",side_effect=AssertionError("subprocess")):
            self.assertEqual(strict_json(execute_local()["lab-result.json"])["cases_passed"],5)

    def test_guard_rejects_external_execution_events(self):
        for event in ("socket.__new__","socket.connect","subprocess.Popen","os.system","os.exec","os.spawn","ctypes.dlopen"):
            with self.subTest(event=event), self.assertRaises(PermissionError):
                deny_external_execution(event,())
        deny_external_execution("open",())

    def test_bundle_verified_independently(self):
        result=verify_local_bundle(self.bundle())
        self.assertEqual(result["cases_passed"],5)
        self.assertFalse(result["vulnerability_confirmed"])

    def test_no_poc_or_live_finding_fields(self):
        result=strict_json(execute_local()["lab-result.json"])
        for field in ("forge_executed","mainnet_connected","program_scope_verified","vulnerability_confirmed"):
            self.assertIs(result[field],False)
        self.assertNotIn("finding",result)
        self.assertNotIn("final_severity",result)

    def test_missing_completion_marker_rejected(self):
        out=self.bundle()
        (out/"COMPLETE.json").unlink()
        with self.assertRaises(OSError):
            verify_local_bundle(out)

    def test_altered_artifact_rejected(self):
        out=self.bundle()
        with (out/"nqc-results.json").open("ab") as f:f.write(b" ")
        with self.assertRaisesRegex(ValueError,"digest mismatch"):
            verify_local_bundle(out)

    def test_resealed_wrong_values_still_rejected(self):
        out=self.bundle()
        self.alter(out,"nqc-results.json",lambda v:v["cases"][0]["nqc"].update(success_path_capacity_usd_wad="0"))
        with self.assertRaisesRegex(ValueError,"disagreement"):
            verify_local_bundle(out)

    def test_resealed_wrong_inputs_rejected(self):
        out=self.bundle()
        self.alter(out,"nqc-results.json",lambda v:v["cases"][0]["inputs"][0].update(start_order=50))
        with self.assertRaisesRegex(ValueError,"input/reference"):
            verify_local_bundle(out)

    def test_resealed_production_claim_rejected(self):
        out=self.bundle()
        self.alter(out,"lab-result.json",lambda v:v.update(vulnerability_confirmed=True))
        with self.assertRaisesRegex(ValueError,"production finding"):
            verify_local_bundle(out)

    def test_resealed_audit_mutation_rejected(self):
        out=self.bundle()
        self.alter(out,"diablo-audit.json",lambda v:v["entries"][0]["data"].update(run_id="different"))
        with self.assertRaisesRegex(ValueError,"audit chain"):
            verify_local_bundle(out)

    def test_audit_truncation_rejected(self):
        out=self.bundle()
        self.alter(out,"diablo-audit.json",lambda v:v["entries"].pop())
        with self.assertRaisesRegex(ValueError,"length"):
            verify_local_bundle(out)

    def test_source_provenance_mutation_rejected(self):
        out=self.bundle()
        self.alter(out,"source-provenance.json",lambda v:v["sources"][0].update(source_commit="a"*40))
        with self.assertRaisesRegex(ValueError,"provenance"):
            verify_local_bundle(out)

    def test_existing_directory_never_overwritten(self):
        out=self.bundle()
        before=(out/"COMPLETE.json").read_bytes()
        with self.assertRaises(FileExistsError):
            run_local(out)
        self.assertEqual((out/"COMPLETE.json").read_bytes(),before)

    def test_private_permissions(self):
        out=self.bundle()
        self.assertEqual(out.stat().st_mode & 0o777,0o700)
        for item in out.iterdir():self.assertEqual(item.stat().st_mode & 0o777,0o600)

    def test_numeric_results_deterministic(self):
        one=execute_local();two=execute_local()
        self.assertEqual(one["nqc-results.json"],two["nqc-results.json"])
        self.assertNotEqual(strict_json(one["lab-result.json"])["run_id"],strict_json(two["lab-result.json"])["run_id"])

    def test_cli_complete_run_and_verification(self):
        out=self.root/"cli"
        first=self.cli("local-lab","--out",out)
        self.assertEqual(first.returncode,0,first.stdout+first.stderr)
        second=self.cli("verify-lab","--bundle",out)
        self.assertEqual(second.returncode,0,second.stdout+second.stderr)
        self.assertFalse(json.loads(second.stdout)["vulnerability_confirmed"])

    def test_cli_rejects_rpc_and_target_parameters(self):
        for parameter in ("--rpc","--target","--poc","--engine"):
            with self.subTest(parameter=parameter):
                result=self.cli("local-lab","--out",self.root/"unknown",parameter,"untrusted")
                self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.root/"unknown").exists())

    def test_worker_timeout_reported_as_error(self):
        with patch("subprocess.run",side_effect=subprocess.TimeoutExpired("fixed-worker",30)),redirect_stdout(io.StringIO()) as stream:
            code=lab_cli.main(["--out",str(self.root/"timeout")])
        self.assertEqual(code,2)
        self.assertEqual(json.loads(stream.getvalue())["status"],"LOCAL_INTEGRATION_ERROR")

    def test_worker_error_never_promoted(self):
        fake=subprocess.CompletedProcess([],1,stdout='{"status":"LOCAL_INTEGRATION_PASS"}',stderr="secret")
        with patch("subprocess.run",return_value=fake),redirect_stdout(io.StringIO()) as stream:
            code=lab_cli.main(["--out",str(self.root/"failure")])
        self.assertEqual(code,2)
        self.assertNotIn("secret",stream.getvalue())

    def test_launcher_does_not_forward_environment_secrets(self):
        fake=subprocess.CompletedProcess([],0,stdout='{"status":"LOCAL_INTEGRATION_PASS","vulnerability_confirmed":false}')
        with patch("subprocess.run",return_value=fake) as run,redirect_stdout(io.StringIO()):
            lab_cli.main(["--out",str(self.root/"env")])
        self.assertEqual(set(run.call_args.kwargs["env"]),{"LANG","LC_ALL"})
        self.assertIn("-I",run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["timeout"],30)


if __name__ == "__main__":
    unittest.main()
