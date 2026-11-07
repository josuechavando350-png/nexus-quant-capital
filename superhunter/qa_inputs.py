"""One fixed, non-executable input prepared before bounded QA workers start.

The 64,000,001 zero bytes retain the original oversized-compiler regression.
Reading this file in a worker does not increase its 20 MiB file-write limit.
No downloaded binary, arbitrary fixture content, or executable is admitted.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat
import tempfile

ENV = 'SUPERHUNTER_QA_OVERSIZED_ZERO_INPUT'
SIZE = 64_000_001
SHA256 = '46e456b9b58dabe1e4f63d0a84a9306df12fb51be24051d91cc6d515d86e6df2'


def validate(path: Path) -> None:
    if not path.is_absolute():
        raise ValueError('QA_INPUT_NOT_ABSOLUTE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size != SIZE or
                stat.S_IMODE(before.st_mode) != 0o400 or before.st_uid != os.getuid()):
            raise ValueError('QA_INPUT_METADATA_MISMATCH')
        digest = hashlib.sha256()
        remaining = SIZE
        while remaining:
            raw = os.read(fd, min(1_000_000, remaining))
            if not raw:
                raise ValueError('QA_INPUT_TRUNCATED')
            remaining -= len(raw)
            digest.update(raw)
        after = os.fstat(fd)
        if (os.read(fd, 1) or digest.hexdigest() != SHA256 or
                (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError('QA_INPUT_CONTENT_MISMATCH')
    finally:
        os.close(fd)


@contextmanager
def oversized_zero_input():
    """Reuse the exact prepared input, or prepare it before resource limits.

    A caller already under a file-size limit must receive the parent's input.
    This function never raises a limit and never substitutes a smaller file.
    """
    inherited = os.environ.get(ENV)
    if inherited is not None:
        path = Path(inherited)
        validate(path)
        yield path
        validate(path)
        return
    with tempfile.TemporaryDirectory(prefix='superhunter-qa-input-') as temp:
        path = Path(temp).resolve()/'oversized-zero-input'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.ftruncate(fd, SIZE)
            os.fchmod(fd, 0o400)
        finally:
            os.close(fd)
        validate(path)
        yield path
        validate(path)
