"""Adversarial evidence checks; the native clients have a separate real replay."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_discovery_native as native
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT
from superhunter.repository_boundary import git_object
from superhunter.safe_io import read_artifact, strict_json


class DiscoveryNativeTests(unittest.TestCase):
    def setUp(self):
        self.payload = native.inputs()
        record = strict_json(read_artifact(ROOT, 'superhunter/product_supply/discovery-native-review.json'))
        self.observed = record['observations']

    def check(self, record):
        return native.validate(record, self.payload)

    def test_recorded_native_results_reconcile_to_owned_endpoint_oracle(self):
        result = self.check(self.observed)
        self.assertEqual(result['cases']['arjun_live']['parameters'], ['include_closed'])
        self.assertEqual(result['cases']['arjun_clean']['parameters'], [])
        self.assertTrue(result['cases']['gobuster_wild']['refused_wildcard'])

    def test_missing_client_or_negative_control_is_rejected(self):
        for name in ('ffuf_live', 'gobuster_clean', 'gobuster_wild', 'arjun_clean'):
            changed = deepcopy(self.observed)
            del changed['cases'][name]
            with self.subTest(name=name), self.assertRaisesRegex(EvidenceError, 'coverage'):
                self.check(changed)

    def test_missing_route_or_fake_extra_route_is_rejected(self):
        for mutate in ('remove', 'add'):
            changed = deepcopy(self.observed)
            rows = changed['cases']['ffuf_live']['matches']
            if mutate == 'remove':
                rows.pop()
            else:
                rows.append({'path': '/live/missing', 'status': 200, 'bytes': 1})
            with self.subTest(mutation=mutate), self.assertRaisesRegex(EvidenceError, 'endpoint oracle'):
                self.check(changed)

    def test_changed_response_status_or_size_is_rejected(self):
        for field, value in [('status', 404), ('bytes', 0)]:
            changed = deepcopy(self.observed)
            changed['cases']['gobuster_live']['matches'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(EvidenceError, 'endpoint oracle'):
                self.check(changed)

    def test_clean_control_cannot_claim_a_route(self):
        changed = deepcopy(self.observed)
        changed['cases']['ffuf_clean']['matches'] = deepcopy(changed['cases']['ffuf_live']['matches'])
        with self.assertRaisesRegex(EvidenceError, 'endpoint oracle'):
            self.check(changed)

    def test_wildcard_refusal_cannot_be_counted_as_a_match(self):
        changed = deepcopy(self.observed)
        changed['cases']['gobuster_wild']['refused_wildcard'] = False
        with self.assertRaisesRegex(EvidenceError, 'endpoint oracle'):
            self.check(changed)
        changed = deepcopy(self.observed)
        changed['cases']['ffuf_wild']['matches'].append({'path': '/wild/missing', 'status': 200, 'bytes': 27})
        with self.assertRaisesRegex(EvidenceError, 'endpoint oracle'):
            self.check(changed)

    def test_live_parameter_must_be_discovered_and_clean_control_empty(self):
        for name, value in [('arjun_live', []), ('arjun_clean', ['include_closed'])]:
            changed = deepcopy(self.observed)
            changed['cases'][name]['parameters'] = value
            with self.subTest(case=name), self.assertRaisesRegex(EvidenceError, 'endpoint oracle'):
                self.check(changed)

    def test_unexecuted_candidate_cannot_satisfy_coverage(self):
        changed = deepcopy(self.observed)
        changed['cases']['arjun_clean']['audit']['parameter_candidates_requested'].pop()
        with self.assertRaisesRegex(EvidenceError, 'traffic'):
            self.check(changed)

    def test_outside_scope_or_unbounded_traffic_is_rejected(self):
        for field, value in [('only_owned_loopback', False), ('only_expected_path', False),
                             ('within_request_budget', False), ('methods', ['GET', 'POST'])]:
            changed = deepcopy(self.observed)
            changed['cases']['ffuf_live']['audit'][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(EvidenceError, 'traffic'):
                self.check(changed)

    def test_changed_namespace_or_tool_version_is_rejected(self):
        for mutate in ('interface', 'route', 'version'):
            changed = deepcopy(self.observed)
            if mutate == 'interface':
                changed['namespace']['interfaces'].append('eth0')
            elif mutate == 'route':
                changed['namespace']['ipv4_route_count'] = 1
            else:
                changed['versions']['ffuf'] = 'ffuf version: other'
            with self.subTest(mutation=mutate), self.assertRaisesRegex(EvidenceError, 'namespace'):
                self.check(changed)

    def test_binary_modification_is_rejected_before_native_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp)
            (kit/'ffuf').write_bytes(b'not the source-built binary')
            with patch.object(native.subprocess, 'run') as execute:
                with self.assertRaisesRegex(EvidenceError, 'binary digest'):
                    native.run(kit)
            execute.assert_not_called()

    def test_producer_pin_mutation_is_rejected_before_execution(self):
        with patch.object(native, 'read_artifact', return_value=b'{}'), \
                patch.object(native.subprocess, 'run') as execute:
            with self.assertRaisesRegex(EvidenceError, 'producer pins'):
                native.run(Path('/unused'))
        execute.assert_not_called()

    def test_arjun_data_is_verified_as_well_as_code(self):
        files = {'arjun/__init__.py': b'# owned code\n', 'arjun/db/special.json': b'{}\n'}
        proof = {'package_git_blobs': {name: git_object('blob', data) for name, data in files.items()}}
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for name, data in files.items():
                path = work/'lib'/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            self.assertEqual(native.verify_arjun(work, proof), 2)
            (work/'lib/arjun/db/special.json').write_bytes(b'{"changed":1}\n')
            with self.assertRaisesRegex(EvidenceError, 'catalog source'):
                native.verify_arjun(work, proof)
