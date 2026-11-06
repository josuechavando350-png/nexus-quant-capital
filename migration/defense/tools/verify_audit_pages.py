"""Verify consecutive audit pages through an independently pinned final checkpoint."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.audit import GENESIS
from nqc_defense.audit_pages import MAX_ARCHIVE_BYTES, AuditPageVerifier
from nqc_defense.codec import Rejected, decode
from nqc_defense.files import read_local


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", type=Path, nargs="+")
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--policy-digest", required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--start", type=Path, help="Prior verified checkpoint; omit only for genesis")
    args = parser.parse_args()
    try:
        if args.key_file.lstat().st_mode & 0o077:
            raise Rejected("key_file_permissions")
        key = read_local(args.key_file.parent, args.key_file.name, 32)
        start = (decode(read_local(args.start.parent, args.start.name, 4096)) if args.start
                 else {"sequence": 0, "head": GENESIS})
        target = decode(read_local(args.target.parent, args.target.name, 4096))
        verifier = AuditPageVerifier(key, args.policy_digest, target, start)
        for path in args.archives:
            verifier.accept(read_local(path.parent, path.name, MAX_ARCHIVE_BYTES))
        result = verifier.finish()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Rejected, OSError) as exc:
        print(json.dumps({"verified": False, "reason": str(exc) if isinstance(exc, Rejected) else "file_unavailable"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
