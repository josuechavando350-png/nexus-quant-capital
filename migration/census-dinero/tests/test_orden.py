"""Orden de propinas dentro de un bloque: de las transacciones del RPC a la comprobación del orden por prioridad."""

import os
import sys
import tempfile
import time
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from census_dinero import shadow_report as sr  # noqa: E402
from census_dinero.orden import analyze_order, ascents, block_tips, expected_random_ascents  # noqa: E402
from test_shadow_live import Env, U  # noqa: E402
from test_shadow_replay import replay, scenario  # noqa: E402

BASE = 5_000_000


def tx(kind=None, **kw):
    t = {"type": kind} if kind else {}
    t.update({k: hex(v) for k, v in kw.items()})
    return t


class TestBlockTips(unittest.TestCase):
    def test_each_kind_of_transaction_has_its_tip(self):
        blk = {"baseFeePerGas": hex(BASE), "transactions": [
            tx("0x7e"),                                                         # depósito de la L1: sin propina
            tx("0x2", maxPriorityFeePerGas=700, maxFeePerGas=BASE + 10_000),    # tope por propina
            tx("0x2", maxPriorityFeePerGas=900, maxFeePerGas=BASE + 300),       # tope por tarifa máxima
            tx(gasPrice=BASE + 40),                                             # legado
            tx(gasPrice=BASE - 1),                                              # por debajo de la base: 0, no negativo
            "0xabc"]}                                                           # solo el hash (bloque pedido sin transacciones)
        base, tips = block_tips(blk)
        self.assertEqual(base, BASE)
        self.assertEqual(tips, [None, 700, 300, 40, 0, None])

    def test_ascents_ignore_deposits_and_only_count_strict_rises(self):
        self.assertEqual(ascents([None, 5, 5, 3, 4, 4, 1, 9]), 2)
        self.assertEqual(ascents([]), 0)


class TestRandomBaseline(unittest.TestCase):
    def test_expected_rises_in_a_random_order(self):
        self.assertEqual(expected_random_ascents([None, 5]), 0.0)
        self.assertEqual(expected_random_ascents([7, 7, 7, 7]), 0.0)                     # todas iguales: nunca suben
        self.assertAlmostEqual(expected_random_ascents([1, 2]), 0.5)                      # un par distinto: sube la mitad de las veces
        self.assertAlmostEqual(expected_random_ascents([1, 2, 3]), 1.0)                   # 2 pares vecinos, todos distintos
        # coincide con simular muchas mezclas
        import random
        rnd = random.Random(3)
        tips = [0] * 30 + [5] * 10 + [9] * 5 + list(range(100, 110))
        sim = []
        for _ in range(400):
            ys = tips[:]
            rnd.shuffle(ys)
            sim.append(ascents(ys))
        self.assertAlmostEqual(sum(sim) / len(sim), expected_random_ascents(tips), delta=1.0)

    def test_the_summary_compares_real_and_random_rises(self):
        tips = [None] + sorted([0] * 30 + [5] * 10 + [9] * 5 + list(range(100, 110)), reverse=True)
        out = analyze_order([{"bloque": 1, "tips": tips}])
        self.assertEqual(out["ascensos_por_bloque"]["p50"], 0)
        self.assertGreater(out["ascensos_si_fuera_al_azar"]["p50"], 5)


class TestAnalyzeOrder(unittest.TestCase):
    # cinco trozos de 4 transacciones; dentro de cada uno, de más a menos propina; al empezar otro, sube
    SORTED = [None, 9, 8, 8, 20, 10, 7, 7, 30, 12, 6, 5, 25, 9, 9, 2, 40, 11, 3, 3]
    PROFILE = {"bloque": 1, "trozos": [[0, 1], [100, 4], [300, 8], [500, 12], [700, 16], [900, 20]]}

    def test_a_block_sorted_by_priority_inside_each_chunk(self):
        out = analyze_order([{"bloque": 1, "tips": self.SORTED}], [self.PROFILE])
        self.assertEqual(out["con_perfil"], 1)
        self.assertEqual(out["dentro"]["sube"], 0)
        self.assertGreater(out["dentro"]["baja"], 0)
        self.assertEqual(out["frontera"]["sube"], 4)                             # al empezar los trozos 2 a 5 la propina sube
        self.assertEqual(out["ascensos_por_bloque"]["p50"], 4)

    def test_arrival_order_shows_rises_inside_the_chunks(self):
        shuffled = [None, 1, 9, 2, 8, 3, 7, 4, 6, 5, 5, 6, 4, 7, 3, 8, 2, 9, 1, 10]
        out = analyze_order([{"bloque": 1, "tips": shuffled}], [self.PROFILE])
        self.assertGreater(out["dentro"]["sube"], 4)

    def test_without_a_profile_only_the_block_wide_count_is_given(self):
        out = analyze_order([{"bloque": 7, "tips": self.SORTED}, {"bloque": 8, "tips": [None, 3, 2]}])
        self.assertEqual((out["bloques"], out["con_perfil"]), (2, 0))
        self.assertEqual(out["dentro"], {"baja": 0, "igual": 0, "sube": 0})
        self.assertEqual(out["transacciones"]["max"], 20)


class TestSamplers(unittest.TestCase):
    def wait_for(self, path, n, seconds=3.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if os.path.exists(path):
                with open(path) as fh:
                    rows = [json.loads(x) for x in fh]
                if len(rows) >= n:
                    return rows
            time.sleep(0.01)
        return []

    def test_live_saves_the_tips_of_every_nth_sealed_block_up_to_the_cap(self):
        env = Env({"orden_cada": 1, "orden_max": 2}).ready((U[0], 1700))
        for _ in range(4):
            env.step()
        rows = self.wait_for(os.path.join(env.out, "orden_bloques.jsonl"), 2)
        self.assertEqual(len(rows), 2)                                           # el tope manda: solo 2 de los bloques
        self.assertTrue(all(isinstance(r["tips"], list) and r["base_fee"] == BASE for r in rows))
        self.assertEqual(env.sh.order_sampled, 2)

    def test_live_does_not_sample_by_default(self):
        env = Env().ready((U[0], 1700))
        env.step()
        self.assertFalse(os.path.exists(os.path.join(env.out, "orden_bloques.jsonl")))

    def test_replay_saves_the_fullest_diag_blocks(self):
        env, _, _ = scenario()
        env.sh.finish()
        meta, rows, out = replay(env, min_bonus_usd=0.1, diag=5, orden=2)
        self.assertEqual(meta["diag"]["bloques_con_propinas"], 2)
        with open(os.path.join(out, "orden_bloques.jsonl")) as fh:
            saved = [json.loads(x) for x in fh]
        self.assertEqual(len(saved), 2)
        self.assertTrue(all(r["tips"] and all(t == 5_000_000 for t in r["tips"]) for r in saved))   # gas 1e7 menos base 5e6
        # y el reporte los lee sin más
        res = sr.build(None, out)
        self.assertEqual(res["orden_historico"]["bloques"], 2)
        self.assertIn("Orden de propinas en 2 bloques llenos", sr.render(res))

    def test_the_live_line_of_the_report(self):
        meta = {"contadores": {}, "flashblocks": {"intervalo_de_consulta_ms": 100, "fotos": 5}}
        a = sr.analyze_live([{"bloque": 1, "ts": 1, "visto_ms": 1, "total_ms": 1}], [], [], [], [], meta, {"min_bonus_usd": 10, "min_net_usd": 5})
        a["orden"] = analyze_order([{"bloque": 1, "tips": TestAnalyzeOrder.SORTED}], [TestAnalyzeOrder.PROFILE])
        res = sr.build(None, None)
        res["vivo"] = {**a, "ventana": {"horas": 1, "bloques": 1, "bloques_en_rango": 1, "cobertura": 1, "desde_bloque": 1, "hasta_bloque": 1}}
        md = sr.render(res)
        self.assertIn("Orden dentro del bloque comprobado en 1 bloques sellados", md)
        self.assertIn("sube en 100% de 4 fronteras", md)


if __name__ == "__main__":
    unittest.main()
