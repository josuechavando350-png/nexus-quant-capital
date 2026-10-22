import copy
import unittest

from competition_ledger import CompetitionLedger, seal_ledger, transaction_metrics, validate_ledger


def h(ch):
    return ch * 64


def tx(ch):
    return "0x" + ch * 64


def addr(ch):
    return "0x" + ch * 40


def record(ch="1", complete=True):
    return {
        "transaction_hash": tx(ch),
        "subject_id": h(ch),
        "winner_address": addr("a"),
        "oracle_update_block": 100,
        "winner_block": 102,
        "liquidation_bonus_usd_wad": "1000",
        "builder_payment_usd_wad": "200" if complete else None,
        "winner_gas_usd_wad": "100" if complete else None,
        "other_observed_costs_usd_wad": "50" if complete else None,
        "observed_costs_complete": complete,
        "evidence_sha256": h("e"),
    }


class CompetitionLedgerTests(unittest.TestCase):
    def test_valid_ledger_passes(self):
        value = seal_ledger([record()])
        self.assertEqual(validate_ledger(value), [])

    def test_delay_is_exact(self):
        self.assertEqual(transaction_metrics(record())["blocks_from_oracle_to_winner"], 2)

    def test_builder_share_is_exact_floor_wad(self):
        metrics = transaction_metrics(record())
        self.assertEqual(metrics["builder_payment_share_of_bonus_wad"], "200000000000000000")

    def test_net_margin_is_observed_winner_not_nqc(self):
        metrics = transaction_metrics(record())
        self.assertEqual(metrics["observed_winner_net_margin_usd_wad"], "650")
        self.assertFalse(metrics["nqc_execution"])
        self.assertIsNone(metrics["nqc_realized_pnl_usd_wad"])

    def test_incomplete_costs_do_not_become_zero(self):
        item = record(complete=False)
        metrics = transaction_metrics(item)
        self.assertIsNone(metrics["observed_winner_net_margin_usd_wad"])
        self.assertIsNone(metrics["builder_payment_share_of_bonus_wad"])

    def test_complete_record_requires_all_costs(self):
        item = record()
        item["winner_gas_usd_wad"] = None
        with self.assertRaisesRegex(ValueError, "complete_record_missing_cost"):
            seal_ledger([item])

    def test_winner_before_oracle_is_blocked(self):
        item = record()
        item["winner_block"] = 99
        with self.assertRaisesRegex(ValueError, "winner_before_oracle"):
            seal_ledger([item])

    def test_duplicate_transaction_is_blocked(self):
        item = record()
        with self.assertRaisesRegex(ValueError, "duplicate_transaction"):
            seal_ledger([item, copy.deepcopy(item)])

    def test_bad_winner_address_is_blocked(self):
        item = record()
        item["winner_address"] = "bad"
        with self.assertRaisesRegex(ValueError, "winner_address_invalid"):
            seal_ledger([item])

    def test_float_amount_is_blocked(self):
        item = record()
        item["winner_gas_usd_wad"] = "1.5"
        with self.assertRaisesRegex(ValueError, "winner_gas_usd_wad_invalid"):
            seal_ledger([item])

    def test_zero_bonus_yields_unknown_share_not_division_error(self):
        item = record()
        item["liquidation_bonus_usd_wad"] = "0"
        metrics = transaction_metrics(item)
        self.assertIsNone(metrics["builder_payment_share_of_bonus_wad"])

    def test_negative_observed_margin_is_preserved(self):
        item = record()
        item["builder_payment_usd_wad"] = "900"
        item["winner_gas_usd_wad"] = "200"
        metrics = transaction_metrics(item)
        self.assertEqual(metrics["observed_winner_net_margin_usd_wad"], "-150")

    def test_summary_counts_only_complete_costs(self):
        ledger = CompetitionLedger(seal_ledger([record("1", True), record("2", False)]))
        summary = ledger.summary()
        self.assertEqual(summary["transaction_count"], 2)
        self.assertEqual(summary["complete_cost_transaction_count"], 1)
        self.assertEqual(summary["builder_share_observation_count"], 1)

    def test_summary_never_claims_nqc_profitability(self):
        summary = CompetitionLedger(seal_ledger([record()])).summary()
        self.assertFalse(summary["nqc_profitability_proven"])
        self.assertFalse(summary["current_market_claimed"])

    def test_unknown_transaction_is_blocked(self):
        ledger = CompetitionLedger(seal_ledger([record()]))
        with self.assertRaisesRegex(ValueError, "unknown_transaction"):
            ledger.metrics(tx("9"))

    def test_tamper_breaks_commitment(self):
        value = seal_ledger([record()])
        value["records"][0]["winner_block"] = 103
        self.assertIn("ledger_commitment_mismatch", validate_ledger(value))

    def test_unsorted_records_are_rejected(self):
        value = seal_ledger([record("2"), record("1")])
        value["records"].reverse()
        self.assertIn("records_not_canonically_sorted", validate_ledger(value))

    def test_all_authorities_are_false(self):
        value = seal_ledger([record()])
        for key in value["authorities"]:
            changed = copy.deepcopy(value)
            changed["authorities"][key] = True
            self.assertIn("authority_forbidden", validate_ledger(changed))

    def test_evidence_is_required(self):
        item = record()
        item["evidence_sha256"] = ""
        with self.assertRaisesRegex(ValueError, "evidence_invalid"):
            seal_ledger([item])

    def test_mean_builder_share_uses_only_observed_shares(self):
        a = record("1", True)
        b = record("2", True)
        b["builder_payment_usd_wad"] = "400"
        c = record("3", False)
        summary = CompetitionLedger(seal_ledger([a, b, c])).summary()
        self.assertEqual(summary["mean_builder_share_wad"], "300000000000000000")


if __name__ == "__main__":
    unittest.main()
