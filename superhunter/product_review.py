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


def copy_release(name, source, dest, expected_digest, *, limit=192 * 1024**2, executable=True):
    """Only the private copy with the reviewed upstream digest is executable."""
    digest = hashlib.sha256()
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as original, dest.open('xb') as output:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise EvidenceError(f'{name} must be a regular file')
        total = 0
        while block := original.read(1024 * 1024):
            total += len(block)
            if total > limit:
                raise EvidenceError(f'{name} exceeds release size limit')
            output.write(block)
            digest.update(block)
    if digest.hexdigest() != expected_digest:
        raise EvidenceError(f'{name} release digest mismatch')
    dest.chmod(0o500 if executable else 0o400)


def copy_tool(name, source, dest):
    copy_release(name, source, dest, TOOLS[name][2])


SYFT_SCAN = ('scan', 'dir:inputs', '--override-default-catalogers',
             'rust-cargo-lock-cataloger,python-package-cataloger', '-q', '-o', 'syft-json')


def stage_inputs(work, inputs):
    for location, raw in inputs.items():
        dest = work/'inputs'/location
        dest.parent.mkdir(parents=True)
        dest.write_bytes(raw)


def run_native(inputs, syft, cvc5):
    with tempfile.TemporaryDirectory(prefix='nqc-product-') as temp:
        work = Path(temp)
        for name, source in [('syft', syft), ('cvc5', cvc5)]:
            copy_tool(name, source, work/name)
        stage_inputs(work, inputs)
        options = dict(cwd=work, env={'HOME': temp, 'XDG_CONFIG_HOME': temp, 'LC_ALL': 'C',
                                       'SYFT_CHECK_FOR_APP_UPDATE': 'false'},
                       stderr=subprocess.PIPE, stdout=subprocess.PIPE, timeout=30, check=True)
        args = [work/'syft', *SYFT_SCAN]
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
    def __init__(self, report, *, supply=None, notices=None):
        self.notices = notices or {}
        self.profile_notices = {}
        self.sbom_locations = {}
        self.similar_notices = None
        self.license_choices = None
        self.owned_source_checks = None
        self.root_declarations = None
        self.source_inventory = None
        self.source_references = None
        self.geth_header = None
        self.census_header = None
        self.upstream_notices = None
        self.solidity_headers = None
        self.citations = None
        self.notice_overlaps = None
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
        if key.startswith('notice-overlaps:'):
            if self.notice_overlaps is None:
                raise EvidenceError('notice overlaps require --pmd-release')
            return self.notice_overlaps.get(key.removeprefix('notice-overlaps:'))
        if key.startswith('notice-context:'):
            if self.citations is None:
                raise EvidenceError('notice contexts require --notice-review-wheels')
            return self.citations.lookup(key.removeprefix('notice-context:'))
        if key == 'integration-matrix':
            from .product_matrix import build
            return build(self)
        if key == 'owned-source-checks':
            if self.owned_source_checks is None:
                raise EvidenceError('owned source checks require --owned-source-kit')
            return self.owned_source_checks
        if key == 'root-declarations':
            if self.root_declarations is None:
                raise EvidenceError('root declarations require --root-manifests')
            return self.root_declarations
        if key == 'source-inventory':
            if self.source_inventory is None:
                raise EvidenceError('source inventory requires --source-inventory')
            return self.source_inventory
        if key == 'source-references':
            if self.source_references is None:
                raise EvidenceError('source reference comparison requires --source-references')
            return self.source_references
        if key == 'geth-census':
            if self.geth_header is None:
                raise EvidenceError('Geth receipt requires --geth-header')
            return self.geth_header
        if key == 'census-header':
            if self.census_header is None:
                raise EvidenceError('Census header replay requires --census-header-kit')
            return self.census_header
        if key == 'upstream-notices':
            if self.upstream_notices is None:
                raise EvidenceError('upstream notices require --upstream-notices')
            return self.upstream_notices
        if key == 'solidity-headers':
            if self.solidity_headers is None:
                raise EvidenceError('Solidity headers require --solidity-metadata-kit')
            return self.solidity_headers
        if key == 'license-choices':
            if self.license_choices is None:
                raise EvidenceError('license choices require --license-proof-kits')
            return self.license_choices
        if key == 'integration-coverage':
            from .product_batches import coverage
            return coverage(self)
        if key in ('batch:1', 'batch:2'):
            from .product_batches import summary
            return summary(self, int(key[-1]))
        if key.startswith('similar:'):
            if self.similar_notices is None:
                raise EvidenceError('notice similarity requires --pgvector-packages and verified wheel notices')
            return self.similar_notices.get(key.removeprefix('similar:').strip())
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
        notice = self.notices.get(normalized)
        profile_notices = self.profile_notices.get(normalized)
        locations = self.sbom_locations.get(normalized)
        if facts or notice or profile_notices or locations:
            result = {'pins': facts, 'python_profile_conflict': self.conflicts.get(normalized),
                      'census_dependencies': self.graph.get(key, [])}
            if notice:
                result['supply_wheel_notices'] = notice
            if profile_notices:
                result['profile_wheel_notices'] = profile_notices
            if locations:
                result['sbom_locations'] = locations
            return result
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
            parser.add_argument('--owned-source-kit', type=Path, help='evaluate fixed owned code and supply declarations')
            parser.add_argument('--root-manifests', type=Path, help='verify external root trees and declarative package inputs')
            parser.add_argument('--source-inventory', action='store_true', help='join the reviewed 200-row source audit')
            parser.add_argument('--source-references', type=Path, help='read two pinned type definitions from a source checkout')
            parser.add_argument('--geth-header', type=Path, help='pinned Geth helper to cross-check the Census header')
            parser.add_argument('--census-header-kit', type=Path, help='replay the fixed Census header with three EVM libraries and two specifications')
            parser.add_argument('--upstream-notices', type=Path, help='add 200 verified upstream license documents to the product notice index')
            parser.add_argument('--solidity-metadata-kit', type=Path, help='compare Foundry, Wake and solc metadata on the fixed NQC migration')
            parser.add_argument('--qemu-aarch64', type=Path, help='replay the inventory on ARM64 with QEMU user mode')
            parser.add_argument('--syft-arm64', type=Path, help='pinned ARM64 Syft inventory executable for QEMU')
            parser.add_argument('--proptest-crates', type=Path, help='check batch ordering and duplicate rejection on the actual catalog')
            parser.add_argument('--pmd-release', type=Path, help='locate copied passages in verified public notices')
            parser.add_argument('--notice-review-wheels', type=Path, help='index notice contexts and reconcile wheel declarations')
            parser.add_argument('--osv-license-cache', type=Path, help='check observed identifiers against the offline OSV-Scanner SPDX registry')
            parser.add_argument('--license-proof-kits', type=Path, help='prove minimal SPDX identifier choices with local pinned distributions')
            parser.add_argument('--dependency-track', type=Path, help='parse and group verified SPDX license observations')
            parser.add_argument('--rustsec-crates', type=Path, help='verify RustSec cargo-lock and compare the local package graph')
            parser.add_argument('--scorecard', type=Path, help='check the committed NQC license-file inventory')
            parser.add_argument('--ast-grep', type=Path, help='locate Cargo.lock registry checksums in the Census SBOM')
            parser.add_argument('--pgvector-packages', type=Path, help='compare verified notices in single-user PostgreSQL')
            parser.add_argument('--lief-wheel', type=Path, help='inventory loaders and libraries of pinned producers')
            parser.add_argument('--producer-bin-dir', type=Path, help='directory with registered NQC inventory binaries')
            parser.add_argument('--sarif-sdk', type=Path, help='validate license observations with SARIF Multitool 5.8.0')
            parser.add_argument('--dotnet-runtime', type=Path, help='pinned Linux x64 .NET runtime archive for the validator')
            parser.add_argument('--export-license-sarif', type=Path, help='write the validated SARIF report into a new directory')
            parser.add_argument('--tlc-jar', type=Path, help='enumerate compatible Python profiles using TLC')
            parser.add_argument('--tree-sitter', type=Path, help='locate components and relations in verified SBOM bytes')
            parser.add_argument('--json-grammar', type=Path, help='directory of pinned Tree-sitter JSON parser sources')
            parser.add_argument('--haystack-wheels', type=Path, help='rank matches in verified notices using local BM25+')
            parser.add_argument('--qdrant', type=Path, help='search verified notices with a private Qdrant index')
            parser.add_argument('--guac-bundle', type=Path, help='verify GUAC evidence against CycloneDX')
            parser.add_argument('--cdxgen-bundle', type=Path, help='verify CycloneDX evidence for cdxgen')
            parser.add_argument('--scancode-release', type=Path, help='official ScanCode 32.5.0 Linux Python 3.12 archive')
            parser.add_argument('--cargo-deny', type=Path, help='compare licenses with cargo-deny 0.22.0')
            parser.add_argument('--rust-bin', type=Path, help='directory of the pinned Cargo and rustc binaries')
            parser.add_argument('--cargo-home', type=Path, help='prepopulated offline Cargo home')
            parser.add_argument('--profile-wheels', type=Path, help='inspect digest-pinned wheels across product profiles')
            parser.add_argument('--notice-wheels', type=Path, help='inspect public notices in local supply wheels')
            parser.add_argument('--export-notices', type=Path, help='write verified notices into a new directory')
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
            notices = None
            if opts.notice_wheels and not opts.supply:
                raise EvidenceError('notice inventory requires --supply')
            if opts.export_notices and not (opts.notice_wheels or opts.profile_wheels):
                raise EvidenceError('notice export requires a local wheel inventory')
            if opts.supply:
                from . import product_supply_review
                supply, wheel_lock = product_supply_review.verify_with_lock(opts.supply, result, files)
                if opts.notice_wheels:
                    from .product_notices import collect
                    notices, public_files = collect(opts.notice_wheels, wheel_lock)
            index = ProductIndex(result, supply=supply, notices=notices)
            if opts.census_header_kit:
                from . import product_census_header
                product_census_header.attach(index, opts.census_header_kit)
            if opts.root_manifests:
                from . import product_remote_roots
                product_remote_roots.attach(index, opts.root_manifests)
            if opts.source_inventory:
                from . import product_source_audit
                product_source_audit.attach(index)
            if opts.source_references:
                from . import product_source_references
                product_source_references.attach(index, opts.source_references, opts.solidity_metadata_kit)
            if opts.owned_source_kit:
                from . import product_owned_source_checks
                product_owned_source_checks.attach(index, opts.source_references, opts.owned_source_kit, opts.solidity_metadata_kit)
            if opts.geth_header:
                from . import product_census_header
                product_census_header.attach_geth(index, opts.geth_header)
            if opts.solidity_metadata_kit:
                from . import product_solidity_headers
                product_solidity_headers.attach(index, opts.solidity_metadata_kit)
            scan_files = dict(public_files) if opts.notice_wheels else {}
            if opts.profile_wheels:
                from .product_cdxgen import capture
                from .product_notices import collect_profiles
                index.profile_notices, profile_files = collect_profiles(opts.profile_wheels, capture(result))
                for name, content in profile_files.items():
                    if name in scan_files and scan_files[name] != content:
                        raise EvidenceError('notice filename collision across inventories')
                    scan_files[name] = content
            if opts.scancode_release:
                from .product_licenses import scan
                if not scan_files:
                    raise EvidenceError('ScanCode requires verified wheel notices')
                observations = scan(opts.scancode_release, scan_files)
                index.repos['aboutcode-org/scancode-toolkit']['license_evidence'] = observations
                packages = list((notices or {}).values())
                packages.extend(record for group in index.profile_notices.values() for record in group)
                for package in packages:
                    for notice in package['notices']:
                        notice['detected_expression'] = observations['notices'][notice['file']]['detected_expression']
            cargo_args = (opts.cargo_deny, opts.rust_bin, opts.cargo_home)
            if opts.cargo_deny or opts.cargo_home or (opts.rust_bin and not (opts.rustsec_crates or opts.proptest_crates)):
                from .product_licenses import check_cargo
                if not all(cargo_args):
                    raise EvidenceError('cargo-deny requires --cargo-deny, --rust-bin and --cargo-home together')
                index.repos['embarkstudios/cargo-deny']['license_evidence'] = check_cargo(*cargo_args, result)
            if opts.qemu_aarch64 or opts.syft_arm64:
                from .product_arm_inventory import build as replay_arm
                if not (opts.qemu_aarch64 and opts.syft_arm64):
                    raise EvidenceError('ARM inventory requires --qemu-aarch64 and --syft-arm64')
                index.repos['qemu/qemu']['arm_inventory_evidence'] = replay_arm(opts.qemu_aarch64, opts.syft_arm64, result)
            if opts.rustsec_crates or opts.ast_grep:
                lock = read_artifact(ROOT, INPUTS['census/Cargo.lock'])
                if sha(lock) != result['input_sha256'][INPUTS['census/Cargo.lock']]:
                    raise EvidenceError('Cargo.lock differs from verified product snapshot')
            if opts.rustsec_crates:
                from .product_rustsec import build as verify_rustsec_graph
                if not opts.rust_bin:
                    raise EvidenceError('RustSec cargo-lock requires --rust-bin')
                index.repos['rustsec/rustsec']['lock_graph_evidence'] = verify_rustsec_graph(
                    opts.rustsec_crates, opts.rust_bin, lock, result['census_graph'])
            if opts.scorecard:
                from .product_scorecard import build as score_license
                index.repos['ossf/scorecard']['license_file_evidence'] = score_license(opts.scorecard, scan_files)
            if opts.dependency_track:
                from .product_spdx_groups import build as group_licenses
                if not (opts.scancode_release and opts.cargo_deny):
                    raise EvidenceError('Dependency-Track requires ScanCode and cargo-deny observations')
                cargo = index.repos['embarkstudios/cargo-deny']['license_evidence']
                index.repos['dependencytrack/dependency-track']['spdx_group_evidence'] = group_licenses(
                    opts.dependency_track, observations, cargo)
            if opts.osv_license_cache:
                from .product_spdx_ids import build as check_spdx_ids
                if not opts.dependency_track:
                    raise EvidenceError('OSV license identifier check requires --dependency-track')
                evidence = index.repos['dependencytrack/dependency-track']['spdx_group_evidence']
                index.repos['google/osv-scanner']['spdx_identifier_evidence'] = check_spdx_ids(opts.osv_license_cache, evidence)
            if opts.proptest_crates:
                from .product_batch_properties import build as check_batches
                if not opts.rust_bin:
                    raise EvidenceError('batch property checks require --rust-bin')
                index.repos['proptest-rs/proptest']['batch_property_evidence'] = check_batches(
                    opts.proptest_crates, opts.rust_bin, result['repositories'])
            search_files = scan_files
            if opts.upstream_notices:
                from .product_upstream_notices import attach
                upstream = attach(index, opts.upstream_notices)
                if scan_files.keys() & upstream.keys():
                    raise EvidenceError('notice filename collision across product and upstream sources')
                search_files = {**scan_files, **upstream}
            if opts.pmd_release:
                from .product_notice_overlap import build as compare_passages
                summary, index.notice_overlaps = compare_passages(opts.pmd_release, search_files)
                index.repos['pmd/pmd']['notice_passage_evidence'] = summary
            if opts.notice_review_wheels:
                from . import product_notice_decisions
                if not opts.scancode_release:
                    raise EvidenceError('notice context and wheel decisions require --scancode-release')
                wheels = product_notice_decisions.collect_records(notices, index.profile_notices, observations)
                index.citations, contexts, decisions = product_notice_decisions.build(opts.notice_review_wheels, scan_files, wheels)
                index.repos['run-llama/llama_index']['citation_evidence'] = contexts
                index.repos['langchain-ai/langgraph']['wheel_decision_evidence'] = decisions
            if opts.license_proof_kits:
                from .product_native_proofs import build as prove_licenses
                if not opts.dependency_track:
                    raise EvidenceError('license choice proofs require --dependency-track')
                evidence = index.repos['dependencytrack/dependency-track']['spdx_group_evidence']
                index.license_choices, receipts = prove_licenses(opts.license_proof_kits, evidence)
                for name, receipt in receipts.items():
                    index.repos[name.casefold()]['license_choice_evidence'] = receipt
            if opts.pgvector_packages:
                from . import product_notice_similarity
                evidence, index.similar_notices = product_notice_similarity.build(opts.pgvector_packages, scan_files)
                index.repos['pgvector/pgvector']['notice_similarity_evidence'] = evidence
            if opts.lief_wheel or opts.producer_bin_dir:
                from . import product_producer_elf
                if not opts.lief_wheel:
                    raise EvidenceError('producer runtime inventory requires --lief-wheel')
                supplied = {'qdrant': opts.qdrant, 'tree-sitter': opts.tree_sitter, 'cargo-deny': opts.cargo_deny}
                info = product_producer_elf.build(opts.lief_wheel, opts.producer_bin_dir, supplied)
                index.repos['lief-project/lief']['runtime_inventory_evidence'] = info
                for name, binary in info['executables'].items():
                    repo = index.repos[binary['repository'].casefold()]
                    repo.setdefault('inspected_producer_binaries', {})[name] = binary
            if opts.sarif_sdk or opts.dotnet_runtime or opts.export_license_sarif:
                from . import product_license_sarif
                if not (opts.sarif_sdk and opts.dotnet_runtime and opts.profile_wheels and opts.scancode_release
                        and opts.cargo_deny):
                    raise EvidenceError('license SARIF requires SDK, runtime, profile wheels, ScanCode and cargo-deny')
                cargo = index.repos['embarkstudios/cargo-deny']['license_evidence']
                evidence, sarif_files = product_license_sarif.build(opts.sarif_sdk, opts.dotnet_runtime, result,
                                                                   cargo, index.profile_notices, observations, scan_files)
                index.repos['microsoft/sarif-sdk']['sarif_evidence'] = evidence
                if opts.export_license_sarif:
                    owned_capture._path(opts.export_license_sarif, new=True)
                    sources = (opts.bundle, opts.supply, opts.notice_wheels, opts.profile_wheels, opts.cdxgen_bundle,
                               opts.guac_bundle, opts.export_notices)
                    out = opts.export_license_sarif.resolve()
                    if any(out.is_relative_to(p.resolve()) or p.resolve().is_relative_to(out) for p in sources if p):
                        raise EvidenceError('SARIF export overlaps another input or output')
                    write_new_bundle(opts.export_license_sarif, sarif_files)
            if opts.tlc_jar:
                from . import product_profile_states
                index.repos['tlaplus/tlaplus']['profile_grouping_evidence'] = product_profile_states.build(opts.tlc_jar, result)
            if opts.cdxgen_bundle:
                from .product_cdxgen import verify_with_files as verify_cdxgen
                evidence, cdx_files = verify_cdxgen(opts.cdxgen_bundle, result)
                index.repos['cdxgen/cdxgen']['cyclonedx_evidence'] = evidence
            if opts.ast_grep:
                from .product_cargo_hashes import build as verify_hashes
                if not opts.cdxgen_bundle:
                    raise EvidenceError('ast-grep requires the verified Census CycloneDX bundle')
                index.repos['ast-grep/ast-grep']['registry_checksum_evidence'] = verify_hashes(
                    opts.ast_grep, cdx_files['census.cdx.json'], lock)
            if opts.tree_sitter or opts.json_grammar:
                from . import product_sbom_locations
                if not (opts.tree_sitter and opts.json_grammar and opts.cdxgen_bundle):
                    raise EvidenceError('SBOM source locations require --tree-sitter, --json-grammar and --cdxgen-bundle')
                docs = {name: raw for name, raw in cdx_files.items() if name.endswith('.cdx.json')}
                evidence, index.sbom_locations = product_sbom_locations.build(opts.tree_sitter, opts.json_grammar, docs)
                index.repos['tree-sitter/tree-sitter']['sbom_location_evidence'] = evidence
            if opts.guac_bundle:
                from . import product_guac
                if not opts.cdxgen_bundle:
                    raise EvidenceError('GUAC verification requires --cdxgen-bundle')
                docs = {name: raw for name, raw in cdx_files.items() if name.endswith('.cdx.json')}
                index.repos['guacsec/guac']['guac_evidence'] = product_guac.verify(opts.guac_bundle, docs)
            if opts.export_notices:
                owned_capture._path(opts.export_notices, new=True)
                inputs = (opts.bundle, opts.supply, opts.notice_wheels, opts.profile_wheels, opts.cdxgen_bundle, opts.guac_bundle)
                if any(opts.export_notices.resolve().is_relative_to(p.resolve()) for p in inputs if p):
                    raise EvidenceError('notice export overlaps an input directory')
                manifest = {'supply_lock_sha256': sha(wheel_lock), 'packages': notices} if opts.notice_wheels else {}
                if opts.profile_wheels:
                    manifest['profile_packages'] = index.profile_notices
                    manifest['profile_input_sha256'] = {scope: result['input_sha256'][INPUTS[scope + '/requirements.txt']]
                                                        for scope in PROFILES}
                write_new_bundle(opts.export_notices, {**scan_files, 'notices.json': canonical(manifest)})
            from .product_notice_search import serve_queries
            serve_queries(index, opts.keys or sys.stdin, opts.qdrant, opts.haystack_wheels, search_files)
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
