"""Recolección de liquidaciones de Aave V3 y Morpho Blue y enriquecimiento por transacción.

Para cada liquidación obtiene: bono en USD, ganador, bloques desde la última
actualización del oráculo involucrado y lo pagado al builder (propina + pagos
directos al coinbase). Todo es lectura; nada se firma ni se envía.
"""

import bisect
import concurrent.futures as cf
import json
import os
import sys
import threading
import time

from .abi import (address_from_topic, address_from_word, decode_string, encode_address,
                  encode_bytes32, norm, to_int, words)
from .config import (AAVE_LIQUIDATION_TOPIC, ANSWER_UPDATED_TOPIC, CHAINS, ERC20_TRANSFER_TOPIC,
                     MORPHO_LIQUIDATE_TOPIC, MORPHO_LIQUIDATION_CURSOR, MORPHO_MAX_LIF,
                     ORACLE_LOOKBACK_SECONDS, SEL)
from .keccak import topic
from .prices import Prices
from .rpc import CallReverted, Rpc, RpcError
from .web import WebClient, WebError

NEW_TRANSMISSION_OCR1 = topic("NewTransmission(uint32,int192,address,int192[],bytes,bytes32)")
NEW_TRANSMISSION_OCR2 = topic("NewTransmission(uint32,int192,address,uint32,int192[],bytes,int192,bytes32,uint40)")
ORACLE_UPDATE_TOPICS = [ANSWER_UPDATED_TOPIC, NEW_TRANSMISSION_OCR1, NEW_TRANSMISSION_OCR2]
ZERO = "0x" + "0" * 40


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def morpho_lif(lltv_wad: int) -> float:
    lltv = lltv_wad / 1e18
    return min(MORPHO_MAX_LIF, 1.0 / (1.0 - MORPHO_LIQUIDATION_CURSOR * (1.0 - lltv)))


# --- Decodificadores -----------------------------------------------------------
def _common(log_, chain_key):
    return {
        "chain": chain_key,
        "block": int(log_["blockNumber"], 16),
        "tx_hash": log_["transactionHash"].lower(),
        "log_index": int(log_["logIndex"], 16),
        "tx_index": int(log_["transactionIndex"], 16),
    }


def decode_aave(log_, chain_key, market_name):
    t = log_["topics"]
    w = words(log_["data"])
    if len(t) != 4 or t[0].lower() != AAVE_LIQUIDATION_TOPIC or len(w) != 4:
        raise ValueError("log no es LiquidationCall de Aave V3")
    rec = _common(log_, chain_key)
    rec.update({
        "protocol": "aave",
        "market": market_name,
        "pool": norm(log_["address"]),
        "collateral": address_from_topic(t[1]),
        "debt": address_from_topic(t[2]),
        "borrower": address_from_topic(t[3]),
        "debt_raw": w[0],
        "collateral_raw": w[1],
        "liquidator": address_from_word(w[2]),
        "receive_atoken": bool(w[3]),
        "bad_debt_raw": 0,
    })
    return rec


def decode_morpho(log_, chain_key):
    t = log_["topics"]
    w = words(log_["data"])
    if len(t) != 4 or t[0].lower() != MORPHO_LIQUIDATE_TOPIC or len(w) != 5:
        raise ValueError("log no es Liquidate de Morpho Blue")
    rec = _common(log_, chain_key)
    rec.update({
        "protocol": "morpho",
        "market": t[1].lower(),
        "pool": norm(log_["address"]),
        "liquidator": address_from_topic(t[2]),
        "borrower": address_from_topic(t[3]),
        "debt_raw": w[0],
        "repaid_shares": w[1],
        "collateral_raw": w[2],
        "bad_debt_raw": w[3],
    })
    return rec


def call_frames_value_to(frame, target):
    """Suma el ETH enviado a `target` en un árbol de callTracer, ignorando subárboles revertidos."""
    if frame.get("error"):
        return 0
    total = 0
    kind = (frame.get("type") or "").upper()
    if kind in ("CALL", "CREATE", "CREATE2", "SELFDESTRUCT") and norm(frame.get("to") or ZERO) == target:
        total += to_int(frame.get("value") or "0x0")
    for child in frame.get("calls") or []:
        total += call_frames_value_to(child, target)
    return total


def parity_traces_value_to(traces, target):
    total = 0
    for tr in traces or []:
        if tr.get("error"):
            continue
        action = tr.get("action") or {}
        kind = tr.get("type")
        if kind == "call" and (action.get("callType") or "call") == "call":
            if norm(action.get("to") or ZERO) == target:
                total += to_int(action.get("value") or "0x0")
        elif kind == "create" and norm((tr.get("result") or {}).get("address") or ZERO) == target:
            total += to_int(action.get("value") or "0x0")
        elif kind in ("suicide", "selfdestruct") and norm(action.get("refundAddress") or ZERO) == target:
            total += to_int(action.get("balance") or "0x0")
    return total


def blockscout_value_to(items, target):
    total = 0
    for it in items or []:
        if it.get("success") is False or it.get("error"):
            continue
        kind = f"{it.get('type') or ''} {it.get('call_type') or ''}".lower()
        if "delegate" in kind or "static" in kind:
            continue
        to = it.get("to") or {}
        to = to.get("hash") if isinstance(to, dict) else to
        if to and norm(to) == target:
            total += int(it.get("value") or 0)
    return total


class Collector:
    def __init__(self, chain_key, *, rpc=None, web=None, protocols=("aave", "morpho"), workers=6,
                 time_budget_s=5 * 3600, rps=12, extra_rpcs=()):
        self.chain = CHAINS[chain_key]
        urls = list(extra_rpcs)
        env = os.environ.get(self.chain.extra_rpcs_env, "")
        urls += [u.strip() for u in env.split(",") if u.strip()]
        urls += list(self.chain.public_rpcs)
        self.rpc = rpc or Rpc(urls, rps=rps, expected_chain_id=self.chain.chain_id)
        self.web = web or WebClient(rps=4)
        self.prices = Prices(self.rpc, self.chain, self.web)
        self.protocols = tuple(protocols)
        self.workers = workers
        self.deadline = time.monotonic() + time_budget_s
        self.lock = threading.Lock()
        self.headers = {}
        self.tokens = {}
        self.morpho_params = {}
        self.feed_cache = {}
        self.updates = {}
        self.direct_stats = {}
        self.errors = []

    # -- utilidades con caché -----------------------------------------------------
    def header(self, number):
        with self.lock:
            if number in self.headers:
                return self.headers[number]
        b = self.rpc.block(number)
        h = {"timestamp": int(b["timestamp"], 16), "base_fee": to_int(b.get("baseFeePerGas") or "0x0"),
             "miner": norm(b.get("miner") or ZERO)}
        with self.lock:
            self.headers[number] = h
        return h

    def token(self, addr):
        addr = norm(addr)
        with self.lock:
            if addr in self.tokens:
                return self.tokens[addr]
        try:
            dec = words(self.rpc.eth_call(addr, SEL["decimals"]))[0]
        except (RpcError, ValueError, IndexError):
            dec = None
        try:
            sym = decode_string(self.rpc.eth_call(addr, SEL["symbol"])) or addr[:10]
        except (RpcError, ValueError):
            sym = addr[:10]
        meta = {"decimals": dec, "symbol": sym.strip().replace(",", " ")[:24]}
        with self.lock:
            self.tokens[addr] = meta
        return meta

    def morpho_market(self, market_id):
        with self.lock:
            if market_id in self.morpho_params:
                return self.morpho_params[market_id]
        w = words(self.rpc.eth_call(self.chain.morpho, SEL["idToMarketParams"] + encode_bytes32(market_id)))
        params = {"loan": address_from_word(w[0]), "collateral": address_from_word(w[1]),
                  "oracle": address_from_word(w[2]), "irm": address_from_word(w[3]), "lltv": w[4]}
        with self.lock:
            self.morpho_params[market_id] = params
        return params

    def _addr_call(self, to, sel):
        try:
            w = words(self.rpc.eth_call(to, sel))
            if not w:
                return None
            a = address_from_word(w[0])
            return None if a == ZERO else a
        except (RpcError, ValueError, IndexError):
            return None

    def feed_addresses(self, addr, depth=0):
        """Direcciones que emiten AnswerUpdated detrás de una fuente de precio (proxy, adaptador CAPO...)."""
        addr = norm(addr)
        if addr == ZERO:
            return set()
        key = (addr, depth)
        with self.lock:
            if key in self.feed_cache:
                return self.feed_cache[key]
        out = {addr}
        agg = self._addr_call(addr, SEL["aggregator"])
        if agg:
            out.add(agg)
        elif depth < 3:
            for g in ("ASSET_TO_USD_AGGREGATOR", "BASE_TO_USD_AGGREGATOR", "REFERENCE_FEED"):
                sub = self._addr_call(addr, SEL[g])
                if sub:
                    out |= self.feed_addresses(sub, depth + 1)
        with self.lock:
            self.feed_cache[key] = out
        return out

    # -- ventana --------------------------------------------------------------------
    def resolve_window(self, days, end_block=None):
        if end_block is None:
            try:
                end = int(self.rpc.block("finalized")["number"], 16)
            except (RpcError, KeyError, TypeError):
                end = self.rpc.block_number() - 64
        else:
            end = end_block
        end_ts = self.header(end)["timestamp"]
        probe = max(1, end - 100_000)
        avg = max(0.05, (end_ts - self.header(probe)["timestamp"]) / max(1, end - probe))

        def find(ts):
            guess = int(end - (end_ts - ts) / avg)
            lo = max(1, guess - int(0.25 * (end - guess)) - 1000)
            if self.header(lo)["timestamp"] >= ts:
                lo = 1
            return self.rpc.block_at_or_after(ts, lo, end)

        start_ts = end_ts - int(days * 86400)
        start = find(start_ts)
        lookback = find(start_ts - ORACLE_LOOKBACK_SECONDS)
        return {"start_block": start, "end_block": end, "lookback_block": lookback,
                "start_ts": self.header(start)["timestamp"], "end_ts": end_ts,
                "avg_block_time_s": round(avg, 4), "days": days}

    # -- paso 1: eventos de liquidación -------------------------------------------
    def fetch_liquidations(self, start, end):
        recs = []
        if "aave" in self.protocols and self.chain.aave:
            by_pool = {norm(m.pool): m for m in self.chain.aave}
            logs = self.rpc.get_logs(list(by_pool), [AAVE_LIQUIDATION_TOPIC], start, end,
                                     on_progress=lambda b: None)
            for lg in logs:
                if lg.get("removed"):
                    continue
                try:
                    recs.append(decode_aave(lg, self.chain.key, by_pool[norm(lg["address"])].name))
                except (ValueError, KeyError) as e:
                    self.errors.append(f"decodificación aave {lg.get('transactionHash')}: {e}")
            log(f"{self.chain.key}: {len(logs)} liquidaciones Aave")
        if "morpho" in self.protocols and self.chain.morpho:
            logs = self.rpc.get_logs(self.chain.morpho, [MORPHO_LIQUIDATE_TOPIC], start, end)
            for lg in logs:
                if lg.get("removed"):
                    continue
                try:
                    recs.append(decode_morpho(lg, self.chain.key))
                except (ValueError, KeyError) as e:
                    self.errors.append(f"decodificación morpho {lg.get('transactionHash')}: {e}")
            log(f"{self.chain.key}: {len(logs)} liquidaciones Morpho")
        recs.sort(key=lambda r: (r["block"], r["log_index"]))
        return recs

    # -- paso 2: metadatos y fuentes de oráculo -----------------------------------
    def attach_metadata(self, recs):
        oracle_of = {norm(m.pool): norm(m.oracle) for m in self.chain.aave}
        feeds_by_key = {}
        for r in recs:
            if r["protocol"] == "morpho":
                try:
                    p = self.morpho_market(r["market"])
                except (RpcError, ValueError, IndexError) as e:
                    r["error"] = f"parámetros Morpho: {e}"
                    continue
                r["collateral"], r["debt"], r["oracle"], r["lltv"] = p["collateral"], p["loan"], p["oracle"], p["lltv"]
                r["lif"] = morpho_lif(p["lltv"])
                fk = ("morpho", p["oracle"])
                if fk not in feeds_by_key:
                    s = {norm(p["oracle"])}
                    for g in ("BASE_FEED_1", "BASE_FEED_2", "QUOTE_FEED_1", "QUOTE_FEED_2"):
                        sub = self._addr_call(p["oracle"], SEL[g])
                        if sub:
                            s |= self.feed_addresses(sub)
                    feeds_by_key[fk] = s
                r["_feeds"] = fk
            else:
                r["oracle"] = oracle_of.get(r["pool"])
                keys = []
                for asset in (r["collateral"], r["debt"]):
                    fk = ("aave", r["oracle"], asset)
                    if fk not in feeds_by_key:
                        src = self._addr_call(r["oracle"], SEL["getSourceOfAsset"] + encode_address(asset)) \
                            if r["oracle"] else None
                        feeds_by_key[fk] = self.feed_addresses(src) if src else set()
                    keys.append(fk)
                r["_feeds"] = tuple(keys)
            for side in ("collateral", "debt"):
                if r.get(side):
                    meta = self.token(r[side])
                    r[f"{side}_symbol"] = meta["symbol"]
                    r[f"{side}_decimals"] = meta["decimals"]
        return feeds_by_key

    # -- paso 3: actualizaciones de oráculo -------------------------------------------
    def fetch_oracle_updates(self, feeds_by_key, lookback, end):
        addrs = sorted({a for s in feeds_by_key.values() for a in s})
        index = {a: [] for a in addrs}
        for i in range(0, len(addrs), 40):
            part = addrs[i:i + 40]
            try:
                logs = self.rpc.get_logs(part, [ORACLE_UPDATE_TOPICS], lookback, end)
            except RpcError as e:
                self.errors.append(f"logs de oráculo: {e}")
                for a in part:
                    index.pop(a, None)
                continue
            for lg in logs:
                if lg.get("removed"):
                    continue
                a = norm(lg["address"])
                if a in index:
                    index[a].append((int(lg["blockNumber"], 16), int(lg["logIndex"], 16), lg["transactionHash"].lower()))
        for a in index:
            index[a].sort()
        self.updates = index
        log(f"{self.chain.key}: {sum(len(v) for v in index.values())} actualizaciones de oráculo en {len(index)} contratos")
        return index

    def last_update(self, rec, feeds_by_key):
        keys = rec.get("_feeds")
        if not keys:
            return None
        keys = keys if isinstance(keys, tuple) and keys and isinstance(keys[0], tuple) else (keys,)
        addrs = set()
        for k in keys:
            addrs |= feeds_by_key.get(k, set())
        best = None
        watched = False
        for a in addrs:
            lst = self.updates.get(a)
            if lst is None:
                continue
            watched = True
            pos = bisect.bisect_left(lst, (rec["block"], rec["log_index"], ""))
            if pos > 0:
                cand = lst[pos - 1]
                if best is None or cand > best:
                    best = cand
        return best if best else ("sin_ver" if watched else None)

    # -- paso 4: pagos al builder ---------------------------------------------------------
    def direct_payment(self, tx, receipt, coinbase):
        """ETH enviado directamente al coinbase dentro de la transacción. None si no se pudo medir."""
        h = tx["hash"]
        weth = norm(self.chain.weth)
        weth_wei = 0
        for lg in receipt.get("logs") or []:
            t = lg.get("topics") or []
            if norm(lg.get("address") or ZERO) == weth and len(t) == 3 and t[0].lower() == ERC20_TRANSFER_TOPIC \
                    and address_from_topic(t[2]) == coinbase:
                weth_wei += to_int(lg["data"])
        try:
            frame = self.rpc.call("debug_traceTransaction", [h, {"tracer": "callTracer"}])
            return call_frames_value_to(frame, coinbase) + weth_wei, "debug_traceTransaction"
        except RpcError:
            pass
        try:
            traces = self.rpc.call("trace_transaction", [h])
            return parity_traces_value_to(traces, coinbase) + weth_wei, "trace_transaction"
        except RpcError:
            pass
        if self.chain.blockscout:
            try:
                total = to_int(tx.get("value") or "0x0") if norm(tx.get("to") or ZERO) == coinbase else 0
                url = f"{self.chain.blockscout}/api/v2/transactions/{h}/internal-transactions"
                for _ in range(10):
                    data = self.web.get(url)
                    total += blockscout_value_to(data.get("items"), coinbase)
                    nxt = data.get("next_page_params")
                    if not nxt:
                        return total + weth_wei, "blockscout"
                    q = "&".join(f"{k}={v}" for k, v in nxt.items())
                    url = f"{self.chain.blockscout}/api/v2/transactions/{h}/internal-transactions?{q}"
            except (WebError, AttributeError, ValueError, TypeError):
                pass
        return None, "no_medido"

    # -- paso 5: enriquecimiento por transacción --------------------------------------
    def enrich_tx(self, group, feeds_by_key):
        h = group[0]["tx_hash"]
        tx = self.rpc.call("eth_getTransactionByHash", [h])
        rc = self.rpc.call("eth_getTransactionReceipt", [h])
        if tx is None or rc is None:
            raise RpcError(f"transacción {h} no disponible")
        hd = self.header(group[0]["block"])
        gas_used = to_int(rc["gasUsed"])
        eff = to_int(rc.get("effectiveGasPrice") or tx.get("gasPrice") or "0x0")
        l1 = to_int(rc.get("l1Fee") or "0x0")
        gas_wei = gas_used * eff + l1
        priority_wei = max(0, eff - hd["base_fee"]) * gas_used if hd["base_fee"] else 0
        if self.chain.builder_market:
            direct_wei, direct_src = self.direct_payment(tx, rc, hd["miner"])
        else:
            direct_wei, direct_src = 0, "no_aplica_l2"
        with self.lock:
            self.direct_stats[direct_src] = self.direct_stats.get(direct_src, 0) + 1
        eth_usd, eth_src = self.prices.eth_usd(group[0]["block"], hd["timestamp"])

        for r in group:
            r["timestamp"] = hd["timestamp"]
            r["tx_from"] = norm(tx["from"])
            r["tx_to"] = norm(tx.get("to") or ZERO)
            r["builder_coinbase"] = hd["miner"]
            r["liqs_in_tx"] = len(group)
            self.value(r, hd)
            upd = self.last_update(r, feeds_by_key)
            if isinstance(upd, tuple):
                r["oracle_update_block"] = upd[0]
                r["oracle_update_tx"] = upd[2]
                r["blocks_since_oracle"] = r["block"] - upd[0]
                r["seconds_since_oracle"] = hd["timestamp"] - self.header(upd[0])["timestamp"]
                r["same_tx_as_oracle"] = upd[2] == r["tx_hash"]
            else:
                r["oracle_status"] = upd or "sin_fuente"

        # Gas y pagos de la transacción se reparten entre sus liquidaciones según el bono.
        bonuses = [r.get("bonus_usd") for r in group]
        if all(b is not None and b > 0 for b in bonuses):
            weights = [b / sum(bonuses) for b in bonuses]
        else:
            weights = [1 / len(group)] * len(group)
        for r, wgt in zip(group, weights):
            r["gas_eth"] = gas_wei * wgt / 1e18
            r["priority_eth"] = priority_wei * wgt / 1e18
            r["direct_eth"] = None if direct_wei is None else direct_wei * wgt / 1e18
            r["direct_source"] = direct_src
            r["eth_usd"] = eth_usd
            r["eth_price_source"] = eth_src
            if eth_usd:
                r["gas_usd"] = r["gas_eth"] * eth_usd
                builder_eth = r["priority_eth"] + (r["direct_eth"] or 0)
                r["builder_usd"] = builder_eth * eth_usd
                if r.get("bonus_usd") is not None:
                    r["net_usd"] = r["bonus_usd"] - r["gas_usd"] - (r["direct_eth"] or 0) * eth_usd
                    if r["bonus_usd"] > 0:
                        r["builder_share"] = r["builder_usd"] / r["bonus_usd"]
            r["builder_payment_complete"] = direct_wei is not None
            r["enriched"] = True

    def value(self, r, hd):
        ts = hd["timestamp"]
        dc, dd = r.get("collateral_decimals"), r.get("debt_decimals")
        if dd is None or (r["protocol"] == "aave" and dc is None):
            r["bonus_source"] = "sin_decimales"
            return
        debt_amt = r["debt_raw"] / 10 ** dd
        r["debt_amount"] = debt_amt
        if dc is not None:
            r["collateral_amount"] = r["collateral_raw"] / 10 ** dc
        if r["protocol"] == "morpho":
            p, src = self.prices.token_usd(r["debt"], r["block"], ts)
            if p is None:
                r["bonus_source"] = "sin_precio"
                return
            r["debt_usd"] = debt_amt * p
            r["bonus_usd"] = debt_amt * (r["lif"] - 1.0) * p
            r["bonus_source"] = "lif_morpho+" + src
            return
        pc, sc = self.prices.token_usd(r["collateral"], r["block"], ts, oracle=r.get("oracle"))
        pd, sd = self.prices.token_usd(r["debt"], r["block"], ts, oracle=r.get("oracle"))
        if sc != sd or pc is None or pd is None:
            pc = self.prices.llama(f"{self.chain.llama}:{r['collateral']}", ts)
            pd = self.prices.llama(f"{self.chain.llama}:{r['debt']}", ts)
            sc = sd = "mercado_defillama"
        if pc is None or pd is None:
            r["bonus_source"] = "sin_precio"
            return
        r["debt_usd"] = debt_amt * pd
        r["bonus_usd"] = r["collateral_amount"] * pc - debt_amt * pd
        r["bonus_source"] = sc

    # -- orquestación -------------------------------------------------------------------
    def run(self, days, out_dir, end_block=None):
        t0 = time.time()
        self.rpc.check_chain()
        win = self.resolve_window(days, end_block)
        log(f"{self.chain.key}: ventana bloques {win['start_block']}..{win['end_block']} ({days} días)")
        recs = self.fetch_liquidations(win["start_block"], win["end_block"])
        feeds = self.attach_metadata(recs)
        self.fetch_oracle_updates(feeds, win["lookback_block"], win["end_block"])

        groups = {}
        for r in recs:
            if "error" not in r:
                groups.setdefault(r["tx_hash"], []).append(r)
        done = 0
        stopped = False
        with cf.ThreadPoolExecutor(max_workers=self.workers) as ex:
            futs = {ex.submit(self.enrich_tx, g, feeds): h for h, g in groups.items()}
            for fut in cf.as_completed(futs):
                h = futs[fut]
                try:
                    fut.result()
                except cf.CancelledError:
                    for r in groups[h]:
                        r["error"] = "sin enriquecer: presupuesto de tiempo agotado"
                except Exception as e:  # noqa: BLE001 - una transacción rara no debe tumbar el census
                    for r in groups[h]:
                        r["error"] = f"enriquecimiento: {type(e).__name__}: {e}"[:300]
                done += 1
                if done % 100 == 0:
                    log(f"{self.chain.key}: {done}/{len(groups)} transacciones enriquecidas")
                if time.monotonic() > self.deadline and not stopped:
                    stopped = True
                    log(f"{self.chain.key}: presupuesto de tiempo agotado; el resto queda sin enriquecer")
                    for f in futs:
                        f.cancel()
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "liquidaciones.jsonl"), "w") as fh:
            for r in recs:
                r.pop("_feeds", None)
                r.setdefault("enriched", False)
                fh.write(json.dumps(r, sort_keys=True, default=str) + "\n")
        meta = {
            "chain": self.chain.key,
            "protocols": list(self.protocols),
            "window": win,
            "events": len(recs),
            "transactions": len(groups),
            "enriched": sum(1 for r in recs if r.get("enriched")),
            "with_bonus_usd": sum(1 for r in recs if r.get("bonus_usd") is not None),
            "price_sources": self.prices.stats,
            "archive_disabled": self.prices.archive_disabled,
            "direct_payment_sources": self.direct_stats,
            "oracle_contracts_watched": len(self.updates),
            "with_oracle_delta": sum(1 for r in recs if r.get("blocks_since_oracle") is not None),
            "time_budget_hit": stopped,
            "rpc_calls": self.rpc.calls,
            "rpc_stats": self.rpc.stats,
            "web_calls": self.web.calls,
            "errors_sample": self.errors[:50] + [r["error"] for r in recs if r.get("error")][:50],
            "elapsed_s": round(time.time() - t0, 1),
        }
        with open(os.path.join(out_dir, "meta.json"), "w") as fh:
            json.dump(meta, fh, indent=2, sort_keys=True, default=str)
        log(f"{self.chain.key}: listo — {meta['events']} eventos, {meta['enriched']} enriquecidos, "
            f"{meta['rpc_calls']} llamadas RPC, {meta['elapsed_s']} s")
        return meta
