"""Join immutable source-tree observations and document-level license evidence by catalog ID."""
from collections import Counter, defaultdict
import os
from pathlib import Path
import re
import subprocess

from .product_sources import git, verify
from .product_upstream_notices import filename, select_document, sources, verified_corpus
from .product_review import CATALOG, ROOT, sha
from .safe_io import canonical, read_artifact, strict_json

REMOTE = 'superhunter/product_supply/catalog-commit-trees.json'
REMOTE_SHA = '836b29fc5e5639f41784b47405bfecc8297f781b05e2686150831b5b3a1b9216'
MANIFESTS = frozenset(('Cargo.toml', 'Cargo.lock', 'go.mod', 'go.sum', 'package.json',
                      'package-lock.json', 'npm-shrinkwrap.json', 'yarn.lock', 'pnpm-lock.yaml',
                      'pyproject.toml', 'requirements.txt', 'setup.py', 'setup.cfg', 'poetry.lock',
                      'uv.lock', 'Pipfile.lock', 'pom.xml', 'build.gradle', 'build.gradle.kts',
                      'Gemfile', 'Gemfile.lock', 'composer.json', 'composer.lock', 'flake.lock',
                      'packages.lock.json', 'vcpkg.json', 'conanfile.txt'))
LICENSE_NAME = re.compile(r'^(?:licen[cs]e|copying|copyright|notice)(?:$|[-_.].*)', re.I)
LFS_HEADER = b'version https://git-lfs.github.com/spec/v1\n'
LFS_PTR = re.compile(re.escape(LFS_HEADER) + rb'(?:ext-[^\n]+\n)*oid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n?')


def remote_trees(root, pending):
    data = read_artifact(root, REMOTE)
    if sha(data) != REMOTE_SHA:
        raise ValueError('remote commit metadata changed')
    rows = strict_json(data)['commits']
    result = {r['id']: r for r in rows}
    if len(result) != len(rows) or set(result) != set(pending):
        raise ValueError('unexpected catalog-only commit metadata')
    for number, row in result.items():
        item = pending[number]
        url = f"https://api.github.com/repos/{item['repository']}/git/commits/{item['revision']}"
        if ((row['repository'], row['commit'], row['url']) != (item['repository'], item['revision'], url)
                or not re.fullmatch(r'[0-9a-f]{40}', row['tree'])):
            raise ValueError('remote commit names a different source')
    return result


def read_blobs(folder, sizes):
    # Batch requests are limited by the expected response size, including attributes.
    ids = list(sizes)
    for start in range(0, len(ids), 128):
        chunk = ids[start:start + 128]
        command = ['git', '--no-replace-objects', '-C', str(folder), 'cat-file', '--batch']
        proc = subprocess.run(command, input=('\n'.join(chunk) + '\n').encode(), check=True,
                              capture_output=True, timeout=60,
                              env={**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0'})
        pos = 0
        for oid in chunk:
            end = proc.stdout.index(b'\n', pos)
            if proc.stdout[pos:end].split() != [oid.encode(), b'blob', str(sizes[oid]).encode()]:
                raise ValueError('unexpected blob in Git response')
            pos = end + 1
            yield oid, proc.stdout[pos:pos + sizes[oid]]
            pos += sizes[oid]
            if proc.stdout[pos:pos + 1] != b'\n':
                raise ValueError('truncated Git blob response')
            pos += 1
        if pos != len(proc.stdout):
            raise ValueError('unexpected bytes after Git blobs')


def tree_inventory(folder, source):
    rev = source['revision']
    nested, manifests, root_notices, oversized_attributes = {}, Counter(), {}, []
    candidates, sizes = defaultdict(list), {}
    for record in git(folder, 'ls-tree', '-rlz', rev).split(b'\0'):
        if not record:
            continue
        meta, raw_path = record.split(b'\t', 1)
        mode, kind, oid, size = meta.decode('ascii').split()
        path = os.fsdecode(raw_path)
        name = path.rsplit('/', 1)[-1]
        if kind == 'commit' and mode == '160000':
            nested[path] = oid
            continue
        if kind != 'blob' or mode not in ('100644', '100755'):
            continue
        if name in MANIFESTS:
            manifests[name] += 1
        if '/' not in path and LICENSE_NAME.fullmatch(name):
            root_notices[path] = oid
        size = int(size)
        if name == '.gitattributes' and size > 65536:
            oversized_attributes.append(path)
        if 0 < size <= 1024 or (name == '.gitattributes' and size <= 65536):
            candidates[oid].append(path)
            sizes[oid] = size
    pointers, attributes, unusual = {}, [], []
    for oid, data in read_blobs(folder, sizes):
        paths = candidates[oid]
        if re.search(rb'(?m)^(?![ \t]*#)[^\n]*[ \t]filter=lfs(?:[ \t\r]|$)', data):
            attributes.extend(p for p in paths if p.rsplit('/', 1)[-1] == '.gitattributes')
        if data.startswith(LFS_HEADER):
            match = LFS_PTR.fullmatch(data)
            if match:
                for path in paths:
                    pointers[path] = {'oid': match[1].decode(), 'bytes': int(match[2])}
            else:
                unusual.extend(paths)
    notice = source['notice']
    oid = git(folder, 'rev-parse', '--verify', rev + ':' + notice['path']).decode().strip()
    if oid != notice['git_blob']:
        raise ValueError('notice path differs from the catalog Git object')
    select_document(source, git(folder, 'cat-file', 'blob', oid))
    return {'nested_gitlinks': nested, 'manifest_counts_by_filename': dict(manifests),
            'root_notice_files': root_notices, 'lfs_pointers': pointers,
            'lfs_attribute_files': sorted(attributes), 'unrecognized_lfs_headers': sorted(unusual),
            'oversized_attributes_not_inspected': sorted(oversized_attributes)}


def license_inventory(folder, release):
    from .product_licenses import scan
    rows = sources()
    corpus = verified_corpus(folder, rows)
    # Repeated bytes require only one native scan. Keep a result for every identity.
    by_hash = {}
    for key, data in corpus.items():
        by_hash.setdefault(sha(data), key)
    names = list(by_hash.values())
    results = {}
    for start in range(0, len(names), 30):
        batch = {n: corpus[n] for n in names[start:start + 30]}
        results.update(scan(release, batch)['notices'])
    return {r['id']: results[by_hash[sha(corpus[filename(r)])]] for r in rows}


def inventory(root, notices=None, release=None):
    verified = verify(root, require_checkout=True)
    checked = {s['catalog_id']: s for s in verified['sources']}
    catalog = sources()
    remote = remote_trees(root, {r['id']: r for r in catalog if r['id'] not in checked})
    licenses = license_inventory(notices, release) if notices is not None else {}
    entries = []
    for row in catalog:
        number = row['id']
        entry = {'id': number, 'github_id': row['github_id'], 'repository': row['repository'],
                 'revision': row['revision'], 'notice_path': row['notice']['path']}
        if number in checked:
            item = checked[number]
            entry.update(evidence='local_git_tree', tree=item['tree'],
                         contents=tree_inventory(root/item['path'], row))
        else:
            entry.update(evidence='github_commit_metadata', tree=remote[number]['tree'], contents=None)
        if licenses:
            entry['notice_scan'] = licenses[number]
        entries.append(entry)
    result = {'schema_version': 1, 'checkouts': len(checked), 'remote_commit_records': len(remote),
              'entries': entries, 'entries_sha256': sha(canonical(entries))}
    if licenses:
        from .product_licenses import SCAN_SHA
        result['notice_producer'] = {'name': 'ScanCode Toolkit', 'version': '32.5.0', 'release_sha256': SCAN_SHA}
    return result


SNAPSHOT = 'superhunter/product_supply/source-inventory.json'
SNAPSHOT_SHA = 'bef1aec717fb4a7800283a1dceff3102a749b04b2a46c1fe02fd22b4ad259b14'
NATURE = 'superhunter/product_supply/source-natures.json'
NATURE_SHA = '5a6fb83a6f6df74992a6423da69db61d712d6fb480a86238775eede20a909212'


def attach(index):
    from .product_licenses import SCAN_SHA
    from .product_upstream_notices import document_hash

    inventory_bytes = read_artifact(ROOT, SNAPSHOT)
    nature_bytes = read_artifact(ROOT, NATURE)
    if sha(inventory_bytes) != SNAPSHOT_SHA or sha(nature_bytes) != NATURE_SHA:
        raise ValueError('source inventory differs from reviewed evidence')
    record = strict_json(inventory_bytes)
    rows = record['entries']
    if sha(canonical(rows)) != record['entries_sha256'] or record['notice_producer']['release_sha256'] != SCAN_SHA:
        raise ValueError('source inventory content or producer differs')
    natures = strict_json(nature_bytes)
    by_id = {n: kind for kind, ids in natures.items() for n in ids}
    if len(by_id) != 200 or sum(map(len, natures.values())) != len(by_id):
        raise ValueError('source classifications overlap or are incomplete')
    declarations = verify(ROOT)
    checkouts = {r['catalog_id']: r for r in declarations['sources']}
    catalog = strict_json(read_artifact(ROOT, CATALOG))['entries']
    for row, source, original in zip(rows, sources(), catalog, strict=True):
        number = row['id']
        if ((number, row['repository'], row['github_id'], row['revision']) !=
                (source['id'], source['repository'], source['github_id'], source['revision'])
                or original['id'] != number or row['notice_scan']['sha256'] != document_hash(source)):
            raise ValueError('source inventory and product identity differ')
        local = number in checkouts
        if local != (row['contents'] is not None) or local != (row['evidence'] == 'local_git_tree'):
            raise ValueError('checkout evidence differs from reviewed product')
        item = index.repos[row['repository'].casefold()]
        item['source_inventory'] = {**row, 'nature': by_id[number], 'catalog_purpose': original['purpose'],
                                    'catalog_license_label': original['license']}
    index.source_inventory = {
        'catalog_count': len(rows), 'checkouts': len(checkouts), 'metadata_only': len(rows) - len(checkouts),
        'notice_matches': sum(bool(r['notice_scan']['detected_expression']) for r in rows),
        'source_natures': {k: len(v) for k, v in natures.items()},
        'nested_gitlinks': sum(len(r['contents']['nested_gitlinks']) for r in rows if r['contents']),
        'lfs_pointers': sum(len(r['contents']['lfs_pointers']) for r in rows if r['contents']),
        'snapshot_sha256': SNAPSHOT_SHA, 'entries_sha256': record['entries_sha256'],
        'notice_producer': record['notice_producer']}
