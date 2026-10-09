import copy
import hashlib
import itertools
import unittest

from gas_budget import Budget, MAX_CENTAVOS, POLICY, UINT256_MAX, replay

WALLET = "0x" + "1" * 40
AT = "2026-10-09T16:00:00Z"


def event(kind, eid, **changes):
    row = {"event_id": eid, "kind": kind, "at": AT, "received_at": AT,
           "policy_id": POLICY, "chain_id": 1, "wallet": WALLET,
           "evidence_sha256": hashlib.sha256(eid.encode()).hexdigest()}
    if kind == "FUND":
        row.update(native_wei=1000, cost_centavos=MAX_CENTAVOS)
    if kind == "RESERVE":
        row.update(nonce=0, tx_hash="0x" + hashlib.sha256(eid.encode()).hexdigest(),
                   purpose="NATIVE_NETWORK_GAS", gas_limit=100, max_fee_per_gas=5,
                   data_and_blob_fee_cap_wei=0)
    if kind == "SETTLE":
        row.update(nonce=0, tx_hash="0x" + hashlib.sha256(b"r").hexdigest(), gas_used=70,
                   effective_gas_price=4, data_and_blob_fee_wei=0, outcome="FINALIZED_SUCCESS")
    row.update(changes)
    return row


class GasBudgetTests(unittest.TestCase):
    def funded(self):
        b = Budget()
        b.apply(event("FUND", "f"))
        return b

    def test_budget_is_global_and_cumulative(self):
        b = Budget()
        b.apply(event("FUND", "f", cost_centavos=100000))
        b.apply(event("FUND", "f2", chain_id=8453, cost_centavos=100000))
        with self.assertRaisesRegex(ValueError, "contribution cap"):
            b.apply(event("FUND", "f3", cost_centavos=1))
        self.assertEqual(b.contributed, 200000)

    def test_integer_minor_unit_boundary(self):
        for amount in (200001, -1, 0, True, 200000.0, "200000"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                Budget().apply(event("FUND", "f", cost_centavos=amount))

    def test_revert_spends_real_gas_and_does_not_replenish_capital(self):
        b = self.funded()
        b.apply(event("RESERVE", "r"))
        b.apply(event("SETTLE", "s", outcome="FINALIZED_REVERT"))
        w = b.report()["wallets"][0]
        self.assertEqual((w["gas_paid_wei"], w["reverted_gas_paid_wei"], w["native_available_wei"]), (280, 280, 720))
        self.assertEqual(b.report()["uncontributed_budget_centavos"], 0)

    def test_no_native_money_invented_from_peso_budget(self):
        with self.assertRaisesRegex(ValueError, "insufficient native"):
            Budget().apply(event("RESERVE", "r"))

    def test_distinct_nonces_sum_and_failed_reservation_is_atomic(self):
        b = self.funded()
        b.apply(event("RESERVE", "r"))
        b.apply(event("RESERVE", "r2", nonce=1))
        before = copy.deepcopy(b.__dict__)
        with self.assertRaisesRegex(ValueError, "concurrent holds"):
            b.apply(event("RESERVE", "r3", nonce=2, gas_limit=1, max_fee_per_gas=1))
        self.assertEqual(b.__dict__, before)

    def test_replacement_never_releases_older_variant_exposure(self):
        b = self.funded()
        b.apply(event("RESERVE", "r", max_fee_per_gas=9))
        b.apply(event("RESERVE", "low", max_fee_per_gas=1))
        self.assertEqual(b.report()["wallets"][0]["native_reserved_wei"], 900)
        with self.assertRaises(ValueError):
            b.apply(event("RESERVE", "other", nonce=1, max_fee_per_gas=2))
        b.apply(event("SETTLE", "s"))  # Older variant can win.
        self.assertEqual(b.report()["wallets"][0]["native_reserved_wei"], 0)

    def test_failed_higher_bid_does_not_change_old_hold(self):
        b = self.funded()
        b.apply(event("RESERVE", "r"))
        before = b.report()
        with self.assertRaises(ValueError):
            b.apply(event("RESERVE", "huge", max_fee_per_gas=11))
        self.assertEqual(b.report(), before)

    def test_no_double_payment_or_reuse_of_nonce(self):
        b = self.funded()
        b.apply(event("RESERVE", "r"))
        b.apply(event("SETTLE", "s"))
        for row in (event("SETTLE", "s2"), event("RESERVE", "r2")):
            with self.assertRaisesRegex(ValueError, "nonce already"):
                b.apply(row)

    def test_nonce_namespaces_are_per_chain_and_wallet(self):
        b = Budget()
        b.apply(event("FUND", "f", cost_centavos=100000))
        b.apply(event("FUND", "f2", chain_id=8453, cost_centavos=100000))
        b.apply(event("RESERVE", "r"))
        b.apply(event("RESERVE", "r2", chain_id=8453))
        self.assertEqual([w["native_reserved_wei"] for w in b.report()["wallets"]], [500, 500])

    def test_failure_liability_is_bounded_by_all_network_fee_components(self):
        b = self.funded()
        b.apply(event("RESERVE", "r", data_and_blob_fee_cap_wei=400))
        self.assertEqual(b.report()["wallets"][0]["native_available_wei"], 100)
        b.apply(event("SETTLE", "s", data_and_blob_fee_wei=300, outcome="FINALIZED_REVERT"))
        self.assertEqual(b.report()["wallets"][0]["reverted_gas_paid_wei"], 580)

    def test_unbounded_or_unfinalized_receipts_fail_without_mutation(self):
        for change in ({"gas_used": 101}, {"effective_gas_price": 6},
                       {"data_and_blob_fee_wei": 1}, {"outcome": "PENDING"}, {"nonce": 7}):
            b = self.funded()
            b.apply(event("RESERVE", "r"))
            before = b.report()
            with self.subTest(change=change), self.assertRaises(ValueError):
                b.apply(event("SETTLE", "s", **change))
            self.assertEqual(b.report(), before)

    def test_operator_money_cannot_be_principal_or_builder_deposit(self):
        for purpose in ("PRINCIPAL", "COLLATERAL", "GUARANTEE", "BUILDER_DEPOSIT", "INFRASTRUCTURE"):
            with self.subTest(purpose=purpose), self.assertRaises(ValueError):
                self.funded().apply(event("RESERVE", "r", purpose=purpose))

    def test_duplicate_funding_receipt_is_not_new_money(self):
        b = Budget()
        f = event("FUND", "f", cost_centavos=1)
        b.apply(f)
        with self.assertRaisesRegex(ValueError, "evidence reused"):
            b.apply(dict(f, event_id="f2"))

    def test_event_replay_and_evidence_timing(self):
        b = self.funded()
        for row in (event("FUND", "f"), event("RESERVE", "r", at="2026-10-09T15:59:59Z"),
                    event("RESERVE", "r", received_at="2026-10-09T16:00:01Z")):
            with self.assertRaises(ValueError):
                b.apply(row)

    def test_unknown_fields_and_implicit_reset_release_are_rejected(self):
        for row in (event("FUND", "f", balance_override=100), event("RESET", "reset"), event("RELEASE", "release")):
            with self.assertRaises(ValueError):
                Budget().apply(row)

    def test_overflow_and_boolean_native_quantities_are_rejected(self):
        for changes in ({"gas_limit": True}, {"max_fee_per_gas": -1},
                        {"gas_limit": UINT256_MAX, "max_fee_per_gas": 2}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.funded().apply(event("RESERVE", "r", **changes))

    def test_exhaustive_small_replacement_sets_match_resource_oracle(self):
        # Independent mathematical resource oracle: one transaction per nonce;
        # reserve the maximum possible spend for each mutually exclusive group.
        for prices in itertools.product(range(1, 5), repeat=3):
            b = self.funded()
            for i, price in enumerate(prices):
                b.apply(event("RESERVE", "r" + str(i), nonce=i // 2, max_fee_per_gas=price))
            oracle = max(100 * prices[0], 100 * prices[1]) + 100 * prices[2]
            self.assertEqual(b.report()["wallets"][0]["native_reserved_wei"], oracle)

    def test_deterministic_and_never_self_certifies(self):
        rows = [event("FUND", "f"), event("RESERVE", "r"), event("SETTLE", "s")]
        self.assertEqual(replay(rows), replay(copy.deepcopy(rows)))
        for flag in ("funding_authenticity_verified", "receipt_semantics_verified",
                     "capital_feasibility_certified", "real_market_census_closed", "operational_executor_connected"):
            self.assertIs(replay(rows)[flag], False)


if __name__ == "__main__":
    unittest.main()
