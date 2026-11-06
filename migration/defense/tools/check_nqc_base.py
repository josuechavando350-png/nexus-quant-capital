"""Verify the NQC integration boundary without changing the repository."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.codec import Rejected, canonical
from nqc_defense.integration import verify_nqc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    args = parser.parse_args()
    try:
        print(canonical(verify_nqc(args.repo)).decode())
        return 0
    except Rejected as exc:
        print(canonical({"verified": False, "reason": str(exc)}).decode())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
