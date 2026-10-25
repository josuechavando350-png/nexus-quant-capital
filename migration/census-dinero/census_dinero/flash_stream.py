"""Trozos de Base empujados por WebSocket: cada transacción preconfirmada y los logs del oráculo, con la hora exacta de llegada.

La consulta del bloque pendiente cada 100 ms (flash_watch.py) llega en promedio ~50 ms tarde más el viaje de ida y vuelta. Con
`eth_subscribe` el servidor empuja cada trozo en cuanto existe: `newFlashblockTransactions` (el hash de cada transacción, una por
mensaje) y `pendingLogs` (los logs de las direcciones pedidas: los feeds del oráculo). Con eso se mide la ventana real entre la
actualización del oráculo y la liquidación del ganador, y la vía rápida (flash_fast.py) decide sin preguntar a la red.

Solo lectura: se suscribe y escucha.
"""

import threading
import time
from collections import OrderedDict

from .shadow_live import log, quantiles
from .ws import WsClient, WsError


class FlashStream:
    def __init__(self, url, addresses=(), on_log=None, wall=time.time, sleep=time.sleep, connect=None, keep=200_000):
        self.url, self.addresses = url, sorted({a.lower() for a in addresses})
        self.on_log, self.wall, self.sleep = on_log, wall, sleep
        self.connect = connect or (lambda: WsClient(url, timeout=15.0, wall=wall).connect())
        self.keep = keep
        self.lock = threading.Lock()
        self.tx_seen = OrderedDict()        # hash -> hora de llegada por WebSocket
        self.alive = False
        self.thread = None
        self.client = None
        self.stats = {"conexiones": 0, "mensajes": 0, "transacciones": 0, "logs": 0, "errores": {}, "suscripciones": {}}
        self.gaps = []                      # ms entre mensajes de transacciones consecutivos (para ver los trozos)
        self._last_tx = None

    def start(self):
        self.alive = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.alive = False
        c = self.client
        if c is not None:
            c.close()

    def seen(self, tx_hash):
        """Hora a la que llegó por WebSocket la transacción, o None."""
        with self.lock:
            return self.tx_seen.get((tx_hash or "").lower())

    def _error(self, key):
        self.stats["errores"][key] = self.stats["errores"].get(key, 0) + 1

    def _loop(self):
        backoff = 1.0
        while self.alive:
            try:
                self.client = self.connect()
                self.stats["conexiones"] += 1
                self._serve(self.client)
                backoff = 1.0
            except (OSError, WsError, ValueError) as e:
                self._error(type(e).__name__ + ": " + str(e)[:60])
            finally:
                if self.client is not None:
                    self.client.close()
                    self.client = None
            if self.alive:
                self.sleep(backoff)
                backoff = min(30.0, backoff * 2)

    def _serve(self, c):
        c.call(1, "eth_subscribe", ["newFlashblockTransactions"])
        if self.addresses:
            c.call(2, "eth_subscribe", ["pendingLogs", {"address": self.addresses}])
        subs = {}
        while self.alive:
            msg, t = c.recv_json()
            self.stats["mensajes"] += 1
            if "id" in msg and msg.get("id") in (1, 2):
                kind = "transacciones" if msg["id"] == 1 else "logs"
                if "error" in msg:
                    self.stats["suscripciones"][kind] = "error: " + str(msg["error"])[:80]
                    log(f"shadow: WebSocket {self.url}: suscripción a {kind} rechazada: {str(msg['error'])[:80]}")
                else:
                    subs[msg.get("result")] = kind
                    self.stats["suscripciones"][kind] = "ok"
                continue
            p = msg.get("params") or {}
            kind = subs.get(p.get("subscription"))
            res = p.get("result")
            if kind == "transacciones":
                h = res.get("hash") if isinstance(res, dict) else res
                if isinstance(h, str):
                    self._tx(h.lower(), t)
            elif kind == "logs" and isinstance(res, dict):
                self.stats["logs"] += 1
                if self.on_log:
                    try:
                        self.on_log(res, t)
                    except Exception as e:                      # la vía rápida nunca debe cortar el flujo
                        self._error("on_log " + type(e).__name__)

    def _tx(self, h, t):
        with self.lock:
            if h not in self.tx_seen:
                self.tx_seen[h] = t
                while len(self.tx_seen) > self.keep:
                    self.tx_seen.popitem(last=False)
            self.stats["transacciones"] += 1
            if self._last_tx is not None and len(self.gaps) < 500_000:
                self.gaps.append(round((t - self._last_tx) * 1000))
            self._last_tx = t

    def report(self):
        with self.lock:
            big = [g for g in self.gaps if g >= 50]               # silencios largos: el paso de un trozo al siguiente
            return {"url": self.url, **{k: (dict(v) if isinstance(v, dict) else v) for k, v in self.stats.items()},
                    "silencio_entre_trozos_ms": quantiles(big)}
