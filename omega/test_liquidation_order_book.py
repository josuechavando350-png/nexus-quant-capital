import copy
import unittest

from liquidation_order_book import LiquidationOrderBook, seal_book, validate_book


def h(ch):
    return ch * 64


def bh(ch):
    return "0x" + ch * 64


def entry(position, oracle, direction, numerator, denominator="1"):
    return {
        "position_id": h(position),
        "oracle_id": h(oracle),
        "direction": direction,
        "threshold_numerator": str(numerator),
        "threshold_denominator": str(denominator),
        "source_commitment_sha256": h("f"),
    }


ANCHOR = {"chain_id": 1, "block_number": 26000000, "block_hash": bh("a")}


class LiquidationOrderBookTests(unittest.TestCase):
    def test_fraction_is_reduced_canonically(self):
        book = seal_book(ANCHOR, [entry("1", "a", "AT_OR_BELOW", 200, 2)])
        item = book["entries"][0]
        self.assertEqual((item["threshold_numerator"], item["threshold_denominator"]), ("100", "1"))

    def test_duplicate_position_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "duplicate_position"):
            seal_book(ANCHOR, [
                entry("1", "a", "AT_OR_BELOW", 100),
                entry("1", "a", "AT_OR_ABOVE", 200),
            ])

    def test_zero_denominator_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "threshold_denominator_invalid"):
            seal_book(ANCHOR, [entry("1", "a", "AT_OR_BELOW", 100, 0)])

    def test_float_like_inputs_are_blocked(self):
        with self.assertRaisesRegex(ValueError, "threshold_numerator_invalid"):
            seal_book(ANCHOR, [entry("1", "a", "AT_OR_BELOW", "100.0")])

    def test_bad_direction_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "direction_invalid"):
            seal_book(ANCHOR, [entry("1", "a", "BELOW", 100)])

    def test_downward_crossing_is_exact(self):
        idx = LiquidationOrderBook(seal_book(ANCHOR, [
            entry("1", "a", "AT_OR_BELOW", 100),
            entry("2", "a", "AT_OR_BELOW", 90),
        ]))
        self.assertEqual(idx.crossed(h("a"), "105", "1", "95", "1"), [h("1")])

    def test_upward_crossing_is_exact(self):
        idx = LiquidationOrderBook(seal_book(ANCHOR, [
            entry("1", "a", "AT_OR_ABOVE", 110),
            entry("2", "a", "AT_OR_ABOVE", 120),
        ]))
        self.assertEqual(idx.crossed(h("a"), "100", "1", "115", "1"), [h("1")])

    def test_boundary_is_inclusive_only_on_current_side(self):
        idx = LiquidationOrderBook(seal_book(ANCHOR, [entry("1", "a", "AT_OR_BELOW", 100)]))
        self.assertEqual(idx.crossed(h("a"), "101", "1", "100", "1"), [h("1")])
        self.assertEqual(idx.crossed(h("a"), "100", "1", "99", "1"), [])

    def test_opposite_price_motion_does_not_cross_wrong_direction(self):
        idx = LiquidationOrderBook(seal_book(ANCHOR, [
            entry("1", "a", "AT_OR_BELOW", 100),
            entry("2", "a", "AT_OR_ABOVE", 120),
        ]))
        self.assertEqual(idx.crossed(h("a"), "90", "1", "110", "1"), [])
        self.assertEqual(idx.crossed(h("a"), "130", "1", "110", "1"), [])

    def test_multiple_downward_crossings_follow_encounter_order(self):
        idx = LiquidationOrderBook(seal_book(ANCHOR, [
            entry("1", "a", "AT_OR_BELOW", 100),
            entry("2", "a", "AT_OR_BELOW", 90),
            entry("3", "a", "AT_OR_BELOW", 80),
        ]))
        self.assertEqual(
            idx.crossed(h("a"), "105", "1", "75", "1"),
            [h("1"), h("2"), h("3")],
        )

    def test_multiple_upward_crossings_follow_encounter_order(self):
        idx = LiquidationOrderBook(seal_book(ANCHOR, [
            entry("1", "a", "AT_OR_ABOVE", 100),
            entry("2", "a", "AT_OR_ABOVE", 110),
            entry("3", "a", "AT_OR_ABOVE", 120),
        ]))
        self.assertEqual(
            idx.crossed(h("a"), "95", "1", "125", "1"),
            [h("1"), h("2"), h("3")],
        )

    def test_active_at_returns_both_directions(self):
        idx = LiquidationOrderBook(seal_book(ANCHOR, [
            entry("1", "a", "AT_OR_BELOW", 100),
            entry("2", "a", "AT_OR_ABOVE", 80),
            entry("3", "a", "AT_OR_BELOW", 70),
        ]))
        self.assertEqual(idx.active_at(h("a"), "90", "1"), sorted([h("1"), h("2")]))

    def test_oracles_are_isolated(self):
        idx = LiquidationOrderBook(seal_book(ANCHOR, [
            entry("1", "a", "AT_OR_BELOW", 100),
            entry("2", "b", "AT_OR_BELOW", 100),
        ]))
        self.assertEqual(idx.crossed(h("a"), "105", "1", "95", "1"), [h("1")])

    def test_huge_integer_ratios_remain_exact(self):
        huge = 2**255 - 19
        idx = LiquidationOrderBook(seal_book(ANCHOR, [
            entry("1", "a", "AT_OR_BELOW", huge, 10**18),
        ]))
        self.assertEqual(
            idx.crossed(h("a"), str(huge + 1), str(10**18), str(huge), str(10**18)),
            [h("1")],
        )

    def test_tampered_threshold_breaks_commitment(self):
        book = seal_book(ANCHOR, [entry("1", "a", "AT_OR_BELOW", 100)])
        book["entries"][0]["threshold_numerator"] = "99"
        self.assertIn("book_commitment_mismatch", validate_book(book))

    def test_unsorted_entries_are_rejected(self):
        book = seal_book(ANCHOR, [
            entry("1", "a", "AT_OR_BELOW", 90),
            entry("2", "a", "AT_OR_BELOW", 100),
        ])
        book["entries"].reverse()
        self.assertIn("entries_not_canonically_sorted", validate_book(book))

    def test_source_commitment_is_required(self):
        raw = entry("1", "a", "AT_OR_BELOW", 100)
        raw["source_commitment_sha256"] = ""
        with self.assertRaisesRegex(ValueError, "source_commitment_invalid"):
            seal_book(ANCHOR, [raw])

    def test_all_execution_authorities_are_false(self):
        book = seal_book(ANCHOR, [entry("1", "a", "AT_OR_BELOW", 100)])
        for key in book["authorities"]:
            changed = copy.deepcopy(book)
            changed["authorities"][key] = True
            self.assertIn("authority_forbidden", validate_book(changed))

    def test_invalid_query_price_is_blocked(self):
        idx = LiquidationOrderBook(seal_book(ANCHOR, [entry("1", "a", "AT_OR_BELOW", 100)]))
        with self.assertRaisesRegex(ValueError, "price_rational_invalid"):
            idx.crossed(h("a"), "100.0", "1", "99", "1")


if __name__ == "__main__":
    unittest.main()
