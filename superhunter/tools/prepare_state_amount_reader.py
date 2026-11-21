"""Create a hash-verified local Cosmos SDK quantity reader for repeated offline runs."""
import argparse
import os
from pathlib import Path
import tempfile

from superhunter.product_state_formats_batch import BINARY_SHA, build, need, sha, source_files


def prepare(root, go, destination):
    with tempfile.TemporaryDirectory(prefix='nqc-amount-builder-') as tmp:
        work = Path(tmp)
        build(source_files(root), work, work/'reader', Path(go).resolve())
        raw = (work/'reader').read_bytes()
        need(sha(raw) == BINARY_SHA, 'unexpected prepared binary')
        # Publish only a fully written file. A concurrent successful writer wins.
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.nqc-amount-', delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(raw)
                stream.flush()
                os.fchmod(stream.fileno(), 0o500)
                os.link(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    arguments = argparse.ArgumentParser(description=__doc__)
    for field in ('sources', 'go', 'output'):
        arguments.add_argument(field, type=Path)
    opts = arguments.parse_args()
    prepare(opts.sources, opts.go, opts.output)
