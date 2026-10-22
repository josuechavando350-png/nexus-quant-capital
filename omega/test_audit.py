"""Negative-first offline architecture integrity tests."""
import copy
import json
import unittest
from pathlib import Path

from audit import verify_plan

PLAN = json.loads((Path(__file__).parent / 'architecture_v3.json').read_text(encoding='utf8'))


class PlanIntegrityTests(unittest.TestCase):
    def test_baseline(self):
        self.assertEqual(verify_plan(PLAN), [])

    def test_removal_blocked(self):
        p = copy.deepcopy(PLAN)
        p['components'].pop()
        self.assertIn('expected_36_components', verify_plan(p))

    def test_duplicate_component_blocked(self):
        p = copy.deepcopy(PLAN)
        p['components'][2]['id'] = 1
        self.assertIn('component_ids_invalid', verify_plan(p))

    def test_wrong_phase_blocked(self):
        p = copy.deepcopy(PLAN)
        p['components'][0]['phase'] = 'Canary'
        self.assertIn('census_components_changed', verify_plan(p))

    def test_signer_permissions_blocked(self):
        p = copy.deepcopy(PLAN)
        p['safety']['observer_can_sign'] = True
        self.assertIn('safety_boundary_broken', verify_plan(p))

    def test_active_workflows_blocked(self):
        p = copy.deepcopy(PLAN)
        p['safety']['legacy_workflows_enabled'] = True
        self.assertIn('safety_boundary_broken', verify_plan(p))

    def test_claim_of_verification_blocked(self):
        p = copy.deepcopy(PLAN)
        p['components'][0]['omega_verification'] = 'certified'
        self.assertIn('unsupported_verification_claim', verify_plan(p))

    def test_missing_gate_blocked(self):
        p = copy.deepcopy(PLAN)
        p['acceptance']['Census'].pop()
        self.assertIn('phase_gates_missing_or_changed', verify_plan(p))

    def test_swapped_shadow_and_canary_blocked(self):
        p = copy.deepcopy(PLAN)
        p['components'][4]['phase'] = 'Shadow'  # ID 5 belongs to Canary
        p['components'][8]['phase'] = 'Canary'  # ID 9 belongs to Shadow
        self.assertIn('component_phase_mismatch', verify_plan(p))

    def test_forged_pdf_digest_blocked(self):
        p = copy.deepcopy(PLAN)
        p['source']['pdf_sha256'] = 'a' * 64
        self.assertIn('source_pdf_sha256_missing', verify_plan(p))

    def test_missing_layer_blocked(self):
        p = copy.deepcopy(PLAN)
        p['components'][0]['layer'] = 'L2'
        # L0 is still represented: verify plan must validate id-specific layer in future.
        # Here we test the coverage rule by removing all L0 labels.
        for component in p['components']:
            if component['layer'] == 'L0':
                component['layer'] = 'L2'
        self.assertIn('layer_coverage_invalid', verify_plan(p))


if __name__ == '__main__':
    unittest.main()
