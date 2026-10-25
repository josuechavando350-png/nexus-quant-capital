"""Vía rápida: decidir con el precio del oráculo calculado en casa en cuanto llega su actualización, sin preguntar a la red.

Lo que hace un sistema que quiere ganar el trozo siguiente: cuando el WebSocket trae el log `AnswerUpdated` de un feed (en el
trozo en que se preconfirmó), el precio nuevo del oráculo sale de multiplicar el último precio conocido por la razón entre la
respuesta nueva y la anterior del feed (los oráculos de Morpho son productos y cocientes de feeds). Con ese precio se evalúa el
libro en memoria y se anota cuánto se tardó en decidir desde que llegó el log. Al sellarse el bloque, si alguien liquidó, se mide
la ventana real (llegada de la liquidación del ganador menos llegada de la actualización, ambas por WebSocket) y la holgura con
un envío SUPUESTO (`submit_rapido_ms`): no se envía nada.
"""

import threading
import time

from .abi import norm
from .keccak import selector
from .rpc import RpcError
from .shadow_live import log, quantiles

ANSWER_UPDATED = "0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f"     # AnswerUpdated(int256,uint256,uint256)
BASE_SLOTS = ("BASE_FEED_1", "BASE_FEED_2")
QUOTE_SLOTS = ("QUOTE_FEED_1", "QUOTE_FEED_2")


def signed(x):
    return x - (1 << 256) if x >> 255 else x


class FastPath:
    def __init__(self, shadow, stream=None, wall=time.time, mono=time.monotonic):
        self.sh, self.stream, self.wall, self.mono = shadow, stream, wall, mono
        self.lock = threading.Lock()
        self.by_addr = {}           # feed (o su agregador) -> [(mercado, ranura, dirección del feed)]
        self.answers = {}           # (mercado, ranura) -> última respuesta conocida del feed
        self.crossings = {}         # (mercado, usuario) -> cruce visto por la vía rápida en un bloque pendiente
        self.updates = {}           # hash de la actualización -> {bloque, t_log, decision_ms, ...} (los últimos)
        self.stats = {"actualizaciones": 0, "sin_precio_base": 0, "cruces": 0, "cruces_liquidados": 0, "errores": 0}
        self.decision_ms, self.ventaja_ms, self.ventana_ms, self.holgura_ms = [], [], [], []

    # -- preparación ------------------------------------------------------------------------------
    def setup(self, block="latest"):
        """Qué feed alimenta a qué mercado (y por qué lado: base o cotización) y la respuesta actual de cada uno."""
        for mid, info in self.sh.markets.items():
            try:
                o = self.sh.oracle_feeds(info, block)
            except RpcError:
                continue
            for slot, d in o["detalle"].items():
                if slot not in BASE_SLOTS + QUOTE_SLOTS:
                    continue
                for a in (d["direccion"], d.get("agregador")):
                    if a:
                        self.by_addr.setdefault(norm(a), []).append((mid, slot, norm(d["direccion"])))
        self.refresh(block)
        return self

    def addresses(self):
        return sorted(self.by_addr)

    def refresh(self, block="latest"):
        """Vuelve a leer la respuesta de cada feed (por si se perdió algún log): `latestRoundData()` en un multicall."""
        feeds = sorted({(mid, slot, feed) for targets in self.by_addr.values() for mid, slot, feed in targets})
        if not feeds:
            return
        try:
            res = self.sh.mcall([(feed, selector("latestRoundData()")) for _, _, feed in feeds], block)
        except RpcError:
            return
        with self.lock:
            for (mid, slot, _), (ok, data) in zip(feeds, res):
                if ok and len(data) >= 64:
                    self.answers[(mid, slot)] = signed(int.from_bytes(data[32:64], "big"))

    # -- un log del WebSocket ---------------------------------------------------------------------
    def on_log(self, lg, t_recv):
        topics = lg.get("topics") or []
        if len(topics) < 2 or topics[0].lower() != ANSWER_UPDATED:
            return
        targets = self.by_addr.get(norm(lg.get("address") or ""))
        if not targets:
            return
        t0 = self.mono()
        new = signed(int(topics[1], 16))
        base_snap = self.sh.last_snap or {}
        snap = {}
        with self.lock:
            for mid, slot, _ in targets:
                old = self.answers.get((mid, slot))
                self.answers[(mid, slot)] = new
                if not old or new <= 0 or mid not in base_snap:
                    self.stats["sin_precio_base"] += 1
                    continue
                state, price = snap.get(mid) or base_snap[mid]
                snap[mid] = (state, price * new // old if slot in BASE_SLOTS else price * old // new)
        if not snap:
            return
        number = int(lg.get("blockNumber") or "0x0", 16)
        liq, _, _ = self.sh._evaluate_core(snap, number, int(self.wall()), offline=True)      # nada de red en el camino crítico
        t_ready = self.wall()
        dms = round((t_ready - t_recv) * 1000, 1)
        known = self.sh.last_liq_keys or set()
        tx = (lg.get("transactionHash") or "").lower()
        with self.lock:
            self.stats["actualizaciones"] += 1
            self.decision_ms.append(dms)
            self.updates[tx] = {"bloque": number, "tx": tx, "tx_index": int(lg.get("transactionIndex") or "0x0", 16), "t_log": t_recv,
                                "decision_ms": dms, "evaluar_ms": round((self.mono() - t0) * 1000, 1), "mercados": sorted(snap)}
            while len(self.updates) > 2000:
                self.updates.pop(next(iter(self.updates)))
            for key in liq:
                if key in known or key in self.crossings:
                    continue
                pos = self.sh.book.pos.get(key)
                if pos is None:
                    continue
                info = self.sh.markets[key[0]]
                state, price = snap[key[0]]
                _, eco = self.sh._economics(info, pos, price, liq[key]["state"])
                reason = self.sh._screen(info, eco)
                self.crossings[key] = {"bloque_pendiente": number, "tx_actualizacion": tx, "t_log": t_recv, "decision_ms": dms,
                                       "mercado": key[0], "etiqueta": info.label, "prestatario": key[1], "salud": liq[key]["ratio"],
                                       "bono_usd": eco["bono_usd"], "neto_modelo_usd": eco["neto_modelo_usd"],
                                       "decision": "GO" if reason is None else "NO-GO", "razon": reason or "ok"}
                self.stats["cruces"] += 1

    # -- cuando se sella el bloque ----------------------------------------------------------------------
    def on_block(self, n, liquidated):
        """Cierra lo visto hasta el bloque n: para cada liquidación real, la ventana entre la actualización y la liquidación
        (llegadas por WebSocket) y la holgura con el envío supuesto; y cuánto antes llegó la actualización por WebSocket que
        por la consulta del bloque pendiente."""
        submit = self.sh.cfg["submit_rapido_ms"]
        flash = self.sh.flash
        with self.lock:
            for tx, u in list(self.updates.items()):
                if u["bloque"] > n or "ventaja_ms" in u:
                    continue
                polled = flash.seen(u["bloque"], tx) if flash is not None else None
                u["ventaja_ms"] = None if polled is None else round((polled[0] - u["t_log"]) * 1000)
                if u["ventaja_ms"] is not None:
                    self.ventaja_ms.append(u["ventaja_ms"])
                self.sh.out.write("flash_actualizaciones.jsonl", u)          # una por actualización: para explicar los casos lentos
            for key, rec in list(self.crossings.items()):
                if rec["bloque_pendiente"] > n:
                    continue
                ev = liquidated.get(key) if rec["bloque_pendiente"] == n else None
                row = dict(rec)
                if ev:
                    t_liq = self.stream.seen(ev["tx_hash"]) if self.stream is not None else None
                    row.update(resultado="liquidada", tx=ev["tx_hash"])
                    if t_liq is not None:
                        win = round((t_liq - rec["t_log"]) * 1000, 1)
                        row.update(ventana_ms=win, holgura_ms=round(win - rec["decision_ms"] - submit, 1), envio_supuesto_ms=submit)
                        self.ventana_ms.append(win)
                        self.holgura_ms.append(row["holgura_ms"])
                    self.stats["cruces_liquidados"] += 1
                else:
                    row["resultado"] = "no_liquidada_en_el_bloque" if rec["bloque_pendiente"] == n else "vencido"
                self.sh.out.write("flash_rapido.jsonl", row)
                del self.crossings[key]

    def window_for(self, upd_tx, liq_tx):
        """Ventana medida por WebSocket entre la actualización y la liquidación (ms), si se vieron ambas."""
        if self.stream is None:
            return None
        a, b = self.stream.seen(upd_tx), self.stream.seen(liq_tx)
        return None if a is None or b is None else round((b - a) * 1000, 1)

    def report(self):
        with self.lock:
            return {**self.stats, "decision_ms": quantiles(self.decision_ms),
                    "evaluar_ms": quantiles([u["evaluar_ms"] for u in self.updates.values()]),
                    "ventaja_frente_a_la_consulta_ms": quantiles(self.ventaja_ms),
                    "ventana_ms": quantiles(self.ventana_ms), "holgura_ms": quantiles(self.holgura_ms),
                    "holgura_positiva": sum(1 for x in self.holgura_ms if x > 0), "supuesto_envio_ms": self.sh.cfg["submit_rapido_ms"],
                    "feeds": len(self.by_addr)}


def describe(fast):
    log(f"shadow: vía rápida lista: {len(fast.by_addr)} direcciones de feeds, {len(fast.answers)} respuestas leídas")
