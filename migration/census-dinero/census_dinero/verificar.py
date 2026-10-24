"""Verificación de filas contra el explorador (API v2 de Blockscout).

Para una muestra de liquidaciones por cadena recalcula, solo con datos del
explorador (transferencias de tokens, transferencias internas de ETH y comisión
de la transacción), las cantidades del evento, el gas, lo pagado en ETH a
terceros y lo que se quedó el liquidador; y lo compara con lo que midió el
census por RPC. Es un camino independiente: no usa recibos, trazas ni el código
de collect.py salvo la definición del conjunto del liquidador (liquidator_set),
que debe ser la misma para comparar. Los precios sí salen de la misma fuente
(DefiLlama) porque lo que se verifica son los flujos, no el precio.
"""

import json
import os
from collections import defaultdict

from .abi import norm
from .analyze import derive, resolve_entries
from .collect import liquidator_set
from .config import CHAINS
from .prices import LLAMA
from .web import WebClient, WebError

ZERO = "0x" + "0" * 40
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _addr(x):
    if isinstance(x, dict):
        x = x.get("hash") or x.get("address_hash") or x.get("address")
    return norm(x) if x else None


def pick_rows(recs, per_chain=4):
    """Muestra por cadena: mayor bono, mayor neto directo, mayor subasta y una sin medir."""
    out = []
    for chain in sorted({r["chain"] for r in recs}):
        rs = [r for r in recs if r["chain"] == chain and r.get("enriched") and r.get("bonus_usd") is not None]
        picks = []

        def add(cands, key):
            cands = sorted(cands, key=key)
            for r in cands:
                if r["tx_hash"] not in {p["tx_hash"] for p in picks}:
                    picks.append(r)
                    return
        add(rs, lambda r: -r["bonus_usd"])
        add([r for r in rs if r.get("route") == "directa"], lambda r: -(r.get("realized_usd") or 0))
        add([r for r in rs if r.get("route") == "subasta"], lambda r: -r["bonus_usd"])
        add([r for r in rs if r.get("route") == "sin_medir"], lambda r: -r["bonus_usd"])
        out.extend(picks[:per_chain])
    return out


class Explorer:
    def __init__(self, base, web):
        self.base = base.rstrip("/")
        self.web = web
        self.contract_cache = {}

    def _pages(self, path):
        items, url = [], f"{self.base}{path}"
        for _ in range(20):
            data = self.web.get(url)
            items += data.get("items") or []
            nxt = data.get("next_page_params")
            if not nxt:
                return items
            url = f"{self.base}{path}?" + "&".join(f"{k}={v}" for k, v in nxt.items())
        return items

    def tx(self, h):
        return self.web.get(f"{self.base}/api/v2/transactions/{h}")

    def miner(self, block):
        try:
            return _addr(self.web.get(f"{self.base}/api/v2/blocks/{block}").get("miner"))
        except WebError:
            return None

    def token_transfers(self, h):
        return self._pages(f"/api/v2/transactions/{h}/token-transfers")

    def internal(self, h):
        return self._pages(f"/api/v2/transactions/{h}/internal-transactions")

    def is_contract(self, a):
        if a not in self.contract_cache:
            try:
                self.contract_cache[a] = bool(self.web.get(f"{self.base}/api/v2/addresses/{a}").get("is_contract"))
            except WebError:
                self.contract_cache[a] = True        # ante la duda no se cuenta como del liquidador
        return self.contract_cache[a]


class RawEvidence:
    """Misma interfaz que Explorer, armada con la evidencia cruda que guarda cada tramo
    (evidencia.json): Transfer de los logs del recibo y ETH interno de la traza, sin la llamada raíz."""

    def __init__(self, ev):
        self.ev = ev

    def tx(self, h):
        t, rc = self.ev["tx"], self.ev["receipt"]
        price = rc.get("effectiveGasPrice") or t.get("gasPrice") or "0x0"
        fee = int(rc["gasUsed"], 16) * int(price, 16) + int(rc.get("l1Fee") or "0x0", 16)
        return {"from": {"hash": t["from"]}, "to": {"hash": t.get("to")}, "value": str(int(t.get("value") or "0x0", 16)),
                "fee": {"value": str(fee)}, "block_number": int(t["blockNumber"], 16)}

    def miner(self, block):
        return norm(self.ev["miner"])

    def is_contract(self, a):
        return self.ev.get("has_code", {}).get(a, True)

    def token_transfers(self, h):
        items = []
        for lg in self.ev["receipt"].get("logs") or []:
            t = [x.lower() for x in lg.get("topics") or []]
            data = lg.get("data") or "0x"
            if len(t) != 3 or t[0] != TRANSFER or len(data) != 66:
                continue
            meta = self.ev.get("tokens", {}).get(norm(lg["address"])) or {}
            items.append({"from": {"hash": "0x" + t[1][-40:]}, "to": {"hash": "0x" + t[2][-40:]},
                          "token": {"address_hash": lg["address"], "type": "ERC-20", "symbol": meta.get("symbol"),
                                    "decimals": meta.get("decimals")},
                          "total": {"value": str(int(data, 16)), "decimals": meta.get("decimals")}})
        return items

    def internal(self, h):
        tr, kind = self.ev.get("trace"), self.ev.get("trace_kind")
        if tr is None:
            raise ValueError("la evidencia no trae traza")
        items = []
        if kind == "debug_traceTransaction":
            def walk(fr, root):
                if fr.get("error"):
                    return
                if not root:
                    items.append({"from": {"hash": fr.get("from")}, "to": {"hash": fr.get("to")},
                                  "value": str(int(fr.get("value") or "0x0", 16)), "type": (fr.get("type") or "").lower(),
                                  "success": True})
                for c in fr.get("calls") or []:
                    walk(c, False)
            walk(tr, True)
        else:
            for x in tr:
                if x.get("error") or not x.get("traceAddress"):
                    continue
                a = x.get("action") or {}
                if x.get("type") == "call":
                    items.append({"from": {"hash": a.get("from")}, "to": {"hash": a.get("to")},
                                  "value": str(int(a.get("value") or "0x0", 16)), "type": a.get("callType") or "call"})
                elif x.get("type") == "create" and (x.get("result") or {}).get("address"):
                    items.append({"from": {"hash": a.get("from")}, "to": {"hash": x["result"]["address"]},
                                  "value": str(int(a.get("value") or "0x0", 16)), "type": "create"})
                elif x.get("type") in ("suicide", "selfdestruct"):
                    items.append({"from": {"hash": a.get("address")}, "to": {"hash": a.get("refundAddress")},
                                  "value": str(int(a.get("balance") or "0x0", 16)), "type": "selfdestruct"})
        return [i for i in items if i["to"]["hash"]]


def explorer_flows(ex, h, weth):
    """[(token, desde, hacia, cantidad cruda, decimales, símbolo)] según el explorador.

    Envolver y desenvolver WETH no cambia valor: se ignoran las transferencias de WETH
    desde/hacia 0x0 y el ETH interno desde/hacia el contrato WETH, sin importar cómo
    las indexe cada explorador."""
    flows = []
    for it in ex.token_transfers(h):
        tok = it.get("token") or {}
        if (tok.get("type") or "ERC-20").upper().replace("-", "") != "ERC20":
            continue
        addr = _addr(tok.get("address_hash") or tok.get("address"))
        frm, to = _addr(it.get("from")) or ZERO, _addr(it.get("to")) or ZERO
        if addr == weth and ZERO in (frm, to):
            continue
        total = it.get("total") or {}
        if total.get("value") is None:
            continue
        dec = total.get("decimals") or tok.get("decimals")
        flows.append((addr, frm, to, int(total["value"]), int(dec) if dec is not None else None,
                      tok.get("symbol") or addr[:10]))
    for it in ex.internal(h):
        if it.get("success") is False or it.get("error"):
            continue
        kind = f"{it.get('type') or ''} {it.get('call_type') or ''}".lower()
        if "delegate" in kind or "static" in kind:
            continue
        v = int(it.get("value") or 0)
        frm, to = _addr(it.get("from")) or ZERO, _addr(it.get("to")) or ZERO
        if v and weth not in (frm, to):
            flows.append(("ETH", frm, to, v, 18, "ETH"))
    return flows


def verify_tx(ex, chain, rows, prices_at):
    """Recalcula una transacción con datos del explorador y la compara con las filas del census."""
    weth = norm(chain.weth)
    h = rows[0]["tx_hash"]
    t = ex.tx(h)
    sender = _addr(t.get("from"))
    tx_to = _addr(t.get("to")) or ZERO
    fee = t.get("fee") or {}
    fee_wei = int(fee.get("value") or 0)
    value = int(t.get("value") or 0)
    flows = explorer_flows(ex, h, weth)
    if value and tx_to:
        flows.append(("ETH", sender, tx_to, value, 18, "ETH"))
    s0 = {sender} | {r["liquidator"] for r in rows}
    coinbase = ex.miner(t.get("block_number") or t.get("block") or rows[0]["block"]) or ZERO
    exclude = {ZERO, weth, coinbase}
    if rows[0].get("entry") == "propia":
        s0.add(tx_to)                    # el contrato de entrada es del mismo bot (ver resolve_entries)
    else:
        exclude.add(tx_to)
    w, benef = liquidator_set(s0, [(f, to) for _, f, to, _, _, _ in flows], exclude,
                              lambda a: not ex.is_contract(a))
    net = defaultdict(int)
    meta = {}
    third_wei = defaultdict(int)
    in_eth = defaultdict(int)
    for tok, f, to, v, dec, sym in flows:
        meta[tok] = (dec, sym)
        if f in w and to not in w:
            net[tok] -= v
            if tok == "ETH":
                third_wei[to] += v
        elif to in w and f not in w:
            net[tok] += v
            if tok == "ETH":
                in_eth[f] += v
    third = sum(max(0, v - in_eth.get(a, 0)) for a, v in third_wei.items()) / 1e18
    ts = rows[0].get("timestamp")
    tokens = [tok for tok, v in net.items() if v and tok not in ("ETH", weth)]
    px = prices_at(chain, tokens, ts)
    eth_usd = rows[0].get("eth_usd")
    usd, unpriced = 0.0, []
    for tok, v in net.items():
        if not v:
            continue
        dec, sym = meta[tok]
        if tok in ("ETH", weth):
            usd += v / 1e18 * eth_usd
            continue
        p = px.get(tok)
        if p is None or dec is None:
            unpriced.append(sym)
            continue
        usd += v / 10 ** dec * p
    usd -= fee_wei / 1e18 * eth_usd
    census_real = sum(r["realized_usd"] for r in rows if r.get("realized_usd") is not None) \
        if any(r.get("realized_usd") is not None for r in rows) else None
    census_third = sum(r["third_party_eth"] for r in rows if r.get("third_party_eth") is not None) \
        if any(r.get("third_party_eth") is not None for r in rows) else None
    census_gas = sum(r.get("gas_eth") or 0 for r in rows)
    # Cada colateral del evento debe aparecer en el explorador como una transferencia de ese
    # token al liquidador por la misma cantidad (Aave la manda desde el aToken, Morpho desde Morpho).
    checks = []
    for r in rows:
        if not r.get("collateral") or r.get("receive_atoken") or r.get("collateral_raw") is None:
            continue
        col, raw = norm(r["collateral"]), int(r["collateral_raw"])
        hit = any(tok == col and to == r["liquidator"] and abs(v - raw) <= max(1, raw // 10 ** 9)
                  for tok, f, to, v, _, _ in flows)
        checks.append({"collateral": r.get("collateral_symbol") or col, "log_index": r["log_index"],
                       "collateral_census": r.get("collateral_amount"), "found_in_explorer": hit})
    return {
        "chain": chain.key, "tx_hash": h, "rows": len(rows), "route": rows[0].get("route"),
        "entry": rows[0].get("entry"),
        "bonus_usd": sum(r.get("bonus_usd") or 0 for r in rows),
        "gas_eth": {"census": census_gas, "explorer": fee_wei / 1e18},
        "third_party_eth": {"census": census_third, "explorer": third},
        "realized_usd": {"census": census_real, "explorer": usd if not unpriced else None},
        "beneficiaries": {"census": rows[0].get("beneficiaries"), "explorer": len(benef)},
        "unpriced_explorer": unpriced,
        "amounts": checks,
    }


def _llama_prices(web):
    cache = {}

    def prices_at(chain, tokens, ts):
        out = {}
        missing = [t for t in tokens if (chain.key, t, ts) not in cache]
        if missing and ts:
            coins = ",".join(f"{chain.llama}:{t}" for t in missing)
            try:
                data = web.get(LLAMA.format(ts=ts - ts % 300, coins=coins))
                low = {k.lower(): v for k, v in (data.get("coins") or {}).items()}
                for t in missing:
                    e = low.get(f"{chain.llama}:{t}".lower())
                    cache[(chain.key, t, ts)] = float(e["price"]) if e and e.get("price") is not None else None
            except (WebError, ValueError, TypeError):
                pass
        for t in tokens:
            out[t] = cache.get((chain.key, t, ts))
        return out
    return prices_at


def close(a, b, tol_abs, tol_rel=0.02):
    if a is None or b is None:
        return None
    return abs(a - b) <= max(tol_abs, tol_rel * max(abs(a), abs(b)))


def verify(recs, web=None, per_chain=4, explorers=None, evidence=None):
    """Verifica la evidencia guardada por los tramos (o una muestra si no hay) contra dos fuentes:
    el explorador (Blockscout, si responde) y la evidencia cruda recalculada con este módulo."""
    web = web or WebClient(rps=3)
    resolve_entries(recs)
    for r in recs:
        if "route" not in r:
            derive(r)
    by_tx = defaultdict(list)
    for r in recs:
        by_tx[(r["chain"], r["tx_hash"])].append(r)
    ev_by = {}
    for ev in evidence or []:
        h = (ev.get("tx") or {}).get("hash", "").lower()
        for chain in {r["chain"] for r in recs}:
            if (chain, h) in by_tx:
                ev_by[(chain, h)] = ev
    picks = list(ev_by) if ev_by else [(p["chain"], p["tx_hash"]) for p in pick_rows(recs, per_chain)]
    prices_at = _llama_prices(web)
    results = []
    dead = set()
    for chain_key, h in picks:
        chain = CHAINS[chain_key]
        rows = sorted(by_tx[(chain_key, h)], key=lambda r: r["log_index"])
        sources = []
        if (chain_key, h) in ev_by:
            sources.append(("evidencia RPC", RawEvidence(ev_by[(chain_key, h)])))
        base = (explorers or {}).get(chain_key, chain.blockscout)
        if base and base not in dead:
            sources.append(("Blockscout", Explorer(base, web)))
        for name, src in sources:
            try:
                res = verify_tx(src, chain, rows, prices_at)
            except (WebError, ValueError, TypeError, KeyError) as e:
                if name == "Blockscout" and "HTTP 403" in str(e):
                    dead.add(base)             # el explorador bloquea esta red: no insistir
                results.append({"chain": chain_key, "tx_hash": h, "fuente": name,
                                "error": f"{type(e).__name__}: {e}"[:200]})
                continue
            res["fuente"] = name
            res["ok"] = {
                "gas": close(res["gas_eth"]["census"], res["gas_eth"]["explorer"], 1e-6),
                "terceros": close(res["third_party_eth"]["census"], res["third_party_eth"]["explorer"], 1e-5),
                "neto": close(res["realized_usd"]["census"], res["realized_usd"]["explorer"], 1.0),
                "colateral": all(c["found_in_explorer"] for c in res["amounts"]) if res["amounts"] else None,
            }
            results.append(res)
    return results


def render(results):
    L = ["# Verificación de filas", "",
         "Cada transacción se recalcula con este módulo, aparte del recolector, desde dos fuentes: el explorador "
         "(API de Blockscout: transferencias de tokens, ETH interno y comisión) y la evidencia cruda guardada por el "
         "tramo (recibo y traza del RPC). Tolerancia: 2% o $1 en neto, 1e-5 ETH en pagos, 1e-6 ETH en gas. "
         "Los precios salen de DefiLlama en ambos lados.", "",
         "| Cadena | Tx | Fuente | Ruta | Bono | Gas census/fuente (ETH) | A terceros census/fuente (ETH) | Neto census/fuente | Colateral del evento | OK |",
         "|---|---|---|---|---:|---|---|---|---|---|"]
    for r in results:
        if r.get("error"):
            L.append(f"| {r['chain']} | `{r['tx_hash']}` | {r.get('fuente', '—')} | — | — | — | — | — | — | "
                     f"no verificable: {r['error']} |")
            continue

        def pair(d, fmt):
            a, b = d["census"], d["explorer"]
            return f"{'—' if a is None else fmt.format(a)} / {'—' if b is None else fmt.format(b)}"
        okv = r["ok"]
        flags = ", ".join(f"{k}: {'sí' if v else ('no' if v is False else '—')}" for k, v in okv.items())
        cols = ", ".join("{} {:.6g} {}".format(c["collateral"], c["collateral_census"] or 0,
                                               "visto" if c["found_in_explorer"] else "NO visto")
                         for c in r["amounts"]) or "—"
        L.append(f"| {r['chain']} | `{r['tx_hash']}` | {r['fuente']} | {r['route']} | ${r['bonus_usd']:,.2f} | "
                 f"{pair(r['gas_eth'], '{:.6f}')} | {pair(r['third_party_eth'], '{:.6f}')} | "
                 f"{pair(r['realized_usd'], '${:,.2f}')} | {cols} | {flags} |")
    return "\n".join(L) + "\n"


def write(results, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "verificacion.json"), "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    md = render(results)
    with open(os.path.join(out_dir, "VERIFICACION.md"), "w") as fh:
        fh.write(md)
    return md
