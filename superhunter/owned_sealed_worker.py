"""Fixed own-source integrity review, reading sealed stdin after restriction.

The parent captures source before starting this child. This worker has no
target/command arguments and never executes the source bytes it reviews.
"""
from pathlib import Path
import resource
import sys
import time

PROFILE = 'owned-sealed-boundary-review-v1'


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_AS, (256*1024**2, 256*1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (131072, 131072))
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from superhunter import (repository_boundary as boundary, owned_compute_guard as guard,
                            owned_sealed_input as sealed)
    from superhunter.safe_io import canonical
    from hashlib import sha256
    phase = 'FILTER_INSTALLATION'
    try:
        if len(sys.argv) != 1:
            raise ValueError('FIXED_WORKER_ARGUMENTS')
        proof = guard.install_sealed(Path.cwd()/'owned-compute-control')
        filter_end = time.monotonic_ns()
        phase = 'SEALED_INPUT_READ'
        raw = sealed.read_stdin(proof['stdin_bytes'])
        frame_hash = sha256(raw).hexdigest()
        files = sealed.decode(raw)
        del raw
        inventory = {name: {'mode': item['mode'], 'sha256': sha256(item['bytes']).hexdigest()}
                     for name, item in files.items()}
        input_hash = sha256(canonical(inventory)).hexdigest()
        acquisition_end = time.monotonic_ns()
        phase = 'PURE_BOUNDARY_REVIEW'
        try:
            reviewed = boundary._review_captured(files, 0)
            code = 0
        except boundary.BoundaryError as error:
            reviewed = {'status': 'REPOSITORY_BOUNDARY_BLOCKED', 'reason': str(error)}
            code = 2
        finished = time.monotonic_ns()
        response = {'schema_version': 1, 'profile': PROFILE,
                    'status': 'OWNED_SEALED_REVIEW_OBSERVED', 'input_inventory_sha256': input_hash,
                    'input_frame_sha256': frame_hash, 'filter_proof': proof, 'boundary_result': reviewed,
                    'phase_clocks': {'filter_controls_finished_monotonic_ns': filter_end,
                                     'sealed_input_finished_monotonic_ns': acquisition_end,
                                     'review_finished_monotonic_ns': finished}}
    except (OSError, ValueError, TypeError, KeyError, RecursionError, MemoryError) as error:
        response = {'schema_version': 1, 'profile': PROFILE,
                    'status': 'OWNED_SEALED_REVIEW_UNAVAILABLE', 'failed_phase': phase,
                    'reason': (str(error) if type(error) in
                               (guard.ComputeGuardError, boundary.BoundaryError, sealed.SealedInputError)
                               else 'SEALED_SYSTEM_ERROR'),
                    'unfiltered_fallback_executed': False}
        code = 3
    sys.stdout.buffer.write(canonical(response))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
