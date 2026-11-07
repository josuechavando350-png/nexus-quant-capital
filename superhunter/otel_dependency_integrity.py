"""Check the fixed optional SDK's installed files before importing its code.

Pins originate in reviewed wheel bytes, never in installed RECORD claims.
This is file integrity, not authentication of a producer or process memory.
"""
from importlib.metadata import distribution
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import sys

from .otel_dependency_pins import PINS

MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES = 2048, 32_000_000, 64_000_000


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def expected_identity() -> dict:
    return {name: {'version': pin['version'], 'wheel_sha256': pin['wheel_sha256'],
                   'runtime_sha256': pin['runtime_sha256'],
                   'metadata_sha256': pin['metadata_sha256'],
                   'runtime_files': len(pin['runtime_files'])}
            for name, pin in sorted(PINS.items())}


def _regular_hash(path: Path, budget: list[int]) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= MAX_FILE_BYTES,
             'OTEL_DEPENDENCY_FILE')
        budget[0] += before.st_size
        need(budget[0] <= MAX_TOTAL_BYTES, 'OTEL_DEPENDENCY_BYTE_BUDGET')
        digest, remaining = hashlib.sha256(), before.st_size
        while remaining:
            raw = os.read(fd, min(1_000_000, remaining))
            need(bool(raw), 'OTEL_DEPENDENCY_TRUNCATED')
            remaining -= len(raw); digest.update(raw)
        after = os.fstat(fd)
        need(not os.read(fd, 1) and
             (before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
             (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
             'OTEL_DEPENDENCY_CHANGED_DURING_READ')
        return digest.hexdigest()
    finally:
        os.close(fd)


def _inventory(base: Path) -> dict:
    """Capture only pinned package roots, including unexpected shadow modules."""
    expected = set()
    metadata = set()
    for pin in PINS.values():
        expected.update(pin['runtime_files']); metadata.add(pin['metadata_path'])
    for name in expected | metadata:
        parts = Path(name).parts
        need(parts and not Path(name).is_absolute() and '..' not in parts and len(parts) <= 20,
             'OTEL_DEPENDENCY_PIN_PATH')
    roots = {Path(name).parts[0] for name in expected}
    stems = {name.split('.')[0] for name in roots}
    # A native module or package may shadow a pinned top-level .py file; include
    # all sibling spellings of each package root, not just entries in RECORD.
    selected = []
    for index, entry in enumerate(base.iterdir()):
        need(index < MAX_FILES, 'OTEL_DEPENDENCY_DIRECTORY_BUDGET')
        if entry.name.split('.')[0] in stems:
            selected.append(entry)
    found, budget, directories, caches = {}, [0], [0], [0]

    def walk(path: Path) -> None:
        info = path.lstat()
        need(not stat.S_ISLNK(info.st_mode), 'OTEL_DEPENDENCY_SYMLINK')
        if stat.S_ISDIR(info.st_mode):
            directories[0] += 1
            need(directories[0] <= MAX_FILES and len(path.relative_to(base).parts) <= 20,
                 'OTEL_DEPENDENCY_DIRECTORY_BUDGET')
            for child in path.iterdir():
                if path.name == '__pycache__':
                    caches[0] += 1
                    need(caches[0] <= MAX_FILES, 'OTEL_DEPENDENCY_CACHE_BUDGET')
                    need(child.is_file() and not child.is_symlink() and child.suffix == '.pyc',
                         'OTEL_DEPENDENCY_CACHE_PAYLOAD')
                    continue  # Acceptance starts with a fresh private cache prefix.
                walk(child)
        else:
            name = path.relative_to(base).as_posix()
            need(len(found) < MAX_FILES and name in expected, 'OTEL_DEPENDENCY_UNEXPECTED_FILE')
            found[name] = _regular_hash(path, budget)
    for root in sorted(selected):
        walk(root)
    need(set(found) == expected, 'OTEL_DEPENDENCY_INVENTORY')
    for name in sorted(metadata):
        path = base/name
        for parent in path.parents:
            if parent == base:
                break
            need(not parent.is_symlink(), 'OTEL_DEPENDENCY_SYMLINK')
        found[name] = _regular_hash(path, budget)
    return found


def verify_dependencies() -> dict:
    need(platform.system() == 'Linux' and platform.machine() == 'x86_64' and
         sys.version_info[:2] == (3, 12), 'OTEL_DEPENDENCY_PLATFORM')
    roots = set()
    for name, pin in PINS.items():
        dist = distribution(name)
        need(dist.version == pin['version'], 'OTEL_DEPENDENCY_VERSION')
        root = Path(dist.locate_file(''))
        need(root.is_absolute() and root.is_dir() and root.resolve() == root,
             'OTEL_DEPENDENCY_ROOT')
        roots.add(root)
    need(len(roots) == 1, 'OTEL_DEPENDENCY_MIXED_ROOTS')
    root = roots.pop()
    before = _inventory(root)
    for pin in PINS.values():
        need(_digest({name: before[name] for name in pin['runtime_files']}) == pin['runtime_sha256'] and
             before[pin['metadata_path']] == pin['metadata_sha256'], 'OTEL_DEPENDENCY_BYTES')
    need(_inventory(root) == before, 'OTEL_DEPENDENCY_CHANGED_DURING_REVIEW')
    return expected_identity()
