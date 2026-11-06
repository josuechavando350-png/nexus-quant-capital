"""Manage local review credentials; all secret inputs are private files."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.codec import Rejected, decode, fields
from nqc_defense.operations import OperationsStore
from nqc_defense.review_credentials import ReviewCredentials, create_credential
from nqc_defense.review_policy import ReviewPolicy, read_credential
from case_review import read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new-token")
    new.add_argument("--credential-file", required=True, type=Path)
    status = commands.add_parser("status")
    change = commands.add_parser("change")
    for command in (status, change):
        command.add_argument("--operations-root", required=True, type=Path)
        command.add_argument("--policy-root", required=True, type=Path)
        command.add_argument("--policy-digest", required=True)
        command.add_argument("--admin-key-file", required=True, type=Path)
    status.add_argument("--expected", type=Path)
    status.add_argument("--after", type=int, default=0)
    status.add_argument("--limit", type=int, default=100)
    change.add_argument("--request-file", required=True, type=Path)
    change.add_argument("--credential-file", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "new-token":
            result = create_credential(args.credential_file)
        else:
            policy = ReviewPolicy(args.policy_root, args.policy_digest)
            lifecycle = ReviewCredentials(OperationsStore(args.operations_root), policy)
            admin = read_credential(args.admin_key_file)
            if args.command == "status":
                expected = decode(read(args.expected, 4096), max_bytes=4096) if args.expected else None
                result = lifecycle.status(admin, expected=expected, after=args.after, limit=args.limit)
            else:
                request = decode(read(args.request_file, 16384), max_bytes=16384)
                fields(request, ("actor", "action", "reason", "request_id", "expected") +
                       (("expires_at_ns",) if type(request) is dict and "expires_at_ns" in request else ()))
                token = read_credential(args.credential_file) if args.credential_file else None
                result = lifecycle.change(admin, **request, credential=token)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Rejected, OSError, sqlite3.Error) as exc:
        print(json.dumps({"success": False, "reason": str(exc) if isinstance(exc, Rejected) else "local_storage_error"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
