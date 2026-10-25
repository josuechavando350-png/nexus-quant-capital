"""Replay histórico del Shadow (el "túnel de viento" del Omega, versión mínima). Solo lectura.

Para liquidaciones que ya pasaron en Base/Morpho reconstruye, con lecturas de archivo, en qué bloque
la posición se volvió liquidable ("cruce") y compara con el bloque en que alguien la liquidó. Esa
distancia es el margen de tiempo que hubo: lo que decide si un actor con cierta latencia llegaba.

También comprueba la matemática contra la cadena: con el estado anterior a la liquidación, el precio
y el interés, ¿el contrato habría dado el embargo y el repago que dice el evento?

Límite: solo ve posiciones que terminaron liquidadas. No sabe nada de las que se volvieron
liquidables y se recuperaron o se quedaron sin liquidar (eso lo mide el modo en vivo).
"""

import bisect
import os
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from . import morpho as mo
from .abi import norm
from .config import SHADOW_PRIOR_KEPT_ALL
from .keccak import selector
from .rpc import BudgetExceeded, RpcError
from .orden import propinas_alrededor
from .shadow_live import AUCTION_ENTRIES, Out, Shadow, log, make_rpc

RDEFAULTS = {
    "dias": 30, "max": 300, "top": 100, "min_bonus_usd": 5.0, "ventana_bloques": 1800, "trabajadores": 6,
    "presupuesto_min": 40.0, "margen_cabeza": 30,
    "libro_dias": 90,           # cuántos días antes de la ventana se buscan los Borrow para medir la cobertura del libro (0 = no)
    "libro_min": 20.0,          # tiempo máximo de esa búsqueda (en Base son ~100 consultas de 50 mil bloques)
    "scan_workers": 4,          # trozos de getLogs que se piden a la vez al buscar eventos de un rango largo
    "diag": 0,                  # cuántas liquidaciones directas se miran con lupa (precio, feeds del oráculo y su actualización)
    "flash_probe": 0,           # segundos de sonda de Flashblocks (bloque pendiente de un RPC con preconfirmaciones); 0 = no
    "orden": 0,                 # de los bloques mirados con lupa, cuántos de los más llenos se guardan con la propina de cada transacción (0 = no)
}

def pick_diag(rows, n):
    """Las liquidaciones directas más grandes, repartidas entre los mercados (no solo las del mercado más grande)."""
    direct = sorted((r for r in rows if r.get("via") == "directa" and not r.get("sin_dato")), key=lambda r: -r["bono_usd"])
    per_market = {}
    for r in direct:
        per_market.setdefault(r["mercado"], []).append(r)
    order = sorted(per_market, key=lambda m: -per_market[m][0]["bono_usd"])
    picks, i = [], 0
    while len(picks) < n and any(i < len(per_market[m]) for m in order):
        for m in order:
            if i < len(per_market[m]) and len(picks) < n:
                picks.append(per_market[m][i])
        i += 1
    return picks


EARLIEST = re.compile(r"earliest available[^0-9]*(\d+)", re.I)


def earliest_available(err):
    """El proveedor ya no guarda tanta historia de logs: "... requested 47866647, earliest available 51500000"."""
    m = EARLIEST.search(str(err))
    return int(m.group(1)) if m else None


def scan_logs(rpc, address, topics, start, end, deadline=None, workers=4, chunk=50_000):
    """getLogs de un rango largo en trozos, varios a la vez.

    Devuelve (logs, desde, hasta, completo). Si el proveedor no guarda tanta historia, empieza donde sí la tiene
    (`desde` mayor que `start`). Si se acaba el tiempo, devuelve lo leído de corrido desde el inicio (`completo` False)."""
    first = start
    for _ in range(2):
        ranges = [(a, min(end, a + chunk - 1)) for a in range(first, end + 1, chunk)]
        out, reached, complete = [], first - 1, True
        ex = ThreadPoolExecutor(max_workers=max(1, workers))
        try:
            futures = [ex.submit(rpc.get_logs, address, topics, a, b, None, deadline) for a, b in ranges]
            for (a, b), f in zip(ranges, futures):
                try:
                    out.extend(f.result())
                    reached = b
                except BudgetExceeded as e:
                    out.extend(e.logs)
                    reached, complete = e.next_block - 1, False
                    break
            return out, first, reached, complete
        except RpcError as e:
            nxt = earliest_available(e)
            if nxt is None or nxt <= first or nxt > end:
                raise
            first = nxt
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
    raise RpcError("no se pudo leer el historial de logs")


def event_bonus(e, markets):
    """Bono de la liquidación en USD: repago x (LIF - 1). None si el mercado no se vigila."""
    info = markets.get(e["market"])
    if info is None:
        return None
    return e["repaid_assets"] * (info.lif - mo.WAD) / mo.WAD / 10 ** info.loan_dec * info.loan_usd


def select_events(events, markets, cfg):
    """Las liquidaciones a reconstruir: las `top` de mayor bono y una muestra pareja del resto (determinista).

    Cada evento elegido lleva su grupo y su peso (1 para las mayores; el tamaño del resto dividido entre la muestra
    para las demás) para poder estimar totales de toda la ventana a partir de la muestra."""
    scored = []
    for e in events:
        bonus = event_bonus(e, markets)
        if bonus is not None and bonus >= cfg["min_bonus_usd"]:
            scored.append((bonus, e))
    scored.sort(key=lambda x: (-x[0], x[1]["block"], x[1]["log_index"]))
    top = scored[:cfg["top"]]
    rest = scored[cfg["top"]:]
    room = max(0, cfg["max"] - len(top))
    weight = 1.0
    if room and rest:
        weight = max(1.0, len(rest) / room)
        stride = max(1, len(rest) / room)
        rest = [rest[int(i * stride)] for i in range(min(room, len(rest)))]
    else:
        rest = []
    return ([{**e, "_grupo": "top", "_peso": 1.0} for _, e in top]
            + [{**e, "_grupo": "muestra", "_peso": weight} for _, e in rest])


def prior_kept(prior, min_n=30):
    kept = prior.get("kept_dir")
    return kept if kept is not None and prior.get("n_dir", 0) >= min_n else SHADOW_PRIOR_KEPT_ALL


class Replay:
    def __init__(self, shadow, out_dir, cfg=None, borrows=None, borrow_from=None):
        self.sh = shadow
        self.borrows = borrows              # {(mercado, usuario): [bloques de Borrow]} o None si no se midió
        self.borrow_from = borrow_from      # primer bloque que cubre esa búsqueda
        self.cfg = {**RDEFAULTS, **(cfg or {})}
        self.out = Out(out_dir)
        self.lock = threading.Lock()
        self.hdr, self.stat = {}, {}
        self.n_sondeos = 0
        self._tips = {}                     # bloque -> propina de cada transacción (solo los últimos bloques mirados con lupa)

    # -- lecturas de archivo -------------------------------------------------------------------
    def header(self, b):
        h = self.hdr.get(b)
        if h is None:
            blk = self.sh.rpc.block(b)
            h = {"ts": int(blk["timestamp"], 16), "base_fee": int(blk.get("baseFeePerGas") or "0x0", 16),
                 "n_tx": len(blk.get("transactions") or [])}
            self.hdr[b] = h
        return h

    def _rate(self, info, state, b):
        if info.params.irm == mo.ZERO:
            return 0
        ok, data = self.sh._single(info.params.irm, mo.call_rate(info.params, state), b, recent=False)
        try:
            return mo.decode_uint(data) if ok else None
        except ValueError:
            return None

    def status(self, mid, user, b):
        """Estado de la posición al cierre del bloque b: ¿liquidable? (con interés si está al borde)."""
        key = (mid, user, b)
        if key in self.stat:
            return self.stat[key]
        info = self.sh.markets[mid]
        res = self.sh.mcall([(self.sh.morpho, mo.call_market(mid)), (info.params.oracle, mo.SEL_PRICE),
                             (self.sh.morpho, mo.call_position(mid, user))], b, recent=False)
        self.n_sondeos += 1
        if not all(ok for ok, _ in res):
            self.stat[key] = None
            return None
        state, price = mo.decode_market(res[0][1]), mo.decode_uint(res[1][1])
        _, shares, coll = mo.decode_position(res[2][1])
        out = {"liq": False, "ratio": None, "state": state, "price": price, "shares": shares, "coll": coll, "con_interes": False}
        if shares > 0:
            lltv = info.params.lltv
            out["ratio"] = mo.health_ratio(shares, coll, price, lltv, state)
            out["liq"] = not mo.is_healthy(shares, coll, price, lltv, state)
            if not out["liq"] and out["ratio"] < 1 + self.sh.cfg["accrual_band"]:
                rate = self._rate(info, state, b)
                if rate:
                    aged = mo.accrue(state, rate, self.header(b)["ts"])
                    if not mo.is_healthy(shares, coll, price, lltv, aged):
                        out["liq"], out["con_interes"] = True, True
        self.stat[key] = out
        return out

    def find_cross(self, mid, user, b_l):
        """Primer bloque desde el que la posición estuvo liquidable de corrido hasta la liquidación."""
        window = self.cfg["ventana_bloques"]
        prev = self.status(mid, user, b_l - 1)
        if prev is None:
            return None
        if not prev["liq"]:
            return {"b_c": b_l, "censurado": False}
        hi, step, lo = b_l - 1, 1, None
        while lo is None:
            cand = max(hi - step, b_l - window)
            s = self.status(mid, user, cand)
            if s is None:
                return None
            if not s["liq"]:
                lo = cand
            else:
                hi = cand
                if cand <= b_l - window:
                    return {"b_c": hi, "censurado": True}
                step *= 2
        while hi - lo > 1:
            m = (lo + hi) // 2
            s = self.status(mid, user, m)
            if s is None:
                return None
            if s["liq"]:
                hi = m
            else:
                lo = m
        return {"b_c": hi, "censurado": False}

    def parity(self, ev, info):
        """¿El contrato habría dado lo que dice el evento? Estado previo + precio + interés hasta la liquidación."""
        if ev["bad_debt_shares"] > 0:
            return {"omitida": "deuda_mala"}
        prev = self.status(ev["market"], ev["user"], ev["block"] - 1)
        res = self.sh.mcall([(info.params.oracle, mo.SEL_PRICE)], ev["block"], recent=False)
        if prev is None or not res[0][0]:
            return {"omitida": "sin_lectura"}
        price = mo.decode_uint(res[0][1])
        state = prev["state"]
        rate = self._rate(info, state, ev["block"] - 1)
        if rate:
            state = mo.accrue(state, rate, self.header(ev["block"])["ts"])
        lltv = info.params.lltv
        seized_pred, repaid_pred = mo.predict_from_repaid_shares(ev["repaid_shares"], price, lltv, state)
        shares_pred, repaid_pred2 = mo.predict_from_seized_assets(ev["seized_assets"], price, lltv, state)
        err_seized = abs(seized_pred - ev["seized_assets"]) / max(1, ev["seized_assets"])
        err_shares = abs(shares_pred - ev["repaid_shares"]) / max(1, ev["repaid_shares"])
        by_shares = err_seized <= err_shares
        repaid = repaid_pred if by_shares else repaid_pred2
        return {"modo": "repaid_shares" if by_shares else "seized_assets", "err_embargo": err_seized if by_shares else 0.0,
                "err_shares": 0.0 if by_shares else err_shares,
                "err_repago": abs(repaid - ev["repaid_assets"]) / max(1, ev["repaid_assets"]), "con_interes": bool(rate)}

    def tx_info(self, h, b):
        tx = self.sh.rpc.call("eth_getTransactionByHash", [h])
        rc = self.sh.rpc.call("eth_getTransactionReceipt", [h])
        if not tx or not rc:
            return {}
        hdr = self.header(b)
        gas_used = int(rc["gasUsed"], 16)
        eff = int(rc.get("effectiveGasPrice") or tx.get("gasPrice") or "0x0", 16)
        l1 = int(rc.get("l1Fee") or "0x0", 16)
        eth = self.sh.eth_usd()
        to = norm(tx.get("to") or mo.ZERO)
        prio = max(0, eff - hdr["base_fee"])
        return {"firmante": norm(tx["from"]), "entrada": to, "via": "subasta" if to in AUCTION_ENTRIES else "directa",
                "gas_usd": (gas_used * eff + l1) / 1e18 * eth,
                "propina_usd": prio * gas_used / 1e18 * eth, "eth_usd_actual": eth,
                # dónde cayó dentro del bloque: cuántas transacciones tuvo y cuánto pagó por prioridad (wei por unidad de gas)
                "bloque_n_tx": hdr["n_tx"], "prioridad_wei": prio}

    def book_age_days(self, ev):
        """Días entre el último Borrow del prestatario y la liquidación: ¿un libro que mira N días atrás lo conocía?
        None: no hubo Borrow en todo lo escaneado (más viejo que eso)."""
        blocks = (self.borrows or {}).get((ev["market"], ev["user"]))
        if not blocks:
            return None
        i = bisect.bisect_right(blocks, ev["block"]) - 1
        if i < 0:
            return None
        return (ev["block"] - blocks[i]) * self.sh.cfg["block_time_s"] / 86400

    def process(self, ev, first_in_block):
        info = self.sh.markets[ev["market"]]
        fc = self.find_cross(ev["market"], ev["user"], ev["block"])
        residual = False
        prev = ev.get("_prev_liq")
        if fc is not None and prev is not None and prev >= fc["b_c"]:
            # Ya la liquidaron antes y siguió liquidable (liquidación parcial): la carrera por el residuo empieza ahí.
            fc, residual = {"b_c": prev, "censurado": False}, True
        bonus = ev["repaid_assets"] * (info.lif - mo.WAD) / mo.WAD / 10 ** info.loan_dec * info.loan_usd
        kept = prior_kept(info.prior, self.sh.cfg["prior_min_n"])
        row = {"mercado": ev["market"], "etiqueta": info.label, "prestatario": ev["user"], "bloque_liquidacion": ev["block"],
               "tx": ev["tx_hash"], "tx_index": ev["tx_index"], "liquidador": ev["caller"], "bono_usd": bonus,
               "retencion_prior": kept, "neto_modelo_usd": bonus * kept, "deuda_mala": ev["bad_debt_shares"] > 0,
               "grupo": ev.get("_grupo"), "peso": ev.get("_peso", 1.0)}
        if self.borrows is not None:
            row["libro_edad_dias"] = self.book_age_days(ev)
            row["libro_historia_dias"] = (ev["block"] - self.borrow_from) * self.sh.cfg["block_time_s"] / 86400
        if fc is None:
            row["sin_dato"] = True
        else:
            row.update(bloque_cruce=fc["b_c"], delta_bloques=ev["block"] - fc["b_c"], censurado=fc["censurado"],
                       residual_de_liquidacion_parcial=residual)
        row.update(self.tx_info(ev["tx_hash"], ev["block"]))
        if first_in_block:
            row["paridad"] = self.parity(ev, info)
        return row

    # -- diagnóstico: una mirada directa, bloque a bloque, a unas liquidaciones ----------------------
    def diag_oracle(self, info, block):
        """Qué feeds hay detrás del oráculo del mercado y cómo se llaman (la misma lectura que usa el modo en vivo)."""
        return self.sh.oracle_feeds(info, block, recent=False)

    def diag_feeds_at(self, oracle_info, block):
        """Respuesta de cada feed en el estado final de `block`: ronda, valor y hora de actualización."""
        out = {}
        items = [(g, d["direccion"]) for g, d in oracle_info["detalle"].items()]
        if not items:
            return out
        res = self.sh.mcall([(a, selector("latestRoundData()")) for _, a in items], block, recent=False)
        for (g, a), (ok, data) in zip(items, res):
            if ok and len(data) >= 160:
                w = [int.from_bytes(data[i:i + 32], "big") for i in range(0, 160, 32)]
                ans = w[1] - (1 << 256) if w[1] >> 255 else w[1]
                out[g] = {"ronda": w[0], "respuesta": ans, "actualizado": w[3]}
        return out

    def block_tip_list(self, b):
        """La propina de cada transacción del bloque, en su orden (el bloque entero con transacciones: pesa, así que se guarda poco)."""
        from .orden import block_tips
        if b not in self._tips:
            blk = self.sh.rpc.call("eth_getBlockByNumber", [hex(b), True])
            self._tips[b] = block_tips(blk)[1] if blk else None
            for old in list(self._tips)[:-64]:
                del self._tips[old]
        return self._tips[b]

    def diagnose(self, rows, n):
        picks = pick_diag(rows, n)
        oracles, out_rows = {}, []
        for r in picks:
            info = self.sh.markets[r["mercado"]]
            b = r["bloque_liquidacion"]
            try:
                if info.params.oracle not in oracles:
                    oracles[info.params.oracle] = self.diag_oracle(info, b)
                orc = oracles[info.params.oracle]
                serie = []
                for k in range(b - 4, b + 2):
                    try:
                        st = self.status(r["mercado"], r["prestatario"], k)
                        feeds = self.diag_feeds_at(orc, k)
                    except RpcError:
                        st, feeds = None, {}              # p. ej. un bloque posterior a la cabeza
                    serie.append({"bloque": k, "precio": None if st is None else st["price"],
                                  "salud": None if st is None else st["ratio"], "liquidable": None if st is None else st["liq"],
                                  "feeds": feeds})
                addrs = [d["direccion"] for d in orc["detalle"].values()] + [d["agregador"] for d in orc["detalle"].values() if d["agregador"]]
                logs = []
                if addrs:
                    for k in (b - 1, b):
                        for lg in self.sh.rpc.call("eth_getLogs", [{"fromBlock": hex(k), "toBlock": hex(k), "address": addrs}]):
                            logs.append({"bloque": k, "direccion": norm(lg["address"]), "tx": lg["transactionHash"],
                                         "tx_index": int(lg["transactionIndex"], 16), "log_index": int(lg["logIndex"], 16),
                                         "topic0": (lg.get("topics") or [None])[0]})
                before = [x for x in logs if x["bloque"] == b and x["tx_index"] < r["tx_index"]]
                upd = max(before, key=lambda x: x["tx_index"]) if before else None
                upd_tx = None
                if upd:
                    tx = self.sh.rpc.call("eth_getTransactionByHash", [upd["tx"]])
                    if tx:
                        upd_tx = {"tx": upd["tx"], "tx_index": upd["tx_index"], "from": norm(tx["from"]), "to": norm(tx.get("to") or mo.ZERO),
                                  "valor_wei": int(tx.get("value") or "0x0", 16)}
                        # Qué hizo esa transacción (¿pagó algo? ¿a quién?): resumen de su recibo
                        rc = self.sh.rpc.call("eth_getTransactionReceipt", [upd["tx"]])
                        if rc:
                            rlogs = rc.get("logs") or []
                            eff = int(rc.get("effectiveGasPrice") or tx.get("gasPrice") or "0x0", 16)
                            upd_tx.update(prioridad_wei=max(0, eff - self.header(b)["base_fee"]),
                                          n_logs=len(rlogs), gas_usado=int(rc.get("gasUsed") or "0x0", 16),
                                          logs=[{"direccion": norm(lg["address"]), "topic0": (lg.get("topics") or [None])[0],
                                                 "topics": (lg.get("topics") or [])[1:3], "datos": (lg.get("data") or "")[:130]}
                                                for lg in rlogs[:16]])
                propinas = None
                if upd_tx:
                    try:
                        propinas = propinas_alrededor(self.block_tip_list(b), upd_tx["tx_index"], r["tx_index"])
                    except RpcError:
                        propinas = None                  # sin las propinas del bloque la fila sigue sirviendo para lo demás
                out_rows.append({"mercado": r["mercado"], "etiqueta": r["etiqueta"], "prestatario": r["prestatario"], "bloque_liquidacion": b,
                                 "tx": r["tx"], "tx_index": r["tx_index"], "firmante": r.get("firmante"), "entrada": r.get("entrada"),
                                 "bono_usd": r["bono_usd"], "bloque_n_tx": r.get("bloque_n_tx"), "prioridad_wei": r.get("prioridad_wei"),
                                 "propinas": propinas, "serie": serie, "logs_feed": logs, "actualizacion_previa": upd_tx})
            except RpcError as e:
                out_rows.append({"mercado": r["mercado"], "etiqueta": r["etiqueta"], "bloque_liquidacion": b, "tx": r["tx"],
                                 "error": self.sh.rpc.scrub(e)[:160]})
        for row in out_rows:
            self.out.write("diag.jsonl", row)
        self.out.json("diag_oraculos.json", oracles)
        return out_rows

    def sample_order(self, diag_rows, n):
        """Los `n` bloques más llenos entre los mirados con lupa, con la propina de cada transacción en su orden: sirve para
        comprobar si dentro de cada trozo de 200 ms van por prioridad (muchos ascensos de propina = no, pocos = sí)."""
        from .orden import block_tips
        sizes = {}
        for d in diag_rows:
            if d.get("bloque_n_tx"):
                sizes[d["bloque_liquidacion"]] = d["bloque_n_tx"]
        done = 0
        for b, _ in sorted(sizes.items(), key=lambda kv: -kv[1])[:n]:
            try:
                blk = self.sh.rpc.call("eth_getBlockByNumber", [hex(b), True])
            except RpcError:
                continue
            if blk:
                base, tips = block_tips(blk)
                self.out.write("orden_bloques.jsonl", {"bloque": b, "base_fee": base, "tips": tips})
                done += 1
        return done

    # -- ejecución -----------------------------------------------------------------------------
    def run(self, events):
        first, last_seen = {}, {}
        for e in sorted(events, key=lambda e: (e["block"], e["log_index"])):
            k = (e["market"], e["block"])
            first[k] = min(first.get(k, e["log_index"]), e["log_index"])
            e["_prev_liq"] = last_seen.get((e["market"], e["user"]))        # liquidación anterior de la misma posición
            last_seen[(e["market"], e["user"])] = e["block"]
        chosen = select_events(events, self.sh.markets, self.cfg)
        deadline = time.monotonic() + self.cfg["presupuesto_min"] * 60
        done, failed, skipped = [], 0, 0
        self.rows_done = done

        def work(ev):
            nonlocal skipped
            if time.monotonic() > deadline:
                skipped += 1
                return None
            try:
                row = self.process(ev, first[(ev["market"], ev["block"])] == ev["log_index"])
            except RpcError as e:
                return {"error": self.sh.rpc.scrub(e)[:160], "tx": ev["tx_hash"], "mercado": ev["market"]}
            with self.lock:
                self.out.write("replay.jsonl", row)
            return row
        log(f"replay: {len(chosen)} liquidaciones elegidas de {len(events)}")
        with ThreadPoolExecutor(max_workers=self.cfg["trabajadores"]) as ex:
            for i, row in enumerate(ex.map(work, chosen)):
                if row is None:
                    continue
                if "error" in row:
                    failed += 1
                    with self.lock:
                        self.out.write("replay_errores.jsonl", row)
                else:
                    done.append(row)
                if (i + 1) % 25 == 0:
                    log(f"replay: {i + 1}/{len(chosen)} reconstruidas, {self.sh.rpc.calls:,} llamadas RPC")
        return self.summary(events, chosen, done, failed, skipped)

    def summary(self, events, chosen, done, failed, skipped):
        bonos = [event_bonus(e, self.sh.markets) for e in events]
        bonos = [b for b in bonos if b is not None]
        par = [r["paridad"] for r in done if r.get("paridad") and "modo" in r["paridad"]]
        errs = sorted(max(p["err_embargo"], p["err_shares"], p["err_repago"]) for p in par)
        elegible = [b for b in bonos if b >= self.cfg["min_bonus_usd"]]
        return {"eventos_en_ventana": len(events), "elegibles": len(elegible), "bono_total_usd": sum(bonos),
                "bono_elegible_usd": sum(elegible), "elegidos": len(chosen),
                "bono_elegido_usd": sum(event_bonus(e, self.sh.markets) for e in chosen),
                "procesados": len(done), "fallidos": failed,
                "omitidos_por_tiempo": skipped, "sin_dato": sum(1 for r in done if r.get("sin_dato")),
                "censurados": sum(1 for r in done if r.get("censurado")),
                "sondeos_de_archivo": self.n_sondeos,
                "paridad": {"n": len(errs), "omitidas": sum(1 for r in done if r.get("paridad") and "omitida" in r["paridad"]),
                            "max": errs[-1] if errs else None, "mediana": errs[len(errs) // 2] if errs else None,
                            "exactas": sum(1 for x in errs if x == 0), "dentro_1e9": sum(1 for x in errs if x <= 1e-9),
                            "dentro_1e6": sum(1 for x in errs if x <= 1e-6), "dentro_1e3": sum(1 for x in errs if x <= 1e-3)}}


def run_replay(cfg, out_dir, rpc=None, markets=None):
    """Punto de entrada: arma los mercados, busca las liquidaciones de la ventana y las reconstruye."""
    rcfg = {**RDEFAULTS, **{k: v for k, v in cfg.items() if k in RDEFAULTS}}
    rpc = rpc or make_rpc()
    sh = Shadow(rpc, os.path.join(out_dir, "_sombra"), cfg, markets=markets).setup()
    bt = sh.cfg["block_time_s"]
    head = rpc.block_number() - rcfg["margen_cabeza"]
    start = max(1, head - int(rcfg["dias"] * 86400 / bt))
    t0 = time.monotonic()
    log(f"replay: buscando liquidaciones en los bloques {start:,}..{head:,}")
    deadline = time.monotonic() + max(60.0, 0.4 * rcfg["presupuesto_min"] * 60)     # la búsqueda de eventos usa hasta 40%
    logs, start_used, scanned_to, complete = scan_logs(rpc, sh.morpho, [[mo.EVENT_TOPICS["Liquidate"]], sh.ids], start, head,
                                                       deadline, rcfg["scan_workers"])
    if start_used > start:
        log(f"replay: el proveedor solo guarda logs desde el bloque {start_used:,}; la ventana se acorta a "
            f"{(head - start_used) * bt / 86400:.1f} días")
    if not complete:
        log(f"replay: ventana parcial: la búsqueda llegó al bloque {scanned_to:,}")
    events = []
    for lg in logs:
        try:
            ev = mo.decode_event(lg)
        except ValueError:
            continue
        if ev and ev["kind"] == "Liquidate" and not lg.get("removed"):
            events.append(ev)
    window = {"desde": start_used, "desde_pedido": start, "hasta_pedido": head, "hasta_leido": scanned_to, "dias": rcfg["dias"],
              "dias_reales": round((scanned_to - start_used) * bt / 86400, 2), "completa": complete}
    early = Out(out_dir)
    early.json("replay_meta.json", {"estado": "en_curso", "ventana": window, "eventos_en_ventana": len(events), "config": rcfg,
                                     "segundos": round(time.monotonic() - t0, 1)})
    log(f"replay: {len(events)} liquidaciones en la ventana ({time.monotonic() - t0:.0f} s)")

    borrows, borrow_from, scan = None, None, {"dias": rcfg["libro_dias"], "completo": False, "borrows": 0}
    if rcfg["libro_dias"] > 0 and events:
        b_start = max(1, start_used - int(rcfg["libro_dias"] * 86400 / bt))
        log(f"replay: buscando Borrow desde el bloque {b_start:,} para medir la cobertura del libro")
        try:
            blogs, b_from, b_to, ok = scan_logs(rpc, sh.morpho, [[mo.EVENT_TOPICS["Borrow"]], sh.ids], b_start, scanned_to,
                                                time.monotonic() + max(60.0, rcfg["libro_min"] * 60), rcfg["scan_workers"])
            scan.update(completo=ok, desde=b_from, hasta=b_to)
            if b_from > b_start:
                log(f"replay: los Borrow solo se pueden leer desde el bloque {b_from:,}")
            if not ok:
                log(f"replay: la búsqueda de Borrow quedó incompleta en el bloque {b_to:,}")
        except RpcError as e:
            blogs = []
            scan["error"] = rpc.scrub(e)[:160]
            log(f"replay: no se pudo medir la cobertura del libro: {scan['error']}")
        if scan["completo"]:
            borrows, borrow_from = defaultdict(list), scan["desde"]
            for lg in blogs:
                try:
                    ev = mo.decode_event(lg)
                except ValueError:
                    continue
                if ev and ev["kind"] == "Borrow" and not lg.get("removed"):
                    borrows[(ev["market"], ev["user"])].append(ev["block"])
            for blocks in borrows.values():
                blocks.sort()
            scan["borrows"] = sum(len(v) for v in borrows.values())
        # una cobertura a medias engaña: sin búsqueda completa no se mide
    rp = Replay(sh, out_dir, rcfg, borrows, borrow_from)
    meta = rp.run(events)
    if rcfg["diag"]:
        try:
            diag = rp.diagnose(rp.rows_done, rcfg["diag"])
            meta["diag"] = {"filas": len(diag), "con_error": sum(1 for d in diag if "error" in d)}
            log(f"replay: diagnóstico de {len(diag)} liquidaciones directas")
            if rcfg["orden"]:
                meta["diag"]["bloques_con_propinas"] = rp.sample_order(diag, rcfg["orden"])
                log(f"replay: propinas de {meta['diag']['bloques_con_propinas']} bloques llenos guardadas")
        except RpcError as e:
            meta["diag"] = {"error": rpc.scrub(e)[:160]}
    if rcfg["flash_probe"]:
        from . import flash_probe
        try:
            meta["flashblocks"] = flash_probe.probe(rpc, flash_probe.PRECONF_URLS, seconds=float(rcfg["flash_probe"]))
            log(f"replay: sonda de Flashblocks: {meta['flashblocks']}")
        except Exception as e:                   # la sonda es opcional: nunca debe tumbar el replay
            meta["flashblocks"] = {"error": str(e)[:160]}
    meta.update({"estado": "completo", "borrow_scan": scan, "ventana": window,
                 "config": rcfg, "segundos": round(time.monotonic() - t0, 1), "multicall_ok": sh.multicall_ok,
                 "mercados": {i: m.label for i, m in sh.markets.items()}, "rpc": rpc.report(), "rpc_llamadas": rpc.calls})
    rp.out.json("replay_meta.json", meta)
    log(f"replay: listo: {meta['procesados']} reconstruidas, paridad {meta['paridad']}")
    return meta
