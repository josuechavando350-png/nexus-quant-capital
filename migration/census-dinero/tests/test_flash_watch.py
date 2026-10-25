"""Observador de Flashblocks: cuándo aparece cada transacción del bloque pendiente."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from census_dinero.flash_watch import FlashWatcher  # noqa: E402
from census_dinero.rpc import Rpc  # noqa: E402
import fakemorpho as fm  # noqa: E402


def h(i):
    return "0x" + format(i, "064x")


class TestIngest(unittest.TestCase):
    def watcher(self, keep=8):
        return FlashWatcher(Rpc(["https://x"], transport=fm.FakeMorpho(), rps=0), "https://pre", keep_blocks=keep)

    def test_each_tx_gets_the_time_and_chunk_of_its_first_photo(self):
        w = self.watcher()
        w.ingest(10.00, 7, [h(1), h(2)])
        w.ingest(10.05, 7, [h(1), h(2)])                    # sin cambios
        w.ingest(10.20, 7, [h(1), h(2), h(3), h(4), h(5)])
        w.ingest(10.41, 7, [h(1), h(2), h(3), h(4), h(5), h(6)])
        self.assertEqual(w.seen(7, h(1)), (10.00, 0))
        self.assertEqual(w.seen(7, h(4)), (10.20, 1))
        self.assertEqual(w.seen(7, h(6)), (10.41, 2))
        self.assertIsNone(w.seen(7, h(99)))
        self.assertIsNone(w.seen(8, h(1)))
        self.assertEqual(w.block_start(7), 10.00)
        self.assertEqual(w.first_photo_size(7), 2)
        self.assertEqual([c[1] for c in w.block_chunks(7)], [2, 5, 6])

    def test_the_profile_of_a_block_is_emitted_when_the_next_one_starts(self):
        w = self.watcher()
        got = []
        w.on_block = got.append
        w.ingest(10.00, 7, [h(1), h(2)])
        w.ingest(10.20, 7, [h(1), h(2), h(3), h(4), h(5)])
        w.ingest(10.40, 7, [h(1), h(2), h(3), h(4), h(5), h(6)])
        self.assertEqual(got, [])                                           # el bloque 7 sigue abierto
        w.ingest(10.62, 8, [h(11)])
        self.assertEqual(got, [{"bloque": 7, "t0": 10.0, "primera_foto": 2, "trozos": [[0, 2], [200, 5], [400, 6]]}])
        w.ingest(10.80, 7, [h(1)])                                          # una foto rezagada de un bloque viejo no cierra nada
        w.ingest(10.82, 8, [h(11), h(12)])
        self.assertEqual(len(got), 1)
        w.ingest(12.62, 10, [h(21)])                                        # se saltó el 9: se cierra el 8 igual
        self.assertEqual([g["bloque"] for g in got], [7, 8])

    def test_a_failing_profile_sink_does_not_stop_the_watcher(self):
        w = self.watcher()

        def boom(_):
            raise OSError("disco lleno")
        w.on_block = boom
        w.ingest(1.0, 7, [h(1)])
        w.ingest(3.0, 8, [h(2)])                                            # intenta emitir el 7 y falla sin propagar
        self.assertEqual(w.errors, {"perfil de bloque": 1})
        self.assertEqual(w.seen(8, h(2)), (3.0, 0))

    def test_blocks_are_independent_and_old_ones_are_dropped(self):
        w = self.watcher(keep=3)
        for n in range(1, 6):
            w.ingest(float(n), n, [h(n * 10)])
        self.assertIsNone(w.seen(1, h(10)))
        self.assertEqual(w.seen(5, h(50)), (5.0, 0))
        self.assertEqual(len(w.blocks), 3)

    def test_a_reshuffled_pending_block_does_not_lose_or_duplicate_times(self):
        w = self.watcher()
        w.ingest(1.0, 7, [h(1), h(2), h(3)])
        w.ingest(1.2, 7, [h(1), h(3), h(2), h(4)])           # el orden cambió y llegó una nueva
        self.assertEqual(w.seen(7, h(2)), (1.0, 0))           # conserva la primera vez
        self.assertEqual(w.seen(7, h(4)), (1.2, 1))

    def test_empty_snapshots_are_ignored(self):
        w = self.watcher()
        w.ingest(1.0, 7, [])
        self.assertIsNone(w.block_start(7))

    def test_report(self):
        w = self.watcher()
        w.ingest(1.0, 7, [h(1)])
        w.ingest(1.2, 7, [h(1), h(2)])
        w.ingest(1.41, 7, [h(1), h(2), h(3)])
        r = w.report()
        self.assertEqual(r["intervalo_entre_trozos_ms"]["n"], 2)
        self.assertEqual(r["intervalo_de_consulta_ms"], 50)


class TestLoop(unittest.TestCase):
    def test_thread_follows_the_fake_pending_block(self):
        chain = fm.FakeMorpho()
        rpc = Rpc(["https://x"], transport=chain, rps=0)
        w = FlashWatcher(rpc, "https://pre", interval=0.01).start()
        try:
            import time
            deadline = time.time() + 3
            while time.time() < deadline and w.samples < 30:
                time.sleep(0.02)
        finally:
            w.stop()
        self.assertGreaterEqual(w.samples, 10)
        n = chain.head + 1
        self.assertIsNotNone(w.block_start(n))
        self.assertEqual(w.report()["errores"], {})


if __name__ == "__main__":
    unittest.main()
