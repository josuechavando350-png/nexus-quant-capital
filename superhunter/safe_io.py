"""Bounded, duplicate-key rejecting artifact IO; no network or code execution."""
from __future__ import annotations

import json
import math
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any

MAX_BYTES = 2_000_000
PENDING_MARKER = '.COMPLETE.pending'


def strict_json(raw: bytes | str) -> dict:
    if len(raw.encode("utf-8") if isinstance(raw, str) else raw) > MAX_BYTES:
        raise ValueError("JSON exceeds artifact limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError("non-finite JSON number")

    value = json.loads(raw, object_pairs_hook=unique, parse_constant=bad_constant)
    if type(value) is not dict:
        raise ValueError("JSON root must be an object")
    stack = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > 40:
            raise ValueError("JSON nesting exceeds limit")
        if isinstance(node, dict):
            stack.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, list):
            stack.extend((child, depth + 1) for child in node)
        elif isinstance(node, float) and not math.isfinite(node):
            raise ValueError("non-finite JSON number")
    return value


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def read_artifact(root: Path, relative: str) -> bytes:
    """POSIX openat walk: no symlinks, devices, path traversal or unbounded reads."""
    if type(relative) is not str or not relative or "\\" in relative or ":" in relative:
        raise ValueError("artifact: invalid relative path")
    rel = PurePosixPath(relative)
    if rel.is_absolute() or any(p in ("", ".", "..") for p in relative.split("/")):
        raise ValueError("artifact: absolute/traversal path rejected")
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise ValueError("secure artifact IO requires POSIX openat/O_NOFOLLOW")
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(root.resolve(), dir_flags)
    try:
        for part in rel.parts[:-1]:
            new = os.open(part, dir_flags, dir_fd=fd)
            os.close(fd)
            fd = new
        leaf = os.open(rel.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(leaf)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError("artifact: regular file within size limit required")
            with os.fdopen(leaf, "rb", closefd=False) as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("artifact: file too large")
            return raw
        finally:
            os.close(leaf)
    finally:
        os.close(fd)


def read_json(path: Path) -> dict:
    return strict_json(read_artifact(path.parent, path.name))


def write_new_bundle(directory: Path, files: dict[str, bytes]) -> None:
    """Prevalidate, then write a private bundle and publish its completed marker.

    A prepared marker is linked without overwrite only after its file fsync.
    Interrupted cleanup may leave both names; strict readers must reject the
    extra pending file. This does not prove power-loss durability or semantic
    success. Readers still need their own manifest, inventory and content checks.
    """
    import hashlib
    if not isinstance(files, dict) or not files:
        raise ValueError("invalid output filenames")
    payload = dict(files)
    for name, raw in payload.items():
        if (type(name) is not str or Path(name).name != name or '\\' in name or ':' in name or '\0' in name or
                name in ('', '.', '..', 'COMPLETE.json', PENDING_MARKER)):
            raise ValueError('invalid output filenames')
        if type(raw) is not bytes or len(raw) > MAX_BYTES:
            raise ValueError("invalid output bytes")
    marker = canonical({
        "schema_version": 1,
        "sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in payload.items()},
    })
    if len(marker) > MAX_BYTES:
        raise ValueError('invalid output manifest bytes')
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(mode=0o700, exist_ok=False)
    parent_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        def write(name: str, raw: bytes) -> None:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent_fd)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        for name, raw in payload.items():
            write(name, raw)
        os.fsync(parent_fd)
        write(PENDING_MARKER, marker)
        os.link(PENDING_MARKER, 'COMPLETE.json', src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd, follow_symlinks=False)
        os.unlink(PENDING_MARKER, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
