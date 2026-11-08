"""Fixed own-copy review: acquire twice, restrict syscalls, compute in memory.

No target or command arguments. Reviewed source bytes are data, never imported
or executed. Filter failure has no unfiltered-computation fallback.
"""
from pathlib import Path
import resource
import sys
import time


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_AS, (256*1024**2, 256*1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (131072, 131072))
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from superhunter import repository_boundary as boundary, owned_compute_guard as guard
    from superhunter.safe_io import canonical
    from hashlib import sha256
    phase = 'INPUT_ACQUISITION'
    try:
        if len(sys.argv) != 1:
            raise ValueError('FIXED_WORKER_ARGUMENTS')
        root = Path.cwd()/'owned-checkout'
        files, ignored = boundary._capture(root)
        after, ignored_after = boundary._capture(root)
        boundary.need(files == after and ignored == ignored_after == 0, 'RESTRICTED_INPUT_CHANGED')
        del after
        inventory = {name: {'mode': item['mode'], 'sha256': sha256(item['bytes']).hexdigest()}
                     for name, item in files.items()}
        input_hash = sha256(canonical(inventory)).hexdigest()
        acquisition_end = time.monotonic_ns()
        phase = 'FILTER_INSTALLATION'
        proof = guard.install(Path.cwd()/'owned-compute-control')
        filter_end = time.monotonic_ns()
        phase = 'PURE_BOUNDARY_REVIEW'
        try:
            reviewed = boundary._review_captured(files, ignored)
            code = 0
        except boundary.BoundaryError as error:
            reviewed = {'status': 'REPOSITORY_BOUNDARY_BLOCKED', 'reason': str(error)}
            code = 2
        finished = time.monotonic_ns()
        response = {'schema_version': 1, 'profile': 'owned-preloaded-boundary-review-v1',
                    'status': 'OWNED_RESTRICTED_REVIEW_OBSERVED', 'input_inventory_sha256': input_hash,
                    'filter_proof': proof, 'boundary_result': reviewed,
                    'phase_clocks': {'input_capture_finished_monotonic_ns': acquisition_end,
                                     'filter_controls_finished_monotonic_ns': filter_end,
                                     'review_finished_monotonic_ns': finished}}
    except (OSError, ValueError, TypeError, KeyError, RecursionError, MemoryError) as error:
        response = {'schema_version': 1, 'profile': 'owned-preloaded-boundary-review-v1',
                    'status': 'OWNED_RESTRICTED_REVIEW_UNAVAILABLE', 'failed_phase': phase,
                    'reason': (str(error) if type(error) in (guard.ComputeGuardError, boundary.BoundaryError)
                               else 'RESTRICTED_SYSTEM_ERROR'),
                    'unfiltered_fallback_executed': False}
        code = 3
    sys.stdout.buffer.write(canonical(response))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
