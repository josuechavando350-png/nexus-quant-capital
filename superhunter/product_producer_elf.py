"""Inventory the runtime libraries of NQC's hash-pinned Linux inventory executables."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import tempfile
from zipfile import ZipFile

from . import product_cdxgen, product_guac, product_licenses, product_notice_search, product_sbom_locations
from .product_reasoning import EvidenceError
from .product_review import TOOLS, copy_release
from .safe_io import strict_json

WHEEL_SHA = '41ff868f5328fc8e5237a9e1f4718590e0ee9180c1422b3e4948b7116ba4517c'
LIEF_VERSION = '1.0.0-d05b3499b'
PRODUCERS = {
    **{name: (repo, digest) for name, (repo, _, digest) in TOOLS.items()},
    'cdxgen': ('cdxgen/cdxgen', product_cdxgen.DIGEST),
    **{name: ('guacsec/guac', digest) for name, digest in product_guac.PINS.items()},
    'cargo-deny': ('EmbarkStudios/cargo-deny', product_licenses.DENY_SHA),
    'qdrant': ('qdrant/qdrant', product_notice_search.QDRANT_SHA),
    'tree-sitter': ('tree-sitter/tree-sitter', product_sbom_locations.BINARY_SHA),
}
ISOLATE = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']


def assess(header, native, readelf):
    if (header[:6] != b'\x7fELF\x02\x01' or len(header) < 20 or int.from_bytes(header[18:20], 'little') != 62
            or (native['class'], native['byte_order'], native['machine']) != ('ELF64', 'LSB', 'X86_64')):
        raise EvidenceError('ELF header disagrees with native runtime inventory')
    interpreters = re.findall(r'\[Requesting program interpreter: ([^\]\r\n]+)\]', readelf)
    needed = re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]\r\n]+)\]', readelf)
    loader = native['interpreter']
    if interpreters != ([loader] if loader else []) or sorted(needed) != sorted(native['needed']):
        raise EvidenceError('LIEF and readelf disagree on runtime requirements')
    return {'class': 'ELF64', 'architecture': 'x86_64', 'byte_order': 'little',
            'interpreter': loader or None, 'needed_shared_libraries': sorted(needed)}


def build(wheel, directory, supplied):
    if sys.version_info[:2] != (3, 12):
        raise EvidenceError('this optional LIEF wheel inventory requires CPython 3.12')
    with tempfile.TemporaryDirectory(prefix='nqc-producer-elf-') as temp:
        work = Path(temp)
        bin_dir = work/'bin'
        bin_dir.mkdir()
        copy_release('LIEF wheel', wheel, work/'lief.whl', WHEEL_SHA, executable=False)
        with ZipFile(work/'lief.whl') as archive:
            members = [m for m in archive.namelist() if m.startswith('lief/') and '..' not in Path(m).parts]
            archive.extractall(work/'wheel', members)
        files = {}
        for name, (repo, digest) in sorted(PRODUCERS.items()):
            source = supplied.get(name)
            if source is None and directory is not None and (directory/name).exists():
                source = directory/name
            if source is not None:
                copy_release(name, source, bin_dir/name, digest, executable=False)
                files[name] = {'repository': repo, 'binary_sha256': digest, 'bytes': (bin_dir/name).stat().st_size}
        if not files:
            raise EvidenceError('no pinned producer executable supplied for runtime inventory')
        worker = Path(__file__).with_name('product_elf_worker.py')
        env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'HOME': temp}
        run = subprocess.run([*ISOLATE, sys.executable, '-B', '-I', str(worker)], cwd=work, env=env,
                             stdin=subprocess.DEVNULL, check=True, capture_output=True, timeout=60)
        native = strict_json(run.stdout)
        if native['version'] != LIEF_VERSION or native['files'].keys() != files.keys():
            raise EvidenceError('LIEF producer inventory is incomplete')
        for name, record in files.items():
            path = bin_dir/name
            output = subprocess.run([*ISOLATE, '/usr/bin/readelf', '-W', '-l', '-d', str(path)],
                                    cwd=work, env=env, stdin=subprocess.DEVNULL, check=True,
                                    capture_output=True, timeout=20)
            with path.open('rb') as f:
                record.update(assess(f.read(20), native['files'][name], output.stdout.decode()))
    return {'version': LIEF_VERSION, 'wheel_sha256': WHEEL_SHA, 'executables': files,
            'uninspected': sorted(PRODUCERS.keys() - files.keys())}
