"""Actual Rust/Polars planning from historical bytes and labelled fixtures."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from export_parquet import ExportError
from prepare_aave_reads import prepare
import test_export_parquet as fixtures

STATE = Path(__file__).resolve().parents[1] / "evidence/public-capture-v2-20261022/state"


class AaveReadPlansTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ParquetExportTests.setUpClass()
        cls.binary = Path(os.environ["NQC_MINER_TEST_BINARY"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nqc-miner-aave-plan-")
        self.root = Path(self.temp.name)
        self.output = self.root / "plans"

    def tearDown(self):
        self.temp.cleanup()

    def test_three_plans_bind_exact_events_borrowers_assets_and_pre_event_blocks(self):
        original = {p.name: p.read_bytes() for p in STATE.iterdir() if p.is_file()}
        result = prepare(STATE, self.output, self.binary)
        self.assertEqual(len(result["events"]), 3)
        self.assertEqual(result["data_class"], "historical")
        self.assertFalse(result["live_reads_executed"])
        records = [json.loads(l)["record"] for l in original["events.jsonl"].splitlines()]
        records = [r for r in records if r["kind"] == "observed"]
        for entry, record in zip(result["events"], records):
            plan = json.loads((self.output / entry["plan_file"]).read_bytes())
            payload = record["decoded"]["payload"]
            self.assertEqual(entry["event_identity"], payload["identity"])
            self.assertEqual(plan["borrower"], payload["borrower"])
            self.assertEqual(set(plan["assets"]), {payload["debt_token"], payload["collateral_token"]})
            self.assertEqual((plan["from_block"], plan["to_block"]), (record["log"]["block_number"] - 16, record["log"]["block_number"] - 1))
            self.assertEqual(plan["event_block_hash"], record["log"]["block_hash"])
        self.assertEqual(original, {p.name: p.read_bytes() for p in STATE.iterdir() if p.is_file()})
        template = json.loads((self.output / "config.template.json").read_bytes())
        self.assertTrue(template["run_id"].startswith("aave-state-"))
        self.assertNotEqual(template["run_id"], result["source_owner"]["run_id"])
        self.assertEqual(template["code_commit"], "__FROM_ABOUT__")

    def test_deterministic_plan_replay(self):
        a = prepare(STATE, self.output, self.binary, 1)
        b = prepare(STATE, self.root / "replay", self.binary, 1)
        self.assertEqual(a, b)
        for entry in a["events"]:
            self.assertEqual(entry["sample_blocks"], 1)
            path = entry["plan_file"]
            self.assertEqual((self.output / path).read_bytes(), (self.root / "replay" / path).read_bytes())

    def test_rejects_invalid_limits_before_creating_output(self):
        for value in (0, 65, -1, True, 1.0):
            with self.subTest(value=value), self.assertRaises(ExportError):
                prepare(STATE, self.output, self.binary, value)
        self.assertFalse(self.output.exists())

    def test_corrupted_journal_rejected_by_rust(self):
        state = self.root / "state"
        shutil.copytree(STATE, state)
        p = state / "events.jsonl"
        p.write_bytes(p.read_bytes().replace(b'"observed_at":1792695288', b'"observed_at":1792695289'))
        with self.assertRaisesRegex(ExportError, "Rust verifier rejected"):
            prepare(state, self.output, self.binary)
        self.assertFalse((self.output / "manifest.json").exists())

    def test_incomplete_and_revoked_fixture_not_admitted(self):
        for options in ({"complete": False}, {"invalidated": True}):
            helper = fixtures.ParquetExportTests()
            helper.setUp()
            try:
                helper.fixture(version=2, **options)
                with self.assertRaisesRegex(ExportError, "complete unrevoked"):
                    prepare(helper.state, helper.output, self.binary)
                self.assertFalse((helper.output / "manifest.json").exists())
            finally:
                helper.tearDown()

    def test_other_protocol_is_not_relabelled_as_aave(self):
        helper = fixtures.ParquetExportTests()
        helper.setUp()
        try:
            helper.fixture(version=2)
            result = prepare(helper.state, helper.output, self.binary)
            self.assertEqual(result["events"], [])
            self.assertEqual(result["data_class"], "synthetic")
        finally:
            helper.tearDown()

    def test_shadow_and_detached_windows_rejected_before_output(self):
        state = self.root / "state"
        shutil.copytree(STATE, state)
        p = state / "owner.json"
        owner = json.loads(p.read_bytes())
        for changes in ({"data_class": "shadow"}, {"run_id": "window-" + "0" * 64}):
            p.write_text(json.dumps({**owner, **changes}))
            with self.assertRaises(ExportError):
                prepare(state, self.output, self.binary)
        self.assertFalse(self.output.exists())

    def test_existing_output_and_symlinks_rejected(self):
        self.output.mkdir()
        with self.assertRaises(ExportError):
            prepare(STATE, self.output, self.binary)
        self.output.rmdir()
        state = self.root / "state"
        state.symlink_to(STATE, target_is_directory=True)
        with self.assertRaises(ExportError):
            prepare(state, self.output, self.binary)


if __name__ == "__main__":
    unittest.main()
