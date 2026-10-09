#!/usr/bin/env python3
"""Required real-source checks; missing archives fail instead of being skipped."""
import argparse
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import reconcile_library_witnesses as m
import replay_library_risk_screen as risk


class RecoveredEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = m.package(ARGS.package)
        cls.inputs = m.base.sources(ARGS.archive_root, ARGS.metadata, ARGS.rpc_root)
        cls.groups, cls.witnesses = m.load_sources(cls.data)
        cls.files, cls.report = m.reconcile(cls.data, cls.inputs)

    def example(self):
        key = next(k for k in self.groups if k[0] == "eth_getTransactionByHash")
        tx = copy.deepcopy(self.groups[key]["nodies"])
        header = copy.deepcopy(self.groups[("eth_getBlockByNumber", m.canonical([tx["blockNumber"], False]))]["nodies"])
        raw = copy.deepcopy(self.groups[("eth_getTransactionReceipt", key[1])]["nodies"])
        return tx, header, raw, self.inputs[0][tx["hash"]]

    def test_raw_parity_and_gas_conservation(self):
        self.assertEqual(self.report["paired_transactions"], 3)
        self.assertEqual(self.report["winner_universe_transactions"], 127)
        self.assertEqual(self.report["new_winner_transactions"], 0)
        self.assertEqual(self.report["gas_paid_wei_in_three_existing_records"], "1823155915785314")
        self.assertEqual(int(self.report["base_fee_burn_wei"]) + int(self.report["priority_fee_wei"]),
                         int(self.report["gas_paid_wei_in_three_existing_records"]))
        rows = [m.parse(line) for line in self.files["paired-winner-supplement.jsonl"].splitlines()]
        self.assertEqual([r["top_level_value_wei"] for r in rows], ["0", "4", "171"])
        self.assertTrue(all(r["receipt_matches_prior_provider_labels"] == ["blockpi", "drpc"] for r in rows))
        self.assertTrue(all(r["net_pnl_usd"] is None and r["original_nqc_observed_at"] is None for r in rows))
        self.assertFalse(self.report["real_market_census_closed"])
        self.assertEqual(len(self.report["provider_representation_differences"]), 6)

    def test_deterministic_without_network(self):
        with patch("socket.socket", side_effect=AssertionError("network prohibited")):
            self.assertEqual(m.reconcile(self.data, self.inputs), (self.files, self.report))

    def test_reject_altered_archives(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.zip"
            for loader, original in ((m.package, ARGS.package), (risk.package, ARGS.risk_package)):
                raw = bytearray(original.read_bytes()); raw[-1] ^= 1; p.write_bytes(raw)
                with self.assertRaisesRegex(ValueError, "pin mismatch"):
                    loader(p)

    def test_source_raw_bytes_and_recorded_times_bound(self):
        row = m.parse(self.data["output/sources.jsonl"].splitlines()[0])
        bad = dict(self.data); bad["output/" + row["packaged_raw_path"]] += b" "
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            m.source(bad, row)
        bad_row = copy.deepcopy(row); bad_row["params"] = ["latest", False]
        with self.assertRaisesRegex(ValueError, "request/source mismatch"):
            m.source(self.data, bad_row)
        meta = m.parse(self.data["output/" + row["packaged_metadata_path"]])
        meta["finished_at"] = "2026-10-09T04:00:00+00:00"
        # Re-seal local witnesses to test chronology beyond mere hash failure.
        raw = m.canonical(meta); digest = m.sha(raw)
        bad_row = copy.deepcopy(row); bad = dict(self.data)
        bad_row["metadata_sha256"] = digest; bad_row["packaged_metadata_path"] = "raw-evidence/" + digest + ".json"
        bad["output/" + bad_row["packaged_metadata_path"]] = raw
        accepted = m.parse(self.data["output/" + row["packaged_acceptance_path"]])
        accepted["metadata_sha256"] = digest; raw = m.canonical(accepted); digest = m.sha(raw)
        bad_row["accepted_marker_sha256"] = digest; bad_row["packaged_acceptance_path"] = "raw-evidence/" + digest + ".json"
        bad["output/" + bad_row["packaged_acceptance_path"]] = raw
        with self.assertRaisesRegex(ValueError, "chronology"):
            m.source(bad, bad_row)

    def test_reject_cross_provider_disagreement_and_missing_pair(self):
        groups = copy.deepcopy(self.groups)
        key = next(k for k in groups if k[0] == "eth_getBlockByNumber")
        groups[key]["tenderly"]["gasUsed"] = "0x1"
        with patch.object(m, "load_sources", return_value=(groups, self.witnesses)):
            with self.assertRaisesRegex(ValueError, "header provider mismatch"):
                m.reconcile(self.data, self.inputs)
        bad = dict(self.data)
        bad["output/sources.jsonl"] = b"".join(line + b"\n" for line in bad["output/sources.jsonl"].splitlines()[:-1])
        with self.assertRaisesRegex(ValueError, "source population"):
            m.load_sources(bad)

    def test_reject_eip1559_fee_drift(self):
        tx, header, raw, expected = self.example()
        tx["maxFeePerGas"] = "0x0"
        with self.assertRaisesRegex(ValueError, "fee arithmetic"):
            m.transaction_view(tx, header, raw, expected)

    def test_reject_wrong_header_index_and_timestamp(self):
        for mutation in ("index", "timestamp"):
            tx, header, raw, expected = self.example()
            if mutation == "index":
                header["transactions"][expected["transaction_index"]] = "0x" + "00" * 32
            else:
                tx["blockTimestamp"] = "0x1"
            with self.assertRaisesRegex(ValueError, "position mismatch|timestamp contradicts"):
                m.transaction_view(tx, header, raw, expected)

    def test_blob_normalization_does_not_hide_costs(self):
        tx, _, raw, _ = self.example()
        raw["blobGasUsed"] = "0x1"
        with self.assertRaisesRegex(ValueError, "nonzero blob"):
            m.normalized_type2_receipt(raw, tx)
        tx["type"] = raw["type"] = "0x3"
        raw["blobGasUsed"] = "0x0"
        with self.assertRaisesRegex(ValueError, "type-2 only"):
            m.normalized_type2_receipt(raw, tx)
        self.assertFalse(m.equal(True, 1))

    def test_risk_original_source_and_reproduction_scope(self):
        data = risk.package(ARGS.risk_package)
        report = m.parse(data["results/report.json"])
        self.assertEqual(report["counters"]["accounts"], 246929)
        self.assertEqual(report["risk_bands"]["HF_LT_1"]["collateral_usd_oracle"], "12.36050759")
        self.assertEqual(report["below_one"]["collateral_at_least_usd_count"]["1"], 1)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "overwrite"):
                risk.replay(ARGS.risk_package, ARGS.archive_root, ARGS.metadata, Path(td))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for field in ("package", "risk-package", "archive-root", "metadata", "rpc-root"):
        p.add_argument("--" + field, type=Path, required=True)
    ARGS = p.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RecoveredEvidence))
    raise SystemExit(not result.wasSuccessful())
