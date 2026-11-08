"""Review only a parent's disposable checkout copy; never execute copied code."""
from pathlib import Path
import resource
import sys


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    sys.dont_write_bytecode = True
    # Import the original reviewed implementation, never code from the copy.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from superhunter import repository_boundary as boundary
    from superhunter.safe_io import canonical
    try:
        if len(sys.argv) != 1:
            raise ValueError('FIXED_WORKER_ARGUMENTS')
        result = boundary.review(Path.cwd() / 'owned-checkout')
    except boundary.BoundaryError as error:
        # Only this known code supports the fixed experiment's diagnosis.
        reason = 'HISTORICAL_TREE_CHANGED' if str(error) == 'HISTORICAL_TREE_CHANGED' else 'BOUNDARY_OTHER_REJECTION'
        result = {'status': 'OWNED_BOUNDARY_TRIAL_REJECTED', 'reason': reason}
        code = 2
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        result = {'status': 'OWNED_BOUNDARY_TRIAL_REJECTED', 'reason': 'WORKER_INPUT_REJECTED'}
        code = 2
    else:
        code = 0
    sys.stdout.buffer.write(canonical(result))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
