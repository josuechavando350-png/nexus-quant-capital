import copy
import json
import os
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from superhunter import product_component_controls as controls
from superhunter.product_batches import FIXED_SOURCE_RECEIPTS, receipt, session_operations
from superhunter.product_change_batch import assess
from superhunter.product_header_digest import SOURCE, SOURCE_SHA, variants
from superhunter.product_census_header import pinned
from superhunter.product_native_capabilities import contracts as native_contracts, expected_receipt
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

    def format_index(self):
        observations = json.loads(read_artifact(ROOT, 'superhunter/product_supply/formats-batch.json'))
        repos = {name.casefold(): {'repository': name} for name in (*observations, *self.supply)}
        go_role, go_field, go_receipt = FIXED_SOURCE_RECEIPTS['securego/gosec']
        self.assertEqual(go_role, 'executable')
        repos['securego/gosec'] = {'repository': 'securego/gosec', go_field: copy.deepcopy(go_receipt)}
        capstone = 'capstone-engine/capstone'
        repos[capstone]['native_capability_receipt'] = expected_receipt('static', capstone, native_contracts()['static'])
        return SimpleNamespace(repos=repos, header_digest=None, component_controls=None), observations

    def test_failed_retry_removes_old_component_receipts_but_preserves_other_producers(self):
        idx, observations = self.format_index()
        original_native = copy.deepcopy(idx.repos['capstone-engine/capstone']['native_capability_receipt'])
        original_legacy = copy.deepcopy(idx.repos['securego/gosec'])
        with patch.object(controls, 'import_module', return_value=SimpleNamespace(review=lambda root: observations)):
            controls.attach(idx, ROOT, 'object-format', None)
        self.assertEqual(len(session_operations(idx.repos['capstone-engine/capstone'])), 2)

        def fail(root):
            raise OSError('controlled retry failed')

        with patch.object(controls, 'import_module', return_value=SimpleNamespace(review=fail)):
            controls.attach(idx, ROOT, 'object-format', None)
        self.assertEqual(idx.component_controls['observations'], {})
        self.assertEqual(set(idx.component_controls['blocked']), {'object-format'})
        self.assertTrue(all(controls.FIELD not in row for row in idx.repos.values()))
        self.assertEqual(receipt(idx.repos['radareorg/radare2']), ('pending', None))
        self.assertEqual(receipt(idx.repos['capstone-engine/capstone']), ('executable', 'native_capability_receipt'))
        self.assertEqual(idx.repos['capstone-engine/capstone']['native_capability_receipt'], original_native)
        self.assertEqual(idx.repos['securego/gosec'], original_legacy)

    def test_changed_selection_replaces_receipts_without_retaining_deselected_domains(self):
        idx, observations = self.format_index()
        original_legacy = copy.deepcopy(idx.repos['securego/gosec'])
        original_native = copy.deepcopy(idx.repos['capstone-engine/capstone']['native_capability_receipt'])
        with patch.object(controls, 'import_module', return_value=SimpleNamespace(review=lambda root: observations)):
            controls.attach(idx, ROOT, 'object-format', None)
        with patch.object(controls, 'import_module', return_value=SimpleNamespace(review=lambda root: self.supply)):
            controls.attach(idx, ROOT, 'supply', None)
        self.assertEqual(idx.component_controls['requested'], ['supply'])
        self.assertEqual(idx.component_controls['blocked'], {})
        self.assertEqual(idx.component_controls['observations'], self.supply)
        self.assertEqual({row['repository'] for row in idx.repos.values() if controls.FIELD in row}, set(self.supply))
        self.assertEqual(receipt(idx.repos['radareorg/radare2']), ('pending', None))
        self.assertEqual(receipt(idx.repos['anchore/grype']), ('executable', controls.FIELD))
        self.assertEqual(idx.repos['securego/gosec'], original_legacy)
        self.assertEqual(idx.repos['capstone-engine/capstone']['native_capability_receipt'], original_native)

    def test_failed_cross_domain_validation_does_not_publish_partial_replacement(self):
        idx, observations = self.format_index()
        with patch.object(controls, 'import_module', return_value=SimpleNamespace(review=lambda root: observations)):
            controls.attach(idx, ROOT, 'object-format', None)
        prior_repos = copy.deepcopy(idx.repos)
        prior_report = copy.deepcopy(idx.component_controls)
        with patch.object(controls, 'import_module', return_value=SimpleNamespace(review=lambda root: self.supply)), \
                patch.object(controls, 'reconcile_digest', side_effect=EvidenceError('controlled corroboration failure')):
            with self.assertRaisesRegex(EvidenceError, 'corroboration'):
                controls.attach(idx, ROOT, 'supply', None)
        self.assertEqual(idx.repos, prior_repos)
        self.assertEqual(idx.component_controls, prior_report)

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

    @unittest.skipUnless(os.environ.get('NQC_TEST_PRODUCT_BUNDLE') and os.environ.get('NQC_TRUST_TEST_SOURCES'),
                         'requires the authenticated product bundle and source checkouts')
    def test_real_selective_entry_reports_blocked_and_complete(self):
        from pathlib import Path
        root = Path(os.environ['NQC_TRUST_TEST_SOURCES']).resolve().parent
        command = [sys.executable, '-B', '-m', 'superhunter', 'query-product', '--bundle',
                   os.environ['NQC_TEST_PRODUCT_BUNDLE'], '--control-source-root', str(root), '--component-controls']
        for domain, expected in [('changes', 2), ('android-policy', 0)]:
            with self.subTest(domain=domain):
                proc = subprocess.run([*command, domain, 'component-controls'], cwd=ROOT,
                                      capture_output=True, timeout=30)
                self.assertEqual(proc.returncode, expected, proc.stdout)
                observed = json.loads(proc.stdout)
                self.assertEqual(observed['requested'], [domain])
                self.assertEqual(set(observed['blocked']), {domain} if expected else set())
                self.assertEqual(set(observed['observations']), set() if expected else
                                 {'OWASP/mastg', 'skylot/jadx', 'iBotPeaches/Apktool'})

    def test_diagnostic_must_touch_the_changed_expression(self):
        raw = pinned(ROOT,SOURCE,SOURCE_SHA)
        with self.assertRaisesRegex(EvidenceError, 'diagnostic'):
            assess({}, variants(raw)['changed'], raw, {'rule':'G401','line':24})


if __name__ == '__main__':
    unittest.main()
