import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from historical_trace_audit import inspect


class TraceAuditTests(unittest.TestCase):
    def setUp(self):
        folder = ROOT / "evidence/2026-10-17"
        self.trace, self.block, self.receipt = [json.loads((folder/f"case_b{s}.json").read_text())
                                               for s in ("_trace", "_block", "")]

    def run_audit(self):
        return inspect(self.trace, self.block, self.receipt)

    def test_exact_interest_and_liquidation_parity(self):
        r = self.run_audit()
        self.assertEqual(r["accrual"]["interest"], 84501962012302301)
        self.assertEqual(r["quote"]["repaid_assets"], 26039738525656992415)
        self.assertEqual(r["quote"]["seized_assets"], 24343983926960874121)
        self.assertEqual(r["prior_transactions_unreplayed"], 1)
        self.assertFalse(r["certified"])
        self.assertFalse(r["live_executable"])

    def test_unwrapped_eth_all_goes_to_coinbase(self):
        r = self.run_audit()
        self.assertEqual(r["coinbase_received_wei"], 368092735714237547)
        self.assertEqual(r["executor_native_change_wei"], 0)
        self.assertIsNone(r["builder_income_wei"])
        self.assertIsNone(r["nqc_realized_profit"])

    def test_prior_weth_is_excluded_from_residual(self):
        r = self.run_audit()
        self.assertEqual(r["executor_initial_weth_wei"], 6392502690919791)
        self.assertEqual(r["executor_weth_increase_wei"], 1849712239770038)
        self.assertEqual(r["residual_minus_sender_gas_arithmetic_wei"], 1651296044494913)

    def test_missing_trace_rejected(self):
        self.trace["data"]["items"].pop()
        with self.assertRaises(ValueError): self.run_audit()

    def test_duplicate_trace_rejected(self):
        self.trace["data"]["items"].append(copy.deepcopy(self.trace["data"]["items"][-1]))
        with self.assertRaises(ValueError): self.run_audit()

    def test_failed_child_rejected(self):
        self.trace["data"]["items"][-1]["error"] = "Reverted"
        with self.assertRaises(ValueError): self.run_audit()

    def test_wrong_block_rejected(self):
        self.block["data"]["block_details"]["hash"] = "0x"+"00"*32
        with self.assertRaises(ValueError): self.run_audit()

    def test_must_not_relabel_position_as_first_transaction(self):
        self.receipt["data"]["position"] = 0
        with self.assertRaises(ValueError): self.run_audit()

    def test_changed_return_rejected(self):
        t = next(t for t in self.trace["data"]["items"] if t["traceAddress"] == [0,1,3])
        t["result"]["output"] = "0x"+"00"*64
        with self.assertRaises(ValueError): self.run_audit()

    def test_delegatecall_value_is_not_double_counted(self):
        t = next(t for t in self.trace["data"]["items"] if t["action"]["callType"] == "delegatecall")
        t["action"]["value"] = "0x123"
        self.assertEqual(self.run_audit()["executor_native_change_wei"], 0)

    def test_incomplete_pagination_rejected(self):
        self.trace["pagination"] = {"next_call": {}}
        with self.assertRaises(ValueError): self.run_audit()

    def test_different_receipt_transaction_rejected(self):
        self.receipt["request"]["transaction_hash"] = "0x" + "11"*32
        with self.assertRaises(ValueError): self.run_audit()

    def test_different_trace_request_rejected(self):
        self.trace["request"]["endpoint_path"] = "/api/v2/transactions/wrong/raw-trace"
        with self.assertRaises(ValueError): self.run_audit()

    def test_different_parent_block_rejected(self):
        self.block["data"]["block_details"]["parent_hash"] = "0x" + "11"*32
        with self.assertRaises(ValueError): self.run_audit()

    def test_receipt_input_must_match_trace_prefix(self):
        self.receipt["data"]["raw_input"] = "0xdeadbeef"
        with self.assertRaises(ValueError): self.run_audit()

    def test_token_receipt_must_match_executed_transfer(self):
        self.receipt["data"]["token_transfers"][0]["total"]["value"] = "1"
        with self.assertRaises(ValueError): self.run_audit()

    def test_normalized_wrap_must_match_native_flow(self):
        self.receipt["data"]["token_transfers"][2]["total"]["value"] = "1"
        with self.assertRaises(ValueError): self.run_audit()
