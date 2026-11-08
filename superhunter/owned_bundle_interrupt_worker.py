"""Fixed local IO cut points; real writes/fsync and SIGKILL of this process only.

Instrumentation selects when to stop the real writer. It is not a power-loss
test and does not alter the bytes the writer was asked to persist.
"""
from pathlib import Path
import json
import os
import resource
import signal
import sys

MODES = ('clean', 'payload-synced', 'marker-half', 'marker-synced', 'marker-linked')


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from superhunter import safe_io, owned_capture
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        print(json.dumps({'state': 'FIXED_INTERRUPT_MODE_REQUIRED'})); return 2
    mode = sys.argv[1]; out = Path.cwd() / 'bundle'
    owned_capture._path(out, new=True)
    pending = getattr(safe_io, 'PENDING_MARKER', '.COMPLETE.pending')
    payload = {'first.json': safe_io.canonical({'profile': 'owned-write-interruption-v1', 'part': 1}),
               'second.bin': b'OWNED_LOCAL_PAYLOAD\n' * 4096}
    original_open, original_fdopen, original_fsync, original_link = os.open, os.fdopen, os.fsync, os.link
    descriptors = {}

    def stop():
        os.kill(os.getpid(), signal.SIGKILL)

    def opened(path, *args, **kwargs):
        fd = original_open(path, *args, **kwargs)
        descriptors[fd] = Path(path).name
        return fd

    class HalfMarker:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def write(self, raw):
            self.stream.write(raw[:max(1, len(raw) // 2)])
            self.stream.flush(); original_fsync(self.stream.fileno()); stop()

    def fdopened(fd, *args, **kwargs):
        stream = original_fdopen(fd, *args, **kwargs)
        if mode == 'marker-half' and descriptors.get(fd) in (pending, 'COMPLETE.json'):
            return HalfMarker(stream)
        return stream

    def synced(fd):
        original_fsync(fd)
        if ((mode == 'payload-synced' and descriptors.get(fd) == 'first.json') or
                (mode == 'marker-synced' and descriptors.get(fd) in (pending, 'COMPLETE.json'))):
            stop()

    def linked(*args, **kwargs):
        result = original_link(*args, **kwargs)
        if mode == 'marker-linked': stop()
        return result

    os.open, os.fdopen, os.fsync, os.link = opened, fdopened, synced, linked
    try:
        safe_io.write_new_bundle(out, payload)
    finally:
        os.open, os.fdopen, os.fsync, os.link = original_open, original_fdopen, original_fsync, original_link
    print(json.dumps({'state': 'FIXED_WRITE_COMPLETED'})); return 0


if __name__ == '__main__':
    raise SystemExit(main())
