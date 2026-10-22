import copy
import unittest

from long_tail import LongTailPrioritizer, dominates, seal_priority_set, validate_priority_set


def h(ch):
    return ch * 64


def candidate(ch, *, age, size, steps, l2, chain=1):
    return {
        "market_id": h(ch),
        "chain_id": chain,
        "is_l2": l2,
        "market_age_blocks": str(age),
        "market_size_usd_wad": str(size),
        "route_complexity_steps": str(steps),
        "source_commitment_sha256": h("f"),
    }


class LongTailTests(unittest.TestCase):
    def test_valid_priority_set_passes(self):
        payload = seal_priority_set([
            candidate("1", age=10, size=100, steps=4, l2=True),
            candidate("2", age=20, size=200, steps=2, l2=False),
        ])
        self.assertEqual(validate_priority_set(payload), [])

    def test_clear_dominance(self):
        left = candidate("1", age=10, size=100, steps=4, l2=True)
        right = candidate("2", age=20, size=200, steps=2, l2=False)
        self.assertTrue(dominates(left, right))
        self.assertFalse(dominates(right, left))

    def test_tradeoff_is_non_dominated(self):
        left = candidate("1", age=10, size=1000, steps=4, l2=True)
        right = candidate("2", age=20, size=100, steps=2, l2=False)
        self.assertFalse(dominates(left, right))
        self.assertFalse(dominates(right, left))

    def test_first_front_contains_non_dominated_markets(self):
        p = LongTailPrioritizer(seal_priority_set([
            candidate("1", age=10, size=100, steps=4, l2=True),
            candidate("2", age=20, size=200, steps=2, l2=False),
            candidate("3", age=5, size=500, steps=5, l2=True),
        ]))
        self.assertEqual(p.pareto_fronts()[0], [h("1"), h("3")])

    def test_dominated_market_moves_to_later_front(self):
        p = LongTailPrioritizer(seal_priority_set([
            candidate("1", age=10, size=100, steps=4, l2=True),
            candidate("2", age=20, size=200, steps=2, l2=False),
        ]))
        self.assertEqual(p.pareto_fronts(), [[h("1")], [h("2")]])

    def test_queue_has_no_economic_score(self):
        p = LongTailPrioritizer(seal_priority_set([
            candidate("1", age=10, size=100, steps=4, l2=True),
        ]))
        row = p.research_queue()[0]
        self.assertIsNone(row["economic_score"])
        self.assertFalse(row["profitability_claimed"])
        self.assertTrue(row["research_only"])

    def test_deterministic_tie_break_is_market_id(self):
        p = LongTailPrioritizer(seal_priority_set([
            candidate("2", age=10, size=100, steps=4, l2=True),
            candidate("1", age=10, size=100, steps=4, l2=True),
        ]))
        self.assertEqual(p.pareto_fronts()[0], [h("1"), h("2")])

    def test_duplicate_market_is_blocked(self):
        item = candidate("1", age=10, size=100, steps=4, l2=True)
        with self.assertRaisesRegex(ValueError, "duplicate_market"):
            seal_priority_set([item, copy.deepcopy(item)])

    def test_float_age_is_blocked(self):
        item = candidate("1", age=10, size=100, steps=4, l2=True)
        item["market_age_blocks"] = "10.0"
        with self.assertRaisesRegex(ValueError, "market_age_blocks_invalid"):
            seal_priority_set([item])

    def test_float_size_is_blocked(self):
        item = candidate("1", age=10, size=100, steps=4, l2=True)
        item["market_size_usd_wad"] = "100.5"
        with self.assertRaisesRegex(ValueError, "market_size_invalid"):
            seal_priority_set([item])

    def test_zero_route_complexity_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "route_complexity_invalid"):
            seal_priority_set([candidate("1", age=10, size=100, steps=0, l2=True)])

    def test_is_l2_must_be_boolean(self):
        item = candidate("1", age=10, size=100, steps=4, l2=True)
        item["is_l2"] = 1
        with self.assertRaisesRegex(ValueError, "is_l2_invalid"):
            seal_priority_set([item])

    def test_chain_id_must_be_positive_int(self):
        item = candidate("1", age=10, size=100, steps=4, l2=True, chain=0)
        with self.assertRaisesRegex(ValueError, "chain_id_invalid"):
            seal_priority_set([item])

    def test_source_evidence_is_required(self):
        item = candidate("1", age=10, size=100, steps=4, l2=True)
        item["source_commitment_sha256"] = ""
        with self.assertRaisesRegex(ValueError, "source_commitment_invalid"):
            seal_priority_set([item])

    def test_tamper_breaks_commitment(self):
        payload = seal_priority_set([candidate("1", age=10, size=100, steps=4, l2=True)])
        payload["candidates"][0]["market_size_usd_wad"] = "101"
        self.assertIn("priority_commitment_mismatch", validate_priority_set(payload))

    def test_unsorted_candidates_are_rejected(self):
        payload = seal_priority_set([
            candidate("2", age=10, size=100, steps=4, l2=True),
            candidate("1", age=20, size=200, steps=2, l2=False),
        ])
        payload["candidates"].reverse()
        self.assertIn("candidates_not_canonically_sorted", validate_priority_set(payload))

    def test_all_execution_authorities_are_false(self):
        payload = seal_priority_set([candidate("1", age=10, size=100, steps=4, l2=True)])
        for key in payload["authorities"]:
            changed = copy.deepcopy(payload)
            changed["authorities"][key] = True
            self.assertIn("authority_forbidden", validate_priority_set(changed))

    def test_unknown_market_explanation_is_blocked(self):
        p = LongTailPrioritizer(seal_priority_set([
            candidate("1", age=10, size=100, steps=4, l2=True),
            candidate("2", age=20, size=200, steps=2, l2=False),
        ]))
        with self.assertRaisesRegex(ValueError, "unknown_market"):
            p.explain_pair(h("1"), h("9"))

    def test_pair_explanation_declares_no_economic_score(self):
        p = LongTailPrioritizer(seal_priority_set([
            candidate("1", age=10, size=100, steps=4, l2=True),
            candidate("2", age=20, size=200, steps=2, l2=False),
        ]))
        result = p.explain_pair(h("1"), h("2"))
        self.assertTrue(result["left_dominates_right"])
        self.assertIsNone(result["economic_score"])


if __name__ == "__main__":
    unittest.main()
