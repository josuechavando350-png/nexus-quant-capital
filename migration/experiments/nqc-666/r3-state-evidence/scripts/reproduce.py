"""Offline reproduction using already installed dependencies, Rust and solc."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--solc", type=Path, required=True)
    a = parser.parse_args()
    a.out = a.out.resolve()
    assert not a.out.is_relative_to(REPO)
    a.out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE="1", CARGO_TARGET_DIR=str(a.out / "target"), RUSTFLAGS="")
    r1 = ROOT.parent / "r1-morpho"
    def run(label, args, cwd=ROOT):
        with (a.out / (label + ".log")).open("w") as log:
            subprocess.run(list(map(str, args)), cwd=cwd, env=env, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
        print(label + " passed", flush=True)
    run("rust-build", ["cargo", "build", "--release", "--locked", "--offline", "--bin", "eval"], r1)
    run("rust-r1-tests", ["cargo", "test", "--locked", "--offline"], r1)
    run("rust-base-tests", ["cargo", "test", "--locked", "--offline"], ROOT.parent)
    run("isolation", [sys.executable, "migration/verify_isolation.py"], REPO)
    run("isolation-tests", [sys.executable, "-m", "unittest", "discover", "-s", "migration", "-p", "test_isolation.py"], REPO)
    run("fixtures", [sys.executable, "scripts/fixtures.py", a.out / "fixtures"])
    for path in (a.out / "fixtures").glob("*.json"):
        assert path.read_bytes() == (ROOT / "fixtures" / path.name).read_bytes(), path.name
    env["NQC_R1_EVAL"] = str(a.out / "target/release/eval")
    run("python-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run("slot-parity", [sys.executable, "scripts/slot_parity.py", "--solc", a.solc, "--out", a.out / "slots"])
    run("benchmark", [sys.executable, "scripts/benchmark.py", "--out", a.out / "benchmark", "--eval", env["NQC_R1_EVAL"]])
    versions = subprocess.check_output(["rustc", "-vV"], text=True, env=env)
    (a.out / "build-metadata.json").write_text(json.dumps({"rustc": versions,
        "rust_profile": "R1 unchanged: O3, fat LTO, codegen-units=1, overflow-checks=true, RUSTFLAGS empty",
        "solc_sha256": hashlib.sha256(a.solc.read_bytes()).hexdigest(),
        "network": "none", "all_commands_completed": True}, indent=2) + "\n")


if __name__ == "__main__":
    main()
