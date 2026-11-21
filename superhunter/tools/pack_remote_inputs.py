"""Package evidence from verified upstream Git commit objects and their declarative root blobs."""
import argparse
import base64
import sys
import zlib

from superhunter.product_remote_roots import manifests, member_name, roots
from superhunter.repository_boundary import git_object
from superhunter.safe_io import canonical, read_artifact
from superhunter.tools.audit_tree_metadata import command
from pathlib import Path


def compress(data):
    return base64.b64encode(zlib.compress(data, 9)).decode('ascii')


def pack(metadata, declarations):
    rows = []
    for row, tree in roots():
        raw = command(metadata/str(row['id']), 'cat-file', 'commit', row['commit'])
        if git_object('commit', raw) != row['commit'] or raw.splitlines()[0] != b'tree ' + row['tree'].encode():
            raise ValueError('invalid commit object')
        files = {}
        for name, oid in manifests(tree).items():
            data = read_artifact(declarations, member_name(row['id'], name))
            if git_object('blob', data) != oid:
                raise ValueError('root declaration differs from Git')
            files[name] = compress(data)
        rows.append({'id': row['id'], 'commit_object': compress(raw), 'declarations': files})
    return {'version': 1, 'codec': 'zlib-base64', 'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('metadata', type=Path, help='external bare Git tree cache')
    parser.add_argument('declarations', type=Path, help='verified root declaration cache')
    args = parser.parse_args()
    sys.stdout.buffer.write(canonical(pack(args.metadata, args.declarations)))


if __name__ == '__main__':
    main()
