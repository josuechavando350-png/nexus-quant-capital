"""Local authentication ingestion and shared incident view; no remote responses."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.codec import Rejected
from nqc_defense.managed_integrity import ManagedIntegrity
from nqc_defense.operations import OperationsStore
from nqc_defense.openssh_log import FORMATS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    register = commands.add_parser("register-auth")
    register.add_argument("--source", required=True)
    register.add_argument("--log-root", type=Path, required=True)
    register.add_argument("--name", required=True)
    register.add_argument("--threshold", type=int, default=5)
    register.add_argument("--window-seconds", type=int, default=300)
    register.add_argument("--format", choices=FORMATS, default="nqc-jsonl")
    register.add_argument("--expected-host")
    events = commands.add_parser("events")
    events.add_argument("--after", type=int, default=0)
    events.add_argument("--limit", type=int, default=100)
    cases = commands.add_parser("cases")
    cases.add_argument("--after", default="")
    cases.add_argument("--limit", type=int, default=100)
    capture = commands.add_parser("capture-managed")
    capture.add_argument("--managed-root", type=Path, required=True)
    capture.add_argument("--manifest-digest", required=True)
    for command in (register, events, cases, capture):
        command.add_argument("--tenant", required=True)
        command.add_argument("--asset", required=True)
    for name in ("poll-auth", "rotate-auth"):
        command = commands.add_parser(name)
        command.add_argument("--source", required=True)
        command.add_argument("--config-digest", required=True)
        command.add_argument("--previous-name", required=name == "rotate-auth")
        if name == "poll-auth":
            command.add_argument("--max-records", type=int, default=500)
    args = parser.parse_args()
    try:
        store = OperationsStore.create(args.root) if args.command == "init" else OperationsStore(args.root)
        if args.command == "init":
            result = {"created": True}
        elif args.command == "register-auth":
            monitor = AuthLogMonitor.register(store, args.source, args.tenant, args.asset, args.log_root, args.name,
                                              args.threshold, args.window_seconds, format_name=args.format,
                                              expected_host=args.expected_host)
            result = {"registered": True, "config_digest": monitor.digest}
        elif args.command in ("poll-auth", "rotate-auth"):
            monitor = AuthLogMonitor(store, args.source, args.config_digest)
            result = monitor.poll(args.previous_name, args.max_records) if args.command == "poll-auth" else monitor.rotate(args.previous_name)
        elif args.command == "events":
            result = {"events": store.events(args.tenant, args.asset, args.after, args.limit)}
        elif args.command == "cases":
            result = {"cases": store.cases(args.tenant, args.asset, args.after, args.limit)}
        else:
            result = store.capture_managed(ManagedIntegrity(args.managed_root, args.manifest_digest), args.tenant, args.asset)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Rejected, OSError, sqlite3.Error) as exc:
        print(json.dumps({"success": False, "reason": str(exc) if isinstance(exc, Rejected) else "local_storage_error"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
