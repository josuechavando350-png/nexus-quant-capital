"""Build and validate offline. Uses installed R3 Python environment and Rust only."""
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
    p = argparse.ArgumentParser(); p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(); a.out = a.out.resolve()
    assert not a.out.is_relative_to(REPO)
    a.out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE="1", RUSTFLAGS="", CARGO_TARGET_DIR=str(a.out / "target"))
    def run(label, command, cwd=ROOT):
        with (a.out / (label + ".log")).open("w") as f:
            subprocess.run(list(map(str, command)), cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, check=True)
        print(label + " passed", flush=True)
    run("fmt", ["cargo", "fmt", "--", "--check"])
    run("clippy", ["cargo", "clippy", "--all-targets", "--locked", "--offline", "--", "-D", "warnings"])
    run("rust-tests", ["cargo", "test", "--locked", "--offline"])
    run("native-build", ["cargo", "build", "--release", "--locked", "--offline"])
    r1 = ROOT.parent / "r1-morpho"
    run("r1-build", ["cargo", "build", "--release", "--bin", "eval", "--locked", "--offline"], r1)
    run("r1-tests", ["cargo", "test", "--locked", "--offline"], r1)
    run("base-tests", ["cargo", "test", "--locked", "--offline"], ROOT.parent)
    lib = a.out / "target/release/libnqc_666_stable_ingress.so"
    binary = a.out / "target/release/eval"
    env.update(NQC_NATIVE_LIB=str(lib), NQC_R1_EVAL=str(binary))
    run("python-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run("r3-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], ROOT.parent / "r3-state-evidence")
    run("reproduce-failures", [sys.executable, "scripts/reproduce_failures.py", "--out", a.out / "failures"])
    run("differential", [sys.executable, "scripts/differential.py", "--library", lib,
                         "--eval", binary, "--out", a.out / "differential"])
    run("isolation", [sys.executable, "migration/verify_isolation.py"], REPO)
    run("isolation-tests", [sys.executable, "-m", "unittest", "discover", "-s", "migration", "-p", "test_isolation.py"], REPO)
    run("benchmark", [sys.executable, "scripts/benchmark.py", "--library", lib,
                       "--eval", binary, "--out", a.out / "benchmark"])
    run("disassembly", ["objdump", "-d", lib])
    (a.out / "build-metadata.json").write_text(json.dumps({
        "rustc": subprocess.check_output(["rustc", "-vV"], text=True, env=env),
        "native_profile": "O3, fat LTO, codegen-units=1, overflow-checks=true, panic=abort, RUSTFLAGS empty",
        "native_sha256": hashlib.sha256(lib.read_bytes()).hexdigest(),
        "eval_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "all_commands_completed": True, "network_during_reproduction": "none",
    }, indent=2) + "\n")


if __name__ == "__main__": main()
