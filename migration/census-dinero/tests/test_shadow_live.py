"""Shadow en vivo contra una Base falsa: libro, cruces, decisiones, resultados, crítico y latencia."""

import json
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fakemorpho as fm  # noqa: E402
from census_dinero import morpho as mo  # noqa: E402
from census_dinero.rpc import Rpc, RpcError  # noqa: E402
from census_dinero.shadow_live import HeadWatcher, LogBloom, Shadow, bloom_bits, bloom_has, run_live  # noqa: E402


def no_sleep(_):
    return None


class Clock:
    def __init__(self):
        self.w, self.m = fm.T0 + 2 * 5000 + 1.0, 0.0

    def wall(self):
        return self.w

    def mono(self):
        self.m += 0.005
        return self.m


def prior(**kw):
    base = {"n": 400, "n_dir": 300, "dir_bonus": 20000, "kept_dir": 0.8, "auc_n": 0.1, "auc_bonus": 0.05}
    return {**base, **kw}


class Env:
    def __init__(self, cfg=None, markets=1, prior_kw=None, multicall=True, rate=0, archive_blocks=None):
        self.chain = fm.FakeMorpho(multicall=multicall, archive_blocks=archive_blocks)
        self.mids = [self.chain.add_market(f"M{i}", rate=rate) for i in range(markets)]
        self.mid = self.mids[0]
        self.cfg_markets = [{"id": m, "label": f"M{i}/USDC", **prior(**(prior_kw or {}))} for i, m in enumerate(self.mids)]
        self.rpc = Rpc(["https://fake"], transport=self.chain, sleep=no_sleep, rps=0, expected_chain_id=8453)
        self.clock = Clock()
        self.out = tempfile.mkdtemp()
        self.sh = Shadow(self.rpc, self.out, cfg, markets=self.cfg_markets, wall=self.clock.wall, mono=self.clock.mono)

    def open(self, actions=()):
        """Arma posiciones iniciales, hace el arranque y deja listo el libro."""
        if actions:
            self.chain.mine(actions)
        self.sh.setup()
        self.sh.bootstrap(self.chain.head)
        return self

    def step(self, actions=(), lag=1.2, dt=2):
        n = self.chain.mine(actions, dt)
        ts = int(self.chain.headers[n]["timestamp"], 16)
        self.clock.w = ts + lag
        seen = self.clock.mono()
        self.sh.process_block(n, self.clock.w, seen)
        return n

    def rows(self, name):
        path = os.path.join(self.out, name)
        if not os.path.exists(path):
            return []
        with open(path) as fh:
            return [json.loads(x) for x in fh if x.strip()]

    def open_position(self, user, borrow_usdc, collateral=10 ** 18, mid=None):
        mid = mid or self.mid
        return [("supply_collateral", mid, user, collateral), ("borrow", mid, user, round(borrow_usdc * 10 ** 6))]

    def ready(self, *specs):
        """specs: (usuario, deuda en USDC[, colateral]). Mina las posiciones y deja listo el libro."""
        actions = []
        for spec in specs:
            actions += self.open_position(*spec)
        return self.open(actions)


U, B, S = fm.USERS, fm.BOTS, fm.SIGNERS
DROP = 1900 * 10 ** 24          # con 1 token y 86%: liquidable si debe más de 1634 USDC


class TestFlow(unittest.TestCase):
    def test_cross_go_then_liquidated_by_someone_else(self):
        env = Env().ready((U[0], 1700), (U[1], 1000))
        self.assertEqual(env.sh.book.active_count(), 2)
        n0 = env.step([("set_price", env.mid, DROP)])
        dec = env.rows("decisiones.jsonl")
        self.assertEqual(len(dec), 1)
        d = dec[0]
        self.assertEqual((d["decision"], d["razon"], d["bloque_cruce"], d["prestatario"]), ("GO", "ok", n0, U[0]))
        self.assertEqual(d["visto_ms"], 1200)
        self.assertGreater(d["decidido_ms"], 0)
        self.assertAlmostEqual(d["bono_usd"], 1700 * (mo.lif(fm.LLTV86) / 1e18 - 1), delta=0.01)
        self.assertAlmostEqual(d["neto_modelo_usd"], d["bono_usd"] * 0.8, places=6)
        self.assertTrue(d["critico"]["paridad_libro"])
        self.assertEqual(d["bloque_llegada_propia"], n0 + 1)                    # 1200 + proceso + 150 ms < 2 s
        n1 = env.step([("liquidate", env.mid, B[0], U[0], {"sender": S[1], "gas_price": 2 * 10 ** 7})])
        res = env.rows("resultados.jsonl")
        self.assertEqual(len(res), 1)
        r = res[0]
        self.assertEqual((r["resultado"], r["delta_bloques"], r["liquidador"], r["via"]), ("liquidada", 1, B[0], "directa"))
        self.assertEqual((r["bloque_cruce"], r["bloque_liquidacion"], r["decision"], r["llegada"]), (n0, n1, "GO", "empate"))
        self.assertEqual(r["firmante"], S[1])
        self.assertGreater(r["gas_usd"], 0)
        self.assertGreater(r["propina_usd"], 0)
        self.assertEqual(env.sh.outcomes["GO_liquidada"], 1)
        self.assertNotIn((env.mid, U[0]), env.sh.pending)
        # la posición quedó con colateral sobrante y sin deuda: ya no está activa
        self.assertFalse(env.sh.book.is_active(env.mid, U[0]))

    def test_arrival_is_before_when_winner_is_slow(self):
        env = Env().ready((U[0], 1700))
        n0 = env.step([("set_price", env.mid, DROP)])
        env.step()
        env.step()
        env.step([("liquidate", env.mid, B[0], U[0])])
        r = env.rows("resultados.jsonl")[0]
        self.assertEqual((r["delta_bloques"], r["llegada"]), (3, "antes"))
        self.assertEqual(r["bloque_cruce"], n0)

    def test_same_block_is_late_by_construction(self):
        env = Env().ready((U[0], 1700))
        n = env.step([("set_price", env.mid, DROP), ("liquidate", env.mid, B[0], U[0], {"to": fm.AUCTION_ENTRY})])
        self.assertEqual(env.rows("decisiones.jsonl"), [])                  # nunca estuvo liquidable al cierre de un bloque
        r = env.rows("resultados.jsonl")[0]
        self.assertEqual((r["resultado"], r["clase"], r["delta_bloques"], r["llegada"], r["via"]),
                         ("liquidada_sin_aviso", "mismo_bloque", 0, "tarde", "subasta"))
        self.assertEqual(r["bloque_liquidacion"], n)
        self.assertFalse(r["detectada_antes"])

    def test_position_unknown_to_the_book(self):
        env = Env()
        env.chain.positions[(env.mid, U[3])] = [0, 1700 * 10 ** 12, 10 ** 18]      # existe en cadena, sin eventos
        env.chain.markets[env.mid]["state"][2:4] = [1700 * 10 ** 6, 1700 * 10 ** 12]
        env.open()
        self.assertEqual(env.sh.book.active_count(), 0)
        env.step([("set_price", env.mid, DROP)])
        env.step([("liquidate", env.mid, B[0], U[3])])
        r = env.rows("resultados.jsonl")[0]
        self.assertEqual((r["resultado"], r["clase"]), ("liquidada_sin_aviso", "fuera_del_libro"))
        self.assertIsNone(r["delta_bloques"])

    def test_recovery_by_price(self):
        env = Env().ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)])
        env.step([("set_price", env.mid, fm.PRICE_2000)])
        r = env.rows("resultados.jsonl")[0]
        self.assertEqual((r["resultado"], r["causa"], r["duracion_bloques"], r["decision"]), ("recuperada", "precio", 1, "GO"))
        self.assertEqual(env.sh.outcomes["GO_recuperada"], 1)

    def test_recovery_by_repay_and_by_collateral(self):
        env = Env().ready((U[0], 1700), (U[1], 1700))
        env.step([("set_price", env.mid, DROP)])
        env.step([("repay", env.mid, U[0], 10 ** 15), ("supply_collateral", env.mid, U[1], 10 ** 17)])
        causes = sorted(r["causa"] for r in env.rows("resultados.jsonl"))
        self.assertEqual(causes, ["movimiento_de_la_posicion", "movimiento_de_la_posicion"])

    def test_expiry_and_no_reflag(self):
        env = Env({"expire_blocks": 3}).ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)])
        for _ in range(5):
            env.step()
        res = env.rows("resultados.jsonl")
        self.assertEqual([r["resultado"] for r in res], ["expirada"])
        self.assertEqual(len(env.rows("decisiones.jsonl")), 1)               # no se vuelve a marcar mientras siga igual
        env.step([("set_price", env.mid, fm.PRICE_2000)])                    # sana otra vez: se olvida
        env.step([("set_price", env.mid, DROP)])
        self.assertEqual(len(env.rows("decisiones.jsonl")), 2)

    def test_liquidation_after_expiry_is_not_a_same_block_miss(self):
        env = Env({"expire_blocks": 3}).ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)])
        for _ in range(5):
            env.step()
        env.step([("liquidate", env.mid, B[0], U[0])])
        last = env.rows("resultados.jsonl")[-1]
        self.assertEqual((last["resultado"], last["clase"]), ("liquidada_tras_expirar", "tras_expirar"))
        self.assertIsNone(last["delta_bloques"])
        self.assertIsNone(last["llegada"])
        self.assertEqual(env.sh.outcomes["tras_expirar"], 1)
        self.assertEqual(env.sh.outcomes["mismo_bloque"], 0)

    def test_partial_liquidation_leaves_residual_candidate(self):
        env = Env().ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)])
        tenth = env.chain.positions[(env.mid, U[0])][1] // 10      # liquidar la mitad lo dejaría sano; un 10% no
        env.step([("liquidate", env.mid, B[0], U[0], {"repaid_shares": tenth})])
        dec = env.rows("decisiones.jsonl")
        self.assertEqual(len(dec), 2)
        self.assertTrue(dec[1]["residual_de_liquidacion_parcial"])
        self.assertEqual(env.rows("resultados.jsonl")[0]["resultado"], "liquidada")


class TestDecisions(unittest.TestCase):
    def only(self, env):
        dec = env.rows("decisiones.jsonl")
        self.assertEqual(len(dec), 1)
        return dec[0]

    def test_small_bonus(self):
        env = Env()
        env.open([("supply_collateral", env.mid, U[0], 10 ** 17), ("borrow", env.mid, U[0], 170 * 10 ** 6)])
        env.step([("set_price", env.mid, DROP)])            # 0.1 token a 1900 = 190 USDC; tope 163: liquidable, bono ~7
        d = self.only(env)
        self.assertEqual((d["decision"], d["razon"]), ("NO-GO", "bono_bajo"))
        self.assertLess(d["bono_usd"], 10)

    def test_bad_debt(self):
        env = Env().ready((U[0], 1700))
        env.step([("set_price", env.mid, 1000 * 10 ** 24)])                # el colateral ya no cubre ni la deuda
        d = self.only(env)
        self.assertEqual((d["decision"], d["razon"]), ("NO-GO", "deuda_mala"))
        self.assertGreater(d["deuda_mala_usd"], 0)

    def test_auction_dominated_market_is_no_go_by_prior(self):
        env = Env(prior_kw={"auc_bonus": 0.97, "dir_bonus": 120}).ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)])
        self.assertEqual(self.only(env)["razon"], "mercado_de_subasta")

    def test_low_net_after_retention(self):
        env = Env({"min_net_usd": 70}, prior_kw={"kept_dir": 0.5}).ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)])
        d = self.only(env)
        self.assertEqual((d["decision"], d["razon"]), ("NO-GO", "neto_bajo"))
        self.assertLess(d["neto_modelo_usd"], 70)

    def test_prior_without_enough_samples_uses_global(self):
        env = Env(prior_kw={"n_dir": 3, "kept_dir": 0.1}).ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)])
        self.assertEqual(self.only(env)["retencion_prior"], 0.678)

    def test_critic_blocks_go_when_book_disagrees_with_chain(self):
        env = Env().ready((U[0], 1700))
        env.chain.positions[(env.mid, U[0])][2] += 5 * 10 ** 15            # cambio de colateral sin evento (el libro no lo vio)
        env.step([("set_price", env.mid, DROP)])
        d = self.only(env)
        self.assertEqual((d["decision"], d["razon"]), ("NO-GO", "discrepancia_libro"))
        self.assertFalse(d["critico"]["paridad_libro"])
        # el libro se corrige con la lectura directa
        self.assertEqual(env.sh.book.pos[(env.mid, U[0])].collateral, env.chain.positions[(env.mid, U[0])][2])

    def test_critic_flags_oracle_jump_as_observar(self):
        env = Env().ready((U[0], 2300, 2 * 10 ** 18))      # 2 tokens: tope 3440 a 2000
        env.step([("set_price", env.mid, 1300 * 10 ** 24)])  # -35% en un bloque: tope 2236 < 2300, sin deuda mala
        d = self.only(env)
        self.assertEqual((d["decision"], d["razon"]), ("OBSERVAR", "oraculo_anomalo"))
        self.assertAlmostEqual(d["critico"]["salto_precio"], 0.35, places=6)

    def test_critic_rejects_stale_data(self):
        env = Env().ready((U[0], 1700))
        env.step([("set_price", env.mid, DROP)], lag=45)
        d = self.only(env)
        self.assertEqual((d["decision"], d["razon"]), ("NO-GO", "datos_viejos"))

    def test_interest_accrual_flags_a_borderline_position(self):
        env = Env(rate=int(0.5 / 31_536_000 * 1e18)).ready((U[0], 1719.9))   # 50% anual; 1719.9 de 1720 de tope
        self.assertTrue(mo.is_healthy(env.chain.positions[(env.mid, U[0])][1], 10 ** 18, fm.PRICE_2000, fm.LLTV86,
                                      mo.MarketState(*env.chain.markets[env.mid]["state"])))
        env.step(dt=20_000)                                                # unas 5 horas sin interactuar con el mercado
        d = self.only(env)
        self.assertTrue(d["con_interes"])
        self.assertLess(d["salud"], 1)


class TestSystem(unittest.TestCase):
    def test_multicall_missing_falls_back_to_single_calls(self):
        env = Env(multicall=False).ready((U[0], 1700))
        self.assertFalse(env.sh.multicall_ok)
        env.step([("set_price", env.mid, DROP)])
        self.assertEqual(env.rows("decisiones.jsonl")[0]["decision"], "GO")
        self.assertFalse(env.sh.meta["multicall"]["ok"])

    def test_multicall_proved_when_available(self):
        env = Env().open()
        self.assertTrue(env.sh.multicall_ok)
        self.assertTrue(env.sh.meta["multicall"]["igual_que_llamadas_sueltas"])

    def test_wrong_chain_is_refused(self):
        env = Env()
        env.chain.chain_id = 1
        with self.assertRaises(RpcError):
            env.sh.setup()

    def test_non_usdc_and_missing_markets_are_excluded(self):
        env = Env()
        env.cfg_markets.append({"id": "0x" + "ee" * 32, "label": "no existe", **prior()})
        other = env.chain.add_market("EUR", loan=fm.WETH)
        env.cfg_markets.append({"id": other, "label": "WETH loan", **prior()})
        env.sh.cfg_markets = env.cfg_markets
        env.open()
        self.assertEqual(list(env.sh.markets), [env.mid])
        self.assertEqual(sorted(env.sh.excluded.values()), ["el préstamo no es USDC", "mercado no existe"])

    def test_reorg_closes_pending_and_resyncs(self):
        env = Env().ready((U[0], 1700))
        n = env.step([("set_price", env.mid, DROP)])
        env.chain.reorg(n)                                                 # el bloque n cambia de hash
        env.step()
        res = env.rows("resultados.jsonl")
        self.assertEqual(res[0]["resultado"], "invalidada_por_reorg")
        self.assertEqual(env.sh.counts["reorgs"], 1)
        self.assertEqual(env.rows("eventos_del_sistema.jsonl")[0]["evento"], "reorg")
        self.assertEqual(len(env.rows("decisiones.jsonl")), 2)             # sigue liquidable: se vuelve a marcar

    def test_reconcile_detects_and_fixes_drift(self):
        env = Env().ready((U[0], 1700))
        env.chain.positions[(env.mid, U[0])][1] -= 10 ** 14                # deuda distinta sin evento
        env.step()
        env.sh.reconcile()
        self.assertEqual(env.sh.counts["deriva_reconciliacion"], 1)
        self.assertEqual(env.rows("eventos_del_sistema.jsonl")[0]["evento"], "deriva_del_libro")
        env.sh.reconcile()
        self.assertEqual(env.sh.counts["deriva_reconciliacion"], 1)       # ya quedó al día

    def test_event_that_would_make_balance_negative_forces_reread(self):
        env = Env().ready((U[0], 1700))
        env.sh.book.pos[(env.mid, U[0])].borrow_shares = 5                 # el libro cree que casi no debe
        env.step([("repay", env.mid, U[0], 10 ** 15)])
        self.assertEqual(env.sh.book.drift, 1)
        self.assertEqual(env.sh.counts["deriva_por_eventos"], 1)
        self.assertEqual(env.sh.book.pos[(env.mid, U[0])].borrow_shares, env.chain.positions[(env.mid, U[0])][1])

    def test_rpc_failure_is_retried_by_the_loop(self):
        env = Env().ready((U[0], 1700))
        n = env.chain.mine([("set_price", env.mid, DROP)])
        env.chain.fail("eth_getBlockByNumber", times=6, message="header not found")
        ts = int(env.chain.headers[n]["timestamp"], 16)
        calls = {"n": 0}

        def head_source(last):
            calls["n"] += 1
            if calls["n"] > 20:
                env.sh.stop = True
                return None, None, None, None
            return env.chain.head, ts + 1.0, 0.0, None
        env.sh.run(5, head_source, no_sleep)
        self.assertEqual(len(env.rows("decisiones.jsonl")), 1)
        self.assertEqual(env.sh.counts["bloques_con_error"], 6)

    def test_run_loop_end_to_end_writes_all_files(self):
        env = Env().ready((U[0], 1700), (U[1], 1000))
        script = [[("set_price", env.mid, DROP)], [], [("liquidate", env.mid, B[0], U[0])], []]
        state = {"i": 0}

        def head_source(last):
            if state["i"] >= len(script):
                env.sh.stop = True
                return None, None, None, None
            n = env.chain.mine(script[state["i"]])
            state["i"] += 1
            ts = int(env.chain.headers[n]["timestamp"], 16)
            return n, ts + 1.1, env.clock.mono(), None
        meta = env.sh.run(5, head_source, no_sleep)
        for name in ("bloques.jsonl", "decisiones.jsonl", "resultados.jsonl", "meta.json", "libro.json"):
            self.assertTrue(os.path.exists(os.path.join(env.out, name)), name)
        self.assertEqual(meta["libro"]["con_deuda"], 2)
        with open(os.path.join(env.out, "meta.json")) as fh:
            m = json.load(fh)
        self.assertEqual(m["contadores"]["bloques"], 4)
        self.assertEqual(m["decisiones"], {"GO:ok": 1})
        self.assertEqual(m["resultados"]["liquidada"], 1)
        self.assertEqual(m["latencia_visto_ms"]["n"], 4)
        self.assertTrue(1000 <= m["latencia_visto_ms"]["p50"] <= 1200)
        self.assertIn("rpc", m)
        bl = env.rows("bloques.jsonl")
        self.assertEqual([b["bloque"] for b in bl], list(range(env.chain.head - 3, env.chain.head + 1)))

    def test_cache_makes_second_bootstrap_incremental(self):
        env = Env().ready((U[0], 1700))
        cache = env.sh.cache_snapshot()
        self.assertEqual(cache["markets"][env.mid]["scanned_to"], env.chain.head)
        self.assertIn(U[0], cache["markets"][env.mid]["candidates"])
        env.chain.mine(env.open_position(U[1], 1000))
        env.chain.calls.clear()
        sh2 = Shadow(env.rpc, tempfile.mkdtemp(), None, markets=env.cfg_markets).setup()
        sh2.bootstrap(env.chain.head, cache)
        self.assertEqual(sh2.book.active_count(), 2)
        self.assertTrue(sh2.meta["libro"]["desde_cache"])
        scans = [c for c in env.chain.calls if c[0] == "eth_getLogs"]
        self.assertEqual(len(scans), 2)                       # solo lo nuevo + una consulta corta para comprobar el bloom

    def test_cache_from_other_morpho_is_ignored(self):
        env = Env().ready((U[0], 1700))
        cache = env.sh.cache_snapshot()
        cache["morpho"] = "0x" + "11" * 20
        sh2 = Shadow(env.rpc, tempfile.mkdtemp(), None, markets=env.cfg_markets).setup()
        sh2.bootstrap(env.chain.head, cache)
        self.assertFalse(sh2.meta["libro"]["desde_cache"])

    def test_catchup_jump_resyncs_book(self):
        env = Env({"max_catchup": 3}).ready((U[0], 1700))
        for _ in range(6):
            env.chain.mine()
        env.chain.mine([("set_price", env.mid, DROP)])
        head = env.chain.head
        ts = int(env.chain.headers[head]["timestamp"], 16)
        state = {"n": 0}

        def head_source(last):
            state["n"] += 1
            if state["n"] > 1:
                env.sh.stop = True
                return None, None, None, None
            return head, ts + 1.0, env.clock.mono(), None
        env.sh.run(5, head_source, no_sleep)
        self.assertEqual(env.sh.counts["saltos"], 1)
        self.assertEqual(env.sh.last_block, head)
        self.assertEqual(len(env.rows("decisiones.jsonl")), 1)             # el libro quedó resincronizado y vio el cruce
        self.assertEqual(env.rows("eventos_del_sistema.jsonl")[0]["evento"], "salto")

    def test_near_threshold_snapshot_is_written(self):
        env = Env({"snapshot_s": 0.0}).ready((U[0], 1710), (U[1], 1000))
        env.step()
        row = env.rows("cercanas.jsonl")[0]
        self.assertEqual(len(row["top"]), 1)                                # solo la que está dentro de la banda
        self.assertEqual(row["top"][0]["prestatario"], U[0])
        self.assertAlmostEqual(row["top"][0]["salud"], 1720 / 1710, places=6)

    def test_run_live_entry_point_with_fake_chain(self):
        env = Env()
        env.chain.mine(env.open_position(U[0], 1700))
        out = tempfile.mkdtemp()
        script = [[("set_price", env.mid, DROP)], [("liquidate", env.mid, B[0], U[0])]]
        state = {"i": 0}

        def head_source(last):
            if state["i"] >= len(script):
                return None, None, None, None
            n = env.chain.mine(script[state["i"]])
            state["i"] += 1
            return n, int(env.chain.headers[n]["timestamp"], 16) + 1.0, time.monotonic(), None
        meta = run_live({"minutos": 0.005}, out, cache_path=None, rpc=env.rpc, markets=env.cfg_markets,
                        head_source=head_source, sleep=no_sleep)
        self.assertEqual(meta["libro"]["con_deuda"], 1)
        with open(os.path.join(out, "meta.json")) as fh:
            self.assertEqual(json.load(fh)["resultados"]["liquidada"], 1)


    def test_on_ready_hook_can_stop_the_loop_and_state_is_still_saved(self):
        env = Env()
        env.chain.mine(env.open_position(U[0], 1700))
        out = tempfile.mkdtemp()
        seen = []

        def on_ready(sh):
            seen.append(sh.book.active_count())
            sh.stop = True                    # como cuando Actions cancela la corrida

        def head_source(last):
            raise AssertionError("no debe vigilar bloques si se pidió parar")
        meta = run_live({"minutos": 5}, out, rpc=env.rpc, markets=env.cfg_markets, head_source=head_source, sleep=no_sleep,
                        on_ready=on_ready)
        self.assertEqual(seen, [1])
        self.assertEqual(meta["libro"]["con_deuda"], 1)
        for name in ("meta.json", "libro.json"):
            self.assertTrue(os.path.exists(os.path.join(out, name)), name)


class TestCatchUp(unittest.TestCase):
    """Tras un atraso (o tras armar el libro) se cubre el hueco con eventos, sin releer todas las posiciones."""

    def position_reads(self, env, since):
        return sum(1 for c in env.chain.calls[since:] if c[0] == "eth_call")

    def test_gap_is_covered_with_events_and_keeps_pending(self):
        env = Env({"max_catchup": 3}).ready((U[0], 1700), (U[1], 1700), (U[2], 1000))
        env.step([("set_price", env.mid, DROP)])                              # U0 y U1 cruzan, se marcan
        self.assertEqual(len(env.rows("decisiones.jsonl")), 2)
        n_cross = env.chain.head
        for _ in range(5):
            env.chain.mine()                                                  # el Shadow "no vio" estos bloques
        n_liq = env.chain.mine([("liquidate", env.mid, B[0], U[0])])
        env.chain.mine([("repay", env.mid, U[2], 10 ** 6)])
        head = env.chain.mine()
        ts = int(env.chain.headers[head]["timestamp"], 16)
        state = {"n": 0}

        def head_source(last):
            state["n"] += 1
            if state["n"] > 1:
                env.sh.stop = True
                return None, None, None, None
            return head, ts + 1.0, env.clock.mono(), None
        calls_before = len(env.chain.calls)
        env.sh.run(5, head_source, no_sleep)
        res = {r["prestatario"]: r for r in env.rows("resultados.jsonl")}
        self.assertEqual(res[U[0]]["resultado"], "liquidada")
        self.assertEqual(res[U[0]]["delta_bloques"], n_liq - n_cross)          # la hora exacta de la liquidación sí se conserva
        self.assertEqual(res[U[0]]["bloque_liquidacion"], n_liq)
        self.assertEqual(res[U[1]]["resultado"], "abierta_al_cierre")          # U1 siguió liquidable: no se dio por "perdida"
        self.assertFalse(res[U[0]]["cruce_incierto"])                         # se vio cruzar bloque a bloque antes del hueco
        self.assertEqual(env.sh.counts["saltos"], 1)
        self.assertEqual(env.sh.counts["bloques_saltados"], head - 1 - n_cross)
        self.assertEqual(env.sh.counts["eventos_en_hueco"], 2)
        self.assertEqual(env.sh.book.pos[(env.mid, U[2])].borrow_shares, env.chain.positions[(env.mid, U[2])][1])
        # Una sola búsqueda de logs para todo el hueco y ninguna relectura de todo el libro.
        gap_logs = [c for c in env.chain.calls[calls_before:] if c[0] == "eth_getLogs"]
        self.assertLessEqual(len(gap_logs), 1 + 1 + 1)                        # hueco + el bloque head por hash (+ posible reintento)
        self.assertLessEqual(self.position_reads(env, calls_before), 8)

    def test_candidates_first_seen_after_a_gap_have_an_uncertain_cross(self):
        env = Env({"max_catchup": 3}).ready((U[0], 1700))
        for _ in range(4):
            env.chain.mine()
        env.chain.mine([("set_price", env.mid, DROP)])                        # cruzó dentro del hueco
        head = env.chain.mine()
        ts = int(env.chain.headers[head]["timestamp"], 16)
        state = {"n": 0}

        def head_source(last):
            state["n"] += 1
            if state["n"] > 1:
                env.sh.stop = True
                return None, None, None, None
            return head, ts + 1.0, env.clock.mono(), None
        env.sh.run(5, head_source, no_sleep)
        dec = env.rows("decisiones.jsonl")
        self.assertEqual(len(dec), 1)
        self.assertTrue(dec[0]["cruce_incierto"])
        self.assertEqual(dec[0]["bloque_cruce"], head)                        # lo único que se sabe: ya era liquidable aquí
        env.step([("set_price", env.mid, fm.PRICE_2000)])
        self.assertTrue(env.rows("resultados.jsonl")[0]["cruce_incierto"])
        env.step([("set_price", env.mid, DROP)])                              # un cruce visto bloque a bloque ya es cierto
        self.assertFalse(env.rows("decisiones.jsonl")[1]["cruce_incierto"])

    def test_positions_already_liquidatable_at_startup_are_uncertain(self):
        env = Env().ready((U[0], 1700))
        env.chain.mine([("set_price", env.mid, DROP)])                        # ya liquidable cuando arranca el libro
        env.sh.bootstrap(env.chain.head)
        env.step()
        dec = env.rows("decisiones.jsonl")
        self.assertEqual(len(dec), 1)
        self.assertTrue(dec[0]["cruce_incierto"])

    def test_huge_gap_falls_back_to_full_reread(self):
        env = Env({"max_catchup": 3, "max_gap_blocks": 4}).ready((U[0], 1700), (U[1], 1000))
        for _ in range(8):
            env.chain.mine()
        env.chain.mine([("set_price", env.mid, DROP)])
        head = env.chain.mine()
        ts = int(env.chain.headers[head]["timestamp"], 16)
        state = {"n": 0}

        def head_source(last):
            state["n"] += 1
            if state["n"] > 1:
                env.sh.stop = True
                return None, None, None, None
            return head, ts + 1.0, env.clock.mono(), None
        env.sh.run(5, head_source, no_sleep)
        self.assertEqual(env.sh.counts["saltos"], 1)
        self.assertEqual(len(env.rows("decisiones.jsonl")), 1)
        self.assertEqual(env.sh.book.active_count(), 2)

    def test_gap_failure_is_retried_without_applying_events_twice(self):
        env = Env({"max_catchup": 3}).ready((U[0], 1700))
        for _ in range(4):
            env.chain.mine()
        env.chain.mine([("repay", env.mid, U[0], 10 ** 6)])
        head = env.chain.mine()
        ts = int(env.chain.headers[head]["timestamp"], 16)
        env.chain.fail("eth_getLogs", times=45, message="boom", when=lambda p: "blockHash" not in p[0])   # agota los reintentos de una búsqueda
        state = {"n": 0}

        def head_source(last):
            state["n"] += 1
            if state["n"] > 6:
                env.sh.stop = True
                return None, None, None, None
            return head, ts + 1.0, env.clock.mono(), None
        env.sh.run(5, head_source, no_sleep)
        self.assertGreaterEqual(env.sh.counts["errores_periodicos"], 1)
        self.assertEqual(env.sh.book.pos[(env.mid, U[0])].borrow_shares, env.chain.positions[(env.mid, U[0])][1])


class TestLostBlocks(unittest.TestCase):
    def test_lost_block_events_are_recovered_later(self):
        env = Env({"retry_blocks": 2}).ready((U[0], 1700), (U[1], 1000))
        env.step([("set_price", env.mid, DROP)])
        n_cross = env.chain.head
        n = env.chain.mine([("liquidate", env.mid, B[0], U[0])])
        ts = int(env.chain.headers[n]["timestamp"], 16)
        env.chain.fail("eth_getBlockByNumber", times=2, message="header not found", when=lambda p: p[0] == hex(n))
        state = {"n": 0}

        def head_source(last):
            state["n"] += 1
            if state["n"] > 12:
                env.sh.stop = True
                return None, None, None, None
            return n, ts + 1.0, env.clock.mono(), None
        env.sh.run(5, head_source, no_sleep)
        self.assertEqual(env.sh.counts["bloques_perdidos"], 1)
        self.assertEqual(env.sh.counts["bloques_recuperados"], 1)
        self.assertEqual(env.sh.lost, {})
        res = [r for r in env.rows("resultados.jsonl") if r.get("prestatario") == U[0]]
        self.assertEqual([r["resultado"] for r in res if "bloque_liquidacion" in r], ["liquidada"])
        self.assertEqual(env.sh.book.pos[(env.mid, U[0])].borrow_shares, env.chain.positions[(env.mid, U[0])][1])
        self.assertEqual(env.sh.counts["saltos"], 0)                           # sin releer todo el libro

    def test_block_that_never_comes_back_is_given_up_with_a_record(self):
        env = Env({"retry_blocks": 1, "lost_retries": 3}).ready((U[0], 1700))
        n = env.chain.mine([("repay", env.mid, U[0], 10 ** 6)])
        ts = int(env.chain.headers[n]["timestamp"], 16)
        env.chain.fail("eth_getBlockByNumber", times=1, message="header not found", when=lambda p: p[0] == hex(n))
        env.chain.fail("eth_getLogs", times=1000, message="boom")
        env.sh.t_lost = -100.0
        state = {"n": 0}

        def head_source(last):
            state["n"] += 1
            if state["n"] > 12:
                env.sh.stop = True
                return None, None, None, None
            env.sh.t_lost = -100.0
            return n, ts + 1.0, env.clock.mono(), None
        env.sh.run(5, head_source, no_sleep)
        self.assertEqual(env.sh.counts["bloques_perdidos_definitivos"], 1)
        self.assertEqual(env.sh.lost, {})
        self.assertIn("bloque_perdido_definitivo", [r["evento"] for r in env.rows("eventos_del_sistema.jsonl")])


class TestEvaluationSpeedup(unittest.TestCase):
    def test_float_prefilter_never_hides_a_liquidatable_or_near_position(self):
        import random
        env = Env().open()
        rnd = random.Random(7)
        sh = env.sh
        state = mo.MarketState(10 ** 14, 10 ** 20, 5 * 10 ** 13, 5 * 10 ** 19, 0, 0)
        price = 2000 * 10 ** 24
        lltv = sh.markets[env.mid].params.lltv
        # posiciones sembradas justo alrededor del umbral (salud entre 0.9999 y 1.03) y otras claramente sanas o rotas
        for i in range(3000):
            collateral = rnd.randint(10 ** 15, 10 ** 21)
            limit_assets = mo.max_borrow(collateral, price, lltv)
            target = limit_assets / rnd.choice([0.9999, 0.99999, 1.0, 1.000001, 1.00001, 1.0001, 1.01, 1.0199, 1.021, 1.5, 3.0])
            shares = max(1, int(target * (state.total_borrow_shares + mo.VIRTUAL_SHARES) / (state.total_borrow_assets + mo.VIRTUAL_ASSETS)))
            sh.book.set_state(env.mid, f"0x{i:040x}", shares, collateral, 1)
        got = sh._evaluate({env.mid: (state, price)}, 1, 0)                   # ts = last_update: sin interés que acumular
        want_liq, want_near = set(), set()
        for (mid, user), p in sh.book.pos.items():
            if p.borrow_shares == 0:
                continue
            borrowed = mo.borrowed_assets(p.borrow_shares, state)
            mb = mo.max_borrow(p.collateral, price, lltv)
            if mb < borrowed:
                want_liq.add((mid, user))
            elif mb / borrowed < 1 + sh.cfg["near_band"]:
                want_near.add((mid, user))
        self.assertGreater(len(want_liq), 100)
        self.assertGreater(len(want_near), 100)
        self.assertEqual({k for k, v in got.items() if not v["accrual"]}, want_liq)
        self.assertEqual(set(sh.last_near), want_near)


# Bloom de un bloque con un log de Liquidate de Morpho en el mercado cbXRP/USDC, calculado con la librería de referencia
# eth-bloom (py-evm): dirección de Morpho + topic0 de Liquidate + id de mercado.
REF_BLOOM = ("000000800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
             "000080000000000000000000000000000000000000100000000000000000000000000000000080000080000000000000"
             "000000000000000000000000000000080000000000000000000000000000000000000000000000080000000000000000"
             "000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000"
             "200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
             "00000000000000000000000000000000")
MORPHO_ADDR = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
CBXRP_ID = "0xd4a903dc6d949519060c7707f9604fdc9772c046e05c2e3a8fce0bd7196e4109"


class TestBloom(unittest.TestCase):
    def three_event_blocks(self):
        env = Env()
        for u in U[:3]:
            env.chain.mine(env.open_position(u, 1700))              # tres bloques con eventos de Morpho, para poder comprobar el bloom
        return env

    def test_bits_match_the_reference_implementation(self):
        morpho = bytes.fromhex(MORPHO_ADDR[2:])
        liq = bytes.fromhex(mo.EVENT_TOPICS["Liquidate"][2:])
        mid = bytes.fromhex(CBXRP_ID[2:])
        self.assertEqual(bloom_bits(morpho), (1492, 963, 509))      # posiciones que da eth-bloom
        self.assertEqual(bloom_bits(liq), (1647, 1335, 2023))
        self.assertEqual(bloom_bits(mid), (1155, 624, 1359))
        raw = bytes.fromhex(REF_BLOOM)
        self.assertEqual(len(raw), 256)
        for item in (morpho, liq, mid):
            self.assertTrue(bloom_has(raw, bloom_bits(item)))
        self.assertFalse(bloom_has(raw, bloom_bits(bytes.fromhex(mo.EVENT_TOPICS["Borrow"][2:]))))

    def test_logbloom_needs_address_event_and_market(self):
        lb = LogBloom(MORPHO_ADDR, mo.BOOK_EVENTS, [CBXRP_ID])
        self.assertTrue(lb.maybe("0x" + REF_BLOOM))
        self.assertFalse(lb.maybe("0x" + "00" * 256))
        other_market = LogBloom(MORPHO_ADDR, mo.BOOK_EVENTS, ["0x" + "ab" * 32])
        self.assertFalse(other_market.maybe("0x" + REF_BLOOM))         # el log es de otro mercado
        other_addr = LogBloom("0x" + "11" * 20, mo.BOOK_EVENTS, [CBXRP_ID])
        self.assertFalse(other_addr.maybe("0x" + REF_BLOOM))
        self.assertTrue(lb.maybe("0x1234"))                            # un bloom raro: ante la duda, se piden los logs
        self.assertTrue(lb.maybe(None))

    def test_fake_chain_bloom_agrees_with_the_package_for_real_logs(self):
        env = self.three_event_blocks()
        lb = LogBloom(env.sh.morpho, mo.BOOK_EVENTS, [env.mid])
        for n in range(env.chain.head - 2, env.chain.head + 1):
            self.assertTrue(lb.maybe(env.chain.headers[n]["logsBloom"]), n)
        empty = env.chain.mine()
        self.assertFalse(lb.maybe(env.chain.headers[empty]["logsBloom"]))

    def test_proved_bloom_skips_get_logs_for_quiet_blocks(self):
        env = self.three_event_blocks()
        env.open()
        self.assertTrue(env.sh.bloom_ok)
        self.assertEqual(env.sh.meta["bloom"]["bloques_con_eventos"], 3)
        env.sh.cfg["bloom_sample"] = 0
        before = len([c for c in env.chain.calls if c[0] == "eth_getLogs"])
        for _ in range(5):
            env.step()
        self.assertEqual(len([c for c in env.chain.calls if c[0] == "eth_getLogs"]), before)       # ninguna consulta de logs
        self.assertEqual(env.sh.counts["bloques_sin_logs_por_bloom"], 5)
        env.step([("set_price", env.mid, DROP)])
        env.step([("liquidate", env.mid, B[0], U[0])])                                              # un bloque con evento sí se consulta
        self.assertEqual([r["resultado"] for r in env.rows("resultados.jsonl")], ["liquidada"])
        self.assertGreater(len([c for c in env.chain.calls if c[0] == "eth_getLogs"]), before)

    def test_blocks_with_events_for_other_markets_are_skipped_too(self):
        env = self.three_event_blocks()
        other = env.chain.add_market("OTRO")
        env.open()
        env.sh.cfg["bloom_sample"] = 0
        n_before = env.sh.counts["bloques_sin_logs_por_bloom"]
        env.step(env.open_position(U[3], 500, mid=other))                                          # evento de un mercado que no vigilamos
        self.assertEqual(env.sh.counts["bloques_sin_logs_por_bloom"], n_before + 1)

    def test_control_sample_detects_a_bloom_that_lies_and_turns_it_off(self):
        env = self.three_event_blocks()
        env.open()
        env.sh.cfg["bloom_sample"] = 1                                                             # se revisa cada bloque
        n = env.chain.mine(env.open_position(U[3], 800))
        env.chain.headers[n] = dict(env.chain.headers[n], logsBloom="0x" + "00" * 256)             # el bloom miente
        env.sh.process_block(n, None, None, None)
        self.assertFalse(env.sh.bloom_ok)
        self.assertEqual(env.sh.counts["bloom_falsos_negativos"], 1)
        self.assertEqual(env.sh.book.pos[(env.mid, U[3])].borrow_shares, env.chain.positions[(env.mid, U[3])][1])    # el evento sí se aplicó
        self.assertIn("bloom_falso_negativo", [r["evento"] for r in env.rows("eventos_del_sistema.jsonl")])
        before = len([c for c in env.chain.calls if c[0] == "eth_getLogs"])
        env.step()
        self.assertEqual(len([c for c in env.chain.calls if c[0] == "eth_getLogs"]), before + 1)     # ya se piden los logs de todos

    def test_a_bloom_that_does_not_match_real_blocks_is_not_trusted(self):
        env = self.three_event_blocks()
        for n in range(env.chain.head - 2, env.chain.head + 1):
            env.chain.headers[n] = dict(env.chain.headers[n], logsBloom="0x" + "00" * 256)
        env.open()
        self.assertFalse(env.sh.bloom_ok)
        self.assertFalse(env.sh.meta["bloom"]["ok"])
        before = len([c for c in env.chain.calls if c[0] == "eth_getLogs"])
        env.step()
        self.assertEqual(len([c for c in env.chain.calls if c[0] == "eth_getLogs"]), before + 1)

    def test_too_few_event_blocks_to_prove_it_means_not_trusted(self):
        env = Env().ready((U[0], 1700))                                                            # un solo bloque con eventos
        self.assertFalse(env.sh.bloom_ok)
        self.assertEqual(env.sh.meta["bloom"]["bloques_con_eventos"], 1)


class TestRateCache(unittest.TestCase):
    RATE = int(0.4 / 31_536_000 * 1e18)

    def count_irm(self, env):
        """Cuenta las llamadas que llegan al IRM del mercado."""
        irm = env.sh.markets[env.mid].params.irm.lower()
        count = {"n": 0}
        orig = env.rpc.transport

        def counting(url, payload, timeout):
            if payload["method"] == "eth_call" and payload["params"][0].get("to", "").lower() == irm:
                count["n"] += 1
            return orig(url, payload, timeout)
        env.rpc.transport = counting
        return count

    def test_irm_rate_is_reused_while_the_market_does_not_change(self):
        env = Env(rate=self.RATE).ready((U[0], 1715))                         # a menos de 0.5% del umbral: cada bloque necesita el interés
        for _ in range(3):
            env.chain.mine()                                                  # pasan >5 s desde la última interacción con el mercado
        count = self.count_irm(env)
        for _ in range(8):
            env.step()
        self.assertEqual(count["n"], 1)                                       # una vez, no ocho

    def test_rate_is_requeried_when_the_market_changes(self):
        env = Env(rate=self.RATE).ready((U[0], 1715), (U[1], 1000))
        for _ in range(3):
            env.chain.mine()
        count = self.count_irm(env)
        for _ in range(3):
            env.step()
        before = count["n"]
        self.assertEqual(before, 1)
        env.step([("borrow", env.mid, U[1], 10 ** 6)])                        # cambia la deuda total: cambia la utilización
        for _ in range(4):
            env.step()                                                        # y pasan >5 s sin tocar el mercado otra vez
        self.assertEqual(count["n"], before + 1)

    def test_rate_is_requeried_after_the_ttl(self):
        env = Env({"rate_ttl_s": 0.0}, rate=self.RATE).ready((U[0], 1715))
        for _ in range(3):
            env.chain.mine()
        count = self.count_irm(env)
        for _ in range(4):
            env.step()
        self.assertEqual(count["n"], 4)

    def test_interest_still_flips_a_position_with_a_cached_rate(self):
        env = Env(rate=int(2.0 / 31_536_000 * 1e18)).ready((U[0], 1719))
        for _ in range(3):
            env.step()
        self.assertEqual(env.rows("decisiones.jsonl"), [])
        env.step(dt=40_000_000)                                               # mucho tiempo sin tocar el mercado: el interés la cruza
        self.assertEqual(len(env.rows("decisiones.jsonl")), 1)
        self.assertTrue(env.rows("decisiones.jsonl")[0]["con_interes"])


class TestParallelReads(unittest.TestCase):
    def test_parallel_position_reads_match_single_reads(self):
        env = Env().ready((U[0], 1700), (U[1], 1000), (U[2], 500), (U[3], 800))
        keys = [(env.mid, u) for u in U[:4]] * 3
        env.sh.cfg["read_batch"] = 2
        env.sh.cfg["read_workers"] = 4
        par = env.sh.read_positions(keys, env.chain.head)
        env.sh.cfg["read_workers"] = 1
        seq = env.sh.read_positions(keys, env.chain.head)
        self.assertEqual(par, seq)
        self.assertEqual(len(par), 4)

    def test_snapshot_runs_alongside_header_and_logs_and_errors_surface(self):
        env = Env().ready((U[0], 1700))
        env.chain.fail("eth_call", times=1000, message="boom", when=lambda p: p[1] != "latest")
        env.chain.mine()
        n = env.chain.head
        env.sh.cfg["retry_blocks"] = 99
        with self.assertRaises(RpcError):
            env.sh.process_block(n, None, None, None)


class TestLaggingProvider(unittest.TestCase):
    """Un respaldo atrasado detrás de un balanceador contesta `[]` a getLogs por número: así se pierde un evento sin error."""

    def make(self):
        env = Env().ready((U[0], 1700))
        chain = env.chain

        def transport(url, payload, timeout):
            if url == "https://lagging" and payload["method"] == "eth_getLogs":
                flt = payload["params"][0]
                if "blockHash" in flt:
                    return {"jsonrpc": "2.0", "id": payload["id"], "error": {"code": -32000, "message": "unknown block"}}
                return {"jsonrpc": "2.0", "id": payload["id"], "result": []}      # el bloque aún no está en ese respaldo
            return chain(url, payload, timeout)
        env.rpc = Rpc(["https://lagging", "https://good"], transport=transport, sleep=no_sleep, rps=0, expected_chain_id=8453)
        env.sh.rpc = env.rpc
        return env

    def test_logs_by_hash_never_return_a_silent_empty_list(self):
        env = self.make()
        env.chain.mine([("set_price", env.mid, DROP)])
        n = env.chain.mine([("liquidate", env.mid, B[0], U[0])])
        ts = int(env.chain.headers[n]["timestamp"], 16)
        env.sh.process_block(n - 1, ts, env.clock.mono(), "https://lagging")
        env.sh.process_block(n, ts + 1.0, env.clock.mono(), "https://lagging")      # se prefiere al proveedor atrasado
        res = env.rows("resultados.jsonl")
        self.assertEqual([r["resultado"] for r in res], ["liquidada"])               # el evento no se perdió
        self.assertEqual(env.sh.counts["logs_por_hash_fallidos"], 0)

    def test_falls_back_to_block_number_when_no_provider_serves_block_hash(self):
        env = Env().ready((U[0], 1700))
        env.chain.fail("eth_getLogs", times=3, message="invalid argument 0: blockHash not supported",
                       when=lambda p: "blockHash" in p[0])
        env.step([("set_price", env.mid, DROP)])
        self.assertEqual(len(env.rows("decisiones.jsonl")), 1)                       # igual se vio el cruce
        self.assertGreaterEqual(env.sh.counts["logs_por_hash_fallidos"], 1)


    def test_hash_filter_is_dropped_after_three_failures_in_a_row(self):
        env = Env().ready((U[0], 1700))
        env.chain.fail("eth_getLogs", times=10_000, message="invalid argument 0: unknown field blockHash",
                       when=lambda p: "blockHash" in p[0])
        for _ in range(8):
            env.step()
        hash_calls = [c for c in env.chain.calls if c[0] == "eth_getLogs"]
        self.assertFalse(env.sh.logs_by_hash)
        self.assertEqual(env.sh.counts["logs_por_hash_fallidos"], 3)
        self.assertIn("desactivado", env.sh.meta["logs_por_hash"])
        before = len(env.chain.calls)
        env.step()
        new = env.chain.calls[before:]
        self.assertEqual(sum(1 for c in new if c[0] == "eth_getLogs"), 1)        # una sola llamada por número, sin intento por hash
        self.assertTrue(hash_calls)

    def test_a_success_resets_the_failure_streak(self):
        env = Env().ready((U[0], 1700))
        env.chain.fail("eth_getLogs", times=2, message="boom", when=lambda p: "blockHash" in p[0])
        for _ in range(3):
            env.step()
        env.chain.fail("eth_getLogs", times=2, message="boom", when=lambda p: "blockHash" in p[0])
        for _ in range(3):
            env.step()
        self.assertTrue(env.sh.logs_by_hash)


class TestHeadWatcher(unittest.TestCase):
    def test_reports_first_sight_of_new_head(self):
        chain = fm.FakeMorpho()
        rpc = Rpc(["https://a", "https://b"], transport=chain, sleep=no_sleep, rps=0)
        w = HeadWatcher(rpc, rpc.urls, interval=0.01).start()
        try:
            head, wall, mono, url = w.wait(0, timeout=2)
            self.assertEqual(head, chain.head)
            threading.Timer(0.05, chain.mine).start()
            head2, wall2, mono2, url2 = w.wait(head, timeout=3)
            self.assertEqual(head2, head + 1)
            self.assertIn(url2, rpc.urls)
            self.assertGreaterEqual(wall2, wall)
            self.assertEqual(w.wait(head2, timeout=0.05), (None, None, None, None))
        finally:
            w.stop()


    def test_first_sight_is_stamped_when_the_answer_arrives_not_when_it_was_asked(self):
        chain = fm.FakeMorpho()
        clock = {"t": 1000.0}

        def slow(url, payload, timeout):
            clock["t"] += 0.3                                  # lo que tarda la respuesta
            return chain(url, payload, timeout)
        rpc = Rpc(["https://a"], transport=slow, sleep=no_sleep, rps=0)
        w = HeadWatcher(rpc, rpc.urls, interval=3600, wall=lambda: clock["t"], mono=lambda: clock["t"])
        t = threading.Thread(target=w._loop, args=(rpc.urls[0],), daemon=True)
        t.start()
        head, wall, mono, url = w.wait(0, timeout=2)
        w.stop()
        self.assertEqual(head, chain.head)
        self.assertAlmostEqual(wall, 1000.3, places=6)        # no 1000.0


if __name__ == "__main__":
    unittest.main()
