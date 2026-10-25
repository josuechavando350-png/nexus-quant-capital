"""Cliente WebSocket mínimo y flujo de trozos por WebSocket, contra un servidor falso en localhost."""

import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from census_dinero.flash_stream import FlashStream  # noqa: E402
from census_dinero.ws import WsClient, WsError  # noqa: E402
from fakews import FakeWsServer  # noqa: E402


def wait(cond, seconds=3.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class TestWsClient(unittest.TestCase):
    def test_messages_fragments_pings_and_large_frames(self):
        got = {}

        def handler(c):
            op, req = c.recv_json()
            got["req"] = req
            c.frame(0x1, b'{"a": 1}')
            c.frame(0x9, b"hola")                                       # ping: el cliente responde pong
            c.frame(0x1, b'{"b": ', fin=False)                          # mensaje en dos trozos
            c.frame(0x0, b'2}')
            c.frame(0x1, ('{"c": "' + "x" * 70000 + '"}').encode())     # largo de 64 bits
            got["pong"] = c.recv_client()
            c.frame(0x8, b"")
        srv = FakeWsServer(handler)
        ws = WsClient(srv.url, timeout=5).connect()
        ws.call(7, "eth_subscribe", ["newFlashblockTransactions"])
        self.assertEqual(ws.recv_json()[0], {"a": 1})
        self.assertEqual(ws.recv_json()[0], {"b": 2})
        big, t = ws.recv_json()
        self.assertEqual(len(big["c"]), 70000)
        self.assertGreater(t, 0)
        with self.assertRaises(WsError):
            ws.recv()                                                    # el servidor cerró
        ws.close()
        self.assertEqual(got["req"], {"jsonrpc": "2.0", "id": 7, "method": "eth_subscribe", "params": ["newFlashblockTransactions"]})
        self.assertEqual(got["pong"], (0xA, b"hola"))
        srv.close()

    def test_only_subscriptions_can_be_sent(self):
        srv = FakeWsServer(lambda c: c.recv_client())
        ws = WsClient(srv.url, timeout=5).connect()
        for method in ("eth_sendRawTransaction", "eth_sendTransaction", "eth_call"):
            with self.assertRaises(WsError):
                ws.call(1, method, [])
        ws.close()
        srv.close()

    def test_refused_or_forged_handshake(self):
        srv = FakeWsServer(lambda c: None, accept=False)
        with self.assertRaises(WsError):
            WsClient(srv.url, timeout=5).connect()
        srv.close()
        srv = FakeWsServer(lambda c: None, bad_key=True)
        with self.assertRaises(WsError):
            WsClient(srv.url, timeout=5).connect()
        srv.close()
        with self.assertRaises(WsError):
            WsClient("https://x/", timeout=1).connect()


class TestFlashStream(unittest.TestCase):
    LOG = {"address": "0xfeed", "topics": ["0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f", "0x" + "0" * 63 + "5"],
           "blockNumber": "0x10", "transactionHash": "0xabc", "transactionIndex": "0x3"}

    def test_subscribes_records_arrivals_and_forwards_logs(self):
        reqs, done = [], threading.Event()

        def handler(c):
            for _ in range(2):
                reqs.append(c.recv_json()[1])
            c.send_json({"jsonrpc": "2.0", "id": 1, "result": "0xs1"})
            c.send_json({"jsonrpc": "2.0", "id": 2, "result": "0xs2"})
            c.send_json({"jsonrpc": "2.0", "method": "eth_subscription", "params": {"subscription": "0xs1", "result": "0xAA"}})
            c.send_json({"jsonrpc": "2.0", "method": "eth_subscription", "params": {"subscription": "0xs1", "result": {"hash": "0xBB"}}})
            c.send_json({"jsonrpc": "2.0", "method": "eth_subscription", "params": {"subscription": "0xs2", "result": self.LOG}})
            done.wait(3)
        srv = FakeWsServer(handler)
        logs = []
        st = FlashStream(srv.url, ["0xFEED"], on_log=lambda lg, t: logs.append((lg, t))).start()
        self.assertTrue(wait(lambda: logs and st.seen("0xbb")))
        self.assertIsNotNone(st.seen("0xAA"))                              # sin importar mayúsculas
        self.assertIsNone(st.seen("0xcc"))
        self.assertEqual(logs[0][0]["transactionHash"], "0xabc")
        self.assertEqual(reqs[1]["params"], ["pendingLogs", {"address": ["0xfeed"]}])
        rep = st.report()
        self.assertEqual((rep["transacciones"], rep["logs"], rep["suscripciones"]), (2, 1, {"transacciones": "ok", "logs": "ok"}))
        done.set()
        st.stop()
        srv.close()

    def test_a_rejected_subscription_is_reported_and_the_stream_reconnects(self):
        calls = {"n": 0}

        def handler(c):
            calls["n"] += 1
            c.recv_json()
            c.recv_json()
            c.send_json({"jsonrpc": "2.0", "id": 1, "result": "0xs1"})
            c.send_json({"jsonrpc": "2.0", "id": 2, "error": {"code": -32601, "message": "pendingLogs no existe"}})
            c.frame(0x8, b"")                                               # corta: el flujo vuelve a conectarse
        srv = FakeWsServer(handler)
        st = FlashStream(srv.url, ["0xfeed"], sleep=lambda s: time.sleep(0.01)).start()
        self.assertTrue(wait(lambda: calls["n"] >= 2))
        rep = st.report()
        self.assertTrue(rep["suscripciones"]["logs"].startswith("error"))
        self.assertGreaterEqual(rep["conexiones"], 2)
        self.assertTrue(rep["errores"])
        st.stop()
        srv.close()

    def test_a_failing_log_handler_does_not_stop_the_stream(self):
        def handler(c):
            c.recv_json()
            c.recv_json()
            c.send_json({"jsonrpc": "2.0", "id": 2, "result": "0xs2"})
            c.send_json({"jsonrpc": "2.0", "id": 1, "result": "0xs1"})
            c.send_json({"jsonrpc": "2.0", "method": "eth_subscription", "params": {"subscription": "0xs2", "result": self.LOG}})
            c.send_json({"jsonrpc": "2.0", "method": "eth_subscription", "params": {"subscription": "0xs1", "result": "0xdd"}})
            time.sleep(1)

        def boom(lg, t):
            raise KeyError("x")
        srv = FakeWsServer(handler)
        st = FlashStream(srv.url, ["0xfeed"], on_log=boom).start()
        self.assertTrue(wait(lambda: st.seen("0xdd")))
        self.assertIn("on_log KeyError", st.report()["errores"])
        st.stop()
        srv.close()


if __name__ == "__main__":
    unittest.main()
