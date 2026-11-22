"""Compare the nonempty regular-file Git blob IDs declared by every pinned source tree."""
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

from .product_sources import gitlinks
from .product_review import ROOT
from .repository_boundary import git_object
from .tools.verify_source_materialization import expected_rows, git_directory, local_git, local_path

EMPTY_BLOB = bytes.fromhex(git_object('blob', b''))
MODES = {b'040000': b'tree', b'100644': b'blob', b'100755': b'blob', b'120000': b'blob', b'160000': b'commit'}


def inventory(listing, root_tree):
    """Reconstruct every tree, including entries excluded from the comparison."""
    trees = {b'': bytearray()}
    expected = {b'': root_tree}
    blobs = set()
    regular_paths = 0
    for record in listing.split(b'\0'):
        if not record:
            continue
        metadata, path = record.split(b'\t', 1)
        mode, kind, oid = metadata.split()
        parent, _, name = path.rpartition(b'/')
        if MODES.get(mode) != kind or parent not in trees or not name:
            raise ValueError('invalid recursive Git listing')
        digest = bytes.fromhex(oid.decode('ascii'))
        if len(digest) != 20:
            raise ValueError('invalid Git object ID')
        trees[parent].extend(mode.lstrip(b'0') + b' ' + name + b'\0' + digest)
        if kind == b'tree':
            if path in trees:
                raise ValueError('duplicate directory')
            expected[path] = oid.decode('ascii')
            trees[path] = bytearray()
        elif mode in (b'100644', b'100755'):
            regular_paths += 1
            if digest != EMPTY_BLOB:
                blobs.add(digest)
    for path, payload in trees.items():
        if git_object('tree', bytes(payload)) != expected[path]:
            raise ValueError('recursive listing differs from pinned Git tree')
    return regular_paths, blobs


def read_source(workspace, row):
    directory = git_directory(workspace, local_path(workspace, workspace / row['path']))
    commit, tree = row['commit'], row['tree']
    if local_git(directory, 'rev-parse', 'HEAD').decode().strip() != commit:
        raise ValueError(f"checkout differs for {row['repository']}")
    raw = local_git(directory, 'cat-file', 'commit', commit)
    if git_object('commit', raw) != commit or raw.split(b'\n', 1)[0] != b'tree ' + tree.encode():
        raise ValueError(f"commit or tree identity differs for {row['repository']}")
    return inventory(local_git(directory, 'ls-tree', '-rtz', tree), tree)


def measure(rows, inventories):
    """Each unordered pair is measured once, including pairs sharing no blob."""
    if len(rows) != len(inventories) or [r['catalog_id'] for r in rows] != list(range(1, len(rows) + 1)):
        raise ValueError('source inventories must follow the complete catalog order')
    measured = [{'id': r['catalog_id'], 'repository': r['repository'], 'commit': r['commit'], 'tree': r['tree'],
                 'regular_paths': paths, 'distinct_nonempty_blobs': len(blobs), 'matches_with_later_ids': []}
                for r, (paths, blobs) in zip(rows, inventories, strict=True)]
    pairs = matching = 0
    for i, j in combinations(range(len(rows)), 2):
        count = len(inventories[i][1] & inventories[j][1])
        measured[i]['matches_with_later_ids'].append(count)
        pairs += 1
        matching += count > 0
    return {'schema_version': 1, 'repositories': len(rows), 'pairs_compared': pairs,
            'pairs_with_shared_blobs': matching, 'pairs_without_shared_blobs': pairs - matching,
            'rows': measured}


def build(workspace, jobs=4):
    workspace = Path(workspace).resolve(strict=True)
    rows = expected_rows()
    if gitlinks(ROOT) != {r['path']: r['commit'] for r in rows}:
        raise ValueError('product Git links differ from the pinned catalog')
    upstream = local_path(workspace, workspace/'upstream')
    if {p.name for p in upstream.iterdir()} != {Path(r['path']).name for r in rows}:
        raise ValueError('source workspace does not contain exactly the catalog directories')
    with ThreadPoolExecutor(max_workers=jobs) as workers:
        inventories = list(workers.map(lambda row: read_source(workspace, row), rows))
    return measure(rows, inventories)


def pair(report, first, second):
    lower, upper = sorted((first, second))
    if not 1 <= lower < upper <= report['repositories']:
        raise ValueError('select two distinct catalog IDs in range')
    left, right = report['rows'][lower - 1], report['rows'][upper - 1]
    return {'repositories': [{k: row[k] for k in ('id', 'repository', 'commit', 'tree')} for row in (left, right)],
            'shared_nonempty_blobs': left['matches_with_later_ids'][upper - lower - 1]}


def coverage(report, matrix):
    """Join content sharing to same-session receipts for each exact catalog revision."""
    rows = report['rows']
    accepted = {r['id']: r for r in matrix['rows']}
    if len(accepted) != len(matrix['rows']) or len(accepted) != len(rows):
        raise ValueError('source and participation inventories differ')
    peers = {row['id']: [] for row in rows}
    for row in rows:
        number = row['id']
        session = accepted.get(number, {})
        if any(session.get(k) != row[k] for k in ('id', 'repository', 'commit', 'tree')):
            raise ValueError('source and participation revisions differ')
        counts = row['matches_with_later_ids']
        for later, count in zip(rows[number:], counts, strict=True):
            if count:
                other = later['id']
                peers[number].append(other)
                peers[other].append(number)
    return {'catalog': len(rows), 'pairs_compared': report['pairs_compared'],
            'participating': sum(bool(r['session_operations']) for r in accepted.values()),
            'rows': [{'id': n, 'repository': accepted[n]['repository'], 'session': accepted[n]['session'],
                      'peers_with_receipts': [p for p in shared if accepted[p]['session_operations']],
                      'peers_without_receipts': [p for p in shared if not accepted[p]['session_operations']]}
                     for n, shared in peers.items()]}
