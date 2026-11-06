"""Create, verify and finalize local audit archives without deleting history."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.archive_store import ArchiveStore
from nqc_defense.archive_coverage import ArchiveCoverage
from nqc_defense.archive_inventory import ArchiveInventory, MAX_SELECTION_BYTES
from nqc_defense.archive_budget import limits as budget_limits
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
    parser.add_argument("--budget-digest", help="Externally retained SHA-256 of the archive budget policy")
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--max-bytes", type=int)
    initialize.add_argument("--max-objects", type=int)
    configure = commands.add_parser("configure-budget", help="Install a create-only budget policy or recover an identical attempt")
    configure.add_argument("--max-bytes", type=int, required=True)
    configure.add_argument("--max-objects", type=int, required=True)
    commands.add_parser("budget-status")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("pages", type=Path, nargs="+")
    prepare.add_argument("--start", type=Path)
    prepare.add_argument("--target", type=Path, required=True)
    verify = commands.add_parser("verify")
    finalize = commands.add_parser("finalize")
    coverage = commands.add_parser("coverage", help="Verify ordered archived intervals against pinned witness receipts")
    coverage.add_argument("manifests", nargs="*")
    coverage.add_argument("--seal", action="store_true", help="Persist a canonical coverage catalog after verification")
    verify_coverage = commands.add_parser("verify-coverage")
    verify_coverage.add_argument("catalog_sha256")
    inventory = commands.add_parser("inventory", help="Read-only inventory against externally pinned catalog selections")
    inventory.add_argument("--selections", type=Path, required=True)
    for command in (prepare, verify, finalize, coverage, verify_coverage, inventory):
        command.add_argument("--audit-key-file", type=Path, required=True)
        command.add_argument("--policy-digest", required=True)
    for command in (verify, finalize):
        command.add_argument("manifest_sha256")
    for command in (finalize, coverage, verify_coverage, inventory):
        command.add_argument("--witness-root", type=Path, required=True)
        command.add_argument("--witness-key-file", type=Path, required=True)
    for command in (coverage, verify_coverage):
        command.add_argument("--start-receipt", type=Path, required=True)
        command.add_argument("--target-receipt", type=Path, required=True)
    finalize.add_argument("--expected", type=Path, required=True)
    finalize.add_argument("--receipt-output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "init":
            if args.budget_digest is not None or (args.max_bytes is None) != (args.max_objects is None):
                raise Rejected("archive_budget_arguments")
            if args.max_bytes is not None:
                budget_limits(args.max_bytes, args.max_objects)
            store = ArchiveStore.create(args.root)
            result = {"created": True}
            if args.max_bytes is not None:
                result.update(store.configure_budget(args.max_bytes, args.max_objects))
        elif args.command == "configure-budget":
            result = ArchiveStore(args.root, args.budget_digest).configure_budget(args.max_bytes, args.max_objects)
        elif args.command == "budget-status":
            result = ArchiveStore(args.root, args.budget_digest).budget_status()
        else:
            store = ArchiveStore(args.root, args.budget_digest)
            audit_key = key_file(args.audit_key_file)
            if args.command == "prepare":
                pages = (read_local(path.parent, path.name, MAX_ARCHIVE_BYTES) for path in args.pages)
                result = store.prepare(pages, audit_key, args.policy_digest,
                                       document(args.start) if args.start else ORIGIN, document(args.target))
            elif args.command == "verify":
                result = store.verify(args.manifest_sha256, audit_key, args.policy_digest)
            elif args.command == "finalize":
                witness = Witness(args.witness_root, key_file(args.witness_key_file), audit_key, args.policy_digest)
                result = store.finalize(witness, args.manifest_sha256, document(args.expected))
                if args.receipt_output:
                    retained = {name: result[name] for name in ("manifest_sha256", "witness_receipt")}
                    publish_local(args.receipt_output.parent, args.receipt_output.name, canonical(retained))
            elif args.command == "inventory":
                witness = Witness(args.witness_root, key_file(args.witness_key_file), audit_key, args.policy_digest)
                selected = decode(read_local(args.selections.parent, args.selections.name, MAX_SELECTION_BYTES),
                                  max_bytes=MAX_SELECTION_BYTES)
                result = ArchiveInventory(store, witness).inspect(selected)
            else:
                witness = Witness(args.witness_root, key_file(args.witness_key_file), audit_key, args.policy_digest)
                checker = ArchiveCoverage(store, witness)
                start, target = document(args.start_receipt), document(args.target_receipt)
                if args.command == "verify-coverage":
                    result = checker.verify_catalog(args.catalog_sha256, start, target)
                elif args.seal:
                    result = checker.seal(args.manifests, start, target)
                else:
                    result = checker.verify(args.manifests, start, target)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("verified", True) and result.get("within_budget", True) else 2
    except (Rejected, OSError, sqlite3.Error) as exc:
        print(json.dumps({"verified": False, "reason": str(exc) if isinstance(exc, Rejected) else "local_storage_error"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
