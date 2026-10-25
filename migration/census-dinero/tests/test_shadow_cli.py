"""Comandos del Shadow en la CLI: planificación del workflow, configuración y reporte."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from census_dinero.__main__ import main, shadow_settings  # noqa: E402
from test_shadow_replay import replay, scenario  # noqa: E402


def run_main(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(list(argv))
    return code, buf.getvalue()


def write_json(obj):
    path = os.path.join(tempfile.mkdtemp(), "run.json")
    with open(path, "w") as fh:
        json.dump(obj, fh)
    return path


def parse(out):
    return dict(line.split("=", 1) for line in out.strip().splitlines())


class TestSettings(unittest.TestCase):
    def test_defaults(self):
        live, rep, live_on, rep_on = shadow_settings({"modo": "shadow"})
        self.assertEqual(live, {"minutos": 90.0})
        self.assertEqual(rep, {})
        self.assertTrue(live_on and rep_on)

    def test_overrides_and_switches(self):
        cfg = {"shadow": {"minutos": 45, "vivo": False, "replay": {"dias": 7, "max": 50}, "config": {"min_bonus_usd": 20}}}
        live, rep, live_on, rep_on = shadow_settings(cfg)
        self.assertEqual(live, {"min_bonus_usd": 20, "minutos": 45.0})
        self.assertEqual(rep, {"min_bonus_usd": 20, "dias": 7, "max": 50})
        self.assertFalse(live_on)
        self.assertTrue(rep_on)
        self.assertFalse(shadow_settings({"shadow": {"replay": False}})[3])

    def test_live_window_is_capped_below_the_job_limit(self):
        self.assertEqual(shadow_settings({"shadow": {"minutos": 9999}})[0]["minutos"], 330.0)


class TestPlan(unittest.TestCase):
    def test_shadow_mode_has_no_census_tranches(self):
        code, out = run_main("plan", "--run-json", write_json({"modo": "shadow", "shadow": {"minutos": 60}}))
        p = parse(out)
        self.assertEqual(code, 0)
        self.assertEqual((p["modo"], p["fuente"], p["vivo"], p["replay"]), ("shadow", "", "true", "true"))
        self.assertEqual(json.loads(p["matrix"])["include"][0]["label"], "sin-recoleccion")

    def test_shadow_can_run_only_one_of_the_two(self):
        p = parse(run_main("plan", "--run-json", write_json({"modo": "shadow", "shadow": {"vivo": False}}))[1])
        self.assertEqual((p["vivo"], p["replay"]), ("false", "true"))
        p = parse(run_main("plan", "--run-json", write_json({"modo": "shadow", "shadow": {"replay": False}}))[1])
        self.assertEqual((p["vivo"], p["replay"]), ("true", "false"))

    def test_shadow_report_mode_only_rebuilds_from_an_earlier_run(self):
        p = parse(run_main("plan", "--run-json", write_json({"modo": "shadow_reporte", "corrida": 123}))[1])
        self.assertEqual((p["modo"], p["fuente"], p["vivo"], p["replay"]), ("shadow_reporte", "123", "false", "false"))

    def test_shadow_report_mode_can_take_replay_and_lupa_from_other_runs(self):
        p = parse(run_main("plan", "--run-json", write_json({"modo": "shadow_reporte", "corrida": 123,
                                                              "corrida_replay": 456, "corrida_lupa": "789"}))[1])
        self.assertEqual((p["fuente"], p["fuente_replay"], p["fuente_lupa"]), ("123", "456", "789"))
        p = parse(run_main("plan", "--run-json", write_json({"modo": "shadow_reporte", "corrida": 123}))[1])
        self.assertEqual((p["fuente_replay"], p["fuente_lupa"]), ("", ""))             # por omisión, todo de la misma corrida
        p = parse(run_main("plan", "--run-json", write_json({"modo": "shadow", "corrida_replay": 456}))[1])
        self.assertEqual((p["fuente_replay"], p["fuente_lupa"]), ("", ""))             # fuera de shadow_reporte no se usan

    def test_a_source_run_id_must_be_a_number(self):
        # el id acaba en una ruta del workflow: que no sea un número es un error, no una ruta
        with self.assertRaises(ValueError):
            run_main("plan", "--run-json", write_json({"modo": "shadow_reporte", "corrida": 1, "corrida_replay": "../x"}))

    def test_census_modes_are_untouched(self):
        p = parse(run_main("plan", "--run-json", write_json({"modo": "reporte", "corrida": 5}))[1])
        self.assertEqual((p["modo"], p["fuente"]), ("reporte", "5"))
        out = run_main("plan", "--run-json", write_json({"days": 1, "chains": ["base"], "end_utc": "2026-10-24T20:00:00Z"}))[1]
        self.assertIn("modo=recolectar", out)


class TestShadowReportCommand(unittest.TestCase):
    def test_writes_markdown_and_json_from_two_run_folders(self):
        env, _, _ = scenario()
        env.sh.finish()
        _, _, rdir = replay(env, min_bonus_usd=1)
        out = tempfile.mkdtemp()
        run_json = write_json({"modo": "shadow", "shadow": {"config": {"min_bonus_usd": 1, "min_net_usd": 0}}})
        code, text = run_main("shadow-report", "--live", env.out, "--replay", rdir, "--run-json", run_json, "--out", out)
        self.assertEqual(code, 0)
        self.assertIn("## Respuesta corta", text)
        with open(os.path.join(out, "shadow.json")) as fh:
            data = json.load(fh)
        self.assertEqual(data["config"]["min_bonus_usd"], 1)
        self.assertEqual(data["replay"]["ganables"]["elegibles"], 2)
        self.assertTrue(os.path.exists(os.path.join(out, "RESUMEN_SHADOW.md")))

    def test_works_with_only_one_side(self):
        env, _, _ = scenario()
        env.sh.finish()
        out = tempfile.mkdtemp()
        code, text = run_main("shadow-report", "--live", env.out, "--out", out)
        self.assertEqual(code, 0)
        self.assertIn("Sin datos del replay", text)
        self.assertIn("este reporte no incluye un replay", text)           # y las puertas lo dicen, sin culpar al replay

    def test_the_oracle_lupa_can_come_from_another_run_folder(self):
        env, _, _ = scenario()
        env.sh.finish()
        _, _, rdir = replay(env, min_bonus_usd=1)                              # filas del replay, sin lupa
        _, _, ldir = replay(env, min_bonus_usd=0.1, diag=5)                    # otra corrida: con lupa
        self.assertFalse(os.path.exists(os.path.join(rdir, "diag.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(ldir, "diag.jsonl")))
        run_json = write_json({"modo": "shadow", "shadow": {"config": {"min_bonus_usd": 1, "min_net_usd": 0}}})
        out = tempfile.mkdtemp()
        run_main("shadow-report", "--live", env.out, "--replay", rdir, "--run-json", run_json, "--out", out)
        with open(os.path.join(out, "shadow.json")) as fh:
            self.assertIsNone(json.load(fh)["diagnostico"])
        out = tempfile.mkdtemp()
        code, text = run_main("shadow-report", "--live", env.out, "--replay", rdir, "--diag", ldir,
                              "--run-json", run_json, "--out", out)
        self.assertEqual(code, 0)
        with open(os.path.join(out, "shadow.json")) as fh:
            data = json.load(fh)
        self.assertEqual(data["replay"]["ganables"]["elegibles"], 2)           # las filas siguen siendo las del replay
        self.assertGreaterEqual(data["diagnostico"]["n"], 1)                   # y la lupa viene de la otra carpeta
        self.assertEqual(data["fuentes"]["lupa"]["filas"], data["diagnostico"]["n"] + data["diagnostico"]["errores"])
        self.assertIn("Diagnóstico del oráculo", text)


class TestReadOnlyGuard(unittest.TestCase):
    """Ningún módulo del Shadow puede contener una forma de enviar o firmar transacciones."""

    FORBIDDEN = ("eth_sendRawTransaction", "eth_sendTransaction", "eth_sign", "eth_signTransaction", "personal_", "eth_accounts",
                 "send_raw_transaction", "sendBundle", "eth_sendBundle", "private_key", "privateKey", "PRIVATE_KEY", "mnemonic")

    def test_shadow_sources_have_no_signing_or_sending(self):
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "census_dinero")
        for name in ("shadow_live.py", "shadow_replay.py", "shadow_report.py", "morpho.py", "flash_watch.py", "flash_eval.py",
                     "flash_stream.py", "flash_fast.py", "ws.py", "orden.py", "flash_probe.py"):
            with open(os.path.join(base, name), encoding="utf-8") as fh:
                src = fh.read()
            for word in self.FORBIDDEN:
                if name == "shadow_report.py" and word in ("eth_sign", "eth_signTransaction", "personal_", "eth_accounts", "eth_sendRawTransaction",
                                                           "eth_sendTransaction", "eth_sendBundle"):
                    continue          # el reporte los nombra solo para marcarlos como peligrosos
                self.assertNotIn(word, src, f"{name} menciona {word}")

    def test_the_rpc_client_only_issues_methods_the_report_calls_read_only(self):
        from census_dinero import shadow_report as sr
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "census_dinero")
        used = set()
        import re
        for name in ("shadow_live.py", "shadow_replay.py", "rpc.py", "sonda.py", "ws.py", "flash_stream.py", "flash_fast.py", "flash_watch.py"):
            with open(os.path.join(base, name), encoding="utf-8") as fh:
                used |= set(re.findall(r'"((?:eth|net|web3|debug|trace|personal|txpool|admin|miner)_[A-Za-z_]+)"', fh.read()))
        extra = {m for m in used if m not in sr.READ_ONLY}
        # La sonda del census puede usar métodos de traza (lectura); los de envío nunca.
        self.assertFalse({m for m in extra if m.startswith(sr.DANGEROUS_PREFIXES)}, extra)


if __name__ == "__main__":
    unittest.main()
