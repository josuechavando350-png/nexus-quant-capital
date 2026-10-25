"""Observador de Flashblocks: sigue el bloque pendiente de un RPC con preconfirmaciones y anota CUÁNDO apareció cada transacción.

Base publica cada bloque en ~10 trozos de ~200 ms antes de sellarlo. Con una consulta rápida al bloque `pending` cada ~50 ms se ve
en qué momento (y en qué trozo) entró cada transacción. Cuando el bloque se sella, con eso se mide la reacción real de los
ganadores: ¿cuántos milisegundos / trozos después de que entró la actualización del oráculo apareció su liquidación?

Solo lectura. No decide nada.
"""

import threading
import time
from collections import OrderedDict

from .shadow_live import quantiles
from .sonda import raw_call


class FlashWatcher:
    def __init__(self, rpc, url, interval=0.05, keep_blocks=8, wall=time.time, mono=time.monotonic, sleep=time.sleep):
        self.rpc, self.url, self.interval, self.keep = rpc, url, interval, keep_blocks
        self.wall, self.mono, self.sleep = wall, mono, sleep
        self.lock = threading.Lock()
        self.blocks = OrderedDict()         # número -> {"t0", "first": {hash: (hora, trozo)}, "chunks": [(hora, transacciones)]}
        self.alive = False
        self.thread = None
        self.samples = 0
        self.errors = {}
        self.rtt = []

    def start(self):
        self.alive = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.alive = False

    def _loop(self):
        while self.alive:
            t0 = self.mono()
            ok, res, dt = raw_call(self.rpc, self.url, "eth_getBlockByNumber", ["pending", False], 3)
            t = self.wall()                                  # cuándo llegó la respuesta: antes no sabíamos lo que trae
            if ok and isinstance(res, dict) and res.get("number") and isinstance(res.get("transactions"), list):
                try:
                    self.ingest(t, int(res["number"], 16), res["transactions"])
                    self.samples += 1
                    if len(self.rtt) < 200_000:
                        self.rtt.append(round(dt * 1000))
                except (TypeError, ValueError):
                    self.errors["respuesta ilegible"] = self.errors.get("respuesta ilegible", 0) + 1
            else:
                key = (str(res)[:80] if not ok else "pending sin bloque")
                self.errors[key] = self.errors.get(key, 0) + 1
            self.sleep(max(0.0, self.interval - (self.mono() - t0)))

    def ingest(self, t, number, txs):
        """Registra una foto del bloque pendiente: las transacciones nuevas reciben la hora y el número de trozo."""
        if not txs:
            return
        with self.lock:
            b = self.blocks.get(number)
            if b is None:
                b = self.blocks[number] = {"t0": t, "first": {}, "chunks": [], "n": 0, "last": None, "primera_foto": len(txs)}
                while len(self.blocks) > self.keep:
                    self.blocks.popitem(last=False)
            if len(txs) == b["n"] and txs[-1] == b["last"]:
                return                                     # nada nuevo desde la foto anterior (lo más común)
            first = b["first"]
            chunk, new = len(b["chunks"]), 0
            for h in txs:
                if h not in first:
                    first[h] = (t, chunk)
                    new += 1
            b["n"], b["last"] = len(txs), txs[-1]
            if new:
                b["chunks"].append((t, len(txs)))

    def seen(self, number, tx_hash):
        """(hora de la primera foto en que apareció, número de trozo) o None si nunca se vio."""
        with self.lock:
            b = self.blocks.get(number)
            return None if b is None else b["first"].get(tx_hash)

    def block_start(self, number):
        with self.lock:
            b = self.blocks.get(number)
            return None if b is None else b["t0"]

    def first_photo_size(self, number):
        """Cuántas transacciones traía el bloque en la primera foto: si es mucho, se empezó a mirar con el bloque ya avanzado."""
        with self.lock:
            b = self.blocks.get(number)
            return None if b is None else b["primera_foto"]

    def block_chunks(self, number):
        with self.lock:
            b = self.blocks.get(number)
            return [] if b is None else list(b["chunks"])

    def report(self):
        gaps = []
        with self.lock:
            for b in self.blocks.values():
                ts = [c[0] for c in b["chunks"]]
                gaps += [round((y - x) * 1000) for x, y in zip(ts, ts[1:])]
        return {"url": self.url, "fotos": self.samples, "errores": dict(self.errors), "rtt_ms": quantiles(self.rtt),
                "intervalo_entre_trozos_ms": quantiles(gaps), "intervalo_de_consulta_ms": round(self.interval * 1000)}
