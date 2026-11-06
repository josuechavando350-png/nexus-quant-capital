"""Compare two explicitly pinned authentication policies on a fixed local corpus; never apply them."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_evaluation import MAX_CORPUS, MAX_POLICY
from nqc_defense.auth_policy_comparison import MAX_COMPARISON, compare, publish_comparison, verify_comparison
from nqc_defense.codec import Rejected
from auth_evaluation import read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    run = commands.add_parser('run'); verify = commands.add_parser('verify')
    for command in (run,verify):
        command.add_argument('--corpus',type=Path,required=True)
        command.add_argument('--corpus-digest',required=True)
        for role in ('baseline','candidate'):
            command.add_argument('--'+role+'-policy',type=Path,required=True)
            command.add_argument('--'+role+'-digest',required=True)
    run.add_argument('--output',type=Path,required=True)
    verify.add_argument('--report',type=Path,required=True)
    verify.add_argument('--report-digest',required=True)
    args = parser.parse_args()
    try:
        report = compare(read(args.corpus,MAX_CORPUS),args.corpus_digest,
            read(args.baseline_policy,MAX_POLICY),args.baseline_digest,
            read(args.candidate_policy,MAX_POLICY),args.candidate_digest)
        result = (publish_comparison(args.output,report) if args.command == 'run' else
            verify_comparison(read(args.report,MAX_COMPARISON),args.report_digest,report))
        print(json.dumps(result,sort_keys=True)); return 0
    except (Rejected,OSError,sqlite3.Error) as exc:
        print(json.dumps({'verified':False,'reason':str(exc) if isinstance(exc,Rejected) else 'local_storage_error'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
