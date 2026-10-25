"""Evaluador de Flashblocks: decide sobre el estado PENDIENTE (preconfirmado) cada vez que llega un trozo nuevo.

Es lo que haría un sistema de verdad: no esperar a que se selle el bloque. Cada trozo nuevo del bloque pendiente
(~200 ms) dispara una lectura de los mercados y precios en estado pendiente; se evalúa el libro y, si una posición
acaba de volverse liquidable, se anota CUÁNDO la vimos (qué trozo, cuántos ms después de empezar el bloque), cuánto
tardamos en decidir y qué habríamos decidido. Cuando el bloque se sella y aparece la liquidación real, se mide la
holgura: ¿nuestra transacción habría llegado antes de que apareciera la del ganador?

Solo lectura: no firma, no envía. La holgura usa un tiempo de envío SUPUESTO (cfg submit_ms).
"""

import threading
import time

from .rpc import RpcError
from .shadow_live import log, quantiles


class FlashEvaluator:
    def __init__(self, shadow, watcher, snapshot_fn, wall=time.time, mono=time.monotonic):
        self.sh, self.w, self.snapshot_fn = shadow, watcher, snapshot_fn
        self.wall, self.mono = wall, mono
        self.lock = threading.Lock()
        self.known = set()              # posiciones ya liquidables en el último estado evaluado (pendiente o sellado)
        self.crossings = {}             # (mercado, usuario) -> cruce visto en el bloque pendiente actual
        self.wake = threading.Event()
        self.latest = None
        self.alive = False
        self.thread = None
        self.stats = {"evaluaciones": 0, "errores": 0, "cruces": 0, "cruces_liquidados": 0, "cruces_sin_liquidar": 0}
        self.decision_ms, self.snapshot_ms, self.holgura_ms = [], [], []

    # -- hilo ---------------------------------------------------------------------------------
    def start(self):
        self.alive = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.alive = False
        self.wake.set()

    def notify(self, number, chunk, t):
        """Lo llama el observador cuando ve un trozo nuevo. Si llegan varios mientras se evalúa, solo importa el último."""
        self.latest = (number, chunk, t)
        self.wake.set()

    def _loop(self):
        while self.alive:
            self.wake.wait(1.0)
            self.wake.clear()
            ev, self.latest = self.latest, None
            if ev is not None and self.alive:
                try:
                    self.run_once(*ev)
                except Exception as e:                    # el evaluador nunca debe tumbar al Shadow
                    self.stats["errores"] += 1
                    log(f"shadow: evaluador de Flashblocks: {type(e).__name__}: {str(e)[:120]}")

    # -- una evaluación -----------------------------------------------------------------------
    def run_once(self, number, chunk, t_seen):
        t0 = self.mono()
        try:
            snap = self.snapshot_fn()
        except RpcError as e:
            self.stats["errores"] += 1
            log(f"shadow: lectura del estado pendiente falló: {self.sh.rpc.scrub(e)[:100]}")
            return
        t1 = self.mono()
        liq, _, _ = self.sh._evaluate_core(snap, number, int(self.wall()))
        t2 = self.mono()
        t_ready = self.wall()
        chunks = self.w.block_chunks(number)
        block_t0 = self.w.block_start(number)
        with self.lock:
            self.stats["evaluaciones"] += 1
            self.snapshot_ms.append(round((t1 - t0) * 1000))
            new = [k for k in liq if k not in self.known and k not in self.crossings]
            self.known = set(liq)
            for key in new:
                pos = self.sh.book.pos.get(key)
                if pos is None:
                    continue
                mid, user = key
                info = self.sh.markets[mid]
                state, price = snap[mid]
                q, eco = self.sh._economics(info, pos, price, liq[key]["state"])
                reason = self.sh._screen(info, eco)
                rec = {"bloque_pendiente": number, "trozo": chunk, "trozo_al_leer": len(chunks) - 1,
                       "t_visto": t_seen, "t_visto_ms": None if block_t0 is None else round((t_seen - block_t0) * 1000),
                       "snapshot_ms": round((t1 - t0) * 1000), "evaluar_ms": round((t2 - t1) * 1000),
                       "decision_ms": round((t_ready - t_seen) * 1000), "mercado": mid, "etiqueta": info.label, "prestatario": user,
                       "salud": liq[key]["ratio"], "con_interes": liq[key]["accrual"], "bono_usd": eco["bono_usd"],
                       "neto_modelo_usd": eco["neto_modelo_usd"], "deuda_mala": eco["deuda_mala"],
                       "decision": "GO" if reason is None else "NO-GO", "razon": reason or "ok"}
                self.crossings[key] = rec
                self.stats["cruces"] += 1
                self.decision_ms.append(rec["decision_ms"])

    # -- cuando se sella el bloque --------------------------------------------------------------
    def match(self, key, n, tx_hash):
        """Para una liquidación real del bloque sellado n: ¿la habíamos visto cruzar en el estado pendiente, y con qué holgura?"""
        with self.lock:
            rec = self.crossings.get(key)
            if rec is None or rec["bloque_pendiente"] != n:
                return None
            out = {"trozo_cruce": rec["trozo"], "decision_ms": rec["decision_ms"], "decision": rec["decision"], "razon": rec["razon"]}
            seen = self.w.seen(n, tx_hash)
            if seen is not None:
                t_liq, ch = seen
                out.update(trozo_ganador=ch, mismo_trozo=ch <= rec["trozo"],
                           visto_a_liquidacion_ms=round((t_liq - rec["t_visto"]) * 1000),
                           holgura_ms=round((t_liq - rec["t_visto"]) * 1000 - rec["decision_ms"] - self.sh.cfg["submit_ms"]))
                self.holgura_ms.append(out["holgura_ms"])
            rec["liquidacion"] = out
            return out

    def on_block(self, n, liquidated, sealed_liq):
        """Cierra los cruces vistos hasta el bloque n y vuelve a partir del estado sellado."""
        with self.lock:
            for key, rec in list(self.crossings.items()):
                if rec["bloque_pendiente"] > n:
                    continue
                ev = liquidated.get(key) if rec["bloque_pendiente"] == n else None
                row = {k: v for k, v in rec.items() if k != "liquidacion"}
                if ev:
                    row.update(resultado="liquidada", tx=ev["tx_hash"], liquidador=ev["caller"], **(rec.get("liquidacion") or {}))
                    self.stats["cruces_liquidados"] += 1
                else:
                    row["resultado"] = "no_liquidada_en_el_bloque" if rec["bloque_pendiente"] == n else "vencido"
                    self.stats["cruces_sin_liquidar"] += 1
                self.sh.out.write("flash_cruces.jsonl", row)
                del self.crossings[key]
            self.known = set(sealed_liq)

    def report(self):
        with self.lock:
            return {**self.stats, "decision_ms": quantiles(self.decision_ms), "lectura_pendiente_ms": quantiles(self.snapshot_ms),
                    "holgura_ms": quantiles(self.holgura_ms), "holgura_positiva": sum(1 for x in self.holgura_ms if x > 0),
                    "supuesto_envio_ms": self.sh.cfg["submit_ms"]}
