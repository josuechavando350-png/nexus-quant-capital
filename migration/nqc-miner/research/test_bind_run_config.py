import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "bind_run_config.py"
SPEC = importlib.util.spec_from_file_location("bind_run_config", MODULE)
bind_run_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bind_run_config)


def template():
    return {
        "schema_version": 2,
        "namespace": "nqc_miner_v1",
        "producer": "nqc-miner",
        "run_id": "fixture-bind",
        "data_class": "historical",
        "code_commit": "__FROM_ABOUT__",
        "cargo_lock_sha256": "__FROM_ABOUT__",
        "build_identity_sha256": "__FROM_ABOUT__",
        "observer_bridge_enabled": False,
        "signing_enabled": False,
        "gas_budget_mxn_centavos": 0,
        "scopes": [],
    }


def about():
    value = {
        "name": "nqc-miner",
        "namespace": "nqc_miner_v1",
        "source_dirty": False,
        "observer_bridge_enabled": False,
        "signing_enabled": False,
        "gas_budget_mxn_centavos": 0,
        "economic_certification": False,
        "code_commit": "a" * 40,
        "cargo_lock_sha256": "b" * 64,
        "source_sha256": "e" * 64,
        "rustc_version": "rustc 1.90.0 fixture",
        "target": "x86_64-unknown-linux-gnu",
        "host": "x86_64-unknown-linux-gnu",
        "profile": "debug",
        "opt_level": "0",
        "debug": True,
        "rustflags_sha256": "c" * 64,
    }
    value["build_identity_sha256"] = bind_run_config.compute_build_identity(value)
    return value


class BindRunConfigTests(unittest.TestCase):
    def test_binds_exact_clean_binary_identity(self):
        value = bind_run_config.bind(template(), about())
        self.assertEqual(value["code_commit"], "a" * 40)
        self.assertEqual(value["cargo_lock_sha256"], "b" * 64)
        self.assertEqual(value["build_identity_sha256"], about()["build_identity_sha256"])

    def test_dirty_or_operational_about_is_rejected(self):
        for key, value in [
            ("source_dirty", True),
            ("observer_bridge_enabled", True),
            ("signing_enabled", True),
            ("gas_budget_mxn_centavos", 1),
            ("economic_certification", True),
        ]:
            candidate = about()
            candidate[key] = value
            with self.subTest(key=key):
                with self.assertRaises(bind_run_config.BindError):
                    bind_run_config.bind(template(), candidate)

    def test_missing_compiler_identity_is_rejected(self):
        for key, value in [
            ("rustc_version", ""),
            ("target", ""),
            ("host", ""),
            ("profile", ""),
            ("opt_level", ""),
            ("debug", "true"),
            ("source_sha256", "not-a-hash"),
            ("rustflags_sha256", "not-a-hash"),
            ("build_identity_sha256", "not-a-hash"),
        ]:
            candidate = about()
            candidate[key] = value
            with self.subTest(key=key):
                with self.assertRaises(bind_run_config.BindError):
                    bind_run_config.bind(template(), candidate)

    def test_build_identity_must_match_compiler_and_source_fields(self):
        for key, value in [
            ("code_commit", "f" * 40),
            ("source_sha256", "f" * 64),
            ("cargo_lock_sha256", "f" * 64),
            ("rustc_version", "rustc 9.99.0 forged"),
            ("target", "forged-target"),
            ("rustflags_sha256", "f" * 64),
        ]:
            candidate = about()
            candidate[key] = value
            with self.subTest(key=key):
                with self.assertRaises(bind_run_config.BindError):
                    bind_run_config.bind(template(), candidate)

    def test_template_cannot_pin_stale_identity(self):
        candidate = template()
        candidate["code_commit"] = "c" * 40
        with self.assertRaises(bind_run_config.BindError):
            bind_run_config.bind(candidate, about())

    def test_foreign_template_is_rejected(self):
        candidate = template()
        candidate["namespace"] = "observer"
        with self.assertRaises(bind_run_config.BindError):
            bind_run_config.bind(candidate, about())

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(bind_run_config.BindError):
                bind_run_config.load_json_strict(path)

    def test_output_is_create_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("sentinel", encoding="utf-8")
            with self.assertRaises(bind_run_config.BindError):
                bind_run_config.write_new_atomic(path, template())
            self.assertEqual(path.read_text(encoding="utf-8"), "sentinel")


if __name__ == "__main__":
    unittest.main()
