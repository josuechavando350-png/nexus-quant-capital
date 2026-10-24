"""Pruebas de tramos, enrutamiento por capacidad, sonda, secretos, plazos y segunda pasada."""

import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from census_dinero import analyze as an  # noqa: E402
from census_dinero.__main__ import parse_utc, plan  # noqa: E402
from census_dinero.collect import Collector  # noqa: E402
from census_dinero.rpc import RangeTooLarge, Rpc, RpcError, hinted_limit  # noqa: E402
from census_dinero.web import WebClient  # noqa: E402
import fakechain as fc  # noqa: E402
from test_census import llama_getter, make_collector, no_sleep  # noqa: E402


def error(payload, message, code=-32000):
    return {"jsonrpc": "2.0", "id": payload["id"], "error": {"code": code, "message": message}}


class TestPlan(unittest.TestCase):
    def test_partition_is_contiguous(self):
        cfg = {"days": 30, "end_utc": "2026-10-24T00:00:00Z", "chains": ["ethereum", "base"],
               "tramos": {"ethereum": 4, "base": 7}}
        matrix, info = plan(cfg)
        end = parse_utc("2026-10-24T00:00:00Z")
        self.assertEqual(info["end_ts"], end)
        self.assertEqual(info["start_ts"], end - 30 * 86400)
        for chain, n in (("ethereum", 4), ("base", 7)):
            rows = [r for r in matrix["include"] if r["chain"] == chain]
            self.assertEqual(len(rows), n)
            self.assertEqual(rows[0]["start_ts"], info["start_ts"])
            self.assertEqual(rows[-1]["end_ts"], end)
            for a, b in zip(rows, rows[1:]):
                self.assertEqual(a["end_ts"], b["start_ts"])
        self.assertEqual(len({r["label"] for r in matrix["include"]}), 11)

    def test_default_end_is_closed_hour(self):
        matrix, info = plan({"days": 1, "chains": ["arbitrum"]}, now=1_800_000_123)
        self.assertEqual(info["end_ts"] % 3600, 0)
        self.assertLess(info["end_ts"], 1_800_000_123 - 3600 + 1)
        self.assertEqual(len(matrix["include"]), 1)


class TestWindowPartition(unittest.TestCase):
    def test_adjacent_tranches_share_no_block(self):
        chain = fc.FakeChain()
        a, _ = make_collector(chain=chain)
        b, _ = make_collector(chain=chain)
        mid = fc.T0 + 12 * 19_000 + 5            # entre bloques
        wa = a.resolve_window(start_ts=mid - 86400, end_ts=mid)
        wb = b.resolve_window(start_ts=mid, end_ts=mid + 3600)
        self.assertEqual(wa["end_block"] + 1, wb["start_block"])
        self.assertLess(fc.T0 + 12 * wa["end_block"], mid)
        self.assertGreaterEqual(fc.T0 + 12 * wb["start_block"], mid)
        self.assertAlmostEqual(wa["days"], 1.0)

    def test_end_after_head_is_refused(self):
        col, chain = make_collector()
        with self.assertRaises(RpcError):
            col.resolve_window(start_ts=fc.T0, end_ts=fc.T0 + 12 * chain.head + 10_000)


class TestRouting(unittest.TestCase):
    def test_hinted_limit(self):
        self.assertEqual(hinted_limit("exceed maximum block range: 50000", 100_000), 50_000)
        self.assertEqual(hinted_limit("ranges over 10,000 blocks are not supported", 50_000), 10_000)
        self.assertEqual(hinted_limit("block range too large", 8_000), 4_000)

    def test_log_limit_per_provider(self):
        big, small = fc.FakeChain(), fc.FakeChain()
        calls = {"chico": [], "grande": []}

        def transport(url, payload, timeout):
            if payload["method"] == "eth_getLogs":
                f = payload["params"][0]
                span = int(f["toBlock"], 16) - int(f["fromBlock"], 16) + 1
                if "chico" in url:
                    calls["chico"].append(span)
                    if span > 1000:
                        return error(payload, "max block range is 1000 blocks")
                else:
                    calls["grande"].append(span)
                    if span > 5000:
                        return error(payload, "query exceeds max block range 5000")
            return (small if "chico" in url else big)(url, payload, timeout)
        rpc = Rpc(["https://chico", "https://grande"], transport=transport, sleep=no_sleep, rps=0)
        logs = rpc.get_logs(None, [None], 1, 20_100)
        self.assertEqual(len(logs), len(big.logs))
        self.assertEqual(rpc.log_limit["https://chico"], 1000)
        self.assertEqual(rpc.log_limit["https://grande"], 5000)
        # Aprendido el límite, ya no se le piden rangos que rechaza.
        self.assertLessEqual(max(calls["grande"][-3:]), 5000)

    def test_range_too_large_when_no_provider_fits(self):
        rpc = Rpc(["https://a"], transport=fc.FakeChain(), sleep=no_sleep, rps=0)
        rpc.log_limit["https://a"] = 100
        with self.assertRaises(RangeTooLarge) as cm:
            rpc.call("eth_getLogs", [{"fromBlock": hex(1), "toBlock": hex(500), "topics": [None]}])
        self.assertEqual(cm.exception.limit, 100)

    def test_useless_provider_dropped_for_method_only(self):
        chain = fc.FakeChain()
        hits = {"sin": 0}

        def transport(url, payload, timeout):
            if "sin" in url and payload["method"] == "debug_traceTransaction":
                hits["sin"] += 1
                return error(payload, "missing trie node abc")
            return chain(url, payload, timeout)
        rpc = Rpc(["https://sin", "https://con"], transport=transport, sleep=no_sleep, rps=0)
        for _ in range(6):
            rpc.call("debug_traceTransaction", [fc.th(0xA), {"tracer": "callTracer"}])
        self.assertLessEqual(hits["sin"], 3)                  # el que traza pasa al frente
        rpc.seed("https://sin", "debug_traceTransaction", err=3)
        self.assertNotIn("https://sin", rpc.usable("debug_traceTransaction"))
        self.assertEqual(rpc.block_number(), chain.head)       # pero sigue sirviendo lo demás
        self.assertIn("https://sin", rpc.usable("eth_blockNumber"))


class TestSecrets(unittest.TestCase):
    def test_secret_urls_never_in_outputs(self):
        chain = fc.FakeChain()
        secret = "https://eth-mainnet.g.alchemy.com/v2/LLAVE-SECRETA-123"

        def transport(url, payload, timeout):
            if url == secret and payload["method"] == "eth_blockNumber":
                raise RpcError(f"HTTP 500 en {url}", code=500)
            return chain(url, payload, timeout)
        rpc = Rpc([secret, "https://publico"], transport=transport, sleep=no_sleep, rps=0,
                  public={"https://publico"})
        rpc.block_number()
        dump = json.dumps(rpc.report())
        self.assertNotIn("LLAVE", dump)
        self.assertIn("secreto1 (alchemy.com)", dump)
        self.assertIn("https://publico", dump)

    def test_collector_meta_has_no_secret(self):
        chain = fc.FakeChain()
        secret = "https://rpc.example.org/key/ABCDEF0123"
        os.environ["NQC_CENSUS_RPC_ETHEREUM"] = secret
        try:
            col = Collector("ethereum", web=WebClient(rps=0, getter=llama_getter, sleep=no_sleep, retries=1),
                            workers=2)
            col.rpc = Rpc(col.rpc.urls[:1], transport=chain, sleep=no_sleep, rps=0, expected_chain_id=1,
                          public=set())
            col.prices.rpc = col.rpc
            tmp = tempfile.mkdtemp()
            col.run(1, tmp)
            for name in ("meta.json", "liquidaciones.jsonl"):
                with open(os.path.join(tmp, name)) as fh:
                    self.assertNotIn("ABCDEF0123", fh.read(), name)
        finally:
            del os.environ["NQC_CENSUS_RPC_ETHEREUM"]


class TestSonda(unittest.TestCase):
    def test_probe_routes_traces_and_archive(self):
        full, pruned = fc.FakeChain(), fc.FakeChain(archive=False, traces=False)

        def transport(url, payload, timeout):
            return (pruned if "podado" in url else full)(url, payload, timeout)
        rpc = Rpc(["https://podado", "https://archivo"], transport=transport, sleep=no_sleep, rps=0,
                  expected_chain_id=1)
        web = WebClient(rps=0, getter=llama_getter, sleep=no_sleep, retries=1)
        col = Collector("ethereum", rpc=rpc, web=web, workers=2)
        tmp = tempfile.mkdtemp()
        meta = col.run(1, tmp)
        sonda = {s["proveedor"]: s for s in meta["sonda"]}
        self.assertFalse(sonda["https://podado"]["archivo"])
        self.assertTrue(sonda["https://archivo"]["archivo"])
        self.assertEqual(sonda["https://archivo"]["debug_traceTransaction_vieja"]["ok"], 2)
        self.assertTrue(rpc.no_method.get(("https://podado", "debug_traceTransaction")))
        self.assertEqual(meta["native_trace_sources"], {"debug_traceTransaction": 4})
        with open(os.path.join(tmp, "liquidaciones.jsonl")) as fh:
            recs = [json.loads(x) for x in fh]
        a = next(r for r in recs if r["tx_hash"] == fc.th(0xA))
        self.assertEqual(a["bonus_source"], "oraculo@bloque")


class TestBudgetAndRetry(unittest.TestCase):
    def test_budget_exhausted_keeps_partial_coverage(self):
        col, _ = make_collector()
        col.deadline = time.monotonic() - 1
        tmp = tempfile.mkdtemp()
        meta = col.run(1, tmp)
        self.assertFalse(meta["events_complete"])
        self.assertTrue(os.path.exists(os.path.join(tmp, "liquidaciones.jsonl")))

    def test_oracle_gap_is_not_a_last_update(self):
        col, _ = make_collector()
        a = fc.AGG_ETH
        col.updates = {a: [(100, 0, "0x1")]}
        col.oracle_cover = {a: 150}
        key = ("morpho", "0xoraculo")
        rec = {"block": 200, "log_index": 0, "_feeds": key}
        self.assertEqual(col.last_update(rec, {key: {a}}), "sin_cobertura")
        rec["block"] = 140
        self.assertEqual(col.last_update(rec, {key: {a}})[0], 100)

    def test_second_pass_recovers_flaky_traces(self):
        chain = fc.FakeChain()
        state = {"a": 0}

        def transport(url, payload, timeout):
            if payload["method"] == "debug_traceTransaction" and payload["params"][0] == fc.th(0xA):
                state["a"] += 1
                if state["a"] <= 4:
                    return error(payload, "historical state not available")
            return chain(url, payload, timeout)
        rpc = Rpc(["https://mixto"], transport=transport, sleep=no_sleep, rps=0, expected_chain_id=1)
        web = WebClient(rps=0, getter=llama_getter, sleep=no_sleep, retries=1)
        col = Collector("ethereum", rpc=rpc, web=web, workers=1)
        col.probe = lambda win: None                   # sin sonda: que la primera pasada falle
        tmp = tempfile.mkdtemp()
        meta = col.run(1, tmp)
        self.assertEqual(meta["second_pass"]["intentadas"], 1)
        self.assertEqual(meta["second_pass"]["recuperadas"], 1)
        with open(os.path.join(tmp, "liquidaciones.jsonl")) as fh:
            recs = [json.loads(x) for x in fh]
        a = next(r for r in recs if r["tx_hash"] == fc.th(0xA))
        self.assertEqual(a["native_source"], "debug_traceTransaction")
        self.assertTrue(a["realized_complete"])


class TestAnalyzeTranches(unittest.TestCase):
    def _tranche(self, recs, meta):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "liquidaciones.jsonl"), "w") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")
        with open(os.path.join(d, "meta.json"), "w") as fh:
            json.dump(meta, fh)
        return os.path.join(d, "liquidaciones.jsonl")

    def rec(self, tx, **kw):
        r = {"chain": "base", "protocol": "aave", "market": "aave-v3-base", "collateral": "0xc", "debt": "0xd",
             "block": 10, "log_index": 0, "tx_hash": tx, "liquidator": "0xbot", "tx_from": "0xe", "tx_to": "0xbot",
             "bonus_usd": 100.0, "realized_usd": 80.0, "realized_complete": True, "third_party_usd": 0.0,
             "gas_usd": 1.0, "priority_eth": 0.0, "direct_eth": 0.0, "eth_usd": 3000.0, "timestamp": 1}
        r.update(kw)
        return r

    def test_merge_dedupe_and_routes(self):
        m = {"chain": "base", "events": 2, "window": {"days": 3.0}, "events_complete": True}
        p1 = self._tranche([self.rec("0x1"), self.rec("0x2", third_party_usd=95.0, realized_usd=2.0,
                                                       liquidator="0xatlas")], m)
        p2 = self._tranche([self.rec("0x2", third_party_usd=95.0, realized_usd=2.0, liquidator="0xatlas"),
                            self.rec("0x3", realized_complete=False)], dict(m, events=2))
        recs, metas = an.load([p1, p2])
        self.assertEqual(len(recs), 3)
        res = an.analyze(recs, metas, expected={"chains": ["base", "arbitrum"], "tramos": {"base": 3, "arbitrum": 2}})
        routes = {r["tx_hash"]: r["route"] for r in recs}
        self.assertEqual(routes, {"0x1": "directa", "0x2": "subasta", "0x3": "sin_medir"})
        cov = {c["chain"]: c for c in res["coverage"]}
        self.assertEqual((cov["base"]["tramos"], cov["base"]["tramos_esperados"], cov["base"]["days"]), (2, 3, 6.0))
        self.assertEqual(cov["arbitrum"]["tramos"], 0)
        self.assertEqual([b["liquidator"] for b in res["bots_direct"]], ["0xbot"])
        flow = res["overall"]["flow"]
        self.assertAlmostEqual(flow["oev"], 95.0)
        self.assertAlmostEqual(flow["kept"], 82.0)
        md = an.render_md(res, "2026-10-24")
        self.assertIn("Cobertura incompleta", md)
        self.assertIn("Bots que ganan por fuera de subastas", md)


if __name__ == "__main__":
    unittest.main()
