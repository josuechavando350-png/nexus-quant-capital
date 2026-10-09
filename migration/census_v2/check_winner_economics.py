#!/usr/bin/env python3
"""Adversarial checks against required real archives and raw receipts."""
import argparse
import copy
import json
from pathlib import Path
import unittest

import reconcile_winner_economics as m
from rmc016_weth_cashflow_audit import calculate as historical_calculate


class RealEconomicEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = m.sources(ARGS.archive_root, ARGS.metadata, ARGS.rpc_root)
        cls.files, cls.report = m.reconcile(ARGS.archive_root, ARGS.metadata, ARGS.rpc_root)
        cls.rows = [json.loads(line) for line in cls.files["winner-economic-ledger.jsonl"].splitlines()]
        cls.flashes = [json.loads(line) for line in cls.files["observed-flash-events.jsonl"].splitlines()]
        cls.weth = [json.loads(line) for line in cls.files["weth-cost-reference.jsonl"].splitlines()]

    def test_real_denominator_and_gas_not_double_counted(self):
        self.assertEqual(len(self.rows), 127)
        self.assertEqual(len({r["transaction_hash"] for r in self.rows}), 127)
        self.assertEqual(sum(len(r["liquidation_log_indices"]) for r in self.rows), 139)
        self.assertEqual(sum(int(r["historical_gas"]["whole_transaction_wei"]) for r in self.rows),
                         448369976498898050)
        self.assertTrue(any(len(r["liquidation_log_indices"]) > 1 for r in self.rows))
        self.assertTrue(all(r["historical_gas"]["counted_times"] == 1 for r in self.rows))
        self.assertEqual(self.report["raw_receipt_transactions"], 123)
        self.assertEqual(self.report["two_operator_full_log_matches"], 87)
        self.assertEqual(len(self.report["raw_receipts_missing"]), 4)

    def test_actual_flash_fee_events_and_no_financing_promotion(self):
        self.assertEqual(len(self.flashes), 20)
        bal = [r for r in self.flashes if r["protocol"] == "BALANCER_V2"]
        aave = [r for r in self.flashes if r["protocol"] == "AAVE_V3"]
        self.assertEqual(len(bal), 19)
        self.assertTrue(all(r["event_fee_raw"] == "0" for r in bal))
        self.assertEqual(len(aave), 1)
        self.assertEqual(aave[0]["principal_raw"], "12412")
        self.assertEqual(aave[0]["event_fee_raw"], "7")
        self.assertEqual(aave[0]["asset"], "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599")
        self.assertFalse(self.report["flash_events_prove_nqc_admissible_capital"])
        self.assertTrue(all(r["complete_realized_net_usd_wad"] is None for r in self.rows))
        self.assertTrue(all(all(v is None for v in r["unresolved_costs"].values()) for r in self.rows))
        self.assertTrue(all(r["classification"] == "INSUFFICIENT_EVIDENCE" for r in self.rows))
        self.assertFalse(self.report["real_market_census_closed"])

    def test_independent_arithmetic_matches_historical_consumer(self):
        receipts, legs, _, _, prices, _, _ = self.inputs
        old = historical_calculate(legs, receipts, prices)
        self.assertEqual(len(old), len(self.weth))
        for old_row, row in zip(old, self.weth):
            self.assertEqual(old_row["transaction_hash"], row["transaction_hash"])
            self.assertEqual(old_row["collateral_minus_debt_minus_winner_gas_wei"],
                             row["collateral_minus_debt_minus_competitor_gas_wei"])
            self.assertEqual(old_row["conditional_remaining_before_other_costs_wei"],
                             row["conditional_remainder_before_other_costs_wei"])
            if row["preblock_usd_reference"] is not None:
                self.assertEqual(old_row["preblock_usd_wad_conditional_cost_budget"],
                                 row["preblock_usd_reference"]["conditional_remainder_usd_wad"])
        self.assertEqual(self.report["weth_positive_after_competitor_gas"], 9)
        self.assertEqual(self.report["weth_positive_after_illustrative_5bps"], 8)
        self.assertEqual(self.report["weth_source_priced_retrospective_ranks"], [1, 3])
        self.assertEqual(self.weth[-1]["conditional_remainder_before_other_costs_wei"], "-2049022153595")
        self.assertIsNone(self.weth[1]["preblock_usd_reference"])
        self.assertFalse(self.report["gas_authorization_applies_to_historical_window"])

    def raw_example(self, *, flash=False):
        observed = self.inputs[2]
        for providers in observed.values():
            sem = next(iter(providers.values()))
            if not flash or any(m.flash_event(log) is not None for log in sem["logs"]):
                return {"from": sem["from"], "to": sem["to"], "logs": copy.deepcopy(sem["logs"])}, sem["receipt"]
        self.fail("real receipt fixture missing")

    def test_all_logs_are_bound_not_just_liquidations(self):
        raw, rec = self.raw_example()
        original = m.semantic_receipt(raw, rec)
        for edit in (
            lambda x: x["logs"][0].update(transactionHash="0x" + "00"*32),
            lambda x: x["logs"][0].update(removed=True),
            lambda x: x["logs"].insert(1, copy.deepcopy(x["logs"][0])),
            lambda x: x["logs"][0].update(transactionIndex="0x00"),
        ):
            altered = copy.deepcopy(raw)
            edit(altered)
            with self.assertRaises(ValueError):
                m.semantic_receipt(altered, rec)
        changed = copy.deepcopy(raw)
        changed["logs"][0]["address"] = "0x" + "11" * 20
        self.assertNotEqual(original, m.semantic_receipt(changed, rec))

    def test_known_flash_abi_rejects_padding_shape_and_wrong_emitter(self):
        raw, _ = self.raw_example(flash=True)
        log = next(x for x in raw["logs"] if m.flash_event(x) is not None)
        for edit in (
            lambda x: x["topics"].__setitem__(1, "0x01" + x["topics"][1][4:]),
            lambda x: x.update(data=x["data"][:-2]),
            lambda x: x["topics"].append("0x" + "00"*32),
        ):
            bad = copy.deepcopy(log)
            edit(bad)
            with self.assertRaises(ValueError):
                m.flash_event(bad)
        bad = copy.deepcopy(log)
        bad["address"] = "0x" + "11"*20
        self.assertIsNone(m.flash_event(bad))
        aave_log = next(log for providers in self.inputs[2].values()
                        for log in next(iter(providers.values()))["logs"]
                        if log["topics"] and log["topics"][0] == m.AAVE_FLASH)
        bad = copy.deepcopy(aave_log)
        bad["data"] = bad["data"][:130] + format(256, "064x") + bad["data"][194:]
        with self.assertRaises(ValueError):
            m.flash_event(bad)

    def test_transfer_shape_and_self_transfer_do_not_create_profit(self):
        raw, _ = self.raw_example()
        log = next(copy.deepcopy(x) for x in raw["logs"] if len(x["topics"]) == 3
                   and x["topics"][0] == m.TRANSFER and len(x["data"]) == 66)
        log["topics"][2] = log["topics"][1]
        flows, count, ambiguous = m.token_flows([log])
        self.assertEqual((count, ambiguous), (1, 0))
        self.assertTrue(all(v == 0 for v in flows.values()))
        log["topics"].append(log["data"])
        log["data"] = "0x"
        self.assertEqual(m.token_flows([log]), ({}, 0, 1))
        self.assertFalse(self.report["transfer_logs_are_balance_proof"])

    def test_wrong_price_block_and_duplicate_price_rejected(self):
        receipts, legs, _, _, prices, _, _ = self.inputs
        altered = copy.deepcopy(prices)
        altered[0]["preblock"]["block"] += 1
        with self.assertRaises(ValueError):
            m.weth_reference(legs, receipts, altered)
        with self.assertRaises(ValueError):
            m.weth_reference(legs, receipts, [prices[0], prices[0]])

    def test_deterministic_outputs_and_fail_closed_missing_sources(self):
        again, _ = m.reconcile(ARGS.archive_root, ARGS.metadata, ARGS.rpc_root)
        self.assertEqual(again, self.files)
        with self.assertRaises(FileNotFoundError):
            m.reconcile(ARGS.archive_root/"missing", ARGS.metadata, ARGS.rpc_root)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-root", type=Path, required=True)
    p.add_argument("--metadata", type=Path, default=m.HERE/"evidence/winner-api")
    p.add_argument("--rpc-root", type=Path, required=True)
    ARGS, remaining = p.parse_known_args()
    unittest.main(argv=[__file__] + remaining)
