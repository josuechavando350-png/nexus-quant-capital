"""Cross-check the declared Census dependency graph and compute downstream consumers."""
from __future__ import annotations

from collections import defaultdict
import re
import tomllib

from .product_reasoning import EvidenceError
from .safe_io import read_artifact


WORKSPACE = 'nqc-census/Cargo.toml'


def capture_manifests(root):
    raw = {WORKSPACE: read_artifact(root, WORKSPACE)}
    members = tomllib.loads(raw[WORKSPACE].decode())['workspace']['members']
    if (not 0 < len(members) <= 128 or len(set(members)) != len(members) or
            not all(re.fullmatch(r'crates/[A-Za-z0-9_-]+', p) for p in members)):
        raise EvidenceError('unsupported Cargo workspace membership')
    for member in members:
        path = f'nqc-census/{member}/Cargo.toml'
        raw[path] = read_artifact(root, path)
    return raw


def census_graph(lock_bytes, sbom, manifests):
    packages = tomllib.loads(lock_bytes.decode())['package']
    by_name = defaultdict(list)
    deps = {}
    for pkg in packages:
        key = (pkg['name'], pkg['version'])
        if key in deps:
            raise EvidenceError('multiple Cargo sources for one name and version')
        by_name[key[0]].append(key)
        deps[key] = set()
    for pkg in packages:
        for ref in pkg.get('dependencies', []):
            fields = ref.split(' ', 2)
            candidates = by_name.get(fields[0], [])
            if len(fields) > 1:
                candidates = [candidate for candidate in candidates if candidate[1] == fields[1]]
            if len(candidates) != 1:
                raise EvidenceError('unresolved or ambiguous Cargo edge')
            deps[(pkg['name'], pkg['version'])].add(candidates[0])

    native = {a['id']: (a['name'], a['version']) for a in sbom['artifacts'] if a['type'] == 'rust-crate'}
    native_edges = set()
    for edge in sbom['artifactRelationships']:
        if edge['type'] == 'dependency-of' and (edge['child'] in native or edge['parent'] in native):
            if not (edge['child'] in native and edge['parent'] in native):
                raise EvidenceError('Cargo dependency edge with an unknown endpoint')
            native_edges.add((native[edge['child']], native[edge['parent']]))
    if set(native.values()) != set(deps) or native_edges != {(p, d) for p, ds in deps.items() for d in ds}:
        raise EvidenceError('Syft dependency edges disagree with Cargo.lock')

    workspace = tomllib.loads(manifests[WORKSPACE].decode())['workspace']
    members = set()
    for path, raw in manifests.items():
        if path == WORKSPACE:
            continue
        manifest = tomllib.loads(raw.decode())
        package = manifest['package']
        version = package['version']
        if version == {'workspace': True}:
            version = workspace['package']['version']
        member = (package['name'], version)
        names = {spec.get('package', name) if isinstance(spec, dict) else name
                 for name, spec in manifest.get('dependencies', {}).items()}
        if member not in deps or {d[0] for d in deps[member]} != names:
            raise EvidenceError('workspace manifest disagrees with locked direct dependencies')
        members.add(member)

    reverse = defaultdict(set)
    for parent, children in deps.items():
        for child in children:
            reverse[child].add(parent)
    rows = []
    for pkg, direct in sorted(deps.items()):
        seen = set()
        pending = list(reverse[pkg])
        while pending:
            parent = pending.pop()
            if parent not in seen:
                seen.add(parent)
                pending.extend(reverse[parent] - seen)
        if pkg in seen:
            raise EvidenceError('cycle in Census lock graph')
        rows.append({'name': pkg[0], 'version': pkg[1], 'workspace_member': pkg in members,
                     'requires': sorted(d[0] + '@' + d[1] for d in direct),
                     'downstream_workspace_members': sorted(p[0] for p in seen & members)})
    return {'nodes': rows, 'dependency_edges': len(native_edges), 'workspace_members': len(members)}
