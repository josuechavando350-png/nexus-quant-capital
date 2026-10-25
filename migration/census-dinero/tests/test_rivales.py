"""Rivales que perdieron: las otras transacciones del bloque que intentaron liquidar la misma posición y dónde quedaron."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fakemorpho as fm  # noqa: E402
from census_dinero import shadow_report as sr  # noqa: E402
from census_dinero.flash_watch import FlashWatcher  # noqa: E402
from census_dinero.orden import MAX_INTENTOS, MORPHO_BLUE, fronteras, intentos, lugar  # noqa: E402
from test_shadow_live import B, DROP, Env, S, U  # noqa: E402
from test_shadow_replay import replay  # noqa: E402

BASE = 5_000_000
WHO = "0x" + "ab" * 20                       # el prestatario
BOT_A = "0x" + "a1" * 20                     # contrato del ganador
BOT_B = "0x" + "b2" * 20                     # contrato de un rival


def tx(i, tip, frm="0x" + "11" * 20, to=BOT_A, data="0x"):
    return {"hash": "0x" + format(i, "064x"), "from": frm, "to": to, "type": "0x2", "input": data,
            "maxPriorityFeePerGas": hex(tip), "maxFeePerGas": hex(BASE + 10 ** 12)}


def calls(who):
    return "0xd8eabcb8" + "0" * 24 + who[2:]


def block(txs):
    return {"baseFeePerGas": hex(BASE), "transactions": txs}


class TestChunkBoundaries(unittest.TestCase):
    def test_a_rise_that_stays_up_is_a_new_chunk_and_one_that_comes_back_is_a_spike(self):
        self.assertEqual(fronteras([100, 90, 80], 0, 2), 0)
        self.assertEqual(fronteras([100, 90, 120, 110], 0, 3), 1)           # sube y la siguiente no vuelve: trozo nuevo
        self.assertEqual(fronteras([100, 90, 120, 80], 0, 3), 0)            # sube y vuelve al nivel de antes: pico
        self.assertEqual(fronteras([100, None, 90, 120, 110, 130], 0, 5), 1)      # el último sube pero no hay siguiente: no se cuenta
        self.assertEqual(fronteras([100, 90, 120, 110, 50, 70, 60], 0, 5), 2)

    def test_where_each_attempt_lands(self):
        tips = [50, 100, 90, 80, 120, 110, 95]                               # 0: antes, 1: actualización, 3: ganador
        self.assertEqual(lugar(tips, 0, 3, 1), "antes_de_la_actualizacion")
        self.assertEqual(lugar(tips, 2, 3, 1), "antes_del_ganador")
        self.assertEqual(lugar(tips, 2, 3, None), "antes_del_ganador")
        self.assertEqual(lugar(tips + [70], 7, 3, 1), "trozo_posterior")       # 120 abre un trozo nuevo antes de él
        self.assertEqual(lugar([100, 80, 70, 60], 3, 1, 0), "mismo_trozo_menos_propina")
        self.assertEqual(lugar([100, 80, 70, 90, 60], 3, 1, 0), "tarde_con_mas_propina")


class TestAttempts(unittest.TestCase):
    def test_finds_other_bots_by_the_borrower_address_in_their_data(self):
        txs = [tx(0, 50, frm="0x" + "c0" * 20, to=BOT_B, data=calls(WHO)),     # disparó antes de la actualización
               tx(1, 100, to="0x" + "fe" * 20),                                   # actualización del oráculo
               tx(2, 90, data=calls(WHO)),                                        # el ganador
               tx(3, 80, frm=WHO, data=calls(WHO)),                               # el propio prestatario: fuera
               tx(4, 70, frm="0x" + "c1" * 20, to=BOT_B, data="0x1234" + WHO[2:] + "00"),   # rival en el mismo trozo, menos propina
               tx(5, 60, frm="0x" + "11" * 20, to=BOT_A, data=calls(WHO)),        # otro intento del mismo bot
               tx(6, 120, frm="0x" + "c2" * 20, to=MORPHO_BLUE, data=calls(WHO)),   # a Morpho directo, más propina, detrás: tarde
               tx(7, 110, frm="0x" + "c3" * 20, to=MORPHO_BLUE, data=calls(WHO)),   # sigue el trozo nuevo
               tx(8, 10, frm="0x" + "c4" * 20, to=BOT_B, data=calls("0x" + "cd" * 20))]   # otro prestatario: no cuenta
        seen = {t["hash"]: 100.0 + 0.01 * i for i, t in enumerate(txs)}
        out = intentos(block(txs), WHO, 2, 1, liquidaciones={txs[7]["hash"].upper()}, llegadas=seen.get)
        self.assertTrue(out["ganador_lleva_prestatario"])
        self.assertEqual((out["n"], out["propina_ganador"]), (5, 90))
        by = {a["i"]: a for a in out["lista"]}
        self.assertEqual(sorted(by), [0, 4, 5, 6, 7])
        self.assertEqual(by[0]["lugar"], "antes_de_la_actualizacion")
        self.assertEqual((by[4]["lugar"], by[4]["mismo_bot"], by[4]["trozos_despues"]), ("mismo_trozo_menos_propina", False, 0))
        self.assertTrue(by[5]["mismo_bot"])
        self.assertEqual((by[6]["lugar"], by[6]["mismo_bot"]), ("tarde_con_mas_propina", False))   # Morpho directo no junta firmantes
        self.assertTrue(by[7].get("tambien_liquido"))
        self.assertNotIn("tambien_liquido", by[6])
        self.assertEqual((by[4]["ms_tras_ganador"], by[0]["ms_tras_ganador"]), (20, -20))
        self.assertNotIn("trozos_despues", by[0])

    def test_nothing_to_look_for_gives_none_and_long_lists_are_capped(self):
        self.assertIsNone(intentos(block([tx(0, 1)]), "", 0))
        self.assertIsNone(intentos(block([tx(0, 1)]), WHO, 3))
        self.assertIsNone(intentos(block(["0xabc"]), WHO, 0))                  # bloque sin transacciones completas
        txs = [tx(0, 100, data=calls(WHO))] + [tx(i, 1, frm="0x" + format(i, "040x"), to=BOT_B, data=calls(WHO)) for i in range(1, 60)]
        out = intentos(block(txs), WHO, 0)
        self.assertEqual((out["n"], len(out["lista"])), (59, MAX_INTENTOS))
        out = intentos(block([tx(0, 100, data="0x")]), WHO, 0)
        self.assertEqual((out["n"], out["ganador_lleva_prestatario"]), (0, False))


def item(bono, attempts, ganador=BOT_A, clase="trozo_siguiente", peso=None, n=None, propina=100):
    return {"bono_usd": bono, "peso": peso, "clase": clase, "ganador": ganador,
            "intentos": {"ganador_lleva_prestatario": True, "propina_ganador": propina, "n": len(attempts) if n is None else n, "lista": attempts}}


def att(i, lugar_, propina, de="0x" + "c0" * 20, a=BOT_B, **kw):
    return {"i": i, "tx": "0x" + format(i, "064x"), "propina": propina, "de": de, "a": a, "lugar": lugar_, "mismo_bot": False, **kw}


class TestCompetitionSummary(unittest.TestCase):
    def test_how_the_second_lost_weighted_by_bonus(self):
        items = [item(100, [att(5, "mismo_trozo_menos_propina", 80), att(9, "trozo_posterior", 50, de="0x" + "c9" * 20, a=MORPHO_BLUE)]),
                 item(300, [att(2, "antes_de_la_actualizacion", 10), att(7, "tarde_con_mas_propina", 150, ms_tras_ganador=180)], ganador="0x" + "dd" * 20),
                 item(50, [att(3, "antes_de_la_actualizacion", 10)], clase="empaquetada"),
                 item(50, [dict(att(4, "mismo_trozo_menos_propina", 60), mismo_bot=True), dict(att(6, "trozo_posterior", 5), tambien_liquido=True)], n=45),
                 item(500, []),                                                      # bloque leído y nadie más lo intentó
                 {"bono_usd": 10, "intentos": None}]                                 # bloque sin leer: no entra
        rv = sr.competition(items)
        self.assertEqual((rv["liquidaciones"], rv["con_rivales"], rv["ganador_lleva_prestatario"]), (5, 3, 5))
        self.assertAlmostEqual(rv["bono_con_rivales"], 450 / 1000)
        sg = rv["segundo"]
        self.assertEqual({k: v["n"] for k, v in sg.items()}, {"mismo_trozo_menos_propina": 1, "tarde_con_mas_propina": 1, "solo_antes": 1, "sin_rivales": 2})
        self.assertAlmostEqual(sg["tarde_con_mas_propina"]["parte_del_bono"], 300 / 1000)
        self.assertEqual(rv["segundo_propina_vs_ganador"]["n"], 2)
        self.assertEqual((rv["segundo_propina_vs_ganador"]["min"], rv["segundo_propina_vs_ganador"]["max"]), (0.8, 1.5))
        self.assertEqual(rv["segundo_ms_tras_ganador"]["p50"], 180)
        self.assertEqual(rv["rivales_por_liquidacion"]["max"], 2)                  # dos bots distintos en la primera
        self.assertEqual((rv["intentos_del_mismo_bot"], rv["listas_recortadas"]), (1, 1))
        self.assertEqual(rv["intentos_por_lugar"]["antes_de_la_actualizacion"], 2)
        self.assertEqual(rv["por_clase"]["trozo_siguiente"]["n"], 4)
        self.assertEqual(rv["por_clase"]["empaquetada"]["segundo"], {"solo_antes": 1})
        bots = {b["bot"]: b for b in rv["bots"]}
        self.assertEqual((bots[BOT_A]["gana"], bots[BOT_B]["pierde"], bots["0x" + "dd" * 20]["gana"]), (4, 3, 1))
        self.assertEqual(bots["0x" + "c9" * 20]["pierde"], 1)                      # el que llama a Morpho directo se cuenta por su firmante
        text = "\n".join(sr.rivals_lines(rv))
        self.assertIn("**Rivales que perdieron** (5 liquidaciones", text)
        self.assertIn("detrás del ganador pagando más (llegó tarde", text)
        self.assertIn("listas recortadas", text)
        self.assertEqual(sr.rivals_lines(sr.competition([])), [])
        bad = sr.competition([{"bono_usd": 5, "intentos": {"error": "datos del bloque ilegibles"}}])
        self.assertEqual((bad["liquidaciones"], bad["con_error"]), (0, 1))               # un bloque ilegible no cuenta como "sin rivales"


class TestReplayFindsRivals(unittest.TestCase):
    def test_the_lupa_records_who_else_tried_in_the_block(self):
        env = Env().ready((U[0], 1700))
        for _ in range(6):
            env.step()
        rival = fm.norm("0x" + "b2" * 20)
        env.step([("set_price", env.mid, DROP), ("liquidate", env.mid, B[0], U[0]),
                  ("noop", {"sender": S[3], "to": rival, "input": "0x5555" + "0" * 24 + U[0][2:], "gas_price": 8 * 10 ** 6})])
        env.step()
        meta, rows, out = replay(env, min_bonus_usd=0.1, diag=5)
        with open(os.path.join(out, "diag.jsonl")) as fh:
            d = [json.loads(x) for x in fh][0]
        it = d["intentos"]
        self.assertTrue(it["ganador_lleva_prestatario"])
        self.assertEqual(it["n"], 1)
        a = it["lista"][0]
        self.assertEqual((a["i"], a["de"], a["a"], a["lugar"], a["mismo_bot"]), (2, S[3], rival, "mismo_trozo_menos_propina", False))
        rv = sr.analyze_diag([d])["rivales"]
        self.assertEqual((rv["liquidaciones"], rv["con_rivales"]), (1, 1))
        self.assertIn("mismo_trozo_menos_propina", rv["segundo"])


class TestLiveFindsRivals(unittest.TestCase):
    def test_live_rows_carry_rivals_with_their_chunk_and_arrival(self):
        env = Env({"flash_url": "https://pre"}).ready((U[0], 1700))
        w = FlashWatcher(env.rpc, "https://pre")
        env.sh.flash = w
        rival = fm.norm("0x" + "b2" * 20)
        n = env.chain.mine([("set_price", env.mid, DROP), ("liquidate", env.mid, B[0], U[0]),
                            ("noop", {"sender": S[3], "to": rival, "input": "0x5555" + "0" * 24 + U[0][2:], "gas_price": 2 * 10 ** 7})])
        upd, liq, riv = env.chain.headers[n]["transactions"]
        w.ingest(100.00, n, [upd, liq])
        w.ingest(100.20, n, [upd, liq, riv])                                # el rival llega un trozo después, pagando más

        class Stream:
            def seen(self, h):
                return {liq: 50.000, riv: 50.215}.get(h)
        env.sh.stream = Stream()
        env.sh.process_block(n, None, None, None)
        r = [x for x in env.rows("resultados.jsonl") if "bloque_liquidacion" in x][0]
        a = r["flash"]["intentos"]["lista"][0]
        self.assertEqual((a["lugar"], a["trozo"], a["ms_tras_ganador"]), ("tarde_con_mas_propina", 1, 215))
        res = sr.build(env.out, None)
        rl = res["vivo"]["rivales_en_vivo"]
        self.assertEqual((rl["con_rivales"], rl["casos"][0]["rivales"], rl["casos"][0]["segundo"]["trozo"]), (1, 1, 1))
        md = sr.render(res)
        self.assertIn("Rivales que perdieron", md)
        self.assertIn("215 ms después por WebSocket, trozo 1", md)


    def test_a_failure_reading_rivals_never_stops_the_live_shadow(self):
        env = Env({"flash_url": "https://pre"}).ready((U[0], 1700))
        env.sh.flash = FlashWatcher(env.rpc, "https://pre")

        def boom(n):
            raise ValueError("bloque raro")
        env.sh._full_block = boom
        n = env.chain.mine([("set_price", env.mid, DROP), ("liquidate", env.mid, B[0], U[0])])
        env.sh.process_block(n, None, None, None)
        r = [x for x in env.rows("resultados.jsonl") if "bloque_liquidacion" in x][0]
        self.assertNotIn("intentos", r["flash"])
        self.assertEqual((env.sh.counts["rivales_sin_leer"], env.sh.counts["propinas_sin_leer"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
