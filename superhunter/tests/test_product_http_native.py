"""Reconciliation tests; recorded native execution has separate replay evidence."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_http_native as native
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT
from superhunter.repository_boundary import git_object
from superhunter.safe_io import read_artifact, strict_json


class HttpNativeTests(unittest.TestCase):
    def setUp(self):
        self.payload, self.bodies = native.inputs()
        record = strict_json(read_artifact(ROOT, 'superhunter/product_supply/http-native-review.json'))
        self.http = record['http']
        self.links = record['link_discovery']['cases']

    def test_recorded_native_controls_still_reconcile(self):
        native.validate_http(self.http, self.payload, self.bodies)
        result = native.validate_links(self.links, self.bodies)
        self.assertEqual(result['route_change']['removed'], ['/api/positions?owner=alice'])
        self.assertEqual(result['parameter_change'], {'removed': ['owner'], 'added': ['account_id']})

    def test_missing_request_or_response_case_is_rejected(self):
        for key, name in [('requests', 'both_lengths'), ('responses', 'corrupt_gzip')]:
            changed = deepcopy(self.http)
            del changed[key][name]
            with self.subTest(key=key), self.assertRaisesRegex(EvidenceError, 'coverage'):
                native.validate_http(changed, self.payload, self.bodies)

    def test_conflicting_framing_cannot_be_forged_as_accepted(self):
        for name in ('both_lengths', 'duplicate_length', 'conflicting_length', 'negative_length',
                     'duplicate_encoding', 'wrong_encoding_order', 'http10_encoding',
                     'invalid_header_name', 'invalid_version'):
            changed = deepcopy(self.http)
            changed['requests'][name] = deepcopy(changed['requests']['clean_get'])
            with self.subTest(name=name), self.assertRaisesRegex(EvidenceError, 'framing'):
                native.validate_http(changed, self.payload, self.bodies)

    def test_clean_request_cannot_be_relabelled_as_error(self):
        changed = deepcopy(self.http)
        changed['requests']['clean_get'] = {'accepted': False, 'error_type': 'ValueError', 'message': 'error'}
        with self.assertRaisesRegex(EvidenceError, 'framing'):
            native.validate_http(changed, self.payload, self.bodies)

    def test_corrupt_response_requires_the_observed_native_rejection(self):
        for field, value in [('accepted', True), ('encoding_error', False), ('message', 'other')]:
            changed = deepcopy(self.http)
            changed['responses']['corrupt_gzip'][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(EvidenceError, 'compressed HTTP'):
                native.validate_http(changed, self.payload, self.bodies)

    def test_decoded_body_must_match_the_original_bytes(self):
        changed = deepcopy(self.http)
        changed['responses']['base']['decoded_body'] += 'fetch("/hidden");'
        with self.assertRaisesRegex(EvidenceError, 'decoding'):
            native.validate_http(changed, self.payload, self.bodies)

    def test_decoder_connection_attempt_is_rejected(self):
        changed = deepcopy(self.http)
        changed['network_events'] = ['socket.connect']
        with self.assertRaisesRegex(EvidenceError, 'offline boundary'):
            native.validate_http(changed, self.payload, self.bodies)

    def test_missing_link_case_or_route_is_rejected(self):
        changed = deepcopy(self.links)
        del changed['no_routes']
        with self.assertRaisesRegex(EvidenceError, 'coverage'):
            native.validate_links(changed, self.bodies)
        changed = deepcopy(self.links)
        changed['base']['links'].pop()
        with self.assertRaisesRegex(EvidenceError, 'route controls'):
            native.validate_links(changed, self.bodies)

    def test_duplicate_route_cannot_inflate_discovery(self):
        changed = deepcopy(self.links)
        changed['duplicates']['links'].append(changed['duplicates']['links'][0])
        with self.assertRaisesRegex(EvidenceError, 'route controls'):
            native.validate_links(changed, self.bodies)

    def test_negative_control_cannot_claim_an_endpoint(self):
        changed = deepcopy(self.links)
        changed['no_routes']['links'] = ['/api/positions?owner=alice']
        with self.assertRaisesRegex(EvidenceError, 'route controls'):
            native.validate_links(changed, self.bodies)

    def test_changed_parameter_and_route_are_required(self):
        changed = deepcopy(self.links)
        changed['changed'] = deepcopy(changed['base'])
        with self.assertRaisesRegex(EvidenceError, 'route controls'):
            native.validate_links(changed, self.bodies)

    def test_finder_requests_or_connection_attempts_are_rejected(self):
        for field, value in [('requests_made', 1), ('visited_urls', ['http://owned.invalid/']),
                             ('network_events', ['socket.__new__', 'socket.connect'])]:
            changed = deepcopy(self.links)
            changed['base'][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(EvidenceError, 'route controls'):
                native.validate_links(changed, self.bodies)

    def test_source_proof_is_pinned_before_execution(self):
        with patch.object(native, 'read_artifact', return_value=b'{}'), \
                patch.object(native.subprocess, 'run') as execute:
            with self.assertRaisesRegex(EvidenceError, 'source proof'):
                native.run(Path('/unused'))
        execute.assert_not_called()

    def test_source_module_changes_and_extra_files_are_rejected(self):
        data = b'# OWNED source verification control\n'
        proof = {'owned': {'python_git_blobs': {'owned/__init__.py': git_object('blob', data)}}}
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            package = work/'lib'/'owned'
            package.mkdir(parents=True)
            (package/'__init__.py').write_bytes(data)
            native.verify_installed(work, proof)
            (package/'__init__.py').write_bytes(data + b'# changed\n')
            with self.assertRaisesRegex(EvidenceError, 'catalog source'):
                native.verify_installed(work, proof)
            (package/'__init__.py').write_bytes(data)
            (package/'extra.py').write_bytes(b'')
            with self.assertRaisesRegex(EvidenceError, 'membership'):
                native.verify_installed(work, proof)
