"""Two-GiB entrypoint for the fixed correct-source counter-controls, not arbitrary input."""
import json
from pathlib import Path
import resource
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from superhunter import owned_correct_geth
from superhunter.privacy import PrivateArgumentParser


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (20 * 1024**2, 20 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    parser = PrivateArgumentParser(description='Fixed correct own counter-control Geth worker')
    parser.add_argument('--solc', type=Path, required=True)
    parser.add_argument('--evm', type=Path, required=True)
    parser.add_argument('--source-digest', required=True)
    parser.add_argument('--geth-fd', type=int, required=True)
    args = parser.parse_args()
    try:
        result = owned_correct_geth.execute_fixed(args.solc, args.evm, args.source_digest, args.geth_fd)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({'status': 'OWNED_CORRECT_GETH_BLOCKED'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
