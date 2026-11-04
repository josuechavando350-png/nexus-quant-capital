"""Regressions for this user-owned integration and its finite numerical domain."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter.bounded_capacity import EXPECTED_CASES, cases, run_bounded, verify_bounded
from superhunter.capability_status import load_registry, validate_registry
from superhunter.evidence_links import digest
from superhunter.local_lab import run_local, verify_local_bundle
from superhunter.native_runtime import load_components
from superhunter.safe_io import canonical, strict_json
from superhunter.system_check import run_system, verify_system


class ConnectedChecks(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.native = load_components()

    def local(self):
        root = self.root / "local"
        run_local(root)
        return root

    def reseal(self, root, changes):
        marker = strict_json((root / "COMPLETE.json").read_bytes())
        for name, value in changes.items():
            raw = canonical(value)
            (root / name).write_bytes(raw)
            marker["sha256"][name] = hashlib.sha256(raw).hexdigest()
        (root / "COMPLETE.json").write_bytes(canonical(marker))

    def rewrite_audit(self, root, change):
        audit = strict_json((root / "diablo-audit.json").read_bytes())
        change(audit["entries"])
        previous = "0" * 64
        for entry in audit["entries"]:
            entry["prev_hash"] = previous
            entry["hash"] = self.native.audit.compute_hash(entry["index"], entry["timestamp"],
                                                           entry["event"], entry["data"], previous)
            previous = entry["hash"]
        result = strict_json((root / "lab-result.json").read_bytes())
        result["audit_head"] = previous
        self.reseal(root, {"diablo-audit.json": audit, "lab-result.json": result})

    def test_all_stage_links_exist(self):
        root = self.local()
        result = verify_local_bundle(root)
        graph = strict_json((root / "evidence-graph.json").read_bytes())
        self.assertEqual(result["linked_nodes"], 30)
        self.assertEqual(result["evidence_root_sha256"], graph["root_sha256"])
        known = set()
        for node in graph["nodes"]:
            self.assertTrue(set(node["depends_on"]).issubset(known))
            known.add(node["id"])
        self.assertIn("scope-negative", known)
        self.assertIn("duplicate-negative", known)
        self.assertEqual(len(strict_json((root / "diablo-audit.json").read_bytes())["entries"]), 24)

    def test_resealed_deny_cannot_be_success(self):
        root = self.local()
        self.rewrite_audit(root, lambda entries: entries[1]["data"].update(decision="DENY"))
        with self.assertRaisesRegex(ValueError, "linked evidence mismatch.*scope.check"):
            verify_local_bundle(root)

    def test_scope_is_bound_to_the_same_case(self):
        root = self.local()
        self.rewrite_audit(root, lambda entries: entries[1]["data"].update(target="other.lab.invalid"))
        with self.assertRaisesRegex(ValueError, "linked evidence mismatch"):
            verify_local_bundle(root)

    def test_input_hash_cannot_be_unrelated(self):
        root = self.local()
        self.rewrite_audit(root, lambda entries: entries[2]["data"].update(input_sha256="a" * 64))
        with self.assertRaisesRegex(ValueError, "lab.nqc.start"):
            verify_local_bundle(root)

    def test_output_hash_cannot_be_unrelated(self):
        root = self.local()
        self.rewrite_audit(root, lambda entries: entries[3]["data"].update(output_commitment="0x" + "a" * 64))
        with self.assertRaisesRegex(ValueError, "lab.nqc.finish"):
            verify_local_bundle(root)

    def test_reference_hash_cannot_be_unrelated(self):
        root = self.local()
        self.rewrite_audit(root, lambda entries: entries[4]["data"].update(reference_sha256="b" * 64))
        with self.assertRaisesRegex(ValueError, "lab.reference.finish"):
            verify_local_bundle(root)

    def test_reference_disagreement_not_a_success(self):
        root = self.local()
        self.rewrite_audit(root, lambda entries: entries[4]["data"].update(matched=False))
        with self.assertRaisesRegex(ValueError, "lab.reference.finish"):
            verify_local_bundle(root)

    def test_negative_scope_is_actually_negative(self):
        root = self.local()
        self.rewrite_audit(root, lambda entries: entries[-3]["data"].update(decision="ALLOW"))
        with self.assertRaisesRegex(ValueError, "scope.check"):
            verify_local_bundle(root)

    def test_duplicate_check_has_recorded_rejection(self):
        root = self.local()
        self.rewrite_audit(root, lambda entries: entries[-2]["data"].update(error="no error"))
        with self.assertRaisesRegex(ValueError, "lab.nqc.reject"):
            verify_local_bundle(root)

    def test_event_name_cannot_claim_another_stage(self):
        root = self.local()
        self.rewrite_audit(root, lambda entries: entries[3].update(event="lab.placeholder.pass"))
        with self.assertRaisesRegex(ValueError, "lab.nqc.finish"):
            verify_local_bundle(root)

    def test_bool_index_is_not_an_integer_index(self):
        root = self.local()
        self.rewrite_audit(root, lambda entries: entries[1].update(index=True))
        with self.assertRaisesRegex(ValueError, "linked evidence mismatch"):
            verify_local_bundle(root)

    def test_timestamps_require_timezone(self):
        root = self.local()
        self.rewrite_audit(root, lambda entries: entries[1].update(timestamp="2026-11-03T00:00:00"))
        with self.assertRaisesRegex(ValueError, "timezone"):
            verify_local_bundle(root)

    def test_event_time_cannot_be_outside_run(self):
        root = self.local()
        self.rewrite_audit(root, lambda entries: entries[1].update(timestamp="2000-01-01T00:00:00+00:00"))
        with self.assertRaisesRegex(ValueError, "time/order"):
            verify_local_bundle(root)

    def test_execution_flag_cannot_disagree(self):
        root = self.local()
        result = strict_json((root / "lab-result.json").read_bytes())
        result["local_component_execution"] = False
        self.reseal(root, {"lab-result.json": result})
        with self.assertRaisesRegex(ValueError, "run verdict"):
            verify_local_bundle(root)

    def test_float_case_count_not_silently_coerced(self):
        root = self.local()
        result = strict_json((root / "lab-result.json").read_bytes())
        result["cases_passed"] = 5.0
        self.reseal(root, {"lab-result.json": result})
        with self.assertRaisesRegex(ValueError, "run verdict"):
            verify_local_bundle(root)

    def test_nqc_extra_claims_rejected_even_with_new_hash(self):
        root = self.local()
        casefile = strict_json((root / "nqc-results.json").read_bytes())
        result = casefile["cases"][0]["nqc"]
        result["bounty_confirmed"] = True
        result["commitment"] = "0x" + digest({k:v for k,v in result.items() if k != "commitment"})
        self.reseal(root, {"nqc-results.json": casefile})
        self.rewrite_audit(root, lambda entries: entries[3]["data"].update(output_commitment=result["commitment"]))
        with self.assertRaisesRegex(ValueError, "NQC result envelope"):
            verify_local_bundle(root)

    def test_missing_graph_rejected(self):
        root = self.local()
        (root / "evidence-graph.json").unlink()
        with self.assertRaises(OSError):
            verify_local_bundle(root)

    def test_graph_missing_dependency_rejected(self):
        root = self.local()
        graph = strict_json((root / "evidence-graph.json").read_bytes())
        graph["nodes"][-1]["depends_on"] = []
        self.reseal(root, {"evidence-graph.json": graph})
        with self.assertRaisesRegex(ValueError, "dependency graph"):
            verify_local_bundle(root)

    def test_graph_cycle_rejected(self):
        root = self.local()
        graph = strict_json((root / "evidence-graph.json").read_bytes())
        graph["nodes"][0]["depends_on"] = ["verdict"]
        self.reseal(root, {"evidence-graph.json": graph})
        with self.assertRaisesRegex(ValueError, "dependency graph"):
            verify_local_bundle(root)

    def test_graph_from_other_run_rejected(self):
        root = self.local()
        other = self.root / "other"
        run_local(other)
        graph = strict_json((other / "evidence-graph.json").read_bytes())
        self.reseal(root, {"evidence-graph.json": graph})
        with self.assertRaisesRegex(ValueError, "dependency graph"):
            verify_local_bundle(root)

    def test_declared_domain_exact_and_unique(self):
        domain = list(cases())
        self.assertEqual(len(domain), EXPECTED_CASES)
        self.assertEqual(len({digest(x) for x in domain}), EXPECTED_CASES)
        self.assertEqual(EXPECTED_CASES, (3 * 2 * 2) ** 3)

    def test_every_finite_case_executes_native_function(self):
        with patch.object(self.native.capacity, "solve", wraps=self.native.capacity.solve) as solve:
            certificate = run_bounded()
        self.assertEqual(solve.call_count, 1728)
        self.assertEqual(certificate["reference_subsets_enumerated"], 13824)
        self.assertFalse(certificate["universal_security_proof"])

    def test_certificate_recalculation_does_not_use_native_solver(self):
        certificate = run_bounded()
        with patch.object(self.native.capacity, "solve", side_effect=AssertionError("native called during verification")):
            self.assertEqual(verify_bounded(certificate), digest(certificate))

    def test_no_self_approved_native_output(self):
        real = self.native.capacity.solve
        def wrong(rows):
            result = real(rows)
            result["selected_opportunity_count"] = 99
            return result
        with patch.object(self.native.capacity, "solve", side_effect=wrong), self.assertRaisesRegex(ValueError, "bounded numerical case"):
            run_bounded()

    def test_partial_enumeration_never_passes(self):
        with patch("superhunter.bounded_capacity.cases", return_value=iter([next(cases())])), self.assertRaisesRegex(ValueError, "incomplete"):
            run_bounded()

    def test_changed_certificate_domain_rejected(self):
        certificate = deepcopy(run_bounded())
        certificate["domain"]["values"].append(3)
        with self.assertRaisesRegex(ValueError, "finite-domain certificate"):
            verify_bounded(certificate)

    def test_changed_transcript_rejected(self):
        certificate = run_bounded()
        certificate["transcript_sha256"] = "c" * 64
        with self.assertRaises(ValueError):
            verify_bounded(certificate)

    def test_universal_claim_rejected(self):
        certificate = run_bounded()
        certificate["universal_security_proof"] = True
        with self.assertRaises(ValueError):
            verify_bounded(certificate)

    def test_complete_registry_without_false_completion(self):
        summary = validate_registry(load_registry())
        self.assertEqual(summary, {"listed":50, "implemented_end_to_end":0,
                                  "states":{"pending":32,"redesign":15,"partial":3}})

    def test_registry_missing_item_rejected(self):
        plan = load_registry(); plan["capabilities"].pop()
        with self.assertRaisesRegex(ValueError, "exactly 50"):
            validate_registry(plan)

    def test_registry_duplicate_id_rejected(self):
        plan = load_registry(); plan["capabilities"][1]["id"] = 1
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_registry(plan)

    def test_registry_cycles_rejected(self):
        plan = load_registry(); plan["capabilities"][0]["dependencies"] = [2]
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_registry(plan)

    def test_registry_cannot_mark_unknown_function_completed(self):
        plan = load_registry(); plan["capabilities"][0]["status"] = "implemented"
        with self.assertRaisesRegex(ValueError, "no evidence"):
            validate_registry(plan)

    def test_partial_feature_needs_actual_code(self):
        plan = load_registry(); plan["capabilities"][36]["code_refs"] = []
        with self.assertRaisesRegex(ValueError, "actual code reference"):
            validate_registry(plan)

    def test_registry_cannot_reference_missing_code(self):
        plan = load_registry(); plan["capabilities"][36]["code_refs"] = ["missing_real_module.py"]
        with self.assertRaises((ValueError, OSError)):
            validate_registry(plan)

    def test_registry_cannot_reference_outside_root(self):
        plan = load_registry(); plan["capabilities"][36]["code_refs"] = ["../outside.py"]
        with self.assertRaises(ValueError):
            validate_registry(plan)

    def test_system_checks_and_verifies_all_components(self):
        out = self.root / "system"
        result = run_system(out)
        self.assertEqual(result, verify_system(out))
        self.assertEqual(result["linked_nodes"], 30)
        self.assertEqual(result["bounded_cases"], 1728)
        self.assertFalse(result["vulnerability_confirmed"])
        self.assertFalse(result["producer_authenticated"])
        text = (out / "CHECKLIST.md").read_text()
        for n in range(1,51):
            self.assertRegex(text, rf"### [○◐↺] {n}\.")

    def test_system_checklist_cannot_invent_completion(self):
        out = self.root / "system"; run_system(out)
        raw = (out / "CHECKLIST.md").read_bytes().replace("○".encode(), "✅".encode())
        (out / "CHECKLIST.md").write_bytes(raw)
        marker = strict_json((out / "COMPLETE.json").read_bytes())
        marker["sha256"]["CHECKLIST.md"] = hashlib.sha256(raw).hexdigest()
        (out / "COMPLETE.json").write_bytes(canonical(marker))
        with self.assertRaisesRegex(ValueError, "checklist does not match"):
            verify_system(out)

    def test_system_missing_component_rejected(self):
        out = self.root / "system"; run_system(out)
        marker = strict_json((out / "COMPLETE.json").read_bytes())
        del marker["sha256"]["finite-domain.json"]
        (out / "COMPLETE.json").write_bytes(canonical(marker))
        with self.assertRaisesRegex(ValueError, "incomplete system"):
            verify_system(out)

    def test_old_receipt_invalidated_by_code_change(self):
        out = self.root / "system"; run_system(out)
        from superhunter.system_check import current_code
        changed = current_code(); changed["bridge.py"] = "a" * 64
        with patch("superhunter.system_check.current_code", return_value=changed), self.assertRaisesRegex(ValueError, "current code changed"):
            verify_system(out)

    def test_system_verdict_cannot_claim_real_vulnerability(self):
        out = self.root / "system"; run_system(out)
        verdict = strict_json((out / "system-result.json").read_bytes())
        verdict["vulnerability_confirmed"] = True
        self.reseal(out,{"system-result.json":verdict})
        with self.assertRaisesRegex(ValueError, "system result"):
            verify_system(out)

    def test_system_has_no_network_or_child_execution_in_process(self):
        with patch("socket.socket", side_effect=AssertionError("network")), patch("subprocess.run", side_effect=AssertionError("child")):
            self.assertEqual(run_system(self.root / "system")["bounded_cases"],1728)

    def test_system_cannot_overwrite_previous_run(self):
        out = self.root / "system"; run_system(out)
        with self.assertRaises(FileExistsError):
            run_system(out)

    def test_system_cli_and_separate_verification(self):
        out = self.root / "system-cli"
        base = Path(__file__).resolve().parents[2]
        summaries = []
        for args in (("system-check", "--out"), ("verify-system", "--bundle")):
            proc = subprocess.run([sys.executable,"-B","-m","superhunter",*args,str(out)],
                                  cwd=base, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode,0,proc.stdout + proc.stderr)
            summaries.append(json.loads(proc.stdout))
        self.assertEqual(summaries[0], summaries[1])
        self.assertEqual(summaries[0]["status"], "LOCAL_DEFENSIVE_CHECKS_PASS")


if __name__ == "__main__":
    unittest.main()
