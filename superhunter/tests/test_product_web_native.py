"""Adversarial verifier tests; real native executions are recorded separately."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_web_native as native
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT, sha
from superhunter.repository_boundary import git_object
from superhunter.safe_io import read_artifact, strict_json


class WebNativeTests(unittest.TestCase):
    def setUp(self):
        self.payload, self.packets = native.fixtures()
        record = strict_json(read_artifact(ROOT, 'superhunter/product_supply/web-native-review.json'))
        self.observed = {k: v for k, v in record['observations'].items() if k != 'summary'}

    def check(self, report):
        return native.validate(report, self.payload, self.packets)

    def test_recorded_native_controls_remain_consistent(self):
        result = self.check(self.observed)
        self.assertEqual(result['summary'], {'api_cases': 18, 'accepted_valid': 3,
                         'rejected_invalid': 15, 'complete_packets': 3,
                         'detected_truncated_packets': 1, 'fingerprint_matches': 2,
                         'unknown_banners': 1})
        self.assertEqual(result['captures']['truncated'][-1]['wire_length'] -
                         result['captures']['truncated'][-1]['captured_length'], 7)

    def test_missing_or_duplicated_api_trial_is_rejected(self):
        shortened = deepcopy(self.observed)
        shortened['api_trials'].pop()
        with self.assertRaisesRegex(EvidenceError, 'incomplete API'):
            self.check(shortened)
        duplicated = deepcopy(self.observed)
        duplicated['api_trials'][1] = duplicated['api_trials'][0]
        with self.assertRaisesRegex(EvidenceError, 'API observation'):
            self.check(duplicated)

    def test_bad_response_cannot_be_presented_as_accepted(self):
        for index in (1, 2, 3, 4, 5):
            changed = deepcopy(self.observed)
            changed['api_trials'][index]['valid'] = True
            changed['api_trials'][index]['failure_types'] = []
            with self.subTest(trial=index), self.assertRaisesRegex(EvidenceError, 'API observation'):
                self.check(changed)

    def test_false_positive_on_clean_response_is_rejected(self):
        changed = deepcopy(self.observed)
        changed['api_trials'][0]['valid'] = False
        changed['api_trials'][0]['failure_types'] = ['JsonSchemaError']
        with self.assertRaisesRegex(EvidenceError, 'API observation'):
            self.check(changed)

    def test_wrong_returned_body_status_or_diagnostic_is_rejected(self):
        for field, value in [('body', {}), ('status', 201), ('failure_types', ['UnknownFailure'])]:
            changed = deepcopy(self.observed)
            changed['api_trials'][1][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(EvidenceError, 'API observation'):
                self.check(changed)

    def test_truncation_cannot_be_silently_repaired(self):
        changed = deepcopy(self.observed)
        changed['captures']['truncated'] = deepcopy(changed['captures']['complete'])
        with self.assertRaisesRegex(EvidenceError, 'packet interpretation'):
            self.check(changed)
        changed = deepcopy(self.observed)
        changed['capture_warnings']['truncated'] = []
        with self.assertRaisesRegex(EvidenceError, 'truncation warning'):
            self.check(changed)

    def test_checksum_or_packet_identity_cannot_be_forged(self):
        for field, value in [('tcp_checksum_valid', True), ('body_hex', ''),
                             ('dport', 1), ('server', 'Apache/9.9.9')]:
            changed = deepcopy(self.observed)
            changed['captures']['truncated'][-1][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(EvidenceError, 'packet interpretation'):
                self.check(changed)

    def test_unknown_banner_does_not_inherit_known_fingerprint(self):
        changed = deepcopy(self.observed)
        changed['fingerprints'][-1]['matches'] = changed['fingerprints'][0]['matches']
        with self.assertRaisesRegex(EvidenceError, 'fingerprint controls'):
            self.check(changed)

    def test_fingerprint_version_is_bound_to_the_observed_banner(self):
        changed = deepcopy(self.observed)
        changed['fingerprints'][0]['matches'][0]['parameters']['service.version'] = '2.4.61'
        with self.assertRaisesRegex(EvidenceError, 'fingerprint controls'):
            self.check(changed)

    def test_wrong_producer_version_or_extra_report_section_is_rejected(self):
        changed = deepcopy(self.observed)
        changed['versions']['scapy'] = '2.7.0'
        with self.assertRaisesRegex(EvidenceError, 'versions'):
            self.check(changed)
        changed = deepcopy(self.observed)
        changed['hidden_extra_results'] = []
        with self.assertRaisesRegex(EvidenceError, 'fields'):
            self.check(changed)

    def test_checksum_matches_a_known_internet_checksum_vector(self):
        self.assertEqual(native.checksum(bytes.fromhex('0001f203f4f5f6f7')), 0x220d)

    def test_source_proof_mutation_fails_before_execution(self):
        with patch.object(native, 'read_artifact', return_value=b'{}'), \
                patch.object(native.subprocess, 'run') as execute:
            with self.assertRaisesRegex(EvidenceError, 'source proof differs'):
                native.source_proofs()
        execute.assert_not_called()

    def test_changed_reference_file_cannot_launch_native_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp)
            (kit/'http_servers.xml').write_bytes(b'<fingerprints/>')
            with patch.object(native.subprocess, 'run') as execute:
                with self.assertRaisesRegex(EvidenceError, 'reference differs'):
                    native.run(kit)
            execute.assert_not_called()

    def test_added_missing_and_modified_native_modules_are_rejected(self):
        original = b'# owned source proof control\n'
        proofs = {name: {'python_git_blobs': {name + '/__init__.py': git_object('blob', original)},
                         'git_archive_export_subst': {}} for name in ('scapy', 'schemathesis')}
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for name in proofs:
                (work/'lib'/name).mkdir(parents=True)
                (work/'lib'/name/'__init__.py').write_bytes(original)
            native.verify_installed(work, proofs)
            target = work/'lib'/'scapy'/'__init__.py'
            target.write_bytes(original + b'# changed\n')
            with self.assertRaisesRegex(EvidenceError, 'differs from the catalog'):
                native.verify_installed(work, proofs)
            target.write_bytes(original)
            extra = target.with_name('unexpected.py')
            extra.write_bytes(b'')
            with self.assertRaisesRegex(EvidenceError, 'membership'):
                native.verify_installed(work, proofs)
            extra.unlink()
            target.unlink()
            with self.assertRaisesRegex(EvidenceError, 'membership'):
                native.verify_installed(work, proofs)

    def test_archive_substitution_requires_both_packaged_and_original_bytes(self):
        token = b'$Format:%ct %(describe:tags=true)$'
        original = b"version = '" + token + b"'\n"
        packaged = original.replace(token, b'1234 ')
        proofs = {name: {'python_git_blobs': {}, 'git_archive_export_subst': {
            name + '/__init__.py': {'git_blob': git_object('blob', original),
                'packaged_sha256': sha(packaged), 'archive_substitution': '1234 '}}}
                  for name in ('scapy', 'schemathesis')}
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for name in proofs:
                (work/'lib'/name).mkdir(parents=True)
                (work/'lib'/name/'__init__.py').write_bytes(packaged)
            native.verify_installed(work, proofs)
            proofs['scapy']['git_archive_export_subst']['scapy/__init__.py']['git_blob'] = '0'*40
            with self.assertRaisesRegex(EvidenceError, 'version transformation'):
                native.verify_installed(work, proofs)
