import base64
from copy import deepcopy
from pathlib import Path
import ssl
import tempfile
import unittest

from superhunter import product_certificate_review as certs
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT, sha
from superhunter.safe_io import read_artifact, strict_json


class ReleaseCertificateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.proof = strict_json(read_artifact(ROOT, certs.PROOF))
        self.entry = self.proof['bundles']['litesvm']

    def test_signed_leaf_bound_to_its_release_and_timestamp(self):
        report = certs.bound_leaf(self.work, 'leaf.pem', self.entry)
        self.assertEqual(report['sha256'], sha(base64.b64decode(self.entry['certificate_der'])))
        self.assertLessEqual(report['not_before'], report['integrated_time'])
        self.assertLessEqual(report['integrated_time'], report['not_after'])

    def test_wrong_valid_certificate_cannot_authenticate_the_release(self):
        entry = dict(self.entry, certificate_der=self.proof['bundles']['litesvm-linux-x64-gnu']['certificate_der'])
        with self.assertRaisesRegex(EvidenceError, 'does not authenticate'):
            certs.bound_leaf(self.work, 'leaf.pem', entry)

    def test_altered_envelope_rejected(self):
        entry = deepcopy(self.entry)
        entry['envelope']['payload'] = base64.b64encode(b'{}').decode()
        with self.assertRaisesRegex(EvidenceError, 'does not authenticate'):
            certs.bound_leaf(self.work, 'leaf.pem', entry)

    def test_attestation_time_outside_signing_window_rejected(self):
        with self.assertRaisesRegex(EvidenceError, 'timestamp'):
            certs.bound_leaf(self.work, 'leaf.pem', dict(self.entry, integrated_time=0))

    def test_chain_requires_intermediate_at_archived_time(self):
        (self.work / 'root.pem').write_text(self.proof['fulcio_root_pem'])
        (self.work / 'intermediate.pem').write_text(self.proof['fulcio_intermediate_pem'])
        report = certs.bound_leaf(self.work, 'leaf.pem', self.entry)
        when = report['integrated_time']
        self.assertEqual(certs.decision(self.work, 'leaf.pem', 'root.pem', when), 'issuer_unavailable_at_depth_0')
        self.assertEqual(certs.decision(self.work, 'leaf.pem', 'root.pem', when, intermediate=True), 'accepted')
        self.assertEqual(certs.decision(self.work, 'leaf.pem', 'root.pem', report['not_after'] + 1, intermediate=True),
                         'expired_at_depth_0')

    def test_malformed_or_duplicate_store_is_rejected(self):
        raw = self.proof['fulcio_root_pem'].encode()
        digest = sha(ssl.PEM_cert_to_DER_cert(raw.decode()))
        self.assertEqual(set(certs.public_certificates(raw)), {digest})
        for content in (raw + raw, raw + b'-----BEGIN CERTIFICATE-----', b'not a certificate'):
            with self.subTest(size=len(content)), self.assertRaises(EvidenceError):
                certs.public_certificates(content)
