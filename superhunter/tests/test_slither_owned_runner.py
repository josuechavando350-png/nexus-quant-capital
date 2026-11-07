"""Contract tests for the fixed OWNED Slither process adapter.

Mocked process events are NOT executions of Slither. Actual scanner admission
requires slither-analyzer 0.11.6 and pinned official solc 0.8.30 on Linux.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import io
import json
import os
import tempfile
import unittest

from superhunter import slither_owned_runner as scan
from superhunter import slither_owned_worker as worker
from superhunter.safe_io import canonical


class SlitherOwnedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.solc = self.root / "solc-input"
        self.out = self.root / "verified-import"
        self.report = {"success": True, "error": None, "results": {"detectors": []}}
        self.calls = []
        self.imported = []

    def fake_run(self, command, *, cwd, env, timeout, stdout, stderr):
        self.calls.append((command, cwd, env, timeout))
        (cwd / scan.REPORT_NAME).write_bytes(canonical(self.report))
        return SimpleNamespace(returncode=0)

    def imported_report(self, report, context, sources, out):
        self.imported.append((report, json.loads(context.read_text()), sources, out))
        raw = report.read_bytes()
        return {"normalization_complete": True, "report_sha256": scan.sha(raw),
                "source_sha256": {scan.SOURCE_NAME: scan.sha(scan.OWNED_SOURCE)},
                "unique_alert_count": 1, "source_bound_alerts": 1}

    def mocks(self, process=None, normalized=None, imported=None):
        self.enterContext(patch.object(
            scan, "_package_state",
            return_value={"package": "slither-analyzer", "required_version": "0.11.6",
                          "installed_version": "0.11.6", "matches": True}))
        self.enterContext(patch.object(scan.native_compile, "read_pinned_binary",
                                       return_value=b"\x7fELF\x01pinned-fixture"))
        self.enterContext(patch.object(scan.owned_process, "run",
                                       side_effect=process or self.fake_run))
        self.enterContext(patch.object(scan.static_review, "normalize",
                                       return_value=normalized or {"normalization_complete": True,
                            "source_bound_alerts": 1, "unique_alert_count": 1,
                            "alerts": [{"check": "tx-origin"}]}))
        self.enterContext(patch.object(scan.static_review, "import_report",
                                       side_effect=imported or self.imported_report))

    def test_fixture_content_identity_and_detector_are_fixed(self):
        self.assertEqual(scan.DETECTOR, "tx-origin")
        self.assertEqual(scan.sha(scan.OWNED_SOURCE),
                         "ef5475a13e367bef34010e339c082c85383ab85e4f229cd607899f5f52ce0c64")
        self.assertIn(b"tx.origin", scan.OWNED_SOURCE)
        self.assertLess(len(scan.OWNED_SOURCE), scan.MAX_SOLIDITY_BYTES)

    def test_readonly_doctor_blocks_missing_scanner(self):
        with patch.object(scan, "_package_state", return_value={"matches": False}), \
             patch.object(scan.native_compile, "read_pinned_binary") as binary, \
             patch("socket.socket", side_effect=AssertionError("network forbidden")):
            report = scan.doctor(self.solc)
        self.assertEqual(report["status"], "OWNED_SLITHER_BLOCKED")
        self.assertFalse(report["scanner_executed"])
        self.assertFalse(report["targets_external"])
        binary.assert_not_called()

    def test_tool_launch_has_only_fixed_source_and_flags(self):
        self.mocks()
        result = scan.run_owned(self.solc, self.out, repo_commit="a" * 40)
        self.assertEqual(result["status"], "OWNED_SLITHER_IMPORTED_UNVERIFIED")
        self.assertFalse(result["vulnerability_confirmed"])
        self.assertFalse(result["independent_producer_authentication"])
        self.assertFalse(result["execution_replayed_independently"])
        self.assertEqual(len(self.calls), 1)
        command, root, env, limit = self.calls[0]
        self.assertEqual(command[:3], [scan.sys.executable, "-I", "-B"])
        self.assertEqual(command[3], str(scan.ROOT / "slither_owned_worker.py"))
        self.assertEqual(command[4], str(root))
        self.assertEqual(limit, 90)
        self.assertEqual(set(env), {"LANG", "LC_ALL", "HOME", "PATH", "PYTHONDONTWRITEBYTECODE"})
        self.assertEqual(self.imported[0][3], self.out)
        context = self.imported[0][1]
        self.assertEqual(context["scope_id"], "owned-fixed-local-fixture")
        self.assertEqual(context["tool"]["version"], "0.11.6")
        self.assertEqual(context["sources"], {"Owned.sol": scan.sha(scan.OWNED_SOURCE)})
        self.assertEqual(context["repository"]["commit"], "a" * 40)

    def test_invalid_commit_never_starts_tool(self):
        self.mocks()
        for value in ("", "A" * 40, "b" * 39, "../../secret"):
            with self.assertRaisesRegex(ValueError, "COMMIT"):
                scan.run_owned(self.solc, self.out, repo_commit=value)
        self.assertEqual(self.calls, [])

    def test_existing_bundle_not_overwritten(self):
        self.mocks()
        self.out.mkdir()
        with self.assertRaisesRegex(ValueError, "OUTPUT"):
            scan.run_owned(self.solc, self.out, repo_commit="a" * 40)
        self.assertEqual(self.calls, [])

    def test_checkout_output_rejected(self):
        self.mocks()
        with self.assertRaisesRegex(ValueError, "OUTPUT"):
            scan.run_owned(self.solc, scan.ROOT / "should-not-write", repo_commit="a" * 40)
        self.assertEqual(self.calls, [])

    def test_process_failure_does_not_import(self):
        self.mocks(process=lambda *args, **kwargs: SimpleNamespace(returncode=5))
        with self.assertRaisesRegex(ValueError, "PROCESS_FAILED"):
            scan.run_owned(self.solc, self.out, repo_commit="a" * 40)
        self.assertEqual(self.imported, [])
        self.assertFalse(self.out.exists())

    def test_timeout_does_not_import(self):
        import subprocess
        def fail(*args, **kwargs):
            raise subprocess.TimeoutExpired(["fixed"], 90)
        self.mocks(process=fail)
        with self.assertRaises(subprocess.TimeoutExpired):
            scan.run_owned(self.solc, self.out, repo_commit="a" * 40)
        self.assertEqual(self.imported, [])

    def test_changed_owned_source_rejected(self):
        def fake(*args, cwd, **kwargs):
            (cwd / scan.SOURCE_NAME).unlink()
            (cwd / scan.SOURCE_NAME).write_bytes(b"modified")
            (cwd / scan.REPORT_NAME).write_bytes(canonical(self.report))
            return SimpleNamespace(returncode=0)
        self.mocks(process=fake)
        with self.assertRaisesRegex(ValueError, "CHANGED"):
            scan.run_owned(self.solc, self.out, repo_commit="a" * 40)
        self.assertEqual(self.imported, [])

    def test_corrupted_slither_envelope_rejected(self):
        self.report["success"] = False
        self.mocks()
        with self.assertRaisesRegex(ValueError, "NOT_COMPLETE"):
            scan.run_owned(self.solc, self.out, repo_commit="a" * 40)
        self.assertEqual(self.imported, [])

    def test_incomplete_source_mapping_fails_closed(self):
        self.mocks(normalized={"normalization_complete": False})
        with self.assertRaisesRegex(ValueError, "BINDING_INCOMPLETE"):
            scan.run_owned(self.solc, self.out, repo_commit="a" * 40)
        self.assertEqual(self.imported, [])

    def test_import_result_drift_is_rejected(self):
        def fake_import(*args, **kwargs):
            return {"normalization_complete": True,
                    "report_sha256": "f" * 64,
                    "source_sha256": {"Owned.sol": scan.sha(scan.OWNED_SOURCE)},
                    "unique_alert_count": 0, "source_bound_alerts": 0}
        self.mocks(imported=fake_import)
        with self.assertRaisesRegex(ValueError, "IMPORT_DIVERGED"):
            scan.run_owned(self.solc, self.out, repo_commit="a" * 40)

    def test_direct_worker_rejects_non_fixture(self):
        (self.root / "Owned.sol").write_text("contract Altered {}")
        (self.root / "solc").write_bytes(b"\x7fELFfake")
        with patch.object(worker.os, "execv", side_effect=AssertionError("executed")):
            self.assertEqual(worker.main([str(self.root)]), 2)

    def test_silent_scanner_does_not_pass_known_positive(self):
        self.mocks(normalized={"normalization_complete": True,
                               "source_bound_alerts": 0, "unique_alert_count": 0,
                               "alerts": []})
        with self.assertRaisesRegex(ValueError, "POSITIVE_CONTROL_NOT_DETECTED"):
            scan.run_owned(self.solc, self.out, repo_commit="a" * 40)
        self.assertEqual(self.imported, [])

    def test_malformed_alert_does_not_satisfy_positive_control(self):
        self.mocks(normalized={"normalization_complete": True,
                               "source_bound_alerts": 1, "unique_alert_count": 1,
                               "alerts": [{"check": "unrelated-check"}]})
        with self.assertRaisesRegex(ValueError, "POSITIVE_CONTROL_NOT_DETECTED"):
            scan.run_owned(self.solc, self.out, repo_commit="a" * 40)
        self.assertEqual(self.imported, [])

    def test_worker_rejects_symlinked_source(self):
        other = self.root / "other.sol"
        other.write_bytes(scan.OWNED_SOURCE)
        (self.root / "Owned.sol").symlink_to(other)
        (self.root / "solc").write_bytes(b"invalid")
        with patch.object(worker.os, "execv", side_effect=AssertionError("executed")):
            self.assertEqual(worker.main([str(self.root)]), 2)

    def test_worker_rejects_oversized_source_and_compiler_before_exec(self):
        source = self.root / "Owned.sol"
        compiler = self.root / "solc"
        source.write_bytes(scan.OWNED_SOURCE)
        compiler.write_bytes(b"x")
        with patch.object(worker.os, "execv", side_effect=AssertionError("executed")):
            source.write_bytes(b"x" * 4097)
            self.assertEqual(worker.main([str(self.root)]), 2)
            source.write_bytes(scan.OWNED_SOURCE)
            # Preserve the exact original 64,000,001 zero bytes. Prepare them
            # outside the worker, which retains its 20 MiB file-write cap.
            import os
            from superhunter import qa_inputs
            with qa_inputs.oversized_zero_input() as prepared:
                compiler.unlink()
                os.link(prepared, compiler, follow_symlinks=False)
                self.assertEqual(compiler.stat().st_size, 64_000_001)
                self.assertEqual(worker.main([str(self.root)]), 2)
                self.assertIsNone(worker._file_sha256(compiler, 64_000_000))

    def test_prepared_large_input_rejects_symlink_and_wrong_size(self):
        from superhunter import qa_inputs
        small = self.root/'small'; small.write_bytes(b'\0'); small.chmod(0o400)
        with self.assertRaisesRegex(ValueError, 'QA_INPUT_METADATA_MISMATCH'):
            qa_inputs.validate(small)
        link = self.root/'link'; link.symlink_to(small)
        with self.assertRaises(OSError):
            qa_inputs.validate(link)

    def test_prepared_large_input_rejects_relative_path_and_wrong_digest(self):
        from superhunter import qa_inputs
        with self.assertRaisesRegex(ValueError, 'QA_INPUT_NOT_ABSOLUTE'):
            qa_inputs.validate(Path('relative-input'))
        # Hash rejection uses the fixed real input, without changing its bytes.
        with qa_inputs.oversized_zero_input() as prepared:
            with patch.object(qa_inputs, 'SHA256', '0'*64):
                with self.assertRaisesRegex(ValueError, 'QA_INPUT_CONTENT_MISMATCH'):
                    qa_inputs.validate(prepared)

    def test_cli_failure_redacts_paths(self):
        with redirect_stdout(io.StringIO()) as stream:
            code = scan.main(["run-owned-slither", "--solc", str(self.root / "SECRET_PATH"),
                              "--out", str(self.out), "--repo-commit", "bad"])
        self.assertEqual(code, 2)
        self.assertNotIn("SECRET_PATH", stream.getvalue())
        self.assertEqual(json.loads(stream.getvalue())["vulnerability_confirmed"], False)


if __name__ == "__main__":
    unittest.main()
