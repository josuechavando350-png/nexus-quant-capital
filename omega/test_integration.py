"""Offline adversarial tests. Real archive tests require explicit artifact paths."""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audit import verify_plan
from census_bridge import build_report, store_report, AUDITOR_PATH
from integrity import canonical, digest, git_blob, load_pinned_python, read_regular, strict_json
from isolation import EXTENSION_FILES, inventory, project_repository, verify_repository

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def synthetic_report():
    result = {"schema": "nqc.omega.census-bridge.v1", "decision": "OBSERVAR",
              "census_closed": False, "phase_advance_authorized": False,
              "signing_authorized": False, "broadcast_authorized": False,
              "spending_authorized": False, "fixture": "SYNTHETIC_NOT_MARKET_EVIDENCE"}
    result["report_commitment_sha256"] = digest(canonical(result))
    return result


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.plan = strict_json((HERE / "architecture_v3.json").read_bytes())

    def test_malformed_component_matrix_1440_cases(self):
        bad = (None, [], {}, True, False, 0, 1.5, "")
        for index in range(36):
            for key in ("id", "phase", "layer", "name", "omega_verification"):
                for value in bad:
                    with self.subTest(index=index, key=key, value=value):
                        plan = copy.deepcopy(self.plan)
                        plan["components"][index][key] = value
                        self.assertTrue(verify_plan(plan))

    def test_unhashable_acceptance_is_rejection_not_exception(self):
        for value in ([{}], [[]], [1], None, True):
            plan = copy.deepcopy(self.plan)
            plan["acceptance"]["Census"] = value
            self.assertIn("phase_gates_missing_or_changed", verify_plan(plan))

    def test_gas_budget_mutations_fail_closed(self):
        for key in self.plan["canary_gas_budget_mxn"]:
            for value in (None, True, [], {}, "2000", 0, 999999):
                plan = copy.deepcopy(self.plan)
                plan["canary_gas_budget_mxn"][key] = value
                self.assertIn("canary_gas_budget_changed", verify_plan(plan))

    def test_missing_gas_policy_is_blocked(self):
        del self.plan["canary_gas_budget_mxn"]
        self.assertIn("canary_gas_budget_changed", verify_plan(self.plan))

    def test_duplicate_keys_are_blocked_at_any_depth(self):
        for raw in (b'{"x":1,"x":2}', b'{"a":{"x":1,"x":2}}'):
            with self.assertRaisesRegex(ValueError, "duplicate_json_key"):
                strict_json(raw)

    def test_nonfinite_values_are_blocked(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaisesRegex(ValueError, "nonfinite_json_number"):
                strict_json(('{"value":' + value + '}').encode())

    def test_census_map_has_nine_unclosed_components(self):
        mapping = strict_json((HERE / "census_map.json").read_bytes())
        self.assertEqual(sorted(c["id"] for c in mapping["components"]), [1, 6, 7, 8, 10, 24, 25, 29, 32])
        self.assertEqual(mapping["certified_components"], 0)
        self.assertIs(mapping["census_closed"], False)
        self.assertTrue(all(c["component_certified"] is False for c in mapping["components"]))

    def test_existing_architecture_still_has_no_live_permissions(self):
        self.assertEqual(verify_plan(self.plan), [])
        self.assertTrue(all(value is False for value in self.plan["safety"].values()))


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.root = self.temp / "repo"
        for name in EXTENSION_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        self.source = self.root / "ci/nqc-census/retained.py"
        self.source.parent.mkdir(parents=True, exist_ok=True)
        self.source.write_bytes(b"# immutable fixture, not original market evidence\n")
        self.source.chmod(0o755)

    def test_exact_inventory_is_allowed(self):
        self.assertEqual(len(inventory(self.root)), len(EXTENSION_FILES) + 1)

    def test_extra_omega_file_is_not_ignored(self):
        (self.root / "omega/extra.py").write_text("not approved\n")
        with self.assertRaisesRegex(ValueError, "unreviewed_omega_path"):
            inventory(self.root)

    def test_extra_omega_directory_is_not_ignored(self):
        (self.root / "omega/newdir").mkdir()
        with self.assertRaisesRegex(ValueError, "unreviewed_omega_path"):
            inventory(self.root)

    def test_missing_extension_file_is_blocked(self):
        (self.root / "omega/README.md").unlink()
        with self.assertRaisesRegex(ValueError, "missing_omega_paths"):
            inventory(self.root)

    def test_symlink_in_extension_is_blocked(self):
        path = self.root / "omega/README.md"
        path.unlink()
        path.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "nonregular_repository_entry"):
            inventory(self.root)

    def test_symlink_in_legacy_is_blocked(self):
        (self.root / "ci/link").symlink_to(self.temp, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "nonregular_repository_entry"):
            inventory(self.root)

    def test_projection_keeps_original_bytes_and_executable_mode(self):
        destination = self.temp / "copy"
        project_repository(self.root, destination)
        target = destination / self.source.relative_to(self.root)
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        self.assertEqual(target.stat().st_mode & 0o777, 0o755)
        self.assertFalse((destination / "omega").exists())
        self.assertTrue((self.root / "omega").exists())

    def test_projection_does_not_hide_forbidden_extra_roots(self):
        for name in (".github/workflows/evil.yml", "apps/client.txt", "runtime/new.py", "rogue.txt"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("must reach and fail the original verifier\n")
        destination = self.temp / "copy"
        project_repository(self.root, destination)
        for name in (".github/workflows/evil.yml", "apps/client.txt", "runtime/new.py", "rogue.txt"):
            self.assertEqual((destination / name).read_bytes(), (self.root / name).read_bytes())

    def test_projection_cannot_write_into_source(self):
        with self.assertRaisesRegex(ValueError, "projection_overlaps_source"):
            project_repository(self.root, self.root / "copy")

    def test_altered_verifier_is_not_executed(self):
        source = self.temp / "untrusted.py"
        source.write_text("raise AssertionError('must not execute')\n")
        with self.assertRaisesRegex(ValueError, "pinned_source_mismatch"):
            load_pinned_python(source, "0" * 40, "test_untrusted")

    def test_incomplete_checkout_cannot_pass_full_isolation(self):
        path = self.root / "migration/verify_isolation.py"
        path.parent.mkdir(parents=True)
        path.write_bytes((ROOT / "migration/verify_isolation.py").read_bytes())
        with self.assertRaises(FileNotFoundError):
            verify_repository(self.root)

    def test_file_size_and_symlink_input_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "input_too_large"):
            read_regular(self.source, limit=1)
        link = self.temp / "link"
        link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "symlink_input"):
            read_regular(link)


class EvidenceStoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.report = synthetic_report()

    def test_content_addressed_store_is_idempotent(self):
        path = store_report(self.root, self.report)
        self.assertEqual(path, store_report(self.root, self.report))
        self.assertEqual(path.read_bytes(), canonical(self.report))
        self.assertEqual(path.stem, self.report["report_commitment_sha256"])
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [path.name])

    def test_invalid_report_commitment_is_blocked(self):
        self.report["fixture"] = "changed"
        with self.assertRaisesRegex(ValueError, "report_commitment_mismatch"):
            store_report(self.root, self.report)

    def test_existing_tampered_evidence_is_never_overwritten(self):
        path = store_report(self.root, self.report)
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "existing_evidence_mismatch"):
            store_report(self.root, self.report)
        self.assertEqual(path.read_bytes(), b"tampered")

    def test_output_directory_symlink_is_blocked(self):
        path = self.root / "symlink"
        path.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink_output_directory"):
            store_report(path, self.report)

    def test_go_or_spending_claim_cannot_be_stored(self):
        for key, value in (("decision", "GO"), ("census_closed", True), ("spending_authorized", True)):
            report = dict(self.report)
            report[key] = value
            with self.assertRaisesRegex(ValueError, "unsupported_report_authority"):
                store_report(self.root, report)

    def test_link_failure_leaves_no_partial_final_file(self):
        with patch("os.link", side_effect=OSError("injected filesystem failure")):
            with self.assertRaises(OSError):
                store_report(self.root, self.report)
        self.assertEqual(list(self.root.iterdir()), [])


@unittest.skipUnless(os.environ.get("NQC_D15_ARCHIVE") and os.environ.get("NQC_D16_ARCHIVE"),
                     "original artifact paths not supplied; this is NOT a real-data pass")
class RealArchiveTests(unittest.TestCase):
    def setUp(self):
        self.d15 = Path(os.environ["NQC_D15_ARCHIVE"])
        self.d16 = Path(os.environ["NQC_D16_ARCHIVE"])

    def test_real_replay_is_deterministic_and_never_go(self):
        left = build_report(self.d15, self.d16)
        right = build_report(self.d15, self.d16)
        self.assertEqual(canonical(left), canonical(right))
        self.assertEqual(left["decision"], "OBSERVAR")
        self.assertIs(left["phase_advance_authorized"], False)
        baseline = left["historical_baseline"]
        self.assertEqual(baseline["historical_winner_transaction_count"], 127)
        self.assertEqual(baseline["historical_liquidation_event_count"], 139)
        self.assertEqual(baseline["audit_commitment_sha256"], "89ebe73a36127f0bfec5f722d5ca4ece0e7e15c8318d68f33f38eeff5ae6a5ca")
        self.assertIsNone(baseline["nexus_monthly_pnl_estimate_usd_wad"])
        self.assertIs(baseline["all_execution_costs_reconciled"], False)
        self.assertTrue(all(v is None for v in left["omega_census_metrics_not_established"].values()))

    def test_real_replay_performs_no_socket_or_subprocess_operations(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                patch("subprocess.Popen", side_effect=AssertionError("subprocess forbidden")):
            self.assertEqual(build_report(self.d15, self.d16)["decision"], "OBSERVAR")

    def test_tampered_original_archive_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "changed.zip"
            path.write_bytes(self.d15.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "artifact_sha256_mismatch"):
                build_report(path, self.d16)

    def test_missing_original_archive_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileNotFoundError):
                build_report(Path(temp) / "missing.zip", self.d16)

    def test_substituted_auditor_is_blocked_before_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / AUDITOR_PATH
            path.parent.mkdir(parents=True)
            path.write_text("raise AssertionError('must not run')\n")
            with self.assertRaisesRegex(ValueError, "pinned_source_mismatch"):
                build_report(self.d15, self.d16, root=root)

    def test_report_file_roundtrip_with_real_data(self):
        with tempfile.TemporaryDirectory() as temp:
            report = build_report(self.d15, self.d16)
            path = store_report(Path(temp), report)
            self.assertEqual(strict_json(path.read_bytes()), report)


if __name__ == "__main__":
    unittest.main()
