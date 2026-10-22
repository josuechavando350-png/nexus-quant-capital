import copy
import unittest

from oracle_semantics import OracleSemanticsRegistry, seal_registry, validate_registry


def h(ch):
    return ch * 64


def bh(ch):
    return "0x" + ch * 64


ANCHOR = {"chain_id": 1, "block_number": 26000000, "block_hash": bh("a")}


def oracle(ch, semantic, base, quote):
    return {
        "oracle_id": h(ch),
        "semantic_class": semantic,
        "base_asset_id": h(base),
        "quote_asset_id": h(quote),
        "source_commitment_sha256": h("f"),
    }


def market(ch, collateral, debt):
    return {
        "market_id": h(ch),
        "collateral_oracle_id": h(collateral),
        "debt_oracle_id": h(debt),
        "source_commitment_sha256": h("e"),
    }


class OracleSemanticsTests(unittest.TestCase):
    def fixture(self):
        return (
            [
                oracle("1", "MARKET_PRICE", "a", "b"),
                oracle("2", "EXCHANGE_RATE", "c", "d"),
            ],
            [market("3", "1", "2")],
        )

    def test_valid_registry_passes(self):
        oracles, markets = self.fixture()
        registry = seal_registry(ANCHOR, oracles, markets)
        self.assertEqual(validate_registry(registry), [])

    def test_market_price_reports_direct_spot_exposure(self):
        oracles, markets = self.fixture()
        registry = OracleSemanticsRegistry(seal_registry(ANCHOR, oracles, markets))
        result = registry.oracle_semantics(h("1"))
        self.assertTrue(result["spot_depeg_directly_reflected"])

    def test_exchange_rate_does_not_claim_direct_spot_depeg(self):
        oracles, markets = self.fixture()
        registry = OracleSemanticsRegistry(seal_registry(ANCHOR, oracles, markets))
        result = registry.oracle_semantics(h("2"))
        self.assertFalse(result["spot_depeg_directly_reflected"])
        self.assertIn("NOT_DIRECTLY_REFLECTED", result["note"])

    def test_market_exposure_combines_both_sides(self):
        oracles, markets = self.fixture()
        registry = OracleSemanticsRegistry(seal_registry(ANCHOR, oracles, markets))
        result = registry.market_depeg_exposure(h("3"))
        self.assertTrue(result["any_direct_spot_exposure"])
        self.assertEqual(result["collateral"]["semantic_class"], "MARKET_PRICE")
        self.assertEqual(result["debt"]["semantic_class"], "EXCHANGE_RATE")

    def test_unknown_semantic_class_is_blocked(self):
        oracles, markets = self.fixture()
        oracles[0]["semantic_class"] = "GUESS_FROM_SYMBOL"
        with self.assertRaisesRegex(ValueError, "oracle_semantic_class_invalid"):
            seal_registry(ANCHOR, oracles, markets)

    def test_duplicate_oracle_is_blocked(self):
        oracles, markets = self.fixture()
        oracles.append(copy.deepcopy(oracles[0]))
        with self.assertRaisesRegex(ValueError, "duplicate_oracle"):
            seal_registry(ANCHOR, oracles, markets)

    def test_duplicate_market_is_blocked(self):
        oracles, markets = self.fixture()
        markets.append(copy.deepcopy(markets[0]))
        with self.assertRaisesRegex(ValueError, "duplicate_market"):
            seal_registry(ANCHOR, oracles, markets)

    def test_unresolved_market_oracle_is_blocked(self):
        oracles, markets = self.fixture()
        markets[0]["collateral_oracle_id"] = h("9")
        with self.assertRaisesRegex(ValueError, "market_oracle_unresolved"):
            seal_registry(ANCHOR, oracles, markets)

    def test_oracle_evidence_is_required(self):
        oracles, markets = self.fixture()
        oracles[0]["source_commitment_sha256"] = ""
        with self.assertRaisesRegex(ValueError, "oracle_evidence_invalid"):
            seal_registry(ANCHOR, oracles, markets)

    def test_market_evidence_is_required(self):
        oracles, markets = self.fixture()
        markets[0]["source_commitment_sha256"] = ""
        with self.assertRaisesRegex(ValueError, "market_evidence_invalid"):
            seal_registry(ANCHOR, oracles, markets)

    def test_same_base_and_quote_is_blocked(self):
        oracles, markets = self.fixture()
        oracles[0]["quote_asset_id"] = oracles[0]["base_asset_id"]
        with self.assertRaisesRegex(ValueError, "oracle_asset_pair_invalid"):
            seal_registry(ANCHOR, oracles, markets)

    def test_tamper_breaks_commitment(self):
        oracles, markets = self.fixture()
        registry = seal_registry(ANCHOR, oracles, markets)
        registry["oracles"][0]["semantic_class"] = "EXCHANGE_RATE"
        self.assertIn("registry_commitment_mismatch", validate_registry(registry))

    def test_unsorted_oracles_are_rejected(self):
        oracles, markets = self.fixture()
        registry = seal_registry(ANCHOR, oracles, markets)
        registry["oracles"].reverse()
        self.assertIn("oracles_not_canonically_sorted", validate_registry(registry))

    def test_unsorted_markets_are_rejected(self):
        oracles = [
            oracle("1", "MARKET_PRICE", "a", "b"),
            oracle("2", "EXCHANGE_RATE", "c", "d"),
        ]
        markets = [market("4", "1", "2"), market("3", "1", "2")]
        registry = seal_registry(ANCHOR, oracles, markets)
        registry["markets"].reverse()
        self.assertIn("markets_not_canonically_sorted", validate_registry(registry))

    def test_unknown_oracle_query_is_blocked(self):
        oracles, markets = self.fixture()
        registry = OracleSemanticsRegistry(seal_registry(ANCHOR, oracles, markets))
        with self.assertRaisesRegex(ValueError, "unknown_oracle"):
            registry.oracle_semantics(h("9"))

    def test_unknown_market_query_is_blocked(self):
        oracles, markets = self.fixture()
        registry = OracleSemanticsRegistry(seal_registry(ANCHOR, oracles, markets))
        with self.assertRaisesRegex(ValueError, "unknown_market"):
            registry.market_depeg_exposure(h("9"))

    def test_no_token_symbol_heuristic_field_exists(self):
        oracles, markets = self.fixture()
        registry = seal_registry(ANCHOR, oracles, markets)
        self.assertNotIn("symbol", registry["oracles"][0])
        self.assertNotIn("name", registry["oracles"][0])

    def test_all_execution_authorities_are_false(self):
        oracles, markets = self.fixture()
        registry = seal_registry(ANCHOR, oracles, markets)
        for key in registry["authorities"]:
            changed = copy.deepcopy(registry)
            changed["authorities"][key] = True
            self.assertIn("authority_forbidden", validate_registry(changed))


if __name__ == "__main__":
    unittest.main()
