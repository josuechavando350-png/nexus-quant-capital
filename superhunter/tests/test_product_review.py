from pathlib import Path
import tempfile
import unittest

from superhunter import product_reasoning as reasoning, product_review as product
from superhunter.safe_io import canonical
from superhunter.product_census_graph import WORKSPACE, census_graph


class ProductTests(unittest.TestCase):
    def test_scoped_catalog_join_and_search(self):
        rows = product.repositories()
        self.assertEqual(len(rows), 200)
        self.assertEqual(len({row['repository'].casefold() for row in rows}), 200)
        self.assertEqual(sum(row['historical_id'] is not None for row in rows), 7)
        self.assertEqual({r['review_tool'] for r in rows if r['review_tool']}, {'syft', 'cvc5'})
        index = product.ProductIndex({'repositories': rows, 'packages': [], 'census_graph': {'nodes': []}, 'conflicting_python_pins': {},
                                      'tools': {r: {'version': v} for r, v, _ in product.TOOLS.values()},
                                      'minimum_python_pin_groups': 2,
                                      'profile_whose_isolation_resolves_all_observed_pin_conflicts': 'owned-spec-evm'})
        self.assertEqual(index.lookup('ANCHORE/SYFT')['catalog_id'], 136)
        self.assertEqual(index.lookup('CVC5/CVC5')['catalog_id'], 41)
        self.assertEqual(index.lookup('cvc5/cvc5')['evidence']['artifact'], 'solver.json')
        self.assertNotIn('evidence', index.lookup('crytic/slither'))
        self.assertIsNone(index.lookup('unlisted/project'))

    def test_triangle_requires_three_groups(self):
        a, b, c = reasoning.PROFILES[:3]
        pins = [(a, 'x', '1'), (b, 'x', '2'), (a, 'y', '1'), (c, 'y', '2'),
                (b, 'z', '1'), (c, 'z', '2')]
        facts = {(p+'/requirements.txt', n, v) for p, n, v in pins}
        groups = reasoning.minimum_partition(facts)
        self.assertEqual(len(groups), 3)
        self.assertEqual(sorted(p for group in groups for p in group), sorted(reasoning.PROFILES))
        self.assertTrue(all(len(set(group) & {a, b, c}) <= 1 for group in groups))
        for profile in (a, b, c):
            remaining = {f for f in facts if f[0] != profile+'/requirements.txt'}
            self.assertEqual(len(reasoning.minimum_partition(remaining)), 2)

    def test_real_source_selects_and_checks_the_isolation_hypothesis(self):
        facts = reasoning.declared_facts(product.capture_inputs())
        conflicts = reasoning.pin_conflicts(facts)
        self.assertEqual(conflicts['cryptography']['owned-spec-evm'], '45.0.7')
        self.assertEqual(reasoning.isolation_candidates(conflicts)[0], 'owned-spec-evm')
        self.assertEqual(len(reasoning.minimum_partition(facts)), 2)
        remaining = {f for f in facts if f[0] != 'owned-spec-evm/requirements.txt'}
        self.assertEqual(len(reasoning.minimum_partition(remaining)), 1)
        self.assertEqual(reasoning.isolation_candidates(reasoning.pin_conflicts(remaining)), [])

    def test_false_solver_verdict_is_rejected(self):
        facts = reasoning.declared_facts(product.capture_inputs())
        conflicts = reasoning.pin_conflicts(facts)
        forged = {'minimum': [{'groups': 1, 'excluding': None, 'answer': 'sat',
                               'query_sha256': product.sha(reasoning.solver_input(conflicts, 1))}],
                  'isolation': []}
        with self.assertRaisesRegex(ValueError, 'direct partition'):
            product.verify_hypotheses(facts, forged)

    def test_overlapping_rust_versions_do_not_create_python_constraints(self):
        facts = {('census/Cargo.lock', 'example', '1'), ('census/Cargo.lock', 'example', '2')}
        self.assertEqual(reasoning.pin_conflicts(facts), {})
        self.assertEqual(len(reasoning.minimum_partition(facts)), 1)

    def test_file_attribution_is_required_even_when_package_and_version_match(self):
        sbom = {'descriptor': {'name': 'syft', 'version': '1.38.2'}, 'schema': {'version': '16.1.0'},
                'artifacts': [{'name': 'test', 'version': '1', 'foundBy': 'python-package-cataloger',
                               'type': 'python', 'locations': [{'path': '/unknown/requirements.txt'}]}]}
        with self.assertRaisesRegex(ValueError, 'outside product'):
            reasoning.observed_facts(canonical(sbom))
        sbom['artifacts'][0]['locations'] = []
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            reasoning.observed_facts(canonical(sbom))

    def test_unsupported_requirement_and_within_profile_duplicates_fail_closed(self):
        for raw in (b'pkg>=1', b'x_a==1\nx-a==2', b'--index-url https://example.invalid'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                reasoning.declared_facts({'custody/requirements.txt': raw})

    def test_search_returns_per_source_evidence_and_unknown_keys(self):
        facts = reasoning.declared_facts(product.capture_inputs())
        report = {'packages': [{'name': n, 'version': v, 'source': reasoning.INPUTS[p]} for p, n, v in facts],
                  'repositories': [], 'census_graph': {'nodes': []}, 'conflicting_python_pins': reasoning.pin_conflicts(facts), 'tools': {},
                  'minimum_python_pin_groups': 2,
                  'profile_whose_isolation_resolves_all_observed_pin_conflicts': 'owned-spec-evm'}
        index = product.ProductIndex(report)
        self.assertEqual(len(index.lookup('CRYPTOGRAPHY')['pins']), 3)
        self.assertEqual(index.lookup('cryptography')['python_profile_conflict']['custody'], '46.0.4')
        self.assertEqual(index.lookup('pydantic_core'), index.lookup('pydantic-core'))
        self.assertTrue(index.lookup('version_check'))
        self.assertIsNone(index.lookup('definitely-absent'))

    def test_graph_edges_require_agreement_from_lock_sbom_and_member_manifest(self):
        lock = b'[[package]]\nname="app"\nversion="1"\ndependencies=["lib"]\n[[package]]\nname="lib"\nversion="2"'
        app = b'[package]\nname="app"\nversion.workspace=true\n[dependencies]\nlib="2"'
        manifests = {WORKSPACE: b'[workspace.package]\nversion="1"', 'crates/app/Cargo.toml': app}
        sbom = {'artifacts': [{'id': n, 'name': n, 'version': v, 'type': 'rust-crate'}
                              for n, v in [('app', '1'), ('lib', '2')]],
                'artifactRelationships': [{'type': 'dependency-of', 'parent': 'lib', 'child': 'app'}]}
        graph = census_graph(lock, sbom, manifests)
        self.assertEqual(graph['dependency_edges'], 1)
        self.assertEqual(graph['nodes'][1]['downstream_workspace_members'], ['app'])
        with self.assertRaisesRegex(ValueError, 'workspace manifest disagrees'):
            census_graph(lock, sbom, {**manifests, 'crates/app/Cargo.toml': app.replace(b'lib=', b'other=')})
        with self.assertRaisesRegex(ValueError, 'edges disagree'):
            census_graph(lock, {**sbom, 'artifactRelationships': []}, manifests)

    def test_unpinned_tool_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wrong = root/'wrong'
            wrong.write_bytes(b'not a release')
            with self.assertRaisesRegex(ValueError, 'release digest mismatch'):
                product.copy_tool('cvc5', wrong, root/'copy')
            self.assertFalse((root/'copy').stat().st_mode & 0o111)


class CdxgenTests(unittest.TestCase):
    def test_python_pin_document_binds_root_component_refs_and_graph(self):
        from copy import deepcopy
        from superhunter.product_cdxgen import validate_components
        root_ref = 'pkg:pypi/nqc-custody@latest'
        ref = 'pkg:pypi/cryptography@46.0.4'
        root = {'type': 'application', 'name': 'nqc-custody', 'version': 'latest',
                'purl': root_ref, 'bom-ref': root_ref}
        doc = {'metadata': {'component': root}, 'dependencies': [], 'components': [
            {'name': 'cryptography', 'version': '46.0.4', 'purl': ref, 'bom-ref': ref}]}
        pins = {('cryptography', '46.0.4')}
        validate_components(doc, 'custody', pins)
        for mutation in ('scope', 'purl', 'alias', 'edge'):
            altered = deepcopy(doc)
            if mutation == 'scope':
                altered['metadata']['component']['name'] = 'nqc-otel-qa'
            elif mutation == 'purl':
                altered['metadata']['component']['purl'] = ref
            elif mutation == 'alias':
                altered['components'][0]['bom-ref'] = root_ref
            else:
                altered['dependencies'] = [{'ref': root_ref, 'dependsOn': [ref]}]
            with self.subTest(mutation=mutation), self.assertRaises(reasoning.EvidenceError):
                validate_components(altered, 'custody', pins)

    def test_cargo_projection_requires_exact_edges_and_checksums(self):
        from superhunter.product_cdxgen import validate_cargo
        checksum = 'a' * 64
        lock = ('[[package]]\nname="dep"\nversion="1"\nchecksum="'+checksum+'"').encode()
        ref = 'pkg:cargo/dep@1'
        doc = {'metadata': {'component': {'bom-ref': 'workspace'}},
               'components': [{'name': 'dep', 'version': '1', 'hashes': [{'alg': 'SHA-256', 'content': checksum}]}],
               'dependencies': [{'ref': ref, 'dependsOn': []}, {'ref': 'workspace', 'dependsOn': [ref]}]}
        graph = {'nodes': [{'name': 'dep', 'version': '1', 'requires': [], 'workspace_member': True}]}
        validate_cargo(doc, graph, lock)
        doc['dependencies'][1]['dependsOn'] = []
        with self.assertRaisesRegex(ValueError, 'relationships'):
            validate_cargo(doc, graph, lock)
        doc['dependencies'][1]['dependsOn'] = [ref]
        doc['components'][0]['hashes'] = []
        with self.assertRaisesRegex(ValueError, 'checksum'):
            validate_cargo(doc, graph, lock)


class GuacTests(unittest.TestCase):
    def test_graph_must_preserve_each_directed_attributed_relation(self):
        from superhunter import product_guac as guac
        root, dep = 'pkg:cargo/workspace@1', 'pkg:cargo/lib@2'
        docs = {'census.cdx.json': canonical({
            'metadata': {'component': {'bom-ref': 'root', 'purl': root}},
            'components': [{'bom-ref': 'child', 'purl': dep}],
            'dependencies': [{'ref': 'root', 'dependsOn': ['child']}]})}

        def node(purl):
            return {'type': 'cargo', 'namespaces': [{'namespace': '', 'names': [
                {'versions': [{'purl': purl}]}]}]}

        direct = {'origin': 'file:///docs/census.cdx.json', 'justification': guac.DIRECT,
                  'dependencyType': 'DIRECT', 'package': node(root), 'dependencyPackage': node(dep)}
        inferred = dict(direct, justification=guac.HEURISTIC, dependencyType='UNKNOWN')

        def compare(edges):
            return guac.compare(docs, canonical({'data': {'IsDependency': edges}}))

        result = compare([inferred, direct])
        self.assertEqual((result['direct_relations'], result['heuristic_relations']), (1, 1))
        inconsistent = dict(direct, package=dict(node(root), type='pypi'))
        with self.assertRaisesRegex(ValueError, 'type disagrees'):
            compare([inferred, inconsistent])
        for change in ([], [direct, direct], [dict(direct, origin='other')],
                       [dict(direct, package=node(dep), dependencyPackage=node(root))],
                       [dict(direct, dependencyType='UNKNOWN')],
                       [dict(direct, dependencyPackage=node(dep + '?source=different'))]):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'dependencies disagree'):
                compare([inferred, *change])
