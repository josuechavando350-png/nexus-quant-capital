"""Launcher with a fixed local-only worker and minimal process environment."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .privacy import PrivateArgumentParser


def main(argv: list[str], *, verify: bool = False) -> int:
    parser = PrivateArgumentParser(description="Run/verify bounded local numerical fuzzing")
    parser.add_argument("--bundle" if verify else "--out", dest="directory", type=Path, required=True)
    if not verify:
        parser.add_argument("--seed", type=int, default=20261103)
        parser.add_argument("--cases", type=int, default=128)
    args = parser.parse_args(argv)
    if os.name != "posix":
        print(json.dumps({"status": "LOCAL_FUZZ_ERROR", "reason": "POSIX required"}))
        return 2
    worker = Path(__file__).with_name("fuzz_worker.py").resolve()
    command = [sys.executable, "-I", "-B", str(worker), "verify" if verify else "run",
               str(args.directory.absolute())]
    if not verify:
        if args.seed < 0 or args.seed >= 2**64 or not 1 <= args.cases <= 256:
            parser.error("seed must be uint64 and cases must be in [1,256]")
        command.extend(["--seed", str(args.seed), "--cases", str(args.cases)])
    try:
        proc = subprocess.run(command, cwd=worker.parent.parent,
                              env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}, timeout=45,
                              capture_output=True, text=True, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "LOCAL_FUZZ_ERROR", "reason": type(exc).__name__,
                          "vulnerability_confirmed": False}))
        return 2
    if proc.returncode:
        print(json.dumps({"status": "LOCAL_FUZZ_ERROR", "worker_exit": proc.returncode,
                          "vulnerability_confirmed": False}))
        return 2
    try:
        result = json.loads(proc.stdout)
        if (type(result) is not dict or result.get("status") != "LOCAL_FUZZ_PASS" or
            result.get("vulnerability_confirmed") is not False):
            raise ValueError("unexpected verdict")
    except (KeyError, TypeError, ValueError):
        print(json.dumps({"status": "LOCAL_FUZZ_ERROR", "reason": "invalid worker result",
                          "vulnerability_confirmed": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0
