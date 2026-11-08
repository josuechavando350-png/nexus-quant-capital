"""Registry integrity; preserving requirements does not implement them."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from superhunter import research_plan, quality
from superhunter.safe_io import canonical
from superhunter.project_context import test_inventory


class ResearchPlanTests(unittest.TestCase):
    def test_all_25_preserved(self):
        plan = research_plan.load_plan(components=quality.COMPONENTS)
        self.assertEqual([i['id'] for i in plan['items']], research_plan.EXPECTED)
        self.assertEqual(len(plan['items']), 25)

    def test_three_partial_and_no_complete_claim(self):
        # Historical test ID retained; the current catalog has four bounded partial initiatives.
        plan = research_plan.load_plan()
        self.assertEqual({i['id'] for i in plan['items'] if i['status']=='PARTIAL'},
                         {'OCTANE.R2', 'IMMUNEFI.R2', 'TRAIL_OF_BITS.R1', 'CERTORA.R1', 'IMMUNEFI.D1'})
        self.assertTrue(all(i['status'] in ('PARTIAL','PLANNED') for i in plan['items']))

    def test_partial_tests_exist_in_real_inventory(self):
        plan = research_plan.load_plan(passing_tests=set(test_inventory(quality.ROOT)))
        self.assertEqual(len(plan['items']), 25)

    def test_source_registry_in_snapshot(self):
        self.assertIn('research_initiatives.json', quality.source_snapshot())

    def test_report_contains_each_identifier(self):
        text = research_plan.render_plan(research_plan.load_plan())
        for identifier in research_plan.EXPECTED: self.assertIn(identifier, text)
        self.assertIn('no implementación de 25 motores', text)

    def test_removing_initiative_rejected(self):
        plan = research_plan.load_plan(); plan['items'].pop()
        with patch.object(research_plan,'read_artifact',return_value=canonical(plan)), self.assertRaises(ValueError):
            research_plan.load_plan()

    def test_duplicate_initiative_rejected(self):
        plan = research_plan.load_plan(); plan['items'][1] = deepcopy(plan['items'][0])
        with patch.object(research_plan,'read_artifact',return_value=canonical(plan)), self.assertRaises(ValueError):
            research_plan.load_plan()

    def test_unearned_completion_rejected(self):
        plan = research_plan.load_plan(); plan['items'][0]['status']='COMPLETE'
        with patch.object(research_plan,'read_artifact',return_value=canonical(plan)), self.assertRaises(ValueError):
            research_plan.load_plan()

    def test_partial_without_evidence_rejected(self):
        plan = research_plan.load_plan(); plan['items'][0]['status']='PARTIAL'
        with patch.object(research_plan,'read_artifact',return_value=canonical(plan)), self.assertRaises(ValueError):
            research_plan.load_plan()

    def test_boolean_capability_id_rejected(self):
        plan = research_plan.load_plan(); plan['items'][0]['related_capabilities']=[True]
        with patch.object(research_plan,'read_artifact',return_value=canonical(plan)), self.assertRaises(ValueError):
            research_plan.load_plan()

    def test_wrong_page_rejected(self):
        plan = research_plan.load_plan(); plan['items'][0]['source_page']=3
        with patch.object(research_plan,'read_artifact',return_value=canonical(plan)), self.assertRaises(ValueError):
            research_plan.load_plan()

    def test_unknown_component_rejected(self):
        with self.assertRaisesRegex(ValueError,'COMPONENT_MISSING'):
            research_plan.load_plan(components={})

    def test_passing_receipt_required(self):
        with self.assertRaisesRegex(ValueError,'TEST_NOT_PASSED'):
            research_plan.load_plan(passing_tests=set())

    def test_boolean_schema_rejected(self):
        plan = research_plan.load_plan(); plan['schema_version']=True
        with patch.object(research_plan,'read_artifact',return_value=canonical(plan)), self.assertRaises(ValueError):
            research_plan.load_plan()


if __name__ == '__main__':
    unittest.main()
