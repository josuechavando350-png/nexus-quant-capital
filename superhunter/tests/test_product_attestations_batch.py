import os
from pathlib import Path
import struct
import unittest
from io import BytesIO
from zipfile import ZipFile

from superhunter import product_attestations_batch as a
from superhunter.product_reasoning import EvidenceError


class AndroidGuards(unittest.TestCase):
    def test_missing_archive_member(self):
        data = BytesIO()
        with ZipFile(data, 'w') as z:
            z.writestr('unrelated', b'irrelevant')
        with self.assertRaises(EvidenceError):
            a.manifest(data.getvalue())

    def test_xml_header_fails_closed(self):
        for bad in (b'', b'<xml></xml>', struct.pack('<HHI', 3, 8, 25),
                    struct.pack('<HHIHHI', 3, 8, 16, 1, 0, 0)):
            with self.assertRaises(EvidenceError):
                a.decode(bad, {})

    def test_nested_boolean_is_not_application_evidence(self):
        text = f'E: manifest (line=1)\n  E: application (line=2)\n    E: activity (line=3)\n      A: {a.ANDROID}:debuggable(0x0101000f)=true'
        self.assertEqual(a.native_flags(text, {'debuggable': 0x0101000f}), {})

    def test_native_false_is_distinct_from_absence_and_wrong_resource_id(self):
        text = f'E: manifest (line=1)\n  E: application (line=2)\n    A: {a.ANDROID}:debuggable(0x0101000f)=false'
        self.assertEqual(a.native_flags(text, {'debuggable': 0x0101000f}), {'debuggable': False})
        with self.assertRaises(EvidenceError):
            a.native_flags(text, {'debuggable': 1})


@unittest.skipUnless(os.environ.get('NQC_TRUST_TEST_SOURCES'), 'set NQC_TRUST_TEST_SOURCES to the checkout directory')
class FixedAndroidData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['NQC_TRUST_TEST_SOURCES']).resolve()
        cls.sources = a.source_files(cls.root)

    def test_fresh_receipt_matches_archive(self):
        r = a.review(self.root)
        archive = Path(a.__file__).parent / 'product_supply' / 'attestations-batch-receipt.json'
        self.assertEqual(a.canonical(r), archive.read_bytes())
        self.assertEqual(set(r), set(a.PINS))
        self.assertEqual(len({x['manifest_set_sha256'] for x in r.values()}), 1)
        self.assertEqual(r[a.JADX]['resource_ids'], {'allowBackup': '0x1010280', 'debuggable': '0x101000f'})
        self.assertEqual(r[a.MASTG]['observations']['framework'], dict.fromkeys(r[a.MASTG]['selectors'].values()))

    def test_binary_attribute_type_corruption_rejected(self):
        sources = self.sources
        ids, _ = a.contracts(sources)
        repo, path = a.ARTIFACTS['empty_9patch']
        data = bytearray(a.manifest(sources[repo][path]))
        _, address = a.decode(data, ids)['debuggable']
        data[address-1] = 0x10
        with self.assertRaisesRegex(EvidenceError, 'value type'):
            a.decode(data, ids)

    def test_rule_and_dictionary_disagreement_detected(self):
        sources = self.sources
        bad = {**sources, a.MASTG: dict(sources[a.MASTG])}
        name = a.RULES['debuggable'][0]
        bad[a.MASTG][name] = bad[a.MASTG][name].replace(b'android:debuggable=', b'android:allowBackup=')
        with self.assertRaisesRegex(EvidenceError, 'selector'):
            a.contracts(bad)
