"""Separate direct Cargo package declarations for release review and isolated development workspaces."""
from collections import Counter
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tomllib

from .product_reasoning import EvidenceError
from .product_review import sha
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

SUBJECT = 'rust-fuzz/cargo-fuzz'
REVISION = 'bf2fc668dafda5295aa6fd01825ee67b885f0f2b'
RULE = 'src/project.rs'
RULE_BLOB = '1abc41437a7595b8d04d5324ce2bb58d18ce466e'
CARGO_SHA = 'da77c8b33849312255ccde3179198ada4c8deb370488d050286146b1d1b27e14'
INPUTS = {
    'verus': ('123-verus', 'cc615f27c3d3dec80a83324ed333e48f32d8686c', 'dependencies',
              'd08b4c7a258f71e1f132b81a1ceb38a2a33c0015'),
    'suricata': ('093-suricata', '5c7787ed61adb1aa7a26c23e093992350fc97d62', 'rust/htp',
                 '212166472bbab245f2fb4881f33f588e64e5cc99'),
}


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def rule_fields(source):
    """Read the two pinned Rust predicates that identify an explicitly marked package and its declared binaries."""
    predicates = {}
    for name in ('is_fuzz_manifest', 'collect_targets'):
        match = re.search(rf'^fn {name}\([^\n]+\n(.*?)^}}', source, re.M | re.S)
        require(match is not None, 'expected package classifier missing from pinned source')
        body = match[1]
        predicates[name] = re.findall(r'\.get\("([a-z-]+)"\)', body)
        if name == 'is_fuzz_manifest':
            require('.and_then(toml::Value::as_bool);' in body and 'is_fuzz == Some(true)' in body,
                    'unsupported source marker coercion')
        else:
            require('.and_then(toml::Value::as_array)' in body and '.and_then(toml::Value::as_str)' in body
                    and 'bins.sort();' in body, 'unsupported source binary declaration rule')
    require(predicates == {'is_fuzz_manifest': ['package', 'metadata', 'cargo-fuzz'], 'collect_targets': ['bin', 'name']},
            'source marker field paths changed')
    return predicates


def marked(manifest, fields):
    value = manifest
    for field in fields:
        value = value.get(field) if isinstance(value, dict) else None
    return value is True


def declared_dependencies(manifest):
    records = []
    for target, table in [(None, manifest), *manifest.get('target', {}).items()]:
        for key, kind in (('dependencies', None), ('build-dependencies', 'build'), ('dev-dependencies', 'dev')):
            for alias, value in table.get(key, {}).items():
                package = value.get('package', alias) if isinstance(value, dict) else alias
                records.append((target, kind, package, alias if alias != package else None))
    return Counter(records)


def package(result, manifest_path, manifest):
    selected = [item for item in result['packages'] if item['manifest_path'] == manifest_path]
    require(result['resolve'] is None and len(selected) == 1 and selected[0]['id'] in result['workspace_members'],
            'Cargo package is missing or the report resolved transitives')
    pkg = selected[0]
    cargo_deps = Counter((d['target'], d['kind'], d['name'], d['rename']) for d in pkg['dependencies'])
    require(cargo_deps == declared_dependencies(manifest), 'Cargo and the checked dependency declarations differ')
    require(pkg['name'] == manifest['package']['name'] and pkg['license'] == manifest['package'].get('license'),
            'Cargo package identity or license declaration differs')
    field = manifest['package'].get('publish')
    require(pkg['publish'] == ([] if field is False else field), 'Cargo publishing scope differs')
    require(pkg['metadata'] == manifest['package'].get('metadata'), 'Cargo package metadata differs')
    return {'package_id': pkg['id'], 'normal': {p for _, kind, p, _ in cargo_deps if kind is None},
            'other': {p for _, kind, p, _ in cargo_deps if kind is not None},
            'direct_declarations': sum(cargo_deps.values()), 'publish': pkg['publish'], 'license': pkg['license'],
            'binaries': {t['name'] for t in pkg['targets'] if t['kind'] == ['bin']}}


def review_pair(rules, public, development, public_doc, development_doc, pub_path, dev_path):
    pub = package(public, pub_path, public_doc)
    dev = package(development, dev_path, development_doc)
    require(not marked(public_doc, rules['is_fuzz_manifest']) and marked(development_doc, rules['is_fuzz_manifest']),
            'cannot establish distinct package roles from checked source markers')
    require(pub['publish'] is None and dev['publish'] == [] and pub['package_id'] in public['workspace_default_members']
            and public['workspace_root'] != development['workspace_root']
            and dev['package_id'] not in public['workspace_members']
            and pub['package_id'] not in development['workspace_members'], 'development package is not isolated')
    container, item = rules['collect_targets']
    declared = [b[item] for b in development_doc.get(container, [])]
    require(declared and len(set(declared)) == len(declared) and set(declared) == dev['binaries'],
            'explicit package marker has no independently corroborated set of binary declarations')
    # Package dependency names remain direct declarations. Optional and overlapping
    # names do not establish distribution or transitive dependency resolution.
    return {'release_direct_normal': sorted(pub['normal']),
            'marked_direct_normal_also_in_release_normal': sorted(dev['normal'] & pub['normal']),
            'marked_direct_normal_only_in_release_non_normal': sorted((dev['normal'] - pub['normal']) & pub['other']),
            'marked_direct_normal_absent_from_release_direct_declarations': sorted(dev['normal'] - pub['normal'] - pub['other']),
            'release_direct_declarations_checked': pub['direct_declarations'],
            'development_direct_declarations_checked': dev['direct_declarations'],
            'development_publishing_disabled': True, 'workspace_memberships_disjoint_for_pair': True,
            'explicit_binary_declarations_confirmed': len(declared), 'release_declared_license': pub['license'],
            'development_declared_license': dev['license'], 'license_review': 'pending'}


def verified_checkout(root, folder, revision):
    repo = root / folder
    require(not repo.is_symlink() and git(repo, 'rev-parse', 'HEAD').decode().strip() == revision,
            'Cargo review checkout differs from its pinned revision')
    return repo


def catalog_view(root, spec):
    folder, revision, rel, tree = spec
    repo = verified_checkout(root, folder, revision)
    view = repo / rel
    require(git(repo, 'rev-parse', revision + ':' + rel).decode().strip() == tree and not view.is_symlink(),
            'Cargo subtree differs from the source inventory')
    members = {}
    for entry in git(repo, 'ls-tree', '-rz', tree).split(b'\0'):
        if entry:
            meta, name = entry.split(b'\t')
            mode, kind, blob = meta.decode().split()
            require(mode in ('100644', '100755') and kind == 'blob', 'nonregular entry in Cargo view')
            members[name.decode()] = blob
    files = {p.relative_to(view).as_posix() for p in view.rglob('*') if p.is_symlink() or p.is_file()}
    require(files == set(members) and all(not (view/p).is_symlink() for p in files), 'Cargo member inventory differs')
    manifests = {}
    for path, blob in members.items():
        name = Path(path).name
        if name in ('Cargo.toml', 'Cargo.toml.in', 'Cargo.lock', 'config', 'config.toml'):
            raw = read_artifact(view, path)
            require(git_object('blob', raw) == blob, 'workspace metadata differs from the pinned Git blob')
            if name == 'Cargo.toml':
                manifests[path] = tomllib.loads(raw.decode())
    return view, manifests


def metadata(tool, view, manifest, expect_missing_parent=False):
    # The Cargo process has a read-only input subtree, no rustc and no registry.
    # No target or build script runs during --no-deps metadata inspection.
    command = ['/usr/bin/unshare', '--user', '--map-current-user', '--net', '--', '/usr/bin/bwrap',
               '--die-with-parent', '--new-session', '--cap-drop', 'ALL', '--clearenv',
               '--ro-bind', '/usr', '/usr', '--ro-bind', '/lib', '/lib', '--ro-bind', '/lib64', '/lib64',
               '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--ro-bind', str(tool), '/cargo',
               '--ro-bind', str(view), '/src', '--chdir', '/tmp', '--setenv', 'HOME', '/tmp',
               '--setenv', 'CARGO_HOME', '/tmp/cargo-home', '--setenv', 'RUSTC', '/usr/bin/false',
               '--', '/cargo', 'metadata', '--offline', '--locked', '--no-deps', '--format-version', '1',
               '--manifest-path', '/src/' + manifest]
    proc = subprocess.run(command, capture_output=True, stdin=subprocess.DEVNULL, timeout=12)
    if expect_missing_parent:
        require(proc.returncode == 101 and b'/src/Cargo.toml' in proc.stderr and b'No such file' in proc.stderr
                and not proc.stdout, 'Cargo did not independently establish missing generated parent metadata')
        return None
    require(proc.returncode == 0, 'Cargo metadata could not validate the complete fixture workspace')
    return strict_json(proc.stdout)


def review(root):
    subject = verified_checkout(root, '115-cargo-fuzz', REVISION)
    require(git(subject, 'rev-parse', REVISION + ':' + RULE).decode().strip() == RULE_BLOB, 'Cargo marker source differs')
    raw = git(subject, 'cat-file', 'blob', RULE_BLOB)
    require(git_object('blob', raw) == RULE_BLOB, 'Cargo marker source object differs')
    rules = rule_fields(raw.decode())
    tool = shutil.which('cargo')
    require(tool, 'pinned Cargo metadata reader unavailable')
    with open(tool, 'rb') as stream:
        require(hashlib.file_digest(stream, 'sha256').hexdigest() == CARGO_SHA, 'Cargo metadata reader differs')
    view, files = catalog_view(root, INPUTS['verus'])
    cases = {}
    require(not marked({'package': {'metadata': {'cargo-fuzz': 'true'}}}, rules['is_fuzz_manifest']),
            'text marker was accepted as a boolean')
    for name in ('prettyplease', 'syn'):
        pkg, dev = name + '/Cargo.toml', name + '/fuzz/Cargo.toml'
        a, b = metadata(tool, view, pkg), metadata(tool, view, dev)
        cases[name] = review_pair(rules, a, b, files[pkg], files[dev], '/src/'+pkg, '/src/'+dev)
        merged_membership = dict(a, workspace_members=a['workspace_members'] + b['workspace_members'])
        try:
            review_pair(rules, merged_membership, b, files[pkg], files[dev], '/src/'+pkg, '/src/'+dev)
        except EvidenceError as error:
            require(str(error) == 'development package is not isolated', 'unexpected negative control failure')
        else:
            raise EvidenceError('false development-only classification on overlapping workspaces')
    view, files = catalog_view(root, INPUTS['suricata'])
    unknown = 'fuzz/Cargo.toml'
    require('Cargo.toml' not in files and (view/'Cargo.toml.in').is_file() and marked(files[unknown], rules['is_fuzz_manifest']),
            'missing-parent fixture no longer demonstrates incomplete release metadata')
    metadata(tool, view, unknown, expect_missing_parent=True)
    return {SUBJECT: {'revision': REVISION, 'role': 'reference', 'operation': 'separate_development_manifest_license_review',
        'source_manifest_sha256': sha(canonical({RULE: RULE_BLOB})), 'result': {
            'used_rules': rules, 'fixture_sources': INPUTS, 'cargo_binary_sha256': CARGO_SHA,
            'verified_manifest_pairs': cases, 'incomplete_pair': {
                'project': 'suricata', 'state': 'unknown_missing_generated_parent_manifest',
                'runtime_or_development_dependency_classification': None},
            'scope': 'direct_declarations_of_the_selected_packages', 'transitives_resolved': False,
            'negative_controls': {'string_marker': 'rejected', 'false_separate_membership': 'rejected_for_both_pairs'},
            'harnesses_built_or_executed': 0, 'redistribution_review': 'pending'}}}
