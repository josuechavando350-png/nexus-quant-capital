"""Prepare the two reviewed upstream source files and the pinned Bandit wheel set."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import urlopen

from superhunter.product_score_comparison import ENGINES, lockfile
from superhunter.product_census_header import pinned
from superhunter.product_owned_source_checks import LOCK, LOCK_SHA, excerpt_files
from superhunter.product_review import ROOT
from superhunter.repository_boundary import git_object
from superhunter.safe_io import MAX_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scorers', action='store_true', help='also download the fixed DSPy and Inspect AI wheels')
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    dest = args.destination.resolve()
    if dest.exists() or dest.is_relative_to(ROOT):
        parser.error('choose a new, external directory')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        work = Path(tmp)/'assets'
        work.mkdir()
        lock = Path(tmp)/'requirements.txt'
        lock.write_bytes(pinned(ROOT, LOCK, LOCK_SHA))
        subprocess.run([sys.executable, '-m', 'pip', '--isolated', 'download', '--only-binary=:all:',
                        '--no-deps', '--require-hashes', '--dest', work, '-r', lock], check=True)
        if args.scorers:
            for name, engine in ENGINES.items():
                wheels = work/(name + '-wheels')
                wheels.mkdir()
                lock.write_bytes(pinned(ROOT, lockfile(name), engine['lock']))
                subprocess.run([sys.executable, '-m', 'pip', '--isolated', 'download', '--only-binary=:all:',
                                '--no-deps', '--require-hashes', '--dest', wheels, '-r', lock], check=True)
        for _, row, path, name, oid in excerpt_files():
            url = f"https://raw.githubusercontent.com/{row['repository']}/{row['commit']}/{path}"
            with urlopen(url, timeout=30) as response:
                raw = response.read(MAX_BYTES+1)
            if len(raw) > MAX_BYTES or git_object('blob', raw) != oid:
                raise ValueError('upstream source differs from Git')
            (work/name).write_bytes(raw)
        work.rename(dest)


if __name__ == '__main__':
    main()
