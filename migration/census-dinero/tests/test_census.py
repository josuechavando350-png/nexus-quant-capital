import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from census_dinero import analyze as an  # noqa: E402
from census_dinero.abi import decode_string, words  # noqa: E402
from census_dinero.collect import (Collector, blockscout_value_to, call_frames_value_to, decode_aave,  # noqa: E402
                                   decode_morpho, morpho_lif, parity_traces_value_to)
from census_dinero.config import SELECTOR_SIGNATURES, SEL, SIGNATURES  # noqa: E402
from census_dinero.keccak import keccak256, selector, topic  # noqa: E402
from census_dinero.rpc import Rpc, RpcError  # noqa: E402
from census_dinero.web import WebClient, WebError  # noqa: E402
import fakechain as fc  # noqa: E402


def no_sleep(_):
    return None


def make_collector(chain=None, web_getter=None, **kw):
    chain = chain or fc.FakeChain(**kw)
    rpc = Rpc(["https://fake"], transport=chain, sleep=no_sleep, rps=0, expected_chain_id=1, log_chunk=50_000)
    web = WebClient(rps=0, getter=web_getter or (lambda url, t: (_ for _ in ()).throw(WebError("sin red"))),
                    sleep=no_sleep, retries=1)
    return Collector("ethereum", rpc=rpc, web=web, workers=2), chain


class TestConstants(unittest.TestCase):
    def test_keccak_vectors(self):
        self.assertEqual(keccak256(b"").hex(), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(keccak256(b"a" * 200).hex(), keccak256(b"a" * 200).hex())

    def test_topics_and_selectors_match_signatures(self):
        for t, sig in SIGNATURES.items():
            self.assertEqual(topic(sig), t, sig)
        for name, sig in SELECTOR_SIGNATURES.items():
            self.assertEqual(selector(sig), SEL[name], sig)

    def test_morpho_lif(self):
        self.assertAlmostEqual(morpho_lif(86 * 10 ** 16), 1 / (1 - 0.3 * 0.14), places=12)
        self.assertAlmostEqual(morpho_lif(915 * 10 ** 15), 1 / (1 - 0.3 * 0.085), places=12)
        self.assertEqual(morpho_lif(50 * 10 ** 16), 1.15)

    def test_decode_string_variants(self):
        self.assertEqual(decode_string("0x" + "4d4b52".ljust(64, "0")), "MKR")
        s = "USDC".encode().hex()
        self.assertEqual(decode_string("0x" + fc.w(32) + fc.w(4) + s.ljust(64, "0")), "USDC")


class TestDecoders(unittest.TestCase):
    def setUp(self):
        self.chain = fc.FakeChain()

    def test_aave(self):
        lg = next(lg for lg in self.chain.logs if lg["address"] == fc.AAVE_POOL)
        r = decode_aave(lg, "ethereum", "aave-v3-core")
        self.assertEqual((r["collateral"], r["debt"], r["liquidator"]), (fc.WETH, fc.USDC, fc.BOT_A))
        self.assertEqual(r["debt_raw"], 1000 * 10 ** 6)
        self.assertEqual(r["collateral_raw"], 35 * 10 ** 16)
        self.assertFalse(r["receive_atoken"])

    def test_morpho(self):
        lg = next(lg for lg in self.chain.logs if lg["address"] == fc.MORPHO)
        r = decode_morpho(lg, "ethereum")
        self.assertEqual(r["market"], fc.MARKET_ID)
        self.assertEqual(r["liquidator"], fc.BOT_B)
        self.assertEqual(r["debt_raw"], 10_000 * 10 ** 6)
        self.assertEqual(r["collateral_raw"], 4 * 10 ** 18)

    def test_rejects_wrong_event(self):
        lg = dict(next(lg for lg in self.chain.logs if lg["address"] == fc.MORPHO))
        with self.assertRaises(ValueError):
            decode_aave(lg, "ethereum", "x")


class TestBuilderPayments(unittest.TestCase):
    def test_call_tracer_ignores_reverted_and_delegatecall(self):
        frame = fc.FakeChain().traces_by_tx[fc.th(0xA)]
        self.assertEqual(call_frames_value_to(frame, fc.BUILDER), 5 * 10 ** 15)

    def test_parity_traces(self):
        traces = [
            {"type": "call", "action": {"callType": "call", "to": fc.BUILDER, "value": hex(7)}},
            {"type": "call", "action": {"callType": "delegatecall", "to": fc.BUILDER, "value": hex(100)}},
            {"type": "call", "action": {"callType": "call", "to": fc.BUILDER, "value": hex(100)}, "error": "Reverted"},
        ]
        self.assertEqual(parity_traces_value_to(traces, fc.BUILDER), 7)

    def test_blockscout(self):
        items = [
            {"type": "call", "to": {"hash": fc.BUILDER.upper().replace("0X", "0x")}, "value": "9", "success": True},
            {"type": "delegatecall", "to": {"hash": fc.BUILDER}, "value": "100", "success": True},
            {"type": "call", "to": {"hash": fc.BUILDER}, "value": "100", "success": False},
        ]
        self.assertEqual(blockscout_value_to(items, fc.BUILDER), 9)


class TestRpc(unittest.TestCase):
    def test_refuses_write_methods(self):
        rpc = Rpc(["https://fake"], transport=fc.FakeChain(), sleep=no_sleep, rps=0)
        for m in ("eth_sendRawTransaction", "eth_sendTransaction", "eth_sign", "personal_sign"):
            with self.assertRaises(ValueError):
                rpc.call(m, [])

    def test_adaptive_get_logs_splits_range(self):
        chain = fc.FakeChain(log_range_limit=700)
        rpc = Rpc(["https://fake"], transport=chain, sleep=no_sleep, rps=0, log_chunk=50_000)
        logs = rpc.get_logs(None, [None], 1, 20_100)
        self.assertEqual(len(logs), len(chain.logs))

    def test_falls_back_to_second_provider(self):
        chain = fc.FakeChain()

        def transport(url, payload, timeout):
            if "mala" in url:
                raise RpcError("HTTP 503 en mala", code=503)
            return chain(url, payload, timeout)
        rpc = Rpc(["https://mala", "https://buena"], transport=transport, sleep=no_sleep, rps=0, retries=2)
        self.assertEqual(rpc.block_number(), chain.head)


class TestEndToEnd(unittest.TestCase):
    def run_collect(self, **kw):
        col, chain = make_collector(**kw)
        tmp = tempfile.mkdtemp()
        meta = col.run(1, tmp)
        with open(os.path.join(tmp, "liquidaciones.jsonl")) as fh:
            recs = [json.loads(x) for x in fh]
        return recs, meta, tmp, chain

    def test_full_pipeline_values(self):
        recs, meta, tmp, _ = self.run_collect()
        self.assertEqual(meta["events"], 4)
        self.assertEqual(meta["enriched"], 4)
        a = next(r for r in recs if r["tx_hash"] == fc.th(0xA))
        self.assertAlmostEqual(a["bonus_usd"], 50.0, places=6)
        self.assertEqual(a["bonus_source"], "oraculo@bloque")
        self.assertAlmostEqual(a["gas_usd"], 10.8, places=6)
        self.assertAlmostEqual(a["builder_usd"], 1.8 + 15.0, places=6)
        self.assertAlmostEqual(a["net_usd"], 50 - 10.8 - 15.0, places=6)
        self.assertAlmostEqual(a["builder_share"], 16.8 / 50, places=6)
        self.assertEqual(a["blocks_since_oracle"], 0)
        self.assertFalse(a["same_tx_as_oracle"])
        self.assertEqual(a["direct_source"], "debug_traceTransaction")

        b = next(r for r in recs if r["tx_hash"] == fc.th(0xB))
        lif = 1 / (1 - 0.3 * 0.14)
        self.assertAlmostEqual(b["bonus_usd"], 10_000 * (lif - 1), places=4)
        self.assertEqual(b["collateral_symbol"], "wstETH")
        self.assertEqual(b["debt_symbol"], "USDC")
        self.assertEqual(b["blocks_since_oracle"], 5)
        self.assertAlmostEqual(b["builder_usd"], 0.0, places=9)

        cs = sorted((r for r in recs if r["tx_hash"] == fc.th(0xC)), key=lambda r: r["log_index"])
        self.assertEqual([r["liqs_in_tx"] for r in cs], [2, 2])
        self.assertAlmostEqual(cs[0]["bonus_usd"], 15.0, places=3)
        self.assertAlmostEqual(cs[1]["bonus_usd"], 5.0, places=3)
        self.assertAlmostEqual(cs[0]["gas_usd"] + cs[1]["gas_usd"], 16.5, places=6)
        self.assertAlmostEqual(cs[0]["gas_usd"] / cs[1]["gas_usd"], 3.0, places=2)
        self.assertEqual(cs[0]["blocks_since_oracle"], 1)   # wstETH vía adaptador CAPO -> feed ETH

    def test_archive_missing_falls_back_to_market_price(self):
        def getter(url, timeout):
            coins = url.split("/")[6].split("?")[0].split(",")
            table = {f"ethereum:{fc.WETH}": 3000, f"ethereum:{fc.USDC}": 1.0, f"ethereum:{fc.WSTETH}": 3500}
            return {"coins": {c: {"price": table[c]} for c in coins if c in table}}
        col, chain = make_collector(web_getter=getter, archive=False)
        tmp = tempfile.mkdtemp()
        col.run(1, tmp)
        with open(os.path.join(tmp, "liquidaciones.jsonl")) as fh:
            recs = [json.loads(x) for x in fh]
        a = next(r for r in recs if r["tx_hash"] == fc.th(0xA))
        self.assertEqual(a["bonus_source"], "mercado_defillama")
        self.assertAlmostEqual(a["bonus_usd"], 50.0, places=6)

    def test_unmeasured_direct_payment_is_marked(self):
        recs, meta, tmp, _ = self.run_collect(traces=False)
        a = next(r for r in recs if r["tx_hash"] == fc.th(0xA))
        self.assertIsNone(a["direct_eth"])
        self.assertFalse(a["builder_payment_complete"])
        self.assertEqual(a["direct_source"], "no_medido")

    def test_wrong_chain_is_rejected(self):
        col, _ = make_collector(chain=fc.FakeChain(chain_id=8453))
        with self.assertRaises(RpcError):
            col.run(1, tempfile.mkdtemp())

    def test_analyze_and_report(self):
        recs, meta, tmp, _ = self.run_collect()
        loaded, metas = an.load([os.path.join(tmp, "liquidaciones.jsonl")])
        res = an.analyze(loaded, metas)
        out = tempfile.mkdtemp()
        md = an.write_outputs(res, loaded, out, "2026-10-24")
        self.assertIn("Census del dinero", md)
        self.assertEqual(res["overall"]["liquidations"], 4)
        self.assertAlmostEqual(res["overall"]["bonus_usd"], 50 + 10_000 * (1 / (1 - 0.3 * 0.14) - 1) + 20, places=2)
        for f in ("RESUMEN.md", "mercados.csv", "liquidaciones.csv", "resumen.json"):
            self.assertTrue(os.path.exists(os.path.join(out, f)), f)


class TestClassify(unittest.TestCase):
    base = {"liquidations": 10, "winners": 1, "builder_share_median": 0.05, "blocks_median": 30, "net_median": 50}

    def test_states(self):
        self.assertEqual(an.classify(dict(self.base)), "virgen")
        self.assertEqual(an.classify(dict(self.base, liquidations=2)), "muestra_insuficiente")
        self.assertEqual(an.classify(dict(self.base, winners=6, builder_share_median=0.9)), "muerta")
        self.assertEqual(an.classify(dict(self.base, winners=6, builder_share_median=0.3, net_median=-1)), "muerta")
        self.assertEqual(an.classify(dict(self.base, winners=3, builder_share_median=0.4)), "disputada")
        self.assertEqual(an.classify(dict(self.base, blocks_median=0)), "disputada")


if __name__ == "__main__":
    unittest.main()
