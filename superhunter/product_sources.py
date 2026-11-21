"""Verify the product's direct Git source pins without running third-party code."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from .product_review import ROOT
from .product_upstream_notices import sources
from .repository_boundary import ROOT_FILES, git_object
from .safe_io import read_artifact


def git(root, *args):
    env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0',
           'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_REPLACE_OBJECTS': '1'}
    return subprocess.check_output(['git', '--no-optional-locks', '-c', 'core.fsmonitor=false',
                                   '-c', 'core.hooksPath=/dev/null', '-C', root, *args],
                                  env=env, stderr=subprocess.PIPE, timeout=90)


def gitlinks(root, ref='HEAD'):
    # Only the superproject's committed Git tree decides which repositories are present.
    entries = {}
    for record in git(root, 'ls-tree', '-rz', ref, '--', 'upstream').split(b'\0'):
        if not record:
            continue
        meta, path = record.decode('utf-8').split('\t', 1)
        mode, kind, oid = meta.split()
        if (mode, kind) != ('160000', 'commit'):
            raise ValueError('unexpected regular file in the upstream Git tree')
        entries[path] = oid
    return entries


def indexed_links(root):
    entries = {}
    for record in git(root, 'ls-files', '--stage', '-z', '--', 'upstream').split(b'\0'):
        if record:
            fields, path = record.decode('utf-8').split('\t', 1)
            mode, oid, stage = fields.split()
            if mode != '160000' or stage != '0':
                raise ValueError('unexpected file or conflict in the upstream index')
            entries[path] = oid
    return entries


def matches_blob(root_fd, path, mode, expected):
    """Hash the bytes Git tracks, without invoking filters or following symlinks."""
    parts = path.split(b'/')
    if any(part in (b'', b'.', b'..') for part in parts):
        return False
    with ExitStack() as handles:
        parent = root_fd
        for part in parts[:-1]:
            parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            handles.callback(os.close, parent)
        if mode == b'120000':
            target = os.readlink(parts[-1], dir_fd=parent)
            digest = hashlib.sha1(b'blob %d\0' % len(target) + target, usedforsecurity=False)
        else:
            if mode not in (b'100644', b'100755'):
                return False
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            handles.callback(os.close, fd)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or bool(info.st_mode & stat.S_IXUSR) != (mode == b'100755'):
                return False
            stream = handles.enter_context(os.fdopen(fd, 'rb', closefd=False))
            digest = hashlib.sha1(b'blob %d\0' % info.st_size, usedforsecurity=False)
            remaining = info.st_size
            while remaining:
                block = stream.read(min(remaining, 1024 * 1024))
                if not block:
                    return False
                remaining -= len(block)
                digest.update(block)
            if stream.read(1):
                return False
        return digest.hexdigest().encode('ascii') == expected


def checkout_blob(folder, path, oid):
    """Compute Git's built-in checkout encoding using only committed attributes.

    The temporary repository shares the immutable objects, not the checkout's
    configuration, filters, hooks, info/attributes or index.
    """
    revision = git(folder, 'rev-parse', 'HEAD').strip()
    objects = git(folder, 'rev-parse', '--path-format=absolute', '--git-path', 'objects').strip()
    with tempfile.TemporaryDirectory(prefix='nqc-attributes-') as empty:
        env = {'PATH': os.defpath, 'HOME': empty, 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_ATTR_NOSYSTEM': '1', 'GIT_NO_LAZY_FETCH': '1',
               'GIT_ALTERNATE_OBJECT_DIRECTORIES': os.fsdecode(objects)}
        options = {'cwd': empty, 'env': env, 'stderr': subprocess.PIPE}
        subprocess.run(['git', 'init', '--quiet', '--bare', '--template='], check=True, timeout=90, **options)
        command = ['git', b'--attr-source=' + revision, 'cat-file', '--filters', b'--path=' + path, oid]
        with subprocess.Popen(command, cwd=empty, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as producer:
            try:
                with producer.stdout as contents:
                    encoded = subprocess.check_output(['git', 'hash-object', '--stdin'], stdin=contents,
                                                      timeout=90, **options)
                if producer.wait(timeout=90) != 0:
                    raise ValueError('could not reconstruct committed checkout representation')
                return encoded.strip()
            finally:
                if producer.poll() is None:
                    producer.kill()


def tracked_files_match(folder):
    # Raw diff-files can report a stat-cache miss for unchanged checkout bytes
    # after a filesystem restore or a user namespace change.
    changes = git(folder, 'diff-files', '--raw', '--no-abbrev', '--no-renames', '--no-ext-diff',
                  '--ignore-submodules=all', '-z', '--')
    if not changes:
        return True
    records = iter(changes.removesuffix(b'\0').split(b'\0'))
    root_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for meta, path in zip(records, records, strict=True):
            old_mode, new_mode, expected, _, status = meta.removeprefix(b':').split()
            if status != b'M' or old_mode != new_mode:
                return False
            if matches_blob(root_fd, path, old_mode, expected):
                continue
            if old_mode not in (b'100644', b'100755'):
                return False
            encoded = checkout_blob(folder, path, expected)
            if encoded == expected or not matches_blob(root_fd, path, old_mode, encoded):
                return False
    except OSError:
        return False
    finally:
        os.close(root_fd)
    return True


def checked_out(root, row):
    """Check one direct checkout without sharing or changing its Git index."""
    path, revision = row['path'], row['commit']
    folder = root/path
    if not (folder/'.git').is_file() and not (folder/'.git').is_dir():
        raise ValueError('submodule not initialized: ' + path)
    if git(folder, 'rev-parse', '--show-toplevel').decode().strip() != str(folder.resolve()):
        raise ValueError('submodule has the wrong working directory: ' + path)
    if git(folder, 'rev-parse', 'HEAD').decode().strip() != revision:
        raise ValueError('submodule checked out at a different revision: ' + path)
    tree = git(folder, 'rev-parse', 'HEAD^{tree}').decode().strip()
    if git(folder, 'diff-index', '--cached', '--no-ext-diff', '--ignore-submodules=all', '--name-only', '-z', 'HEAD', '--'):
        raise ValueError('submodule index differs from committed source: ' + path)
    # Ignore only nested Git links. This inventory covers direct upstream repositories.
    if not tracked_files_match(folder):
        raise ValueError('tracked submodule files differ: ' + path)
    return {**row, 'status': 'checked_out', 'tree': tree}


def verify(root, require_checkout=False, jobs=4):
    if type(jobs) is not int or not 1 <= jobs <= 8:
        raise ValueError('jobs must be an integer between 1 and 8')
    manifest = read_artifact(root, '.gitmodules')
    if (git_object('blob', manifest) != ROOT_FILES['.gitmodules']
            or git(root, 'show', 'HEAD:.gitmodules') != manifest):
        raise ValueError('submodule manifest differs from the reviewed product')
    targets = gitlinks(root)
    if indexed_links(root) != targets:
        raise ValueError('staged upstream sources differ from HEAD')
    declarations = []
    rows = []
    upstream = root/'upstream'
    if upstream.is_symlink():
        raise ValueError('unexpected symlink at upstream')
    if upstream.exists():
        for child in upstream.iterdir():
            if child.is_symlink() or not child.is_dir() or 'upstream/' + child.name not in targets:
                raise ValueError('unexpected upstream path: ' + child.name)
    catalog = sources()
    catalog_only = []
    for source in catalog:
        number, name, revision = source['id'], source['repository'], source['revision']
        path = f"upstream/{number:03}-{name.split('/')[1].lower()}"
        if path not in targets:
            catalog_only.append({'catalog_id': number, 'repository': name})
            continue
        if targets.pop(path) != revision:
            raise ValueError('Git tree and catalog revision differ: ' + path)
        declarations.append(f'[submodule "{path}"]\n\tpath = {path}\n\turl = https://github.com/{name}.git\n\tshallow = true\n')
        folder = root/path
        if folder.is_symlink():
            raise ValueError('unexpected submodule symlink: ' + path)
        row = {'catalog_id': number, 'repository': name, 'path': path, 'commit': revision, 'status': 'pinned'}
        rows.append(row)
    if targets or ''.join(declarations).encode() != manifest or len(rows) != 153:
        raise ValueError('catalog, committed gitlinks and manifest must describe the same 153 repositories')
    # Structural checks above finish before any checkout worker starts. map retains
    # catalog order, and no partial inventory escapes if any worker fails.
    if require_checkout:
        if jobs == 1:
            rows = [checked_out(root, row) for row in rows]
        else:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                rows = list(pool.map(lambda row: checked_out(root, row), rows))
    return {'count': len(rows), 'catalog_count': len(catalog), 'catalog_only_count': len(catalog_only),
            'catalog_only': catalog_only, 'status_counts': dict(Counter(row['status'] for row in rows)),
            'upstream_code_executed_by_verifier': False, 'manifest_sha256': hashlib.sha256(manifest).hexdigest(),
            'sources': rows}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-checkout', action='store_true', help='also verify each local submodule working tree')
    parser.add_argument('--jobs', type=int, choices=range(1, 9), default=4,
                        help='parallel checkout and tree checks (1-8; default: 4)')
    parser.add_argument('--inventory', action='store_true', help='audit committed manifests, LFS pointers and nested gitlinks')
    parser.add_argument('--notice-bundle', type=Path, help='verified upstream notice bundle for native license review')
    parser.add_argument('--scancode-release', type=Path, help='pinned ScanCode distribution for notice review')
    args = parser.parse_args(argv)
    if bool(args.notice_bundle) != bool(args.scancode_release) or (args.notice_bundle and not args.inventory):
        parser.error('notice review requires --inventory, --notice-bundle and --scancode-release together')
    try:
        if args.inventory:
            from .product_source_audit import inventory
            result = inventory(ROOT, args.notice_bundle, args.scancode_release, jobs=args.jobs)
        else:
            result = verify(ROOT, args.require_checkout, jobs=args.jobs)
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0
