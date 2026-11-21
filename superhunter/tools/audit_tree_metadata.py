"""Verify reachable Git trees on the fixed 47 revisions without acquiring any source blobs."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import quote
from urllib.request import urlopen

from superhunter.product_remote_roots import roots
from superhunter.product_source_audit import MANIFESTS
from superhunter.product_review import ROOT, sha
from superhunter.repository_boundary import git_object
from superhunter.safe_io import MAX_BYTES, canonical, read_artifact

FORMATS = MANIFESTS | {'build.gradle', 'build.gradle.kts', 'gradle.properties', 'packages.config',
                       'Directory.Packages.props', 'requirements-dev.txt', 'Pipfile', 'Gemfile',
                       'Package.swift', 'mix.exs', 'mix.lock', 'project.clj', 'deps.edn', 'pubspec.yaml'}


def command(directory, *argv):
    env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0', 'GIT_NO_REPLACE_OBJECTS': '1'}
    return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.file.allow=never',
                                    '-C', directory, *argv], env=env, stderr=subprocess.PIPE, timeout=180)


def attributes(row, path, oid, cache, fetch):
    name = oid + '.txt'
    if fetch and not (cache/name).exists():
        url = 'https://raw.githubusercontent.com/{}/{}/{}'.format(row['repository'], row['commit'], quote(path))
        with urlopen(url, timeout=30) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or git_object('blob', raw) != oid:
            raise ValueError('attributes differ from reviewed Git blob')
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as tmp:
            tmp.write(raw)
        os.replace(tmp.name, cache/name)
    raw = read_artifact(cache, name)
    if git_object('blob', raw) != oid:
        raise ValueError('attributes differ from reviewed Git blob')
    rules = [line for line in raw.splitlines() if line.strip() and not line.lstrip().startswith(b'#')]
    return {'path': path, 'git_blob': oid, 'sha256': sha(raw),
            'literal_filter_lfs_lines': sum(b'filter=lfs' in rule.split()[1:] for rule in rules)}


def verify_repository(row, directory, attribute_cache=None, fetch=False):
    rev = row['commit']
    head_tree = command(directory, 'rev-parse', rev + '^{tree}').decode().strip()
    if head_tree != row['tree'] or command(directory, 'cat-file', '-t', rev).strip() != b'commit':
        raise ValueError('commit-to-tree binding failed')
    types = Counter(command(directory, 'cat-file', '--batch-all-objects', '--batch-check=%(objecttype)').splitlines())
    if types[b'blob'] or set(types) - {b'commit', b'tree'}:
        raise ValueError('metadata checkout contains unexpected object types')
    # Missing promised blobs are expected. fsck still checks the bytes/hash of each local object.
    command(directory, 'fsck', '--full', '--no-dangling', '--no-reflogs', '--no-progress')
    raw = command(directory, 'ls-tree', '-rtz', rev)
    counts, manifests = Counter(), Counter()
    tree_ids = {row['tree']}
    attribute_files = []
    for item in raw.split(b'\0'):
        if not item:
            continue
        meta, path = item.split(b'\t', 1)
        mode, kind, oid = meta.split()
        if kind == b'tree':
            tree_ids.add(oid.decode())
        elif kind == b'commit' and mode == b'160000':
            counts['nested_gitlinks'] += 1
        elif kind == b'blob':
            counts['tracked_blob_paths'] += 1
            basename = os.fsdecode(path.rsplit(b'/', 1)[-1])
            if mode in (b'100644', b'100755') and basename in FORMATS:
                manifests[basename] += 1
            if attribute_cache is not None and basename == '.gitattributes' and mode in (b'100644', b'100755'):
                attribute_files.append(attributes(row, os.fsdecode(path), oid.decode(), attribute_cache, fetch))
        else:
            raise ValueError('unexpected committed tree entry')
    if len(tree_ids) > types[b'tree'] or counts['tracked_blob_paths'] == 0:
        raise ValueError('incomplete remote trees')
    return {'id': row['id'], 'repository': row['repository'], 'commit': rev, 'root': row['tree'],
            'reachable_unique_trees': len(tree_ids), 'tracked_blob_paths': counts['tracked_blob_paths'],
            'nested_gitlinks': counts['nested_gitlinks'], 'manifest_counts': dict(manifests),
            'listing_sha256': sha(raw), 'blobs_in_git_object_db': 0, 'attributes': attribute_files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--fetch', action='store_true', help='start a new external metadata cache')
    mode.add_argument('--resume', action='store_true', help='retry missing rows in an existing external cache')
    parser.add_argument('cache', type=Path)
    parser.add_argument('attributes', type=Path, help='separate cache of Git-verified .gitattributes files')
    args = parser.parse_args()
    cache, attrs = args.cache.resolve(), args.attributes.resolve()
    if any(d.is_relative_to(ROOT) for d in (cache, attrs)) or attrs == cache:
        parser.error('choose separate external cache paths')
    if args.fetch:
        cache.mkdir(exist_ok=False, parents=True)
    acquire = args.fetch or args.resume
    if acquire:
        attrs.mkdir(exist_ok=True, parents=True)

    def process(row):
        directory = cache/str(row['id'])
        if acquire and not directory.exists():
            with tempfile.TemporaryDirectory(dir=cache) as temp:
                staging = Path(temp)/'git'
                staging.mkdir()
                command(staging, 'init', '--bare', '--quiet')
                command(staging, '-c', 'protocol.version=2', 'fetch', '--quiet', '--depth=1', '--no-tags',
                        '--no-recurse-submodules', '--filter=blob:none', 'https://github.com/'+row['repository']+'.git',
                        row['commit'])
                verify_repository(row, staging)
                staging.rename(directory)
        return verify_repository(row, directory, attrs, acquire)

    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [(row['id'], pool.submit(process, row)) for row, _ in roots()]
        for number, job in futures:
            try:
                rows.append(job.result())
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                errors.append(f'ID {number}: {exc}')
    if errors:
        sys.exit('metadata audit incomplete\n' + '\n'.join(errors))
    sys.stdout.buffer.write(canonical({'repositories': rows, 'rows_sha256': sha(canonical(rows))}))


if __name__ == '__main__':
    main()
