"""Read the 47 pinned remote Git root trees and original, declarative dependency inputs."""
import base64
import re
import tomllib

from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_source_audit import REMOTE, REMOTE_SHA
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

TREES = 'superhunter/product_supply/remote-tree-inventory.json'
TREES_SHA = '76dae6544fcd75ef89908c925817e85d2d9ada18adfe826e10263acfe55a7beb'
PROOFS = 'superhunter/product_supply/remote-root-proofs.json'
PROOFS_SHA = 'a00144788cb867c288e927e95213a99084d1b3f25bdc7604739f515264df6e2a'
FORMATS = ('Cargo.toml', 'go.mod', 'package.json', 'pyproject.toml', 'requirements.txt')
REQ = re.compile(r'([a-zA-Z0-9][a-zA-Z0-9._-]*)(?=\s|\[|[<>=!~;]|$)')


def parse_tree(raw, expected):
    if git_object('tree', raw) != expected:
        raise EvidenceError('remote root tree does not match pinned commit metadata')
    entries = {}
    order = []
    offset = 0
    while offset < len(raw):
        end = raw.index(b'\0', offset)
        mode, name = raw[offset:end].split(b' ', 1)
        oid = raw[end+1:end+21]
        if (mode not in (b'40000', b'100644', b'100755', b'120000', b'160000') or len(oid) != 20
                or not name or name in (b'.', b'..') or b'/' in name or name in entries):
            raise EvidenceError('invalid remote root tree entry')
        entries[name] = (mode, oid.hex())
        order.append(name + (b'/' if mode == b'40000' else b''))
        offset = end + 21
    if order != sorted(order):
        raise EvidenceError('noncanonical Git tree order')
    return entries


def roots():
    record = read_artifact(ROOT, REMOTE)
    data = read_artifact(ROOT, PROOFS)
    if sha(record) != REMOTE_SHA or sha(data) != PROOFS_SHA:
        raise EvidenceError('remote root proof inventory changed')
    commits = strict_json(record)['commits']
    proofs = strict_json(data)['roots']
    if [r['id'] for r in proofs] != [r['id'] for r in commits] or len(proofs) != 47:
        raise EvidenceError('remote root proof scope changed')
    for item, proof in zip(commits, proofs, strict=True):
        entries = parse_tree(base64.b64decode(proof['root'], validate=True), item['tree'])
        yield item, entries


def manifests(entries):
    return {name: entries[name.encode()][1] for name in FORMATS
            if name.encode() in entries and entries[name.encode()][0] in (b'100644', b'100755')}


def declared_names(name, raw):
    """Count literal declarations; never resolve or install a package."""
    text = raw.decode('utf-8-sig')
    names, skipped = set(), 0
    def python_line(value):
        nonlocal skipped
        match = REQ.match(value.strip())
        if match:
            names.add(re.sub(r'[-_.]+', '-', match[1]).lower())
        else:
            skipped += 1
    if name == 'package.json':
        package = strict_json(raw)
        for group in ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies'):
            names.update(package.get(group, {}))
    elif name == 'Cargo.toml':
        cargo = tomllib.loads(text)
        for section in (cargo, cargo.get('workspace', {}), *cargo.get('target', {}).values()):
            for group in ('dependencies', 'dev-dependencies', 'build-dependencies'):
                for alias, value in section.get(group, {}).items():
                    names.add(value.get('package', alias) if isinstance(value, dict) else alias)
    elif name == 'pyproject.toml':
        project = tomllib.loads(text)
        metadata = project.get('project', {})
        for dep in metadata.get('dependencies', []):
            python_line(dep)
        for group in metadata.get('optional-dependencies', {}).values():
            for dep in group:
                python_line(dep)
        poetry = project.get('tool', {}).get('poetry', {})
        for section in [poetry, *poetry.get('group', {}).values()]:
            for dep in section.get('dependencies', {}):
                if dep != 'python':
                    python_line(dep)
    elif name == 'requirements.txt':
        for line in text.splitlines():
            line = line.split('#', 1)[0].strip()
            if line:
                python_line(line)
    elif name == 'go.mod':
        within = False
        for line in text.splitlines():
            words = line.split('//', 1)[0].split()
            if words == ['require', '(']:
                within = True
            elif words == [')']:
                within = False
            elif within and len(words) == 2:
                names.add(words[0])
            elif words[:1] == ['require'] and len(words) == 3:
                names.add(words[1])
    else:
        raise EvidenceError('unsupported dependency declaration')
    return {'names': sorted(names), 'unparsed_lines': skipped}


def member_name(number, name):
    return f'{number:03}-{name}'


def root_results(folder=None, *, read_file=None):
    if read_file is None:
        def read_file(name):
            return read_artifact(folder, name)
    results = []
    for item, entries in roots():
        files = {}
        for name, digest in manifests(entries).items():
            raw = read_file(member_name(item['id'], name))
            if git_object('blob', raw) != digest:
                raise EvidenceError('dependency file differs from its Git tree')
            files[name] = {'git_blob': digest, 'sha256': sha(raw), **declared_names(name, raw)}
        results.append({'id': item['id'], 'repository': item['repository'], 'commit': item['commit'],
                        'tree': item['tree'], 'root_entries': len(entries), 'manifests': files})
    return results


def attach(index, folder=None, *, read_file=None):
    results = root_results(folder, read_file=read_file)
    data = read_artifact(ROOT, TREES)
    if sha(data) != TREES_SHA:
        raise EvidenceError('recursive tree inventory does not match the reviewed evidence')
    inventory = strict_json(data)
    remote = inventory['repositories']
    if sha(canonical(remote)) != inventory['rows_sha256']:
        raise EvidenceError('recursive tree rows differ from the verified corpus')
    for row, entry in zip(results, remote, strict=True):
        if ((entry['id'], entry['commit'], entry['root'], entry['repository']) !=
                (row['id'], row['commit'], row['tree'], row['repository'])):
            raise EvidenceError('recursive tree inventory joined to wrong catalog entry')
        product = index.repos[row['repository'].casefold()]
        if row['id'] != product['catalog_id']:
            raise EvidenceError('dependency evidence attached to a different product identity')
        product['root_declarations'] = row
        product['recursive_tree_inventory'] = entry
    attrs = [attr for row in remote for attr in row['attributes']]
    index.recursive_source_trees = {
        'repositories': len(remote), 'rows_sha256': inventory['rows_sha256'],
        'unique_trees_summed_per_repository': sum(r['reachable_unique_trees'] for r in remote),
        'tracked_blob_paths': sum(r['tracked_blob_paths'] for r in remote),
        'nested_gitlinks': sum(r['nested_gitlinks'] for r in remote),
        'manifest_paths': sum(sum(r['manifest_counts'].values()) for r in remote),
        'attributes_files': len(attrs), 'literal_filter_lfs_lines': sum(a['literal_filter_lfs_lines'] for a in attrs),
        'source_blobs_in_metadata_databases': sum(r['blobs_in_git_object_db'] for r in remote)}
    files = [f for row in results for f in row['manifests'].values()]
    index.root_declarations = {
        'remote_roots_verified': len(results), 'root_manifest_files': len(files),
        'projects_with_root_manifest': sum(bool(row['manifests']) for row in results),
        'declarations_by_file': sum(len(f['names']) for f in files),
        'unparsed_lines': sum(f['unparsed_lines'] for f in files),
        'proofs_sha256': PROOFS_SHA, 'results_sha256': sha(canonical(results))}
