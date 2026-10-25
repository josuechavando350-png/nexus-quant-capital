"""Vía rápida: el precio del oráculo calculado en casa al llegar su actualización por WebSocket, y la ventana frente al ganador."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fakemorpho as fm  # noqa: E402
from census_dinero import shadow_report as sr  # noqa: E402
from census_dinero.flash_fast import ANSWER_UPDATED, FastPath  # noqa: E402
from census_dinero.flash_watch import FlashWatcher  # noqa: E402
from test_shadow_live import B, DROP, U, Env  # noqa: E402


class StreamStub:
    """Lo que el flujo por WebSocket habría visto llegar (hash -> hora)."""

    def __init__(self):
        self.t = {}

    def seen(self, h):
        return self.t.get((h or "").lower())

    def report(self):
        return {"url": "wss://falso", "conexiones": 1, "transacciones": len(self.t), "logs": 1, "errores": {},
                "suscripciones": {"logs": "ok", "transacciones": "ok"}, "silencio_entre_trozos_ms": {"n": 0}}


def answer_log(feed, price, n, tx="0x" + "77" * 32, index=0):
    return {"address": feed, "topics": [ANSWER_UPDATED, "0x" + format(price // 10 ** 18, "064x"), "0x" + format(9, "064x")],
            "data": "0x" + "0" * 64, "blockNumber": hex(n), "transactionHash": tx, "transactionIndex": hex(index)}


class TestFastPath(unittest.TestCase):
    def make(self):
        env = Env({"flash_url": "https://pre", "min_bonus_usd": 0, "min_net_usd": 0}).ready((U[0], 1700), (U[1], 1000))
        env.sh.flash = FlashWatcher(env.rpc, "https://pre")
        env.step()                                                        # un bloque procesado: deja la última foto de mercados
        st = StreamStub()
        clock = {"wall": 100.005}
        fast = FastPath(env.sh, st, wall=lambda: clock["wall"]).setup()
        env.sh.fast, env.sh.stream = fast, st
        return env, fast, st, clock

    def test_setup_maps_feeds_and_reads_their_answers(self):
        env, fast, _, _ = self.make()
        feed = env.chain.markets[env.mid]["feed"]
        agg = fm.norm("0x" + format(int(feed, 16) + 1, "040x"))
        self.assertEqual(fast.by_addr[feed], [(env.mid, "BASE_FEED_1", feed)])
        self.assertEqual(fast.by_addr[agg], [(env.mid, "BASE_FEED_1", feed)])          # los logs salen del agregador
        self.assertEqual(fast.answers[(env.mid, "BASE_FEED_1")], fm.PRICE_2000 // 10 ** 18)
        self.assertEqual(fast.addresses(), sorted([feed, agg]))

    def test_an_update_is_priced_locally_and_the_crossing_is_decided_without_rpc(self):
        env, fast, st, clock = self.make()
        n = env.chain.head + 1
        calls = len(env.chain.calls)
        fast.on_log(answer_log(env.chain.markets[env.mid]["feed"], DROP, n), 100.0)
        self.assertEqual(len(env.chain.calls), calls)                     # ni una consulta a la red para decidir
        key = (env.mid, U[0])
        self.assertEqual(set(fast.crossings), {key})                      # U1 (1000) sigue sana
        rec = fast.crossings[key]
        self.assertEqual((rec["decision"], rec["decision_ms"], rec["bloque_pendiente"]), ("GO", 5.0, n))
        self.assertEqual(fast.answers[(env.mid, "BASE_FEED_1")], DROP // 10 ** 18)    # la respuesta nueva queda para la próxima
        # el bloque real: actualización y liquidación; el ganador llegó 200 ms después por WebSocket
        n2 = env.chain.mine([("set_price", env.mid, DROP), ("liquidate", env.mid, B[0], U[0])])
        upd, liq = env.chain.headers[n2]["transactions"]
        st.t[upd.lower()], st.t[liq.lower()] = 100.0, 100.2
        env.sh.process_block(n2, 101.0, env.clock.mono())
        row = env.rows("flash_rapido.jsonl")[0]
        self.assertEqual((row["resultado"], row["ventana_ms"], row["holgura_ms"], row["envio_supuesto_ms"]), ("liquidada", 200.0, 175.0, 20))
        res = [r for r in env.rows("resultados.jsonl") if "bloque_liquidacion" in r][0]
        self.assertEqual(res["flash"]["ws_ventana_ms"], 200.0)            # la misma ventana para cada liquidación real
        rep = fast.report()
        self.assertEqual((rep["actualizaciones"], rep["cruces"], rep["cruces_liquidados"], rep["holgura_positiva"]), (1, 1, 1, 1))
        self.assertEqual(rep["decision_ms"]["p50"], 5.0)
        # y el reporte lo cuenta
        env.sh.write_meta()
        md = sr.render(sr.build(env.out, None))
        self.assertIn("Vía rápida (precio del oráculo calculado en casa", md)
        self.assertIn("decidir tomó p50 5 ms", md)
        self.assertIn("Ventana medida por WebSocket entre la actualización del oráculo y la liquidación del ganador: mediana 200 ms", md)
        self.assertIn("positiva en 1 de 1", md)

    def test_already_liquidatable_and_unknown_logs_are_ignored(self):
        env, fast, _, _ = self.make()
        n = env.chain.head + 1
        env.sh.last_liq_keys = {(env.mid, U[0])}                         # ya era liquidable: no es un cruce nuevo
        fast.on_log(answer_log(env.chain.markets[env.mid]["feed"], DROP, n), 100.0)
        self.assertEqual(fast.crossings, {})
        fast.on_log(answer_log("0x" + "12" * 20, DROP, n), 100.0)          # un feed que no es de nuestros oráculos
        fast.on_log({**answer_log(env.chain.markets[env.mid]["feed"], DROP, n), "topics": ["0x" + "ab" * 32]}, 100.0)
        self.assertEqual(fast.report()["actualizaciones"], 1)

    def test_quote_feeds_move_the_price_the_other_way(self):
        env, fast, _, _ = self.make()
        seen = {}
        env.sh._evaluate_core = lambda snap, n, ts, **kw: (seen.update(snap) or {}, [], {})
        quote = "0x" + "34" * 20
        fast.by_addr[quote] = [(env.mid, "QUOTE_FEED_1", quote)]
        fast.answers[(env.mid, "QUOTE_FEED_1")] = 100
        price = env.sh.last_snap[env.mid][1]
        fast.on_log({**answer_log(quote, 0, env.chain.head + 1), "topics": [ANSWER_UPDATED, "0x" + format(125, "064x")]}, 100.0)
        self.assertEqual(seen[env.mid][1], price * 100 // 125)            # la cotización sube: el precio del colateral baja

    def test_without_a_previous_snapshot_nothing_is_decided(self):
        env, fast, _, _ = self.make()
        env.sh.last_snap = None
        fast.on_log(answer_log(env.chain.markets[env.mid]["feed"], DROP, env.chain.head + 1), 100.0)
        self.assertEqual((fast.crossings, fast.stats["sin_precio_base"]), ({}, 1))


    def test_each_update_is_logged_with_its_timings_when_the_block_seals(self):
        env, fast, st, clock = self.make()
        n = env.chain.head + 1
        fast.on_log(answer_log(env.chain.markets[env.mid]["feed"], DROP, n, tx="0x" + "78" * 32), 100.0)
        self.assertEqual(env.rows("flash_actualizaciones.jsonl"), [])         # todavía no se selló el bloque
        n2 = env.chain.mine([("set_price", env.mid, DROP)])
        env.sh.process_block(n2, 101.0, env.clock.mono())
        rows = env.rows("flash_actualizaciones.jsonl")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["tx"], rows[0]["decision_ms"], rows[0]["mercados"]), ("0x" + "78" * 32, 5.0, [env.mid]))
        self.assertIn("evaluar_ms", rows[0])
        self.assertEqual(fast.report()["evaluar_ms"]["n"], 1)


class TestNoNetworkInTheFastPath(unittest.TestCase):
    RATE = int(0.05 / 31_536_000 * 1e18)              # 5% al año

    def make(self):
        env = Env({"flash_url": "https://pre", "rate_ttl_s": 0.0, "min_bonus_usd": 0, "min_net_usd": 0},
                  rate=self.RATE).ready((U[0], 1630))                         # tras la caída queda a 0.25% del umbral: hay que mirar el interés
        env.sh.flash = FlashWatcher(env.rpc, "https://pre")
        env.step()
        later = {"wall": int(env.chain.headers[env.chain.head]["timestamp"], 16) + 60}
        fast = FastPath(env.sh, StreamStub(), wall=lambda: later["wall"]).setup()
        env.sh.fast = fast
        return env, fast

    def test_without_a_cached_rate_it_decides_without_waiting_for_one(self):
        env, fast = self.make()
        env.sh.rate_cache.clear()
        calls = len(env.chain.calls)
        fast.on_log(answer_log(env.chain.markets[env.mid]["feed"], DROP, env.chain.head + 1), 100.0)
        self.assertEqual(len(env.chain.calls), calls)                         # ni la tasa del IRM se pide a la red
        self.assertEqual(env.sh.counts["tasa_sin_cache_via_rapida"], 1)
        self.assertEqual(fast.report()["actualizaciones"], 1)

    def test_an_expired_cached_rate_is_used_as_is(self):
        env, fast = self.make()
        env.sh.rate_cache[env.mid] = (("otro", "estado", 0), -1e9, self.RATE)  # caducada y de otro estado: igual sirve en la vía rápida
        calls = len(env.chain.calls)
        fast.on_log(answer_log(env.chain.markets[env.mid]["feed"], DROP, env.chain.head + 1), 100.0)
        self.assertEqual(len(env.chain.calls), calls)
        self.assertEqual(env.sh.counts["tasa_sin_cache_via_rapida"], 0)

    def test_the_sealed_block_loop_still_reads_the_rate(self):
        env, _ = self.make()
        env.sh.rate_cache.clear()
        for _ in range(3):
            env.step()                                                        # que pasen más de 5 s sin tocar el mercado
        env.step([("set_price", env.mid, DROP)])
        self.assertIn(env.mid, env.sh.rate_cache)                             # fuera de la vía rápida se sigue leyendo de la red


if __name__ == "__main__":
    unittest.main()
