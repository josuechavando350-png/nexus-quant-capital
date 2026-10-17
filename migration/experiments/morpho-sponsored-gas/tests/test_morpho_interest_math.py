import dataclasses
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from morpho_interest_math import MarketState, accrue, taylor_compounded
from morpho_liquidation_math import U128, U256, WAD


class InterestMathTests(unittest.TestCase):
    def setUp(self):
        self.market = MarketState(10000, 10_000_000_000, 8000, 8_000_000_000, 100, 0)

    def test_elapsed_zero(self):
        a = accrue(self.market, 100, 10**12)
        self.assertEqual(a.market, self.market)
        self.assertEqual(a.interest, 0)

    def test_zero_irm_updates_time_only(self):
        self.assertEqual(accrue(self.market, 500, None).market,
                         dataclasses.replace(self.market, last_update=500))

    def test_fee_shares_dilution_exact(self):
        m = dataclasses.replace(self.market, fee=WAD//4)
        a = accrue(m, 101, WAD//10)
        self.assertEqual(a.interest, 841)
        self.assertEqual(a.fee_shares, 210 * (10_000_000_000 + 10**6) // (10841 - 210 + 1))
        self.assertEqual(a.market.total_borrow_assets, 8841)

    def test_historical_rate_terms(self):
        m = MarketState(28439848072772601036, 26262383326729953349623264,
                        25958961383310086496, 23705175968761821157206366, 1791070487, 0)
        self.assertEqual(accrue(m, 1791983495, 3559581937).interest, 84501962012302301)

    def test_reverse_time_or_missing_market_rejected(self):
        for m, t in [(self.market, 99), (dataclasses.replace(self.market, last_update=0), 100)]:
            with self.assertRaises(ValueError): accrue(m, t, 1)

    def test_uint128_market_overflow(self):
        m = dataclasses.replace(self.market, total_supply_assets=U128, total_borrow_assets=U128)
        with self.assertRaises(ValueError): accrue(m, 101, WAD)

    def test_taylor_overflow(self):
        for rate, elapsed in [(U256, 2), (2**128, 1)]:
            with self.assertRaises(ValueError): taylor_compounded(rate, elapsed)

    def test_bad_types_and_fee(self):
        for bad in [True, -1, 1.1, "1"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError): accrue(self.market, 101, bad)
        with self.assertRaises(ValueError): accrue(dataclasses.replace(self.market, fee=WAD), 101, 0)
