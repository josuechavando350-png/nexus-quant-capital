"""Replay histórico del Shadow contra una Base falsa con historial por bloque."""

import json
import os
import sys
import tempfile
import time
import unittest
from dataclasses import replace as dc_replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fakemorpho as fm  # noqa: E402
from census_dinero import morpho as mo  # noqa: E402
from census_dinero.rpc import RpcError  # noqa: E402
from census_dinero.shadow_replay import (RDEFAULTS, earliest_available, event_bonus, pick_diag, prior_kept, run_replay,  # noqa: E402
                                          scan_logs, select_events)  # noqa: E402
from test_shadow_live import B, DROP, Env, S, U  # noqa: E402


def replay(env, **cfg):
    out = tempfile.mkdtemp()
    meta = run_replay({"margen_cabeza": 0, "trabajadores": 1, **cfg}, out, rpc=env.rpc, markets=env.cfg_markets)
    path = os.path.join(out, "replay.jsonl")
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            rows = [json.loads(x) for x in f]
    return meta, rows, out


def scenario(**env_kw):
    env = Env(**env_kw).ready((U[0], 1700), (U[1], 1700), (U[2], 1700))
    env.step([("set_price", env.mid, DROP)])                       # las tres cruzan aquí
    n_cross = env.chain.head
    env.step()
    env.step([("liquidate", env.mid, B[0], U[0])])                 # 2 bloques después del cruce
    env.step([("liquidate", env.mid, B[1], U[1], {"to": fm.AUCTION_ENTRY, "sender": S[2]})])    # 3 después, por subasta
    n_late = env.chain.head
    env.step([("set_price", env.mid, fm.PRICE_2000)])
    env.step([("supply_collateral", env.mid, U[4], 10 ** 18), ("borrow", env.mid, U[4], 1700 * 10 ** 6)])
    env.step([("set_price", env.mid, DROP), ("liquidate", env.mid, B[2], U[4])])      # cruce y liquidación en el mismo bloque
    return env, n_cross, n_late


class TestFindCross(unittest.TestCase):
    def test_distances_and_route(self):
        env, n_cross, n_late = scenario()
        meta, rows, _ = replay(env, min_bonus_usd=1)
        self.assertEqual((meta["procesados"], meta["fallidos"], meta["sin_dato"]), (3, 0, 0))
        by = {r["prestatario"]: r for r in rows}
        self.assertEqual((by[U[0]]["bloque_cruce"], by[U[0]]["delta_bloques"], by[U[0]]["via"]), (n_cross, 2, "directa"))
        self.assertEqual((by[U[1]]["delta_bloques"], by[U[1]]["via"], by[U[1]]["firmante"]), (3, "subasta", S[2]))
        self.assertEqual(by[U[4]]["delta_bloques"], 0)                          # mismo bloque: nadie pudo verlo antes
        self.assertFalse(any(r["censurado"] for r in rows))
        r0 = by[U[0]]
        self.assertAlmostEqual(r0["bono_usd"], 1700 * (mo.lif(fm.LLTV86) / 1e18 - 1), delta=0.01)
        self.assertAlmostEqual(r0["neto_modelo_usd"], r0["bono_usd"] * 0.8, places=6)
        self.assertGreater(r0["gas_usd"], 0)
        self.assertEqual(n_late - n_cross, 3)

    def test_censored_when_window_is_too_short(self):
        env, n_cross, _ = scenario()
        _, rows, _ = replay(env, min_bonus_usd=1, ventana_bloques=2)
        r = next(x for x in rows if x["prestatario"] == U[1])             # cruzó 3 bloques antes
        self.assertTrue(r["censurado"])
        self.assertEqual(r["delta_bloques"], 2)                           # cota inferior: "al menos la ventana"
        edge = next(x for x in rows if x["prestatario"] == U[0])          # cruzó justo en el borde de la ventana
        self.assertTrue(edge["censurado"])                                # sigue liquidable allí: no se puede confirmar el cruce

    def test_exact_binary_search_over_many_blocks(self):
        env = Env().ready((U[0], 1700))
        for _ in range(37):
            env.step()
        env.step([("set_price", env.mid, DROP)])
        n_cross = env.chain.head
        for _ in range(20):
            env.step()
        env.step([("liquidate", env.mid, B[0], U[0])])
        _, rows, _ = replay(env, min_bonus_usd=1)
        self.assertEqual((rows[0]["bloque_cruce"], rows[0]["delta_bloques"]), (n_cross, 21))

    def test_price_wobble_uses_last_continuous_stretch(self):
        env = Env().ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)])                          # liquidable
        env.step([("set_price", env.mid, fm.PRICE_2000)])                 # se recupera
        env.step()
        env.step([("set_price", env.mid, DROP)])
        n_cross = env.chain.head                                          # vuelve a cruzar: este es el que cuenta
        env.step()
        env.step([("liquidate", env.mid, B[0], U[0])])
        _, rows, _ = replay(env, min_bonus_usd=1)
        self.assertEqual((rows[0]["bloque_cruce"], rows[0]["delta_bloques"]), (n_cross, 2))


class TestResidual(unittest.TestCase):
    def test_race_for_the_residual_starts_at_the_partial_liquidation(self):
        env = Env().ready((U[0], 1700))
        for _ in range(10):
            env.step()                            # historia suficiente: la búsqueda hacia atrás no sale de la cadena falsa
        env.step([("set_price", env.mid, DROP)])
        n_cross = env.chain.head
        env.step()
        tenth = env.chain.positions[(env.mid, U[0])][1] // 10                       # un 10% no la deja sana
        env.step([("liquidate", env.mid, B[0], U[0], {"repaid_shares": tenth})])
        n_partial = env.chain.head
        env.step()
        env.step()
        env.step([("liquidate", env.mid, B[1], U[0])])                              # el resto, 3 bloques después de la parcial
        _, rows, _ = replay(env, min_bonus_usd=0.01)
        first, second = sorted(rows, key=lambda r: r["bloque_liquidacion"])
        self.assertEqual((first["bloque_cruce"], first["delta_bloques"], first["residual_de_liquidacion_parcial"]), (n_cross, 2, False))
        self.assertEqual((second["bloque_cruce"], second["delta_bloques"], second["residual_de_liquidacion_parcial"]), (n_partial, 3, True))

    def test_two_liquidations_in_one_block_count_as_same_block_for_the_second(self):
        env = Env().ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)])
        env.step()
        tenth = env.chain.positions[(env.mid, U[0])][1] // 10
        env.step([("liquidate", env.mid, B[0], U[0], {"repaid_shares": tenth}), ("liquidate", env.mid, B[1], U[0])])
        _, rows, _ = replay(env, min_bonus_usd=0.01)
        first, second = sorted(rows, key=lambda r: (r["bloque_liquidacion"], r["liquidador"]))
        self.assertEqual({r["delta_bloques"] for r in rows if r["residual_de_liquidacion_parcial"]}, {0})
        self.assertEqual(len(rows), 2)


class TestBookCoverage(unittest.TestCase):
    """¿Un libro que mira N días atrás conocería al prestatario? Con bloques de medio día para poder probarlo."""

    def make(self):
        env = Env().ready((U[0], 1700))
        for _ in range(30):
            env.step()
        env.step(env.open_position(U[1], 1700))                      # U1 pide prestado 30 bloques (15 días) después
        for _ in range(10):
            env.step()
        env.step([("set_price", env.mid, DROP)])
        env.step([("liquidate", env.mid, B[0], U[0]), ("liquidate", env.mid, B[1], U[1])])
        return env

    def test_age_of_last_borrow_before_liquidation(self):
        env = self.make()
        _, rows, _ = replay(env, min_bonus_usd=0.1, block_time_s=43_200)
        age = {r["prestatario"]: r["libro_edad_dias"] for r in rows}
        self.assertAlmostEqual(age[U[1]], 12 * 0.5)                  # 12 bloques de medio día
        self.assertAlmostEqual(age[U[0]], 43 * 0.5)

    def test_coverage_table_in_report(self):
        from census_dinero import shadow_report as sr
        env = self.make()
        meta, rows, _ = replay(env, min_bonus_usd=0.1, block_time_s=43_200)
        self.assertTrue(meta["borrow_scan"]["completo"])
        a = sr.analyze_replay(rows, [], meta, {"min_bonus_usd": 0.1, "min_net_usd": 0})
        cov = {x["dias"]: x["parte_n"] for x in a["cobertura_libro"]["por_dias_atras"]}
        self.assertEqual((cov[7], cov[30], cov[90]), (0.5, 1.0, 1.0))        # U1 (6 d) cabe en 7 días; U0 (21.5 d) en 30

    def test_borrow_older_than_the_scan_is_reported_as_unknown(self):
        env = self.make()
        meta, rows, _ = replay(env, min_bonus_usd=0.1, block_time_s=43_200, dias=10, libro_dias=5)   # ventana de 20 bloques + 10 antes
        by = {r["prestatario"]: r["libro_edad_dias"] for r in rows}
        self.assertIsNone(by[U[0]])
        self.assertIsNotNone(by[U[1]])

    def test_pruned_log_history_is_handled_and_reduces_the_measurable_lookback(self):
        from census_dinero import shadow_report as sr
        env = self.make()
        env.chain.logs_from = 5020                                   # el proveedor ya no guarda logs anteriores al bloque 5020
        meta, rows, _ = replay(env, min_bonus_usd=0.1, block_time_s=43_200, dias=10)
        self.assertEqual(meta["borrow_scan"]["desde"], 5020)
        self.assertTrue(meta["borrow_scan"]["completo"])
        by = {r["prestatario"]: r for r in rows}
        self.assertIsNone(by[U[0]]["libro_edad_dias"])               # su Borrow (5001) cae en lo que ya no se puede leer
        self.assertAlmostEqual(by[U[1]]["libro_historia_dias"], (5044 - 5020) * 0.5)
        a = sr.analyze_replay(rows, [], meta, {"min_bonus_usd": 0.1, "min_net_usd": 0})
        cov = {x["dias"]: x for x in a["cobertura_libro"]["por_dias_atras"]}
        self.assertEqual((cov[7]["n"], cov[7]["parte_n"]), (2, 0.5))   # con 7 días de historia: U1 conocido, U0 no
        self.assertEqual((cov[30]["n"], cov[30]["parte_n"]), (0, None))
        sr.render(sr.build(None, None))
        self.assertIn("sin historia suficiente", sr.render({**sr.build(None, None), "replay": a}))

    def test_scan_failure_of_the_book_coverage_does_not_abort_the_replay(self):
        env = self.make()
        env.chain.fail("eth_getLogs", times=10_000, message="boom", when=lambda p: p[0].get("topics", [[None]])[0] ==
                       [mo.EVENT_TOPICS["Borrow"]])
        meta, rows, _ = replay(env, min_bonus_usd=0.1, block_time_s=43_200)
        self.assertEqual(meta["procesados"], 2)
        self.assertFalse(meta["borrow_scan"]["completo"])
        self.assertIn("boom", meta["borrow_scan"]["error"])
        self.assertNotIn("libro_edad_dias", rows[0])

    def test_events_window_is_shortened_when_logs_are_pruned(self):
        env = self.make()
        env.chain.logs_from = 5030
        meta, rows, _ = replay(env, min_bonus_usd=0.1, block_time_s=43_200, dias=30)
        self.assertEqual(meta["ventana"]["desde"], 5030)
        self.assertEqual(meta["ventana"]["desde_pedido"], 5044 - 60)
        self.assertEqual(meta["procesados"], 2)
        self.assertEqual(meta["estado"], "completo")

    def test_switch_off(self):
        env = self.make()
        meta, rows, _ = replay(env, min_bonus_usd=0.1, block_time_s=43_200, libro_dias=0)
        self.assertNotIn("libro_edad_dias", rows[0])
        self.assertFalse(meta["borrow_scan"]["completo"])


class TestDiagnostic(unittest.TestCase):
    """La lupa: precio, salud y feeds del oráculo bloque a bloque alrededor de cada liquidación."""

    def same_block_update(self):
        env = Env().ready((U[0], 1700))
        for _ in range(6):
            env.step()
        env.step([("set_price", env.mid, DROP), ("liquidate", env.mid, B[0], U[0])])   # el precio se actualiza y se liquida en el mismo bloque
        env.step()
        return env

    def test_update_and_liquidation_in_the_same_block_are_visible(self):
        from census_dinero import shadow_report as sr
        env = self.same_block_update()
        meta, rows, out = replay(env, min_bonus_usd=0.1, diag=5)
        self.assertEqual(meta["diag"], {"filas": 1, "con_error": 0})
        with open(os.path.join(out, "diag.jsonl")) as fh:
            d = [json.loads(x) for x in fh][0]
        b = d["bloque_liquidacion"]
        by = {x["bloque"]: x for x in d["serie"]}
        self.assertFalse(by[b - 1]["liquidable"])
        self.assertTrue(by[b]["liquidable"] or by[b]["salud"] is None)             # tras liquidar ya no tiene deuda; antes estaba por debajo
        self.assertNotEqual(by[b - 1]["precio"], by[b]["precio"])
        self.assertNotEqual(by[b - 1]["feeds"]["BASE_FEED_1"]["ronda"], by[b]["feeds"]["BASE_FEED_1"]["ronda"])
        self.assertEqual(d["actualizacion_previa"]["tx_index"], 0)                  # la actualización fue la transacción 0 del bloque
        self.assertEqual(d["tx_index"], 1)                                          # y la liquidación la 1
        with open(os.path.join(out, "diag_oraculos.json")) as fh:
            orc = list(json.load(fh).values())[0]
        self.assertIn("M0 / USD", orc["detalle"]["BASE_FEED_1"]["descripcion"])
        with open(os.path.join(out, "diag_oraculos.json")) as fh:
            oracles = json.load(fh)
        a = sr.analyze_diag([d], oracles)
        self.assertEqual((a["n"], a["liquidable_un_bloque_antes"], a["precio_cambio_en_el_bloque"], a["feed_cambio_en_el_bloque"]), (1, 0, 1, 1))
        self.assertEqual(a["con_actualizacion_antes_en_el_bloque"], 1)
        self.assertEqual(a["tx_entre_actualizacion_y_liquidacion_mediana"], 1)

    def test_an_update_a_block_earlier_is_seen_as_liquidable_before(self):
        from census_dinero import shadow_report as sr
        env = Env().ready((U[0], 1700))
        for _ in range(6):
            env.step()
        env.step([("set_price", env.mid, DROP)])
        env.step([("liquidate", env.mid, B[0], U[0])])
        env.step()
        meta, rows, out = replay(env, min_bonus_usd=0.1, diag=5)
        self.assertEqual(rows[0]["delta_bloques"], 1)
        with open(os.path.join(out, "diag.jsonl")) as fh:
            d = [json.loads(x) for x in fh][0]
        a = sr.analyze_diag([d])
        self.assertEqual((a["liquidable_un_bloque_antes"], a["precio_cambio_en_el_bloque"], a["feed_cambio_en_el_bloque"]), (1, 0, 0))
        self.assertEqual(a["filas"][0]["bloques_desde_el_ultimo_cambio_de_feed"], 1)
        self.assertIsNone(d["actualizacion_previa"])

    def test_picks_are_spread_across_markets_and_skip_auctions(self):
        rows = [{"mercado": "A", "via": "directa", "bono_usd": 100 - i} for i in range(5)] + \
               [{"mercado": "B", "via": "directa", "bono_usd": 10 - i} for i in range(3)] + \
               [{"mercado": "C", "via": "subasta", "bono_usd": 1000}, {"mercado": "D", "via": "directa", "bono_usd": 5, "sin_dato": True}]
        picks = pick_diag(rows, 4)
        self.assertEqual([(p["mercado"], p["bono_usd"]) for p in picks], [("A", 100), ("B", 10), ("A", 99), ("B", 9)])
        self.assertEqual(pick_diag(rows, 0), [])
        self.assertEqual(len(pick_diag(rows, 100)), 8)

    def test_diag_off_by_default_and_errors_are_isolated(self):
        env = self.same_block_update()
        meta, rows, out = replay(env, min_bonus_usd=0.1)
        self.assertNotIn("diag", meta)
        self.assertFalse(os.path.exists(os.path.join(out, "diag.jsonl")))


class TestParallelScan(unittest.TestCase):
    def test_chunks_come_back_in_order_and_complete(self):
        env = Env().ready((U[0], 1700))
        for _ in range(40):
            env.step()
        logs, first, last, complete = scan_logs(env.rpc, env.sh.morpho, [mo.BOOK_EVENTS, env.sh.ids], 1, env.chain.head, workers=4, chunk=7)
        direct = env.rpc.get_logs(env.sh.morpho, [mo.BOOK_EVENTS, env.sh.ids], 1, env.chain.head)
        self.assertEqual(logs, direct)
        self.assertEqual((first, last, complete), (1, env.chain.head, True))

    def test_budget_returns_the_contiguous_prefix(self):
        env = Env().ready((U[0], 1700))
        for _ in range(20):
            env.step()
        logs, first, last, complete = scan_logs(env.rpc, env.sh.morpho, [mo.BOOK_EVENTS, env.sh.ids], 1, env.chain.head,
                                                deadline=time.monotonic() - 1, workers=2, chunk=5)
        self.assertFalse(complete)
        self.assertLess(last, env.chain.head)

    def test_earliest_available_is_parsed(self):
        self.assertEqual(earliest_available(RpcError("pruned history unavailable: requested 47866647, earliest available 51500000")), 51500000)
        self.assertIsNone(earliest_available(RpcError("boom")))

    def test_other_errors_are_raised(self):
        env = Env().ready((U[0], 1700))
        env.chain.fail("eth_getLogs", times=10_000, message="boom")
        with self.assertRaises(RpcError):
            scan_logs(env.rpc, env.sh.morpho, [mo.BOOK_EVENTS, env.sh.ids], 1, env.chain.head, workers=2, chunk=5)


class TestParity(unittest.TestCase):
    def test_exact_match_in_both_liquidation_modes(self):
        env = Env().ready((U[0], 1700), (U[1], 1700))
        env.step([("set_price", env.mid, DROP)])
        env.step([("liquidate", env.mid, B[0], U[0])])                                   # fija repaidShares
        seized = env.chain.positions[(env.mid, U[1])][2] // 2
        env.step([("liquidate", env.mid, B[0], U[1], {"seized": seized})])               # fija seizedAssets
        meta, rows, _ = replay(env, min_bonus_usd=1)
        modes = sorted(r["paridad"]["modo"] for r in rows)
        self.assertEqual(modes, ["repaid_shares", "seized_assets"])
        self.assertEqual(meta["paridad"]["n"], 2)
        self.assertEqual(meta["paridad"]["max"], 0.0)
        self.assertEqual(meta["paridad"]["exactas"], 2)

    def test_parity_includes_accrued_interest(self):
        env = Env(rate=int(0.4 / 31_536_000 * 1e18)).ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)], dt=7_200)                               # 2 horas de interés
        env.step([("liquidate", env.mid, B[0], U[0])], dt=7_200)
        meta, rows, _ = replay(env, min_bonus_usd=1)
        p = rows[0]["paridad"]
        self.assertTrue(p["con_interes"])
        self.assertLess(max(p["err_embargo"], p["err_shares"], p["err_repago"]), 1e-9)

    def test_parity_detects_a_wrong_model(self):
        env = Env().ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)])
        env.step([("liquidate", env.mid, B[0], U[0])])
        m = env.chain.markets[env.mid]
        m["params"] = dc_replace(m["params"], lltv=90 * 10 ** 16)         # el replay lee otro lltv: otro LIF, otro embargo
        meta, rows, _ = replay(env, min_bonus_usd=1)
        p = rows[0]["paridad"]
        self.assertGreater(max(p["err_embargo"], p["err_shares"]), 1e-4)
        self.assertEqual(meta["paridad"]["dentro_1e6"], 0)

    def test_bad_debt_skips_parity(self):
        env = Env().ready((U[0], 1700))
        env.step([("set_price", env.mid, 1000 * 10 ** 24)])
        env.step([("liquidate", env.mid, B[0], U[0], {"seized": 10 ** 18})])       # embarga todo el colateral: queda deuda sin respaldo
        meta, rows, _ = replay(env, min_bonus_usd=1)
        self.assertEqual(rows[0]["paridad"], {"omitida": "deuda_mala"})
        self.assertTrue(rows[0]["deuda_mala"])


class TestRunMechanics(unittest.TestCase):
    def test_select_events_top_plus_even_sample(self):
        env = Env().open()
        info = env.sh.markets
        evs = [{"market": env.mid, "block": 100 + i, "log_index": 0, "repaid_assets": (1000 - i) * 10 ** 6} for i in range(200)]
        evs.append({"market": "0x" + "ee" * 32, "block": 1, "log_index": 0, "repaid_assets": 10 ** 12})       # mercado no vigilado
        chosen = select_events(evs, info, {**RDEFAULTS, "top": 5, "max": 25, "min_bonus_usd": 1})
        self.assertEqual(len(chosen), 25)
        self.assertEqual([e["block"] for e in chosen[:5]], [100, 101, 102, 103, 104])         # las 5 más grandes
        blocks = [e["block"] for e in chosen[5:]]
        self.assertEqual(blocks, sorted(blocks))
        self.assertGreater(blocks[-1] - blocks[0], 100)                                          # muestra repartida, no pegada
        self.assertEqual(chosen, select_events(evs, info, {**RDEFAULTS, "top": 5, "max": 25, "min_bonus_usd": 1}))
        small = select_events(evs, info, {**RDEFAULTS, "top": 5, "max": 25, "min_bonus_usd": 100_000})
        self.assertEqual(small, [])

    def test_sample_weights_estimate_the_whole_window(self):
        env = Env().open()
        info = env.sh.markets
        evs = [{"market": env.mid, "block": 100 + i, "log_index": 0, "repaid_assets": (1000 - i) * 10 ** 6} for i in range(200)]
        chosen = select_events(evs, info, {**RDEFAULTS, "top": 5, "max": 25, "min_bonus_usd": 1})
        self.assertEqual([e["_grupo"] for e in chosen[:5]], ["top"] * 5)
        self.assertTrue(all(e["_grupo"] == "muestra" and e["_peso"] == 195 / 20 for e in chosen[5:]))
        total = sum(event_bonus(e, info) for e in evs)
        estimated = sum(event_bonus(e, info) * e["_peso"] for e in chosen)
        self.assertAlmostEqual(estimated / total, 1.0, delta=0.02)           # la muestra reparte bien el total
        few = select_events(evs[:10], info, {**RDEFAULTS, "top": 5, "max": 25, "min_bonus_usd": 1})
        self.assertEqual({e["_peso"] for e in few}, {1.0})                   # si cabe todo, nada se pondera

    def test_prior_kept_needs_enough_samples(self):
        self.assertEqual(prior_kept({"kept_dir": 0.9, "n_dir": 40}), 0.9)
        self.assertEqual(prior_kept({"kept_dir": 0.9, "n_dir": 3}), 0.678)
        self.assertEqual(prior_kept({"kept_dir": None, "n_dir": 400}), 0.678)

    def test_rpc_errors_are_counted_not_fatal(self):
        env = Env().ready((U[0], 1700), (U[1], 1700))
        env.step([("set_price", env.mid, DROP)])
        env.step([("liquidate", env.mid, B[0], U[0]), ("liquidate", env.mid, B[0], U[1])])
        env.chain.fail("eth_getTransactionByHash", times=1000, message="boom")
        meta, rows, out = replay(env, min_bonus_usd=1)
        self.assertEqual((meta["procesados"], meta["fallidos"]), (0, 2))
        self.assertTrue(os.path.exists(os.path.join(out, "replay_errores.jsonl")))

    def test_without_archive_nothing_is_invented(self):
        env = Env(archive_blocks=1).ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)])
        env.step([("liquidate", env.mid, B[0], U[0])])
        for _ in range(5):
            env.step()
        meta, rows, _ = replay(env, min_bonus_usd=1)
        self.assertEqual(rows, [])
        self.assertEqual(meta["fallidos"], 1)

    def test_time_budget_stops_new_work(self):
        env = Env().ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)])
        env.step([("liquidate", env.mid, B[0], U[0])])
        meta, rows, _ = replay(env, min_bonus_usd=1, presupuesto_min=0.0)
        self.assertEqual((meta["procesados"], meta["omitidos_por_tiempo"]), (0, 1))

    def test_flashblocks_probe_is_optional_and_reported(self):
        env, _, _ = scenario()
        meta, _, _ = replay(env, min_bonus_usd=1)
        self.assertNotIn("flashblocks", meta)
        meta, rows, _ = replay(env, min_bonus_usd=1, flash_probe=0.4)
        self.assertEqual(meta["procesados"], 3)
        probe = list(meta["flashblocks"].values())[0]
        self.assertGreater(probe["llamadas"], 0)

    def test_flashblocks_probe_failure_never_breaks_the_replay(self):
        env, _, _ = scenario()
        env.chain.fail("eth_getBlockByNumber", times=10_000, message="pending no soportado", when=lambda p: p[0] == "pending")
        meta, rows, _ = replay(env, min_bonus_usd=1, flash_probe=0.3)
        self.assertEqual(meta["procesados"], 3)
        self.assertIn("pending no soportado", list(list(meta["flashblocks"].values())[0]["errores"])[0])

    def test_meta_has_window_and_rpc_report(self):
        env, _, _ = scenario()
        meta, _, out = replay(env, min_bonus_usd=1, dias=1)
        self.assertEqual(meta["ventana"]["hasta_leido"], env.chain.head)
        self.assertEqual(meta["eventos_en_ventana"], 3)
        self.assertGreater(meta["bono_total_usd"], 0)
        self.assertAlmostEqual(meta["bono_elegido_usd"], meta["bono_elegible_usd"], places=6)
        self.assertIn("rpc", meta)
        self.assertTrue(os.path.exists(os.path.join(out, "replay_meta.json")))


if __name__ == "__main__":
    unittest.main()
