"""Reporte del Shadow: tablas de distancia y de llegada, puertas, y una corrida completa contra la Base falsa."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from census_dinero import shadow_report as sr  # noqa: E402
from test_shadow_replay import replay, scenario  # noqa: E402

CFG = {"min_bonus_usd": 10.0, "min_net_usd": 5.0}


def row(delta, bono=100.0, via="directa", peso=1.0, censurado=False, **kw):
    r = {"mercado": "0x01", "etiqueta": "M/USDC", "prestatario": "0xaa", "bloque_liquidacion": 1000, "tx": "0x" + "ab" * 32,
         "bono_usd": bono, "neto_modelo_usd": bono * 0.8, "deuda_mala": False, "peso": peso, "via": via, "delta_bloques": delta,
         "censurado": censurado, "gas_usd": 0.3, "propina_usd": 0.1}
    r.update(kw)
    return r


class TestReplayTables(unittest.TestCase):
    def test_buckets_and_landing_by_total_time(self):
        rows = [row(0, 100), row(1, 200), row(2, 300), row(5, 400), row(40, 500)]
        a = sr.analyze_replay(rows, [], None, CFG)
        by = {b["tramo"]: b for b in a["por_distancia"]}
        self.assertEqual([by[k]["n"] for k in ("0", "1", "2", "3-5", "6-15", "16+")], [1, 1, 1, 1, 0, 1])
        self.assertAlmostEqual(by["0"]["parte_del_bono_directo"], 100 / 1500)
        k1, k2, k3 = a["ganables"]["por_tiempo_total"]
        self.assertEqual((k1["antes"]["n"], k1["empate"]["n"], k1["tarde"]["n"]), (3, 1, 1))     # k=1: >1 antes, =1 empate, <1 tarde
        self.assertEqual((k2["antes"]["n"], k2["empate"]["n"], k2["tarde"]["n"]), (2, 1, 2))
        self.assertEqual((k3["antes"]["n"], k3["empate"]["n"], k3["tarde"]["n"]), (2, 0, 3))
        self.assertAlmostEqual(k1["antes"]["bono_est_usd"], 1200)
        self.assertAlmostEqual(k1["antes"]["parte_bono"], 1200 / 1500)
        self.assertAlmostEqual(k1["antes"]["neto_est_usd"], 960)

    def test_weights_scale_estimates_but_not_counts(self):
        rows = [row(2, 100, peso=1.0), row(0, 100, peso=4.0)]
        a = sr.analyze_replay(rows, [], None, CFG)
        k1 = a["ganables"]["por_tiempo_total"][0]
        self.assertEqual((k1["antes"]["n"], k1["tarde"]["n"]), (1, 1))
        self.assertEqual((k1["antes"]["n_est"], k1["tarde"]["n_est"]), (1.0, 4.0))
        self.assertAlmostEqual(k1["tarde"]["parte_bono"], 400 / 500)
        self.assertAlmostEqual(k1["antes"]["parte_n"], 1 / 5)                  # las partes se calculan con peso, no con la muestra cruda
        self.assertEqual(a["ganables"]["elegibles_est"], 5.0)

    def test_what_is_not_winnable_is_left_out(self):
        rows = [row(3, 100, via="subasta"), row(3, 100, deuda_mala=True), row(3, 4.0), row(3, 100, censurado=True),
                row(3, 100, sin_dato=True), row(3, 100, via=None)]
        rows[5].pop("via")
        a = sr.analyze_replay(rows, [{"error": "x"}], None, CFG)
        g = a["ganables"]
        self.assertEqual(g["elegibles"], 0)                                   # subasta, deuda mala, bono bajo, censurada, sin dato, sin vía
        self.assertEqual(a["censuradas"], 1)
        self.assertEqual(a["sin_dato"], 1)
        self.assertEqual(a["errores"], 1)
        self.assertEqual(g["censuradas"]["n"], 1)
        self.assertTrue(g["muestra_pequena"])
        self.assertEqual(a["vias"]["subasta"]["n"], 1)
        self.assertIn("sin_via", a["vias"])

    def test_parity_summary_and_worst_cases(self):
        ok = {"modo": "repaid_shares", "err_embargo": 0.0, "err_shares": 0.0, "err_repago": 0.0, "con_interes": True}
        bad = {"modo": "seized_assets", "err_embargo": 0.0, "err_shares": 3e-4, "err_repago": 1e-4, "con_interes": False}
        a = sr.analyze_replay([row(2, paridad=ok), row(2, paridad=ok), row(2, paridad=bad, tx="0xbad"),
                               row(2, paridad={"omitida": "deuda_mala"})], [], None, CFG)
        p = a["paridad"]
        self.assertEqual((p["n"], p["exactas"], p["dentro_1e9"], p["dentro_1e6"], p["con_interes"]), (3, 2, 2, 2, 2))
        self.assertEqual(p["omitidas"], {"deuda_mala": 1})
        self.assertEqual(p["max"], 3e-4)
        self.assertEqual(p["peores"][0]["tx"], "0xbad")

    def test_markets_and_winner_costs(self):
        rows = [row(2, 100, etiqueta="A/USDC"), row(4, 300, etiqueta="A/USDC", gas_usd=1.0), row(0, 50, etiqueta="B/USDC")]
        a = sr.analyze_replay(rows, [], None, CFG)
        m = {x["mercado"]: x for x in a["por_mercado"]}
        self.assertEqual(a["por_mercado"][0]["mercado"], "A/USDC")             # ordenados por bono directo
        self.assertEqual((m["A/USDC"]["mediana_bloques"], m["A/USDC"]["parte_2_o_mas"]), (3, 1.0))
        self.assertEqual(m["B/USDC"]["parte_2_o_mas"], 0.0)
        self.assertEqual(a["costos_del_ganador"]["gas_usd"]["n"], 3)

    def test_census_cross_check_uses_window_days(self):
        meta = {"ventana": {"dias": 15}, "mercados": {}}
        a = sr.analyze_replay([row(2, 1000)], [], meta, CFG)
        full = sum(m["dir_bonus"] for m in sr.SHADOW_BASE_MARKETS)
        self.assertAlmostEqual(a["control_census"]["bono_directo_census_usd"], full / 2)
        self.assertAlmostEqual(a["control_census"]["razon"], 1000 / (full / 2))


class TestConcentration(unittest.TestCase):
    def test_winners_and_days(self):
        day = 43_200
        rows = [row(2, 600, firmante="0xA", bloque_liquidacion=1000), row(2, 300, firmante="0xB", bloque_liquidacion=1000 + day),
                row(2, 100, firmante="0xC", bloque_liquidacion=1000 + 5 * day), row(1, 50, via="subasta", firmante="0xD")]
        a = sr.analyze_replay(rows, [], {"ventana": {"desde": 1000}}, CFG)
        gw, cd = a["ganadores"], a["concentracion_dias"]
        self.assertEqual(gw["distintos"], 3)                                  # la subasta no cuenta
        self.assertAlmostEqual(gw["top1"], 0.6)
        self.assertAlmostEqual(gw["top3"], 1.0)
        self.assertEqual(cd["dias_con_liquidaciones"], 3)
        self.assertAlmostEqual(cd["top1"], 0.6)
        self.assertAlmostEqual(cd["top3"], 1.0)

    def test_weights_count_and_missing_fields_do_not_break(self):
        rows = [row(2, 100, peso=3.0, firmante="0xA", bloque_liquidacion=10), row(2, 100, liquidador="0xB", bloque_liquidacion=10)]
        a = sr.analyze_replay(rows, [], None, CFG)
        self.assertAlmostEqual(a["ganadores"]["top1"], 0.75)
        self.assertEqual(a["concentracion_dias"]["dias_con_liquidaciones"], 1)
        empty = sr.analyze_replay([], [], None, CFG)
        self.assertEqual(empty["ganadores"]["distintos"], 0)
        self.assertIsNone(empty["ganadores"]["top1"])
        sr.render(sr.build(None, None))


class TestGates(unittest.TestCase):
    def find(self, G, text):
        return next(g for g in G if text in g["puerta"])

    def test_dangerous_rpc_methods_fail_the_read_only_gate(self):
        G = sr.gates(None, None, {"eth_call", "eth_sendRawTransaction"})
        self.assertEqual(self.find(G, "sin enviar")["estado"], "falla")
        G = sr.gates(None, None, {"eth_call", "eth_getLogs", "debug_traceTransaction"})
        self.assertEqual(self.find(G, "sin enviar")["estado"], "parcial")
        self.assertEqual(self.find(sr.gates(None, None, set()), "sin enviar")["estado"], "sin_datos")

    def test_nothing_is_certified_without_data(self):
        G = sr.gates(None, None, {"eth_call"})
        self.assertTrue(all(g["estado"] in ("sin_datos", "parcial") for g in G))
        self.assertEqual(self.find(G, "Latencia")["estado"], "sin_datos")

    def test_latency_and_economics_never_read_as_complete(self):
        # Aunque haya muchos datos, la latencia se midió desde Actions y la economía usa un prior: como máximo "parcial".
        rows = [row(2, 100, paridad={"modo": "repaid_shares", "err_embargo": 0.0, "err_shares": 0.0, "err_repago": 0.0})] * 40
        rp = sr.analyze_replay(rows, [], None, CFG)
        lv = {"latencia": {"visto_mas_proceso_ms": {"p50": 900, "p90": 1500, "p99": 2000, "n": 500}, "visto_ms": {"n": 500}},
              "decisiones": {"por_decision": {"GO": 3}}, "go": {"n": 3, "cerrados": 3, "destino": {"liquidada": 3}},
              "calidad": {"contadores": {"reconciliadas": 900}}, "liquidaciones": {"clases": {}}}
        G = sr.gates(lv, rp, {"eth_call"})
        self.assertEqual(self.find(G, "Latencia")["estado"], "parcial")
        self.assertEqual(self.find(G, "Economía")["estado"], "parcial")
        self.assertEqual(self.find(G, "Detección")["estado"], "parcial")
        self.assertEqual(self.find(G, "Simulaciones")["estado"], "cumple")
        self.assertEqual(self.find(G, "Cada GO")["estado"], "cumple")

    def test_divergences_fail_the_simulations_gate(self):
        lv = {"latencia": {"visto_mas_proceso_ms": {"n": 0}, "visto_ms": {"n": 0}}, "decisiones": {"por_decision": {}},
              "go": {"n": 0, "cerrados": 0, "destino": {}}, "calidad": {"contadores": {"deriva_reconciliacion": 2}},
              "liquidaciones": {"clases": {"fuera_del_libro": 1}}}
        G = sr.gates(lv, None, {"eth_call"})
        g = self.find(G, "Simulaciones")
        self.assertEqual(g["estado"], "falla")
        self.assertIn("deriva_reconciliacion 2", g["evidencia"])
        self.assertIn("fuera_del_libro 1", g["evidencia"])


class TestFlashSection(unittest.TestCase):
    def live(self, rows, flashblocks=None):
        return sr.analyze_live([{"bloque": 1, "ts": 1, "visto_ms": 300, "total_ms": 400}], [], rows, [], [],
                               {"flashblocks": flashblocks, "contadores": {}}, CFG)

    def liq(self, via, bono, flash):
        return {"bloque_liquidacion": 10, "tx": "0x1", "prestatario": "0xa", "etiqueta": "M", "via": via, "bono_usd": bono,
                "resultado": "liquidada_sin_aviso", "clase": "mismo_bloque", "flash": flash}

    def test_groups_by_reaction_and_via(self):
        rows = [self.liq("directa", 100, {"visto": True, "trozos_entre": 0, "reaccion_ms": 0, "t_liquidacion_ms": 300}),
                self.liq("directa", 50, {"visto": True, "trozos_entre": 1, "reaccion_ms": 210, "t_liquidacion_ms": 900}),
                self.liq("directa", 20, {"visto": True, "trozos_entre": 3, "reaccion_ms": 640, "t_liquidacion_ms": 1500}),
                self.liq("directa", 10, {"visto": True}),
                self.liq("directa", 5, {"visto": False}),
                self.liq("subasta", 400, {"visto": True, "trozos_entre": 0, "reaccion_ms": 0, "t_liquidacion_ms": 100})]
        a = self.live(rows, {"intervalo_de_consulta_ms": 50, "rtt_ms": {"p50": 26}, "fotos": 100, "intervalo_entre_trozos_ms": {"p50": 198}})
        d = a["flash"]["grupos"]["directa"]
        self.assertEqual(d["n"], 5)
        self.assertEqual(d["por_tipo"], {"mismo_trozo": 1, "siguiente_trozo": 1, "dos_o_mas": 1, "sin_actualizacion": 1, "no_visto": 1})
        self.assertEqual(d["bono_usd"]["mismo_trozo"], 100)
        self.assertEqual(d["reaccion_ms"]["p50"], 210)
        self.assertEqual(a["flash"]["grupos"]["subasta"]["por_tipo"], {"mismo_trozo": 1})
        rows[0]["flash"]["actualizacion_por_subasta"] = True
        a2 = self.live(rows)
        self.assertEqual(a2["flash"]["grupos"]["directa"]["con_actualizacion_por_subasta"], 1)

    def test_rendering_and_absence(self):
        rows = [self.liq("directa", 100, {"visto": True, "trozos_entre": 0, "reaccion_ms": 0, "t_liquidacion_ms": 300})]
        res = sr.build(None, None)
        res["vivo"] = {**self.live(rows, {"intervalo_de_consulta_ms": 50, "rtt_ms": {"p50": 26}, "fotos": 100,
                                          "intervalo_entre_trozos_ms": {"p50": 198}}),
                       "ventana": {"horas": 1, "bloques": 1, "bloques_en_rango": 1, "cobertura": 1, "desde_bloque": 1, "hasta_bloque": 1}}
        md = sr.render(res)
        self.assertIn("Flashblocks (bloque pendiente de Base", md)
        self.assertIn("en el mismo trozo que la actualización del oráculo 1", md)
        none = self.live([self.liq("directa", 1, None)])
        self.assertNotIn("flash", none)


class TestFlashCrossings(unittest.TestCase):
    def test_summary_of_crossings_seen_in_the_pending_state(self):
        cruces = [{"resultado": "liquidada", "decision": "GO", "decision_ms": 70, "holgura_ms": 40, "mismo_trozo": False, "bono_usd": 300},
                  {"resultado": "liquidada", "decision": "GO", "decision_ms": 90, "holgura_ms": -120, "mismo_trozo": True, "bono_usd": 100},
                  {"resultado": "no_liquidada_en_el_bloque", "decision": "NO-GO", "decision_ms": 80, "bono_usd": 5}]
        liqs = [{"bloque_liquidacion": 1, "tx": "0x1", "prestatario": "0xa", "etiqueta": "M", "via": "directa", "bono_usd": 400,
                 "resultado": "liquidada_sin_aviso", "clase": "mismo_bloque", "flash_cruce": None}]
        a = sr.analyze_live([{"bloque": 1, "ts": 1, "visto_ms": 1, "total_ms": 1}], [], liqs, [], [],
                            {"contadores": {}, "flash_evaluador": {"lectura_pendiente_ms": {"p50": 60}, "supuesto_envio_ms": 150}}, CFG, cruces)
        f = a["flash_cruces"]
        self.assertEqual((f["n"], f["go"], f["mismo_trozo"], f["liquidaciones_sin_cruce_visto"]), (3, 2, 1, 1))
        self.assertEqual((f["holgura"]["n"], f["holgura"]["positivas"], f["holgura"]["bono_positivo_usd"]), (2, 1, 300))
        self.assertEqual(f["decision_ms"]["p50"], 80)
        res = sr.build(None, None)
        res["vivo"] = {**a, "ventana": {"horas": 1, "bloques": 1, "bloques_en_rango": 1, "cobertura": 1, "desde_bloque": 1, "hasta_bloque": 1}}
        md = sr.render(res)
        self.assertIn("Evaluador del estado pendiente: 3 cruces vistos", md)
        self.assertIn("Holgura frente al ganador", md)
        self.assertIn("1 liquidaciones reales no se vieron cruzar antes", md)

    def test_absent_without_the_evaluator(self):
        a = sr.analyze_live([{"bloque": 1, "ts": 1, "visto_ms": 1, "total_ms": 1}], [], [], [], [], {"contadores": {}}, CFG)
        self.assertNotIn("flash_cruces", a)


class TestInputs(unittest.TestCase):
    def test_read_jsonl_tolerates_a_cut_last_line(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "x.jsonl")
        with open(p, "w") as fh:
            fh.write('{"a": 1}\n\n{"a": 2}\n{"a": 3, "b"')
        rows, bad = sr.read_jsonl(p)
        self.assertEqual((rows, bad), ([{"a": 1}, {"a": 2}], 1))
        self.assertEqual(sr.read_jsonl(os.path.join(d, "no_existe.jsonl")), ([], 0))
        self.assertIsNone(sr.read_json(os.path.join(d, "no_existe.json")))

    def test_empty_inputs_render_without_failing(self):
        res = sr.build(None, None)
        md = sr.render(res)
        self.assertIn("Sin datos del replay", md)
        self.assertIn("Sin datos del modo en vivo", md)
        self.assertIn("Qué NO prueba", md)
        d = tempfile.mkdtemp()
        res = sr.build(d, d)                                      # carpetas vacías
        self.assertIsNone(res["vivo"])
        self.assertIsNone(res["replay"])
        sr.render(res)


class TestEndToEnd(unittest.TestCase):
    """Corre el modo en vivo y el replay contra la Base falsa y arma el reporte con lo que escribieron."""

    @classmethod
    def setUpClass(cls):
        cls.env, cls.n_cross, _ = scenario()
        cls.env.sh.finish()
        cls.meta, cls.rows, cls.rdir = replay(cls.env, min_bonus_usd=1)
        cls.res = sr.build(cls.env.out, cls.rdir, {"min_bonus_usd": 1, "min_net_usd": 0})

    def test_live_section(self):
        lv = self.res["vivo"]
        self.assertEqual(lv["decisiones"]["por_decision"], {"GO": 4})        # U0, U1, U2 y U2 otra vez cuando el precio vuelve a caer
        go = lv["go"]
        self.assertEqual(go["destino"], {"liquidada": 2, "recuperada": 1, "abierta_al_cierre": 1})
        self.assertEqual((go["n"], go["cerrados"]), (4, 3))
        self.assertEqual(go["liquidadas_por_subasta"], 1)                     # U1 salió por la subasta
        self.assertEqual(go["llegada_medida"]["antes"]["n"], 2)               # con ~1.4 s de latencia el primer bloque propio es el +1
        self.assertEqual(lv["liquidaciones"]["n"], 3)
        self.assertEqual(lv["liquidaciones"]["clases"], {"con_aviso": 2, "mismo_bloque": 1})
        self.assertEqual(lv["liquidaciones"]["recall_visibles"], 1.0)
        self.assertEqual(lv["liquidaciones"]["vias"], {"directa": 2, "subasta": 1})
        self.assertGreater(lv["latencia"]["visto_mas_proceso_ms"]["p50"], 1000)
        self.assertEqual(lv["ventana"]["cobertura"], 1.0)

    def test_replay_section_matches_the_scenario(self):
        rp = self.res["replay"]
        g = rp["ganables"]
        self.assertEqual(g["elegibles"], 2)                                   # U0 (+2, directa) y U4 (0, directa); U1 fue subasta
        k1 = g["por_tiempo_total"][0]
        self.assertEqual((k1["antes"]["n"], k1["empate"]["n"], k1["tarde"]["n"]), (1, 0, 1))
        self.assertEqual(rp["vias"]["subasta"]["n"], 1)
        self.assertEqual((rp["paridad"]["n"], rp["paridad"]["exactas"]), (3, 3))

    def test_gates_and_markdown(self):
        states = {g["puerta"]: g["estado"] for g in self.res["puertas"]}
        self.assertEqual(states["Decisiones en tiempo real sin enviar nada"], "cumple")
        self.assertEqual(states["Cada GO comparado con lo que ocurrió"], "parcial")      # uno sigue abierto al cierre
        self.assertNotIn("falla", states.values())
        self.assertIn("eth_call", self.res["metodos_rpc"])
        md = sr.render(self.res)
        for text in ("## Respuesta corta", "Llegas antes", "Visto + proceso", "Puertas del Omega", "Qué NO prueba",
                     "GO liquidados por la subasta: 1", "Cobertura del libro"):
            self.assertIn(text, md)
        out = tempfile.mkdtemp()
        sr.write(self.res, out)
        with open(os.path.join(out, "shadow.json")) as fh:
            back = json.load(fh)
        self.assertEqual(back["vivo"]["go"]["n"], 4)
        self.assertTrue(os.path.exists(os.path.join(out, "RESUMEN_SHADOW.md")))


if __name__ == "__main__":
    unittest.main()
