"""Offline verification of an export; no archive extraction or network access."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.codec import Rejected, decode
from nqc_defense.files import read_local
from nqc_defense.verify_export import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--policy-digest", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True, help="Trusted checkpoint stored outside the export")
    args = parser.parse_args()
    try:
        if args.key_file.lstat().st_mode & 0o077:
            raise Rejected("key_file_permissions")
        key = read_local(args.key_file.parent, args.key_file.name, 32)
        data = read_local(args.archive.parent, args.archive.name, 65 * 1024 * 1024)
        checkpoint = decode(read_local(args.checkpoint.parent, args.checkpoint.name, 4096))
        result = verify(data, key, args.policy_digest, checkpoint)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Rejected, OSError) as exc:
        print(json.dumps({"verified": False, "reason": str(exc) if isinstance(exc, Rejected) else "file_unavailable"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
