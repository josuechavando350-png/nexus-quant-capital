"""Compare native GUAC IsDependency output to seven verified local CycloneDX SBOMs."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from . import bundle_recovery, owned_capture, product_cdxgen, product_review
from .privacy import PrivateArgumentParser
from .product_reasoning import EvidenceError
from .safe_io import canonical, strict_json, write_new_bundle

PINS = {'guacone': 'fb929dfb5a96dc3e5d8c6af52806f565c465662e5de3af42926b886bac1675d2',
        'guacgql': 'afd3231a3fa65933385a7f03caeee11e83120bee095ba23a06e6635242fed534'}
DIRECT = 'CDX BOM Dependency'
HEURISTIC = 'top-level package GUAC heuristic connecting to each file/package'


def package_ref(node):
    namespaces = node['namespaces']
    if len(namespaces) != 1 or namespaces[0]['namespace'] != '' or len(namespaces[0]['names']) != 1:
        raise EvidenceError('ambiguous GUAC package identity')
    name = namespaces[0]['names'][0]
    if len(name['versions']) != 1 or node['type'] not in ('pypi', 'cargo'):
        raise EvidenceError('unexpected GUAC package version')
    purl = name['versions'][0]['purl']
    if not isinstance(purl, str) or not purl.startswith(f"pkg:{node['type']}/"):
        raise EvidenceError('GUAC package type disagrees with PURL')
    return purl


def compare(docs, response):
    expected = Counter()
    for name, raw in docs.items():
        doc = strict_json(raw)
        root = doc['metadata']['component']
        refs = {c['bom-ref']: c['purl'] for c in [root, *doc['components']]}
        origin = 'file:///docs/' + name
        for dep in doc['dependencies']:
            for target in dep['dependsOn']:
                expected[origin, DIRECT, 'DIRECT', refs[dep['ref']], refs[target]] += 1
        for component in doc['components']:
            expected[origin, HEURISTIC, 'UNKNOWN', root['purl'], component['purl']] += 1
    graph = strict_json(response)
    if graph.get('errors'):
        raise EvidenceError('GUAC query returned errors')
    observed = Counter((r['origin'], r['justification'], r['dependencyType'], package_ref(r['package']),
                        package_ref(r['dependencyPackage'])) for r in graph['data']['IsDependency'])
    if observed != expected:
        raise EvidenceError('GUAC dependencies disagree with CycloneDX')
    return {'producer': 'guacsec/guac', 'version': '1.1.0', 'release_sha256': PINS,
            'sbom_sha256': {key: product_review.sha(raw) for key, raw in docs.items()},
            'direct_relations': sum(n for key, n in observed.items() if key[1] == DIRECT),
            'heuristic_relations': sum(n for key, n in observed.items() if key[1] == HEURISTIC)}


def documents(bundle, product):
    _, raw = product_cdxgen.verify_with_files(bundle, product)
    return {scope+'.cdx.json': raw[scope+'.cdx.json'] for scope in product_cdxgen.SCOPES}


def build(docs, guacone, guacgql, out):
    owned_capture._path(out, new=True)
    with tempfile.TemporaryDirectory(prefix='nqc-guac-') as temp:
        work = Path(temp)
        for name, path in [('guacone', guacone), ('guacgql', guacgql)]:
            product_review.copy_release(name, path, work/name, PINS[name])
        (work/'docs').mkdir()
        for name, raw in docs.items():
            (work/'docs'/name).write_bytes(raw)
        worker = Path(__file__).with_name('product_guac_worker.py')
        command = ['/usr/bin/unshare', '--user', '--map-root-user', '--net', '--pid', '--fork',
                   '--kill-child', sys.executable, '-I', str(worker), str(os.stat('/proc/self/ns/net').st_ino)]
        response = subprocess.run(command, cwd=work, env={'HOME': temp, 'PATH': '/usr/bin:/bin'},
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  check=True, timeout=90).stdout
    result = compare(docs, response)
    write_new_bundle(out, {'guac.json': response, 'comparison.json': canonical(result)})
    return result


def verify(bundle, docs):
    raw, ids = bundle_recovery._capture(bundle)
    if set(raw) != {'guac.json', 'comparison.json', 'COMPLETE.json'} or (
            bundle_recovery.classify(raw)['state'] != 'BUNDLE_BYTES_COMPLETE'):
        raise EvidenceError('incomplete GUAC evidence')
    result = compare(docs, raw['guac.json'])
    if canonical(result) != raw['comparison.json'] or bundle_recovery._capture(bundle) != (raw, ids):
        raise EvidenceError('GUAC evidence inconsistent')
    return result


def main(argv):
    command, *args = argv
    parser = PrivateArgumentParser(prog='python -m superhunter '+command)
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--cdxgen-bundle', type=Path, required=True)
    producing = command == 'review-product-guac'
    for name in (('guacone', 'guacgql', 'out') if producing else ('bundle',)):
        parser.add_argument('--'+name, type=Path, required=True)
    opts = parser.parse_args(args)
    try:
        docs = documents(opts.cdxgen_bundle, product_review.verify(opts.product))
        if producing:
            if any(opts.out.resolve().is_relative_to(p.resolve()) for p in (opts.product, opts.cdxgen_bundle)):
                raise EvidenceError('GUAC output must be outside input bundles')
            result = build(docs, opts.guacone, opts.guacgql, opts.out)
        else:
            result = verify(opts.bundle, docs)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'GUAC_BLOCKED', 'reason': str(error) if isinstance(error, EvidenceError)
                          else type(error).__name__}))
        return 2
