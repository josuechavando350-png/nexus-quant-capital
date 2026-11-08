"""Bounded data-only frames for a fixed own-source worker.

Names are inventory keys, never extraction paths. No pickle, imports, commands,
network, or reviewed-source execution. Parent acquisition precedes restriction.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
import stat
import struct

from .repository_boundary import MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES

MAGIC = b'SHOWNED1'
HEADER = struct.Struct('!8sI')
ENTRY = struct.Struct('!HBI')
MAX_NAME_BYTES = 1024
MAX_FRAME_BYTES = HEADER.size + MAX_TOTAL_BYTES + MAX_FILES*(ENTRY.size + MAX_NAME_BYTES)
MODES = ('100644', '100755')
SEAL_NAMES = ('F_SEAL_WRITE', 'F_SEAL_GROW', 'F_SEAL_SHRINK', 'F_SEAL_SEAL')


class SealedInputError(ValueError):
    """Fixed diagnostics without source data or private paths."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise SealedInputError(reason)


def _name(name: str) -> bytes:
    need(type(name) is str, 'SEALED_NAME')
    try:
        raw = name.encode('utf-8')
    except UnicodeError:
        raise SealedInputError('SEALED_NAME') from None
    need(0 < len(raw) <= MAX_NAME_BYTES and not any(ord(c) < 32 or ord(c) == 127 for c in name)
         and '\\' not in name and ':' not in name and
         all(part not in ('', '.', '..') for part in name.split('/')) and
         len(name.split('/')) <= 21, 'SEALED_NAME')
    return raw


def encode(files: dict) -> bytes:
    need(type(files) is dict and 0 < len(files) <= MAX_FILES, 'SEALED_FILE_COUNT')
    need(all(type(name) is str for name in files), 'SEALED_NAME')
    rows, total = [], 0
    for name, item in sorted(files.items()):
        encoded = _name(name)
        need(type(item) is dict and set(item) == {'mode', 'bytes'} and
             item['mode'] in MODES and type(item['bytes']) is bytes, 'SEALED_ITEM')
        raw = item['bytes']
        total += len(raw)
        need(len(raw) <= MAX_FILE_BYTES and total <= MAX_TOTAL_BYTES, 'SEALED_BYTES_BUDGET')
        rows.extend((ENTRY.pack(len(encoded), MODES.index(item['mode']), len(raw)), encoded, raw))
    return HEADER.pack(MAGIC, len(files)) + b''.join(rows)


def decode(raw: bytes) -> dict:
    need(type(raw) is bytes and HEADER.size <= len(raw) <= MAX_FRAME_BYTES, 'SEALED_FRAME_SIZE')
    magic, count = HEADER.unpack_from(raw)
    need(magic == MAGIC, 'SEALED_MAGIC')
    need(0 < count <= MAX_FILES, 'SEALED_FILE_COUNT')
    files, offset, total, previous = {}, HEADER.size, 0, None
    for _ in range(count):
        need(offset + ENTRY.size <= len(raw), 'SEALED_TRUNCATED')
        name_size, mode, size = ENTRY.unpack_from(raw, offset)
        offset += ENTRY.size
        need(0 < name_size <= MAX_NAME_BYTES and mode < len(MODES), 'SEALED_ENTRY')
        total += size
        need(size <= MAX_FILE_BYTES and total <= MAX_TOTAL_BYTES, 'SEALED_BYTES_BUDGET')
        need(offset + name_size + size <= len(raw), 'SEALED_TRUNCATED')
        try:
            name = raw[offset:offset+name_size].decode('utf-8')
        except UnicodeError:
            raise SealedInputError('SEALED_NAME') from None
        _name(name)
        need(previous is None or previous < name, 'SEALED_ORDER_OR_DUPLICATE')
        previous = name
        offset += name_size
        files[name] = {'mode': MODES[mode], 'bytes': raw[offset:offset+size]}
        offset += size
    need(offset == len(raw), 'SEALED_TRAILING_BYTES')
    return files


def required_seals() -> int:
    need(all(hasattr(fcntl, name) for name in (*SEAL_NAMES, 'F_GET_SEALS', 'F_ADD_SEALS')) and
         all(hasattr(os, name) for name in ('memfd_create', 'MFD_ALLOW_SEALING', 'MFD_CLOEXEC')),
         'SEALED_PLATFORM_UNAVAILABLE')
    value = 0
    for name in SEAL_NAMES:
        value |= getattr(fcntl, name)
    return value


def inspect(descriptor: int) -> int:
    """Inspect metadata and offset only; do not read the worker's payload."""
    seals = required_seals()
    info = os.fstat(descriptor)
    need(stat.S_ISREG(info.st_mode) and HEADER.size <= info.st_size <= MAX_FRAME_BYTES,
         'SEALED_DESCRIPTOR_SIZE')
    need(fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
         'SEALED_DESCRIPTOR_READONLY')
    need(fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & seals == seals, 'SEALED_DESCRIPTOR_SEALS')
    need(os.lseek(descriptor, 0, os.SEEK_CUR) == 0, 'SEALED_DESCRIPTOR_OFFSET')
    return info.st_size


@contextmanager
def sealed_bytes(raw: bytes):
    """Yield a read-only, sealed, zero-offset own input; close both handles."""
    need(type(raw) is bytes and HEADER.size <= len(raw) <= MAX_FRAME_BYTES, 'SEALED_FRAME_SIZE')
    seals = required_seals()
    descriptor = os.memfd_create('superhunter-owned-input', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    readonly = None
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, memoryview(raw)[offset:])
            need(written > 0, 'SEALED_WRITE_PROGRESS')
            offset += written
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, seals)
        # A new open description gives the child its own offset and read mode.
        readonly = os.open(f'/proc/self/fd/{descriptor}', os.O_RDONLY | os.O_CLOEXEC)
        need(inspect(readonly) == len(raw), 'SEALED_DESCRIPTOR_SIZE')
        os.close(descriptor)
        descriptor = None
        yield readonly
    finally:
        if readonly is not None:
            os.close(readonly)
        if descriptor is not None:
            os.close(descriptor)


def read_stdin(size: int) -> bytes:
    """Read only FD 0 after restriction; require exact bytes and immediate EOF."""
    need(type(size) is int and HEADER.size <= size <= MAX_FRAME_BYTES, 'SEALED_FRAME_SIZE')
    chunks, remaining = [], size
    while remaining:
        part = os.read(0, min(65536, remaining))
        need(bool(part), 'SEALED_TRUNCATED')
        chunks.append(part)
        remaining -= len(part)
    need(os.read(0, 1) == b'', 'SEALED_TRAILING_BYTES')
    return b''.join(chunks)
