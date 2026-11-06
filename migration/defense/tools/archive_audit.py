"""Create, verify and finalize local audit archives without deleting history."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.archive_store import ArchiveStore
from nqc_defense.audit_pages import MAX_ARCHIVE_BYTES
from nqc_defense.codec import Rejected, canonical, decode
from nqc_defense.files import publish_local, read_local
from nqc_defense.witness import ORIGIN, Witness


def key_file(path):
    if path.lstat().st_mode & 0o077:
        raise Rejected("key_file_permissions")
    key = read_local(path.parent, path.name, 32)
    if len(key) != 32:
        raise Rejected("audit_key_size")
    return key


def document(path):
    return decode(read_local(path.parent, path.name, 4096))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("pages", type=Path, nargs="+")
    prepare.add_argument("--start", type=Path)
    prepare.add_argument("--target", type=Path, required=True)
    verify = commands.add_parser("verify")
    finalize = commands.add_parser("finalize")
    for command in (prepare, verify, finalize):
        command.add_argument("--audit-key-file", type=Path, required=True)
        command.add_argument("--policy-digest", required=True)
    for command in (verify, finalize):
        command.add_argument("manifest_sha256")
    finalize.add_argument("--witness-root", type=Path, required=True)
    finalize.add_argument("--witness-key-file", type=Path, required=True)
    finalize.add_argument("--expected", type=Path, required=True)
    finalize.add_argument("--receipt-output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "init":
            ArchiveStore.create(args.root)
            result = {"created": True}
        else:
            store = ArchiveStore(args.root)
            audit_key = key_file(args.audit_key_file)
            if args.command == "prepare":
                pages = (read_local(path.parent, path.name, MAX_ARCHIVE_BYTES) for path in args.pages)
                result = store.prepare(pages, audit_key, args.policy_digest,
                                       document(args.start) if args.start else ORIGIN, document(args.target))
            elif args.command == "verify":
                result = store.verify(args.manifest_sha256, audit_key, args.policy_digest)
            else:
                witness = Witness(args.witness_root, key_file(args.witness_key_file), audit_key, args.policy_digest)
                result = store.finalize(witness, args.manifest_sha256, document(args.expected))
                if args.receipt_output:
                    retained = {name: result[name] for name in ("manifest_sha256", "witness_receipt")}
                    publish_local(args.receipt_output.parent, args.receipt_output.name, canonical(retained))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Rejected, OSError, sqlite3.Error) as exc:
        print(json.dumps({"verified": False, "reason": str(exc) if isinstance(exc, Rejected) else "local_storage_error"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
