"""Replay histórico del Shadow contra una Base falsa con historial por bloque."""

import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace as dc_replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fakemorpho as fm  # noqa: E402
from census_dinero import morpho as mo  # noqa: E402
from census_dinero.shadow_replay import RDEFAULTS, event_bonus, prior_kept, run_replay, select_events  # noqa: E402
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
