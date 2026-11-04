"""A short-lived local-only worker for bounded numerical property fuzzing."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import resource
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="SUPERHUNTER pinned native fuzz laboratory")
    parser.add_argument("mode", choices=("run", "verify"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--seed", type=int, default=20261103)
    parser.add_argument("--cases", type=int, default=128)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024**2, 1024 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (20 * 1024**2, 20 * 1024**2))
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from superhunter.lab_worker import deny_external_execution
    sys.addaudithook(deny_external_execution)
    try:
        import socket
        try:
            socket.socket()
        except PermissionError:
            pass
        else:
            raise RuntimeError("network guard self-test failed")
        # Executed with -I: sys.path contains only isolated stdlib by default.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from superhunter.fuzz_lab import run_fuzz, verify_fuzz
        result = (run_fuzz(args.directory, args.seed, args.cases)
                  if args.mode == "run" else verify_fuzz(args.directory))
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "LOCAL_FUZZ_ERROR", "reason": type(exc).__name__,
                          "vulnerability_confirmed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
