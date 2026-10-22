"""Actual Rust verifier + Polars integration tests; all fixtures are synthetic."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import polars as pl

from export_parquet import ExportError, export_journal


def packed(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def h(n):
    return "0x" + f"{n:02x}" * 32


def address(n):
    return "0x" + f"{n:02x}" * 20


class ParquetExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured = os.environ.get("NQC_MINER_TEST_BINARY")
        if not configured:
            raise RuntimeError("Set NQC_MINER_TEST_BINARY to the compiled Rust nqc-miner executable; verification is never mocked")
        cls.binary = Path(configured)
        result = subprocess.run([str(cls.binary), "topics"], capture_output=True, check=True)
        cls.topic = json.loads(result.stdout)["morpho-blue"][1]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nqc-miner-parquet-test-")
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.output = self.root / "export"

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, *, complete=True, invalidated=False, empty=False, version=1):
        providers = [{"id": "provider-a", "url_env": "NQC_MINER_RPC_A"},
                     {"id": "provider-b", "url_env": "NQC_MINER_RPC_B"}]
        config = {
            "schema_version": 1, "namespace": "nqc_miner_v1", "producer": "nqc-miner",
            "run_id": "parquet-test", "data_class": "synthetic", "code_commit": "1" * 40,
            "cargo_lock_sha256": "2" * 64, "observer_bridge_enabled": False,
            "signing_enabled": False, "gas_budget_mxn_centavos": 0,
            "scopes": [{"id": "morpho-1", "chain_id": 1, "protocol": "morpho-blue", "contract": address(1),
                        "event_topics": [self.topic], "from_block": 10, "to_block": 10,
                        "chunk_blocks": 1, "providers": providers,
                        "deployment_source": "https://github.com/morpho-org/morpho-blue"}],
        }
        if version == 2:
            config["schema_version"] = 2
            ordered = {}
            for key, value in config.items():
                ordered[key] = value
                if key == "cargo_lock_sha256":
                    ordered["build_identity_sha256"] = "3" * 64
            config = ordered
        owner = {"schema": f"nqc-miner-owner-v{version}", "namespace": "nqc_miner_v1", "producer": "nqc-miner",
                 "run_id": "parquet-test", "data_class": "synthetic", "config_sha256": digest(packed(config)),
                 "code_commit": config["code_commit"], "cargo_lock_sha256": config["cargo_lock_sha256"]}
        if version == 2:
            owner["build_identity_sha256"] = config["build_identity_sha256"]
        self.state.joinpath("owner.json").write_bytes(packed(owner))
        self.state.joinpath("config.json").write_bytes(packed(config))
        log = {"chain_id": 1, "address": address(1), "block_number": 10, "block_hash": h(2),
               "transaction_hash": h(3), "log_index": 0,
               "topics": [self.topic, h(4), "0x" + "00" * 12 + "05" * 20, "0x" + "00" * 12 + "06" * 20],
               "data": "0x" + "".join(f"{n:064x}" for n in (100, 101, 105, 0, 0)), "removed": False}
        decoder_input = self.root / "decode.json"
        decoder_input.write_bytes(packed({"scope": {"chain_id": 1, "address": address(1), "family": "morpho_blue", "from_block": 10, "to_block": 10}, "log": log}))
        decoded = json.loads(subprocess.run([str(self.binary), "decode", "--input", str(decoder_input)], capture_output=True, check=True).stdout)
        records = [] if empty else [{"kind": "observed", "scope_id": "morpho-1", "log": log, "decoded": decoded,
                                    "block_timestamp": 100, "observed_at": 110, "providers": ["provider-a", "provider-b"]}]
        if not empty:
            records.append({"kind": "chunk_completed", "scope_id": "morpho-1", "chain_id": 1, "from_block": 10, "to_block": 10,
                            "start_block_hash": h(2), "start_parent_hash": h(1), "end_block_hash": h(2), "observed_at": 110,
                            "providers": ["provider-a", "provider-b"], "event_count": 1, "logs_sha256": digest(packed([log]))})
            if complete:
                records.append({"kind": "scope_completed", "scope_id": "morpho-1", "chain_id": 1, "from_block": 10, "to_block": 10,
                                "finalized_anchor_number": 10, "finalized_anchor_hash": h(2), "observed_at": 110,
                                "providers": ["provider-a", "provider-b"]})
            if invalidated:
                records.append({"kind": "invalidated", "chain_id": 1, "from_block": 10, "reason": "synthetic test reorg"})
        owner_digest = digest(packed(owner))
        previous = "0" * 64
        lines = []
        for sequence, record in enumerate(records):
            value = digest(packed([sequence, owner_digest, previous, record]))
            envelope = {"sequence": sequence, "owner_sha256": owner_digest, "previous_sha256": previous, "record": record, "sha256": value}
            lines.append(packed(envelope) + b"\n")
            previous = value
        self.state.joinpath("events.jsonl").write_bytes(b"".join(lines))
        return lines

    def export(self, **kwargs):
        return export_journal(self.state, self.output, self.binary, **kwargs)

    def test_actual_parquet_roundtrip_preserves_all_bytes_and_provenance(self):
        lines = self.fixture()
        before = {p.name: p.read_bytes() for p in self.state.iterdir()}
        manifest = self.export(batch_rows=2)
        self.assertEqual(manifest["records"], 3)
        self.assertEqual(len(manifest["batches"]), 2)
        self.assertFalse(manifest["authenticity_verified"])
        frames = [pl.read_parquet(self.output / batch["file"]) for batch in manifest["batches"]]
        rows = pl.concat(frames).to_dicts()
        self.assertEqual([row["raw_line"] for row in rows], lines)
        self.assertEqual(rows[0]["event_state"], "scope_completed")
        self.assertEqual({row["data_class"] for row in rows}, {"synthetic"})
        self.assertEqual([row["raw_line_sha256"] for row in rows], [digest(line) for line in lines])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.state.iterdir()})
        for batch in manifest["batches"]:
            self.assertEqual(batch["parquet_sha256"], digest((self.output / batch["file"]).read_bytes()))

    def test_chunk_without_scope_marker_is_not_completed(self):
        self.fixture(complete=False)
        manifest = self.export()
        row = pl.read_parquet(self.output / manifest["batches"][0]["file"]).to_dicts()[0]
        self.assertEqual(row["event_state"], "chunk_committed")

    def test_v2_roundtrip_retains_exact_build_owner_and_source_bytes(self):
        lines = self.fixture(version=2)
        manifest = self.export()
        self.assertEqual(manifest["owner"]["schema"], "nqc-miner-owner-v2")
        self.assertEqual(manifest["owner"]["build_identity_sha256"], "3" * 64)
        rows = pl.read_parquet(self.output / manifest["batches"][0]["file"]).to_dicts()
        self.assertEqual([row["raw_line"] for row in rows], lines)

    def test_v2_foreign_or_missing_build_is_rejected_before_export(self):
        self.fixture(version=2)
        path = self.state / "owner.json"
        owner = json.loads(path.read_bytes())
        owner["build_identity_sha256"] = "4" * 64
        path.write_bytes(packed(owner))
        with self.assertRaisesRegex(ExportError, "mixed build"):
            self.export()
        del owner["build_identity_sha256"]
        path.write_bytes(packed(owner))
        with self.assertRaisesRegex(ExportError, "owner schema"):
            self.export()
        self.assertFalse(self.output.exists())

    def test_invalidations_are_preserved_and_exclude_event(self):
        lines = self.fixture(invalidated=True)
        manifest = self.export()
        rows = pl.read_parquet(self.output / manifest["batches"][0]["file"]).to_dicts()
        self.assertEqual(rows[0]["event_state"], "invalidated")
        self.assertEqual(rows[-1]["record_kind"], "invalidated")
        self.assertEqual(b"".join(row["raw_line"] for row in rows), b"".join(lines))

    def test_empty_journal_does_not_invent_rows(self):
        self.fixture(empty=True)
        manifest = self.export()
        self.assertEqual(manifest["records"], 0)
        self.assertEqual(manifest["batches"], [])
        self.assertTrue(manifest["complete"])

    def test_foreign_namespace_and_mixed_class_rejected_before_output(self):
        self.fixture()
        path = self.state / "owner.json"
        owner = json.loads(path.read_bytes())
        owner["namespace"] = "observer"
        path.write_bytes(packed(owner))
        with self.assertRaisesRegex(ExportError, "foreign"):
            self.export()
        self.assertFalse(self.output.exists())
        self.fixture()
        path = self.state / "config.json"
        config = json.loads(path.read_bytes())
        config["data_class"] = "historical"
        path.write_bytes(packed(config))
        with self.assertRaisesRegex(ExportError, "mixed"):
            self.export()
        self.assertFalse(self.output.exists())

    def test_corruption_is_rejected_by_actual_rust_verifier(self):
        self.fixture()
        path = self.state / "events.jsonl"
        path.write_bytes(path.read_bytes().replace(b'"observed_at":110', b'"observed_at":111', 1))
        with self.assertRaisesRegex(ExportError, "Rust verifier rejected"):
            self.export()
        self.assertFalse((self.output / "manifest.json").exists())
        self.assertFalse(any(self.output.glob("*.parquet")))

    def test_existing_output_and_symlink_ancestor_are_rejected(self):
        self.fixture()
        self.output.mkdir()
        sentinel = self.output / "observer.txt"
        sentinel.write_text("untouched")
        with self.assertRaises(ExportError):
            self.export()
        self.assertEqual(sentinel.read_text(), "untouched")
        link = self.root / "alias"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ExportError, "symlink"):
            export_journal(self.state, link / "different-output", self.binary)
        with self.assertRaises(ExportError):
            export_journal(self.state, self.state / "nested", self.binary)

    def test_resource_bounds_and_torn_records_leave_no_complete_export(self):
        self.fixture()
        with self.assertRaises(ExportError):
            self.export(batch_rows=0)
        for value in (True, 1.5, "1"):
            with self.assertRaises(ExportError):
                self.export(batch_rows=value)
        with self.assertRaises(ExportError):
            self.export(maximum_bytes=1)
        self.assertFalse((self.output / "manifest.json").exists())
        # A different output is required after any failed export; no overwrite retry.
        self.output = self.root / "second-export"
        path = self.state / "events.jsonl"
        path.write_bytes(path.read_bytes()[:-1])
        with self.assertRaises(ExportError):
            self.export()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_duplicate_json_owner_fields_are_rejected(self):
        self.fixture()
        path = self.state / "owner.json"
        data = path.read_bytes()
        path.write_bytes(data[:-1] + b',"namespace":"observer"}')
        with self.assertRaisesRegex(ExportError, "duplicate JSON"):
            self.export()
        self.assertFalse(self.output.exists())

    def test_nonstring_owner_values_fail_closed(self):
        self.fixture()
        path = self.state / "owner.json"
        owner = json.loads(path.read_bytes())
        owner["run_id"] = ["parquet-test"]
        path.write_bytes(packed(owner))
        with self.assertRaisesRegex(ExportError, "owner schema"):
            self.export()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
