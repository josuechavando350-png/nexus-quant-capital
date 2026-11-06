"""Evaluate pinned authentication fixtures or recompute an existing evaluation report."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_evaluation import MAX_CORPUS, MAX_POLICY, MAX_REPORT, evaluate, publish_report, verify_report
from nqc_defense.codec import Rejected
from nqc_defense.files import read_local


def read(path, maximum):
    path = path.absolute()
    return read_local(path.parent,path.name,maximum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    run = commands.add_parser('run'); verify = commands.add_parser('verify')
    for command in (run,verify):
        command.add_argument('--corpus',type=Path,required=True)
        command.add_argument('--corpus-digest',required=True)
        command.add_argument('--policy',type=Path,required=True)
        command.add_argument('--policy-digest',required=True)
    run.add_argument('--output',type=Path,required=True)
    verify.add_argument('--report',type=Path,required=True)
    verify.add_argument('--report-digest',required=True)
    args = parser.parse_args()
    try:
        report = evaluate(read(args.corpus,MAX_CORPUS),args.corpus_digest,read(args.policy,MAX_POLICY),args.policy_digest)
        result = (publish_report(args.output,report) if args.command == 'run' else
                  verify_report(read(args.report,MAX_REPORT),args.report_digest,report))
        print(json.dumps(result,sort_keys=True)); return 0
    except (Rejected,OSError,sqlite3.Error) as exc:
        print(json.dumps({'verified':False,'reason':str(exc) if isinstance(exc,Rejected) else 'local_storage_error'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
