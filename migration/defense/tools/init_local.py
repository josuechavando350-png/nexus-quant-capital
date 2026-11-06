"""Initialize a new local defense workspace around an existing artifact."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.codec import Rejected, canonical
from nqc_defense.enroll import enroll
from nqc_defense.integration import verify_nqc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--canary", required=True, help="New relative filename; its parent must exist")
    parser.add_argument("--control", type=Path, required=True, help="New directory; parent must exist")
    parser.add_argument("--nqc-repo", type=Path, help="Require exact NQC base and full isolation verification before enrollment")
    args = parser.parse_args()
    try:
        if args.nqc_repo is not None:
            verify_nqc(args.nqc_repo)
        print(canonical(enroll(args.assets, args.artifact, args.asset_id, args.canary, args.control)).decode())
    except (Rejected, OSError) as exc:
        print("Enrollment failed: " + type(exc).__name__ +
              ". Existing source bytes were not overwritten; inspect any newly created control/canary files.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
