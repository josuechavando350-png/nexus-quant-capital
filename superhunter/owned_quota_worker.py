"""Resource-limited worker for the closed quota corpus only."""
from pathlib import Path
import json
import resource
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

from superhunter.owned_quota_review import execute_native
from superhunter.privacy import PrivateArgumentParser


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CPU,(90,90))
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(20*1024**2,20*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    p = PrivateArgumentParser(description='Fixed owned quota worker')
    p.add_argument('--solc',type=Path,required=True); p.add_argument('--evm',type=Path,required=True)
    p.add_argument('--source-digest',required=True)
    p.add_argument('--geth-fd',type=int,required=True)
    args = p.parse_args()
    try:
        print(json.dumps(execute_native(args.solc,args.evm,args.source_digest,args.geth_fd),sort_keys=True)); return 0
    except Exception:
        print(json.dumps({'status':'OWNED_QUOTA_WORKER_BLOCKED'})); return 2


if __name__ == '__main__':
    raise SystemExit(main())
