"""Sonda de Flashblocks (preconfirmaciones de Base). Solo lectura.

Base arma cada bloque de 2 s en ~10 trozos de ~200 ms (flashblocks) y los publica antes de sellar el bloque.
Quien los sigue ve una transacción (por ejemplo la actualización de un oráculo) hasta ~1.8 s antes que quien
espera el bloque. Esta sonda pregunta por el bloque `pending` de un RPC con preconfirmaciones y mide:

  - si responde y con qué latencia,
  - si el bloque pendiente avanza (número de bloque y transacciones vistas) y a qué cadencia,
  - cuánto antes del bloque sellado aparecen las transacciones.

No decide nada ni envía nada: dice si seguir el bloque pendiente por HTTP es viable desde donde corre el Shadow.
"""

import threading
import time
from collections import Counter

from .shadow_live import quantiles
from .sonda import raw_call

PRECONF_URLS = ("https://mainnet-preconf.base.org",)


def summarize(samples, errors):
    """samples: [(hora, número de bloque pendiente, transacciones, segundos de la llamada)] en orden."""
    out = {"llamadas": len(samples) + sum(errors.values()), "errores": dict(errors.most_common(3)),
           "rtt_ms": quantiles([round(s[3] * 1000) for s in samples])}
    if not samples:
        return out
    numbers = sorted({s[1] for s in samples})
    changes, last = [], None
    for t, n, k, _ in samples:
        if last is not None and n == last[1] and k > last[2]:
            changes.append(t)                         # llegó un trozo nuevo al mismo bloque pendiente
        last = (t, n, k)
    gaps = [round((b - a) * 1000) for a, b in zip(changes, changes[1:])]
    per_block = {}
    for t, n, k, _ in samples:
        per_block[n] = max(per_block.get(n, 0), k)
    out.update({"bloques_pendientes": numbers, "trozos_nuevos_vistos": len(changes), "intervalo_entre_trozos_ms": quantiles(gaps),
                "transacciones_max_por_bloque": per_block})
    return out


def probe(rpc, urls=PRECONF_URLS, seconds=20.0, interval=0.1, wall=time.time, mono=time.monotonic, sleep=time.sleep):
    """Consulta `eth_getBlockByNumber("pending")` cada `interval` s durante `seconds` s en cada URL (un hilo por URL)."""
    results = {}

    def loop(url):
        samples, errors = [], Counter()
        end = mono() + seconds
        while mono() < end:
            t0 = mono()
            ok, res, dt = raw_call(rpc, url, "eth_getBlockByNumber", ["pending", False], 5)
            if ok and isinstance(res, dict) and res.get("number"):
                try:
                    samples.append((wall(), int(res["number"], 16), len(res.get("transactions") or []), dt))
                except (TypeError, ValueError):
                    errors["respuesta ilegible"] += 1
            else:
                errors[str(res)[:100] if not ok else "pending sin bloque"] += 1
            sleep(max(0.0, interval - (mono() - t0)))
        results[url] = summarize(samples, errors)
    threads = [threading.Thread(target=loop, args=(u,), daemon=True) for u in urls]
    for t in threads:
        t.start()
    for t in threads:
        t.join(seconds + 30)
    # Referencia: cuántos bloques va por delante el pendiente del último sellado que ven los RPC normales.
    ok, res, _ = raw_call(rpc, rpc.urls[0], "eth_blockNumber", [], 5)
    head = int(res, 16) if ok else None
    for r in results.values():
        r["bloque_sellado_al_final"] = head
    return results
