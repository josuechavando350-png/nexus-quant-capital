"""Transporte con conexión persistente: reutiliza la conexión, se reconecta si el servidor la cierra y conserva los errores HTTP."""

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from census_dinero.rpc import KeepAlive, Rpc, RpcError  # noqa: E402


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.connections = 0
        self.hits = 0
        self.script = {}                     # número de petición -> comportamiento
        self.lock = threading.Lock()

    def get_request(self):
        sock, addr = super().get_request()
        with self.lock:
            self.connections += 1
        return sock, addr


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(n))
        with self.server.lock:
            self.server.hits += 1
            k = self.server.hits
        act = self.server.script.get(k)
        if act == "drop":
            self.connection.close()          # corta sin responder, como un servidor que cerró la conexión inactiva
            self.close_connection = True
            return
        if act == "429":
            data = b'{"error": "slow down"}'
            self.send_response(429)
        elif act == "garbage":
            data = b"no es json"
            self.send_response(200)
        else:
            data = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": f"ok{k}"}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if act == "close":
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(data)


class TestKeepAlive(unittest.TestCase):
    def setUp(self):
        self.srv = Server()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/rpc"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.t = KeepAlive()

    def tearDown(self):
        self.t.close()
        self.srv.shutdown()
        self.srv.server_close()

    def call(self, i=1):
        return self.t(self.url, {"jsonrpc": "2.0", "id": i, "method": "eth_blockNumber", "params": []}, 5)

    def test_one_connection_serves_many_requests(self):
        for i in range(6):
            self.assertEqual(self.call(i)["result"], f"ok{i + 1}")
        self.assertEqual((self.srv.connections, self.srv.hits), (1, 6))

    def test_each_thread_has_its_own_connection(self):
        self.call()
        out = []

        def other():
            out.append(self.call(2))
            self.t.close()
        th = threading.Thread(target=other)
        th.start()
        th.join()
        self.call(3)
        self.assertEqual((self.srv.connections, self.srv.hits), (2, 3))

    def test_server_that_closes_the_connection_is_followed_transparently(self):
        self.srv.script = {2: "close"}
        for i in range(4):
            self.call(i)
        self.assertEqual(self.srv.hits, 4)
        self.assertEqual(self.srv.connections, 2)

    def test_a_dropped_idle_connection_is_retried_once(self):
        self.srv.script = {2: "drop"}
        self.call(1)
        self.assertEqual(self.call(2)["result"], "ok3")               # la petición 2 se cortó; el reintento fue la 3
        self.assertEqual(self.srv.connections, 2)

    def test_http_errors_keep_their_code_and_the_connection_stays_usable(self):
        self.srv.script = {2: "429"}
        self.call(1)
        with self.assertRaises(RpcError) as cm:
            self.call(2)
        self.assertEqual(cm.exception.code, 429)
        self.assertEqual(self.call(3)["result"], "ok3")
        self.assertEqual(self.srv.connections, 1)

    def test_garbage_body_is_an_rpc_error(self):
        self.srv.script = {1: "garbage"}
        with self.assertRaises(RpcError):
            self.call(1)

    def test_unreachable_server_is_an_rpc_error(self):
        t = KeepAlive()
        with self.assertRaises(RpcError):
            t("http://127.0.0.1:1/rpc", {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}, 1)
        t.close()

    def test_works_inside_the_rpc_client(self):
        rpc = Rpc([self.url], transport=self.t, rps=0)
        self.assertEqual(rpc.call("eth_blockNumber", []), "ok1")
        self.assertEqual(rpc.call("eth_blockNumber", []), "ok2")
        self.assertEqual(self.srv.connections, 1)


if __name__ == "__main__":
    unittest.main()
