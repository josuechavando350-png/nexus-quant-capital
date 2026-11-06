"""Issue a dossier validation statement or verify it with an externally pinned public key."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.codec import Rejected, decode
from nqc_defense.dossier_attestation import MAX_ATTESTATION, create_signer, load_signer, publish_attestation, verify_attestation
from nqc_defense.review_dossier import MAX_DOSSIER
from nqc_defense.review_policy import read_credential
from case_review import read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init-signer')
    init.add_argument('--signer-root', type=Path, required=True)
    issue = commands.add_parser('issue')
    verify = commands.add_parser('verify')
    for command in (issue, verify):
        command.add_argument('--pins-file', type=Path, required=True)
        command.add_argument('--dossier-file', type=Path, required=True)
        command.add_argument('--dossier-digest', required=True)
        command.add_argument('--public-key-digest', required=True)
    issue.add_argument('--signer-root', type=Path, required=True)
    issue.add_argument('--audit-key-file', type=Path, required=True)
    issue.add_argument('--output', type=Path, required=True)
    verify.add_argument('--public-key-file', type=Path, required=True)
    verify.add_argument('--attestation-file', type=Path, required=True)
    verify.add_argument('--attestation-digest', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'init-signer':
            result = create_signer(args.signer_root)
        else:
            pins = decode(read(args.pins_file, 4096), max_bytes=4096)
            dossier = read(args.dossier_file, MAX_DOSSIER)
            if args.command == 'issue':
                result = publish_attestation(args.output, dossier, args.dossier_digest, pins,
                    read_credential(args.audit_key_file), load_signer(args.signer_root, args.public_key_digest),
                    args.public_key_digest)
            else:
                result = verify_attestation(read(args.attestation_file, MAX_ATTESTATION), args.attestation_digest,
                    dossier, args.dossier_digest, pins, read(args.public_key_file, 32), args.public_key_digest)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Rejected, OSError) as exc:
        print(json.dumps({'success': False, 'reason': str(exc) if isinstance(exc, Rejected) else 'local_storage_error'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
