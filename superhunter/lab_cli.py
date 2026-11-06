"""Fixed worker launcher: never accepts target addresses, RPCs or executable paths."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .privacy import PrivateArgumentParser


def main(argv: list[str], *, verify: bool = False) -> int:
    parser = PrivateArgumentParser(description="Execute or verify the fixed DIABLO/NQC local lab")
    parser.add_argument("--bundle" if verify else "--out", required=True, type=Path, dest="directory")
    args = parser.parse_args(argv)
    if os.name != "posix":
        print(json.dumps({"status": "LOCAL_INTEGRATION_ERROR", "reason": "POSIX worker required"}))
        return 2
    worker = Path(__file__).with_name("lab_worker.py").resolve()
    command = [sys.executable, "-I", "-B", str(worker), "verify" if verify else "run", str(args.directory.absolute())]
    # Do not forward RPC URLs, API keys, PYTHONPATH or shell configuration.
    env = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        proc = subprocess.run(command, cwd=worker.parent.parent, env=env, timeout=30,
                              capture_output=True, text=True, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "LOCAL_INTEGRATION_ERROR", "error_type": type(exc).__name__}))
        return 2
    if proc.returncode != 0:
        # Worker stderr may include paths or environment details; don't echo it.
        print(json.dumps({"status": "LOCAL_INTEGRATION_ERROR", "worker_exit": proc.returncode,
                          "vulnerability_confirmed": False}))
        return 2
    try:
        result = json.loads(proc.stdout)
        if result["status"] != "LOCAL_INTEGRATION_PASS" or result["vulnerability_confirmed"] is not False:
            raise ValueError("unexpected worker verdict")
    except (ValueError, KeyError, TypeError):
        print(json.dumps({"status": "LOCAL_INTEGRATION_ERROR", "reason": "invalid worker response"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0
