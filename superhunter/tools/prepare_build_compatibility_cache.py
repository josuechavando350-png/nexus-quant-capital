"""Assemble the importable Crytic wheel files for offline reuse; the compiler runs for every review."""
import argparse
import os
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from superhunter.product_build_compatibility import LOCK, LOCK_SHA
from superhunter.product_notice_ranking import install_wheels


def pack(kit, destination):
    with tempfile.TemporaryDirectory(prefix='nqc-abi-wheels-') as tmp:
        work = Path(tmp)
        env = {'HOME': tmp, 'TMPDIR': tmp, 'PATH': os.defpath, 'LANG':'C'}
        install_wheels(kit, work, env, lock_path=LOCK, lock_digest=LOCK_SHA, producer='Crytic Compile')
        library = work/'lib'
        archive = work/'lib.zip'
        with ZipFile(archive, 'w') as output:
            for path in sorted(library.rglob('*')):
                name = path.relative_to(library)
                if not path.is_file() or name.parts[0] == 'bin':
                    continue
                if name.parts[0].endswith('.dist-info') and name.name not in ('METADATA','WHEEL'):
                    continue
                info = ZipInfo(name.as_posix())
                info.compress_type = ZIP_DEFLATED
                output.writestr(info, path.read_bytes())
        destination.write_bytes(archive.read_bytes())


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kit', type=Path)
    parser.add_argument('destination', type=Path)
    opts=parser.parse_args()
    if opts.destination.exists():
        parser.error('destination must be new')
    pack(opts.kit, opts.destination)
