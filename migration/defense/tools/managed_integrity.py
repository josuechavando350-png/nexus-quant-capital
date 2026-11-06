"""Operate an explicitly initialized managed JSON copy; never enroll a production source in place."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.managed_integrity import ManagedIntegrity
from nqc_defense.codec import Rejected, integer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest-digest")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("init")
    create.add_argument("source", type=Path)
    for name in ("inspect", "status", "read-json", "recover", "archive"):
        commands.add_parser(name)
    monitor = commands.add_parser("monitor")
    monitor.add_argument("--samples", type=int, default=1)
    monitor.add_argument("--interval-seconds", type=int, default=3)
    args = parser.parse_args()
    try:
        if args.command == "init":
            if args.manifest_digest is not None:
                raise Rejected("managed_init_arguments")
            managed = ManagedIntegrity.create(args.source, args.root)
            result = {"created": True, "manifest_digest": managed.digest}
        else:
            managed = ManagedIntegrity(args.root, args.manifest_digest)
            if args.command == "monitor":
                integer(args.samples, 1, 1000)
                integer(args.interval_seconds, 3, 3600)
                for index in range(args.samples):
                    print(json.dumps(managed.inspect(), sort_keys=True), flush=True)
                    if index + 1 < args.samples:
                        time.sleep(args.interval_seconds)
                return 0
            operation = {"inspect": managed.inspect, "status": managed.status, "read-json": managed.read_json,
                         "recover": managed.recover, "archive": managed.archive_evidence}[args.command]
            result = operation()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Rejected, OSError, sqlite3.Error) as exc:
        print(json.dumps({"success": False, "reason": str(exc) if isinstance(exc, Rejected) else "local_storage_error"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
