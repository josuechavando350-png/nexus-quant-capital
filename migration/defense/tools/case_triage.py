"""Rank selected authentication dossiers using a pinned policy and received signer registry."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nqc_defense.case_triage import MAX_POLICY, MAX_REPORT, MAX_SELECTION, TriagePolicy, load_selection, publish_output, verify_output
from nqc_defense.codec import Rejected
from nqc_defense.registry_mirror import RegistryMirror
from case_review import read
from signer_registry import document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    rank = commands.add_parser('rank'); verify = commands.add_parser('verify')
    for command in (rank,verify):
        command.add_argument('--mirror-root',type=Path,required=True)
        command.add_argument('--registry-digest',required=True)
        command.add_argument('--authority-public-digest',required=True)
        command.add_argument('--expected-file',type=Path,required=True)
        command.add_argument('--policy-file',type=Path,required=True)
        command.add_argument('--policy-digest',required=True)
        command.add_argument('--input-root',type=Path,required=True)
        command.add_argument('--selection-file',type=Path,required=True)
        command.add_argument('--selection-digest',required=True)
    rank.add_argument('--output',type=Path,required=True)
    verify.add_argument('--report-file',type=Path,required=True); verify.add_argument('--report-digest',required=True)
    args = parser.parse_args()
    try:
        policy = TriagePolicy(read(args.policy_file,MAX_POLICY),args.policy_digest)
        items = load_selection(args.input_root,read(args.selection_file,MAX_SELECTION),args.selection_digest)
        mirror = RegistryMirror(args.mirror_root,args.registry_digest,args.authority_public_digest)
        report = mirror.triage(document(args.expected_file),policy,items)
        result = (publish_output(args.output,report) if args.command == 'rank' else
                  verify_output(read(args.report_file,MAX_REPORT),args.report_digest,report))
        print(json.dumps(result,sort_keys=True)); return 0
    except (Rejected,OSError,sqlite3.Error) as exc:
        print(json.dumps({'success':False,'reason':str(exc) if isinstance(exc,Rejected) else 'local_storage_error'})); return 2


if __name__ == '__main__':
    raise SystemExit(main())
