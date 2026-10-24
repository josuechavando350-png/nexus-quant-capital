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
import traceback

from .abi import (address_from_topic, address_from_word, decode_string, encode_address,
                  encode_bytes32, norm, to_int, words)
from .config import (AAVE_LIQUIDATION_TOPIC, ANSWER_UPDATED_TOPIC, CHAINS, ERC20_TRANSFER_TOPIC,
                     MORPHO_LIQUIDATE_TOPIC, MORPHO_LIQUIDATION_CURSOR, MORPHO_MAX_LIF,
                     ORACLE_LOOKBACK_SECONDS, SEL)
from .keccak import topic
from . import sonda
from .prices import Prices
from .rpc import BudgetExceeded, CallReverted, Rpc, RpcError
from .web import WebClient, WebError

NEW_TRANSMISSION_OCR1 = topic("NewTransmission(uint32,int192,address,int192[],bytes,bytes32)")
NEW_TRANSMISSION_OCR2 = topic("NewTransmission(uint32,int192,address,uint32,int192[],bytes,int192,bytes32,uint40)")
ORACLE_UPDATE_TOPICS = [ANSWER_UPDATED_TOPIC, NEW_TRANSMISSION_OCR1, NEW_TRANSMISSION_OCR2]
ZERO = "0x" + "0" * 40


def log(msg):
    try:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)
    except OSError:
        pass        # el tee del workflow puede morir antes que nosotros al cancelar


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


WETH_DEPOSIT_TOPIC = topic("Deposit(address,uint256)")
WETH_WITHDRAWAL_TOPIC = topic("Withdrawal(address,uint256)")
_VALUE_FRAMES = ("CALL", "CREATE", "CREATE2", "SELFDESTRUCT")


def call_frames_transfers(frame, out=None):
    """[(desde, hacia, wei)] de un árbol de callTracer, ignorando subárboles revertidos."""
    out = [] if out is None else out
    if frame.get("error"):
        return out
    kind = (frame.get("type") or "").upper()
    value = to_int(frame.get("value") or "0x0") or 0
    if kind in _VALUE_FRAMES and value and frame.get("to"):
        out.append((norm(frame.get("from") or ZERO), norm(frame["to"]), value))
    for child in frame.get("calls") or []:
        call_frames_transfers(child, out)
    return out


def parity_transfers(traces):
    out = []
    for tr in traces or []:
        if tr.get("error"):
            continue
        action = tr.get("action") or {}
        kind = tr.get("type")
        if kind == "call" and (action.get("callType") or "call") == "call" and action.get("to"):
            v = to_int(action.get("value") or "0x0")
            if v:
                out.append((norm(action.get("from") or ZERO), norm(action["to"]), v))
        elif kind == "create":
            v = to_int(action.get("value") or "0x0")
            addr = (tr.get("result") or {}).get("address")
            if v and addr:
                out.append((norm(action.get("from") or ZERO), norm(addr), v))
        elif kind in ("suicide", "selfdestruct"):
            v = to_int(action.get("balance") or "0x0")
            if v and action.get("refundAddress"):
                out.append((norm(action.get("address") or ZERO), norm(action["refundAddress"]), v))
    return out


def blockscout_transfers(items):
    out = []
    for it in items or []:
        if it.get("success") is False or it.get("error"):
            continue
        kind = f"{it.get('type') or ''} {it.get('call_type') or ''}".lower()
        if "delegate" in kind or "static" in kind:
            continue
        frm, to = it.get("from") or {}, it.get("to") or {}
        frm = frm.get("hash") if isinstance(frm, dict) else frm
        to = to.get("hash") if isinstance(to, dict) else to
        v = int(it.get("value") or 0)
        if v and to:
            out.append((norm(frm or ZERO), norm(to), v))
    return out


def call_frames_value_to(frame, target):
    return sum(v for _, t, v in call_frames_transfers(frame) if t == target)


def parity_traces_value_to(traces, target):
    return sum(v for _, t, v in parity_transfers(traces) if t == target)


def blockscout_value_to(items, target):
    return sum(v for _, t, v in blockscout_transfers(items) if t == target)


def token_flows(receipt, weth):
    """[(token, desde, hacia, cantidad)] de los logs del recibo (ERC-20 y Deposit/Withdrawal de WETH)."""
    flows, wraps = [], []
    for lg in receipt.get("logs") or []:
        t = [x.lower() for x in (lg.get("topics") or [])]
        if not t:
            continue
        addr = norm(lg.get("address") or ZERO)
        data = lg.get("data") or "0x"
        if t[0] == ERC20_TRANSFER_TOPIC and len(t) == 3 and len(data) == 66:
            flows.append((addr, address_from_topic(t[1]), address_from_topic(t[2]), int(data, 16)))
        elif addr == weth and len(t) == 2 and len(data) == 66 and t[0] in (WETH_DEPOSIT_TOPIC, WETH_WITHDRAWAL_TOPIC):
            who, amt = address_from_topic(t[1]), int(data, 16)
            wraps.append((addr, weth, who, amt) if t[0] == WETH_DEPOSIT_TOPIC else (addr, who, weth, amt))
    # Un WETH que emita Transfer desde/hacia 0x0 y además Deposit/Withdrawal se contaría doble.
    burns = [(f, a) for tok, f, to, a in flows if tok == weth and to == ZERO]
    mints = [(to, a) for tok, f, to, a in flows if tok == weth and f == ZERO]
    for w_ in wraps:
        key = (w_[1], w_[3]) if w_[2] == weth else (w_[2], w_[3])
        pool = burns if w_[2] == weth else mints
        if key in pool:
            pool.remove(key)
            continue
        flows.append(w_)
    return flows


class Collector:
    def __init__(self, chain_key, *, rpc=None, web=None, protocols=("aave", "morpho"), workers=6,
                 time_budget_s=5 * 3600, rps=12, extra_rpcs=()):
        self.chain = CHAINS[chain_key]
        urls = list(extra_rpcs)
        env = os.environ.get(self.chain.extra_rpcs_env, "")
        urls += [u.strip() for u in env.split(",") if u.strip()]
        urls += list(self.chain.public_rpcs)
        self.rpc = rpc or Rpc(urls, rps=rps, expected_chain_id=self.chain.chain_id,
                              public=set(self.chain.public_rpcs))
        self.web = web or WebClient(rps=4)
        self.blockscout = self.chain.blockscout
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
        self.code_cache = {}
        self.trace_errors = {}
        self.errors = []
        self.phases = {}
        self.sonda = []
        self.web_sources = {}
        self.oracle_cover = {}          # dirección -> último bloque leído de sus actualizaciones
        self.events_cover = None        # último bloque leído de eventos de liquidación
        self.interrupted = False
        self.fatal = None
        self.budget_hit = False
        self.second_pass = {}

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
    def resolve_window(self, days=None, end_block=None, start_ts=None, end_ts=None):
        """Ventana de bloques. Con start_ts/end_ts (tramos) la partición es exacta: el tramo
        cubre los bloques con start_ts <= timestamp < end_ts, sin huecos ni solapes entre tramos."""
        if end_block is None:
            try:
                head = int(self.rpc.block("finalized")["number"], 16)
            except (RpcError, KeyError, TypeError):
                head = self.rpc.block_number() - 64
        else:
            head = end_block
        head_ts = self.header(head)["timestamp"]
        probe = max(1, head - 100_000)
        avg = max(0.05, (head_ts - self.header(probe)["timestamp"]) / max(1, head - probe))

        def find(ts):
            """Primer bloque con timestamp >= ts (head + 1 si ninguno)."""
            if ts > head_ts:
                return head + 1
            guess = int(head - (head_ts - ts) / avg)
            lo = max(1, guess - int(0.25 * (head - guess)) - 1000)
            if self.header(lo)["timestamp"] >= ts:
                lo = 1
            return self.rpc.block_at_or_after(ts, lo, head)

        if end_ts is None:
            end, end_ts = head, head_ts + 1
            start_ts = end_ts - 1 - int(days * 86400)
        else:
            if end_ts > head_ts + 1:
                raise RpcError(f"el fin del tramo ({end_ts}) es posterior al último bloque final ({head_ts})")
            end = find(end_ts) - 1
            if start_ts is None:
                start_ts = end_ts - int(days * 86400)
        start = find(start_ts)
        lookback = find(start_ts - ORACLE_LOOKBACK_SECONDS)
        return {"start_block": start, "end_block": end, "lookback_block": lookback,
                "start_ts": start_ts, "end_ts": end_ts, "first_block_ts": self.header(start)["timestamp"],
                "avg_block_time_s": round(avg, 4), "days": round((end_ts - start_ts) / 86400, 4)}

    # -- paso 1: eventos de liquidación -------------------------------------------
    def _progress(self, what, lo, hi):
        """Callback de get_logs que reporta avance cada 30 s."""
        state = {"t": time.monotonic()}

        def cb(block, n, chunk):
            now = time.monotonic()
            if now - state["t"] >= 30:
                state["t"] = now
                pct = 100 * (block - lo + 1) / max(1, hi - lo + 1)
                log(f"{self.chain.key}: {what}: bloque {block:,} ({pct:.0f}%), {n:,} logs, tramo de {chunk:,} bloques")
        return cb

    def _logs(self, what, address, topics, lo, hi):
        """get_logs con avance y plazo; si se acaba el tiempo devuelve lo leído y hasta dónde."""
        try:
            return self.rpc.get_logs(address, topics, lo, hi, on_progress=self._progress(what, lo, hi),
                                     deadline=self.deadline), hi
        except BudgetExceeded as e:
            self.errors.append(f"{what}: tiempo agotado en el bloque {e.next_block}")
            return e.logs, e.next_block - 1

    def fetch_liquidations(self, start, end):
        recs = []
        cover = end
        if "aave" in self.protocols and self.chain.aave:
            by_pool = {norm(m.pool): m for m in self.chain.aave}
            logs, got = self._logs("eventos Aave", list(by_pool), [AAVE_LIQUIDATION_TOPIC], start, end)
            cover = min(cover, got)
            for lg in logs:
                if lg.get("removed"):
                    continue
                try:
                    recs.append(decode_aave(lg, self.chain.key, by_pool[norm(lg["address"])].name))
                except (ValueError, KeyError) as e:
                    self.errors.append(f"decodificación aave {lg.get('transactionHash')}: {e}")
            log(f"{self.chain.key}: {len(logs)} liquidaciones Aave")
        if "morpho" in self.protocols and self.chain.morpho:
            logs, got = self._logs("eventos Morpho", self.chain.morpho, [MORPHO_LIQUIDATE_TOPIC], start, end)
            cover = min(cover, got)
            for lg in logs:
                if lg.get("removed"):
                    continue
                try:
                    recs.append(decode_morpho(lg, self.chain.key))
                except (ValueError, KeyError) as e:
                    self.errors.append(f"decodificación morpho {lg.get('transactionHash')}: {e}")
            log(f"{self.chain.key}: {len(logs)} liquidaciones Morpho")
        self.events_cover = cover
        # Si un protocolo se cortó antes, se descarta lo del otro más allá: la cobertura es una sola.
        recs = [r for r in recs if r["block"] <= cover]
        recs.sort(key=lambda r: (r["block"], r["log_index"]))
        return recs

    # -- paso 2: metadatos y fuentes de oráculo -----------------------------------
    def morpho_feeds(self, oracle):
        s = {norm(oracle)}
        for g in ("BASE_FEED_1", "BASE_FEED_2", "QUOTE_FEED_1", "QUOTE_FEED_2"):
            sub = self._addr_call(oracle, SEL[g])
            if sub:
                s |= self.feed_addresses(sub)
        return s

    def aave_feeds(self, oracle, asset):
        src = self._addr_call(oracle, SEL["getSourceOfAsset"] + encode_address(asset)) if oracle else None
        return self.feed_addresses(src) if src else set()

    def _parallel(self, fn, items):
        """Corre fn sobre items en paralelo; los errores quedan como None (el paso secuencial los registra)."""
        def safe(x):
            try:
                return fn(*x) if isinstance(x, tuple) else fn(x)
            except (RpcError, ValueError, IndexError):
                return None
        items = list(dict.fromkeys(items))
        if not items:
            return {}
        with cf.ThreadPoolExecutor(max_workers=max(1, min(self.workers, len(items)))) as ex:
            return dict(zip(items, ex.map(safe, items)))

    def attach_metadata(self, recs):
        oracle_of = {norm(m.pool): norm(m.oracle) for m in self.chain.aave}
        # Calentar cachés en paralelo: parámetros de Morpho, tokens y fuentes de oráculo.
        self._parallel(self.morpho_market, [r["market"] for r in recs if r["protocol"] == "morpho"])
        params = [self.morpho_params.get(r["market"]) for r in recs if r["protocol"] == "morpho"]
        tokens = [r[s] for r in recs for s in ("collateral", "debt") if r.get(s)]
        tokens += [p[k] for p in params if p for k in ("collateral", "loan")]
        self._parallel(self.token, tokens)
        morpho_keys = [p["oracle"] for p in params if p]
        aave_keys = [(oracle_of.get(r["pool"]), a) for r in recs if r["protocol"] == "aave"
                     for a in (r["collateral"], r["debt"])]
        mf = self._parallel(self.morpho_feeds, morpho_keys)
        af = self._parallel(self.aave_feeds, aave_keys)
        feeds_by_key = {("morpho", o): v for o, v in mf.items() if v is not None}
        feeds_by_key.update({("aave", o, a): v for (o, a), v in af.items() if v is not None})

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
                    feeds_by_key[fk] = self.morpho_feeds(p["oracle"])
                r["_feeds"] = fk
            else:
                r["oracle"] = oracle_of.get(r["pool"])
                keys = []
                for asset in (r["collateral"], r["debt"]):
                    fk = ("aave", r["oracle"], asset)
                    if fk not in feeds_by_key:
                        feeds_by_key[fk] = self.aave_feeds(r["oracle"], asset)
                    keys.append(fk)
                r["_feeds"] = tuple(keys)
            for side in ("collateral", "debt"):
                if r.get(side):
                    meta = self.token(r[side])
                    r[f"{side}_symbol"] = meta["symbol"]
                    r[f"{side}_decimals"] = meta["decimals"]
        return feeds_by_key

    # -- paso 3: actualizaciones de oráculo -------------------------------------------
    def fetch_oracle_updates(self, feeds_by_key, lookback, end, deadline=None):
        """Índice de actualizaciones por contrato. Se lee hasta `end` o hasta el plazo; la parte
        no leída queda registrada en oracle_cover para no inventar una "última actualización"."""
        addrs = sorted({a for s in feeds_by_key.values() for a in s})
        index = {a: [] for a in addrs}
        parts = [addrs[i:i + 40] for i in range(0, len(addrs), 40)]
        saved = self.deadline
        if deadline is not None:
            self.deadline = min(self.deadline, deadline)

        def one(k, part):
            try:
                logs, got = self._logs(f"oráculos {k + 1}/{len(parts)}", part, [ORACLE_UPDATE_TOPICS], lookback, end)
            except RpcError as e:
                self.errors.append(f"logs de oráculo: {self.rpc.scrub(e)}"[:300])
                return part, [], None
            return part, logs, got
        try:
            with cf.ThreadPoolExecutor(max_workers=max(1, min(3, len(parts)))) as ex:
                results = list(ex.map(lambda kp: one(*kp), enumerate(parts)))
        finally:
            self.deadline = saved
        for part, logs, got in results:
            if got is None:
                for a in part:
                    index.pop(a, None)
                continue
            for a in part:
                self.oracle_cover[a] = got
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
            if self.oracle_cover.get(a, rec["block"]) < rec["block"]:
                return "sin_cobertura"          # no se alcanzó a leer ese tramo del feed
            watched = True
            pos = bisect.bisect_left(lst, (rec["block"], rec["log_index"], ""))
            if pos > 0:
                cand = lst[pos - 1]
                if best is None or cand > best:
                    best = cand
        return best if best else ("sin_ver" if watched else None)

    # -- paso 4: flujos de ETH y pagos a terceros -------------------------------------
    def trace_viable(self, method):
        """Un método de trazas deja de intentarse si ya falló 20 veces sin un solo éxito."""
        if not self.rpc.usable(method):
            return False
        return self.rpc.method_ok(method) > 0 or self.rpc.method_err(method) < 20

    def native_transfers(self, tx, tries=3):
        """Movimientos de ETH nativo dentro de la transacción: [(desde, hacia, wei)] o None si no hay trazas.

        Cada intento recorre los proveedores que sí trazan, del más confiable al menos; varios
        intentos porque hay balanceadores que mezclan nodos con y sin estado viejo."""
        h = tx["hash"]
        for method, n in (("debug_traceTransaction", tries), ("trace_transaction", max(1, tries - 1))):
            for _ in range(n):
                if not self.trace_viable(method):
                    break
                try:
                    res = self.rpc.call(method, sonda.trace_params(method, h))
                except RpcError as e:
                    self._trace_error(method, e)
                    continue
                if method == "debug_traceTransaction" and isinstance(res, dict):
                    return call_frames_transfers(res), method
                if method == "trace_transaction" and isinstance(res, list) and res:
                    return parity_transfers(res), method
                self._trace_error(method, f"resultado inesperado: {str(res)[:60]}")
        if self.blockscout:
            try:
                out = []
                if to_int(tx.get("value") or "0x0") and tx.get("to"):
                    out.append((norm(tx["from"]), norm(tx["to"]), to_int(tx["value"])))
                url = f"{self.blockscout}/api/v2/transactions/{h}/internal-transactions"
                for _ in range(10):
                    data = self.web.get(url)
                    out += blockscout_transfers(data.get("items"))
                    nxt = data.get("next_page_params")
                    if not nxt:
                        return out, "blockscout"
                    q = "&".join(f"{k}={v}" for k, v in nxt.items())
                    url = f"{self.blockscout}/api/v2/transactions/{h}/internal-transactions?{q}"
            except (WebError, AttributeError, ValueError, TypeError, KeyError) as e:
                self._trace_error("blockscout", e)
        return None, "no_medido"

    def _trace_error(self, source, err):
        key = f"{source}: {self.rpc.scrub(err)[:90]}"
        with self.lock:
            self.trace_errors[key] = self.trace_errors.get(key, 0) + 1

    def is_eoa(self, addr):
        with self.lock:
            if addr in self.code_cache:
                return self.code_cache[addr]
        try:
            code = self.rpc.call("eth_getCode", [addr, "latest"])
            eoa = code in ("0x", "0x0", "", None)
        except RpcError:
            eoa = False
        with self.lock:
            self.code_cache[addr] = eoa
        return eoa

    def realized(self, tx, rc, group, native, gas_wei, eth_usd, ts):
        """Lo que el liquidador realmente se quedó en la transacción, en USD.

        Suma todos los movimientos de tokens (logs Transfer/Deposit/Withdrawal) y de ETH
        (trazas) que entran o salen del conjunto W = {EOA firmante, contrato liquidador,
        beneficiarios EOA que solo reciben}, valuados a precio de mercado, menos el gas.
        Así quedan descontados la venta del colateral, comisiones de flash loan, pujas a
        subastas de oráculo (OEV) y pagos al builder, sin modelar cada uno.
        """
        weth = norm(self.chain.weth)
        coinbase = self.header(group[0]["block"])["miner"]
        flows = token_flows(rc, weth)
        nat = [("ETH", f, t, v) for f, t, v in (native or [])]
        s0 = {norm(tx["from"])} | {r["liquidator"] for r in group}
        senders = {f for _, f, _, _ in flows + nat}
        tx_to = norm(tx.get("to") or ZERO)
        cands = {t for _, f, t, _ in flows + nat if f in s0 and t not in s0}
        cands -= {ZERO, coinbase, weth, tx_to}
        benef = {a for a in cands if a not in senders and self.is_eoa(a)}
        w = s0 | benef
        net = {}
        out_eth, in_eth = {}, {}
        for tok, f, t, v in flows + nat:
            if f in w and t not in w:
                net[tok] = net.get(tok, 0) - v
                if tok == "ETH" and t != weth:
                    out_eth[t] = out_eth.get(t, 0) + v
            elif t in w and f not in w:
                net[tok] = net.get(tok, 0) + v
                if tok == "ETH":
                    in_eth[f] = in_eth.get(f, 0) + v
        third_wei = sum(max(0, v - in_eth.get(a, 0)) for a, v in out_eth.items())
        usd, unpriced = 0.0, []
        tokens = [t for t, v in net.items() if v and t not in ("ETH", weth)]
        prices = self.prices.llama_many([f"{self.chain.llama}:{t}" for t in tokens], ts) if tokens else {}
        for tok, v in net.items():
            if not v:
                continue
            if tok in ("ETH", weth):
                if eth_usd is None:
                    unpriced.append("ETH")
                    continue
                usd += v / 1e18 * eth_usd
                continue
            meta = self.token(tok)
            p = prices.get(f"{self.chain.llama}:{tok}")
            if p is None or meta["decimals"] is None:
                unpriced.append(meta["symbol"])
                continue
            usd += v / 10 ** meta["decimals"] * p
        if eth_usd is not None:
            usd -= gas_wei / 1e18 * eth_usd
        return {
            "realized_usd": usd if eth_usd is not None else None,
            "realized_complete": native is not None and not unpriced and eth_usd is not None,
            "third_party_eth": third_wei / 1e18 if native is not None else None,
            "beneficiaries": len(benef),
            "unpriced": unpriced,
        }

    # -- paso 5: enriquecimiento por transacción --------------------------------------
    def enrich_tx(self, group, feeds_by_key, tries=3):
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
        native, native_src = self.native_transfers(tx, tries=tries)
        if self.chain.builder_market:
            if native is None:
                direct_wei, direct_src = None, "no_medido"
            else:
                weth = norm(self.chain.weth)
                direct_wei = sum(v for f, t, v in native if t == hd["miner"])
                direct_wei += sum(v for tok, f, t, v in token_flows(rc, weth) if tok == weth and t == hd["miner"])
                direct_src = native_src
        else:
            direct_wei, direct_src = 0, "no_aplica_l2"
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

        try:
            real = self.realized(tx, rc, group, native, gas_wei, eth_usd, hd["timestamp"])
        except (RpcError, ValueError, KeyError, TypeError) as e:
            real = {"realized_usd": None, "realized_complete": False, "third_party_eth": None,
                    "beneficiaries": 0, "unpriced": [], "realized_error": str(e)[:200]}

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
            r["native_source"] = native_src
            r["eth_usd"] = eth_usd
            r["eth_price_source"] = eth_src
            r["realized_complete"] = real["realized_complete"]
            r["beneficiaries"] = real["beneficiaries"]
            if real["unpriced"]:
                r["unpriced_tokens"] = ",".join(real["unpriced"])[:120]
            if real["realized_usd"] is not None:
                r["realized_usd"] = real["realized_usd"] * wgt
            if real["third_party_eth"] is not None:
                r["third_party_eth"] = real["third_party_eth"] * wgt
            if eth_usd:
                r["gas_usd"] = r["gas_eth"] * eth_usd
                builder_eth = r["priority_eth"] + (r["direct_eth"] or 0)
                r["builder_usd"] = builder_eth * eth_usd
                if r.get("third_party_eth") is not None:
                    r["third_party_usd"] = r["third_party_eth"] * eth_usd
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
    def _phase(self, name, t):
        self.phases[name] = round(time.monotonic() - t, 1)
        log(f"{self.chain.key}: fase {name}: {self.phases[name]} s")

    def probe(self, win):
        """Sonda de proveedores y fuentes web; ajusta el enrutamiento antes de recolectar."""
        aave = self.chain.aave[0] if self.chain.aave else None
        plan = {
            "end": win["end_block"],
            "max_span": win["end_block"] - win["lookback_block"] + 1,
            "log_address": [norm(m.pool) for m in self.chain.aave] if aave else self.chain.morpho,
            "log_topics": [AAVE_LIQUIDATION_TOPIC] if aave else [MORPHO_LIQUIDATE_TOPIC],
            "archive_call": (aave.oracle, SEL["getAssetPrice"] + encode_address(self.chain.weth),
                             win["lookback_block"]) if aave else None,
            "old_tx": sonda.sample_tx(self.rpc, win["start_block"]),
            "new_tx": sonda.sample_tx(self.rpc, max(win["start_block"], win["end_block"] - 20)),
        }
        self.sonda = sonda.run(self.rpc, plan)
        for line in sonda.summary_lines(self.sonda):
            log(f"{self.chain.key}: sonda: {line}")
        if aave and not any(r.get("archivo") for r in self.sonda):
            self.prices.archive_disabled = True
            log(f"{self.chain.key}: ningún proveedor tiene estado viejo: precios de DefiLlama")
        if self.blockscout:
            t = time.monotonic()
            try:
                self.web.get(f"{self.blockscout}/api/v2/transactions/{plan['old_tx'] or ZERO}/internal-transactions")
                self.web_sources["blockscout"] = {"ok": True, "ms": round(1000 * (time.monotonic() - t))}
            except WebError as e:
                self.web_sources["blockscout"] = {"ok": False, "error": str(e)[:120]}
                self.blockscout = ""
        p = self.prices.llama("coingecko:ethereum", win["end_ts"] - 3600)
        self.web_sources["defillama"] = {"ok": p is not None}
        log(f"{self.chain.key}: fuentes web: {json.dumps(self.web_sources)}")

    def enrich(self, groups, feeds, hashes=None, workers=None, tries=3, label="enriquecidas", first=True):
        hashes = list(groups) if hashes is None else list(hashes)
        if not hashes:
            return
        ex = cf.ThreadPoolExecutor(max_workers=workers or self.workers)
        futs = {ex.submit(self.enrich_tx, groups[h], feeds, tries): h for h in hashes}
        pending, done, last_log = set(futs), 0, time.monotonic()
        try:
            while pending:
                finished, pending = cf.wait(pending, timeout=15, return_when=cf.FIRST_COMPLETED)
                for fut in finished:
                    h = futs[fut]
                    done += 1
                    try:
                        fut.result()
                    except cf.CancelledError:
                        if first:
                            for r in groups[h]:
                                r["error"] = "sin enriquecer: presupuesto de tiempo agotado"
                    except Exception as e:  # noqa: BLE001 - una transacción rara no debe tumbar el census
                        if first:
                            for r in groups[h]:
                                r["error"] = self.rpc.scrub(f"enriquecimiento: {type(e).__name__}: {e}")[:300]
                now = time.monotonic()
                if now - last_log >= 60:
                    last_log = now
                    log(f"{self.chain.key}: {done}/{len(hashes)} transacciones {label}, "
                        f"{self.rpc.calls:,} llamadas RPC, {self.web.calls:,} web")
                if now > self.deadline and not self.budget_hit:
                    self.budget_hit = True
                    log(f"{self.chain.key}: presupuesto de tiempo agotado; el resto queda sin enriquecer")
                    for f in pending:
                        f.cancel()
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        log(f"{self.chain.key}: {done}/{len(hashes)} transacciones {label}")

    def retry_traces(self, groups, feeds):
        """Segunda pasada, con menos concurrencia, para las transacciones que quedaron sin trazas."""
        pending = [h for h, g in groups.items() if g[0].get("enriched") and g[0].get("native_source") == "no_medido"]
        self.second_pass = {"intentadas": len(pending)}
        if not pending:
            return
        if self.deadline - time.monotonic() < 120:
            self.second_pass["omitida"] = "sin tiempo"
            return
        if not self.blockscout and not any(self.trace_viable(m) for m in sonda.TRACE_METHODS):
            self.second_pass["omitida"] = "ninguna fuente de trazas funciona"
            return
        log(f"{self.chain.key}: segunda pasada de trazas para {len(pending)} transacciones")
        self.enrich(groups, feeds, hashes=pending, workers=2, tries=5, label="reintentadas", first=False)
        self.second_pass["recuperadas"] = sum(1 for h in pending if groups[h][0].get("native_source") != "no_medido")

    def run(self, days, out_dir, end_block=None, start_ts=None, end_ts=None, tramo=None):
        t0 = time.time()
        recs, groups, win = [], {}, None
        try:
            t = time.monotonic()
            self.rpc.check_chain()
            win = self.resolve_window(days, end_block, start_ts, end_ts)
            log(f"{self.chain.key}: ventana bloques {win['start_block']}..{win['end_block']} ({win['days']:g} días), "
                f"{len(self.rpc.urls)} proveedores responden")
            self._phase("ventana", t)
            t = time.monotonic()
            self.probe(win)
            self._phase("sonda", t)
            t = time.monotonic()
            recs = self.fetch_liquidations(win["start_block"], win["end_block"])
            self._phase("eventos", t)
            t = time.monotonic()
            feeds = self.attach_metadata(recs)
            self._phase("metadatos", t)
            t = time.monotonic()
            # Los oráculos no pueden comerse el tiempo del enriquecimiento: a lo más 35% de lo que queda.
            self.fetch_oracle_updates(feeds, win["lookback_block"], win["end_block"],
                                      deadline=t + 0.35 * max(0.0, self.deadline - t))
            self._phase("oraculos", t)
            for r in recs:
                if "error" not in r:
                    groups.setdefault(r["tx_hash"], []).append(r)
            t = time.monotonic()
            self.enrich(groups, feeds)
            self._phase("enriquecimiento", t)
            t = time.monotonic()
            self.retry_traces(groups, feeds)
            self._phase("segunda_pasada", t)
        except KeyboardInterrupt:
            self.interrupted = True
            log(f"{self.chain.key}: interrumpido; se guarda lo que haya")
        except Exception as e:  # noqa: BLE001 - se guarda lo recolectado y se reporta el fallo
            self.fatal = self.rpc.scrub(f"{type(e).__name__}: {e}")[:300]
            log(f"{self.chain.key}: falla: {self.fatal}")
            log(self.rpc.scrub(traceback.format_exc()))
        return self.write(out_dir, recs, groups, win, t0, tramo)

    def write(self, out_dir, recs, groups, win, t0, tramo=None):
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "liquidaciones.jsonl"), "w") as fh:
            for r in recs:
                for _ in range(5):
                    try:
                        row = dict(r)       # copia: un hilo cancelado todavía puede estar escribiendo
                        break
                    except RuntimeError:
                        time.sleep(0.05)
                row.pop("_feeds", None)
                row.setdefault("enriched", False)
                fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        native = {}
        for g in groups.values():
            k = g[0].get("native_source", "sin_enriquecer")
            native[k] = native.get(k, 0) + 1
        oracle_status = {}
        for r in recs:
            if r.get("oracle_status"):
                oracle_status[r["oracle_status"]] = oracle_status.get(r["oracle_status"], 0) + 1
        meta = {
            "chain": self.chain.key,
            "protocols": list(self.protocols),
            "tramo": tramo,
            "window": win,
            "events_cover_block": self.events_cover,
            "events_complete": bool(win) and self.events_cover == win["end_block"],
            "events": len(recs),
            "transactions": len(groups),
            "enriched": sum(1 for r in recs if r.get("enriched")),
            "with_bonus_usd": sum(1 for r in recs if r.get("bonus_usd") is not None),
            "price_sources": self.prices.stats,
            "archive_disabled": self.prices.archive_disabled,
            "native_trace_sources": native,
            "trace_errors": dict(sorted(self.trace_errors.items(), key=lambda kv: -kv[1])[:20]),
            "second_pass": self.second_pass,
            "with_realized": sum(1 for r in recs if r.get("realized_usd") is not None),
            "with_realized_complete": sum(1 for r in recs if r.get("realized_complete")),
            "oracle_contracts_watched": len(self.updates),
            "oracle_status": oracle_status,
            "with_oracle_delta": sum(1 for r in recs if r.get("blocks_since_oracle") is not None),
            "time_budget_hit": self.budget_hit,
            "interrupted": self.interrupted,
            "fatal_error": self.fatal,
            "phases_s": self.phases,
            "sonda": self.sonda,
            "web_sources": self.web_sources,
            "rpc_calls": self.rpc.calls,
            "rpc_providers": self.rpc.report(),
            "web_calls": self.web.calls,
            "errors_sample": [self.rpc.scrub(e)[:300] for e in
                              (self.errors[:50] + [r["error"] for r in recs if r.get("error")][:50])],
            "elapsed_s": round(time.time() - t0, 1),
        }
        with open(os.path.join(out_dir, "meta.json"), "w") as fh:
            json.dump(meta, fh, indent=2, sort_keys=True, default=str)
        log(f"{self.chain.key}: listo — {meta['events']} eventos, {meta['enriched']} enriquecidos, "
            f"{meta['rpc_calls']} llamadas RPC, {meta['elapsed_s']} s")
        return meta
