"""Shadow Base/Morpho en vivo. Solo lectura: no firma, no envía, no usa fondos.

Responde con la cadena real la pregunta de la fase Shadow del Omega (cap. 5): ¿llegaríamos a
tiempo y con margen? Cada bloque nuevo de Base:

  1. aplica los eventos de Morpho (Borrow, Repay, SupplyCollateral, WithdrawCollateral,
     Liquidate) a un libro de posiciones;
  2. lee el estado y el precio del oráculo de cada mercado vigilado en ese mismo bloque;
  3. detecta las posiciones que acaban de volverse liquidables (el "cruce") y, para cada una,
     simula la decisión GO / NO-GO / OBSERVAR (economía + crítico independiente);
  4. cuando alguien liquida de verdad, la compara con la decisión: cuántos bloques después del
     cruce, quién, por subasta o directa, cuánto pagó de gas y de propina;
  5. mide la latencia: cuánto después del timestamp del bloque lo vimos y cuánto tardamos en decidir.

Nada de esto prueba que se pueda ganar dinero: mide el margen de tiempo y de bono que hubo.
"""

import json
import math
import os
import statistics
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from . import morpho as mo
from .abi import norm
from .config import (CHAINS, KNOWN_SHARED_ENTRIES, SEL, SHADOW_BASE_MARKETS, SHADOW_BASE_USDC, SHADOW_PRIOR_GAS_USD,
                     SHADOW_PRIOR_KEPT_ALL, SHADOW_PRIORS_SOURCE)
from .keccak import keccak256
from .rpc import BudgetExceeded, CallReverted, Rpc, RpcError
from .sonda import raw_call

DEFAULTS = {
    "min_bonus_usd": 10.0,          # por debajo, NO-GO (bono_bajo)
    "min_net_usd": 5.0,             # neto del modelo por debajo, NO-GO (neto_bajo)
    "submit_ms": 150,               # supuesto: del servidor al secuenciador (no se mide aquí)
    "expire_blocks": 900,           # una candidata sin liquidar tras tanto tiempo se da por expirada (30 min)
    "max_age_s": 30.0,              # crítico: datos del bloque más viejos que esto no sirven
    "price_jump": 0.30,             # crítico: salto de precio entre bloques que se considera anómalo
    "near_band": 0.02,              # "cerca del umbral": salud entre 1.00 y 1.02
    "accrual_band": 0.005,          # dentro de esta banda se calcula el interés acumulado con el IRM
    "reconcile_s": 45.0,            # cada cuánto se compara el libro con la cadena
    "reconcile_batch": 400,
    "snapshot_s": 300.0,            # cada cuánto se guarda la foto de las más cercanas al umbral
    "near_top": 30,
    "max_catchup": 15,              # más bloques de atraso que esto: se salta (se anota y se resincroniza)
    "block_time_s": 2.0,
    "read_batch": 400,             # posiciones por multicall (cada una cuesta ~7k de gas: de sobra dentro del tope de eth_call)
    "read_workers": 4,             # lecturas de posiciones en paralelo (el límite de llamadas por segundo del cliente manda)
    "max_gap_blocks": 20000,       # un hueco mayor que esto (11 h) ya no se cubre con eventos: se vuelve a leer todo el libro
    "lost_retries": 10,            # intentos de recuperar los eventos de un bloque perdido antes de rendirse
    "lookback_days": 30,            # cuánto atrás se buscan prestatarios al armar el libro por primera vez
    "book_budget_s": 1200.0,
    "auction_prior_bonus": 0.90,    # mercado cuyo bono fue >= 90% subasta en el censo ...
    "auction_prior_direct_usd": 500.0,   # ... y con < $500 de bono directo en 30 días: NO-GO de mercado
    "prior_min_n": 30,              # mínimo de liquidaciones directas para usar la retención propia del mercado
    "retry_blocks": 25,
    "rate_ttl_s": 30.0,             # cuánto se reutiliza el tipo de interés del IRM mientras el mercado no cambie
    "bloom_sample": 40,             # aun si el bloom dice "sin logs", se piden los de 1 de cada tantos bloques para comprobarlo
}
AUCTION_ENTRIES = {a for c, a in KNOWN_SHARED_ENTRIES if c == "base"}
CACHE_VERSION = 1


def log(msg):
    try:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)
    except OSError:
        pass


def quantiles(xs, qs=(0.5, 0.9, 0.99)):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return {f"p{int(q * 100)}": None for q in qs} | {"min": None, "max": None, "n": 0}
    out = {f"p{int(q * 100)}": xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))] for q in qs}
    return out | {"min": xs[0], "max": xs[-1], "n": len(xs)}


def bloom_bits(data):
    """Las 3 posiciones (0..2047) que un valor activa en el bloom de logs de Ethereum (yellow paper, M3:2048)."""
    h = keccak256(data)
    return tuple(((h[i] << 8) | h[i + 1]) & 2047 for i in (0, 2, 4))


def bloom_has(bloom, bits):
    """`bloom`: los 256 bytes del campo logsBloom. El bit 0 es el menos significativo del último byte."""
    return all(bloom[255 - (b >> 3)] & (1 << (b & 7)) for b in bits)


class LogBloom:
    """¿Puede un bloque tener logs de Morpho que nos interesen? El bloom del bloque contiene la dirección y todos los
    topics de todos sus logs: un "no" es seguro (no hace falta pedir logs); un "sí" hay que confirmarlo con getLogs."""

    def __init__(self, address, topic0s, ids):
        self.address = bloom_bits(bytes.fromhex(address[2:]))
        self.topics = [bloom_bits(bytes.fromhex(t[2:])) for t in topic0s]
        self.ids = [bloom_bits(bytes.fromhex(i[2:])) for i in ids]

    def maybe(self, bloom_hex):
        try:
            raw = bytes.fromhex(bloom_hex[2:])
        except (TypeError, ValueError):
            return True
        if len(raw) != 256:
            return True
        return (bloom_has(raw, self.address) and any(bloom_has(raw, t) for t in self.topics)
                and any(bloom_has(raw, i) for i in self.ids))


class Out:
    """Archivos JSONL de solo agregar: sobreviven a una cancelación a medias."""

    def __init__(self, directory):
        self.dir = directory
        os.makedirs(directory, exist_ok=True)

    def write(self, name, row):
        # Se abre y se cierra en cada línea: unas pocas por bloque, y nada queda a medias si el job se cancela.
        with open(os.path.join(self.dir, name), "a") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    def json(self, name, obj):
        tmp = os.path.join(self.dir, name + ".tmp")
        with open(tmp, "w") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True, default=str)
        os.replace(tmp, os.path.join(self.dir, name))

    def close(self):
        pass


class Pos:
    __slots__ = ("borrow_shares", "collateral", "synced")

    def __init__(self, borrow_shares=0, collateral=0, synced=-1):
        self.borrow_shares, self.collateral, self.synced = borrow_shares, collateral, synced


class Book:
    """Posiciones por eventos. Cada una guarda hasta qué bloque su estado ya está al día (`synced`):
    los eventos de bloques anteriores a ese ya están dentro de la lectura directa y se ignoran."""

    def __init__(self):
        self.pos = {}
        self.by_market = defaultdict(dict)       # mercado -> {usuario: Pos} con deuda y sincronizadas
        self.unsynced = set()
        self.drift = 0

    def is_active(self, mid, user):
        p = self.pos.get((mid, user))
        return bool(p and p.synced >= 0 and p.borrow_shares > 0)

    def _index(self, mid, user, p):
        if p.synced >= 0 and p.borrow_shares > 0:
            self.by_market[mid][user] = p
        else:
            self.by_market[mid].pop(user, None)

    def set_state(self, mid, user, borrow_shares, collateral, block):
        p = self.pos.get((mid, user))
        if p is None:
            p = self.pos[(mid, user)] = Pos()
        p.borrow_shares, p.collateral, p.synced = borrow_shares, collateral, block
        self.unsynced.discard((mid, user))
        self._index(mid, user, p)

    def apply(self, ev):
        key = (ev["market"], ev["user"])
        p = self.pos.get(key)
        if p is None:
            p = self.pos[key] = Pos()
        if p.synced < 0:
            self.unsynced.add(key)
            return "sin_sincronizar"
        if ev["block"] <= p.synced:
            return "ya_incluido"
        nb, nc = p.borrow_shares + ev["d_shares"], p.collateral + ev["d_collateral"]
        if nb < 0 or nc < 0:                      # el libro no puede estar bien: se vuelve a leer
            self.drift += 1
            p.synced = -1
            self.unsynced.add(key)
            self._index(key[0], key[1], p)
            return "deriva"
        p.borrow_shares, p.collateral = nb, nc
        self._index(key[0], key[1], p)
        return "ok"

    def active_count(self):
        return sum(len(v) for v in self.by_market.values())


class MarketInfo:
    __slots__ = ("id", "label", "params", "loan_dec", "coll_dec", "prior", "loan_usd", "lif")

    def __init__(self, id, label, params, loan_dec, coll_dec, prior):
        self.id, self.label, self.params, self.loan_dec, self.coll_dec, self.prior = id, label, params, loan_dec, coll_dec, prior
        self.loan_usd = 1.0                      # solo se vigilan mercados con préstamo en USDC
        self.lif = mo.lif(params.lltv)


class Shadow:
    def __init__(self, rpc, out_dir, cfg=None, markets=None, wall=time.time, mono=time.monotonic):
        self.rpc = rpc
        self.cfg = {**DEFAULTS, **(cfg or {})}
        self.out = Out(out_dir)
        self.wall, self.mono = wall, mono
        chain = CHAINS["base"]
        self.morpho = norm(chain.morpho)
        self.aave_oracle = norm(chain.aave[0].oracle)
        self.weth = norm(chain.weth)
        self.cfg_markets = list(markets if markets is not None else SHADOW_BASE_MARKETS)
        self.markets = {}
        self.excluded = {}
        self.book = Book()
        self.pending = {}                        # (mercado, usuario) -> candidata abierta
        self.expired = set()
        self.last_block = None
        self.hashes = {}
        self.prev_price = {}
        self.last_near = {}                      # (mercado, usuario) -> salud, de las que están cerca del umbral
        self.last_near_prev = {}
        self.near_list = []
        self.cands, self.scanned_to = {}, {}
        self.multicall_ok = True
        self.multicall_proved = False
        self.stop = False
        self.lost = {}                           # bloque perdido -> intentos de recuperar sus eventos
        self.rate_cache = {}
        self.bloom = None                        # LogBloom, tras setup()
        self.bloom_ok = False                    # solo se usa para saltarse getLogs si se comprobó con bloques reales
        self.first_eval_block = None             # primer bloque evaluado tras un hueco: sus cruces son inciertos
        self.uncertain_keys = set()              # ya eran liquidables cuando arrancó el libro: su hora de cruce no se conoce
        self._pool = None
        self.t_lost = self.mono()
        self.logs_by_hash, self.hash_fail_streak = True, 0
        self.eth_usd_cache = (0.0, None)
        self.t_reconcile = self.mono()
        self.t_snapshot = self.mono()
        self.reconcile_at = 0
        self.lat_visto, self.lat_proc, self.lat_total = [], [], []
        self.counts = defaultdict(int)
        self.decisions = defaultdict(int)
        self.outcomes = defaultdict(int)
        self.meta = {"inicio": self.wall(), "supuestos": {
            "submit_ms": self.cfg["submit_ms"], "priors": SHADOW_PRIORS_SOURCE, "kept_prior_global": SHADOW_PRIOR_KEPT_ALL,
            "interes": "se acumula con el IRM solo para posiciones a menos de %.1f%% del umbral" % (100 * self.cfg["accrual_band"]),
            "latencia": "visto_ms = hora en que llegó la respuesta del primer proveedor que ya tenía el bloque - timestamp del "
                        "bloque (segundos enteros: ±1 s); incluye el intervalo de sondeo"}}
        self.libro_parcial = False

    # -- lecturas ---------------------------------------------------------------------------
    @staticmethod
    def tag(block):
        return block if isinstance(block, str) else hex(block)

    def _single(self, target, data, block, prefer=None, recent=True):
        try:
            res = self.rpc.eth_call(target, data, self.tag(block), recent=recent, prefer=prefer)
        except CallReverted:
            return False, b""
        return True, bytes.fromhex(res[2:]) if res and res != "0x" else b""

    def mcall(self, calls, block, prefer=None, recent=True):
        """calls: [(destino, calldata)] -> [(éxito, bytes)] leídos en el mismo bloque."""
        if not calls:
            return []
        if self.multicall_ok:
            try:
                data = mo.encode_aggregate3([(t, True, d) for t, d in calls])
                res = self.rpc.call("eth_call", [{"to": mo.MULTICALL3, "data": data}, self.tag(block)],
                                    recent=recent, prefer=prefer)
                out = mo.decode_aggregate3(res)
                if len(out) != len(calls):
                    raise ValueError("multicall devolvió otra cantidad de resultados")
                return out
            except (RpcError, ValueError) as e:
                self.counts["multicall_fallos"] += 1
                if not self.multicall_proved and self.counts["multicall_fallos"] >= 3:
                    self.multicall_ok = False
                    log(f"shadow: multicall deshabilitado tras 3 fallos ({self.rpc.scrub(e)[:120]}); se leen llamadas sueltas")
        return [self._single(t, d, block, prefer, recent) for t, d in calls]

    def prove_multicall(self):
        """Comprueba que Multicall3 responde igual que las llamadas sueltas; si no, no se usa."""
        mid = self.cfg_markets[0]["id"]
        try:
            solo = self.rpc.eth_call(self.morpho, mo.call_params(mid), "latest")
            res = mo.decode_aggregate3(self.rpc.call("eth_call", [{"to": mo.MULTICALL3, "data": mo.encode_aggregate3(
                [(self.morpho, True, mo.call_params(mid)), (mo.MULTICALL3, True, mo.SEL_BLOCK_NUMBER)])}, "latest"]))
            same = res[0][0] and res[0][1].hex() == solo[2:]
            head = self.rpc.block_number()
            near = res[1][0] and abs(mo.decode_uint(res[1][1]) - head) <= 5
        except (RpcError, ValueError, IndexError) as e:
            same = near = False
            log(f"shadow: prueba de multicall falló: {self.rpc.scrub(e)[:120]}")
        self.multicall_ok = bool(same and near)
        self.multicall_proved = self.multicall_ok
        self.meta["multicall"] = {"ok": self.multicall_ok, "igual_que_llamadas_sueltas": bool(same), "bloque_coincide": bool(near)}
        log(f"shadow: multicall {'verificado' if self.multicall_ok else 'NO disponible: se usan llamadas sueltas'}")

    def read_positions(self, pairs, block, recent=True):
        """{(mercado, usuario): (shares de deuda, colateral)} leído en `block`."""
        step = self.cfg["read_batch"]
        chunks = [pairs[i:i + step] for i in range(0, len(pairs), step)]

        def one(chunk):
            res = self.mcall([(self.morpho, mo.call_position(m, u)) for m, u in chunk], block, recent=recent)
            got = {}
            for key, (ok, data) in zip(chunk, res):
                if ok:
                    try:
                        _, bs, coll = mo.decode_position(data)
                        got[key] = (bs, coll)
                    except ValueError:
                        pass
            return got
        out = {}
        if len(chunks) > 2 and self.cfg["read_workers"] > 1:
            with ThreadPoolExecutor(max_workers=self.cfg["read_workers"]) as ex:
                for got in ex.map(one, chunks):
                    out.update(got)
        else:
            for chunk in chunks:
                out.update(one(chunk))
        return out

    def _executor(self):
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=2)
        return self._pool

    def eth_usd(self):
        t, v = self.eth_usd_cache
        if v is not None and self.mono() - t < 60:
            return v
        try:
            ok, data = self._single(self.aave_oracle, SEL["getAssetPrice"] + "0" * 24 + self.weth[2:], "latest")
            if ok:
                v = mo.decode_uint(data) / 1e8
        except (RpcError, ValueError):
            pass
        self.eth_usd_cache = (self.mono(), v if v else (self.eth_usd_cache[1] or 2500.0))
        return self.eth_usd_cache[1]

    # -- arranque ----------------------------------------------------------------------------
    def setup(self):
        self.rpc.check_chain()
        self.prove_multicall()
        ids = [m["id"] for m in self.cfg_markets]
        res = self.mcall([(self.morpho, mo.call_params(i)) for i in ids], "latest")
        params = {}
        for i, (ok, data) in zip(ids, res):
            try:
                params[i] = mo.decode_params(data) if ok else None
            except ValueError:
                params[i] = None
        tokens = sorted({a for p in params.values() if p for a in (p.loan, p.collateral)})
        dec = {}
        for tok, (ok, data) in zip(tokens, self.mcall([(t, mo.SEL_DECIMALS) for t in tokens], "latest")):
            if ok and len(data) == 32:
                dec[tok] = mo.decode_uint(data)
        for m in self.cfg_markets:
            p = params.get(m["id"])
            if p is None or p.lltv == 0:
                self.excluded[m["id"]] = "mercado no existe"
            elif p.loan != norm(SHADOW_BASE_USDC):
                self.excluded[m["id"]] = "el préstamo no es USDC"
            elif p.oracle == mo.ZERO or p.loan not in dec or p.collateral not in dec:
                self.excluded[m["id"]] = "sin oráculo o sin decimales"
            else:
                self.markets[m["id"]] = MarketInfo(m["id"], m["label"], p, dec[p.loan], dec[p.collateral], m)
        self.ids = list(self.markets)
        self.bloom = LogBloom(self.morpho, mo.BOOK_EVENTS, self.ids)
        self.meta["mercados"] = {i: {"label": m.label, "lltv": m.params.lltv, "oraculo": m.params.oracle, "irm": m.params.irm}
                                 for i, m in self.markets.items()}
        self.meta["mercados_excluidos"] = self.excluded
        log(f"shadow: {len(self.markets)} mercados vigilados, {len(self.excluded)} excluidos")
        return self

    def prove_bloom(self, head, event_blocks):
        """Comprueba con bloques reales que el bloom no descarta ningún bloque con eventos nuestros. Solo si pasa
        (y hay suficientes bloques para saberlo) se deja de pedir los logs de los bloques que el bloom descarta."""
        blocks = sorted(set(event_blocks))[-12:]
        if len(blocks) < 3:
            try:
                recent = self.rpc.call("eth_getLogs", [{"fromBlock": hex(max(1, head - 20000)), "toBlock": hex(head),
                                                        "address": self.morpho, "topics": [mo.BOOK_EVENTS, self.ids]}])
                blocks = sorted({int(lg["blockNumber"], 16) for lg in recent if not lg.get("removed")})[-12:]
            except RpcError as e:
                log(f"shadow: no se pudo probar el bloom: {self.rpc.scrub(e)[:100]}")
                blocks = []
        bad, seen = 0, 0
        for b in blocks:
            try:
                hdr = self._header(b, None)
            except RpcError:
                continue
            seen += 1
            if not (hdr["bloom"] and self.bloom.maybe(hdr["bloom"])):
                bad += 1
        self.bloom_ok = seen >= 3 and bad == 0
        self.meta["bloom"] = {"ok": self.bloom_ok, "bloques_con_eventos": seen, "descartados_por_error": bad}
        log(f"shadow: bloom {'verificado' if self.bloom_ok else 'NO verificado'} con {seen} bloques con eventos"
            + (f" ({bad} descartados por error)" if bad else ""))

    def bootstrap(self, head, cache=None, deadline=None):
        """Arma el libro: busca prestatarios en los eventos y lee su posición exacta en `head`."""
        lookback = int(self.cfg["lookback_days"] * 86400 / self.cfg["block_time_s"])
        cache_markets = (cache or {}).get("markets", {}) if (cache or {}).get("version") == CACHE_VERSION \
            and norm((cache or {}).get("morpho", "0x0")) == self.morpho else {}
        cands = defaultdict(set)
        starts = defaultdict(list)
        event_blocks = []
        for mid in self.ids:
            c = cache_markets.get(mid)
            if c:
                cands[mid].update(c.get("candidates", []))
                starts[max(c["scanned_to"] + 1, head - lookback)].append(mid)
            else:
                starts[max(1, head - lookback)].append(mid)
        self.scanned_to = {mid: head for mid in self.ids}
        t0 = self.mono()
        for start, mids in sorted(starts.items()):
            if start > head:
                continue
            try:
                logs = self.rpc.get_logs(self.morpho, [[mo.EVENT_TOPICS["Borrow"], mo.EVENT_TOPICS["Liquidate"]], mids],
                                         start, head, on_progress=self._scan_progress(start, head), deadline=deadline)
                last = head
            except BudgetExceeded as e:
                logs, last = e.logs, e.next_block - 1
                self.libro_parcial = True
                log(f"shadow: libro parcial: presupuesto agotado en el bloque {e.next_block}")
            for mid in mids:
                self.scanned_to[mid] = last
            for lg in logs:
                try:
                    ev = mo.decode_event(lg)
                except ValueError:
                    continue
                if ev and not lg.get("removed"):
                    cands[ev["market"]].add(ev["user"])
                    event_blocks.append(ev["block"])
        pairs = [(mid, user) for mid, users in cands.items() for user in sorted(users) if mid in self.markets]
        log(f"shadow: {len(pairs)} prestatarios candidatos; leyendo posiciones en el bloque {head}")
        got = self.read_positions(pairs, head)
        for (mid, user), (bs, coll) in got.items():
            self.book.set_state(mid, user, bs, coll, head)
        self.last_block = head
        snap0 = self._snapshot(head, None)
        for mid, (_, price) in snap0.items():
            self.prev_price[mid] = price                # sin precio previo el crítico no vería un salto en el primer bloque
        try:
            # Lo que ya es liquidable al arrancar no tiene hora de cruce conocida: se anota para no tomarlo por un cruce nuevo.
            self.uncertain_keys = set(self._evaluate(snap0, head, self._header(head, None)["ts"]))
        except RpcError:
            self.first_eval_block = head + 1
        self.cands = cands
        self.prove_bloom(head, event_blocks)
        self.meta["libro"] = {"bloque": head, "candidatos": len(pairs), "leidos": len(got), "con_deuda": self.book.active_count(),
                              "libro_parcial": self.libro_parcial, "segundos": round(self.mono() - t0, 1),
                              "desde_cache": bool(cache_markets), "dias_atras": self.cfg["lookback_days"]}
        log(f"shadow: libro listo: {self.book.active_count()} posiciones con deuda de {len(got)} leídas "
            f"({self.meta['libro']['segundos']} s)")
        return self

    def _scan_progress(self, lo, hi):
        state = {"t": self.mono()}

        def cb(block, n, chunk):
            if self.mono() - state["t"] >= 30:
                state["t"] = self.mono()
                log(f"shadow: libro: bloque {block:,} ({100 * (block - lo + 1) / max(1, hi - lo + 1):.0f}%), {n:,} logs")
        return cb

    def cache_snapshot(self):
        return {"version": CACHE_VERSION, "chain": "base", "morpho": self.morpho, "guardado": int(self.wall()),
                "markets": {mid: {"scanned_to": self.scanned_to.get(mid, self.last_block),
                                  "candidates": sorted(self.cands.get(mid, set()) | {u for (m, u) in self.book.pos if m == mid})}
                            for mid in self.ids}}

    # -- un bloque ---------------------------------------------------------------------------
    def _header(self, n, prefer):
        b = self.rpc.block(n, recent=True, prefer=prefer)
        return {"ts": int(b["timestamp"], 16), "hash": b.get("hash"), "parent": b.get("parentHash"),
                "base_fee": int(b.get("baseFeePerGas") or "0x0", 16), "txs": b.get("transactions") or [],
                "bloom": b.get("logsBloom")}

    def _logs_of_block(self, n, block_hash, prefer):
        """Logs de un bloque. Con el hash del bloque, un proveedor atrasado contesta con error y se prueba otro;
        con solo el número contestaría una lista vacía y se perdería el evento sin que nadie lo note."""
        topics = [mo.BOOK_EVENTS, self.ids]
        if block_hash and self.logs_by_hash:
            try:
                logs = self.rpc.call("eth_getLogs", [{"blockHash": block_hash, "address": self.morpho, "topics": topics}], prefer=prefer)
                self.hash_fail_streak = 0
                return logs
            except RpcError as e:
                self.counts["logs_por_hash_fallidos"] += 1
                self.hash_fail_streak += 1
                if self.hash_fail_streak >= 3:
                    # Si ningún proveedor sirve el filtro por hash, cada bloque perdería un viaje de ida y vuelta de más.
                    self.logs_by_hash = False
                    self.meta["logs_por_hash"] = "desactivado tras 3 fallos seguidos: " + self.rpc.scrub(e)[:100]
                    log(f"shadow: el filtro de logs por hash no funciona ({self.rpc.scrub(e)[:100]}); se piden por número de bloque")
                else:
                    log(f"shadow: logs por hash fallaron en el bloque {n} ({self.rpc.scrub(e)[:100]}); se prueba por número")
        return self.rpc.call("eth_getLogs", [{"fromBlock": hex(n), "toBlock": hex(n), "address": self.morpho, "topics": topics}],
                             prefer=prefer)

    def _events(self, a, b, prefer, block_hash=None):
        logs = self._logs_of_block(a, block_hash, prefer) if a == b else \
            self.rpc.get_logs(self.morpho, [mo.BOOK_EVENTS, self.ids], a, b)
        evs = []
        for lg in logs:
            if lg.get("removed"):
                continue
            try:
                ev = mo.decode_event(lg)
            except ValueError as e:
                self.counts["eventos_malos"] += 1
                log(f"shadow: evento ilegible en {lg.get('transactionHash')}: {e}")
                continue
            if ev:
                evs.append(ev)
        evs.sort(key=lambda e: (e["block"], e["log_index"]))
        return evs

    def _snapshot(self, block, prefer):
        calls = []
        for mid in self.ids:
            calls.append((self.morpho, mo.call_market(mid)))
            calls.append((self.markets[mid].params.oracle, mo.SEL_PRICE))
        res = self.mcall(calls, block, prefer)
        snap = {}
        for i, mid in enumerate(self.ids):
            (ok_m, dm), (ok_p, dp) = res[2 * i], res[2 * i + 1]
            try:
                if ok_m and ok_p:
                    price = mo.decode_uint(dp)
                    if price > 0:
                        snap[mid] = (mo.decode_market(dm), price)
                        continue
            except ValueError:
                pass
            self.counts["lecturas_de_mercado_fallidas"] += 1
        return snap

    def _sync_unsynced(self, n, prefer):
        keys = [k for k in sorted(self.book.unsynced) if k[0] in self.markets]
        if not keys:
            return
        got = self.read_positions(keys, n)
        for key, (bs, coll) in got.items():
            self.book.set_state(key[0], key[1], bs, coll, n)
        self.counts["posiciones_sincronizadas"] += len(got)

    def _rate(self, mid, state, n, ts):
        """Tipo de interés del IRM para estimar el interés acumulado. Solo hace falta cerca del umbral y cambia muy
        despacio, así que se reutiliza mientras el mercado no cambie (una llamada por bloque costaba ~200 ms)."""
        info = self.markets[mid]
        if info.params.irm == mo.ZERO:
            return 0
        key = (state.last_update, state.total_supply_assets, state.total_borrow_assets)
        hit = self.rate_cache.get(mid)
        if hit and hit[0] == key and self.mono() - hit[1] < self.cfg["rate_ttl_s"]:
            return hit[2]
        ok, data = self._single(info.params.irm, mo.call_rate(info.params, state), n)
        try:
            rate = mo.decode_uint(data) if ok else None
        except ValueError:
            rate = None
        if rate is not None:
            self.rate_cache[mid] = (key, self.mono(), rate)
        return rate

    def _evaluate(self, snap, n, ts):
        """{(mercado, usuario): datos} de las posiciones liquidables ahora (con interés acumulado si están al borde)."""
        liq, near, self.last_near = {}, [], {}
        limit = 1 + self.cfg["near_band"] + 1e-6
        for mid, (state, price) in snap.items():
            info = self.markets[mid]
            lltv = info.params.lltv
            # Descarte rápido, en coma flotante, de las claramente sanas (decenas de miles por bloque). El margen de 1e-6
            # cubre de sobra el error de los flotantes (~1e-15): las que quedan cerca se calculan con enteros exactos.
            per_share = (state.total_borrow_assets + mo.VIRTUAL_ASSETS) / (state.total_borrow_shares + mo.VIRTUAL_SHARES)
            cap = price / 1e36 * lltv / 1e18
            edge = []
            for user, p in self.book.by_market.get(mid, {}).items():
                if p.collateral * cap >= p.borrow_shares * per_share * limit:
                    continue
                borrowed = mo.borrowed_assets(p.borrow_shares, state)
                if borrowed == 0:
                    continue
                mb = mo.max_borrow(p.collateral, price, lltv)
                ratio = mb / borrowed
                if mb < borrowed:
                    liq[(mid, user)] = {"ratio": ratio, "state": state, "accrual": False}
                    continue
                if ratio < 1 + self.cfg["accrual_band"]:
                    edge.append((user, p))
                if ratio < 1 + self.cfg["near_band"]:
                    self.last_near[(mid, user)] = ratio
                    near.append((ratio, mid, user, borrowed))
            if edge and ts - state.last_update > 5:
                rate = self._rate(mid, state, n, ts)
                if rate:
                    aged = mo.accrue(state, rate, ts)
                    for user, p in edge:
                        if not mo.is_healthy(p.borrow_shares, p.collateral, price, lltv, aged):
                            liq[(mid, user)] = {"ratio": mo.health_ratio(p.borrow_shares, p.collateral, price, lltv, aged),
                                                "state": aged, "accrual": True}
        near.sort()
        self.near_list = near[:self.cfg["near_top"]]
        return liq

    # -- decisiones --------------------------------------------------------------------------
    def _economics(self, info, pos, price, state):
        q = mo.full_quote(pos.borrow_shares, pos.collateral, price, info.params.lltv, state)
        scale = 10 ** info.loan_dec
        bonus = q["bonus_assets"] / scale * info.loan_usd
        pr = info.prior
        kept = pr.get("kept_dir") if (pr.get("kept_dir") is not None and pr.get("n_dir", 0) >= self.cfg["prior_min_n"]) \
            else SHADOW_PRIOR_KEPT_ALL
        return q, {"bono_usd": bonus, "repago_usd": q["repaid_assets"] / scale * info.loan_usd,
                   "retencion_prior": kept, "neto_modelo_usd": bonus * kept,
                   "deuda_mala": q["bad_debt_shares"] > 0, "deuda_mala_usd": q["bad_debt_assets"] / scale * info.loan_usd}

    def _critic(self, key, pos, snap_price, n, hdr, seen_wall):
        """Verificaciones independientes antes de un GO. Devuelve (ok, razón, detalle)."""
        det = {}
        read = self.read_positions([key], n)
        chain = read.get(key)
        det["paridad_libro"] = bool(chain and chain == (pos.borrow_shares, pos.collateral))
        if chain and not det["paridad_libro"]:
            det["lectura_directa"] = {"deuda_shares": chain[0], "colateral": chain[1]}
            self.book.set_state(key[0], key[1], chain[0], chain[1], n)
            self.counts["deriva_en_critico"] += 1
            return False, "discrepancia_libro", det
        if not chain:
            return False, "sin_lectura_directa", det
        prev = self.prev_price.get(key[0])
        det["salto_precio"] = None if not prev else abs(snap_price - prev) / prev
        if prev and det["salto_precio"] > self.cfg["price_jump"]:
            return False, "oraculo_anomalo", det
        age = (seen_wall or self.wall()) - hdr["ts"]
        det["edad_dato_s"] = round(age, 1)
        if age > self.cfg["max_age_s"]:
            return False, "datos_viejos", det
        return True, "ok", det

    def _decide(self, key, info_ev, snap, hdr, n, seen_wall, seen_mono, prefer, residual, uncertain=False):
        mid, user = key
        info, pos = self.markets[mid], self.book.pos[key]
        state, price = snap[mid]
        state = info_ev["state"]
        q, eco = self._economics(info, pos, price, state)
        pr = info.prior
        visto_ms = None if seen_wall is None else round((seen_wall - hdr["ts"]) * 1000)
        decision, reason, crit = "NO-GO", None, None
        if eco["deuda_mala"]:
            reason = "deuda_mala"
        elif eco["bono_usd"] < self.cfg["min_bonus_usd"]:
            reason = "bono_bajo"
        elif pr.get("auc_bonus", 0) >= self.cfg["auction_prior_bonus"] and pr.get("dir_bonus", 0) < self.cfg["auction_prior_direct_usd"]:
            reason = "mercado_de_subasta"
        elif eco["neto_modelo_usd"] < self.cfg["min_net_usd"]:
            reason = "neto_bajo"
        else:
            ok, why, crit = self._critic(key, pos, price, n, hdr, seen_wall)
            decision, reason = ("GO", "ok") if ok else (("OBSERVAR" if why == "oraculo_anomalo" else "NO-GO"), why)
        decided_ms = None if seen_mono is None else round((self.mono() - seen_mono) * 1000)
        x_ms = None if visto_ms is None or decided_ms is None else visto_ms + decided_ms + self.cfg["submit_ms"]
        k = None if x_ms is None else max(1, math.ceil(x_ms / (self.cfg["block_time_s"] * 1000)))
        cand = {"id": f"{mid[2:10]}-{user[2:10]}-{n}", "key": key, "b_c": n, "ts_c": hdr["ts"], "decision": decision,
                "razon": reason, "bono_usd": eco["bono_usd"], "neto_modelo_usd": eco["neto_modelo_usd"], "price_c": price,
                "visto_ms": visto_ms, "decidido_ms": decided_ms, "x_ms": x_ms, "k": k, "residual": residual,
                "incierto": uncertain}
        row = {"id": cand["id"], "mercado": mid, "etiqueta": info.label, "prestatario": user, "bloque_cruce": n,
               "ts_bloque": hdr["ts"], "decision": decision, "razon": reason, "visto_ms": visto_ms, "decidido_ms": decided_ms,
               "x_ms": x_ms, "bloque_llegada_propia": None if k is None else n + k, "residual_de_liquidacion_parcial": residual,
               "cruce_incierto": uncertain,
               "salud": info_ev["ratio"], "con_interes": info_ev["accrual"],
               "deuda_shares": pos.borrow_shares, "colateral": pos.collateral, "precio": price,
               "embargo": q["seized_assets"], "repago_assets": q["repaid_assets"], "critico": crit,
               "prior": {"retencion": eco["retencion_prior"], "fuente": SHADOW_PRIORS_SOURCE}, **eco}
        self.out.write("decisiones.jsonl", row)
        self.decisions[f"{decision}:{reason}"] += 1
        self.counts["candidatas"] += 1
        self.pending[key] = cand
        return cand

    # -- resultados --------------------------------------------------------------------------
    def _tx_info(self, h, hdr):
        try:
            tx = self.rpc.call("eth_getTransactionByHash", [h])
            rc = self.rpc.call("eth_getTransactionReceipt", [h])
        except RpcError:
            return {}
        if not tx or not rc:
            return {}
        gas_used = int(rc["gasUsed"], 16)
        eff = int(rc.get("effectiveGasPrice") or tx.get("gasPrice") or "0x0", 16)
        l1 = int(rc.get("l1Fee") or "0x0", 16)
        eth = self.eth_usd()
        to = norm(tx.get("to") or mo.ZERO)
        return {"firmante": norm(tx["from"]), "entrada": to, "via": "subasta" if to in AUCTION_ENTRIES else "directa",
                "gas_usd": (gas_used * eff + l1) / 1e18 * eth,
                "propina_usd": max(0, eff - hdr["base_fee"]) * gas_used / 1e18 * eth,
                "propina_gwei": max(0, eff - hdr["base_fee"]) / 1e9, "eth_usd": eth}

    def _resolve_liquidation(self, e, hdr, n, known_before, snap):
        key = (e["market"], e["user"])
        info = self.markets[e["market"]]
        cand = self.pending.pop(key, None)
        was_expired = key in self.expired
        self.expired.discard(key)
        bonus_usd = e["repaid_assets"] * (info.lif - mo.WAD) / mo.WAD / 10 ** info.loan_dec * info.loan_usd
        row = {"mercado": e["market"], "etiqueta": info.label, "prestatario": e["user"], "bloque_liquidacion": n,
               "tx": e["tx_hash"], "tx_index": e["tx_index"], "log_index": e["log_index"], "liquidador": e["caller"],
               "repago_assets": e["repaid_assets"], "embargado": e["seized_assets"], "deuda_mala_shares": e["bad_debt_shares"],
               "bono_usd": bonus_usd, "bono_formula": "repago x (LIF - 1)"}
        if cand:
            delta = n - cand["b_c"]
            row.update(resultado="liquidada", detectada_antes=True, id=cand["id"], bloque_cruce=cand["b_c"], delta_bloques=delta,
                       decision=cand["decision"], razon=cand["razon"], visto_ms=cand["visto_ms"], x_ms=cand["x_ms"],
                       bloque_llegada_propia=None if cand["k"] is None else cand["b_c"] + cand["k"],
                       neto_modelo_usd=cand["neto_modelo_usd"], residual=cand["residual"], cruce_incierto=cand["incierto"])
            if cand["k"] is not None:
                row["llegada"] = "antes" if n > cand["b_c"] + cand["k"] else "empate" if n == cand["b_c"] + cand["k"] else "tarde"
        elif was_expired:
            # Llevaba más de `expire_blocks` liquidable sin que nadie la tomara: no fue una carrera.
            row.update(resultado="liquidada_tras_expirar", detectada_antes=True, clase="tras_expirar", delta_bloques=None, llegada=None)
        else:
            clase = "mismo_bloque" if key in known_before else "fuera_del_libro"
            row.update(resultado="liquidada_sin_aviso", detectada_antes=False, clase=clase, delta_bloques=0 if clase == "mismo_bloque" else None,
                       llegada="tarde" if clase == "mismo_bloque" else None)
            if clase == "mismo_bloque" and key in self.last_near_prev:
                row["salud_bloque_anterior"] = self.last_near_prev[key]
        row.update(self._tx_info(e["tx_hash"], hdr))
        self.out.write("resultados.jsonl", row)
        self.outcomes[row["resultado"] if cand else row["clase"]] += 1
        if cand and cand["decision"] == "GO":
            self.outcomes["GO_liquidada"] += 1

    def _close_pending(self, key, resultado, n, **extra):
        cand = self.pending.pop(key, None)
        if cand is None:
            return
        self.out.write("resultados.jsonl", {"mercado": key[0], "etiqueta": self.markets[key[0]].label, "prestatario": key[1],
                                            "id": cand["id"], "bloque_cruce": cand["b_c"], "bloque_cierre": n, "resultado": resultado,
                                            "duracion_bloques": n - cand["b_c"], "decision": cand["decision"], "razon": cand["razon"],
                                            "bono_usd": cand["bono_usd"], "detectada_antes": True,
                                            "cruce_incierto": cand["incierto"], **extra})
        self.outcomes[resultado] += 1
        if cand["decision"] == "GO":
            self.outcomes[f"GO_{resultado}"] += 1

    # -- bucle principal de un bloque ---------------------------------------------------------
    def process_block(self, n, seen_wall=None, seen_mono=None, prefer=None):
        t0 = self.mono()
        # La lectura del mercado no depende de la cabecera ni de los logs: corre en paralelo con ellos.
        snap_future = self._executor().submit(self._snapshot, n, prefer)
        hdr = self._header(n, prefer)
        t_hdr = self.mono()
        if n - 1 in self.hashes and hdr["parent"] and hdr["parent"] != self.hashes[n - 1]:
            self._reorg(n)
        self.hashes[n] = hdr["hash"]
        self.hashes.pop(n - 80, None)
        no_logs = self.bloom_ok and bool(hdr["bloom"]) and not self.bloom.maybe(hdr["bloom"])
        if no_logs and not (self.cfg["bloom_sample"] and n % self.cfg["bloom_sample"] == 0):
            events = []                           # el bloom del bloque descarta cualquier log nuestro: ni se piden
            self.counts["bloques_sin_logs_por_bloom"] += 1
        else:
            events = self._events(n, n, prefer, hdr["hash"])
            if no_logs and events:                # la muestra de control encontró eventos donde el bloom decía que no había
                self.bloom_ok = False
                self.counts["bloom_falsos_negativos"] += 1
                self.meta["bloom"] = {**self.meta.get("bloom", {}), "ok": False, "falso_negativo_en": n}
                log(f"shadow: el bloom descartó el bloque {n} pero tenía eventos; se vuelve a pedir los logs de todos los bloques")
                self.out.write("eventos_del_sistema.jsonl", {"evento": "bloom_falso_negativo", "bloque": n})
        t_logs = self.mono()
        known_before = {(e["market"], e["user"]) for e in events if e["kind"] == "Liquidate"
                        and self.book.is_active(e["market"], e["user"])}
        touched = {(e["market"], e["user"]) for e in events}
        for e in events:
            if self.book.apply(e) == "deriva":
                self.counts["deriva_por_eventos"] += 1
        self._sync_unsynced(n, prefer)
        snap = snap_future.result()
        t_snap = self.mono()
        self.last_near_prev = dict(self.last_near)
        liq_now = self._evaluate(snap, n, hdr["ts"])
        t_eval = self.mono()
        for e in events:
            if e["kind"] == "Liquidate":
                self._resolve_liquidation(e, hdr, n, known_before, snap)
        liquidated_now = {(e["market"], e["user"]) for e in events if e["kind"] == "Liquidate"}
        after_gap = self.first_eval_block is not None and n >= self.first_eval_block
        for key, ev_info in liq_now.items():
            if key in self.pending or key in self.expired:
                continue
            self._decide(key, ev_info, snap, hdr, n, seen_wall, seen_mono, prefer, residual=key in liquidated_now,
                         uncertain=after_gap or key in self.uncertain_keys)
        if after_gap:
            self.first_eval_block = None
        self.uncertain_keys &= set(liq_now)       # los que dejaron de ser liquidables ya no cuentan: un cruce nuevo sí es cierto
        for key in list(self.pending):
            if key[0] not in snap:
                continue                          # no se pudo leer ese mercado: no se concluye nada
            if key not in liq_now and key not in liquidated_now:
                mid = key[0]
                cause = "precio" if mid in snap and snap[mid][1] > self.pending[key]["price_c"] else \
                    "movimiento_de_la_posicion" if key in touched else "otro"
                self._close_pending(key, "recuperada", n, causa=cause)
            elif n - self.pending[key]["b_c"] >= self.cfg["expire_blocks"]:
                self.expired.add(key)
                self._close_pending(key, "expirada", n)
        self.expired = {k for k in self.expired if k in liq_now}
        for mid, v in snap.items():
            self.prev_price[mid] = v[1]
        self.last_block = n
        self._block_row(n, hdr, seen_wall, t0, t_hdr, t_logs, t_snap, t_eval, len(events), len(liq_now))
        self._periodic(n, snap)
        return {"eventos": len(events), "liquidables": len(liq_now)}

    def _block_row(self, n, hdr, seen_wall, t0, t_hdr, t_logs, t_snap, t_eval, n_events, n_liq):
        total = self.mono() - t0
        visto = None if seen_wall is None else round((seen_wall - hdr["ts"]) * 1000)
        row = {"bloque": n, "ts": hdr["ts"], "visto_ms": visto, "cabecera_ms": round((t_hdr - t0) * 1000),
               "logs_ms": round((t_logs - t_hdr) * 1000), "lectura_ms": round((t_snap - t_logs) * 1000),
               "evaluar_ms": round((t_eval - t_snap) * 1000), "total_ms": round(total * 1000), "eventos": n_events,
               "liquidables": n_liq, "activas": self.book.active_count()}
        self.out.write("bloques.jsonl", row)
        if visto is not None:
            self.lat_visto.append(visto)
            self.lat_total.append(visto + round(total * 1000))
        self.lat_proc.append(round(total * 1000))
        self.counts["bloques"] += 1

    def _reorg(self, n):
        self.counts["reorgs"] += 1
        log(f"shadow: reorg detectado en el bloque {n}: se vuelve a leer el libro")
        self.out.write("eventos_del_sistema.jsonl", {"evento": "reorg", "bloque": n, "pendientes": len(self.pending)})
        for key in list(self.pending):
            self._close_pending(key, "invalidada_por_reorg", n)
        pairs = [k for k in self.book.pos if k[0] in self.markets]
        got = self.read_positions(pairs, n - 1)
        for (mid, user), (bs, coll) in got.items():
            self.book.set_state(mid, user, bs, coll, n - 1)

    def _periodic(self, n, snap):
        now = self.mono()
        if now - self.t_snapshot >= self.cfg["snapshot_s"]:
            self.t_snapshot = now
            self.out.write("cercanas.jsonl", {"bloque": n, "ts": int(self.wall()), "top": [
                {"mercado": mid, "etiqueta": self.markets[mid].label, "prestatario": user, "salud": ratio,
                 "caida_de_precio_pct": round((1 - 1 / ratio) * 100, 3) if ratio else None,
                 "deuda_usd": b / 10 ** self.markets[mid].loan_dec * self.markets[mid].loan_usd}
                for ratio, mid, user, b in self.near_list]})
            self.write_meta()

    def reconcile(self, budget=None):
        """Compara una rebanada del libro con la lectura directa de la cadena y corrige las diferencias."""
        keys = sorted(self.book.pos)
        if not keys:
            return
        step = budget or self.cfg["reconcile_batch"]
        a = self.reconcile_at % len(keys)
        chunk = keys[a:a + step]
        self.reconcile_at = a + len(chunk)
        n = self.last_block
        got = self.read_positions(chunk, n)
        diffs = 0
        for key, (bs, coll) in got.items():
            p = self.book.pos[key]
            if p.synced >= 0 and (p.borrow_shares, p.collateral) != (bs, coll):
                diffs += 1
                self.out.write("eventos_del_sistema.jsonl", {
                    "evento": "deriva_del_libro", "bloque": n, "mercado": key[0], "prestatario": key[1],
                    "libro": [p.borrow_shares, p.collateral], "cadena": [bs, coll]})
            self.book.set_state(key[0], key[1], bs, coll, n)
        self.counts["reconciliadas"] += len(got)
        self.counts["deriva_reconciliacion"] += diffs
        self.t_reconcile = self.mono()

    # -- ciclo --------------------------------------------------------------------------------
    def run(self, minutes, head_source, sleep=time.sleep):
        deadline = self.mono() + minutes * 60
        fails = 0
        while self.mono() < deadline and not self.stop:
            head, wall, mono, url = head_source(self.last_block)
            if head is None or head <= self.last_block:
                if self.lost and self.mono() - self.t_lost >= 5:
                    self._safely(self._recover_lost)
                if self.mono() - self.t_reconcile >= self.cfg["reconcile_s"]:
                    self._safely(self.reconcile)
                continue
            if head - self.last_block > self.cfg["max_catchup"]:
                try:
                    self._catch_up(head - 1)
                except RpcError as e:
                    self.counts["errores_periodicos"] += 1
                    log(f"shadow: no se pudo cubrir el hueco: {self.rpc.scrub(e)[:140]}")
                    sleep(0.5)
                    continue
            for n in range(self.last_block + 1, head + 1):
                last = n == head
                try:
                    self.process_block(n, wall if last else None, mono if last else None, url)
                    fails = 0
                except RpcError as e:
                    fails += 1
                    self.counts["bloques_con_error"] += 1
                    log(f"shadow: error en el bloque {n}: {self.rpc.scrub(e)[:140]}")
                    if fails >= self.cfg["retry_blocks"]:
                        self._skip(n)
                        fails = 0
                    else:
                        sleep(0.3)
                    break
        return self.finish()

    def _safely(self, fn, *a):
        try:
            return fn(*a)
        except RpcError as e:
            self.counts["errores_periodicos"] += 1
            log(f"shadow: {fn.__name__} falló: {self.rpc.scrub(e)[:120]}")

    def _apply_events(self, events, sync_at):
        """Aplica al libro los eventos de varios bloques (en orden) y resuelve las liquidaciones que traen.
        El libro se modifica entero antes de la primera llamada a la red: si algo falla después, reintentar no
        vuelve a aplicar nada."""
        by_block = defaultdict(list)
        for e in events:
            by_block[e["block"]].append(e)
        liquidations = []
        for b in sorted(by_block):
            evs = by_block[b]
            known = {(e["market"], e["user"]) for e in evs if e["kind"] == "Liquidate" and self.book.is_active(e["market"], e["user"])}
            for e in evs:
                if self.book.apply(e) == "deriva":
                    self.counts["deriva_por_eventos"] += 1
            liquidations += [(e, b, known) for e in evs if e["kind"] == "Liquidate"]
        self.counts["eventos_en_hueco"] += len(events)
        return liquidations

    def _resolve_late(self, liquidations):
        headers = {}
        for e, b, known in liquidations:
            if b not in headers:
                try:
                    headers[b] = self._header(b, None)
                except RpcError:
                    headers[b] = {"ts": 0, "hash": None, "parent": None, "base_fee": 0, "txs": [], "perdida": True}
                    self.counts["cabeceras_perdidas"] += 1
            self._resolve_liquidation(e, headers[b], b, known, None)

    def _catch_up(self, upto):
        """Ponerse al día tras un atraso (o tras armar el libro) sin releerlo: los eventos de todo el hueco en una sola
        búsqueda. Lo que se pierde es la hora exacta de los cruces dentro del hueco, y queda anotado."""
        a = self.last_block + 1
        if upto < a:
            return
        gap = upto - a + 1
        self.counts["saltos"] += 1
        self.counts["bloques_saltados"] += gap
        log(f"shadow: {gap} bloques de atraso; se cubren con los eventos del hueco {a}..{upto}")
        self.out.write("eventos_del_sistema.jsonl", {"evento": "salto", "desde": a, "hasta": upto, "bloques": gap})
        if gap > self.cfg["max_gap_blocks"]:
            self._resync_all(upto)
            return
        events = self._events(a, upto, None)
        liquidations = self._apply_events(events, upto)
        self.last_block = upto
        self.first_eval_block = upto + 1
        self._safely(self._sync_unsynced, upto, None)
        self._resolve_late(liquidations)

    def _resync_all(self, upto):
        """Un hueco enorme: ya no se puede reconstruir con eventos; se vuelve a leer todo el libro."""
        log(f"shadow: hueco demasiado grande; se vuelve a leer todo el libro en el bloque {upto}")
        for key in list(self.pending):
            self._close_pending(key, "perdida_por_salto", upto)
        self.last_block = upto
        self.first_eval_block = upto + 1
        for key in self.book.pos:
            self.book.unsynced.add(key)
            self.book.pos[key].synced = -1
        self.book.by_market.clear()
        self._sync_unsynced(upto, None)

    def _skip(self, n):
        """El bloque no se pudo procesar tras muchos intentos: se sigue y se intenta recuperar sus eventos más tarde."""
        self.counts["bloques_perdidos"] += 1
        log(f"shadow: se da por perdido el bloque {n}; se intentará recuperar sus eventos")
        self.out.write("eventos_del_sistema.jsonl", {"evento": "bloque_perdido", "bloque": n})
        self.lost[n] = 0
        self.last_block = n
        self.first_eval_block = n + 1

    def _recover_lost(self):
        self.t_lost = self.mono()
        for n in sorted(self.lost):
            try:
                events = self._events(n, n, None)
            except RpcError:
                self.lost[n] += 1
                if self.lost[n] >= self.cfg["lost_retries"]:
                    del self.lost[n]
                    self.counts["bloques_perdidos_definitivos"] += 1
                    self.out.write("eventos_del_sistema.jsonl", {"evento": "bloque_perdido_definitivo", "bloque": n})
                continue
            del self.lost[n]
            self.counts["bloques_recuperados"] += 1
            liquidations = self._apply_events(events, self.last_block)
            self._safely(self._sync_unsynced, self.last_block, None)
            self._resolve_late(liquidations)

    def write_meta(self, final=False):
        meta = dict(self.meta)
        meta.update({
            "fin": self.wall() if final else None, "bloque_actual": self.last_block, "contadores": dict(self.counts),
            "decisiones": dict(self.decisions), "resultados": dict(self.outcomes), "pendientes": len(self.pending),
            "bloques_perdidos_sin_recuperar": sorted(self.lost),
            "latencia_visto_ms": quantiles(self.lat_visto), "latencia_proceso_ms": quantiles(self.lat_proc),
            "latencia_visto_mas_proceso_ms": quantiles(self.lat_total), "libro_deriva": self.book.drift,
            "multicall_ok": self.multicall_ok, "rpc_llamadas": self.rpc.calls, "rpc": self.rpc.report(),
            "reconstruible_desde": "bloques.jsonl, decisiones.jsonl, resultados.jsonl"})
        self.out.json("meta.json", meta)

    def finish(self):
        if self.lost:
            self._safely(self._recover_lost)
        if self._pool is not None:
            self._pool.shutdown(wait=False)
            self._pool = None
        for key in list(self.pending):
            self._close_pending(key, "abierta_al_cierre", self.last_block)
        self.write_meta(final=True)
        self.out.json("libro.json", self.cache_snapshot())
        self.out.close()
        log(f"shadow: listo: {self.counts['bloques']} bloques, {self.counts['candidatas']} candidatas, "
            f"decisiones {dict(self.decisions)}")
        return self.meta


class HeadWatcher:
    """Hilos que le preguntan la cabeza de la cadena a varios proveedores y guardan cuándo se vio cada bloque primero."""

    def __init__(self, rpc, urls, interval=0.4, wall=time.time, mono=time.monotonic):
        self.rpc, self.urls, self.interval, self.wall, self.mono = rpc, list(urls), interval, wall, mono
        self.cond = threading.Condition()
        self.head, self.first, self.alive = 0, {}, True
        self.threads = []

    def start(self):
        for u in self.urls:
            t = threading.Thread(target=self._loop, args=(u,), daemon=True)
            t.start()
            self.threads.append(t)
        return self

    def _loop(self, url):
        while self.alive:
            ok, res, _ = raw_call(self.rpc, url, "eth_blockNumber", [], 5)
            t_wall, t_mono = self.wall(), self.mono()       # cuando llegó la respuesta: antes no sabíamos que existía el bloque
            if ok:
                try:
                    n = int(res, 16)
                except (TypeError, ValueError):
                    n = 0
                with self.cond:
                    if n > self.head:
                        self.head = n
                        self.first[n] = (t_wall, t_mono, url)
                        for old in [b for b in self.first if b < n - 300]:
                            del self.first[old]
                        self.cond.notify_all()
            time.sleep(self.interval)

    def wait(self, after, timeout=1.0):
        with self.cond:
            if self.head <= (after or 0):
                self.cond.wait(timeout)
            if self.head <= (after or 0):
                return None, None, None, None
            w, m, u = self.first.get(self.head, (self.wall(), self.mono(), None))
            return self.head, w, m, u

    def stop(self):
        self.alive = False


def choose_watchers(rpc, k=3):
    """Los k proveedores que responden más rápido eth_blockNumber (mediana de 3 intentos)."""
    scored = []
    for url in rpc.urls:
        ms = []
        for _ in range(3):
            ok, res, dt = raw_call(rpc, url, "eth_blockNumber", [], 5)
            if ok:
                ms.append(dt)
        if len(ms) >= 2:
            scored.append((statistics.median(ms), url))
    scored.sort()
    return [u for _, u in scored[:k]]


def make_rpc(rps=8):
    urls = [u.strip() for u in os.environ.get(CHAINS["base"].extra_rpcs_env, "").split(",") if u.strip()]
    urls += list(CHAINS["base"].public_rpcs)
    return Rpc(urls, rps=rps, expected_chain_id=CHAINS["base"].chain_id, public=set(CHAINS["base"].public_rpcs))


def run_live(cfg, out_dir, cache_path=None, rpc=None, markets=None, head_source=None, sleep=time.sleep, on_ready=None):
    """Punto de entrada del modo en vivo (también lo usan las pruebas con una cadena falsa).

    `on_ready(shadow)` se llama con el libro ya armado, justo antes de empezar a vigilar bloques."""
    rpc = rpc or make_rpc()
    shadow = Shadow(rpc, out_dir, cfg, markets=markets).setup()
    cache = None
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path) as fh:
                cache = json.load(fh)
        except (OSError, ValueError):
            cache = None
    head = rpc.block_number()
    budget = shadow.mono() + shadow.cfg["book_budget_s"]
    shadow.bootstrap(head, cache, deadline=budget)
    shadow.write_meta()
    watcher = None
    if head_source is None:
        urls = choose_watchers(rpc) or rpc.urls[:1]
        log(f"shadow: vigilando la cabeza con {len(urls)} proveedores")
        watcher = HeadWatcher(rpc, urls).start()
        head_source = lambda last: watcher.wait(last)    # noqa: E731
    try:
        if on_ready:
            on_ready(shadow)
        return shadow.run(cfg.get("minutos", 90), head_source, sleep)
    finally:
        if watcher:
            watcher.stop()
