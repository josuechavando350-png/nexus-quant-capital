"""Manage a separate local checkpoint witness; never sends data or deletes audit history."""

import argparse
import json
from pathlib import Path
import secrets
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.audit_pages import MAX_ARCHIVE_BYTES
from nqc_defense.codec import Rejected, decode
from nqc_defense.files import create_local, read_local
from nqc_defense.witness import Witness
from nqc_defense.receipts import hex_digest


def private_key(path):
    if path.lstat().st_mode & 0o077:
        raise Rejected("key_file_permissions")
    key = read_local(path.parent, path.name, 32)
    if len(key) != 32:
        raise Rejected("witness_key_size")
    return key


def document(path):
    return decode(read_local(path.parent, path.name, 4096))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--witness-key-file", type=Path, required=True)
    parser.add_argument("--audit-key-file", type=Path, required=True)
    parser.add_argument("--policy-digest", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create a new private witness key file and a new witness directory")
    status = commands.add_parser("status")
    status.add_argument("--expected", type=Path, help="Trusted receipt stored independently from this witness")
    advance = commands.add_parser("advance")
    advance.add_argument("archives", type=Path, nargs="+")
    advance.add_argument("--target", type=Path, required=True)
    advance.add_argument("--expected", type=Path, required=True)
    args = parser.parse_args()
    try:
        audit_key = private_key(args.audit_key_file)
        hex_digest(args.policy_digest)
        if args.command == "init":
            if args.root.exists() or args.root.is_symlink():
                raise Rejected("witness_directory_exists")
            witness_key = secrets.token_bytes(32)
            create_local(args.witness_key_file.parent, args.witness_key_file.name, witness_key)
            witness = Witness.create(args.root, witness_key, audit_key, args.policy_digest)
            result = witness.head()
        else:
            witness = Witness(args.root, private_key(args.witness_key_file), audit_key, args.policy_digest)
            if args.command == "status":
                result = witness.head(document(args.expected) if args.expected else None)
            else:
                pages = (read_local(path.parent, path.name, MAX_ARCHIVE_BYTES) for path in args.archives)
                result = witness.advance(pages, document(args.target), document(args.expected))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Rejected, OSError, sqlite3.Error) as exc:
        print(json.dumps({"verified": False, "reason": str(exc) if isinstance(exc, Rejected) else "local_storage_error"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
