"""Capture scoped authentication evidence or verify a preserved bundle offline."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.case_evidence import MAX_BUNDLE, capture_case, describe_case, verify_bundle
from nqc_defense.codec import Rejected, decode
from nqc_defense.files import read_local
from nqc_defense.operations import OperationsStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    describe = commands.add_parser("describe")
    capture = commands.add_parser("capture")
    verify = commands.add_parser("verify")
    for command in (describe, capture, verify):
        command.add_argument("--tenant", required=True)
        command.add_argument("--asset", required=True)
        command.add_argument("--case-id", required=True)
    for command in (describe, capture):
        command.add_argument("--store-root", type=Path, required=True)
    for command in (capture, verify):
        command.add_argument("--case-digest", required=True)
        command.add_argument("--config-digest", required=True)
    capture.add_argument("--source-map", type=Path, required=True)
    capture.add_argument("--output", type=Path, required=True)
    verify.add_argument("--input", type=Path, required=True)
    verify.add_argument("--digest", required=True)
    args = parser.parse_args()
    try:
        if args.command == "verify":
            path = args.input.absolute()
            result = verify_bundle(read_local(path.parent, path.name, MAX_BUNDLE), args.digest,
                                   args.tenant, args.asset, args.case_id, args.case_digest, args.config_digest)
        else:
            store = OperationsStore(args.store_root)
            if args.command == "describe":
                result = describe_case(store, args.tenant, args.asset, args.case_id)
            else:
                path = args.source_map.absolute()
                selection = decode(read_local(path.parent, path.name, 4096), max_bytes=4096)
                result = capture_case(store, args.tenant, args.asset, args.case_id, args.case_digest,
                                      args.config_digest, selection, args.output)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Rejected, OSError, sqlite3.Error) as exc:
        print(json.dumps({"verified": False, "reason": str(exc) if isinstance(exc, Rejected) else "local_storage_error"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
