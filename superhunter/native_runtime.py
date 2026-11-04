"""Load only byte-pinned, user-owned, non-offensive native components.

These pins preserve source identity, not historical certification. The loader
is not a plug-in API: no user-supplied paths, code, engines or modules.
"""
from __future__ import annotations

import hashlib
import sys
import threading
import types
from dataclasses import dataclass
from pathlib import Path

from .safe_io import read_artifact

ROOT = Path(__file__).resolve().parent / "native_sources"
DIABLO_COMMIT = "0c27792fba1af1f925bfff03fbcc6fd82a3791b0"
NQC_COMMIT = "16e352225ba8a6a931834c4edf3d86d9a2924b7d"
PINS = (
    ("diablo/models.py", "bd832c728e71dc18bb4e9fa76bca7b36bf714a8b", "nexus-offensive/core/models.py", DIABLO_COMMIT),
    ("diablo/audit.py", "b2f153b4f9f3157b385c47915fdae07db4888017", "nexus-offensive/core/audit.py", DIABLO_COMMIT),
    ("diablo/scope.py", "76ad323c59b60fd519d5446254662df1e8135082", "nexus-offensive/core/scope.py", DIABLO_COMMIT),
    ("nqc/capacity.py", "bbdcc5373adde03f0cad090e88bb9044aca8432a", "ci/nqc-census/rmc016_capacity_model.py", NQC_COMMIT),
)
_LOCK = threading.RLock()


def source_inventory() -> list[dict]:
    result = []
    for relative, expected, original, commit in PINS:
        raw = read_artifact(ROOT, relative)
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if actual != expected:
            raise ValueError(f"native source mismatch: {relative}")
        result.append({"path": relative, "git_blob": actual, "sha256": hashlib.sha256(raw).hexdigest(),
                       "source_path": original, "source_commit": commit,
                       "repository": "josuechavando350-png/" + ("DIABLO" if relative.startswith("diablo/") else "nexus-quant-capital")})
    return result


@dataclass(frozen=True)
class NativeComponents:
    models: types.ModuleType
    audit: types.ModuleType
    scope: types.ModuleType
    capacity: types.ModuleType
    provenance: tuple[dict, ...]


def load_components() -> NativeComponents:
    """Verify and compile the same bytes; never fetch a dependency or source."""
    with _LOCK:
        inventory = source_inventory()
        modules = []
        for pin, info in zip(PINS, inventory):
            relative, expected, _, _ = pin
            raw = read_artifact(ROOT, relative)
            if hashlib.sha256(raw).hexdigest() != info["sha256"]:
                raise ValueError("native bytes changed between verification and load")
            group, filename = relative.split("/")
            package = f"superhunter._pinned_{group}"
            if package not in sys.modules:
                shell = types.ModuleType(package)
                shell.__path__ = []  # no incidental filesystem module discovery
                sys.modules[package] = shell
            name = package + "." + filename.removesuffix(".py")
            if name not in sys.modules:
                module = types.ModuleType(name)
                module.__package__ = package
                module.__file__ = str(ROOT / relative)
                sys.modules[name] = module
                try:
                    exec(compile(raw, module.__file__, "exec"), module.__dict__)
                except BaseException:
                    sys.modules.pop(name, None)
                    raise
            modules.append(sys.modules[name])
        return NativeComponents(*modules, tuple(inventory))
