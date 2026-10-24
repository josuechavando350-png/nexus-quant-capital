"""Sonda de proveedores: qué puede hacer cada RPC antes de recolectar.

Mide en paralelo, por proveedor: latencia, rango máximo que acepta eth_getLogs,
si responde eth_call en el bloque más viejo de la ventana (nodo de archivo) y si
traza una transacción vieja y una reciente. El resultado queda en meta.json y
siembra las estadísticas del cliente para que cada método vaya solo a quien lo
sirve. Solo usa métodos de lectura de rpc.ALLOWED_METHODS.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from .rpc import _NO_METHOD_HINTS, ALLOWED_METHODS, RpcError

LOG_RANGES = (1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 2_000_000)
TRACE_METHODS = ("debug_traceTransaction", "trace_transaction")
SLOW_S = 8.0          # un proveedor que tarda más que esto en eth_blockNumber no entra a la rotación


def trace_params(method, tx_hash):
    if method == "debug_traceTransaction":
        return [tx_hash, {"tracer": "callTracer", "timeout": "20s"}]
    return [tx_hash]


def raw_call(rpc, url, method, params, timeout):
    """Una llamada directa a un proveedor, sin enrutamiento: (ok, resultado o mensaje, segundos)."""
    if method not in ALLOWED_METHODS:
        raise ValueError(f"método no permitido en census de solo lectura: {method}")
    payload = {"jsonrpc": "2.0", "id": rpc._next_id(), "method": method, "params": params}
    t0 = time.monotonic()
    try:
        resp = rpc.transport(url, payload, timeout)
    except RpcError as e:
        return False, rpc.scrub(e)[:160], time.monotonic() - t0
    dt = time.monotonic() - t0
    if not isinstance(resp, dict):
        return False, "respuesta inválida", dt
    if resp.get("error") is not None:
        err = resp["error"]
        msg = str(err.get("message", err)) if isinstance(err, dict) else str(err)
        return False, rpc.scrub(msg)[:160], dt
    if "result" not in resp:
        return False, "respuesta sin result", dt
    return True, resp["result"], dt


def probe_provider(rpc, url, plan, timeout=25):
    out = {"proveedor": rpc.label(url)}
    ok, res, dt = raw_call(rpc, url, "eth_blockNumber", [], 10)
    out["vivo"] = bool(ok) and dt <= SLOW_S
    out["ms"] = round(1000 * dt)
    if not ok or dt > SLOW_S:
        out["error"] = res if not ok else f"lento: {dt:.1f} s para eth_blockNumber"
        return out
    try:
        head = int(res, 16)
    except (TypeError, ValueError):
        out["vivo"] = False
        out["error"] = "eth_blockNumber inválido"
        return out
    out["atraso_bloques"] = max(0, plan["end"] - head) if head < plan["end"] else 0

    # getLogs: el rango más grande que acepta, sobre el mismo filtro que usa el census. Si
    # rechaza el primero por ritmo o tiempo, se prueba una vez con 100 bloques tras una pausa.
    best, fail = 0, None
    ranges = list(LOG_RANGES)
    while ranges:
        span = ranges.pop(0)
        lo = max(0, plan["end"] - span + 1)
        flt = {"fromBlock": hex(lo), "toBlock": hex(plan["end"]), "topics": plan["log_topics"],
               "address": plan["log_address"]}
        ok, res, dt = raw_call(rpc, url, "eth_getLogs", [flt], timeout)
        if not ok or not isinstance(res, list):
            fail = res if not ok else "respuesta no es lista"
            transient = any(h in str(fail).lower() for h in ("429", "408", "timeout", "transporte", "rate"))
            if best == 0 and span == LOG_RANGES[0] and transient:
                time.sleep(2)
                ranges = [100]
                continue
            break
        best = span
        out["getlogs_ms"] = round(1000 * dt)
        if lo == 0 or span >= plan["max_span"]:
            break
    out["getlogs_max"] = best
    if fail:
        out["getlogs_error"] = fail

    # Archivo: precio del oráculo de Aave en el bloque más viejo que se va a consultar.
    if plan.get("archive_call"):
        to, data, block = plan["archive_call"]
        ok, res, dt = raw_call(rpc, url, "eth_call", [{"to": to, "data": data}, hex(block)], timeout)
        out["archivo"] = bool(ok and isinstance(res, str) and len(res) > 2 and int(res, 16) > 0)
        if not out["archivo"]:
            out["archivo_error"] = res if not ok else f"resultado {str(res)[:40]}"

    # Trazas: una transacción vieja (dos intentos, hay balanceadores con nodos mixtos) y una reciente.
    for method in TRACE_METHODS:
        for age, tx_hash, tries in (("vieja", plan.get("old_tx"), 2), ("reciente", plan.get("new_tx"), 1)):
            if not tx_hash:
                continue
            got, err = 0, None
            for _ in range(tries):
                ok, res, dt = raw_call(rpc, url, method, trace_params(method, tx_hash), timeout)
                if ok and res:
                    got += 1
                else:
                    err = res if not ok else "resultado vacío"
                    if any(h in str(err).lower() for h in _NO_METHOD_HINTS) or "-32601" in str(err):
                        break
            out[f"{method}_{age}"] = {"ok": got, "de": tries, **({"error": err} if err else {})}
    return out


def apply(rpc, results, urls):
    """Siembra el cliente con lo que la sonda encontró."""
    for url, r in zip(urls, results):
        if not r.get("vivo"):
            rpc.drop(url)
            continue
        if not r.get("getlogs_max"):
            rpc.no_method[(url, "eth_getLogs")] = True
        elif r.get("getlogs_error"):
            rpc.log_limit[url] = r["getlogs_max"]      # sin error: aceptó toda la ventana, sin límite
        rpc.seed(url, "eth_call@archive", ok=1 if r.get("archivo") else 0, err=0 if r.get("archivo") else 3)
        for method in TRACE_METHODS:
            v = r.get(f"{method}_vieja")
            if not v:
                continue
            err = str(v.get("error", "")).lower()
            if not v["ok"] and (any(h in err for h in _NO_METHOD_HINTS) or "-32601" in err):
                rpc.no_method[(url, method)] = True
            rpc.seed(url, method, ok=v["ok"], err=(v["de"] - v["ok"]) * 2)


def sample_tx(rpc, block, limit=6):
    """Hash de una transacción de usuario cerca de `block` (la del medio del bloque)."""
    for n in range(block, block + limit):
        try:
            txs = rpc.block(n).get("transactions") or []
        except RpcError:
            continue
        txs = [t if isinstance(t, str) else t.get("hash") for t in txs]
        if len(txs) >= 2:
            return txs[len(txs) // 2]
    return None


def run(rpc, plan, workers=16):
    urls = list(rpc.urls)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(urls)))) as ex:
        results = list(ex.map(lambda u: probe_provider(rpc, u, plan), urls))
    apply(rpc, results, urls)
    return results


def summary_lines(results):
    lines = ["proveedor | ms | getLogs máx | archivo | debug viejo | trace viejo"]
    for r in results:
        if not r.get("vivo"):
            lines.append(f"{r['proveedor']} | caído: {r.get('error', '')[:60]}")
            continue
        def tr(m):
            v = r.get(f"{m}_vieja")
            return "—" if not v else f"{v['ok']}/{v['de']}"
        lines.append(f"{r['proveedor']} | {r['ms']} | {r.get('getlogs_max', 0):,} | "
                     f"{'sí' if r.get('archivo') else 'no'} | {tr('debug_traceTransaction')} | {tr('trace_transaction')}")
    return lines
