"""Produce CycloneDX inventories from fixed local Census and SuperHunter manifests."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import tomllib

from . import bundle_recovery, owned_capture, product_review
from .privacy import PrivateArgumentParser
from .product_census_graph import capture_manifests
from .product_reasoning import EvidenceError, INPUTS, PROFILES, python_name
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

RELEASE = '13.8.0'
DIGEST = '01f2a7f822449242987942ae81da7464dc9d8eed27ae36d33b0f4ddce95e5b43'
SCOPES = ('census', *PROFILES)


def capture(product):
    files = {src: read_artifact(product_review.ROOT, src) for src in INPUTS.values()}
    files.update(capture_manifests(product_review.ROOT))
    if {p: product_review.sha(raw) for p, raw in files.items()} != product['input_sha256']:
        raise EvidenceError('inputs differ from verified product snapshot')
    return files


def assess(product, inputs, docs):
    counts = {}
    for scope in SCOPES:
        rust = scope == 'census'
        doc = strict_json(docs[scope + '.cdx.json'])
        producers = doc['metadata']['tools']['components']
        if ((doc['bomFormat'], doc['specVersion']) != ('CycloneDX', '1.6') or
                not any((p['name'], p['version']) == ('cdxgen', RELEASE) for p in producers)):
            raise EvidenceError('unexpected CycloneDX format or producer')
        source = 'nqc-census/Cargo.lock' if rust else INPUTS[f'{scope}/requirements.txt']
        required = {(p['name'], p['version']) for p in product['packages'] if p['source'] == source}
        validate_components(doc, scope, required)
        counts[scope] = len(required)
        if rust:
            validate_cargo(doc, product['census_graph'], inputs[source])
    return {'producer': 'cdxgen/cdxgen', 'version': RELEASE, 'release_sha256': DIGEST,
            'product_review_sha256': product_review.sha(canonical(product)), 'package_counts': counts,
            'cargo_edges': product['census_graph']['dependency_edges'],
            'workspace_members': product['census_graph']['workspace_members']}


def validate_components(doc, scope, required):
    rust = scope == 'census'
    ecosystem = 'cargo' if rust else 'pypi'
    root = doc['metadata']['component']
    name, version = ('census', 'workspace') if rust else ('nqc-' + scope, 'latest')
    root_ref = f'pkg:{ecosystem}/{name}@{version}'
    if (root['type'], root['name'], root['version'], root['purl'], root['bom-ref']) != (
            'application', name, version, root_ref, root_ref):
        raise EvidenceError('CycloneDX root disagrees with product scope')
    if not rust and doc['dependencies'] != []:
        raise EvidenceError('Python pin files do not establish dependency edges')

    observed = set()
    for component in doc['components']:
        name = component['name'] if rust else python_name(component['name'])
        version = component['version']
        ref = f'pkg:{ecosystem}/{name}@{version}'
        if (component['purl'] != ref or component['bom-ref'] != ref or ref == root_ref
                or (name, version) in observed):
            raise EvidenceError('invalid or duplicate CycloneDX package identity')
        observed.add((name, version))
    if observed != required:
        raise EvidenceError('CycloneDX packages disagree with product for ' + scope)


def validate_cargo(doc, graph, lock):
    nodes = graph['nodes']
    root = doc['metadata']['component']['bom-ref']
    edges = {'pkg:cargo/'+n['name']+'@'+n['version']: {'pkg:cargo/'+r for r in n['requires']} for n in nodes}
    if root in edges:
        raise EvidenceError('workspace ref collides with package')
    edges[root] = {'pkg:cargo/'+n['name']+'@'+n['version'] for n in nodes if n['workspace_member']}
    seen = {}
    for row in doc['dependencies']:
        target = set(row['dependsOn'])
        if row['ref'] in seen or len(target) != len(row['dependsOn']):
            raise EvidenceError('duplicate CycloneDX dependency record')
        seen[row['ref']] = target
    if seen != edges:
        raise EvidenceError('CycloneDX relationships disagree with Census')
    checksums = {(p['name'], p['version']): p['checksum'] for p in tomllib.loads(lock.decode())['package']
                 if 'checksum' in p}
    for component in doc['components']:
        expected = checksums.get((component['name'], component['version']))
        if expected and [h['content'] for h in component.get('hashes', []) if h['alg'] == 'SHA-256'] != [expected]:
            raise EvidenceError('CycloneDX checksum disagrees with Cargo.lock')


def generate(product_dir, executable, out):
    owned_capture._path(out, new=True)
    if out.resolve().is_relative_to(product_dir.resolve()):
        raise EvidenceError('output must be outside product bundle')
    product = product_review.verify(product_dir)
    inputs = capture(product)
    with tempfile.TemporaryDirectory(prefix='nqc-cdxgen-') as temp:
        work = Path(temp)
        binary = work/'cdxgen'
        product_review.copy_release('cdxgen', executable, binary, DIGEST)
        for path, raw in inputs.items():
            if path.startswith('nqc-census/'):
                dest = work/'census'/path.removeprefix('nqc-census/')
            else:
                profile = Path(path).stem.removeprefix('requirements-')
                dest = work/profile/'requirements.txt'
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        docs = {}
        for scope in SCOPES:
            name = scope+'.cdx.json'
            subprocess.run(['/usr/bin/unshare', '--user', '--map-current-user', '--net', str(binary),
                            '-t', 'rust' if scope == 'census' else 'python', '--no-install-deps', '--no-cache',
                            '--spec-version', '1.6', '--project-name', 'nqc-'+scope, '-o', str(work/name), '.'],
                           cwd=work/scope, env={'HOME': temp, 'TMPDIR': temp, 'PATH': '/usr/bin:/bin',
                                               'FETCH_LICENSE': 'false', 'CARGO_NET_OFFLINE': 'true',
                                               'PIP_NO_INDEX': '1'}, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, check=True)
            docs[name] = read_artifact(work, name)
    result = assess(product, inputs, docs)
    write_new_bundle(out, {**docs, 'inventory.json': canonical(result)})
    return result


def verify_with_files(bundle, product):
    raw, ids = bundle_recovery._capture(bundle)
    if set(raw) != {s+'.cdx.json' for s in SCOPES} | {'inventory.json','COMPLETE.json'}:
        raise EvidenceError('unexpected CycloneDX bundle contents')
    if bundle_recovery.classify(raw)['state'] != 'BUNDLE_BYTES_COMPLETE':
        raise EvidenceError('incomplete CycloneDX bundle')
    result = assess(product, capture(product), raw)
    if canonical(result) != raw['inventory.json'] or bundle_recovery._capture(bundle) != (raw, ids):
        raise EvidenceError('CycloneDX bundle inconsistent')
    return result, raw


def verify(bundle, product):
    return verify_with_files(bundle, product)[0]


def main(argv):
    command, *args = argv
    parser = PrivateArgumentParser(prog='python -m superhunter '+command)
    parser.add_argument('--product', type=Path, required=True)
    producing = command == 'review-product-cdxgen'
    if producing:
        parser.add_argument('--cdxgen', type=Path, required=True)
        parser.add_argument('--out', type=Path, required=True)
    else:
        parser.add_argument('--bundle', type=Path, required=True)
    opts = parser.parse_args(args)
    try:
        result = (generate(opts.product, opts.cdxgen, opts.out) if producing else
                  verify(opts.bundle, product_review.verify(opts.product)))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'CDXGEN_BLOCKED', 'reason': str(exc) if isinstance(exc, EvidenceError)
                          else type(exc).__name__}))
        return 2
