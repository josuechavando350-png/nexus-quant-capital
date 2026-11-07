"""Fixed, local Slither worker under the owned session-group supervisor.

Only the immutable Owned.sol fixture is accepted; no target URL, RPC endpoint,
arbitrary path, shell or plug-in is passed to Slither by this launcher.
This bounds CPU/address-space/output, NOT egress or host sandbox isolation.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import resource
import stat
import sys


def _file_sha256(path: Path, maximum: int) -> str | None:
    """Hash a bounded regular file without following a symlink or loading it all."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            return None
        count = 0
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as stream:
            while True:
                block = stream.read(min(1024 * 1024, maximum + 1 - count))
                if not block:
                    break
                count += len(block)
                if count > maximum:
                    return None
                digest.update(block)
        return digest.hexdigest() if count == info.st_size else None
    except (OSError, ValueError):
        return None
    finally:
        os.close(fd)


def main(argv: list[str]) -> int:
    if (len(argv) not in (1, 2) or platform.system() != "Linux" or
            platform.machine() not in ("x86_64", "amd64")):
        return 2
    mode = "positive" if len(argv) == 1 else argv[1]
    if mode not in ("positive", "clean", "comparison"):
        return 2
    root = Path(argv[0])
    if (not root.is_absolute() or root.is_symlink() or
            (root / "Owned.sol").is_symlink() or (root / "solc").is_symlink() or
            not (root / "Owned.sol").is_file() or
            not (root / "solc").is_file()):
        return 2
    # Even direct invocation cannot substitute arbitrary Solidity or solc bytes.
    source_sha256 = {
        "positive": "ef5475a13e367bef34010e339c082c85383ab85e4f229cd607899f5f52ce0c64",
        "clean": "f4435d614ec0d890f56f06c6250bba4a60152255fa3f8d5ceec13952f9aba0f1",
        "comparison": "45e77d6d43ee7a13720323e48ed103e64447013c705af58f53e824ae3807df92",
    }[mode]
    if (_file_sha256(root / "Owned.sol", 4096) != source_sha256 or
            _file_sha256(root / "solc", 64_000_000) !=
            "f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7"):
        return 2
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
    resource.setrlimit(resource.RLIMIT_NOFILE, (96, 96))
    os.chdir(root)
    command = [sys.executable, "-I", "-B", "-m", "slither",
               "Owned.sol", "--solc", str(root / "solc"),
               "--detect", "tx-origin", "--fail-none",
               "--disable-color", "--json", "slither.json"]
    os.execv(sys.executable, command)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
