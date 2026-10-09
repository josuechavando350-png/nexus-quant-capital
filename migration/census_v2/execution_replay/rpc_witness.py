#!/usr/bin/env python3
"""Finite, read-only fork RPC recorder; replay mode never opens an upstream URL."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import threading
import time
from datetime import datetime, timezone
import urllib.request
import urllib.error

PREVIOUS = 25938047
WINNER = 25938048
HASHES = {
    PREVIOUS: "0x42cf44b75185587327a1aa8fc859cc5f49a639e7256547511430d6068b6f09ab",
    WINNER: "0xf143f9988199037938e4dff57aaf24301a4c26770aefc0ec64774954cbf2dbe4",
}
ENDPOINT = "https://eth.drpc.org"
STATE_METHODS = {"eth_getBalance": 1, "eth_getTransactionCount": 1,
                 "eth_getCode": 1, "eth_getStorageAt": 2}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def upstream_params(method, params):
    if method == "eth_chainId" and params == []:
        return params
    if method == "eth_getBlockByNumber" and len(params) == 2:
        if params[0] in {hex(PREVIOUS), hex(WINNER)} and params[1] is False:
            return params
    if method in STATE_METHODS:
        index = STATE_METHODS[method]
        if len(params) != index + 1 or params[index] != hex(PREVIOUS):
            raise ValueError("unapproved state block")
        address = params[0]
        if not isinstance(address, str) or len(address) != 42 or not address.startswith("0x"):
            raise ValueError("invalid address")
        int(address[2:], 16)
        if method == "eth_getStorageAt":
            slot = params[1]
            if not isinstance(slot, str) or not slot.startswith("0x") or len(slot) > 66:
                raise ValueError("invalid slot")
            int(slot[2:], 16)
        result = list(params)
        result[index] = {"blockHash": HASHES[PREVIOUS], "requireCanonical": True}
        return result
    raise ValueError("method or parameters outside read-only scope")


def validate_result(method, params, result):
    if method == "eth_chainId":
        if result != "0x1":
            raise ValueError("wrong chain")
    elif method == "eth_getBlockByNumber":
        number = int(params[0], 16)
        if not isinstance(result, dict) or result.get("hash") != HASHES[number] or result.get("number") != params[0]:
            raise ValueError("historical header mismatch")
        if number == WINNER and result.get("parentHash") != HASHES[PREVIOUS]:
            raise ValueError("broken parent link")
    elif not isinstance(result, str) or not result.startswith("0x"):
        raise ValueError("invalid state result")


class Witness:
    def __init__(self, directory, replay=None, max_requests=2000, max_seconds=1800, interval=1.1):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.replay = replay is not None
        self.cache = {}
        self.max_requests = max_requests
        self.deadline = time.monotonic() + max_seconds
        self.interval = interval
        self.last_request = 0.0
        self.count = 0
        self.failed = None
        self.lock = threading.Lock()
        if replay is not None:
            for raw in Path(replay).read_bytes().splitlines():
                row = json.loads(raw)
                request = row["request_utf8"].encode()
                response = row["response_utf8"].encode()
                if sha(request) != row["request_sha256"] or sha(response) != row["response_sha256"]:
                    raise ValueError("witness bytes mismatch")
                req, res = json.loads(request), json.loads(response)
                method, params = row["client_method"], row["client_params"]
                if req != {"jsonrpc": "2.0", "id": row["sequence"], "method": method,
                           "params": upstream_params(method, params)}:
                    raise ValueError("witness request binding mismatch")
                if row["http_status"] != 200 or res.get("id") != req["id"] or "error" in res:
                    raise ValueError("failed RPC witness")
                validate_result(method, params, res.get("result"))
                key = canonical([method, params])
                if key in self.cache:
                    raise ValueError("duplicate witness key")
                self.cache[key] = res["result"]

    def call(self, method, params):
        with self.lock:
            # Validate even cached requests; there are no write methods in either mode.
            up = upstream_params(method, params)
            key = canonical([method, params])
            if self.failed:
                raise RuntimeError("witness halted: " + self.failed)
            if key in self.cache:
                result, source = self.cache[key], "retained_response"
            elif self.replay:
                raise ValueError("offline witness miss: " + key)
            else:
                if self.count >= self.max_requests or time.monotonic() >= self.deadline:
                    self.failed = "finite acquisition budget exhausted"
                    raise RuntimeError(self.failed)
                time.sleep(max(0.0, self.interval - (time.monotonic() - self.last_request)))
                self.count += 1
                request = canonical({"jsonrpc": "2.0", "id": self.count, "method": method, "params": up}).encode()
                row = {"sequence": self.count, "client_method": method, "client_params": params,
                       "endpoint": ENDPOINT, "request_utf8": request.decode(),
                       "request_sha256": sha(request), "sent_at": now()}
                try:
                    self.last_request = time.monotonic()
                    req = urllib.request.Request(ENDPOINT, data=request, headers={"Content-Type": "application/json"})
                    try:
                        response = urllib.request.urlopen(req, timeout=35)
                    except urllib.error.HTTPError as error:
                        response = error
                    with response:
                        raw = response.read(8_000_001)
                        row.update(http_status=response.status, headers=list(response.headers.items()),
                                   received_at=now(), response_utf8=raw.decode("utf-8"), response_sha256=sha(raw))
                    if len(raw) > 8_000_000 or row["http_status"] != 200:
                        raise ValueError("HTTP or response-size failure")
                    parsed = json.loads(raw)
                    if parsed.get("id") != self.count or "error" in parsed:
                        raise ValueError("JSON-RPC failure")
                    result = parsed["result"]
                    validate_result(method, params, result)
                    self.cache[key] = result
                    source = "new_network_response"
                except Exception as error:
                    row["failure"] = str(error)
                    self.failed = str(error)
                    raise
                finally:
                    with (self.directory / "upstream.jsonl").open("a") as f:
                        f.write(canonical(row) + "\n")
            with (self.directory / "requests.jsonl").open("a") as f:
                f.write(canonical({"method": method, "params": params, "source": source,
                                   "served_at": now(), "result_sha256": sha(canonical(result).encode())}) + "\n")
            return result


def serve(witness, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = {}
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 20000:
                    raise ValueError("request size")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                    raise ValueError("single JSON-RPC request required")
                result = witness.call(request["method"], request["params"])
                body = {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
            except Exception as error:
                body = {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
                        "error": {"code": -32000, "message": str(error)}}
            raw = canonical(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--replay")
    parser.add_argument("--port", type=int, default=18545)
    args = parser.parse_args()
    witness = Witness(args.out, replay=args.replay)
    server = serve(witness, args.port)
    print(server.server_address, flush=True)
    threading.Event().wait()
