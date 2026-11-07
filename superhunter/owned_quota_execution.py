"""Dedicated fixed quota executor; historical captured engine remains unchanged.

Reuse only a caller-owned sealed image whose bytes match the pinned Geth image.
This private transport is consumed only by the closed OWNED quota corpus.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

from .evm_execution import PIN, GAS, EVMError, need, sha, parse_run
from . import owned_process
from .safe_io import canonical

ROOT = Path(__file__).resolve().parent


def _run_bounded(command, root, out, err, fd) -> int:
    """Keep the typed timeout contract of this fixed internal transport."""
    try:
        return owned_process.run(command, stdout=out, stderr=err,
            cwd=root, env={'LANG': 'C', 'LC_ALL': 'C'}, pass_fds=(fd,), timeout=15).returncode
    except subprocess.TimeoutExpired:
        raise EVMError('EVM_PROCESS_TIMEOUT') from None


@contextmanager
def _execution_image(image: bytes, sealed_fd: int | None):
    """Reuse an immutable caller-owned image without rewriting a large memfd.

    The caller of this helper has checked the official Geth byte hash. Every
    reuse checks descriptor seals, size and bytes; it never executes a pathname.
    Ownership stays with the caller and the descriptor is not closed here.
    """
    need(type(sealed_fd) is int and sealed_fd >= 0,'EVM_SEALED_DESCRIPTOR')
    info = os.fstat(sealed_fd)
    seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
    need(stat.S_ISREG(info.st_mode) and info.st_size == len(image) and
         fcntl.fcntl(sealed_fd,fcntl.F_GET_SEALS) & seals == seals,'EVM_IMAGE_NOT_SEALED')
    need(sha(os.pread(sealed_fd,len(image)+1,0)) == sha(image),'EVM_SEALED_IMAGE_MISMATCH')
    yield sealed_fd


def run(image: bytes, *, prestate: dict, creation: str | None = None,
         calldata: str = '', gas: int = GAS, sealed_fd: int | None = None) -> dict:
    """Internal fixed-image process boundary, not a public arbitrary EVM runner."""
    need(type(gas) is int and gas in (GAS, 1), 'GAS_PROFILE')
    need(sha(image) == PIN['sha256'], 'EVM_BINARY_HASH')
    need(prestate.get('gasLimit') == hex(gas), 'GENESIS_GAS_DISAGREEMENT')
    mode = 'create' if creation is not None else 'call'
    need((mode == 'create' and type(creation) is str and 0 < len(creation) <= 64000 and
          re.fullmatch('[0-9a-f]+', creation) is not None and len(creation) % 2 == 0) or
         (mode == 'call' and re.fullmatch('[0-9a-f]{72}', calldata) is not None), 'EVM_CALL_PROFILE')
    with _execution_image(image,sealed_fd) as fd, tempfile.TemporaryDirectory(prefix='sh-evm-fixed-') as tmp:
        root = Path(tmp)
        (root/'prestate.json').write_bytes(canonical(prestate))
        if creation is not None:
            (root/'creation.hex').write_text(creation)
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            command = [sys.executable, '-I', '-B', str(ROOT/'owned_quota_evm_worker.py'), mode, str(fd),
                       '-' if mode == 'create' else calldata, str(gas)]
            rc = _run_bounded(command, root, out, err, fd)
            need(out.seek(0, os.SEEK_END) < 2_000_000 and err.seek(0, os.SEEK_END) < 2_000_000, 'EVM_OUTPUT_LIMIT')
            out.seek(0); err.seek(0)
            stdout, stderr = out.read(), err.read()
            need(rc == 0 and not stderr, 'EVM_PROCESS_FAILED')
    parsed = parse_run(stdout)
    return {'prestate_sha256': sha(canonical(prestate)), 'mode': mode, 'gas_limit': gas,
            'calldata': calldata, 'stdout_utf8': stdout.decode(), 'stderr_utf8': '', 'observed': parsed}

