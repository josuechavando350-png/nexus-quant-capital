"""Validate the earlier separated-workspace checkout records against the product catalog, offline."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import zlib

from ..product_review import ROOT, sha
from ..product_sources import git, gitlinks
from ..product_source_audit import SNAPSHOT, SNAPSHOT_SHA
from ..product_upstream_notices import sources
from ..repository_boundary import git_object
from ..safe_io import canonical, read_artifact, strict_json

ARCHIVE = 'superhunter/product_supply/source-materialization-observations.json'
ARCHIVE_SHA = '811b7cd787ed8180bb179be0ba9498c0e83dfcdb02b4630c70d54df6b399668f'
SOURCE_INVENTORY_SHA = '9fe08694ea198e7872cc954a122fc4bdc4675996a5403cb7344822a89a3bfe3f'
SOURCE_COMMIT = '785860fc85166597d40ba08503a3d89a6be8e5be'
SOURCE_TREE = 'fabbe3713be54db5c64a7f752ba419f7e7fd3c6c'
OBSERVED_UPSTREAM_TREE = 'd8b5a3d79e81e686d4299e40bea64d37824d29fe'
PRODUCT_UPSTREAM_TREE = '20df6bd14174b62825d33de0d48f9af4598079cd'
PRIOR_SCRIPT_SHA = '0f0c7d438b766ea9899aa854f4c0f815e1bc40be0d74d79a4ab957e523d73ff4'
RECORDS = {
    'summary.json': (13151, '6690a332aadd202f48b70289cd86d1e2a310301221daa653b8ff8423fd5e8214'),
    'preserved153.json': (23563, 'bb9daf7f299995884632031691b81e89710412d4b76d14fff840a598079fc971'),
    'all200-checkouts.json': (44525, 'c4e92c74303625b19e0ad4a8bf9643b3c1eb3b93fae72292d3f956ed89ed07bb'),
}


def unpack_records():
    raw = read_artifact(ROOT, ARCHIVE)
    if sha(raw) != ARCHIVE_SHA:
        raise ValueError('source materialization archive changed')
    archived = strict_json(raw)
    if archived.get('schema') != 1 or set(archived['records']) != set(RECORDS):
        raise ValueError('unexpected observations')
    observations = {}
    for name, (size, digest) in RECORDS.items():
        item = archived['records'][name]
        if (item['size'], item['sha256']) != (size, digest):
            raise ValueError('changed observation identity')
        decoder = zlib.decompressobj()
        contents = decoder.decompress(base64.b64decode(item['zlib_base64'], validate=True), size + 1)
        if (len(contents) != size or sha(contents) != digest or not decoder.eof
                or decoder.unconsumed_tail or decoder.unused_data):
            raise ValueError('malformed or changed compressed observation')
        observations[name] = strict_json(b'{"value":' + contents + b'}')['value']
    return observations


def expected_rows():
    raw = read_artifact(ROOT, 'superhunter/product_supply/source-inventory-153.json')
    if sha(raw) != SOURCE_INVENTORY_SHA:
        raise ValueError('audited source inventory changed')
    inventory = strict_json(raw)['entries']
    rows = []
    for identity, tree in zip(sources(), inventory, strict=True):
        repo = identity['repository']
        if ((identity['id'], repo, identity['revision'])
                != (tree['id'], tree['repository'], tree['revision'])):
            raise ValueError('catalog and prior tree authority differ')
        folder = f"upstream/{identity['id']:03}-{repo.split('/')[1].lower()}"
        rows.append({'catalog_id': identity['id'], 'commit': identity['revision'], 'path': folder,
                     'repository': repo, 'status': 'checked_out', 'tree': tree['tree']})
    if [row['catalog_id'] for row in rows] != list(range(1, 201)):
        raise ValueError('catalog must identify exactly 200 distinct subjects')
    return rows


def tree_oid(links):
    raw = b''.join(b'160000 ' + path.removeprefix('upstream/').encode() + b'\0' + bytes.fromhex(oid)
                   for path, oid in sorted(links.items()))
    return git_object('tree', raw)


def verify(records, product):
    prior = records['all200-checkouts.json']
    rows = expected_rows()
    if (prior['count'] != 200 or prior['catalog_count'] != 200 or prior['catalog_only_count'] != 0
            or prior['catalog_only'] or prior['status_counts'] != {'checked_out': 200}
            or prior['upstream_code_executed_by_verifier'] is not False or prior['sources'] != rows):
        raise ValueError('historical observations differ from the 200 pinned catalog rows')
    links = {r['path']: r['commit'] for r in rows}
    local = {r['path']: r for r in rows}
    if product != links or tree_oid(product) != OBSERVED_UPSTREAM_TREE:
        raise ValueError('current product gitlinks differ from the 200 observed catalog revisions')
    manifest = ''.join(f'[submodule "{r["path"]}"]\n\tpath = {r["path"]}\n'
                       f'\turl = https://github.com/{r["repository"]}.git\n\tshallow = true\n' for r in rows)
    if tree_oid(links) != OBSERVED_UPSTREAM_TREE or sha(manifest.encode()) != prior['manifest_sha256']:
        raise ValueError('historical upstream tree or manifest differs')
    preserved = records['preserved153.json']
    historical_links = {r['path']: r['commit'] for r in preserved}
    if (len(preserved) != 153 or len(historical_links) != 153
            or any(r.get('status') != 'materialized_local_shared_objects' for r in preserved)
            or not historical_links.items() <= product.items() or tree_oid(historical_links) != PRODUCT_UPSTREAM_TREE):
        raise ValueError('preserved source cohort differs from the historical 153 gitlinks')
    acquired = records['summary.json']
    if len(acquired) != 47 or {r['path'] for r in acquired} != links.keys()-historical_links.keys():
        raise ValueError('new historical observations must cover exactly the other 47 projects')
    for r in acquired:
        if r['seconds'] < 0 or {**{k: r[k] for k in ('commit', 'path', 'repository', 'status', 'tree')},
                                'catalog_id': r['id']} != local[r['path']]:
            raise ValueError('checkout batch row conflicts with the catalog')
    historical = {'schema': 1, 'product_gitlinks': len(historical_links), 'separate_checkout_observations': len(links),
            'prior_153_matched': len(preserved), 'additional_checkouts_in_separate_workspace': len(acquired),
            'catalog_revisions_and_trees_matched': len(rows), 'historical_fsck_success_rows': len(acquired),
            'new_fsck_runs': 0, 'new_functional_credits': 0, 'historical_runner_sha256': PRIOR_SCRIPT_SHA,
            'historical_record_sha256': {n: v[1] for n, v in RECORDS.items()},
            'product_upstream_tree': PRODUCT_UPSTREAM_TREE, 'separate_upstream_tree': OBSERVED_UPSTREAM_TREE,
            'separate_workspace_commit': SOURCE_COMMIT, 'separate_workspace_root_tree': SOURCE_TREE}
    return {'schema': 2, 'current_product_gitlinks': len(product), 'current_product_upstream_tree': tree_oid(product),
            'preserved_gitlinks': len(historical_links), 'added_gitlinks': len(product) - len(historical_links),
            'new_functional_credits': 0, 'historical_record': historical}


def compare_local(workspace):
    """Observe the existing 200 direct checkouts. No fetching or checkout mutation."""
    roots = git(workspace, 'rev-parse', SOURCE_COMMIT + '^{tree}', SOURCE_COMMIT + ':upstream').decode().splitlines()
    rows = expected_rows()
    if (roots != [SOURCE_TREE, OBSERVED_UPSTREAM_TREE]
            or gitlinks(workspace, SOURCE_COMMIT) != {r['path']: r['commit'] for r in rows}):
        raise ValueError('local historical superproject does not match the observed tree')

    def check_head(row):
        folder = workspace / row['path']
        observed = git(folder, 'rev-parse', '--show-toplevel', 'HEAD', 'HEAD^{tree}').decode().splitlines()
        if observed != [str(folder.resolve()), row['commit'], row['tree']] or folder.is_symlink():
            raise ValueError('incorrect checkout for catalog ID ' + str(row['catalog_id']))
        return [row['catalog_id'], *observed[1:]]

    with ThreadPoolExecutor(max_workers=4) as pool:
        local = list(pool.map(check_head, rows))
    return {'local_checkouts_observed': len(local), 'commit_tree_pairs_sha256': sha(canonical(local)),
            'local_check_scope': 'historical superproject, directory identity, checked-out HEAD and root tree'}


def local_path(workspace, path):
    """Reject traversal and symlinks in any component of an observed local path."""
    if not path.is_relative_to(workspace) or path.resolve() != path:
        raise ValueError('dependency observation leaves its physical workspace')
    return path


def git_directory(workspace, checkout):
    marker = local_path(workspace, checkout/'.git')
    if marker.is_file():
        record = read_artifact(workspace, str(marker.relative_to(workspace))).decode().splitlines()
        if len(record) != 1 or not record[0].startswith('gitdir: '):
            raise ValueError('invalid Git directory marker')
        marker = local_path(workspace, (checkout/record[0][8:]).resolve(strict=True))
    if not marker.is_dir():
        raise ValueError('direct checkout has no Git directory')
    return marker


def common_storage(workspace, gitdir):
    shared = local_git(gitdir, 'rev-parse', '--path-format=absolute', '--git-common-dir').decode().strip()
    store = local_path(workspace, Path(shared))
    # An alternate object database can lie outside the supplied checkout collection.
    # It needs a separate inventory before its objects can be attributed to these stores.
    for name in ('alternates', 'http-alternates'):
        alternate = local_path(workspace, store/'objects/info'/name)
        if alternate.exists():
            raise ValueError('Git alternate storage requires a separate scope')
    return store


def local_git(gitdir, *args, query=None):
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/dev/null', 'LC_ALL': 'C',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_ALLOW_PROTOCOL': '', 'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0'}
    return subprocess.check_output(['/usr/bin/git', '--no-optional-locks', '--no-replace-objects',
                                   '--literal-pathspecs', '--git-dir', str(gitdir), *args],
                                   env=env, input=query, stderr=subprocess.PIPE, timeout=60)


def local_payload(workspace, path, pointer):
    try:
        data = read_artifact(workspace, str(local_path(workspace, path).relative_to(workspace)))
    except FileNotFoundError:
        return 'absent'
    if len(data) == pointer['bytes'] and sha(data) == pointer['oid']:
        return 'verified_payload'
    if data == pointer_bytes(pointer):
        return 'pointer_only'
    raise ValueError('local LFS candidate differs from the pinned pointer and payload')


def pointer_bytes(pointer):
    return (f'version https://git-lfs.github.com/spec/v1\noid sha256:{pointer["oid"]}\n'
            f'size {pointer["bytes"]}\n').encode()


def nested_artifacts(workspace):
    """Observe pinned trees, worktree entries and object visibility without filling a cache."""
    raw = read_artifact(ROOT, SNAPSHOT)
    if sha(raw) != SNAPSHOT_SHA:
        raise ValueError('direct source inventory differs from its reviewed bytes')
    rows = strict_json(raw)['entries']
    oids = sorted({oid for row in rows for oid in row['contents']['nested_gitlinks'].values()})
    query = b''.join((oid + '\n').encode() for oid in oids)
    hits, links, payloads, stores, nested_stores = {}, [], [], [], []
    for authority, row in zip(expected_rows(), rows, strict=True):
        if (row['id'], row['repository'], row['revision'], row['tree']) != (
                authority['catalog_id'], authority['repository'], authority['commit'], authority['tree']):
            raise ValueError('direct catalog identity or tree differs')
        checkout = local_path(workspace, workspace/authority['path'])
        gitdir = git_directory(workspace, checkout)
        if local_git(gitdir, 'rev-parse', 'HEAD', 'HEAD^{tree}').decode().splitlines() != [row['revision'], row['tree']]:
            raise ValueError('direct checkout differs from its catalog revision')
        store = common_storage(workspace, gitdir)
        stores.append((row['id'], store))
        modules = local_path(workspace, store/'modules')
        if modules.is_dir() and any(modules.iterdir()):
            nested_stores.append(row['id'])
        objects = local_git(gitdir, 'cat-file', '--batch-check', query=query).decode().splitlines()
        for oid, line in zip(oids, objects, strict=True):
            values = line.split()
            if values == [oid, 'missing']:
                continue
            if len(values) != 3 or values[:2] != [oid, 'commit']:
                raise ValueError('unexpected Git object type')
            hits.setdefault(oid, []).append(row['id'])
        nested = row['contents']['nested_gitlinks']
        pointers = row['contents']['lfs_pointers']
        paths = [*nested, *pointers]
        if not paths:
            continue
        entries = local_git(gitdir, 'ls-tree', '-z', row['tree'], '--', *paths).split(b'\0')
        tree = {path: meta.split() for meta, path in (item.decode().split('\t', 1) for item in entries if item)}
        if tree.keys() != set(paths):
            raise ValueError('pinned tree lacks a recorded dependency path')
        for name, oid in sorted(nested.items()):
            if tree[name] != ['160000', 'commit', oid]:
                raise ValueError('gitlink differs from pinned direct tree')
            folder = local_path(workspace, checkout/name)
            state = 'missing'
            if folder.is_dir():
                state = 'nonempty_unverified' if any(folder.iterdir()) else 'empty'
                if local_path(workspace, folder/'.git').exists():
                    head = local_git(git_directory(workspace, folder), 'rev-parse', 'HEAD').decode().strip()
                    state = 'pinned_head' if head == oid else 'different_head'
            elif folder.exists():
                raise ValueError('nested checkout path is not a directory')
            links.append([row['id'], name, oid, state])
        for name, pointer in sorted(pointers.items()):
            meta = tree[name]
            expected_pointer = pointer_bytes(pointer)
            if (meta[:2] != ['100644', 'blob'] or meta[2] != git_object('blob', expected_pointer)
                    or local_git(gitdir, 'cat-file', 'blob', meta[2]) != expected_pointer):
                raise ValueError('tracked LFS blob differs from its recorded pointer')
            payloads.append({'id': row['id'], 'path': name, **pointer, 'pointer_blob': meta[2],
                             'worktree_state': local_payload(workspace, checkout/name, pointer)})
    if len({store for _, store in stores}) != len(stores):
        raise ValueError('multiple catalog checkouts share an object database')
    for pointer in payloads:
        oid = pointer['oid']
        cached = {}
        for number, directory in stores:
            state = local_payload(workspace, directory/'lfs/objects'/oid[:2]/oid[2:4]/oid, pointer)
            if state != 'absent':
                cached[str(number)] = state
        pointer['canonical_cache_hits_by_catalog_id'] = cached
    states = sorted({row[3] for row in links})
    return {'schema_version': 1, 'source_inventory_sha256': SNAPSHOT_SHA, 'direct_object_databases': len(stores),
            'gitlink_paths': len(links), 'unique_gitlink_commits': len(oids),
            'gitlink_parent_count': len({row[0] for row in links}),
            'checkout_states': {state: sum(row[3] == state for row in links) for state in states},
            'gitlink_path_states_sha256': sha(canonical(links)),
            'commit_hits_in_direct_object_databases': hits, 'parents_with_separate_module_storage': nested_stores,
            'lfs': payloads, 'scope': 'Direct catalog object databases, nested working paths and canonical direct LFS caches. Nested HEAD observations identify commits; tracked-file completeness requires a separate comparison.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--existing-workspace', type=Path, help='also compare the existing 200-checkout observation workspace')
    modes.add_argument('--nested-workspace', type=Path, help='observe nested gitlinks and pinned LFS bytes in local direct checkouts')
    args = parser.parse_args()
    try:
        if args.nested_workspace:
            sys.stdout.buffer.write(canonical(nested_artifacts(args.nested_workspace.resolve(strict=True))))
            return 0
        result = verify(unpack_records(), gitlinks(ROOT))
        if args.existing_workspace:
            result.update(compare_local(args.existing_workspace.resolve()))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, zlib.error, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
