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
    raw = read_artifact(ROOT, 'superhunter/product_supply/source-inventory.json')
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
    if not (len(product) == 153 and product.items() <= links.items() and tree_oid(product) == PRODUCT_UPSTREAM_TREE):
        raise ValueError('product source set differs from the 153 reviewed rows')
    manifest = ''.join(f'[submodule "{r["path"]}"]\n\tpath = {r["path"]}\n'
                       f'\turl = https://github.com/{r["repository"]}.git\n\tshallow = true\n' for r in rows)
    if tree_oid(links) != OBSERVED_UPSTREAM_TREE or sha(manifest.encode()) != prior['manifest_sha256']:
        raise ValueError('historical upstream tree or manifest differs')
    preserved = records['preserved153.json']
    if (len(preserved) != 153 or any(r.get('status') != 'materialized_local_shared_objects' for r in preserved)
            or {r['path']: r['commit'] for r in preserved} != product):
        raise ValueError('preserved source cohort differs from the product gitlinks')
    acquired = records['summary.json']
    if len(acquired) != 47 or {r['path'] for r in acquired} != links.keys()-product.keys():
        raise ValueError('new historical observations must cover exactly the other 47 projects')
    for r in acquired:
        if r['seconds'] < 0 or {**{k: r[k] for k in ('commit', 'path', 'repository', 'status', 'tree')},
                                'catalog_id': r['id']} != local[r['path']]:
            raise ValueError('checkout batch row conflicts with the catalog')
    return {'schema': 1, 'product_gitlinks': len(product), 'separate_checkout_observations': len(links),
            'prior_153_matched': len(preserved), 'additional_checkouts_in_separate_workspace': len(acquired),
            'catalog_revisions_and_trees_matched': len(rows), 'historical_fsck_success_rows': len(acquired),
            'new_fsck_runs': 0, 'new_functional_credits': 0, 'historical_runner_sha256': PRIOR_SCRIPT_SHA,
            'historical_record_sha256': {n: v[1] for n, v in RECORDS.items()},
            'product_upstream_tree': PRODUCT_UPSTREAM_TREE, 'separate_upstream_tree': OBSERVED_UPSTREAM_TREE,
            'separate_workspace_commit': SOURCE_COMMIT, 'separate_workspace_root_tree': SOURCE_TREE}


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--existing-workspace', type=Path, help='also compare the existing 200-checkout observation workspace')
    args = parser.parse_args()
    try:
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
