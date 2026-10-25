"""Cliente JSON-RPC de solo lectura con varios proveedores, reintentos y getLogs adaptativo.

No existe ningún método de firma ni de envío de transacciones: los únicos
métodos permitidos están en ALLOWED_METHODS y cualquier otro se rechaza.

Cada método se enruta por separado: un proveedor que no traza o que no tiene
estado viejo deja de recibir esas llamadas sin dejar de servir las demás, y
eth_getLogs recuerda el rango máximo que acepta cada proveedor.
"""

import json
import random
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ALLOWED_METHODS = frozenset({
    "eth_chainId",
    "eth_blockNumber",
    "eth_getBlockByNumber",
    "eth_getLogs",
    "eth_call",
    "eth_getTransactionByHash",
    "eth_getTransactionReceipt",
    "eth_getCode",
    "debug_traceTransaction",
    "trace_transaction",
})

# Clasificación de errores del proveedor (no del dato).
_ARCHIVE_HINTS = ("missing trie", "header not found", "archive", "pruned", "historical state",
                  "state is not available", "state histories", "not available for block")
_QUOTA_HINTS = ("usage limit", "upgrade", "your plan", "current plan", "quota", "credits", "pricing",
                "subscription", "unauthorized", "api key", "apikey", "forbidden", "payment required",
                "daily limit", "monthly limit")
_NO_METHOD_HINTS = ("method not found", "not supported", "does not exist", "unsupported", "not whitelisted",
                    "not allowed", "disabled", "not available on")
_RATE_HINTS = ("rate limit", "too many request", "capacity", "busy", "429", "slow down", "throttl")
_LOG_SIZE_HINTS = ("results", "response size", "too many logs", "too big", "size limit", "log response")
_LOG_RANGE_HINTS = ("range", "block", "exceed", "too large", "too wide", "limit", "max")
_INF = float("inf")
# Métodos donde `null` significa "este proveedor no lo tiene" (índice de tx podado, nodo sin
# estado viejo), no "no existe": se prueba el siguiente proveedor.
_NULL_IS_MISS = frozenset({"eth_getTransactionByHash", "eth_getTransactionReceipt", "debug_traceTransaction",
                           "trace_transaction"})


class RpcError(Exception):
    def __init__(self, message, code=None, provider_issue=True):
        super().__init__(message)
        self.code = code
        self.provider_issue = provider_issue


class CallReverted(RpcError):
    """eth_call revirtió: es un hecho del contrato, no del proveedor."""

    def __init__(self, message):
        super().__init__(message, code=3, provider_issue=False)


class RangeTooLarge(RpcError):
    """Ningún proveedor acepta un rango de getLogs así de grande; `limit` es el mayor aceptado."""

    def __init__(self, message, limit):
        super().__init__(message)
        self.limit = limit


class BudgetExceeded(Exception):
    """Se acabó el tiempo a mitad de un getLogs: `logs` trae lo leído y `next_block` dónde se quedó."""

    def __init__(self, logs, next_block):
        super().__init__(f"presupuesto de tiempo agotado en el bloque {next_block}")
        self.logs = logs
        self.next_block = next_block


def host_of(url):
    return urllib.parse.urlsplit(url).netloc or url


def http_transport(url, payload, timeout):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={
        "content-type": "application/json",
        "user-agent": "nqc-census-dinero/1.0",
    })
    # Los mensajes llevan solo el host: una URL de secret puede traer la llave en la ruta.
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RpcError(f"HTTP {e.code} en {host_of(url)}", code=e.code) from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        raise RpcError(f"transporte: {type(e).__name__} en {host_of(url)}") from None


def hinted_limit(message, span):
    """Rango máximo que sugiere un error de getLogs ("max 10000 blocks"), o la mitad del pedido."""
    nums = [int(n) for n in re.findall(r"\d+", message.replace(",", ""))]
    nums = [n for n in nums if 100 <= n < span]
    return max(1, min(nums) if nums else span // 2)


class _Bucket:
    def __init__(self, rps):
        self.interval = 1.0 / rps if rps else 0.0
        self.next_at = 0.0
        self.lock = threading.Lock()

    def wait(self, sleep):
        if not self.interval:
            return
        with self.lock:
            now = time.monotonic()
            at = max(now, self.next_at)
            self.next_at = at + self.interval
        if at > now:
            sleep(at - now)


class Rpc:
    def __init__(self, urls, *, timeout=20, retries=2, rps=12, transport=None, sleep=time.sleep,
                 expected_chain_id=None, log_chunk=50_000, max_log_chunk=2_000_000, public=None,
                 trace_concurrency=3):
        urls = [u for u in urls if u]
        if not urls:
            raise ValueError("sin proveedores RPC")
        self.urls = list(dict.fromkeys(urls))
        self.timeout = timeout
        self.retries = retries
        self.transport = transport or http_transport
        self.sleep = sleep
        self.buckets = {u: _Bucket(rps) for u in self.urls}
        self.dead = {}                 # url -> monotonic hasta cuándo evitarlo
        self.strikes = {}              # url -> fallas de transporte seguidas (castigo creciente)
        self.no_method = {}            # (url, método) -> True
        self.log_limit = {}            # url -> mayor rango de getLogs que acepta
        self.stats = {u: {"ok": 0, "err": 0} for u in self.urls}
        self.mstats = {}               # (url, método) -> {"ok", "err", "s", "errors"}
        self.lock = threading.Lock()
        self._id = 0
        self.expected_chain_id = expected_chain_id
        self.log_chunk = log_chunk
        self.max_log_chunk = max_log_chunk
        self.calls = 0
        # Trazar es caro: pocos proveedores lo sirven y responden 429 si se les pide en paralelo.
        self.gates = {m: threading.BoundedSemaphore(trace_concurrency)
                      for m in ("debug_traceTransaction", "trace_transaction")}
        # URLs públicas se muestran tal cual; las de secrets solo como "secretoN (dominio)".
        public = set(self.urls if public is None else public)
        self.labels = {}
        n = 0
        for u in self.urls:
            if u in public:
                self.labels[u] = u
            else:
                n += 1
                self.labels[u] = f"secreto{n} ({'.'.join(host_of(u).split('.')[-2:])})"

    # -- bajo nivel -------------------------------------------------------------
    def label(self, url):
        return self.labels.get(url, host_of(url))

    def scrub(self, text):
        text = str(text)
        for u, lab in self.labels.items():
            if lab != u:
                text = text.replace(u, lab)
        return text

    def _next_id(self):
        with self.lock:
            self._id += 1
            self.calls += 1
            return self._id

    def _m(self, url, mkey):
        st = self.mstats.get((url, mkey))
        if st is None:
            with self.lock:
                st = self.mstats.setdefault((url, mkey), {"ok": 0, "err": 0, "s": 0.0, "errors": {}})
        return st

    def _record(self, url, mkey, ok, secs, err=None):
        """ok: True, False, o None (respuesta que no cuenta a favor ni en contra, p. ej. rango)."""
        st = self._m(url, mkey)
        with self.lock:
            if ok is True:
                self.stats[url]["ok"] += 1
                st["ok"] += 1
            elif ok is False:
                self.stats[url]["err"] += 1
                st["err"] += 1
            st["s"] += secs
            if err:
                key = self.scrub(err)[:100]
                if key in st["errors"] or len(st["errors"]) < 6:
                    st["errors"][key] = st["errors"].get(key, 0) + 1

    def seed(self, url, mkey, ok=0, err=0):
        """Siembra estadísticas por método (lo usa la sonda)."""
        st = self._m(url, mkey)
        with self.lock:
            st["ok"] += ok
            st["err"] += err

    def _score(self, url, mkey):
        st = self.mstats.get((url, mkey))
        if not st or st["ok"] + st["err"] == 0:
            st = self.stats[url]
        return (st["err"] + 1) / (st["ok"] + st["err"] + 2)

    def usable(self, mkey, span=None):
        """Proveedores que pueden recibir el método; descarta los que solo han fallado si otro funciona."""
        out = [u for u in self.urls if not self.no_method.get((u, mkey))]
        if span is not None:
            out = [u for u in out if self.log_limit.get(u, _INF) >= span]
        if any(self._m(u, mkey)["ok"] for u in out):
            out = [u for u in out if self._m(u, mkey)["ok"] or self._m(u, mkey)["err"] < 3]
        return out

    def _order(self, mkey, span=None):
        """Proveedores vivos primero, ordenados por tasa de error en ese método; los castigados al final."""
        now = time.monotonic()
        usable = self.usable(mkey, span)
        alive = sorted((u for u in usable if self.dead.get(u, 0) <= now), key=lambda u: self._score(u, mkey))
        rest = sorted((u for u in usable if self.dead.get(u, 0) > now), key=lambda u: self.dead.get(u, 0))
        return alive + rest

    def max_log_limit(self, alive_only=False):
        """Mayor rango de getLogs aceptado; con alive_only, solo entre proveedores no castigados."""
        now = time.monotonic()
        urls = [u for u in self.urls if not self.no_method.get((u, "eth_getLogs"))]
        if alive_only and any(self.dead.get(u, 0) <= now for u in urls):
            urls = [u for u in urls if self.dead.get(u, 0) <= now]
        lims = [self.log_limit.get(u, _INF) for u in urls]
        return max(lims) if lims else 0

    def call(self, method, params, *, recent=False, prefer=None):
        """`recent`: la llamada apunta a un bloque de la punta de la cadena. Un "header not found" es
        entonces un proveedor atrasado (se prueba el siguiente), no un proveedor sin archivo.
        `prefer`: URL a la que se le pregunta primero (el proveedor que vio el bloque primero)."""
        if method not in ALLOWED_METHODS:
            raise ValueError(f"método no permitido en census de solo lectura: {method}")
        gate = self.gates.get(method)
        if gate is None:
            return self._call(method, params, recent, prefer)
        with gate:
            return self._call(method, params, recent, prefer)

    def _call(self, method, params, recent=False, prefer=None):
        last = None
        mkey = method + ("@archive" if method == "eth_call" and params[1] != "latest" and not recent else "")
        span = None
        if method == "eth_getLogs":
            span = int(params[0]["toBlock"], 16) - int(params[0]["fromBlock"], 16) + 1
        order = self._order(mkey, span)
        if prefer in order:
            order = [prefer] + [u for u in order if u != prefer]
        if not order:
            if span is not None and self.max_log_limit() > 0:
                raise RangeTooLarge(f"ningún proveedor acepta {span} bloques en getLogs", int(self.max_log_limit()))
            raise RpcError(f"ningún proveedor soporta {mkey}")
        range_error = None
        for url in order:
            transport_failures = 0
            for attempt in range(self.retries):
                self.buckets[url].wait(self.sleep)
                payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params}
                t0 = time.monotonic()
                try:
                    resp = self.transport(url, payload, self.timeout)
                except RpcError as e:
                    last = e
                    self._record(url, mkey, False, time.monotonic() - t0, str(e))
                    transport_failures += 1
                    if e.code in (401, 402, 403, 404, 405):
                        self._kill(url, 900)
                        break
                    if e.code == 429:
                        self.sleep(min(10.0, 1.0 * 2 ** attempt) + random.random())
                        continue
                    self.sleep(min(8.0, 0.5 * 2 ** attempt) + random.random() * 0.3)
                    continue
                dt = time.monotonic() - t0
                if "error" in resp and resp["error"] is not None:
                    err = resp["error"]
                    msg = str(err.get("message", err)) if isinstance(err, dict) else str(err)
                    code = err.get("code") if isinstance(err, dict) else None
                    low = msg.lower()
                    last = RpcError(msg, code)
                    archive_issue = any(h in low for h in _ARCHIVE_HINTS)
                    if method == "eth_call" and ("revert" in low or code == 3) and not archive_issue:
                        self._record(url, mkey, True, dt)
                        raise CallReverted(msg)
                    if any(h in low for h in _QUOTA_HINTS):
                        self._record(url, mkey, False, dt, msg)
                        self._kill(url, 900)          # sin cuota o sin permiso: fuera 15 min
                        break
                    if mkey.endswith("@archive") and archive_issue:
                        self._record(url, mkey, False, dt, msg)
                        self.no_method[(url, mkey)] = True
                        break
                    if code == -32601 or any(h in low for h in _NO_METHOD_HINTS):
                        self._record(url, mkey, False, dt, msg)
                        self.no_method[(url, mkey)] = True
                        break
                    if any(h in low for h in _RATE_HINTS):
                        self._record(url, mkey, False, dt, msg)
                        self.sleep(min(10.0, 1.0 * 2 ** attempt) + random.random())
                        continue
                    if method == "eth_getLogs":
                        # Demasiados resultados: achicar solo esta vez. Rango excedido: recordarlo.
                        if any(h in low for h in _LOG_SIZE_HINTS):
                            self._record(url, mkey, None, dt, msg)
                        elif any(h in low for h in _LOG_RANGE_HINTS):
                            self._record(url, mkey, None, dt, msg)
                            with self.lock:
                                self.log_limit[url] = min(self.log_limit.get(url, _INF), hinted_limit(low, span))
                        else:
                            self._record(url, mkey, False, dt, msg)
                        range_error = last            # probar el mismo rango con otro proveedor
                        break
                    self._record(url, mkey, False, dt, msg)
                    break
                if "result" not in resp:
                    last = RpcError(f"respuesta sin result: {str(resp)[:200]}")
                    self._record(url, mkey, False, dt, "respuesta sin result")
                    continue
                if resp["result"] is None and (method in _NULL_IS_MISS or (recent and method == "eth_getBlockByNumber")):
                    last = RpcError(f"{method}: resultado nulo en {host_of(url)}")
                    self._record(url, mkey, False, dt, "resultado nulo")
                    break
                self._record(url, mkey, True, dt)
                if self.strikes.get(url):
                    with self.lock:
                        self.strikes[url] = 0
                return resp["result"]
            if transport_failures >= self.retries:
                with self.lock:
                    self.strikes[url] = self.strikes.get(url, 0) + 1
                    k = self.strikes[url]
                self._kill(url, min(600, 30 * 2 ** (k - 1)))
        if range_error is not None:
            raise range_error                       # get_logs lo maneja reduciendo el rango
        raise last or RpcError(f"{method} falló en todos los proveedores")

    def method_ok(self, mkey):
        """Llamadas exitosas de un método entre todos los proveedores."""
        return sum(st["ok"] for (u, m), st in list(self.mstats.items()) if m == mkey)

    def method_err(self, mkey):
        return sum(st["err"] for (u, m), st in list(self.mstats.items()) if m == mkey)

    def dead_for_all(self, method):
        """True si ningún proveedor soporta el método (todos lo rechazaron como no disponible)."""
        return all(self.no_method.get((u, method)) for u in self.urls)

    def _kill(self, url, seconds):
        with self.lock:
            self.dead[url] = max(self.dead.get(url, 0), time.monotonic() + seconds)

    def drop(self, url):
        """Saca un proveedor de la rotación (la sonda lo encontró muerto o en otra cadena)."""
        if url in self.urls and len(self.urls) > 1:
            self.urls.remove(url)

    def report(self):
        """Estadísticas por proveedor y método, con URLs de secrets ocultas."""
        out = {}
        for u in list(self.labels):
            methods = {}
            for (url, m), st in sorted(self.mstats.items()):
                if url != u or not (st["ok"] or st["err"] or st["errors"]):
                    continue
                n = st["ok"] + st["err"]
                methods[m] = {"ok": st["ok"], "err": st["err"],
                              "ms_prom": round(1000 * st["s"] / n) if n else None,
                              "errores": dict(st["errors"])}
            lim = self.log_limit.get(u)
            out[self.label(u)] = {"ok": self.stats.get(u, {}).get("ok", 0), "err": self.stats.get(u, {}).get("err", 0),
                                  "en_rotacion": u in self.urls,
                                  "getlogs_max": None if lim is None or lim == _INF else int(lim),
                                  "sin_metodo": sorted(m for (url, m), v in self.no_method.items() if url == u and v),
                                  "metodos": methods}
        return out

    # -- utilidades -------------------------------------------------------------
    def chain_id(self):
        return int(self.call("eth_chainId", []), 16)

    def check_chain(self):
        if self.expected_chain_id is None:
            return
        def probe(url):
            try:
                resp = self.transport(url, {"jsonrpc": "2.0", "id": self._next_id(), "method": "eth_chainId",
                                            "params": []}, min(self.timeout, 10))
                return int(resp["result"], 16) == self.expected_chain_id
            except Exception:  # noqa: BLE001 - un proveedor caído simplemente se descarta
                return False
        with ThreadPoolExecutor(max_workers=min(16, len(self.urls))) as ex:
            flags = list(ex.map(probe, self.urls))
        good = [u for u, ok in zip(self.urls, flags) if ok]
        if not good:
            raise RpcError(f"ningún proveedor responde con chainId {self.expected_chain_id}")
        self.urls = good

    def block_number(self):
        return int(self.call("eth_blockNumber", []), 16)

    def block(self, number, recent=False, prefer=None):
        tag = number if isinstance(number, str) else hex(number)
        b = self.call("eth_getBlockByNumber", [tag, False], recent=recent, prefer=prefer)
        if b is None:
            raise RpcError(f"bloque {number} no disponible")
        return b

    def eth_call(self, to, data, block="latest", recent=False, prefer=None):
        tag = block if isinstance(block, str) else hex(block)
        return self.call("eth_call", [{"to": to, "data": data}, tag], recent=recent, prefer=prefer)

    def get_logs(self, address, topics, from_block, to_block, on_progress=None, deadline=None):
        """getLogs que parte el rango cuando el proveedor lo rechaza y lo agranda cuando funciona."""
        out = []
        start = from_block
        known = [self.log_limit[u] for u in self.urls if u in self.log_limit and self.log_limit[u] != _INF]
        chunk = int(max(known)) if known else self.log_chunk
        failures = 0
        while start <= to_block:
            if deadline is not None and time.monotonic() > deadline:
                raise BudgetExceeded(out, start)
            # Tope: el mayor rango entre los proveedores vivos; un castigado no arrastra el tamaño.
            cap = self.max_log_limit(alive_only=True)
            chunk = int(max(1, min(chunk, cap, self.max_log_chunk)))
            end = min(to_block, start + chunk - 1)
            flt = {"fromBlock": hex(start), "toBlock": hex(end), "topics": topics}
            if address:
                flt["address"] = address
            try:
                logs = self.call("eth_getLogs", [flt])
            except RangeTooLarge as e:
                failures += 1
                if failures > 40 or e.limit < 1:
                    raise
                chunk = max(1, min(chunk // 2, int(e.limit)))
                continue
            except RpcError:
                failures += 1
                if chunk <= 1 or failures > 40:
                    raise
                chunk = max(1, chunk // 4 if failures > 3 else chunk // 2)
                if failures > 3:
                    self.sleep(min(10.0, 0.5 * failures))
                continue
            failures = 0
            out.extend(logs)
            if on_progress:
                on_progress(end, len(out), chunk)
            start = end + 1
            if len(logs) < 2000:
                chunk = min(self.max_log_chunk, int(chunk * 1.5) + 1)
        return out

    def block_at_or_after(self, timestamp, lo, hi):
        """Primer bloque con timestamp >= timestamp (búsqueda binaria)."""
        while lo < hi:
            mid = (lo + hi) // 2
            if int(self.block(mid)["timestamp"], 16) < timestamp:
                lo = mid + 1
            else:
                hi = mid
        return lo
