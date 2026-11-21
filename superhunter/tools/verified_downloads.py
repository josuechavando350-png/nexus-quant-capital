"""Reuse pinned download bytes; execution receipts are never cached here."""
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile


MAX_ASSET_BYTES = 512 * 1024**2


def copy_verified(source, target, digest):
    """Copy a regular file into a new destination, checking the bytes copied."""
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('invalid download digest')
    source, target = Path(source), Path(target)
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ASSET_BYTES:
            raise ValueError('download must be a bounded regular file')
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.verified-', delete=False) as out:
            temporary = Path(out.name)
            try:
                total, observed = 0, hashlib.sha256()
                with os.fdopen(fd, 'rb', closefd=False) as inp:
                    while chunk := inp.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_ASSET_BYTES:
                            raise ValueError('download exceeds size limit')
                        observed.update(chunk)
                        out.write(chunk)
                if observed.hexdigest() != digest:
                    raise ValueError('download digest mismatch')
                out.flush()
                os.fsync(out.fileno())
                # Publish only complete verified bytes, without overwriting a target.
                os.link(temporary, target)
            finally:
                temporary.unlink()
    finally:
        os.close(fd)


def acquire(target, digest, download, cache=None):
    """Download once or verify a cached blob; concurrent writers publish atomically.

    `download` writes a new staging file. The session receives its own copy so
    editing an extracted/session input cannot change the shared cached object.
    A corrupt or linked cache entry is an error, never accepted as a cache hit.
    """
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('invalid download digest')
    target = Path(target)
    if target.exists() or target.is_symlink():
        raise ValueError('download destination already exists')
    if cache is not None:
        cache = Path(cache)
        if cache.is_symlink():
            raise ValueError('download cache cannot be a symlink')
        cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        entry = cache/digest
        try:
            copy_verified(entry, target, digest)
        except FileNotFoundError:
            pass
        else:
            return
    with tempfile.TemporaryDirectory(prefix='.download-', dir=cache or target.parent) as tmp:
        staging = Path(tmp)/'asset'
        download(staging)
        copy_verified(staging, target, digest)
        if cache is not None:
            try:
                os.link(staging, entry, follow_symlinks=False)
            except FileExistsError:
                # Another writer won. Every subsequent reader verifies its bytes.
                pass
