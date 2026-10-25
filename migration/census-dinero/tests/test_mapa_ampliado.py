"""Mapa ampliado: Morpho Blue en otras cadenas (configuración, precio del gas que no es ETH y deudas en moneda estable)."""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from census_dinero.__main__ import plan  # noqa: E402
from census_dinero.collect import Collector  # noqa: E402
from census_dinero.config import CHAINS, MORPHO_ONLY_CHAINS, USD_STABLE_SYMBOLS  # noqa: E402
from census_dinero.prices import Prices  # noqa: E402
from census_dinero.web import WebClient, WebError  # noqa: E402

HEX40 = re.compile(r"0x[0-9a-fA-F]{40}")


def no_sleep(_):
    return None


def web(prices, seen=None):
    def getter(url, timeout):
        if "coins.llama.fi" not in url:
            raise WebError("sin red")
        coins = url.split("/")[6].split("?")[0].split(",")
        if seen is not None:
            seen.extend(coins)
        return {"coins": {c: {"price": prices[c]} for c in coins if c in prices}}
    return WebClient(rps=0, getter=getter, sleep=no_sleep, retries=1)


class NoRpc:
    """Las pruebas de precios no deben tocar la red de la cadena."""
    calls = 0

    def eth_call(self, *a, **k):
        raise AssertionError("no se esperaba una llamada a la cadena")


class TestConfig(unittest.TestCase):
    def test_every_new_chain_is_complete_and_unique(self):
        self.assertGreaterEqual(len(MORPHO_ONLY_CHAINS), 30)
        ids = [c.chain_id for c in CHAINS.values()]
        self.assertEqual(len(ids), len(set(ids)))
        for key in MORPHO_ONLY_CHAINS:
            c = CHAINS[key]
            self.assertTrue(HEX40.fullmatch(c.morpho) and HEX40.fullmatch(c.weth), key)
            self.assertNotEqual(int(c.morpho, 16), 0, key)
            self.assertEqual(c.aave, (), key)                                  # solo Morpho Blue
            self.assertTrue(c.public_rpcs and all(u.startswith("https://") for u in c.public_rpcs), key)
            self.assertEqual(c.extra_rpcs_env, f"NQC_CENSUS_RPC_{key.upper()}")
            self.assertFalse(c.builder_market)
        self.assertNotIn("xlayer", CHAINS)                                    # el registro de Morpho lo tiene sin desplegar

    def test_the_original_three_chains_are_untouched(self):
        self.assertEqual(CHAINS["base"].morpho, "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb")
        self.assertEqual(CHAINS["ethereum"].morpho, "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb")
        self.assertEqual(CHAINS["arbitrum"].morpho, "0x6c247b1F6182318877311737BaC0844bAa518F5e")
        self.assertTrue(all(CHAINS[k].native_eth and CHAINS[k].native_usd is None for k in ("ethereum", "base", "arbitrum")))

    def test_known_addresses_from_the_official_registry(self):
        self.assertEqual(CHAINS["polygon"].morpho, "0x1bF0c2541F820E775182832f06c0B7Fc27A25f67")
        self.assertEqual(CHAINS["unichain"].morpho, "0x8f5ae9CddB9f68de460C77730b018Ae7E04a140A")
        self.assertEqual(CHAINS["katana"].morpho, "0xD50F2DffFd62f94Ee4AEd9ca05C61d0753268aBc")
        self.assertEqual(CHAINS["hyperevm"].chain_id, 999)
        self.assertFalse(CHAINS["polygon"].native_eth)                        # el gas de Polygon es POL

    def test_one_job_per_new_chain(self):
        matrix, info = plan({"days": 30, "chains": list(MORPHO_ONLY_CHAINS), "tramos": 1, "end_utc": "2026-10-25T18:00:00Z"})
        self.assertEqual(info["jobs"], len(MORPHO_ONLY_CHAINS))
        self.assertEqual({r["chain"] for r in matrix["include"]}, set(MORPHO_ONLY_CHAINS))


class TestGasPrice(unittest.TestCase):
    def test_a_chain_whose_gas_is_not_eth_never_borrows_the_eth_price(self):
        seen = []
        p = Prices(NoRpc(), CHAINS["polygon"], web({"coingecko:ethereum": 3000.0}, seen))
        self.assertEqual(p.eth_usd(1, 1_790_000_000), (None, "sin_precio"))
        self.assertNotIn("coingecko:ethereum", seen)

    def test_the_wrapped_native_price_is_used_when_there_is_one(self):
        c = CHAINS["polygon"]
        p = Prices(NoRpc(), c, web({f"{c.llama}:{c.weth.lower()}": 0.21}))
        self.assertEqual(p.eth_usd(1, 1_790_000_000), (0.21, "mercado_defillama"))

    def test_eth_chains_still_fall_back_to_eth_and_stable_gas_is_one_dollar(self):
        p = Prices(NoRpc(), CHAINS["unichain"], web({"coingecko:ethereum": 3000.0}))
        self.assertEqual(p.eth_usd(1, 1_790_000_000), (3000.0, "mercado_defillama"))
        p = Prices(NoRpc(), CHAINS["stable"], web({}))
        self.assertEqual(p.eth_usd(1, 1_790_000_000), (1.0, "nativo_estable"))


class TestStableDebt(unittest.TestCase):
    def collector(self, prices):
        return Collector("katana", rpc=NoRpc(), web=web(prices), workers=1)

    def rec(self, symbol):
        return {"protocol": "morpho", "debt": "0x" + "ab" * 20, "debt_symbol": symbol, "debt_decimals": 6, "debt_raw": 1_000 * 10 ** 6,
                "collateral_decimals": 18, "collateral_raw": 10 ** 18, "lif": 1.05, "block": 1}

    def test_a_stable_debt_without_a_market_price_is_valued_at_one_dollar(self):
        col = self.collector({})
        r = self.rec("USDC")
        col.value(r, {"timestamp": 1_790_000_000})
        self.assertAlmostEqual(r["bonus_usd"], 50.0)
        self.assertEqual(r["bonus_source"], "lif_morpho+estable_por_simbolo")
        r = self.rec("vbUSDC")                                                 # no está en la lista: sin precio, sin inventar
        col.value(r, {"timestamp": 1_790_000_000})
        self.assertEqual(r["bonus_source"], "sin_precio")
        self.assertNotIn("bonus_usd", r)

    def test_a_market_price_wins_over_the_symbol(self):
        col = self.collector({"katana:" + "0x" + "ab" * 20: 0.99})
        r = self.rec("USDC")
        col.value(r, {"timestamp": 1_790_000_000})
        self.assertAlmostEqual(r["bonus_usd"], 49.5)
        self.assertEqual(r["bonus_source"], "lif_morpho+mercado_defillama")
        self.assertIn("USDT0", USD_STABLE_SYMBOLS)


if __name__ == "__main__":
    unittest.main()
