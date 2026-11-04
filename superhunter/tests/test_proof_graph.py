"""Independent checks for local DIABLO/NQC causal proof DAG."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from superhunter.local_lab import execute_local, run_local, verify_local_bundle
from superhunter.proof_graph import build_graph, verify_graph
from superhunter.safe_io import canonical, strict_json


class CausalGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle_bytes = execute_local()

    def setUp(self):
        self.contents = {k: strict_json(v) for k, v in self.bundle_bytes.items()}
        self.cases = self.contents['nqc-results.json']['cases']
        self.entries = self.contents['diablo-audit.json']['entries']
        self.provenance = self.contents['source-provenance.json']['sources']
        self.result = self.contents['lab-result.json']
        self.graph = self.contents['proof-graph.json']

    def build(self):
        return build_graph(self.cases, self.entries, self.provenance, self.result)

    def test_graph_is_rebuilt_exactly(self):
        self.assertEqual(self.build(), self.graph)
        verify_graph(self.graph, cases=self.cases, entries=self.entries,
                     provenance=self.provenance, summary=self.result)

    def test_all_module_links_present(self):
        nodes = self.graph['nodes']
        self.assertEqual(len(nodes), 24)
        self.assertEqual(len({n['id'] for n in nodes}), 24)
        for node in nodes:
            self.assertTrue(set(node['depends_on']).issubset({x['id'] for x in nodes}))
        self.assertEqual(nodes[-1]['id'], 'run:decision')
        self.assertEqual(nodes[-1]['depends_on'], ['diablo:audit'])
        self.assertFalse(self.graph['production_finding'])
        self.assertFalse(self.graph['independently_authenticated'])

    def test_modified_root_rejected(self):
        self.graph['root_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'causal graph mismatch'):
            verify_graph(self.graph, cases=self.cases, entries=self.entries,
                         provenance=self.provenance, summary=self.result)

    def test_removed_dependency_rejected(self):
        self.graph['nodes'][3]['depends_on'] = []
        with self.assertRaisesRegex(ValueError, 'causal graph mismatch'):
            verify_graph(self.graph, cases=self.cases, entries=self.entries,
                         provenance=self.provenance, summary=self.result)

    def test_extra_node_rejected(self):
        self.graph['nodes'].append(deepcopy(self.graph['nodes'][0]))
        with self.assertRaises(ValueError):
            verify_graph(self.graph, cases=self.cases, entries=self.entries,
                         provenance=self.provenance, summary=self.result)

    def test_forged_authentication_claim_rejected(self):
        self.graph['independently_authenticated'] = True
        with self.assertRaises(ValueError):
            verify_graph(self.graph, cases=self.cases, entries=self.entries,
                         provenance=self.provenance, summary=self.result)

    def test_wrong_scope_order_cannot_build_graph(self):
        self.entries[1], self.entries[4] = self.entries[4], self.entries[1]
        with self.assertRaisesRegex(ValueError, 'scope admission'):
            self.build()

    def test_wrong_scope_allow_claim_rejected(self):
        self.entries[1]['data']['decision'] = 'DENY'
        with self.assertRaisesRegex(ValueError, 'scope admission'):
            self.build()

    def test_run_input_audit_binding_required(self):
        self.entries[2]['data']['input_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'NQC input digest'):
            self.build()

    def test_nqc_commitment_audit_binding_required(self):
        self.entries[3]['data']['output_commitment'] = '0x'+'0'*64
        with self.assertRaisesRegex(ValueError, 'NQC result commitment'):
            self.build()

    def test_negative_scope_event_required(self):
        self.entries[16]['data']['decision'] = 'ALLOW'
        with self.assertRaisesRegex(ValueError, 'negative witness'):
            self.build()

    def test_completion_must_not_claim_bug(self):
        self.entries[17]['data']['vulnerability_confirmed'] = True
        with self.assertRaisesRegex(ValueError, 'completion event'):
            self.build()

    def test_provenance_has_both_sources(self):
        self.provenance.pop()
        with self.assertRaisesRegex(ValueError, 'all four pinned sources'):
            self.build()

    def test_cases_cannot_be_silently_removed(self):
        self.cases.pop()
        with self.assertRaisesRegex(ValueError, 'five cases'):
            self.build()

    def test_mix_graphs_of_two_runs_rejected(self):
        other = execute_local()
        other_graph = strict_json(other['proof-graph.json'])
        with self.assertRaises(ValueError):
            verify_graph(other_graph, cases=self.cases, entries=self.entries,
                         provenance=self.provenance, summary=self.result)

    def test_boolean_schema_is_not_integer_version(self):
        self.graph['schema_version'] = True
        with self.assertRaisesRegex(ValueError, 'causal graph mismatch'):
            verify_graph(self.graph, cases=self.cases, entries=self.entries,
                         provenance=self.provenance, summary=self.result)

    def test_numeric_false_is_not_boolean_authentication(self):
        self.graph['independently_authenticated'] = 0
        with self.assertRaisesRegex(ValueError, 'causal graph mismatch'):
            verify_graph(self.graph, cases=self.cases, entries=self.entries,
                         provenance=self.provenance, summary=self.result)

    def test_stored_bundle_receipt_catches_graph_reseal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'case'
            run_local(root)
            graph = strict_json((root/'proof-graph.json').read_bytes())
            graph['production_finding'] = True
            data = canonical(graph)
            (root/'proof-graph.json').write_bytes(data)
            receipt = strict_json((root/'COMPLETE.json').read_bytes())
            receipt['sha256']['proof-graph.json'] = hashlib.sha256(data).hexdigest()
            (root/'COMPLETE.json').write_bytes(canonical(receipt))
            with self.assertRaisesRegex(ValueError, 'causal graph mismatch'):
                verify_local_bundle(root)


if __name__ == '__main__':
    unittest.main()
