"""Offline evidence for a single NQC product with potentially distinct Python environments."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from . import bundle_recovery, owned_capture, portfolio_inventory
from .product_census_graph import capture_manifests, census_graph
from .privacy import PrivateArgumentParser
from .product_reasoning import (EvidenceError, INPUTS, PROFILES, declared_facts, isolation_candidates, minimum_partition, observed_facts,
                                pin_conflicts, python_name, solver_input)
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parents[1]
CATALOG = 'superhunter/repositories_200.json'
CATALOG_SHA = 'b09440d99064c283e53acb5f5ee34a62dc59338ad6fe090d4978e2b562806449'
TOOLS = {
    'syft': ('anchore/syft', '1.38.2', 'b569e7d89bf892793e6c5fcab6d847f60780c02c31961eed9f1464d6eb96f30f'),
    'cvc5': ('cvc5/cvc5', '1.3.1', '3ac157cf769c8fbaafe72e16179f062950c55a0537efb2bd15d5bc4d6793b16b'),
}
FILES = {'syft.json', 'solver.json', 'review.json'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def repositories():
    raw = read_artifact(ROOT, CATALOG)
    if sha(raw) != CATALOG_SHA:
        raise EvidenceError('catalog differs from reviewed PR 110')
    historical = {row['repository'].casefold(): row['id']
                  for row in portfolio_inventory.load_portfolio()['entries']}
    tools = {repo: name for name, (repo, _, _) in TOOLS.items()}
    rows = []
    for row in strict_json(raw)['entries']:
        name = row['repository']
        rows.append({'repository': name, 'catalog_id': row['id'], 'category': row['category'],
                     'historical_id': historical.get(name.casefold()), 'review_tool': tools.get(name)})
    return rows


def capture_inputs():
    expected = {Path(p).name for p in INPUTS.values() if p.endswith('.txt')}
    if {p.name for p in (ROOT/'superhunter').glob('requirements-*.txt')} != expected:
        raise EvidenceError('Python profile inventory changed')
    return {dest: read_artifact(ROOT, src) for dest, src in INPUTS.items()}


def copy_release(name, source, dest, expected_digest):
    """Only the private copy with the reviewed upstream digest is executable."""
    digest = hashlib.sha256()
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as original, dest.open('xb') as output:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise EvidenceError(f'{name} must be a regular file')
        total = 0
        while block := original.read(1024 * 1024):
            total += len(block)
            if total > 192 * 1024 * 1024:
                raise EvidenceError(f'{name} exceeds release size limit')
            output.write(block)
            digest.update(block)
    if digest.hexdigest() != expected_digest:
        raise EvidenceError(f'{name} release digest mismatch')
    dest.chmod(0o500)


def copy_tool(name, source, dest):
    copy_release(name, source, dest, TOOLS[name][2])


def run_native(inputs, syft, cvc5):
    with tempfile.TemporaryDirectory(prefix='nqc-product-') as temp:
        work = Path(temp)
        for name, source in [('syft', syft), ('cvc5', cvc5)]:
            copy_tool(name, source, work/name)
        for location, raw in inputs.items():
            dest = work/'inputs'/location
            dest.parent.mkdir(parents=True)
            dest.write_bytes(raw)
        options = dict(cwd=work, env={'HOME': temp, 'XDG_CONFIG_HOME': temp, 'LC_ALL': 'C',
                                       'SYFT_CHECK_FOR_APP_UPDATE': 'false'},
                       stderr=subprocess.PIPE, stdout=subprocess.PIPE, timeout=30, check=True)
        args = [work/'syft', 'scan', 'dir:inputs', '--override-default-catalogers',
                'rust-cargo-lock-cataloger,python-package-cataloger', '-q', '-o', 'syft-json']
        sbom = subprocess.run(args, stdin=subprocess.DEVNULL, **options).stdout
        facts = observed_facts(sbom)
        if facts != declared_facts(inputs):
            raise EvidenceError('SBOM and product pins disagree')
        conflicts = pin_conflicts(facts)
        def solve(count, excluding=None):
            query = solver_input(conflicts, count, excluding=excluding)
            answer = subprocess.run([work/'cvc5', '--lang=smt2'], input=query, **options).stdout.strip()
            if answer not in (b'sat', b'unsat'):
                raise EvidenceError('cvc5 returned an inconclusive result')
            return {'groups': count, 'excluding': excluding, 'query_sha256': sha(query), 'answer': answer.decode()}

        bounds = []
        for count in range(1, len(PROFILES) + 1):
            bounds.append(solve(count))
            if bounds[-1]['answer'] == 'sat':
                break
        isolations = []
        for candidate in isolation_candidates(conflicts):
            isolations.append(solve(1, candidate))
            if isolations[-1]['answer'] == 'sat':
                break
        return sbom, {'minimum': bounds, 'isolation': isolations}


def verify_hypotheses(facts, trials):
    conflicts = pin_conflicts(facts)
    groups = minimum_partition(facts)
    bounds = [{'groups': k, 'excluding': None, 'query_sha256': sha(solver_input(conflicts, k)),
               'answer': 'sat' if k == len(groups) else 'unsat'} for k in range(1, len(groups) + 1)]
    isolations = []
    resolved_by = None
    for profile in isolation_candidates(conflicts):
        remaining = {fact for fact in facts if fact[0] != f'{profile}/requirements.txt'}
        compatible = len(minimum_partition(remaining)) == 1
        isolations.append({'groups': 1, 'excluding': profile,
                           'query_sha256': sha(solver_input(conflicts, 1, excluding=profile)),
                           'answer': 'sat' if compatible else 'unsat'})
        if compatible:
            resolved_by = profile
            break
    if canonical(trials) != canonical({'minimum': bounds, 'isolation': isolations}):
        raise EvidenceError('solver outcomes disagree with direct partition enumeration')
    return conflicts, groups, resolved_by


def review(inputs, manifests, sbom, trials):
    facts = declared_facts(inputs)
    if observed_facts(sbom) != facts:
        raise EvidenceError('SBOM and product pins disagree')
    graph = census_graph(inputs['census/Cargo.lock'], strict_json(sbom), manifests)
    conflicts, groups, resolved_by = verify_hypotheses(facts, trials)
    return {
        'schema_version': 1, 'status': 'EXACT_PINS_CROSSCHECKED',
        'scope': 'Declared versions in six SuperHunter Python profiles and NQC Census Cargo.lock',
        'catalog_sha256': CATALOG_SHA, 'repositories': repositories(),
        'tools': {repo: {'version': version, 'executable_sha256': digest}
                  for repo, version, digest in TOOLS.values()},
        'input_sha256': {**{INPUTS[path]: sha(raw) for path, raw in inputs.items()},
                         **{path: sha(raw) for path, raw in manifests.items()}},
        'census_graph': graph,
        'packages': [{'source': INPUTS[path], 'name': name, 'version': version}
                     for path, name, version in sorted(facts)],
        'conflicting_python_pins': conflicts, 'minimum_python_pin_groups': len(groups),
        'one_valid_grouping': groups, 'solver_trials': trials,
        'profile_whose_isolation_resolves_all_observed_pin_conflicts': resolved_by,
        'claim': 'Minimum for exact direct version pins only; transitive resolution and installation untested.',
    }


def build(out, syft, cvc5):
    owned_capture._path(out, new=True)
    inputs = capture_inputs()
    manifests = capture_manifests(ROOT)
    sbom, trials = run_native(inputs, syft, cvc5)
    result = review(inputs, manifests, sbom, trials)
    if inputs != capture_inputs() or manifests != capture_manifests(ROOT):
        raise EvidenceError('source changed during native review')
    write_new_bundle(out, {'syft.json': sbom, 'solver.json': canonical(trials),
                           'review.json': canonical(result)})
    return result


def verify_with_files(bundle):
    raw, identities = bundle_recovery._capture(bundle)
    if raw.keys() != FILES | {'COMPLETE.json'}:
        raise EvidenceError('incomplete or unexpected evidence files')
    if bundle_recovery.classify(raw)['state'] != 'BUNDLE_BYTES_COMPLETE':
        raise EvidenceError('evidence integrity mismatch')
    inputs = capture_inputs()
    manifests = capture_manifests(ROOT)
    result = review(inputs, manifests, raw['syft.json'], strict_json(raw['solver.json']))
    if canonical(result) != raw['review.json'] or (inputs, manifests) != (capture_inputs(), capture_manifests(ROOT)):
        raise EvidenceError('evidence disagrees with checked out source')
    if bundle_recovery._capture(bundle) != (raw, identities):
        raise EvidenceError('evidence changed during verification')
    return result, raw


def verify(bundle):
    return verify_with_files(bundle)[0]


class ProductIndex:
    """Exact-name lookups over one independently verified, immutable-in-time snapshot."""
    def __init__(self, report, *, supply=None):
        self.repos = {r['repository'].casefold(): r.copy() for r in report['repositories']}
        if supply:
            summary, identities = supply
            for identity in identities:
                row = self.repos[identity['full_name'].casefold()]
                row['github_identity'] = identity
                row['supply_role'] = summary['source_roles'].get(row['repository'])
                if row['repository'] in ('OWASP/ASVS', 'OWASP/CheatSheetSeries'):
                    row['controls'] = summary['controls']
        self.packages = {}
        for fact in report['packages']:
            key = fact['name'].casefold()
            self.packages.setdefault(key, []).append(fact)
        self.graph = {}
        for node in report['census_graph']['nodes']:
            self.graph.setdefault(node['name'].casefold(), []).append(node)
        self.conflicts = report['conflicting_python_pins']
        self.tools = report['tools']
        self.groups = report['minimum_python_pin_groups']
        self.isolate = report['profile_whose_isolation_resolves_all_observed_pin_conflicts']
        self.observations = len(report['packages'])

    def lookup(self, query):
        key = query.strip().casefold()
        if '/' in key:
            row = self.repos.get(key)
            if not row or not row['review_tool']:
                return row
            if row['review_tool'] == 'syft':
                evidence = {'artifact': 'syft.json', 'package_observations': self.observations}
            else:
                evidence = {'artifact': 'solver.json', 'minimum_python_pin_groups': self.groups,
                            'isolate_profile': self.isolate}
            return {**row, **self.tools[row['repository']], 'evidence': evidence}
        normalized = python_name(key)
        facts = self.packages.get(key, [])
        if normalized != key:
            facts = [*facts, *(f for f in self.packages.get(normalized, []) if f['source'].endswith('.txt'))]
        if facts:
            return {'pins': facts, 'python_profile_conflict': self.conflicts.get(normalized),
                    'census_dependencies': self.graph.get(key, [])}
        return None


def main(argv):
    command, *args = argv
    parser = PrivateArgumentParser(prog=f'python -m superhunter {command}')
    if command == 'review-product':
        for name in ('out', 'syft', 'cvc5'):
            parser.add_argument('--' + name, type=Path, required=True)
    else:
        parser.add_argument('--bundle', type=Path, required=True)
        if command == 'query-product':
            parser.add_argument('--guac-bundle', type=Path, help='verify GUAC evidence against CycloneDX')
            parser.add_argument('--cdxgen-bundle', type=Path, help='verify CycloneDX evidence for cdxgen')
            parser.add_argument('--supply', type=Path, help='add verified identities and supply evidence')
            parser.add_argument('keys', nargs='*', help='repository or package names; default: lines from stdin')
    opts = parser.parse_args(args)
    try:
        if command == 'review-product':
            result = build(opts.out, opts.syft, opts.cvc5)
        else:
            result, files = verify_with_files(opts.bundle)
        if command == 'query-product':
            supply = None
            if opts.supply:
                from . import product_supply_review
                supply = product_supply_review.verify(opts.supply, result, files)
            index = ProductIndex(result, supply=supply)
            if opts.cdxgen_bundle:
                from .product_cdxgen import verify_with_files as verify_cdxgen
                evidence, cdx_files = verify_cdxgen(opts.cdxgen_bundle, result)
                index.repos['cdxgen/cdxgen']['cyclonedx_evidence'] = evidence
            if opts.guac_bundle:
                from . import product_guac
                if not opts.cdxgen_bundle:
                    raise EvidenceError('GUAC verification requires --cdxgen-bundle')
                docs = {name: raw for name, raw in cdx_files.items() if name.endswith('.cdx.json')}
                index.repos['guacsec/guac']['guac_evidence'] = product_guac.verify(opts.guac_bundle, docs)
            for key in opts.keys or sys.stdin:
                print(json.dumps(index.lookup(key), sort_keys=True), flush=True)
        else:
            print(json.dumps({'status': result['status'], 'catalog_count': len(result['repositories']),
                              'native_tools': list(result['tools']), 'observations': len(result['packages']),
                              'conflicts': result['conflicting_python_pins'],
                              'census_edges': result['census_graph']['dependency_edges'],
                              'minimum_python_pin_groups': result['minimum_python_pin_groups'],
                              'isolate_profile': result['profile_whose_isolation_resolves_all_observed_pin_conflicts']}))
        return 0
    except EvidenceError as error:
        print(json.dumps({'status': 'PRODUCT_REVIEW_BLOCKED', 'reason': str(error)}))
        return 2
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'PRODUCT_REVIEW_BLOCKED', 'error_type': type(error).__name__}))
        return 2
