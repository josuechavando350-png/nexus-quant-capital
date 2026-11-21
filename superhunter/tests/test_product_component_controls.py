import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from superhunter import product_component_controls as controls
from superhunter.product_batches import receipt
from superhunter.product_change_batch import assess
from superhunter.product_header_digest import SOURCE, SOURCE_SHA, variants
from superhunter.product_census_header import pinned
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT
from superhunter.safe_io import read_artifact


class ComponentControlTests(unittest.TestCase):
    def setUp(self):
        self.supply = json.loads(read_artifact(ROOT, 'superhunter/product_supply/trust-batch-receipt.json'))

    def test_rejects_interchanged_rows_for_same_domain(self):
        names = list(self.supply)
        self.supply[names[0]], self.supply[names[1]] = self.supply[names[1]], self.supply[names[0]]
        with self.assertRaisesRegex(EvidenceError, 'revision'):
            controls.validate_group('supply', self.supply)

    def test_rejects_same_revision_with_changed_operation(self):
        self.supply['anchore/grype']['checked_edges'] = 0
        with self.assertRaisesRegex(EvidenceError, 'result'):
            controls.validate_group('supply', self.supply)

    def test_partial_group_does_not_receive_credit(self):
        self.supply.pop('anchore/grype')
        with self.assertRaisesRegex(EvidenceError, 'missing'):
            controls.validate_group('supply', self.supply)

    def test_domain_failure_leaves_other_domains_eligible(self):
        idx = SimpleNamespace(repos={n.casefold(): {'repository':n} for n in self.supply}, header_digest=None)
        def select(name, _):
            if name.endswith('trust_batch'):
                return SimpleNamespace(review=lambda root:self.supply)
            raise ImportError('test missing adapter')
        with patch.object(controls, 'import_module', side_effect=select):
            controls.attach(idx, ROOT, 'all', None)
        self.assertIn('changes', idx.component_controls['blocked'])
        self.assertNotIn('supply', idx.component_controls['blocked'])
        self.assertEqual(set(idx.component_controls['observations']), set(self.supply))
        self.assertEqual(receipt(idx.repos['anchore/grype']), ('executable', controls.FIELD))

    def test_receipt_requires_approved_producer_and_observation(self):
        row = {'repository':'usestrix/strix',controls.FIELD:{'domain':'source-extracts','revision':'0'*40}}
        with self.assertRaises(EvidenceError):
            receipt(row)

    def test_inconsistent_cross_domain_finding_is_rejected(self):
        tax = json.loads(read_artifact(ROOT, 'superhunter/product_supply/languages-batch.json'))
        changes = json.loads(read_artifact(ROOT, 'superhunter/product_supply/owned-change-control.json'))
        go = json.loads(read_artifact(ROOT, 'superhunter/product_supply/review-117.json'))['case_evidence']
        combined = {**tax, **changes}
        self.assertEqual(controls.reconcile_digest(combined, go)['cwe'], '328')
        combined['find-sec-bugs/find-sec-bugs']['result']['classification']['changed']['line'] += 1
        with self.assertRaisesRegex(EvidenceError, 'disagree'):
            controls.reconcile_digest(combined, go)

    def test_diagnostic_must_touch_the_changed_expression(self):
        raw = pinned(ROOT,SOURCE,SOURCE_SHA)
        with self.assertRaisesRegex(EvidenceError, 'diagnostic'):
            assess({}, variants(raw)['changed'], raw, {'rule':'G401','line':24})


if __name__ == '__main__':
    unittest.main()
