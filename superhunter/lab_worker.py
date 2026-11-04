"""Isolated-interpreter worker for fixed native regression fixtures only.

The audit hook is defense in depth for trusted pinned code, not an OS security
sandbox suitable for hostile Python, Solidity, native libraries or plugins.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import sys


def deny_external_execution(event: str, args: tuple) -> None:
    if event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn")) or event in ("os.system", "ctypes.dlopen"):
        raise PermissionError("local native lab forbids network and child execution")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fixed local native-component regressions")
    parser.add_argument("mode", choices=("run", "verify"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    # Hard bounds apply to this short-lived process, not the caller.
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024**2, 1024 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (20 * 1024**2, 20 * 1024**2))
    sys.dont_write_bytecode = True
    sys.addaudithook(deny_external_execution)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        # Check guard without connecting anywhere.
        import socket
        try:
            socket.socket()
        except PermissionError:
            pass
        else:
            raise RuntimeError("network guard self-test failed")
        from superhunter.local_lab import run_local, verify_local_bundle
        result = run_local(args.directory) if args.mode == "run" else verify_local_bundle(args.directory)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "LOCAL_INTEGRATION_ERROR", "error_type": type(exc).__name__,
                          "reason": str(exc)[:240], "vulnerability_confirmed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
