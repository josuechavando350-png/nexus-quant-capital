"""Cliente JSON-RPC de solo lectura con varios proveedores, reintentos y getLogs adaptativo.

No existe ningún método de firma ni de envío de transacciones: los únicos
métodos permitidos están en ALLOWED_METHODS y cualquier otro se rechaza.
"""

import json
import random
import threading
import time
import urllib.error
import urllib.request

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


class RpcError(Exception):
    def __init__(self, message, code=None, provider_issue=True):
        super().__init__(message)
        self.code = code
        self.provider_issue = provider_issue


class CallReverted(RpcError):
    """eth_call revirtió: es un hecho del contrato, no del proveedor."""

    def __init__(self, message):
        super().__init__(message, code=3, provider_issue=False)


def http_transport(url, payload, timeout):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={
        "content-type": "application/json",
        "user-agent": "nqc-census-dinero/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RpcError(f"HTTP {e.code} en {url}", code=e.code) from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        raise RpcError(f"transporte: {e} en {url}") from None


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
                 expected_chain_id=None, log_chunk=50_000, max_log_chunk=2_000_000):
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
        self.no_method = {}            # (url, method) -> True
        self.stats = {u: {"ok": 0, "err": 0} for u in self.urls}
        self.lock = threading.Lock()
        self._id = 0
        self.expected_chain_id = expected_chain_id
        self.log_chunk = log_chunk
        self.max_log_chunk = max_log_chunk
        self.calls = 0

    # -- bajo nivel -------------------------------------------------------------
    def _next_id(self):
        with self.lock:
            self._id += 1
            self.calls += 1
            return self._id

    def _score(self, url):
        st = self.stats[url]
        return (st["err"] + 1) / (st["ok"] + st["err"] + 2)

    def _order(self, method):
        """Proveedores vivos primero, ordenados por tasa de error; los castigados al final."""
        now = time.monotonic()
        usable = [u for u in self.urls if not self.no_method.get((u, method))]
        alive = sorted((u for u in usable if self.dead.get(u, 0) <= now), key=self._score)
        rest = sorted((u for u in usable if self.dead.get(u, 0) > now), key=lambda u: self.dead.get(u, 0))
        return alive + rest

    def call(self, method, params):
        if method not in ALLOWED_METHODS:
            raise ValueError(f"método no permitido en census de solo lectura: {method}")
        last = None
        mkey = method + ("@archive" if method == "eth_call" and params[1] != "latest" else "")
        order = self._order(mkey)
        if not order:
            raise RpcError(f"ningún proveedor soporta {mkey}")
        range_error = None
        for url in order:
            transport_failures = 0
            for attempt in range(self.retries):
                self.buckets[url].wait(self.sleep)
                payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params}
                try:
                    resp = self.transport(url, payload, self.timeout)
                except RpcError as e:
                    last = e
                    self.stats[url]["err"] += 1
                    transport_failures += 1
                    if e.code in (401, 402, 403, 404, 405):
                        self._kill(url, 900)
                        break
                    if e.code == 429:
                        self.sleep(min(10.0, 1.0 * 2 ** attempt) + random.random())
                        continue
                    self.sleep(min(8.0, 0.5 * 2 ** attempt) + random.random() * 0.3)
                    continue
                if "error" in resp and resp["error"] is not None:
                    err = resp["error"]
                    msg = str(err.get("message", err)) if isinstance(err, dict) else str(err)
                    code = err.get("code") if isinstance(err, dict) else None
                    low = msg.lower()
                    self.stats[url]["err"] += 1
                    last = RpcError(msg, code)
                    archive_issue = any(h in low for h in _ARCHIVE_HINTS)
                    if method == "eth_call" and ("revert" in low or code == 3) and not archive_issue:
                        raise CallReverted(msg)
                    if any(h in low for h in _QUOTA_HINTS):
                        self._kill(url, 900)          # sin cuota o sin permiso: fuera 15 min
                        break
                    if mkey.endswith("@archive") and archive_issue:
                        self.no_method[(url, mkey)] = True
                        break
                    if code == -32601 or any(h in low for h in _NO_METHOD_HINTS):
                        self.no_method[(url, mkey)] = True
                        break
                    if any(h in low for h in _RATE_HINTS):
                        self.sleep(min(10.0, 1.0 * 2 ** attempt) + random.random())
                        continue
                    if method == "eth_getLogs":
                        range_error = last            # probar el mismo rango con otro proveedor
                    break
                if "result" not in resp:
                    last = RpcError(f"respuesta sin result: {str(resp)[:200]}")
                    self.stats[url]["err"] += 1
                    continue
                self.stats[url]["ok"] += 1
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

    def dead_for_all(self, method):
        """True si ningún proveedor soporta el método (todos lo rechazaron como no disponible)."""
        return all(self.no_method.get((u, method)) for u in self.urls)

    def _kill(self, url, seconds):
        with self.lock:
            self.dead[url] = max(self.dead.get(url, 0), time.monotonic() + seconds)

    # -- utilidades -------------------------------------------------------------
    def chain_id(self):
        return int(self.call("eth_chainId", []), 16)

    def check_chain(self):
        if self.expected_chain_id is None:
            return
        good = []
        for url in self.urls:
            try:
                resp = self.transport(url, {"jsonrpc": "2.0", "id": self._next_id(), "method": "eth_chainId",
                                            "params": []}, self.timeout)
                if int(resp["result"], 16) == self.expected_chain_id:
                    good.append(url)
            except Exception:  # noqa: BLE001 - un proveedor caído simplemente se descarta
                continue
        if not good:
            raise RpcError(f"ningún proveedor responde con chainId {self.expected_chain_id}")
        self.urls = good

    def block_number(self):
        return int(self.call("eth_blockNumber", []), 16)

    def block(self, number):
        tag = number if isinstance(number, str) else hex(number)
        b = self.call("eth_getBlockByNumber", [tag, False])
        if b is None:
            raise RpcError(f"bloque {number} no disponible")
        return b

    def eth_call(self, to, data, block="latest"):
        tag = block if isinstance(block, str) else hex(block)
        return self.call("eth_call", [{"to": to, "data": data}, tag])

    def get_logs(self, address, topics, from_block, to_block, on_progress=None):
        """getLogs que parte el rango cuando el proveedor lo rechaza y lo agranda cuando funciona."""
        out = []
        start = from_block
        chunk = self.log_chunk
        failures = 0
        while start <= to_block:
            end = min(to_block, start + chunk - 1)
            flt = {"fromBlock": hex(start), "toBlock": hex(end), "topics": topics}
            if address:
                flt["address"] = address
            try:
                logs = self.call("eth_getLogs", [flt])
            except RpcError:
                failures += 1
                if chunk <= 1 or failures > 40:
                    raise
                chunk = max(1, chunk // 4 if failures > 3 else chunk // 2)
                continue
            failures = 0
            out.extend(logs)
            if on_progress:
                on_progress(end)
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
