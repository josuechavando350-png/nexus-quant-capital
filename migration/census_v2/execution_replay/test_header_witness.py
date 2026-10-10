import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from rpc_witness import sha
from run_fork import checksum_overlay, TEST_PATH, PATCHED_TEST_SHA
from verify_headers import verify, verify_header
from verify_recovery import verify as verify_recovery, ARCHIVE_SHA

HERE = Path(__file__).parent


class HeaderWitnessTests(unittest.TestCase):
    def archive(self):
        path = HERE / "inputs/rpc-recovery.zip"
        self.assertEqual(sha(path.read_bytes()), ARCHIVE_SHA)
        return zipfile.ZipFile(path)

    def test_actual_fork_replays_and_failures_keep_their_scope(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            report = verify_recovery(HERE / "inputs/rpc-recovery.zip")
        self.assertEqual(report["offline_network_requests"], 0)
        self.assertTrue(report["original_and_isolated_replays_pass"])
        self.assertFalse(report["economic_profit_admitted"])

    def test_exact_archive_members_and_producer_snapshots(self):
        with self.archive() as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(set(archive.namelist()), set(manifest["files"]) | {"manifest.json"})
            for name, pin in manifest["files"].items():
                raw = archive.read(name)
                self.assertEqual((len(raw), sha(raw)), (pin["bytes"], pin["sha256"]))
            for attempt, producer in manifest["attempt_producers"].items():
                report = json.loads(archive.read(attempt + "/report.json"))
                for name, digest in report["producer_sources"].items():
                    self.assertEqual(sha(archive.read(producer + "/" + name)), digest)
                for run in report["runs"]:
                    self.assertEqual(sha(archive.read(attempt + "/" + run["mode"] + ".log")), run["log_sha256"])
                if "build" in report:
                    self.assertEqual(sha(archive.read(attempt + "/build.log")), report["build"]["log_sha256"])
                self.assertFalse(report["capital_admission_changed"])
                self.assertFalse(report["census_closed"])

    def test_original_headers_and_payment_are_reconciled_without_network(self):
        with self.archive() as archive, tempfile.TemporaryDirectory() as d:
            path = Path(d) / "witness.jsonl"
            path.write_bytes(archive.read("nodies-001/rpc/upstream.jsonl"))
            with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
                report = verify(path)
            self.assertEqual(len(report["headers"]), 2)
            self.assertEqual(report["trace_visible_payments_to_block_fee_recipient"][0]["wei"], "95915734379292898")
            self.assertEqual(report["historical_transaction_gas"]["priority_fee_to_block_fee_recipient_wei"], "0")
            self.assertEqual(report["historical_transaction_gas"]["base_fee_burn_wei"], "19694395579376")
            self.assertIsNone(report["complete_profit_wei"])
            self.assertFalse(report["payment_applied_as_nqc_capture_cost"])

    def test_substituting_recipient_or_state_root_cannot_keep_anchor_hash(self):
        with self.archive() as archive:
            rows = [json.loads(x) for x in archive.read("nodies-001/rpc/upstream.jsonl").splitlines()]
            original = json.loads(rows[-1]["response_utf8"])["result"]
        for field, replacement in [("miner", "0x" + "11" * 20), ("stateRoot", "0x" + "22" * 32)]:
            header = copy.deepcopy(original)
            header[field] = replacement
            with self.assertRaisesRegex(ValueError, "RLP hash mismatch"):
                verify_header(header)

    def test_checksum_overlay_is_exact_and_rejects_already_modified_input(self):
        with self.archive() as archive, tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / TEST_PATH
            path.parent.mkdir()
            raw = archive.read("inputs/" + TEST_PATH)
            path.write_bytes(raw)
            receipt = checksum_overlay(root)
            self.assertEqual(sha(path.read_bytes()), PATCHED_TEST_SHA)
            self.assertEqual(sum(a != b for a, b in zip(raw, path.read_bytes())), 1)
            self.assertFalse(receipt["address_value_changed"])
            with self.assertRaisesRegex(ValueError, "preimage differs"):
                checksum_overlay(root)


if __name__ == "__main__":
    unittest.main()
