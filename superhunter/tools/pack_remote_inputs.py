"""Package reviewed Git inputs or restore the fixed CycloneDX and GUAC inventory files."""
import argparse
import base64
import ctypes
import hashlib
import os
import secrets
import shutil
import stat
from contextlib import ExitStack
import sys
import zlib

from superhunter.product_remote_roots import manifests, member_name, roots
from superhunter.repository_boundary import git_object
from superhunter.safe_io import canonical, read_artifact, strict_json
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


INVENTORY_FILE = 'product_supply/fixed-cdxgen-guac-inputs.json'
INVENTORY_SHA256 = '943ca6c8acc2612bc90951f02a88fc37ee1700c239891720812c401b0cd1fedc'
INVENTORY_NAMES = {
    'cdx': ('COMPLETE.json', 'census.cdx.json', 'custody.cdx.json', 'inventory.json',
            'local-lab.cdx.json', 'otel-qa.cdx.json', 'owned-cross-evm.cdx.json',
            'owned-slither.cdx.json', 'owned-spec-evm.cdx.json'),
    'guac': ('COMPLETE.json', 'comparison.json', 'guac.json'),
}
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def inventory_bytes():
    raw = read_artifact(Path(__file__).resolve().parents[1], INVENTORY_FILE)
    if len(raw) != 19880 or hashlib.sha256(raw).hexdigest() != INVENTORY_SHA256:
        raise ValueError('fixed inventory package differs')
    archive = strict_json(raw)
    paths = {f'{group}/{name}' for group, names in INVENTORY_NAMES.items() for name in names}
    if archive['schema_version'] != 1 or set(archive['files']) != paths:
        raise ValueError('fixed inventory filenames differ')
    result = {}
    for path, item in archive['files'].items():
        size = item['bytes']
        if type(size) is not int or not 0 < size <= 47038:
            raise ValueError('fixed inventory member size out of range')
        compressed = base64.b64decode(item['zlib_base64'], validate=True)
        stream = zlib.decompressobj()
        data = stream.decompress(compressed, size + 1)
        if (len(data) != size or not stream.eof or stream.unused_data or stream.unconsumed_tail
                or hashlib.sha256(data).hexdigest() != item['sha256']):
            raise ValueError('fixed inventory member differs')
        result[path] = data
    if sum(map(len, result.values())) != 106246:
        raise ValueError('fixed inventory total size differs')
    return result


def directory_fd(path, handles):
    if '..' in path.parts:
        raise ValueError('parent traversal in directory path')
    fd = os.open('/' if path.is_absolute() else '.', DIRECTORY)
    handles.callback(os.close, fd)
    for part in path.parts[int(path.is_absolute()):]:
        fd = os.open(part, DIRECTORY, dir_fd=fd)
        handles.callback(os.close, fd)
    return fd


def restore_inventory(destination, *, check=False):
    data = inventory_bytes()
    with ExitStack() as handles:
        if check:
            source = directory_fd(destination, handles)
            if set(os.listdir(source)) != set(INVENTORY_NAMES):
                raise ValueError('inventory group set differs')
            for group, names in INVENTORY_NAMES.items():
                folder = os.open(group, DIRECTORY, dir_fd=source)
                handles.callback(os.close, folder)
                if set(os.listdir(folder)) != set(names):
                    raise ValueError('inventory file set differs')
                for name in names:
                    expected = data[f'{group}/{name}']
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
                    try:
                        info = os.fstat(fd)
                        if not stat.S_ISREG(info.st_mode) or info.st_size != len(expected):
                            raise ValueError('inventory member type or size differs')
                        with os.fdopen(fd, 'rb', closefd=False) as entry:
                            if entry.read(len(expected) + 1) != expected:
                                raise ValueError('inventory content differs')
                    finally:
                        os.close(fd)
            return
        if not destination.name or destination.name == '..':
            raise ValueError('destination must be a new directory')
        parent = directory_fd(destination.parent, handles)
        staged = '.nqc-inventory-' + secrets.token_hex(12)
        os.mkdir(staged, 0o700, dir_fd=parent)
        staged_fd = os.open(staged, DIRECTORY, dir_fd=parent)
        handles.callback(os.close, staged_fd)
        try:
            for group, names in INVENTORY_NAMES.items():
                os.mkdir(group, 0o700, dir_fd=staged_fd)
                folder = os.open(group, DIRECTORY, dir_fd=staged_fd)
                handles.callback(os.close, folder)
                for name in names:
                    fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY,
                                 0o600, dir_fd=folder)
                    with os.fdopen(fd, 'wb') as output:
                        output.write(data[f'{group}/{name}'])
            # Linux RENAME_NOREPLACE publishes the whole directory and never replaces
            # an existing file, empty directory or symbolic link at the destination.
            rename = ctypes.CDLL(None, use_errno=True).renameat2
            if rename(parent, os.fsencode(staged), parent, os.fsencode(destination.name), 1) != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error))
        except BaseException:
            shutil.rmtree(staged, dir_fd=parent)
            raise


def main():
    if sys.argv[1:2] in (['--restore-inventory'], ['--check-inventory']):
        parser = argparse.ArgumentParser(description='Restore or verify the twelve fixed NQC inventory inputs on Linux.')
        modes = parser.add_mutually_exclusive_group(required=True)
        modes.add_argument('--restore-inventory', type=Path, metavar='NEW_DIRECTORY')
        modes.add_argument('--check-inventory', type=Path, metavar='DIRECTORY')
        args = parser.parse_args()
        try:
            restore_inventory(args.restore_inventory or args.check_inventory,
                              check=args.check_inventory is not None)
        except (OSError, ValueError) as exc:
            parser.exit(2, f'Inventory verification failed: {exc}\n')
        print('12 inventory files verified')
        return
    parser = argparse.ArgumentParser(description=__doc__,
                epilog='Also accepts --restore-inventory NEW_DIRECTORY or --check-inventory DIRECTORY.')
    parser.add_argument('metadata', type=Path, help='external bare Git tree cache')
    parser.add_argument('declarations', type=Path, help='verified root declaration cache')
    args = parser.parse_args()
    sys.stdout.buffer.write(canonical(pack(args.metadata, args.declarations)))


if __name__ == '__main__':
    main()
