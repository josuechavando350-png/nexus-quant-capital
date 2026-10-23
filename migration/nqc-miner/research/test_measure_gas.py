"""Exact fee arithmetic, hostile indexer data and actual Rust journal integration."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from export_parquet import ExportError
import test_export_parquet as fixtures
from measure_gas import decimal, index_calls, measure, timestamp, transaction_measurement

MODULE = Path(__file__).resolve().parents[1]
PUBLIC_STATE = MODULE / "evidence/public-capture-v2-20261022/state"
PUBLIC_INPUT = MODULE / "evidence/gas-measurement-20261023/blockscout-input.json"


def synthetic_pair(record):
    tx = {"block_number": 10, "timestamp": "1970-01-01T00:01:40Z", "is_pending_update": False,
          "result": "success", "status": "ok", "position": 0, "type": 2,
          "gas_used": "100", "gas_limit": "200", "gas_price": "8", "base_fee_per_gas": "5",
          "max_fee_per_gas": "8", "max_priority_fee_per_gas": "6",
          "fee": {"type": "actual", "value": "800"}, "transaction_burnt_fee": "500", "priority_fee": "300"}
    block = {"block_details": {"hash": record["log"]["block_hash"], "height": 10,
             "timestamp": "1970-01-01T00:01:40.000000Z", "type": "block", "is_pending_update": False,
             "transactions_count": 1, "gas_limit": "1000", "gas_used": "100", "base_fee_per_gas": "5"},
             "transaction_hashes": [record["log"]["transaction_hash"]]}
    return tx, block


class GasMeasurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ParquetExportTests.setUpClass()
        cls.binary = Path(os.environ["NQC_MINER_TEST_BINARY"])

    def setUp(self):
        self.fixture = fixtures.ParquetExportTests()
        self.fixture.setUp()
        self.fixture.fixture(version=2)
        self.root = self.fixture.root
        self.state = self.fixture.state
        self.output = self.root / "measurement"
        self.evidence = self.root / "evidence.json"
        self.record = json.loads((self.state / "events.jsonl").read_bytes().splitlines()[0])["record"]
        self.tx, self.block = synthetic_pair(self.record)
        self.bundle = {"schema": "nqc-miner-blockscout-fee-input-v1", "namespace": "nqc_miner_v1",
                       "producer": "nqc-miner", "data_class": "synthetic", "source": "blockscout-mcp",
                       "server_version": "0.19.0", "calls": [
            {"tool": "get_transaction_info", "params": {"chain_id": "1", "transaction_hash": self.record["log"]["transaction_hash"]},
             "response": {"data": self.tx}},
            {"tool": "get_block_info", "params": {"chain_id": "1", "number_or_hash": self.record["log"]["block_hash"], "include_transactions": True},
             "response": {"data": self.block}}]}

    def tearDown(self):
        self.fixture.tearDown()

    def run_measurement(self):
        self.evidence.write_text(json.dumps(self.bundle))
        return measure(self.state, self.evidence, self.output, self.binary)

    def calculate(self):
        return transaction_measurement([self.record], self.tx, self.block)

    def test_real_three_event_capture_has_two_measured_transactions_and_one_unknown(self):
        before = {p.name: p.read_bytes() for p in PUBLIC_STATE.iterdir() if p.is_file()}
        result = measure(PUBLIC_STATE, PUBLIC_INPUT, self.output, self.binary)
        self.assertEqual(result["canonical_liquidations"], 3)
        self.assertEqual(result["measured_transactions"], 2)
        self.assertEqual(result["measured_execution_fee_wei"], "277470486732374")
        self.assertEqual([t["status"] for t in result["transactions"]],
                         ["auxiliary_measured", "membership_not_returned", "auxiliary_measured"])
        self.assertIsNone(result["transactions"][1]["execution_fee_wei"])
        self.assertFalse(result["all_transaction_fees_measured"])
        self.assertFalse(result["economic_certification"])
        self.assertFalse(result["activation_allowed"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in PUBLIC_STATE.iterdir() if p.is_file()})

    def test_actual_export_manifest_exact_costs_and_no_invented_economics(self):
        result = self.run_measurement()
        self.assertEqual(result["measured_execution_fee_wei"], "800")
        self.assertTrue(result["all_transaction_fees_measured"])
        self.assertEqual(result["data_class"], "synthetic")
        tx = result["transactions"][0]
        self.assertEqual((tx["base_fee_burn_wei"], tx["priority_fee_wei"]), ("500", "300"))
        for key in ("direct_builder_payment_wei", "fee_microusd", "gas_allocation_to_events", "net_profit_microusd"):
            self.assertIsNone(tx[key])
        manifest = json.loads((self.output / "manifest.json").read_bytes())
        self.assertTrue(manifest["complete"])
        self.assertFalse(manifest["complete_economic_measurement"])
        self.assertEqual(manifest["measurement_sha256"], fixtures.digest((self.output / "measurement.json").read_bytes()))
        self.assertEqual(self.evidence.read_bytes(), (self.output / "source-evidence.json").read_bytes())

    def test_multiple_liquidations_in_one_transaction_charge_fee_once(self):
        old = [json.loads(line)["record"] for line in (self.state / "events.jsonl").read_bytes().splitlines()]
        extra = deepcopy(old[0])
        extra["log"]["log_index"] = 1
        extra["decoded"]["payload"]["identity"]["log_index"] = 1
        records = [old[0], extra, *old[1:]]
        records[2]["event_count"] = 2
        records[2]["logs_sha256"] = fixtures.digest(fixtures.packed([records[0]["log"], extra["log"]]))
        owner_hash = fixtures.digest((self.state / "owner.json").read_bytes())
        previous, lines = "0" * 64, []
        for i, record in enumerate(records):
            digest = fixtures.digest(fixtures.packed([i, owner_hash, previous, record]))
            lines.append(fixtures.packed({"sequence": i, "owner_sha256": owner_hash, "previous_sha256": previous,
                                          "record": record, "sha256": digest}) + b"\n")
            previous = digest
        (self.state / "events.jsonl").write_bytes(b"".join(lines))
        result = self.run_measurement()
        self.assertEqual((result["canonical_liquidations"], result["unique_transactions"]), (2, 1))
        self.assertEqual(result["measured_execution_fee_wei"], "800")
        self.assertEqual(result["transactions"][0]["event_count"], 2)

    def test_partial_membership_absence_is_unknown_and_complete_absence_rejected(self):
        self.block["transaction_hashes"] = [fixtures.h(9)]
        with self.assertRaisesRegex(ExportError, "complete block"):
            self.calculate()
        self.block["block_details"]["transactions_count"] = 2
        result = self.calculate()
        self.assertEqual(result["status"], "membership_not_returned")
        self.assertIsNone(result["execution_fee_wei"])

    def test_missing_source_and_unsupported_chains_and_types_stay_unknown(self):
        self.assertEqual(transaction_measurement([self.record], None, self.block)["status"], "missing_source")
        self.record["log"]["chain_id"] = 8453
        self.assertEqual(self.calculate()["status"], "unsupported_chain")
        self.record["log"]["chain_id"] = 1
        for tx_type in (0, 1, 3, 4, 255):
            self.tx["type"] = tx_type
            result = self.calculate()
            self.assertEqual(result["status"], "unsupported_transaction_type")
            self.assertIsNone(result["execution_fee_wei"])

    def test_exact_integer_arithmetic_above_javascript_precision(self):
        self.tx.update(gas_price="9007199254740993", base_fee_per_gas="9007199254740992",
                       max_fee_per_gas="9007199254740993", max_priority_fee_per_gas="1",
                       transaction_burnt_fee="900719925474099200", priority_fee="100",
                       fee={"type": "actual", "value": "900719925474099300"})
        self.block["block_details"]["base_fee_per_gas"] = "9007199254740992"
        self.assertEqual(self.calculate()["execution_fee_wei"], "900719925474099300")

    def test_canonical_decimal_and_timestamp_boundaries(self):
        for value in (True, 0, 1.0, "01", "-1", "1e3", " 1", "NaN", str(1 << 256), "1" * 10000):
            with self.subTest(value=str(value)[:20]), self.assertRaises(ExportError):
                decimal(value)
        self.assertEqual(decimal(str((1 << 256) - 1)), (1 << 256) - 1)
        for value in (True, "1970-01-01T00:01:40.1Z", "1970-01-01T00:01:40+01:00", "2026-02-30T00:00:00Z"):
            with self.subTest(value=value), self.assertRaises(ExportError):
                timestamp(value)

    def test_fee_field_tampering_caps_and_extra_costs_fail(self):
        original = deepcopy(self.tx)
        changes = {"gas_price": "9", "gas_used": "101", "gas_limit": "99", "base_fee_per_gas": "4",
                   "max_fee_per_gas": "4", "max_priority_fee_per_gas": "9", "transaction_burnt_fee": "0",
                   "priority_fee": "0", "l1_fee": "0", "blob_gas_used": "0", "position": True,
                   "type": True, "is_pending_update": 0, "result": "error", "status": "error",
                   "block_hash": fixtures.h(9)}
        for field, value in changes.items():
            with self.subTest(field=field), self.assertRaises(ExportError):
                self.tx = {**original, field: value}
                self.calculate()
        for fee in ({"type": "maximum", "value": "800"}, {"type": "actual", "value": "801"}):
            with self.subTest(fee=fee), self.assertRaises(ExportError):
                self.tx = {**original, "fee": fee}
                self.calculate()

    def test_block_location_pending_membership_and_gas_tampering_fail(self):
        original = deepcopy(self.block)
        changes = {"hash": fixtures.h(9), "height": 11, "timestamp": "1970-01-01T00:01:41Z",
                   "is_pending_update": True, "type": "reorg", "transactions_count": 0,
                   "gas_limit": "199", "gas_used": "99"}
        for field, value in changes.items():
            with self.subTest(field=field), self.assertRaises(ExportError):
                self.block = deepcopy(original)
                self.block["block_details"][field] = value
                self.calculate()
        self.block = deepcopy(original)
        self.block["transaction_hashes"] *= 2
        with self.assertRaises(ExportError):
            self.calculate()

    def test_foreign_duplicate_unbound_and_paginated_calls_rejected(self):
        original = deepcopy(self.bundle)
        mutations = [lambda b: b.update(namespace="observer"), lambda b: b.update(data_class="historical"),
                     lambda b: b["calls"].append(deepcopy(b["calls"][0])),
                     lambda b: b["calls"][0]["params"].update(chain_id="8453"),
                     lambda b: b["calls"][0]["params"].update(extra=True),
                     lambda b: b["calls"][0]["response"].update(pagination={"next_call": {}}),
                     lambda b: b["calls"][0]["response"]["data"].update(hash=fixtures.h(9)),
                     lambda b: b["calls"][1]["params"].update(include_transactions=1),
                     lambda b: b["calls"][1]["params"].update(number_or_hash=fixtures.h(9))]
        for mutation in mutations:
            bundle = deepcopy(original)
            mutation(bundle)
            with self.subTest(bundle=str(bundle)[:100]), self.assertRaises(ExportError):
                index_calls(bundle, "synthetic")

    def test_missing_auxiliary_data_is_retained_as_unknown(self):
        self.bundle["calls"] = []
        result = self.run_measurement()
        self.assertEqual(result["canonical_liquidations"], 1)
        self.assertEqual(result["measured_transactions"], 0)
        self.assertIsNone(result["measured_execution_fee_wei"])
        self.assertIsNone(result["transactions"][0]["execution_fee_wei"])

    def test_unrelated_source_cannot_be_attached(self):
        self.bundle["calls"][0]["params"]["transaction_hash"] = fixtures.h(8)
        with self.assertRaisesRegex(ExportError, "unrelated"):
            self.run_measurement()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_incomplete_or_invalidated_source_is_not_economically_admitted(self):
        for options in ({"complete": False}, {"invalidated": True}):
            self.fixture.fixture(version=2, **options)
            with tempfile.TemporaryDirectory(dir=self.root) as directory:
                self.output = Path(directory) / "out"
                with self.assertRaisesRegex(ExportError, "complete unrevoked"):
                    self.run_measurement()
                self.assertFalse((self.output / "manifest.json").exists())

    def test_collection_window_requires_parent_revocation_context(self):
        owner = json.loads((self.state / "owner.json").read_bytes())
        owner["run_id"] = "window-" + "0" * 64
        (self.state / "owner.json").write_text(json.dumps(owner))
        with self.assertRaisesRegex(ExportError, "parent revocation"):
            self.run_measurement()
        self.assertFalse(self.output.exists())

    def test_tampered_journal_rejected_by_actual_rust(self):
        path = self.state / "events.jsonl"
        path.write_bytes(path.read_bytes().replace(b'"observed_at":110', b'"observed_at":111'))
        with self.assertRaisesRegex(ExportError, "Rust verifier rejected"):
            self.run_measurement()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_existing_output_symlink_or_duplicate_json_does_not_publish(self):
        self.output.mkdir()
        with self.assertRaises(ExportError):
            self.run_measurement()
        self.output.rmdir()
        self.evidence.unlink()
        self.evidence.symlink_to(PUBLIC_INPUT)
        with self.assertRaises(ExportError):
            measure(self.state, self.evidence, self.output, self.binary)
        self.evidence.unlink()
        self.evidence.write_text('{"schema":"a","schema":"b"}')
        with self.assertRaisesRegex(ExportError, "duplicate JSON"):
            measure(self.state, self.evidence, self.output, self.binary)
        self.assertFalse((self.output / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
