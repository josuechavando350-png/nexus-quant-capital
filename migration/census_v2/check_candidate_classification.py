#!/usr/bin/env python3
"""Adversarial joins on actual pinned D08/D12 records; missing inputs fail."""
import argparse
import copy
from pathlib import Path
import unittest

import classify_historical_candidates as ledger
from gas_budget import replay


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        old = ledger.legacy()
        cls.summary, cls.actions, cls.promotions = old.read_d12(ARGS.d12)
        required, _, _, _ = old.parse_actionability(cls.actions, cls.promotions)
        cls.tokens, _, _ = old.scan_d08_tokens(ARGS.d08, required)

    def run_rows(self, actions=None, promotions=None, tokens=None):
        return ledger.classify(self.actions if actions is None else actions,
                               self.promotions if promotions is None else promotions,
                               self.tokens if tokens is None else tokens,
                               replay([]), "2026-10-09T23:00:00Z", self.summary["anchor"]["timestamp"])

    def test_real_population_and_join_conservation(self):
        rows = self.run_rows()
        self.assertEqual(len(rows), 474)
        self.assertEqual(len({r["borrower"] for r in rows}), 400)
        self.assertEqual(sum(r["classification"] == "NON_EXECUTABLE" for r in rows), 42)
        self.assertEqual(sum(r["classification"] == "INSUFFICIENT_EVIDENCE" for r in rows), 432)
        self.assertTrue(all(r["admitted_executable_value_mxn_centavos"] == 0 for r in rows))
        self.assertTrue(all(r["net_profit_estimate_mxn_centavos"] is None for r in rows))
        self.assertTrue(all(not r["decision_time"]["later_gas_authorization_applied_to_historical_state"] for r in rows))

    def test_input_order_cannot_change_ledger(self):
        self.assertEqual(self.run_rows(), self.run_rows(list(reversed(self.actions)), list(reversed(self.promotions))))

    def test_missing_or_duplicate_or_orphan_promotions_fail(self):
        cases = [self.promotions[:-1], self.promotions + self.promotions[:1]]
        altered = copy.deepcopy(self.promotions)
        altered[0]["actionable_candidate_id"] = "f" * 64
        cases.append(altered)
        for rows in cases:
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                self.run_rows(promotions=rows)

    def test_duplicate_pairs_fail(self):
        with self.assertRaises(ValueError):
            self.run_rows(self.actions + self.actions[:1])

    def test_capital_asset_amount_and_false_success_cannot_be_substituted(self):
        for field, value in {"debt_asset": "0x" + "1" * 40, "principal": "0" * 64,
                             "repayment_principal": "0" * 64, "flash_premium": "f" * 64,
                             "capital_status": "FEASIBLE", "gas_funding_certified": True,
                             "allocations": [{"fabricated": True}]}.items():
            rows = copy.deepcopy(self.promotions)
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_rows(promotions=rows)

    def test_missing_token_or_relabeling_blocked_as_compatible_fails(self):
        token = self.actions[0]["debt_asset"]
        rows = copy.deepcopy(self.tokens)
        del rows[token]
        with self.assertRaises(ValueError):
            self.run_rows(tokens=rows)
        rows = copy.deepcopy(self.tokens)
        rows[token]["AAVE_RESERVE_UNDERLYING"]["status"] = "PROVEN_COMPATIBLE"
        with self.assertRaises(ValueError):
            self.run_rows(tokens=rows)

    def test_unknown_rejection_cannot_be_claimed_impossible(self):
        rows = copy.deepcopy(self.actions)
        next(r for r in rows if r["status"] == "REJECTED")["reason"] = "UNKNOWN_STATE"
        with self.assertRaisesRegex(ValueError, "unhandled"):
            self.run_rows(actions=rows)

    def test_gas_policy_cannot_widen_principal_or_budget(self):
        import json
        policy = json.loads((Path(__file__).parent / "capital-policy.json").read_bytes())
        for change in ({"operator_principal_centavos": 1}, {"operator_guarantees_centavos": 1},
                       {"operator_gas_budget_centavos": 200001}, {"allowed_operator_purposes": ["PRINCIPAL"]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                ledger.validate_policy(json.dumps(dict(policy, **change)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--d08", type=Path, required=True)
    p.add_argument("--d12", type=Path, required=True)
    ARGS = p.parse_args()
    unittest.main(argv=[__file__], verbosity=2)
