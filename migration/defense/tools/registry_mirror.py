"""Receive signed registry snapshots locally and verify dossiers against the accepted view."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.codec import Rejected
from nqc_defense.dossier_attestation import MAX_ATTESTATION
from nqc_defense.registry_mirror import RegistryMirror
from nqc_defense.review_dossier import MAX_DOSSIER
from nqc_defense.signer_registry import MAX_BUNDLE
from signer_registry import document
from case_review import read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init'); status = commands.add_parser('status'); accept = commands.add_parser('accept')
    export = commands.add_parser('export'); verify = commands.add_parser('verify')
    for command in (init, status, accept, export, verify):
        command.add_argument('--mirror-root', type=Path, required=True)
        command.add_argument('--registry-digest', required=True)
        command.add_argument('--authority-public-digest', required=True)
    for command in (accept, export, verify):
        command.add_argument('--expected-file', type=Path, required=True)
    status.add_argument('--expected-file', type=Path)
    accept.add_argument('--bundle-file', type=Path, required=True)
    accept.add_argument('--bundle-digest', required=True)
    accept.add_argument('--target-file', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    verify.add_argument('--receipt-file', type=Path, required=True)
    verify.add_argument('--pins-file', type=Path, required=True)
    verify.add_argument('--attestation-file', type=Path, required=True)
    verify.add_argument('--attestation-digest', required=True)
    verify.add_argument('--dossier-file', type=Path, required=True)
    verify.add_argument('--dossier-digest', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'init':
            mirror = RegistryMirror.create(args.mirror_root, args.registry_digest, args.authority_public_digest)
            result = mirror.status()
        else:
            mirror = RegistryMirror(args.mirror_root, args.registry_digest, args.authority_public_digest)
            if args.command == 'status':
                result = mirror.status(document(args.expected_file) if args.expected_file else None)
            elif args.command == 'accept':
                result = mirror.accept(read(args.bundle_file, MAX_BUNDLE), args.bundle_digest,
                                       document(args.target_file), document(args.expected_file))
            elif args.command == 'export':
                result = mirror.publish(args.output, document(args.expected_file))
            else:
                result = mirror.verify(document(args.expected_file), document(args.receipt_file),
                    read(args.attestation_file, MAX_ATTESTATION), args.attestation_digest,
                    read(args.dossier_file, MAX_DOSSIER), args.dossier_digest, document(args.pins_file))
        print(json.dumps(result, sort_keys=True)); return 0
    except (Rejected, OSError, sqlite3.Error) as exc:
        print(json.dumps({'success': False, 'reason': str(exc) if isinstance(exc, Rejected) else 'local_storage_error'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
