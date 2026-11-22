"""Verify separately staged Git dependencies against the product's direct source pins, offline."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from ..product_review import ROOT
from ..repository_boundary import git_object
from ..safe_io import canonical, read_artifact, strict_json
from .verify_source_materialization import (
    common_storage, expected_rows, git_directory, local_git, local_path, upstream_name,
)

RECEIPTS = {
    'report-interop': '345ca90e89adcc2a7f8e65cd637cce7d2450956a394ca9c06ca67740b1adc973',
    'evidence-contracts': '290124144e184d11bcf739886912d35be83382c6759f012d972dcd4cea91362e',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def working_blob(directory, path, mode, size):
    """Hash the working file once, treating a symlink as its literal target."""
    parts = path.split(b'/')
    require(all(part not in (b'', b'.', b'..') for part in parts), 'invalid tree path')
    with ExitStack() as handles:
        for part in parts[:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=directory)
            handles.callback(os.close, directory)
        sha256 = hashlib.sha256()
        if mode == b'120000':
            raw = os.readlink(parts[-1], dir_fd=directory)
            require(len(raw) == size, 'working symlink length differs')
            sha256.update(raw)
            return git_object('blob', raw), sha256.hexdigest(), False
        require(mode in (b'100644', b'100755'), 'unexpected Git mode')
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        stream = handles.enter_context(os.fdopen(fd, 'rb'))
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and bool(info.st_mode & stat.S_IXUSR) == (mode == b'100755'),
                'working file type or executable bit differs')
        require(info.st_size == size, 'working file length differs')
        digest = hashlib.sha1(b'blob %d\0' % info.st_size, usedforsecurity=False)
        first = stream.read(min(64, size))
        is_pointer = first.startswith(b'version https://git-lfs.github.com/spec/v1')
        digest.update(first)
        sha256.update(first)
        remaining = size - len(first)
        while remaining:
            data = stream.read(min(1024 * 1024, remaining))
            require(data, 'working file truncated during verification')
            digest.update(data)
            sha256.update(data)
            remaining -= len(data)
        require(not stream.read(1), 'working file grew during verification')
        return digest.hexdigest(), sha256.hexdigest(), is_pointer


def check_parent(sources, direct, claim):
    directory = git_directory(sources, local_path(sources, sources / direct['path']))
    commit, tree = local_git(directory, 'rev-parse', 'HEAD', 'HEAD^{tree}').decode().splitlines()
    require(commit == direct['commit'] == claim['parent_revision'] and tree == direct['tree'],
            'direct source revision differs')
    child_path, child_commit = claim['path'], claim['commit']
    entry = local_git(directory, 'ls-tree', '-z', tree, '--', child_path)
    require(entry == f'160000 commit {child_commit}\t{child_path}\0'.encode(), 'parent gitlink differs')
    modules = local_git(directory, 'rev-parse', commit + ':.gitmodules').decode().strip()
    require(modules == claim['parent_gitmodules_blob'] and
            git_object('blob', local_git(directory, 'cat-file', 'blob', modules)) == modules,
            'parent submodule declarations differ')
    raw = local_git(directory, 'config', '-z', '--no-includes', '--blob', modules, '--get-regexp',
                    r'^submodule\..*\.(path|url)$')
    entries = [line.decode().split('\n', 1) for line in raw.split(b'\0') if line]
    paths = [k[:-5] for k, v in entries if k.endswith('.path') and v == child_path]
    require(len(paths) == 1, 'ambiguous nested path')
    urls = [v for k, v in entries if k == paths[0] + '.url']
    require(len(urls) == 1 and upstream_name(urls[0]) == claim['origin'], 'parent origin differs')


def check_staging(staging, claim):
    checkout = local_path(staging, staging / claim['origin'].rsplit('/', 1)[1])
    directory = git_directory(staging, checkout)
    common_storage(staging, directory)
    origin = local_git(directory, 'config', '--local', '--no-includes', '--get', 'remote.origin.url')
    require(upstream_name(origin.decode().strip()) == claim['origin'], 'staged origin differs')
    commit, tree = local_git(directory, 'rev-parse', 'HEAD', 'HEAD^{tree}').decode().splitlines()
    require(commit == claim['commit'] and tree == claim['tree'], 'staged revision differs')
    for kind, oid in (('commit', commit), ('tree', tree)):
        require(git_object(kind, local_git(directory, 'cat-file', kind, oid)) == oid, 'object ID differs')
    files, children, notices, pointers, index = {}, {}, {}, [], []
    fd = os.open(checkout, os.O_DIRECTORY | os.O_NOFOLLOW | os.O_RDONLY)
    try:
        for line in local_git(directory, 'ls-tree', '-rlz', tree).split(b'\0'):
            if not line:
                continue
            header, path = line.split(b'\t', 1)
            mode, kind, oid, size = header.split()
            name = path.decode()
            index.append(mode + b' ' + oid + b' 0\t' + path + b'\0')
            if mode == b'160000' and kind == b'commit':
                children[name] = oid.decode()
                continue
            require(kind == b'blob', 'unexpected Git entry')
            literal, digest, is_pointer = working_blob(fd, path, mode, int(size))
            require(literal == oid.decode(), 'working file differs: ' + name)
            files[name] = [mode.decode(), literal, digest]
            if re.fullmatch(r'(LICENSE.*|NOTICE.*|COPYING.*|composer\.json)', name, re.IGNORECASE) and '/' not in name:
                notices[name] = [literal, digest]
            if is_pointer:
                pointers.append(name)
    finally:
        os.close(fd)
    require(local_git(directory, 'ls-files', '--stage', '-z') == b''.join(index), 'staged index differs')
    require(len(files) == claim['files'] and sorted({v[0] for v in files.values()}) == claim['modes'] and
            children == claim['child_gitlinks'] and pointers == claim['lfs_pointers'] and
            notices == claim['root_notices_and_manifests'] and
            hashlib.sha256(canonical(files)).hexdigest() == claim['tracked_paths_modes_blob_ids_and_sha256'],
            'recorded working-tree evidence differs')
    return len(files)


def batch_claims(batch):
    receipt = f'superhunter/product_supply/acceptance-120/{batch}-nested-checkouts.json'
    raw = read_artifact(ROOT, receipt)
    require(hashlib.sha256(raw).hexdigest() == RECEIPTS[batch], 'published receipt differs')
    claims = strict_json(raw)['records']
    require(claims and len({c['commit'] for c in claims}) == len(claims), 'distinct revisions required')
    return claims


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', required=True, choices=sorted(RECEIPTS))
    parser.add_argument('--direct-sources', required=True, type=Path)
    parser.add_argument('--staging', required=True, type=Path)
    args = parser.parse_args()
    sources, staging = args.direct_sources.resolve(strict=True), args.staging.resolve(strict=True)
    require(not (sources.is_relative_to(staging) or staging.is_relative_to(sources)), 'staging must be separate')
    direct = {row['repository']: row for row in expected_rows()}
    claims = batch_claims(args.batch)
    total = 0
    for claim in claims:
        check_parent(sources, direct[claim['parent']], claim)
        total += check_staging(staging, claim)
    print(json.dumps({'distinct_first_level_revisions': len(claims), 'tracked_files_checked': total}))


if __name__ == '__main__':
    main()
