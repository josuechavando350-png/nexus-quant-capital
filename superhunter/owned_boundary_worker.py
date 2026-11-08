"""Fixed read-only review of this checkout; no target or command arguments."""
from pathlib import Path
import resource
import sys


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    sys.dont_write_bytecode = True
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    from superhunter.repository_boundary import review
    from superhunter.safe_io import canonical
    try:
        if len(sys.argv) != 1:
            raise ValueError('FIXED_WORKER_ARGUMENTS')
        result = review(root)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        sys.stdout.buffer.write(canonical({'status': 'OWNED_BOUNDARY_WORKER_BLOCKED'}))
        return 2
    sys.stdout.buffer.write(canonical(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
