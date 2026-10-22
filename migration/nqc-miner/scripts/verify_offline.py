#!/usr/bin/env python3
"""Run the isolated offline checks and retain exact logs in a new directory.

This verifies software behavior. It does not certify economic performance, source
authenticity, a deployment, or any authority to operate funds/the observer.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest(module: Path) -> dict[str, str]:
    files = [module / name for name in ("Cargo.toml", "Cargo.lock", "build.rs", "rust-toolchain.toml")]
    for name in ("src", "tests", "research", "infra", "scripts", "schemas", "fixtures"):
        files.extend(path for path in (module / name).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    if any(path.is_symlink() for path in files):
        raise ValueError("symlink in audited inputs")
    return {str(path.relative_to(module)): sha(path.read_bytes()) for path in sorted(files)}


def rust_source_sha256(module: Path) -> str:
    files = [module / name for name in ("Cargo.toml", "Cargo.lock", "build.rs", "rust-toolchain.toml")]
    files.extend((module / "src").rglob("*.rs"))
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(str(path.relative_to(module)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_identity_sha256(identity: dict) -> str:
    required = (
        "code_commit", "source_sha256", "cargo_lock_sha256", "rustc_version",
        "target", "host", "profile", "opt_level", "debug", "rustflags_sha256",
    )
    if any(key not in identity for key in required) or not isinstance(identity["debug"], bool):
        raise ValueError("incomplete build identity")
    fields = [
        ("commit", identity["code_commit"]),
        ("source", identity["source_sha256"]),
        ("lock", identity["cargo_lock_sha256"]),
        ("rustc", identity["rustc_version"]),
        ("target", identity["target"]),
        ("host", identity["host"]),
        ("profile", identity["profile"]),
        ("opt", identity["opt_level"]),
        ("debug", "true" if identity["debug"] else "false"),
        ("rustflags", identity["rustflags_sha256"]),
    ]
    material = "\0".join(part for pair in fields for part in pair)
    return sha(material.encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--research-python", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True,
                        help="path produced by cargo build, normally $CARGO_TARGET_DIR/debug/nqc-miner")
    args = parser.parse_args()
    module = Path(__file__).resolve().parents[1]
    root = module.parents[1]
    output = args.output.absolute()
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError("symlink in audit output path")
    output.mkdir(exist_ok=False)
    initial = manifest(module)
    environment = os.environ.copy()
    environment.update(CARGO_NET_OFFLINE="true", PYTHONDONTWRITEBYTECODE="1",
                       POLARS_MAX_THREADS="1", NQC_MINER_TEST_BINARY=str(args.binary.absolute()))
    commands = [
        ("rust-build", ["cargo", "build", "--locked", "--offline"]),
        ("rust-tests", ["cargo", "test", "--all-targets", "--locked", "--offline"]),
        ("clippy", ["cargo", "clippy", "--all-targets", "--locked", "--offline", "--", "-D", "warnings"]),
        ("rustfmt", ["cargo", "fmt", "--", "--check"]),
        ("python-research-tests", [str(args.research_python.absolute()), "-m", "unittest", "discover", "-s", "research", "-p", "test_*.py", "-v"]),
        ("repository-isolation", [str(args.research_python.absolute()), str(root / "migration/verify_isolation.py")]),
        ("miner-scope", [str(args.research_python.absolute()), "scripts/check_scope.py"]),
        ("build-identity", [str(args.binary.absolute()), "about"]),
    ]
    checks = []
    for name, command in commands:
        start = time.monotonic()
        result = subprocess.run(command, cwd=module, env=environment,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        log_name = name + ".txt"
        with (output / log_name).open("xb") as stream:
            stream.write(result.stdout)
        check = {"name": name, "command": command, "exit_code": result.returncode,
                 "elapsed_seconds": round(time.monotonic() - start, 3),
                 "log": log_name, "log_sha256": sha(result.stdout)}
        text = result.stdout.decode("utf-8", errors="replace")
        if name == "rust-tests":
            check["passed"] = sum(int(value) for value in re.findall(r"test result: ok\. (\d+) passed", text))
            check["failed"] = sum(int(value) for value in re.findall(r"; (\d+) failed", text))
            check["ignored"] = sum(int(value) for value in re.findall(r"; (\d+) ignored", text))
        if name == "python-research-tests":
            counts = re.findall(r"Ran (\d+) tests?", text)
            check["executed"] = int(counts[-1]) if counts else None
        if name == "build-identity" and result.returncode == 0:
            identity = json.loads(text)
            rustc = subprocess.run(["rustc", "--version"], cwd=module, env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            expected_rustc = rustc.stdout.decode("utf-8", errors="replace").strip()
            check["binary_source_matches_inputs"] = (
                identity["source_sha256"] == rust_source_sha256(module)
                and identity["cargo_lock_sha256"] == initial["Cargo.lock"]
                and rustc.returncode == 0
                and identity["rustc_version"] == expected_rustc
                and identity["profile"] == "debug"
                and identity.get("build_identity_sha256") == build_identity_sha256(identity)
            )
            if not check["binary_source_matches_inputs"]:
                check["exit_code"] = 1
        checks.append(check)
        print(json.dumps({"check": name, "exit_code": check["exit_code"]}), flush=True)
    stable = manifest(module) == initial
    summary = {"schema": "nqc-miner-offline-audit-v1", "producer": "nqc-miner",
               "namespace": "nqc_miner_v1", "completed_at_utc": datetime.now(timezone.utc).isoformat(),
               "status": "pass" if stable and all(c["exit_code"] == 0 for c in checks) else "fail",
               "audited_inputs_unchanged": stable, "inputs": initial, "checks": checks,
               "network_required_for_checks": False, "observer_bridge_enabled": False,
               "spending_authorized": False, "economic_certification": False,
               "infrastructure_runtime_checks_executed": False}
    with (output / "summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"status": summary["status"], "summary": str(output / "summary.json")}), flush=True)
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
