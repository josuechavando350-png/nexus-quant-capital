"""Regression checks for the public QA command and metadata derivative."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_report_privacy as privacy


class PrivacyDerivativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = privacy.input_manifests()
        cls.record = cls.records['first']

    def sanitized(self):
        projected = privacy.project(self.record)
        return {'producer': dict(projected['producer']), 'input_fingerprints': ['REDACTED'] * 4,
                'files': [{'path': 'REDACTED', 'sha256': 'REDACTED'} for _ in projected['files']]}

    def test_export_preserves_concrete_producer_and_file_count(self):
        observed = privacy.public_view(self.record, self.sanitized(), 'portable-command')
        self.assertEqual(observed['prepared_file_count'], len(self.record['prepared_files']))
        self.assertEqual(observed['producer']['commit'], self.record['commit'])
        self.assertEqual(observed['command'], 'portable-command')
        self.assertFalse(any(path.encode() in privacy.canonical(observed) for path in self.record['prepared_files']))
        self.assertNotIn(self.record['native_manifest_sha256'].encode(), privacy.canonical(observed))

    def test_two_distinct_manifests_have_matching_minimized_metadata(self):
        other = self.records['second']
        self.assertNotEqual(self.record['native_manifest_sha256'], other['native_manifest_sha256'])
        self.assertEqual(privacy.public_view(self.record, self.sanitized(), 'cmd'),
                         privacy.public_view(other, self.sanitized(), 'cmd'))

    def test_out_of_scope_extra_field_and_partially_masked_fields_are_rejected(self):
        for mutation in ('extra', 'fingerprint', 'nested_path', 'nested_digest', 'absent_file', 'producer_type'):
            masked = self.sanitized()
            if mutation == 'extra':
                masked['message'] = 'NQC-FIXTURE-FOREIGN'
            elif mutation == 'fingerprint':
                masked['input_fingerprints'][0] = self.record['native_manifest_sha256']
            elif mutation == 'nested_path':
                masked['files'][0]['path'] = 'private-path'
            elif mutation == 'nested_digest':
                masked['files'][0]['sha256'] = 'a' * 64
            elif mutation == 'absent_file':
                masked['files'].pop()
            else:
                masked['producer']['checkout_clean_before'] = 1
            with self.subTest(mutation=mutation), self.assertRaises(privacy.EvidenceError):
                privacy.public_view(self.record, masked, 'cmd')

    def test_command_controls_include_selective_preservation_and_masking(self):
        argv = self.record['argv']
        cases, expected = privacy.commands(argv)
        self.assertEqual(cases['recorded'], argv)
        self.assertEqual(expected['recorded'], ' '.join(argv))
        self.assertTrue(expected['benign'].endswith(' --threads 2'))
        for name in ('separate', 'equals', 'attached'):
            self.assertIn('NQC-FIXTURE-', ' '.join(cases[name]))
            self.assertNotIn('NQC-FIXTURE-', expected[name])
            self.assertTrue(expected[name].endswith('<redacted>'))

    def test_public_view_rejects_malformed_file_digest(self):
        changed = copy.deepcopy(self.record)
        changed['prepared_files']['product/review.json'] = 'uncertified'
        with self.assertRaises(privacy.EvidenceError):
            privacy.project(changed)

    def test_reading_unpinned_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / privacy.DOSSIER / 'first'
            folder.mkdir(parents=True)
            (folder / 'run-inputs.json').write_bytes(b'{}')
            with patch.object(privacy, 'ROOT', Path(tmp)), self.assertRaises(privacy.EvidenceError):
                privacy.input_manifests()

    def test_replaced_checkout_is_rejected_before_producer_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / privacy.SOURCES[privacy.DIRSEARCH][0]).symlink_to(root)
            with self.assertRaises(privacy.EvidenceError):
                privacy.upstream(root, privacy.DIRSEARCH)
