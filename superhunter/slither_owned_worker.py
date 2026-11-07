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
import sys


def main(argv: list[str]) -> int:
    if (len(argv) != 1 or platform.system() != "Linux" or
            platform.machine() not in ("x86_64", "amd64")):
        return 2
    root = Path(argv[0])
    if (not root.is_absolute() or root.is_symlink() or
            (root / "Owned.sol").is_symlink() or (root / "solc").is_symlink() or
            not (root / "Owned.sol").is_file() or
            not (root / "solc").is_file()):
        return 2
    # Even direct invocation cannot substitute arbitrary Solidity or solc bytes.
    if (hashlib.sha256((root / "Owned.sol").read_bytes()).hexdigest() !=
            "ef5475a13e367bef34010e339c082c85383ab85e4f229cd607899f5f52ce0c64" or
            hashlib.sha256((root / "solc").read_bytes()).hexdigest() !=
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
