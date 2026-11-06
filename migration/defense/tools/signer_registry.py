"""Manage a local signing-key registry and verify registered dossiers using public data."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.codec import Rejected, decode, fields
from nqc_defense.dossier_attestation import MAX_ATTESTATION
from nqc_defense.review_dossier import MAX_DOSSIER
from nqc_defense.review_policy import read_credential
from nqc_defense.signer_registry import MAX_BUNDLE, SignerRegistry, public_hex, verify_registered
from case_review import read


def document(path, limit=8192):
    return decode(read(path, limit), max_bytes=limit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init'); change = commands.add_parser('change'); record = commands.add_parser('record')
    status = commands.add_parser('status'); export = commands.add_parser('export'); verify = commands.add_parser('verify')
    for command in (init, change, record, status, export):
        command.add_argument('--registry-root', type=Path, required=True)
    for command in (init, change, record, status, export, verify):
        command.add_argument('--authority-public-digest', required=True)
    for command in (change, record, status, export, verify):
        command.add_argument('--registry-digest', required=True)
    init.add_argument('--authority-public-file', type=Path, required=True)
    init.add_argument('--scope-file', type=Path, required=True)
    for command in (change, record):
        command.add_argument('--authority-key-file', type=Path, required=True)
        command.add_argument('--request-file', type=Path, required=True)
    status.add_argument('--expected-file', type=Path)
    for command in (export, verify):
        command.add_argument('--expected-file', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    for command in (record, verify):
        command.add_argument('--pins-file', type=Path, required=True)
        command.add_argument('--attestation-file', type=Path, required=True)
        command.add_argument('--attestation-digest', required=True)
        command.add_argument('--dossier-file', type=Path, required=True)
        command.add_argument('--dossier-digest', required=True)
    verify.add_argument('--bundle-file', type=Path, required=True)
    verify.add_argument('--bundle-digest', required=True)
    verify.add_argument('--receipt-file', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'init':
            scope = document(args.scope_file); fields(scope, ('tenant', 'asset', 'policy_digest'))
            registry = SignerRegistry.create(args.registry_root, read(args.authority_public_file, 32),
                args.authority_public_digest, scope['tenant'], scope['asset'], scope['policy_digest'])
            result = registry.status()
        elif args.command == 'verify':
            result = verify_registered(read(args.bundle_file, MAX_BUNDLE), args.bundle_digest,
                args.registry_digest, args.authority_public_digest, document(args.expected_file), document(args.receipt_file),
                read(args.attestation_file, MAX_ATTESTATION), args.attestation_digest,
                read(args.dossier_file, MAX_DOSSIER), args.dossier_digest, document(args.pins_file))
        else:
            registry = SignerRegistry(args.registry_root, args.registry_digest, args.authority_public_digest)
            if args.command == 'status':
                result = registry.status(document(args.expected_file) if args.expected_file else None)
            elif args.command == 'export':
                result = registry.publish(args.output, document(args.expected_file))
            else:
                request = document(args.request_file)
                key = read_credential(args.authority_key_file)
                if args.command == 'change':
                    fields(request, ('action', 'key_id', 'request_id', 'reason', 'expected', 'new_public_key_hex'))
                    public_key = public_hex(request['new_public_key_hex']) if request['new_public_key_hex'] is not None else None
                    result = registry.change(key, request['action'], request['key_id'], request['request_id'],
                                             request['reason'], request['expected'], public_key)
                else:
                    fields(request, ('key_id', 'request_id', 'reason', 'expected'))
                    result = registry.record(key, read(args.attestation_file, MAX_ATTESTATION), args.attestation_digest,
                        read(args.dossier_file, MAX_DOSSIER), args.dossier_digest, document(args.pins_file), request['key_id'],
                        request['request_id'], request['reason'], request['expected'])
        print(json.dumps(result, sort_keys=True)); return 0
    except (Rejected, OSError, sqlite3.Error) as exc:
        print(json.dumps({'success': False, 'reason': str(exc) if isinstance(exc, Rejected) else 'local_storage_error'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
