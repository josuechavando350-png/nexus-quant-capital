"""Strict offline serialization and pinned-source loading; no network or signing."""
from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from types import ModuleType


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def strict_json(raw: bytes) -> object:
    def pairs(items: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key: " + key)
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError("nonfinite_json_number: " + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject_constant)


def read_regular(path: Path, limit: int = 1_048_576) -> bytes:
    """Reject symlinks in the supplied path, special files and oversized inputs."""
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("symlink_input: " + str(path))
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError("nonregular_input: " + str(path))
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("input_too_large: " + str(path))
    return raw


def load_pinned_python(path: Path, expected_blob: str, name: str) -> ModuleType:
    """Execute precisely the bytes verified, never reopen a different source file."""
    raw = read_regular(path)
    if git_blob(raw) != expected_blob:
        raise ValueError("pinned_source_mismatch: " + str(path))
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module
