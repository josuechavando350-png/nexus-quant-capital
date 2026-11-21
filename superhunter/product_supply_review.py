"""Bind GitHub identities and OWASP supply-chain guidance to verified NQC evidence."""
from __future__ import annotations

from collections import Counter
import csv
from importlib.metadata import PackageNotFoundError, version
from io import StringIO
import json
from pathlib import Path
import re
import tempfile

from . import bundle_recovery, owned_capture, product_review
from .privacy import PrivateArgumentParser
from .product_reasoning import EvidenceError
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parents[1]
IDENTITIES = 'superhunter/product_repository_identities.json'
WHEELS = 'superhunter/product_supply/wheels.txt'
IDENTITIES_SHA = '91d057c55906cdd56210f47209b71a7d077e88778dab4e918addc4f33df335d6'
ASVS_COMMIT = '5cf9b032440be53ce345ab3c130fda46ba1ce7a2'
GUIDES_COMMIT = 'c2a1e3e32cec12f27be0a3b1e771ce51288a363e'
UPSTREAM = {'asvs.csv': '98c8fe911b9edb403af8ee05d3ce8201ecac2659e313b053890a62847cdcf680',
            'asvs-guides.md': '8e38f26817ae06165cce695b4a5b5fced030c8f81ce2ef9dc16e778f5f397814'}
CHECKS = {'V15.1.1': 'remediation_deadlines', 'V15.1.2': 'third_party_inventory',
          'V15.2.1': 'component_update_deadlines'}
GUIDES = {'Dependency_Graph_SBOM_Cheat_Sheet.md', 'Software_Supply_Chain_Security_Cheat_Sheet.md',
          'Vulnerable_Dependency_Management_Cheat_Sheet.md'}
LINK_NAME = 'nqc-product-supply-review'
ARTIFACTS = set(UPSTREAM) | {'supply.json', 'supply.link', 'COMPLETE.json'}


def identity_rows(raw, catalog, catalog_raw):
    if product_review.sha(raw) != IDENTITIES_SHA:
        raise EvidenceError('repository identity snapshot digest mismatch')
    snapshot = strict_json(raw)
    rows = snapshot['repositories']
    if (len(rows) != len(catalog) or len({r['github_id'] for r in rows}) != len(rows)
            or any((r['id'], r['full_name'].casefold()) != (p['catalog_id'], p['repository'].casefold())
                   for r, p in zip(rows, catalog))):
        raise EvidenceError('repository identities disagree with product inventory')
    if product_review.sha(catalog_raw) != product_review.CATALOG_SHA:
        raise EvidenceError('catalog digest differs from the reviewed selection')
    declared = strict_json(catalog_raw)['entries']
    results = []
    for row, candidate in zip(rows, declared, strict=True):
        if candidate['id'] != row['id'] or candidate['repository'].casefold() != row['full_name'].casefold():
            raise EvidenceError('catalog ID or name mismatch')
        label = row['spdx']
        state = 'UNDETERMINED' if label in (None, 'NOASSERTION') else (
            'SAME_TEXT' if label == candidate['license'] else 'DIFFERENT_TEXT')
        results.append({**row, 'catalog_license_text': candidate['license'], 'label_comparison': state})
    return results


def guidance(sources, report):
    for name, digest in UPSTREAM.items():
        if product_review.sha(sources[name]) != digest:
            raise EvidenceError('OWASP data differs from pinned upstream')
    sections = {}
    section = None
    for line in sources['asvs-guides.md'].decode().splitlines():
        if line.startswith('#'):
            heading = re.match(r'^### (V\d+\.\d+):', line)
            section = heading[1] if heading else None
        elif section:
            link = re.search(r'\]\(cheatsheets/([\w-]+\.md)\)', line)
            if link and link[1] in GUIDES:
                sections.setdefault(section, []).append(
                    f'https://github.com/OWASP/CheatSheetSeries/blob/{GUIDES_COMMIT}/cheatsheets/{link[1]}')
    rows = []
    for req in csv.DictReader(StringIO(sources['asvs.csv'].decode('utf-8-sig'))):
        key = req['req_id']
        if key not in CHECKS:
            continue
        guides = sections.get(req['section_id'])
        if not guides:
            raise EvidenceError('missing supply guidance for ASVS section')
        row = {'control': key, 'topic': CHECKS[key], 'level': int(req['L']),
               'section': req['section_id'], 'section_guides': guides, 'assessment': 'UNASSESSED'}
        if key == 'V15.1.2':
            row.update(assessment='PARTIAL_INVENTORY_EVIDENCE',
                       evidence={'artifact': 'review.json', 'package_observations': len(report['packages']),
                                 'workspace_members': report['census_graph']['workspace_members']},
                       unchecked=['installed_runtime_inventory', 'supplier_trust', 'continued_maintenance'])
        rows.append(row)
    if [r['control'] for r in rows] != list(CHECKS):
        raise EvidenceError('ASVS controls missing or duplicated')
    return rows


def summarize(product, original, sources):
    identities = read_artifact(ROOT, IDENTITIES)
    catalog = read_artifact(ROOT, product_review.CATALOG)
    rows = identity_rows(identities, product['repositories'], catalog)
    materials = {'catalog.json': catalog, 'identities.json': identities,
                 'wheels.txt': read_artifact(ROOT, WHEELS), **sources,
                 **{'product/' + name: raw for name, raw in original.items()}}
    syft_cvc5 = set(product['tools'])
    if syft_cvc5 != {'anchore/syft', 'cvc5/cvc5'}:
        raise EvidenceError('unexpected product producers')
    evidence = {
        'anchore/syft': {'role': 'executable', 'artifact': 'product/syft.json'},
        'cvc5/cvc5': {'role': 'executable', 'artifact': 'product/solver.json'},
        'in-toto/in-toto': {'role': 'executable', 'version': '3.0.0', 'artifact': 'supply.link'},
        'OWASP/ASVS': {'role': 'reference_data', 'revision': ASVS_COMMIT, 'artifact': 'asvs.csv'},
        'OWASP/CheatSheetSeries': {'role': 'reference_data', 'revision': GUIDES_COMMIT, 'artifact': 'asvs-guides.md'}}
    if not evidence.keys() <= {r['full_name'] for r in rows}:
        raise EvidenceError('producer or data source absent from catalog')
    summary = {'schema_version': 1, 'status': 'PRODUCT_SUPPLY_EVIDENCE',
               'identity_snapshot_date': strict_json(identities)['observed_on'],
               'repository_count': len(rows), 'github_identity_sha256': IDENTITIES_SHA,
               'license_label_counts': dict(Counter(r['label_comparison'] for r in rows)),
               'review_license_ids': [r['id'] for r in rows if r['label_comparison'] != 'SAME_TEXT'],
               'source_roles': evidence, 'integration_counts': dict(Counter(r['role'] for r in evidence.values())),
               'controls': guidance(sources, product), 'signed': False}
    return summary, materials, rows


def python_link(materials, output):
    """Reconstruct the documented unsigned Link semantics without the in-toto package."""
    return {'signatures': [], 'signed': {'_type': 'link', 'name': LINK_NAME,
            'materials': {p: {'sha256': product_review.sha(b)} for p, b in materials.items()},
            'products': {'supply.json': {'sha256': product_review.sha(output)}},
            'byproducts': {}, 'command': [], 'environment': {}}}


def native_link(materials, output):
    try:
        if version('in-toto') != '3.0.0':
            raise EvidenceError('expected in-toto 3.0.0')
        from in_toto.models.link import Link
        from in_toto.models.metadata import Metablock
        from in_toto.runlib import record_artifacts_as_dict
    except (PackageNotFoundError, ImportError) as error:
        raise EvidenceError('install the locked in-toto environment to produce a link') from error
    with tempfile.TemporaryDirectory(prefix='nqc-supply-') as work:
        for name, raw in {**materials, 'supply.json': output}.items():
            path = Path(work)/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        hashes = record_artifacts_as_dict(sorted(materials), base_path=work, exclude_patterns=[])
        products = record_artifacts_as_dict(['supply.json'], base_path=work, exclude_patterns=[])
    link = Metablock(signed=Link(name=LINK_NAME, materials=hashes, products=products)).to_dict()
    if canonical(link) != canonical(python_link(materials, output)):
        raise EvidenceError('in-toto and independent digest calculation disagree')
    return link


def build(product_dir, out, asvs_path, guides_path):
    owned_capture._path(out, new=True)
    if out.resolve().is_relative_to(product_dir.resolve()):
        raise EvidenceError('supply output must be outside the product evidence')
    product, original = product_review.verify_with_files(product_dir)
    sources = {n: read_artifact(path.parent, path.name) for n, path in
               [('asvs.csv', asvs_path), ('asvs-guides.md', guides_path)]}
    summary, materials, _ = summarize(product, original, sources)
    output = canonical(summary)
    link = native_link(materials, output)
    write_new_bundle(out, {**sources, 'supply.json': output, 'supply.link': canonical(link)})
    return summary


def verify_with_lock(bundle, product, original):
    raw, identities = bundle_recovery._capture(bundle)
    if raw.keys() != ARTIFACTS or bundle_recovery.classify(raw)['state'] != 'BUNDLE_BYTES_COMPLETE':
        raise EvidenceError('incomplete or altered supply evidence')
    summary, materials, rows = summarize(product, original, {name: raw[name] for name in UPSTREAM})
    expected = canonical(summary)
    if raw['supply.json'] != expected or raw['supply.link'] != canonical(python_link(materials, expected)):
        raise EvidenceError('supply evidence disagrees with source data or product bytes')
    if bundle_recovery._capture(bundle) != (raw, identities):
        raise EvidenceError('supply evidence changed during verification')
    return (summary, rows), materials['wheels.txt']


def verify(bundle, product, original):
    return verify_with_lock(bundle, product, original)[0]


def main(argv):
    command, *args = argv
    parser = PrivateArgumentParser(prog='python -m superhunter ' + command)
    parser.add_argument('--product', type=Path, required=True)
    if command == 'review-product-supply':
        for name in ('out', 'asvs-csv', 'guide-index'):
            parser.add_argument('--' + name, type=Path, required=True)
    else:
        parser.add_argument('--bundle', type=Path, required=True)
    opts = parser.parse_args(args)
    try:
        if command == 'review-product-supply':
            result = build(opts.product, opts.out, opts.asvs_csv, opts.guide_index)
        else:
            result, _ = verify(opts.bundle, *product_review.verify_with_files(opts.product))
        print(json.dumps({k: result[k] for k in ('status', 'repository_count', 'integration_counts', 'signed')}))
        return 0
    except EvidenceError as error:
        print(json.dumps({'status': 'SUPPLY_REVIEW_BLOCKED', 'reason': str(error)}))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({'status': 'SUPPLY_REVIEW_BLOCKED', 'error_type': type(error).__name__}))
    return 2
