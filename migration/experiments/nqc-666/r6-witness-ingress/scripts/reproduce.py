"""Offline R6 validation, rebuilding unchanged R4/R1 binaries in a fresh directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[3]
R4 = ROOT.parent / "r4-stable-ingress"
R1 = ROOT.parent / "r1-morpho"


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
    run("native-build", ["cargo", "build", "--release", "--locked", "--offline"], R4)
    run("r1-build", ["cargo", "build", "--release", "--bin", "eval", "--locked", "--offline"], R1)
    run("r4-rust-tests", ["cargo", "test", "--locked", "--offline"], R4)
    run("r1-rust-tests", ["cargo", "test", "--locked", "--offline"], R1)
    lib = a.out / "target/release/libnqc_666_stable_ingress.so"
    binary = a.out / "target/release/eval"
    env.update(NQC_NATIVE_LIB=str(lib), NQC_R1_EVAL=str(binary))
    run("python-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run("r5-regression", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], ROOT.parent / "r5-proof-traversal")
    run("isolation", [sys.executable, "migration/verify_isolation.py"], REPO)
    run("isolation-tests", [sys.executable, "-m", "unittest", "discover", "-s", "migration", "-p", "test_isolation.py"], REPO)
    library_sha = hashlib.sha256(lib.read_bytes()).hexdigest()
    run("benchmark", [sys.executable, "scripts/benchmark.py", "--library", lib,
                       "--library-sha256", library_sha, "--out", a.out / "benchmark"])
    run("verify-results", [sys.executable, "scripts/verify_results.py", a.out / "benchmark"])
    (a.out / "build-metadata.json").write_text(json.dumps({
        "rustc": subprocess.check_output(["rustc", "-vV"], text=True, env=env),
        "profile": "unchanged R4: O3, fat LTO, codegen-units=1, overflow-checks=true, panic=abort",
        "native_sha256": library_sha, "eval_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "network": "none", "all_commands_completed": True,
    }, indent=2) + "\n")


if __name__ == "__main__": main()
