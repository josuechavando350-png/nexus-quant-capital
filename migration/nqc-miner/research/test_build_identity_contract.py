import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "verify_offline.py"
SPEC = importlib.util.spec_from_file_location("verify_offline", MODULE)
verify_offline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_offline)


class BuildIdentityContractTests(unittest.TestCase):
    def test_rust_source_digest_changes_when_toolchain_pin_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            for name, content in {
                "Cargo.toml": "[package]\nname='fixture'\n",
                "Cargo.lock": "version = 4\n",
                "build.rs": "fn main() {}\n",
                "rust-toolchain.toml": "[toolchain]\nchannel='1.90.0'\n",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            (root / "src" / "lib.rs").write_text("pub fn fixture() {}\n", encoding="utf-8")
            before = verify_offline.rust_source_sha256(root)
            (root / "rust-toolchain.toml").write_text(
                "[toolchain]\nchannel='1.91.0'\n", encoding="utf-8"
            )
            after = verify_offline.rust_source_sha256(root)
            self.assertNotEqual(before, after)

    def test_build_script_tracks_toolchain_in_dirty_hash_and_rerun_contract(self):
        build = (Path(__file__).resolve().parents[1] / "build.rs").read_text(encoding="utf-8")
        self.assertGreaterEqual(build.count('"rust-toolchain.toml"'), 2)
        self.assertIn("cargo:rerun-if-changed=rust-toolchain.toml", build)
        for field in [
            "NQC_MINER_BUILD_RUSTC_VERSION",
            "NQC_MINER_BUILD_TARGET",
            "NQC_MINER_BUILD_HOST",
            "NQC_MINER_BUILD_PROFILE",
            "NQC_MINER_BUILD_OPT_LEVEL",
            "NQC_MINER_BUILD_DEBUG",
            "NQC_MINER_BUILD_RUSTFLAGS_SHA256",
        ]:
            self.assertIn(field, build)


if __name__ == "__main__":
    unittest.main()
