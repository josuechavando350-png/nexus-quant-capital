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

    def test_punished_provider_does_not_drive_chunk_size(self):
        chain = fc.FakeChain()
        calls = {"grande": 0}

        def transport(url, payload, timeout):
            if "grande" in url and payload["method"] == "eth_getLogs":
                calls["grande"] += 1
                raise RpcError("HTTP 403 en grande", code=403)
            return chain(url, payload, timeout)
        rpc = Rpc(["https://grande", "https://chico"], transport=transport, sleep=no_sleep, rps=0)
        rpc.log_limit.update({"https://grande": 50_000, "https://chico": 1_000})
        logs = rpc.get_logs(None, [None], 1, 20_100)
        self.assertEqual(len(logs), len(chain.logs))
        self.assertEqual(calls["grande"], 1)          # un 403 lo castiga y ya no se le piden rangos

    def test_trace_calls_are_gated(self):
        rpc = Rpc(["https://a"], transport=fc.FakeChain(), sleep=no_sleep, rps=0, trace_concurrency=2)
        self.assertEqual(rpc.gates["debug_traceTransaction"]._value, 2)

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


class TestLiquidatorSet(unittest.TestCase):
    def test_owner_wallets_join_w_but_third_parties_do_not(self):
        from census_dinero.collect import liquidator_set
        bot, signer, owner, fund, pool, auction = "0xb", "0xs", "0xo", "0xf", "0xp", "0xa"
        pairs = [(fund, bot), (bot, pool), (pool, bot), (bot, owner), (bot, auction), (pool, "0xq")]
        eoas = {owner, fund, signer}
        w, extra = liquidator_set({bot, signer}, pairs, {"0x0"}, lambda a: a in eoas)
        self.assertEqual(extra, {owner, fund})
        self.assertNotIn(pool, w)
        self.assertNotIn(auction, w)

    def test_codeless_protocol_pocket_falls_back_to_minimal_w(self):
        pocket = fc.norm("0x" + "3a" * 20)        # como el bolsillo del PSM de Maker: sin código
        chain = fc.FakeChain()
        rc = chain.receipts[fc.th(0xD)]
        def tr(tok, frm, to, amt):
            return {"address": tok, "topics": [fc.ERC20_TRANSFER_TOPIC, "0x" + fc.encode_address(frm),
                                                "0x" + fc.encode_address(to)], "data": "0x" + fc.w(amt)}
        rc["logs"] += [tr(fc.USDC, fc.BOT_A, pocket, 35_000 * 10 ** 6), tr(fc.WSTETH, fc.POOLX, fc.BOT_A, 10 ** 19)]
        fc.EOAS.add(pocket)
        try:
            col, _ = make_collector(chain=chain)
            tmp = tempfile.mkdtemp()
            col.run(1, tmp)
        finally:
            fc.EOAS.discard(pocket)
        with open(os.path.join(tmp, "liquidaciones.jsonl")) as fh:
            d = next(r for r in map(json.loads, fh) if r["tx_hash"] == fc.th(0xD))
        gas = 350_000 * 12e9 / 1e18 * 3000
        self.assertTrue(d["w_minimal"])
        self.assertTrue(d["realized_complete"])
        self.assertAlmostEqual(d["realized_usd"], 15.0 - gas, places=6)

    def test_out_of_range_realized_is_flagged(self):
        chain = fc.FakeChain()
        rc = chain.receipts[fc.th(0xD)]
        rc["logs"].append({"address": fc.USDC, "topics": [fc.ERC20_TRANSFER_TOPIC, "0x" + fc.encode_address(fc.POOLX),
                                                           "0x" + fc.encode_address(fc.BOT_A)],
                           "data": "0x" + fc.w(50_000 * 10 ** 6)})
        col, _ = make_collector(chain=chain)
        tmp = tempfile.mkdtemp()
        meta = col.run(1, tmp)
        with open(os.path.join(tmp, "liquidaciones.jsonl")) as fh:
            d = next(r for r in map(json.loads, fh) if r["tx_hash"] == fc.th(0xD))
        self.assertEqual(d["realized_anomaly"], "neto_fuera_de_rango")
        self.assertFalse(d["realized_complete"])
        self.assertIn("USDC +50015", d["net_flows"])
        self.assertEqual(meta["with_realized_complete"], 4)


class FakeExplorer:
    """Blockscout falso armado con los mismos hechos de FakeChain, pero con su propio formato."""

    BASE = "https://explorador.falso"

    def __init__(self, chain):
        self.chain = chain

    def __call__(self, url, timeout):
        if "coins.llama.fi" in url:
            return llama_getter(url, timeout)
        path = url[len(self.BASE):].split("?")[0].strip("/").split("/")
        c = self.chain
        if path[:3] == ["api", "v2", "blocks"]:
            return {"miner": {"hash": fc.BUILDER}}
        if path[:3] == ["api", "v2", "addresses"]:
            return {"is_contract": fc.norm(path[3]) not in fc.EOAS}
        h = path[3]
        tx, rc = c.txs[h], c.receipts[h]
        if len(path) == 4:
            return {"from": {"hash": tx["from"]}, "to": {"hash": tx["to"]}, "value": "0",
                    "block_number": int(tx["blockNumber"], 16),
                    "fee": {"type": "actual", "value": str(int(rc["gasUsed"], 16) * int(rc["effectiveGasPrice"], 16))}}
        if path[4] == "token-transfers":
            items = []
            for lg in rc["logs"]:
                if lg["topics"][0] != fc.ERC20_TRANSFER_TOPIC:
                    continue
                dec = 18 if fc.norm(lg["address"]) == fc.WETH else 6
                items.append({"from": {"hash": "0x" + lg["topics"][1][-40:]}, "to": {"hash": "0x" + lg["topics"][2][-40:]},
                              "token": {"address_hash": lg["address"], "symbol": "T", "type": "ERC-20", "decimals": str(dec)},
                              "total": {"value": str(int(lg["data"], 16)), "decimals": str(dec)}})
            return {"items": items, "next_page_params": None}
        if path[4] == "internal-transactions":
            items = [{"from": {"hash": k["from"]}, "to": {"hash": k["to"]}, "value": str(int(k["value"], 16)),
                      "type": "call", "success": not k.get("error")}
                     for k in c.traces_by_tx[h].get("calls", []) if k["type"] == "CALL"]
            return {"items": items, "next_page_params": None}
        raise AssertionError(url)


class TestVerificar(unittest.TestCase):
    def test_explorer_recomputation_matches_census(self):
        from census_dinero import verificar
        col, chain = make_collector()
        tmp = tempfile.mkdtemp()
        col.run(1, tmp)
        recs, _ = an.load([os.path.join(tmp, "liquidaciones.jsonl")])
        web = WebClient(rps=0, getter=FakeExplorer(chain), sleep=no_sleep, retries=1)
        with open(os.path.join(tmp, "evidencia.json")) as fh:
            evidence = json.load(fh)
        self.assertIn(fc.th(0xD), {e["tx"]["hash"] for e in evidence})
        res = verificar.verify(recs, web=web, explorers={"ethereum": FakeExplorer.BASE}, evidence=evidence)
        for fuente in ("Blockscout", "evidencia RPC"):
            d = next(r for r in res if r["tx_hash"] == fc.th(0xD) and r["fuente"] == fuente)
            self.assertEqual(d["ok"], {"gas": True, "terceros": True, "neto": True, "colateral": True}, fuente)
            self.assertAlmostEqual(d["third_party_eth"]["explorer"], 80 / 3000, places=9)
        a = next(r for r in res if r["tx_hash"] == fc.th(0xA) and r["fuente"] == "evidencia RPC")
        self.assertTrue(a["ok"]["neto"] and a["ok"]["terceros"])
        md = verificar.render(res)
        self.assertIn(fc.th(0xD), md)


class TestOracleInTxAndPayees(unittest.TestCase):
    def test_oracle_update_in_same_tx_counts_as_zero_blocks(self):
        chain = fc.FakeChain()
        svr = fc.norm("0x" + "5f" * 20)          # agregador SVR que no está en la cadena de fuentes vigilada
        chain.receipts[fc.th(0xB)]["logs"].insert(0, {"address": svr, "topics": [fc.ANSWER_UPDATED_TOPIC, fc.th(1), fc.th(2)],
                                                      "data": "0x" + fc.w(0), "logIndex": hex(1)})
        col, _ = make_collector(chain=chain)
        tmp = tempfile.mkdtemp()
        col.run(1, tmp)
        with open(os.path.join(tmp, "liquidaciones.jsonl")) as fh:
            b = next(r for r in map(json.loads, fh) if r["tx_hash"] == fc.th(0xB))
        self.assertEqual(b["blocks_since_oracle"], 0)
        self.assertTrue(b["same_tx_as_oracle"])
        self.assertEqual(b["oracle_in_tx"], svr)

    def test_payees_show_who_gets_the_eth(self):
        col, chain = make_collector()
        tmp = tempfile.mkdtemp()
        col.run(1, tmp)
        recs, metas = an.load([os.path.join(tmp, "liquidaciones.jsonl")])
        res = an.analyze(recs, metas)
        kinds = {p["payee"]: p["kind"] for p in res["payees"]}
        self.assertEqual(kinds[fc.AUCTION], "un_solo_liquidador")
        self.assertEqual(kinds[fc.BUILDER], "builder")


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

    def test_entry_contract_own_vs_shared(self):
        alt = {"realized_usd": 90.0, "third_party_eth": 0.0, "realized_complete": True, "net_flows": "USDC +91"}
        own = self.rec("0xa", tx_to="0xmain", liquidator="0xhelper", realized_usd=-1.0, entry_variant=alt)
        s1 = self.rec("0xb", tx_to="0xatlas", liquidator="0xsolver1", third_party_usd=95.0, realized_usd=2.0,
                      entry_variant=dict(alt, realized_usd=97.0))
        s2 = self.rec("0xc", tx_to="0xatlas", liquidator="0xsolver2", third_party_usd=95.0, realized_usd=2.0,
                      entry_variant=dict(alt, realized_usd=97.0))
        known = self.rec("0xd", chain="arbitrum", tx_to="0x8ad1ae9d97c79aa68a0a151e83ff3942f68f86c1",
                         liquidator="0xsolver3", entry_variant=dict(alt, realized_usd=97.0))
        direct = self.rec("0xe", tx_to="0xpool", pool="0xpool", liquidator="0xeoa", realized_usd=170.0,
                          entry_variant=dict(alt, realized_usd=-0.02))
        an.resolve_entries([direct])
        self.assertEqual((direct["entry"], direct["realized_usd"]), ("liquidador", 170.0))
        an.resolve_entries([own, s1, s2, known])
        self.assertEqual([r["entry"] for r in (own, s1, s2, known)], ["propia", "compartida", "compartida", "compartida"])
        self.assertEqual((own["realized_usd"], own["realized_base_usd"]), (90.0, -1.0))
        self.assertEqual(s1["realized_usd"], 2.0)
        an.resolve_entries([own])                      # idempotente
        self.assertEqual(own["realized_usd"], 90.0)

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
