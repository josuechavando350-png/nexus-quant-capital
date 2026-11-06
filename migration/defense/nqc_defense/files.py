"""Descriptor-relative local file access. No shell, network, or symlink following."""

import hashlib
import os
from pathlib import Path, PurePosixPath
import stat

from .codec import Rejected


def relative_parts(name):
    if not isinstance(name, str) or not name or len(name) > 512 or "\\" in name or "\x00" in name:
        raise Rejected("unsafe_path")
    parts = name.split("/")
    if any(p in {"", ".", ".."} for p in parts) or PurePosixPath(name).is_absolute():
        raise Rejected("unsafe_path")
    return parts


def open_parent(root, name):
    parts = relative_parts(name)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


def read_local(root, name, maximum=16 * 1024 * 1024):
    parent = fd = None
    try:
        parent, leaf = open_parent(root, name)
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise Rejected("file_type_or_size")
        chunks, size = [], 0
        while True:
            block = os.read(fd, min(65536, maximum + 1 - size))
            if not block:
                break
            size += len(block)
            if size > maximum:
                raise Rejected("file_size")
            chunks.append(block)
        after = os.fstat(fd)
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if stamp(before) != stamp(after) or size != after.st_size:
            raise Rejected("file_changed_during_read")
        return b"".join(chunks)
    except OSError as exc:
        raise Rejected("file_unavailable") from exc
    finally:
        for handle in (fd, parent):
            if handle is not None:
                os.close(handle)


def create_local(root, name, data):
    """Create only; never replace an existing asset. Parent dirs must already exist."""
    parent = fd = None
    try:
        parent, leaf = open_parent(root, name)
        fd = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
        os.fsync(parent)
    finally:
        for handle in (fd, parent):
            if handle is not None:
                os.close(handle)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def private_directory(path):
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    mode = path.lstat().st_mode
    if not stat.S_ISDIR(mode) or mode & 0o077:
        raise Rejected("state_directory_permissions")
    return path
