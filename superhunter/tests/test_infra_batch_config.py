from copy import deepcopy
from pathlib import Path
import ssl
import unittest

from superhunter import product_config_batch as config
from superhunter.safe_io import strict_json


class ConfigChecks(unittest.TestCase):
    def setUp(self):
        self.report = strict_json((config.ROOT / 'superhunter/product_supply/infra_batch_config.json').read_bytes())

    def test_workflow_tree_provenance(self):
        self.assertEqual(len(config.workflow_bytes()), self.report[config.CART]['files_parsed'])

    def test_tag_permission_and_exact_revision(self):
        sha = '1' * 40
        source = ('permissions:\n  contents: read\n  id-token: write\njobs:\n'
                  f'    - uses: sample/build@{sha}\n    - uses: sample/test@v1\n')
        parsed = {'actions': {'sample/build@' + sha: True, 'sample/test@v1': False},
                  'permissions': {'contents': 'read', 'id_token': 'write'}}
        self.assertEqual(config.verify_workflow(source, parsed),
                         {'requires_pin_review': ['sample/test@v1'], 'declared_write_scopes': ['id_token']})
        forged = deepcopy(parsed)
        forged['actions']['sample/test@v1'] = True
        with self.assertRaisesRegex(config.EvidenceError, 'disagree'):
            config.verify_workflow(source, forged)

    def test_missing_or_unrecognized_permissions(self):
        with self.assertRaisesRegex(config.EvidenceError, 'independently parsed layout'):
            config.verify_workflow('jobs: {}\n', {})

    def test_no_keys_or_peer_required_to_compare_offers(self):
        normal, versions = config.default_offer()
        narrowed, control = config.default_offer(tls12_only=True)
        self.assertIn(ssl.TLSVersion.TLSv1_3, versions)
        self.assertEqual(control, [ssl.TLSVersion.TLSv1_2])
        self.assertTrue(all(s['protocol'] != 'TLSv1.3' for s in narrowed))
        self.assertGreater(len(normal), len(narrowed))

    def test_reject_malformed_handshake_lengths(self):
        with self.assertRaisesRegex(config.EvidenceError, 'envelope length'):
            config.hello_offers(bytes.fromhex('16 03 03 00 04 01 00 00 01'))
        with self.assertRaisesRegex(config.EvidenceError, 'truncated'):
            config.vector(b'\x00\x04\x01', 0, 2)
        with self.assertRaisesRegex(config.EvidenceError, 'invalid TLS identifier'):
            config.pairs(b'\x13')

    def test_disagreeing_iana_alias_rejected(self):
        normal, versions = config.default_offer()
        with self.assertRaisesRegex(config.EvidenceError, 'cipher identity'):
            config.resolve_profiles(normal, versions, '', {})

    def test_source_compatibility_is_not_a_peer_certificate_validation(self):
        rows = self.report[config.TLS]
        self.assertGreater(len(rows['overlap_by_profile']['modern']), 0)
        self.assertGreater(len(rows['tls12_only_control']['intermediate']), 0)
        self.assertEqual(rows['tls12_only_control']['modern'], [])
