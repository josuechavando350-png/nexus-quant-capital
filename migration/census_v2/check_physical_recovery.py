#!/usr/bin/env python3
"""Adversarial verification of recovered historical logs and real oracle bytes."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import verify_physical_recovery as m


class PhysicalLogEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = m.verify(ARGS.archive_root)
        cls.gas_raw = gzip.decompress((m.EVIDENCE/"37742063251.log.gz").read_bytes())
        cls.gas_records = m.output_records(cls.gas_raw)

    def test_four_original_producers_and_narrow_scope(self):
        r = self.report
        self.assertEqual(len(r["original_runs"]), 4)
        self.assertEqual(r["historical_physical_test_results_observed"], 16)
        self.assertEqual(r["historical_tests_rerun_here"], 0)
        self.assertFalse(r["physical_artifact_zip_bytes_recovered"])
        self.assertFalse(r["independent_fork_reexecution_here"])
        self.assertFalse(r["real_market_census_closed"])
        self.assertFalse(r["capital_or_execution_admission_changed"])
        self.assertTrue(r["event_to_fork_surplus_integer_parity"])
        self.assertEqual(r["counterfactual_execution"]["measured_execute_call_gas"], 562357)
        self.assertEqual([x["time_only_below_one"] for x in r["time_only_cases"]], [True, False, False])
        self.assertEqual(m.canonical(r), m.canonical(m.verify(ARGS.archive_root)))

    def test_echoed_grep_pass_is_not_execution_evidence(self):
        text = self.gas_raw.decode("utf-8-sig")
        self.assertIn("grep -Fq 'Suite result: ok. 2 passed; 0 failed; 0 skipped'", text)
        edited = "\n".join(line for line in text.splitlines()
                            if not m.PASS.fullmatch(line.split(" ", 1)[1] if " " in line else "")) + "\n"
        with self.assertRaises(ValueError):
            m.suites(m.output_records(edited.encode()), m.RUNS[3])

    def test_command_display_forged_measurement_ignored(self):
        lines = self.gas_raw.decode("utf-8-sig").splitlines()
        at = next(i for i, line in enumerate(lines) if "##[group]Run " in line)
        prefix = lines[at].split(" ", 1)[0]
        lines.insert(at+1, prefix + "   NQC_RANK1_FORK_EXECUTE_CALL_GAS_UNITS: 1")
        found = m.suites(m.output_records(("\n".join(lines)+"\n").encode()), m.RUNS[3])
        self.assertEqual(m.metric(found[0], "NQC_RANK1_FORK_EXECUTE_CALL_GAS_UNITS"), 562357)

    def test_duplicate_measurement_and_unfinished_suite_rejected(self):
        duplicate = copy.deepcopy(self.gas_records)
        i = next(i for i, r in enumerate(duplicate) if r["text"].startswith("  NQC_RANK1_FORK_EXECUTE_CALL_GAS_UNITS:"))
        duplicate.insert(i+1, copy.deepcopy(duplicate[i]))
        with self.assertRaises(ValueError):
            m.suites(duplicate, m.RUNS[3])
        truncated = [r for r in self.gas_records if not m.END.fullmatch(r["text"])]
        with self.assertRaises(ValueError):
            m.suites(truncated, m.RUNS[3])

    def test_actual_failure_not_hidden_by_expected_command_text(self):
        records = copy.deepcopy(self.gas_records)
        r = next(r for r in records if m.PASS.fullmatch(r["text"]))
        r["text"] = r["text"].replace("[PASS]", "[FAIL: gas funding missing]")
        with self.assertRaises(ValueError):
            m.suites(records, m.RUNS[3])

    def test_metadata_cannot_relabel_checkout_tree_or_conclusion(self):
        for field, value in (("head_sha", "f"*40), ("conclusion", "failure")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as d:
                root = Path(d)/"evidence"
                shutil.copytree(m.EVIDENCE, root)
                p = root/"api-snapshot.json"
                doc = json.loads(p.read_bytes())
                doc["runs"][0]["run"][field] = value
                p.write_bytes(m.canonical(doc))
                with self.assertRaises(ValueError):
                    m.source_identity(root)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/"evidence"
            shutil.copytree(m.EVIDENCE, root)
            p = root/"api-snapshot.json"
            doc = json.loads(p.read_bytes())
            doc["runs"][0]["run"]["head_commit"]["tree_id"] = "f"*40
            p.write_bytes(m.canonical(doc))
            with self.assertRaises(ValueError):
                m.source_identity(root)

    def test_byte_changes_and_missing_original_source_fail(self):
        for relative in ("37742063251.log.gz", "sources/37741109591-NqcFlashFundingExecutor.sol.txt"):
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as d:
                root = Path(d)/"evidence"
                shutil.copytree(m.EVIDENCE, root)
                p = root/relative
                p.write_bytes(p.read_bytes() + b"CORRUPTION")
                with self.assertRaises(ValueError):
                    m.source_identity(root)
        with self.assertRaises(FileNotFoundError):
            m.verify(ARGS.archive_root/"missing")

    def test_integer_gas_sensitivity_is_not_full_transaction_or_profit(self):
        cases = self.report["gas_sensitivities"]
        self.assertEqual(len(cases), 5)
        self.assertEqual(cases[0]["modeled_gas_cost_wei"], "34681581690896")
        self.assertEqual(cases[-1]["modeled_gas_cost_wei"], "8886087100090896")
        for c in cases:
            units = 562357 + 21000 + c["assumed_additional_overhead_gas"]
            self.assertEqual(int(c["modeled_gas_cost_wei"]), units * (59451728 + int(c["assumed_tip_wei_per_gas"])))
            self.assertFalse(c["actual_transaction_gas_measured"])
            self.assertFalse(c["nqc_native_gas_funding_proven"])
            self.assertEqual(c["nqc_executable_value_admitted_usd_wad"], "0")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-root", type=Path, required=True)
    ARGS, rest = p.parse_known_args()
    unittest.main(argv=[__file__] + rest)
