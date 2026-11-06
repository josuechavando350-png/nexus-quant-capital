"""Export a private review dossier or verify its historical snapshot offline."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nqc_defense.case_evidence import MAX_BUNDLE
from nqc_defense.case_review import CaseReview
from nqc_defense.codec import Rejected, decode
from nqc_defense.operations import OperationsStore
from nqc_defense.review_dossier import MAX_DOSSIER, capture_dossier, verify_dossier
from nqc_defense.review_policy import ReviewPolicy, read_credential
from case_review import read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    capture = commands.add_parser('capture'); verify = commands.add_parser('verify')
    for command in (capture,verify):
        command.add_argument('--pins-file',type=Path,required=True)
        command.add_argument('--audit-key-file',type=Path,required=True)
    capture.add_argument('--operations-root',type=Path,required=True)
    capture.add_argument('--policy-root',type=Path,required=True)
    capture.add_argument('--policy-digest',required=True)
    capture.add_argument('--evidence-file',type=Path,required=True)
    capture.add_argument('--output',type=Path,required=True)
    verify.add_argument('--dossier-file',type=Path,required=True)
    verify.add_argument('--dossier-digest',required=True)
    args = parser.parse_args()
    try:
        pins = decode(read(args.pins_file,4096),max_bytes=4096)
        key = read_credential(args.audit_key_file)
        if args.command == 'capture':
            review = CaseReview(OperationsStore(args.operations_root),ReviewPolicy(args.policy_root,args.policy_digest))
            result = capture_dossier(review,key,pins,read(args.evidence_file,MAX_BUNDLE),args.output)
        else:
            result = verify_dossier(read(args.dossier_file,MAX_DOSSIER),args.dossier_digest,pins,key)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (Rejected,OSError,sqlite3.Error) as exc:
        print(json.dumps({'success':False,'reason':str(exc) if isinstance(exc,Rejected) else 'local_storage_error'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
