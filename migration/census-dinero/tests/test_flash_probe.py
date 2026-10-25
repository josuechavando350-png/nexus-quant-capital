"""Sonda de Flashblocks contra el bloque pendiente de la cadena falsa."""

import os
import sys
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from census_dinero import flash_probe as fp  # noqa: E402
from census_dinero.rpc import Rpc  # noqa: E402
import fakemorpho as fm  # noqa: E402


class FakeTime:
    def __init__(self):
        self.t = 1000.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class TestSummarize(unittest.TestCase):
    def test_cadence_and_blocks(self):
        # el mismo bloque pendiente gana transacciones cada 200 ms; luego pasa al siguiente
        samples = [(1000.0 + 0.1 * i, 10 if i < 12 else 11, i // 2 if i < 12 else 0, 0.05) for i in range(16)]
        s = fp.summarize(samples, Counter())
        self.assertEqual(s["bloques_pendientes"], [10, 11])
        self.assertEqual(s["trozos_nuevos_vistos"], 5)
        self.assertEqual(s["intervalo_entre_trozos_ms"]["p50"], 200)
        self.assertEqual(s["transacciones_max_por_bloque"][10], 5)
        self.assertEqual(s["rtt_ms"]["p50"], 50)

    def test_errors_and_empty(self):
        s = fp.summarize([], Counter({"HTTP 403": 3, "timeout": 1}))
        self.assertEqual(s["llamadas"], 4)
        self.assertEqual(s["errores"], {"HTTP 403": 3, "timeout": 1})
        self.assertNotIn("bloques_pendientes", s)


class TestProbe(unittest.TestCase):
    def test_probe_against_the_fake_pending_block(self):
        chain = fm.FakeMorpho()
        ft = FakeTime()
        rpc = Rpc(["https://fake"], transport=chain, sleep=ft.sleep, rps=0)
        res = fp.probe(rpc, ("https://preconf",), seconds=5.0, interval=0.1, wall=ft.now, mono=ft.now, sleep=ft.sleep)
        r = res["https://preconf"]
        self.assertGreater(r["llamadas"], 40)
        self.assertEqual(r["errores"], {})
        self.assertEqual(r["bloque_sellado_al_final"], chain.head)
        self.assertGreater(r["trozos_nuevos_vistos"], 10)
        self.assertEqual(min(r["bloques_pendientes"]), chain.head + 1)

    def test_endpoint_that_rejects_pending_is_reported(self):
        chain = fm.FakeMorpho()
        chain.fail("eth_getBlockByNumber", times=10_000, message="pending tag not supported")
        ft = FakeTime()
        rpc = Rpc(["https://fake"], transport=chain, sleep=ft.sleep, rps=0)
        res = fp.probe(rpc, ("https://preconf",), seconds=1.0, interval=0.1, wall=ft.now, mono=ft.now, sleep=ft.sleep)
        self.assertIn("pending tag not supported", list(res["https://preconf"]["errores"])[0])


if __name__ == "__main__":
    unittest.main()
