"""Quality-gate regressions, fixed own-component fixtures only."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import assurance
from superhunter.capabilities import catalogue, checklist, FOUNDATIONS, render_checklist, validate_catalogue
from superhunter.local_lab import run_local, verify_local_bundle
from superhunter.native_runtime import load_components
from superhunter.qa_worker import RecordedResult, summarize, test_ids as flatten_test_ids
from superhunter.safe_io import canonical, strict_json


class AssuranceTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)

    def lab(self):
        out = self.root / "lab"
        run_local(out)
        return out

    def rewrite(self, out, name, change):
        value = strict_json((out / name).read_bytes())
        change(value)
        raw = canonical(value)
        (out / name).write_bytes(raw)
        marker = strict_json((out / "COMPLETE.json").read_bytes())
        marker["sha256"][name] = hashlib.sha256(raw).hexdigest()
        (out / "COMPLETE.json").write_bytes(canonical(marker))

    def rechain(self, out, change):
        audit = strict_json((out / "diablo-audit.json").read_bytes())
        change(audit["entries"])
        previous = "0" * 64
        native = load_components()
        for entry in audit["entries"]:
            entry["prev_hash"] = previous
            entry["hash"] = native.audit.compute_hash(entry["index"], entry["timestamp"], entry["event"], entry["data"], previous)
            previous = entry["hash"]
        self.rewrite(out, "diablo-audit.json", lambda v: v.update(audit))
        self.rewrite(out, "lab-result.json", lambda v: v.update(audit_head=previous))

    def test_catalogue_has_all_fifty_and_no_completed_engines(self):
        rows = catalogue()
        self.assertEqual([r["id"] for r in rows], list(range(1, 51)))
        self.assertTrue(all(r["implemented"] is False for r in rows))
        self.assertEqual(len(rows), 50)

    def test_original_offensive_requests_have_explicit_safe_redesign(self):
        rows = {r["id"]: r for r in catalogue()}
        for n in (22, 25, 32, 35, 43, 44, 46):
            self.assertEqual(rows[n]["status"], "REDESIGN_REQUIRED")

    def test_catalogue_rejects_cycle(self):
        rows = catalogue()
        rows[0]["depends_on"] = [2]
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_catalogue(rows)

    def test_catalogue_rejects_missing_dependency(self):
        rows = catalogue()
        rows[0]["depends_on"] = [51]
        with self.assertRaisesRegex(ValueError, "dependency"):
            validate_catalogue(rows)

    def test_catalogue_rejects_duplicate_identity(self):
        rows = catalogue()
        rows[1]["id"] = 1
        with self.assertRaises(ValueError):
            validate_catalogue(rows)

    def test_catalogue_rejects_boolean_id(self):
        rows = catalogue()
        rows[0]["id"] = True
        with self.assertRaises(ValueError):
            validate_catalogue(rows)

    def test_catalogue_never_promotes_a_title_to_implementation(self):
        rows = catalogue()
        rows[0].update(implemented=True, status="COMPLETE")
        with self.assertRaisesRegex(ValueError, "promoted"):
            validate_catalogue(rows)

    def test_foundations_require_tests_and_all_gates(self):
        records = [{"id": name, "outcome": "PASS"} for _, required in FOUNDATIONS.values() for name in required]
        self.assertTrue(all(r["verified_this_run"] for r in checklist(records, True)["foundations"]))
        self.assertFalse(any(r["verified_this_run"] for r in checklist(records, False)["foundations"]))
        self.assertFalse(any(r["verified_this_run"] for r in checklist([], True)["foundations"]))
        self.assertEqual(checklist(records, True)["completed_requested_capabilities"], 0)

    def test_render_keeps_fifty_items_pending(self):
        text = render_checklist(checklist([], False))
        self.assertEqual(sum(line.startswith("☐ ") and line[2:4].isdigit() for line in text.splitlines()), 50)
        self.assertNotIn("✅", text)

    def test_false_execution_declaration_rejected(self):
        out = self.lab()
        self.rewrite(out, "lab-result.json", lambda v: v.update(local_component_execution=False))
        with self.assertRaisesRegex(ValueError, "execution declaration"):
            verify_local_bundle(out)

    def test_resealed_unrelated_case_rejected(self):
        out = self.lab()
        self.rechain(out, lambda rows: rows[2]["data"].update(case="unrelated"))
        with self.assertRaisesRegex(ValueError, "semantic link"):
            verify_local_bundle(out)

    def test_resealed_wrong_input_link_rejected(self):
        out = self.lab()
        self.rechain(out, lambda rows: rows[2]["data"].update(input_sha256="f" * 64))
        with self.assertRaisesRegex(ValueError, "semantic link"):
            verify_local_bundle(out)

    def test_resealed_wrong_output_link_rejected(self):
        out = self.lab()
        self.rechain(out, lambda rows: rows[3]["data"].update(output_commitment="0x" + "f" * 64))
        with self.assertRaisesRegex(ValueError, "semantic link"):
            verify_local_bundle(out)

    def test_resealed_scope_claim_rejected(self):
        out = self.lab()
        self.rechain(out, lambda rows: rows[1]["data"].update(decision="DENY"))
        with self.assertRaisesRegex(ValueError, "semantic link"):
            verify_local_bundle(out)

    def test_resealed_event_name_rejected(self):
        out = self.lab()
        self.rechain(out, lambda rows: rows[3].update(event="unrelated.event"))
        with self.assertRaisesRegex(ValueError, "semantic link"):
            verify_local_bundle(out)

    def test_boolean_schema_rejected(self):
        out = self.lab()
        self.rewrite(out, "lab-result.json", lambda v: v.update(schema_version=True))
        with self.assertRaisesRegex(ValueError, "integer declaration"):
            verify_local_bundle(out)

    def test_noncanonical_run_id_rejected(self):
        out = self.lab()
        self.rewrite(out, "lab-result.json", lambda v: v.update(run_id=v["run_id"].upper()))
        with self.assertRaises(ValueError):
            verify_local_bundle(out)

    def test_resealed_timestamp_without_timezone_rejected(self):
        out = self.lab()
        self.rechain(out, lambda rows: rows[2].update(timestamp="2026-11-03T00:00:00"))
        with self.assertRaisesRegex(ValueError, "timezone"):
            verify_local_bundle(out)

    def test_resealed_time_outside_execution_rejected(self):
        out = self.lab()
        self.rechain(out, lambda rows: rows[2].update(timestamp="2000-01-01T00:00:00+00:00"))
        with self.assertRaisesRegex(ValueError, "timestamp order"):
            verify_local_bundle(out)

    def test_extra_result_declarations_rejected(self):
        out = self.lab()
        self.rewrite(out, "lab-result.json", lambda v: v.update(perfect_security=True))
        with self.assertRaisesRegex(ValueError, "fields mismatch"):
            verify_local_bundle(out)

    def receipt(self):
        return {"schema_version": 1, "status": "PASS", "tests_run": 1, "expected_count": 1,
                "records": [{"id": "test_example.Case.test_ok", "outcome": "PASS"}],
                "failures": 0, "errors": 0, "skipped": 0, "expected_failures": 0, "unexpected_successes": 0}

    def test_test_receipt_rejects_missing_tests(self):
        value = self.receipt()
        value["expected_count"] = 2
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            assurance.verify_tests(value)

    def test_test_receipt_rejects_all_nonpasses(self):
        for outcome in ("SKIP", "FAIL", "ERROR", "EXPECTED_FAILURE", "UNEXPECTED_SUCCESS", "INCOMPLETE"):
            with self.subTest(outcome=outcome):
                value = self.receipt()
                value["records"][0]["outcome"] = outcome
                with self.assertRaises(ValueError):
                    assurance.verify_tests(value)

    def test_test_receipt_rejects_duplicate_ids(self):
        value = self.receipt()
        value["records"] *= 2
        value["expected_count"] = value["tests_run"] = 2
        with self.assertRaisesRegex(ValueError, "duplicate"):
            assurance.verify_tests(value)

    def test_test_receipt_rejects_boolean_counts(self):
        value = self.receipt()
        value["tests_run"] = True
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            assurance.verify_tests(value)

    def execute_examples(self, cls):
        suite = unittest.TestLoader().loadTestsFromTestCase(cls)
        expected = list(flatten_test_ids(suite))
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=RecordedResult).run(suite)
        return summarize(result, expected)

    def test_actual_worker_records_successful_test(self):
        class Sample(unittest.TestCase):
            def test_example(self):
                self.assertEqual(2 + 2, 4)
        value = self.execute_examples(Sample)
        self.assertEqual(value["status"], "PASS")
        self.assertEqual(value["tests_run"], 1)

    def test_actual_worker_never_treats_skip_as_success(self):
        class Sample(unittest.TestCase):
            @unittest.skip("intentional unit fixture")
            def test_example(self):
                self.fail("not executed")
        value = self.execute_examples(Sample)
        self.assertEqual(value["status"], "FAIL")
        self.assertEqual(value["records"][0]["outcome"], "SKIP")

    def test_actual_worker_records_subtest_failure(self):
        class Sample(unittest.TestCase):
            def test_example(self):
                with self.subTest(example=1):
                    self.assertEqual(1, 2)
        value = self.execute_examples(Sample)
        self.assertEqual(value["status"], "FAIL")

    def graph(self):
        nodes, files = {}, {name: b"{}" for outputs in assurance.STAGE_OUTPUTS.values() for name in outputs}
        for name, deps in assurance.STAGES:
            nodes[name] = assurance._node(name, deps, nodes, "a" * 64, assurance.STAGE_OUTPUTS[name], files)
        return {"source_sha256": "a" * 64, "stages": list(nodes.values())}, files

    def test_graph_requires_all_stages(self):
        receipt, files = self.graph()
        receipt["stages"].pop()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            assurance.verify_stage_links(receipt, files)

    def test_graph_rejects_disconnected_stage(self):
        receipt, files = self.graph()
        receipt["stages"][2]["parents"] = {}
        with self.assertRaisesRegex(ValueError, "dependency"):
            assurance.verify_stage_links(receipt, files)

    def test_graph_rejects_changed_artifact(self):
        receipt, files = self.graph()
        files["source-snapshot.json"] = b"changed"
        with self.assertRaisesRegex(ValueError, "artifact"):
            assurance.verify_stage_links(receipt, files)

    def test_graph_rejects_wrong_evidence_role(self):
        receipt, files = self.graph()
        receipt["stages"][1]["outputs"] = {"source-snapshot.json": assurance.sha(files["source-snapshot.json"])}
        with self.assertRaisesRegex(ValueError, "evidence missing"):
            assurance.verify_stage_links(receipt, files)

    def test_graph_success_has_every_required_dependency(self):
        receipt, files = self.graph()
        assurance.verify_stage_links(receipt, files)
        self.assertEqual(len(receipt["stages"]), 5)

    def test_failed_tests_stop_downstream_execution(self):
        out = self.root / "blocked"
        with patch.object(assurance, "_fixed_worker", side_effect=ValueError("unit-injected failure")) as worker:
            result = assurance.run_assurance(out)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["failed_stage"], "regressions")
        self.assertEqual(worker.call_count, 1)
        status = strict_json((out / "capability-status.json").read_bytes())
        self.assertFalse(any(f["verified_this_run"] for f in status["foundations"]))

    def test_existing_output_never_reused(self):
        out = self.root / "exists"
        out.mkdir()
        with patch.object(assurance, "_fixed_worker") as worker, self.assertRaises(FileExistsError):
            assurance.run_assurance(out)
        worker.assert_not_called()

    def test_quality_bundle_rejects_unknown_files_before_reading(self):
        root = self.root / "unknown"
        root.mkdir()
        (root / "COMPLETE.json").write_bytes(canonical({"schema_version": 1, "sha256": {"missing": "a" * 64}}))
        with self.assertRaisesRegex(ValueError, "files mismatch"):
            assurance.verify_assurance(root)

    def test_no_arbitrary_worker_command(self):
        with self.assertRaisesRegex(ValueError, "unknown fixed worker"):
            assurance._fixed_worker("attack", self.root)

    def test_source_snapshot_covers_tests_and_runtime(self):
        value = assurance.snapshot()
        for name in ("qa_worker.py", "capabilities.py", "lab_integrity.py", "tests/test_assurance.py"):
            self.assertIn(name, value["files"])
        self.assertEqual(value["sha256"], assurance.sha(canonical(value["files"])))


if __name__ == "__main__":
    unittest.main()
