"""Matemática exacta, ABI, eventos y multicall de Morpho Blue."""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from census_dinero import morpho as mo  # noqa: E402
from census_dinero.abi import encode_address, norm  # noqa: E402
from census_dinero.collect import morpho_lif  # noqa: E402
from census_dinero.config import MORPHO_LIQUIDATE_TOPIC  # noqa: E402
from census_dinero.keccak import selector, topic  # noqa: E402

WETH = norm("0x4200000000000000000000000000000000000006")
USDC = norm("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
ORACLE, IRM = norm("0x" + "0a" * 20), norm("0x" + "0b" * 20)
ALICE, BOB = norm("0x" + "a1" * 20), norm("0x" + "b2" * 20)
MID = "0x" + "ab" * 32

# Mercado de 1M USDC prestados: cada activo (6 decimales) vale 1e6 shares, así que los
# shares son exactamente 1e6 veces los activos y las cuentas salen redondas.
M = mo.MarketState(10 ** 12, 10 ** 18, 10 ** 12, 10 ** 18, 1_000, 0)
PRICE_2000 = 2000 * 10 ** 24          # 1 WETH (18 dec) = 2000 USDC (6 dec), escala 1e36
LLTV86 = 86 * 10 ** 16


class TestShares(unittest.TestCase):
    def test_rounding_directions(self):
        self.assertEqual(mo.to_shares_down(100, 1000, 1000), 100_000)
        self.assertEqual(mo.to_assets_up(100_000, 1000, 1000), 100)
        self.assertEqual(mo.to_assets_down(1, 1000, 1000), 0)        # 1 share vale < 1 activo: abajo da 0
        self.assertEqual(mo.to_assets_up(1, 1000, 1000), 1)          # arriba da 1
        self.assertEqual(mo.to_shares_up(1, 1000, 1000), 1000)
        # Sin deuda previa los shares virtuales fijan el cambio 1e6:1.
        self.assertEqual(mo.to_shares_down(5, 0, 0), 5 * 10 ** 6)

    def test_round_trip_never_gains(self):
        for assets in (1, 7, 999, 10 ** 9 + 3):
            sh = mo.to_shares_down(assets, 123_456_789, 987_654_321_000)
            self.assertLessEqual(mo.to_assets_down(sh, 123_456_789, 987_654_321_000), assets)


class TestLif(unittest.TestCase):
    def test_matches_formula_and_census_float(self):
        for lltv in (385, 625, 770, 860, 915, 945, 965, 980):
            wad = lltv * 10 ** 15
            exact = mo.lif(wad) / 1e18
            self.assertAlmostEqual(exact, min(1.15, 1 / (1 - 0.3 * (1 - lltv / 1000))), places=12)
            self.assertAlmostEqual(exact, morpho_lif(wad), places=12)     # mismo valor que usó el censo

    def test_cap(self):
        self.assertEqual(mo.lif(50 * 10 ** 16), mo.MAX_LIQUIDATION_INCENTIVE_FACTOR)
        self.assertEqual(mo.lif(86 * 10 ** 16), 1_043_841_336_116_910_229)


class TestHealth(unittest.TestCase):
    collateral = 10 ** 18                                   # 1 WETH = 2000 USDC; 86% -> 1720 USDC

    def shares(self, usdc):
        return usdc * 10 ** 6 * 10 ** 6

    def test_borrowed_and_max_borrow(self):
        self.assertEqual(mo.borrowed_assets(self.shares(1721), M), 1_721_000_000)
        self.assertEqual(mo.max_borrow(self.collateral, PRICE_2000, LLTV86), 1_720_000_000)

    def test_threshold_is_exact(self):
        at_limit = self.shares(1720)
        self.assertTrue(mo.is_healthy(at_limit, self.collateral, PRICE_2000, LLTV86, M))       # == maxBorrow: sana
        self.assertFalse(mo.is_healthy(at_limit + 10 ** 6, self.collateral, PRICE_2000, LLTV86, M))   # +1 unidad
        self.assertTrue(mo.is_healthy(0, 0, PRICE_2000, LLTV86, M))                            # sin deuda: sana

    def test_health_ratio_and_price(self):
        s = self.shares(1721)
        ratio = mo.health_ratio(s, self.collateral, PRICE_2000, LLTV86, M)
        self.assertAlmostEqual(ratio, 1720 / 1721, places=9)
        self.assertIsNone(mo.health_ratio(0, self.collateral, PRICE_2000, LLTV86, M))
        p = mo.liquidation_price(s, self.collateral, LLTV86, M)         # debe dar justo el precio de borde
        self.assertAlmostEqual(p / mo.ORACLE_PRICE_SCALE * 1e12, 1721 / 0.86, places=3)     # USDC por WETH
        self.assertTrue(mo.is_healthy(s, self.collateral, p, LLTV86, M))
        self.assertFalse(mo.is_healthy(s, self.collateral, p - 10 ** 15, LLTV86, M))
        self.assertIsNone(mo.liquidation_price(s, 0, LLTV86, M))


class TestQuote(unittest.TestCase):
    def test_full_liquidation_with_enough_collateral(self):
        s = 1721 * 10 ** 12
        q = mo.full_quote(s, 10 ** 18, PRICE_2000, LLTV86, M)
        self.assertEqual(q["repaid_shares"], s)
        self.assertEqual(q["repaid_assets"], 1_721_000_000)
        f = mo.lif(LLTV86) / 1e18
        self.assertAlmostEqual(q["seized_assets"] / 1e18, 1721 * f / 2000, places=9)
        self.assertAlmostEqual(q["bonus_assets"] / 1e6, 1721 * (f - 1), delta=0.001)      # = repago x (LIF-1)
        self.assertEqual((q["bad_debt_shares"], q["bad_debt_assets"]), (0, 0))

    def test_collateral_short_leaves_bad_debt(self):
        s = 1721 * 10 ** 12
        q = mo.full_quote(s, 5 * 10 ** 17, PRICE_2000, LLTV86, M)          # 0.5 WETH = 1000 USDC de colateral
        self.assertEqual(q["seized_assets"], 5 * 10 ** 17)
        f = mo.lif(LLTV86) / 1e18
        self.assertAlmostEqual(q["repaid_assets"] / 1e6, 1000 / f, delta=0.01)
        self.assertGreater(q["bad_debt_shares"], 0)
        self.assertAlmostEqual((q["repaid_shares"] + q["bad_debt_shares"]) / 1e12, 1721, places=3)
        self.assertAlmostEqual(q["bad_debt_assets"] / 1e6, 1721 - 1000 / f, delta=0.01)

    def test_parity_helpers_agree_with_full_quote(self):
        s = 1721 * 10 ** 12
        q = mo.full_quote(s, 10 ** 18, PRICE_2000, LLTV86, M)
        seized, repaid = mo.predict_from_repaid_shares(s, PRICE_2000, LLTV86, M)
        self.assertEqual((seized, repaid), (q["seized_assets"], q["repaid_assets"]))
        shares, repaid2 = mo.predict_from_seized_assets(q["seized_assets"], PRICE_2000, LLTV86, M)
        self.assertLessEqual(abs(shares - s), 2 * 10 ** 6)               # ida y vuelta: a lo más unas unidades de activo
        self.assertLessEqual(abs(repaid2 - q["repaid_assets"]), 2)


class TestAccrue(unittest.TestCase):
    def test_ten_percent_apr_one_day(self):
        rate = int(0.10 / 31_536_000 * 1e18)
        m = mo.accrue(M, rate, M.last_update + 86_400)
        grown = m.total_borrow_assets / M.total_borrow_assets
        self.assertAlmostEqual(grown, math.exp(0.10 * 86_400 / 31_536_000), places=9)
        self.assertEqual(m.total_supply_assets - M.total_supply_assets, m.total_borrow_assets - M.total_borrow_assets)
        self.assertEqual(m.total_borrow_shares, M.total_borrow_shares)        # los shares no cambian
        self.assertEqual(m.last_update, M.last_update + 86_400)

    def test_noop_cases(self):
        self.assertIs(mo.accrue(M, 0, M.last_update + 100), M)
        self.assertIs(mo.accrue(M, 10 ** 9, M.last_update), M)
        self.assertIs(mo.accrue(M, 10 ** 9, M.last_update - 5), M)

    def test_interest_can_flip_health(self):
        shares = 1_719_999_999 * 10 ** 6                                     # 1719.999999 USDC de deuda
        coll = 10 ** 18
        self.assertTrue(mo.is_healthy(shares, coll, PRICE_2000, LLTV86, M))
        aged = mo.accrue(M, int(0.2 / 31_536_000 * 1e18), M.last_update + 3_600)
        self.assertFalse(mo.is_healthy(shares, coll, PRICE_2000, LLTV86, aged))


class TestAbi(unittest.TestCase):
    def test_known_selectors(self):
        self.assertEqual(mo.SEL_MARKET, "0x5c60e39a")
        self.assertEqual(mo.SEL_POSITION, "0x93c52062")
        self.assertEqual(mo.SEL_PRICE, "0xa035b1fe")
        self.assertEqual(mo.SEL_AGGREGATE3, "0x82ad56cb")
        self.assertEqual(mo.SEL_BLOCK_NUMBER, "0x42cbb15c")
        self.assertEqual(mo.SEL_PARAMS, "0x2c3c9157")

    def test_event_topics_match_signatures(self):
        for name, sig in mo.EVENT_SIGNATURES.items():
            self.assertEqual(mo.EVENT_TOPICS[name], topic(sig))
        self.assertEqual(mo.EVENT_TOPICS["Liquidate"], MORPHO_LIQUIDATE_TOPIC)
        self.assertEqual(len(set(mo.EVENT_TOPICS.values())), 5)

    def test_call_encoders(self):
        self.assertEqual(mo.call_market(MID), "0x5c60e39a" + "ab" * 32)
        self.assertEqual(mo.call_position(MID, ALICE), "0x93c52062" + "ab" * 32 + "0" * 24 + "a1" * 20)
        c = mo.call_rate(mo.Params(USDC, WETH, ORACLE, IRM, LLTV86), M)
        self.assertEqual(len(c), 2 + 8 + 11 * 64)
        self.assertEqual(c[:10], mo.SEL_RATE)

    def test_decoders(self):
        w = lambda *xs: "".join(format(x, "064x") for x in xs)           # noqa: E731
        m = mo.decode_market("0x" + w(1, 2, 3, 4, 5, 6))
        self.assertEqual((m.total_supply_assets, m.total_borrow_shares, m.last_update, m.fee), (1, 4, 5, 6))
        self.assertEqual(mo.decode_position("0x" + w(7, 8, 9)), (7, 8, 9))
        p = mo.decode_params("0x" + w(int(USDC, 16), int(WETH, 16), int(ORACLE, 16), int(IRM, 16), LLTV86))
        self.assertEqual((p.loan, p.collateral, p.lltv), (USDC, WETH, LLTV86))
        self.assertEqual(mo.decode_uint("0x" + w(42)), 42)
        for bad in (mo.decode_market, mo.decode_position, mo.decode_params):
            with self.assertRaises(ValueError):
                bad("0x" + w(1))


class TestMulticall(unittest.TestCase):
    @staticmethod
    def encode_results(results):
        """Codificador independiente de Result[] (solo para probar el decodificador)."""
        def word(n):
            return n.to_bytes(32, "big")
        tuples = []
        for ok, data in results:
            tuples.append(word(1 if ok else 0) + word(0x40) + word(len(data)) + data + b"\0" * ((-len(data)) % 32))
        head, off = b"", len(tuples) * 32
        for t in tuples:
            head += word(off)
            off += len(t)
        return "0x" + (word(0x20) + word(len(tuples)) + head + b"".join(tuples)).hex()

    def test_encode_layout_by_hand(self):
        data = mo.call_market(MID)                                # 36 bytes: se rellena a 64
        enc = mo.encode_aggregate3([(mo.MULTICALL3, True, data)])
        body = bytes.fromhex(enc[10:])
        self.assertEqual(enc[:10], "0x82ad56cb")
        self.assertEqual(int.from_bytes(body[0:32], "big"), 0x20)          # offset del arreglo
        self.assertEqual(int.from_bytes(body[32:64], "big"), 1)            # largo
        self.assertEqual(int.from_bytes(body[64:96], "big"), 32)           # offset de la tupla 0 (1 * 32)
        t = body[96:]
        self.assertEqual(t[:32], bytes.fromhex("0" * 24 + mo.MULTICALL3[2:]))
        self.assertEqual(int.from_bytes(t[32:64], "big"), 1)               # allowFailure
        self.assertEqual(int.from_bytes(t[64:96], "big"), 0x60)            # offset de callData en la tupla
        self.assertEqual(int.from_bytes(t[96:128], "big"), 36)             # largo de callData
        self.assertEqual(t[128:164], bytes.fromhex(data[2:]))
        self.assertEqual(len(t), 128 + 64)                                 # 36 bytes rellenados a 64

    def test_two_calls_have_correct_offsets(self):
        a, b = mo.call_market(MID), mo.SEL_PRICE
        body = bytes.fromhex(mo.encode_aggregate3([(MULTICALL3_ADDR, False, a), (ORACLE, True, b)])[10:])
        self.assertEqual(int.from_bytes(body[32:64], "big"), 2)
        off0, off1 = int.from_bytes(body[64:96], "big"), int.from_bytes(body[96:128], "big")
        self.assertEqual(off0, 64)                                         # 2 offsets de 32
        self.assertEqual(off1, 64 + 192)                                   # tupla 0 = 3*32 + 32 + 64 = 192
        t1 = 64 + off1
        self.assertEqual(int.from_bytes(body[t1 + 96:t1 + 128], "big"), 4)  # callData de price(): 4 bytes
        self.assertEqual(body[t1 + 128:t1 + 132], bytes.fromhex("a035b1fe"))

    def test_decode_round_trip(self):
        results = [(True, (123).to_bytes(32, "big")), (False, b"\x08\xc3\x79\xa0" + b"\0" * 60), (True, b"")]
        self.assertEqual(mo.decode_aggregate3(self.encode_results(results)), results)
        self.assertEqual(mo.decode_aggregate3(self.encode_results([])), [])

    def test_decode_truncated_fails(self):
        enc = self.encode_results([(True, b"\x01" * 64)])
        with self.assertRaises(ValueError):
            mo.decode_aggregate3(enc[:-80])


MULTICALL3_ADDR = mo.MULTICALL3


def log(sig, topics, words, block=100, idx=3, tx="0x" + "11" * 32, tx_index=2):
    return {"address": "0x" + "bb" * 20, "topics": [topic(sig)] + topics,
            "data": "0x" + "".join(format(x, "064x") for x in words), "blockNumber": hex(block),
            "logIndex": hex(idx), "transactionHash": tx, "transactionIndex": hex(tx_index)}


def t(addr):
    return "0x" + encode_address(addr)


class TestEvents(unittest.TestCase):
    def test_borrow(self):
        ev = mo.decode_event(log(mo.EVENT_SIGNATURES["Borrow"], [MID, t(ALICE), t(BOB)], [int(WETH, 16), 500, 5000]))
        self.assertEqual((ev["kind"], ev["user"], ev["receiver"], ev["caller"]), ("Borrow", ALICE, BOB, WETH))
        self.assertEqual((ev["d_shares"], ev["d_collateral"], ev["assets"]), (5000, 0, 500))
        self.assertEqual((ev["block"], ev["log_index"], ev["tx_index"], ev["market"]), (100, 3, 2, MID))

    def test_repay_supply_withdraw(self):
        r = mo.decode_event(log(mo.EVENT_SIGNATURES["Repay"], [MID, t(BOB), t(ALICE)], [10, 7]))
        self.assertEqual((r["user"], r["caller"], r["d_shares"]), (ALICE, BOB, -7))
        s = mo.decode_event(log(mo.EVENT_SIGNATURES["SupplyCollateral"], [MID, t(BOB), t(ALICE)], [900]))
        self.assertEqual((s["user"], s["d_collateral"], s["d_shares"]), (ALICE, 900, 0))
        w = mo.decode_event(log(mo.EVENT_SIGNATURES["WithdrawCollateral"], [MID, t(ALICE), t(BOB)], [int(BOB, 16), 400]))
        self.assertEqual((w["user"], w["caller"], w["d_collateral"]), (ALICE, BOB, -400))

    def test_liquidate_includes_bad_debt_shares(self):
        ev = mo.decode_event(log(mo.EVENT_SIGNATURES["Liquidate"], [MID, t(BOB), t(ALICE)], [111, 222, 333, 44, 55]))
        self.assertEqual((ev["user"], ev["caller"], ev["borrower"]), (ALICE, BOB, ALICE))
        self.assertEqual((ev["repaid_assets"], ev["repaid_shares"], ev["seized_assets"]), (111, 222, 333))
        self.assertEqual((ev["d_shares"], ev["d_collateral"]), (-(222 + 55), -333))

    def test_unknown_and_malformed(self):
        other = log("Supply(bytes32,address,address,uint256,uint256)", [MID, t(BOB), t(ALICE)], [1, 2])
        self.assertIsNone(mo.decode_event(other))
        bad = log(mo.EVENT_SIGNATURES["Borrow"], [MID, t(ALICE), t(BOB)], [1, 2])
        with self.assertRaises(ValueError):
            mo.decode_event(bad)


class TestSelectorHelper(unittest.TestCase):
    def test_same_selector_function_as_census(self):
        self.assertEqual(selector("price()"), mo.SEL_PRICE)


if __name__ == "__main__":
    unittest.main()
