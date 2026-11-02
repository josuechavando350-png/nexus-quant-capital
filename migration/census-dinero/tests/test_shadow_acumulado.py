"""Acumulado de varias corridas en vivo: peleables, ventana frente al ganador, holgura estimada y rivales."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from census_dinero import shadow_acumulado as sa  # noqa: E402
from census_dinero.__main__ import main  # noqa: E402


def write_run(root, run_id, liqs=(), updates=(), rapid=(), p50=0.2, hours=1.0):
    d = os.path.join(root, "corridas", str(run_id), "shadow-vivo")
    os.makedirs(d)
    with open(os.path.join(d, "bloques.jsonl"), "w") as fh:
        for ts in (1000, 1000 + int(hours * 3600)):
            fh.write(json.dumps({"bloque": ts, "ts": ts}) + "\n")
    with open(os.path.join(d, "resultados.jsonl"), "w") as fh:
        fh.write(json.dumps({"resultado": "recuperada", "bono_usd": 3}) + "\n")            # un cierre de candidata: no es una liquidación
        for r in liqs:
            fh.write(json.dumps(r) + "\n")
    for name, rows in (("flash_actualizaciones.jsonl", updates), ("flash_rapido.jsonl", rapid)):
        with open(os.path.join(d, name), "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
    with open(os.path.join(d, "meta.json"), "w") as fh:
        json.dump({"via_rapida": {"decision_ms": {"p50": p50}}}, fh)
    return d


def liq(bono, via="directa", **flash):
    return {"bloque_liquidacion": 1, "etiqueta": "M/USDC", "tx": "0x" + format(int(bono * 100), "064x"), "bono_usd": bono, "via": via,
            "entrada": "0x" + "a1" * 20, "firmante": "0x" + "11" * 20, "flash": flash}


class TestAccumulated(unittest.TestCase):
    def make(self):
        root = tempfile.mkdtemp()
        write_run(root, 100, [liq(5, trozos_entre=0, ws_ventana_ms=3)])                    # misma trozo: no se pelea; corrida vieja
        write_run(root, 200, [liq(50, trozos_entre=1, ws_ventana_ms=210, actualizacion_tx="0xAB"),
                              liq(0.4, trozos_entre=1, ws_ventana_ms=190),                 # peleable pero de bono chico
                              liq(80, via="subasta", trozos_entre=1, ws_ventana_ms=200)],  # por subasta: no se pelea
                  updates=[{"tx": "0xab", "decision_ms": 0.5}], hours=5.5)
        write_run(root, 300, [liq(20, trozos_entre=1, ws_ventana_ms=15),                   # peleable pero la ventana no alcanza
                              liq(30, ws_ventana_ms=205, propinas={"u": 100, "l": 150, "gap": 3, "n": 900, "antes_de_l": 90,
                                                                    "despues_de_l": 140, "entre": None}),   # sin trozos medidos: por propinas
                              liq(60, trozos_entre=2)],                                    # sin ventana por WebSocket
                  rapid=[{"resultado": "liquidada", "holgura_ms": 150.0}, {"resultado": "liquidada", "holgura_ms": -5.0},
                         {"resultado": "no_liquidada_en_el_bloque"}], p50=0.3, hours=5.5)
        return root

    def test_counts_what_could_be_fought_and_whether_we_would_be_on_time(self):
        root = self.make()
        dirs = sa.run_dirs(root, desde=200)
        self.assertEqual([os.path.basename(os.path.dirname(d)) for d in dirs], ["200", "300"])
        a = sa.acumulado(dirs)
        self.assertEqual((a["liquidaciones"]["n"], a["liquidaciones"]["directas"]), (6, 5))
        p = a["peleables"]
        self.assertEqual((p["n"], p["con_ventana"], p["que_valen"], p["a_tiempo"]), (5, 4, 3, 2))
        self.assertEqual((p["bono_que_valen_usd"], p["bono_a_tiempo_usd"]), (100, 80))
        by = {c["bono_usd"]: c for c in p["casos"]}
        self.assertEqual((by[50]["decision_ms"], by[50]["holgura_est_ms"]), (0.2, 189.8))   # hash→hash sin origen común: solo mediana
        self.assertEqual((by[30]["decision_ms"], by[30]["holgura_est_ms"]), (0.3, 184.7))   # si no, la mediana de la corrida
        self.assertEqual(by[20]["holgura_est_ms"], -5.3)
        v = a["via_rapida_vio_el_cruce"]
        self.assertEqual((v["n"], v["positivas"]), (2, 1))
        self.assertEqual(a["horas"], 11.0)
        md = sa.render(a)
        self.assertIn("2 corridas en vivo, 11.0 h", md)
        self.assertIn("habríamos llegado a tiempo para el trozo del ganador en 2 ($80 de $100)", md)
        self.assertIn("Muestra: 0 de 20 casos", md)
        self.assertEqual(a["muestra"]["n"], 0)  # las medianas y las propinas no se convierten en evidencia exacta
        self.assertIn("Es una cota optimista", md)

    def test_rivals_are_summed_across_runs(self):
        root = tempfile.mkdtemp()
        att = {"ganador_lleva_prestatario": True, "propina_ganador": 100, "n": 1,
               "lista": [{"i": 9, "tx": "0x9", "propina": 80, "de": "0x" + "c0" * 20, "a": "0x" + "b2" * 20,
                          "lugar": "mismo_trozo_menos_propina", "mismo_bot": False}]}
        write_run(root, 1, [liq(40, trozos_entre=1, ws_ventana_ms=200, intentos=att)])
        write_run(root, 2, [liq(10, trozos_entre=1, ws_ventana_ms=200, intentos=dict(att, n=0, lista=[]))])
        a = sa.acumulado(sa.run_dirs(root))
        self.assertEqual((a["rivales"]["liquidaciones"], a["rivales"]["con_rivales"]), (2, 1))
        self.assertIn("Rivales: en 1 de 2 liquidaciones otro bot lo intentó y perdió", sa.render(a))

    def test_empty_and_the_command_line(self):
        a = sa.acumulado([])
        self.assertEqual((a["liquidaciones"]["n"], a["peleables"]["que_valen"]), (0, 0))
        self.assertIn("Muestra: 0 de 20", sa.render(a))
        self.assertEqual(sa.run_dirs(tempfile.mkdtemp()), [])
        root = self.make()
        out = tempfile.mkdtemp()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["shadow-acumulado", "--resultados", root, "--desde", "200", "--min-bono", "25", "--out", out])
        self.assertEqual(code, 0)
        self.assertIn("Con bono de $25 o más: 2", buf.getvalue())
        with open(os.path.join(out, "acumulado.json")) as fh:
            self.assertEqual(json.load(fh)["peleables"]["que_valen"], 2)
        self.assertTrue(os.path.exists(os.path.join(out, "ACUMULADO.md")))


def exact_case(bono=50, window=200.0, decision=5.0, idx=0):
    update = {"tx": "0xab", "bloque": 1, "mercados": ["0xmarket"], "t_log": 100.0, "decision_ms": decision}
    r = liq(bono, trozos_entre=1, ws_ventana_ms=400.0, actualizacion_tx="0xab")
    r.update(log_index=idx, mercado="0xmarket")
    r["flash"]["ws_decision"] = {"schema": "nqc-shadow-log-window-v1", "actualizacion_tx": "0xab",
        "liquidacion_tx": r["tx"], "mercado": "0xmarket", "bloque": 1, "t_log": 100.0,
        "t_liquidacion": 100.0 + window / 1000, "ventana_ms": window, "decision_ms": decision}
    return r, update


class TestEvidenceSample(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def build(self):
        return sa.acumulado(sa.run_dirs(self.root))

    def test_log_window_and_its_decision_share_the_same_time_origin(self):
        r, u = exact_case(window=60, decision=50)
        write_run(self.root, 1, [r], updates=[u], p50=0.1)
        a = self.build()
        c = a["muestra"]["casos"][0]
        self.assertEqual((c["ventana_ms"], c["decision_ms"], c["holgura_est_ms"]), (60, 50, -10))
        self.assertEqual(a["muestra"]["a_tiempo_estimado"], 0)  # usar la ventana del hash (400) daría un falso positivo

    def test_cannot_borrow_a_matching_update_from_another_run(self):
        r, u = exact_case()
        write_run(self.root, 1, [r])
        write_run(self.root, 2, [], updates=[u])
        self.assertEqual(self.build()["muestra"]["n"], 0)

    def test_wrong_market_block_timestamp_or_decision_cannot_enter_sample(self):
        for field, value in (("mercados", ["0xother"]), ("bloque", 2), ("t_log", 99.0), ("decision_ms", 4.0)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as root:
                r, u = exact_case()
                u[field] = value
                write_run(root, 1, [r], updates=[u])
                self.assertEqual(sa.acumulado(sa.run_dirs(root))["muestra"]["n"], 0)

    def test_duplicate_events_not_counted_but_distinct_logs_in_same_tx_are(self):
        r, u = exact_case()
        r2 = json.loads(json.dumps(r))
        r2["log_index"] = 1
        d = write_run(self.root, 1, [r, r, r2], updates=[u])
        a = sa.acumulado([d, d])
        self.assertEqual((len(a["corridas"]), a["liquidaciones"]["n"], a["muestra"]["n"]), (1, 2, 2))
        self.assertEqual(a["calidad"]["eventos_duplicados"], 1)

    def test_conflicting_observations_are_not_selected_for_better_slack(self):
        r, u = exact_case()
        r2 = json.loads(json.dumps(r))
        r2["flash"]["ws_decision"]["ventana_ms"] = 500
        write_run(self.root, 1, [r], updates=[u])
        write_run(self.root, 2, [r2], updates=[u])
        a = self.build()
        self.assertEqual((a["liquidaciones"]["n"], a["muestra"]["n"], a["calidad"]["conflictos"]), (1, 0, 1))

    def test_inferred_trozos_or_missing_log_index_only_enter_descriptive_counts(self):
        for field in ("trozos", "identity"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as root:
                r, u = exact_case()
                if field == "identity":
                    del r["log_index"]
                else:
                    del r["flash"]["trozos_entre"]
                    r["flash"]["propinas"] = {"u": 100, "l": 150, "gap": 3, "n": 900, "antes_de_l": 90,
                                                "despues_de_l": 140, "entre": None}
                write_run(root, 1, [r], updates=[u])
                a = sa.acumulado(sa.run_dirs(root))
                self.assertEqual((a["peleables"]["que_valen"], a["muestra"]["n"]), (1, 0))

    def test_invalid_or_negative_decision_and_changed_window_are_rejected(self):
        for field, value in (("decision_ms", -1), ("decision_ms", float("nan")), ("ventana_ms", 500),
                             ("t_liquidacion", float("inf")), ("decision_ms", True)):
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as root:
                r, u = exact_case()
                r["flash"]["ws_decision"][field] = value
                write_run(root, 1, [r], updates=[u])
                self.assertEqual(sa.acumulado(sa.run_dirs(root))["muestra"]["n"], 0)

    def test_losing_windows_remain_in_sample_to_avoid_selection_bias(self):
        for i, window in enumerate((0, -20)):
            r, u = exact_case(window=window, idx=i)
            write_run(self.root, i + 1, [r], updates=[u])
        a = self.build()
        self.assertEqual((a["muestra"]["n"], a["muestra"]["a_tiempo_estimado"]), (2, 0))

    def test_truncated_inputs_are_disclosed_and_excluded_from_sample(self):
        r, u = exact_case()
        d = write_run(self.root, 1, [r], updates=[u])
        with open(os.path.join(d, "resultados.jsonl"), "a") as fh:
            fh.write('{"partial":')
        a = self.build()
        self.assertEqual((a["muestra"]["n"], a["calidad"]["lineas_invalidas"]), (0, 1))
        self.assertEqual(len(a["fuentes"][0]["sha256"]["resultados.jsonl"]), 64)

    def test_twenty_cases_only_open_review_without_certifying_money(self):
        rows = [exact_case(idx=i)[0] for i in range(20)]
        write_run(self.root, 1, rows, updates=[exact_case()[1]])
        a = self.build()
        self.assertEqual((a["muestra"]["n"], a["muestra"]["faltan"], a["muestra"]["estado"]), (20, 0, "LISTA_PARA_REVISION"))
        self.assertFalse(a["muestra"]["captura_demostrada"])
        self.assertFalse(a["muestra"]["rentabilidad_demostrada"])


if __name__ == "__main__":
    unittest.main()
