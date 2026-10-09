#!/usr/bin/env python3
"""Adversarial checks on actual recovered API metadata and archive bytes."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest

from verify_winner_recovery import PINS, transport, archive, verify, rpc_records

class ActualWinnerEvidenceTests(unittest.TestCase):
    def rpc_directories(self):
        return [self.rpc_root/("historical-rpc-" + item + "-resumed")
                for item in ("drpc-receipts", "blockpi-receipts", "blockpi-logs")]

    def test_partial_real_rpc_is_reconciled_without_full_coverage_claim(self):
        report = verify(self.root, self.metadata, self.rpc_directories(), True)
        self.assertEqual(report["status"], "ARCHIVES_VERIFIED_NEW_RPC_PARTIAL")
        self.assertEqual(report["new_receipt_counts"], {"drpc": 87, "blockpi": 123})
        self.assertEqual(report["two_operator_matching_receipt_count"], 87)
        self.assertFalse(report["new_two_operator_receipt_consistency"])
        self.assertFalse(report["archived_blockscout_and_new_distinct_operator_log_consistency"])
        self.assertEqual(len(report["acquisition_failures"]), 3)

    def test_full_mode_rejects_actual_incomplete_rpc_acquisition(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            verify(self.root, self.metadata, self.rpc_directories())

    def test_all_five_archives_and_failed_conclusions(self):
        report = verify(self.root, self.metadata, [])
        self.assertEqual(len(report["archives"]), 5)
        self.assertEqual(sum(r["original_run_conclusion"] == "failure" for r in report["archives"]), 2)
        self.assertFalse(report["real_market_census_closed"])

    def test_failed_run_cannot_be_relabelled_success(self):
        pin = PINS[1]
        doc = json.loads((self.metadata/f"{pin[0]}.json").read_bytes())
        doc["run"]["conclusion"] = "success"
        with self.assertRaisesRegex(ValueError, "conclusion"):
            transport(pin, doc, (self.root/pin[2]).read_bytes())

    def test_commit_tree_repository_and_artifact_mutations_fail(self):
        pin = PINS[0]
        original = json.loads((self.metadata/f"{pin[0]}.json").read_bytes())
        raw = (self.root/pin[2]).read_bytes()
        for key in ["tree", "repository", "artifact", "head"]:
            doc = copy.deepcopy(original)
            if key == "tree": doc["commit"]["commit"]["tree"]["sha"] = "a"*40
            if key == "repository": doc["run"]["repository"]["full_name"] = "other/repo"
            if key == "artifact": doc["artifacts"]["artifacts"][0]["workflow_run"]["id"] += 1
            if key == "head": doc["run"]["head_sha"] = "b"*40
            with self.subTest(key=key), self.assertRaises(ValueError):
                transport(pin, doc, raw)

    def test_zip_byte_mutation_fails(self):
        pin = PINS[0]
        doc = json.loads((self.metadata/f"{pin[0]}.json").read_bytes())
        raw = bytearray((self.root/pin[2]).read_bytes())
        raw[len(raw)//2] ^= 1
        with self.assertRaises(ValueError):
            transport(pin, doc, bytes(raw))

    def test_rpc_manifest_rejects_path_escape_and_corrupt_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path/"manifest.json").write_text(json.dumps([{"path":"../outside", "size": 0, "sha256": "a"*64}]))
            with self.assertRaisesRegex(ValueError, "unsafe"):
                rpc_records(path)
            (path/"witness.json").write_bytes(b"bad")
            (path/"manifest.json").write_text(json.dumps([{"path":"witness.json", "size": 3, "sha256": "a"*64}]))
            with self.assertRaisesRegex(ValueError, "mismatch"):
                rpc_records(path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--rpc-root", required=True, type=Path)
    args = parser.parse_args()
    ActualWinnerEvidenceTests.root = args.archive_root
    ActualWinnerEvidenceTests.metadata = args.metadata
    ActualWinnerEvidenceTests.rpc_root = args.rpc_root
    unittest.main(argv=[__file__], verbosity=2)
