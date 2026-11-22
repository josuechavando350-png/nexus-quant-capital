"""Validate real native scanner samples and reject forged or incomplete evidence."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_secrets_native as native
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import canonical, read_artifact, strict_json


class SecretsNativeTests(unittest.TestCase):
    def setUp(self):
        self.pins, self.cases = native.inputs()
        raw = read_artifact(native.ROOT, 'superhunter/product_supply/secrets-native-samples.json')
        self.assertEqual(native.sha(raw), self.pins['native_samples_sha256'])
        self.samples = strict_json(raw)

    def encode(self, producer, rows):
        return canonical(rows) if producer == 'betterleaks' else b''.join(canonical(r) for r in rows)

    def result(self, producer, rows=None, name='positive.env'):
        return native.findings(producer, self.encode(producer, self.samples[producer] if rows is None else rows),
                               name, self.cases)

    def test_native_samples_agree_with_independently_owned_bytes(self):
        sections = {}
        for producer in self.samples:
            result = self.result(producer)
            self.assertEqual(len(result['findings']), 2)
            self.assertTrue(all(r['synthetic'] and r['verification'] == 'disabled' for r in result['findings']))
            self.assertTrue(all(r['native_severity'] is None for r in result['findings']))
            sections[producer] = {'cases': {'positive.env': result}}
        self.assertEqual(native.agreement(sections)['matching_synthetic_findings'], 2)

    def test_empty_results_only_satisfy_clean_and_benign_lookalike_controls(self):
        for producer in self.samples:
            for name in ('clean.env', 'lookalikes.env'):
                with self.subTest(producer=producer, case=name):
                    self.assertEqual(self.result(producer, [], name)['findings'], [])
            with self.assertRaises(EvidenceError):
                self.result(producer, [])

    def test_positive_results_cannot_be_reported_for_clean_inputs(self):
        for producer in self.samples:
            for name in ('clean.env', 'lookalikes.env'):
                with self.subTest(producer=producer, case=name), self.assertRaises(EvidenceError):
                    self.result(producer, name=name)

    def test_missing_or_duplicated_findings_are_rejected(self):
        for producer, rows in self.samples.items():
            for changed in (rows[:1], rows + rows[:1]):
                with self.subTest(producer=producer), self.assertRaises(EvidenceError):
                    self.result(producer, changed)

    def test_wrong_detector_value_and_location_are_rejected(self):
        mutations = {
            'betterleaks': [('RuleID', 'generic-api-key'), ('Secret', 'invented'), ('StartLine', True),
                            ('StartColumn', 15), ('EndColumn', 500), ('File', '/etc/passwd')],
            'trufflehog': [('DetectorType', 999), ('DetectorName', 'Unexpected'), ('Raw', 'invented'),
                           ('SourceType', 1), ('DecoderName', 'BASE64')],
        }
        for producer, changes in mutations.items():
            for key, value in changes:
                rows = deepcopy(self.samples[producer])
                rows[0][key] = value
                with self.subTest(producer=producer, field=key), self.assertRaises(EvidenceError):
                    self.result(producer, rows)
        for key, value in [('line', 42), ('line', True), ('file', '../outside.env')]:
            rows = deepcopy(self.samples['trufflehog'])
            rows[0]['SourceMetadata']['Data']['Filesystem'][key] = value
            with self.subTest(field=key), self.assertRaises(EvidenceError):
                self.result('trufflehog', rows)

    def test_verified_or_cached_credentials_cannot_enter_offline_evidence(self):
        for field, value in [('Verified', True), ('Verified', 0), ('VerificationFromCache', True)]:
            rows = deepcopy(self.samples['trufflehog'])
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                self.result('trufflehog', rows)
        rows = deepcopy(self.samples['betterleaks'])
        rows[0]['ValidationStatus'] = 'valid'
        with self.assertRaises(EvidenceError):
            self.result('betterleaks', rows)

    def test_duplicate_json_keys_and_wrong_shapes_are_rejected(self):
        for producer, raw in [('trufflehog', b'{"Verified":false,"Verified":true}'),
                              ('betterleaks', b'[{"RuleID":"a","RuleID":"b"}]'),
                              ('betterleaks', b'{}'), ('trufflehog', b'[]'),
                              ('betterleaks', b'[true]')]:
            with self.subTest(producer=producer, raw=raw), self.assertRaises(EvidenceError):
                native.native_rows(producer, raw)

    def test_oversized_native_output_is_rejected(self):
        with self.assertRaisesRegex(EvidenceError, 'artifact limit'):
            native.native_rows('trufflehog', b' ' * native.MAX_BYTES)

    def test_cross_engine_disagreement_is_rejected(self):
        sections = {p: {'cases': {'positive.env': self.result(p)}} for p in self.samples}
        sections['trufflehog']['cases']['positive.env']['findings'][0]['line'] = 42
        with self.assertRaisesRegex(EvidenceError, 'disagree'):
            native.agreement(sections)

    def test_pin_substitution_is_rejected_before_any_execution(self):
        with patch.object(native, 'read_artifact', return_value=b'{}'), \
                patch.object(native.subprocess, 'run') as execute:
            with self.assertRaisesRegex(EvidenceError, 'producer pins'):
                native.run(Path('/unused'))
        execute.assert_not_called()

    def test_modified_binary_is_rejected_before_any_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp)
            (kit/'trufflehog').write_bytes(b'not the reviewed scanner')
            with patch.object(native.subprocess, 'run') as execute:
                with self.assertRaisesRegex(EvidenceError, 'release digest mismatch'):
                    native.run(kit)
            execute.assert_not_called()
