"""Local evidence-bound review; credentials are read from private files, never command arguments."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.case_evidence import MAX_BUNDLE
from nqc_defense.case_review import CaseReview
from nqc_defense.codec import Rejected, decode, fields
from nqc_defense.files import read_local
from nqc_defense.operations import OperationsStore
from nqc_defense.review_policy import ReviewPolicy, read_credential


def read(path, maximum):
    path = Path(path).absolute()
    return read_local(path.parent, path.name, maximum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init-policy")
    init.add_argument("--policy-root", type=Path, required=True)
    init.add_argument("--grants-file", type=Path, required=True)
    view = commands.add_parser("view")
    act = commands.add_parser("act")
    for command in (view, act):
        command.add_argument("--operations-root", type=Path, required=True)
        command.add_argument("--policy-root", type=Path, required=True)
        command.add_argument("--policy-digest", required=True)
        command.add_argument("--actor", required=True)
        command.add_argument("--credential-file", type=Path, required=True)
        command.add_argument("--tenant", required=True)
        command.add_argument("--asset", required=True)
        command.add_argument("--case-id", required=True)
        command.add_argument("--credential-checkpoint", type=Path)
    view.add_argument("--expected", type=Path)
    view.add_argument("--after", type=int, default=0)
    view.add_argument("--limit", type=int, default=100)
    act.add_argument("--request-file", type=Path, required=True)
    act.add_argument("--bundle-file", type=Path, required=True)
    act.add_argument("--bundle-digest", required=True)
    act.add_argument("--case-digest", required=True)
    act.add_argument("--config-digest", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init-policy":
            policy = ReviewPolicy.create(args.policy_root, decode(read(args.grants_file, 32768), max_bytes=32768))
            result = {"created": True, "policy_digest": policy.digest, "credential_files_created": len(policy.value["grants"])}
        else:
            policy = ReviewPolicy(args.policy_root, args.policy_digest)
            credential = read_credential(args.credential_file)
            review = CaseReview(OperationsStore(args.operations_root), policy)
            credentials = decode(read(args.credential_checkpoint, 4096), max_bytes=4096) if args.credential_checkpoint else None
            if args.command == "view":
                expected = decode(read(args.expected, 4096), max_bytes=4096) if args.expected else None
                result = review.view(args.actor, credential, args.tenant, args.asset, args.case_id,
                                     expected=expected, after=args.after, limit=args.limit, expected_credentials=credentials)
            else:
                request = decode(read(args.request_file, 16384), max_bytes=16384)
                fields(request, ("action", "reason", "request_id", "expected", "verdict"))
                result = review.apply(args.actor, credential, args.tenant, args.asset, args.case_id,
                                      request["action"], request["reason"], request["request_id"], request["expected"],
                                      read(args.bundle_file, MAX_BUNDLE), args.bundle_digest, args.case_digest,
                                      args.config_digest, verdict=request["verdict"], expected_credentials=credentials)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Rejected, OSError, sqlite3.Error) as exc:
        print(json.dumps({"success": False, "reason": str(exc) if isinstance(exc, Rejected) else "local_storage_error"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
