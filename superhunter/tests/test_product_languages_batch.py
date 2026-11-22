"""Control mismatched values, source locations, provider schema and diagnostic identities."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from superhunter import product_languages_batch as batch

RECEIPTS = batch.ROOT/'superhunter/product_supply/languages-batch.json'


class LanguageEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads(RECEIPTS.read_bytes())
        cls.q = batch.quantities(json.loads(batch.pinned(batch.ROOT, batch.FIXTURE, batch.FIXTURE_SHA))['block'])
        cls.sources = batch.variants(batch.pinned(batch.ROOT, batch.SOURCE, batch.SOURCE_SHA))

    def test_evidence_chain_matches_consumed_producer_results(self):
        cpp = self.rows[batch.CPP]['result']
        cc = self.rows[batch.CC]['result']
        self.assertEqual(cc['cppcheck_sha256'], batch.sha(batch.canonical(cpp)))
        self.assertEqual(cpp['comparisons'], 144)
        self.assertEqual(len(cc['source_anchored_keys']), 3)
        self.assertEqual(cc['input_reports'], 6)
        self.assertEqual(self.rows[batch.FSB]['result']['schema_result_sha256'],
                         batch.sha(batch.canonical(self.rows[batch.SPOT]['result'])))
        for project, row in self.rows.items():
            self.assertEqual(row['revision'], batch.PROJECTS[project][1])
            self.assertTrue(all(len(h) == 64 for h in row['upstream_sha256'].values()))

    def native_flags_reference(self):
        # Deliberately use bit_length here independently of struct.pack and the C++ ranges.
        values = [n for _, n in self.q.values()] + list(batch.BOUNDS)
        return [' '.join(''.join('1' if n.bit_length() < b*8 else '0' for b in widths)
                         for widths in batch.MODELS.values()) for n in values]

    def test_ranges_at_all_unsigned_limits(self):
        flags = self.native_flags_reference()
        result = batch.verify_widths('\n'.join(flags), self.q)
        self.assertEqual(result, self.rows[batch.CPP]['result']['incompatible_signed_encodings'])
        self.assertEqual(flags[-1], '000 000 000')
        self.assertEqual(flags[-2], '000 000 000')
        self.assertEqual(flags[-3], '001 011 001')

    def test_rejects_omissions_and_tampered_sign_bound(self):
        flags = self.native_flags_reference()
        for invalid in (flags[:-1], flags + flags[:1], flags[:-1]+['001 011 001']):
            with self.subTest(flag=invalid[-1]), self.assertRaises(batch.EvidenceError):
                batch.verify_widths('\n'.join(invalid), self.q)

    def test_rejects_unsigned_input_above_wire_domain(self):
        block = {key: '0x1' for key, _ in self.q.values()}
        block['number'] = '0x10000000000000000'
        with self.assertRaises(batch.EvidenceError):
            batch.quantities(block)

    def test_rejects_unreviewed_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/batch.PROJECTS[batch.CPP][0]
            subprocess.run(['git', 'init', '--quiet', path], check=True)
            subprocess.run(['git', '-C', path, '-c', 'user.name=NQC', '-c', 'user.email=test@invalid',
                            'commit', '-qm', 'Control', '--allow-empty'], check=True)
            with self.assertRaises(batch.EvidenceError):
                batch.source_files(Path(tmp), batch.CPP, batch.CPP_FILES)

    def test_descriptors_require_expected_position(self):
        raw = b'<FindbugsPlugin><EngineRegistrar/><Detector class="a.D"/><BugPattern type="P"/></FindbugsPlugin>'
        out = batch.descriptor_order(raw)
        self.assertEqual([n.tag for n in out], ['Detector', 'EngineRegistrar', 'BugPattern'])
        with self.assertRaises(batch.EvidenceError):
            batch.descriptor_order(ET.tostring(out))
        with self.assertRaises(batch.EvidenceError):
            batch.descriptor_order(raw.replace(b'<EngineRegistrar/>', b''))

    def test_digest_mapping_rejects_common_mode_and_source_substitution(self):
        names = ['WEAK_MESSAGE_DIGEST_MD5', 'WEAK_MESSAGE_DIGEST_SHA1']
        descriptor = ET.Element('FindbugsPlugin')
        ET.SubElement(descriptor, 'Detector', {'class': 'a.WeakMessageDigestDetector', 'reports': ','.join(names)})
        catalog = ET.Element('MessageCollection')
        for name in names:
            ET.SubElement(descriptor, 'BugPattern', {'type': name, 'category': 'SECURITY', 'cweid': '328'})
            ET.SubElement(ET.SubElement(catalog, 'BugPattern', {'type': name}), 'ShortDescription').text = name
        messages = ET.tostring(catalog)
        self.assertEqual(batch.digest_patterns(descriptor, messages, self.sources)['classification']['changed']['line'], 25)
        with self.assertRaises(batch.EvidenceError):
            batch.digest_patterns(descriptor, messages, {**self.sources, 'original': self.sources['changed']})
        with self.assertRaises(batch.EvidenceError):
            batch.digest_patterns(descriptor, messages, {**self.sources, 'changed': self.sources['changed'] * 2})
        descriptor.find('BugPattern').set('cweid', '999')
        with self.assertRaises(batch.EvidenceError):
            batch.digest_patterns(descriptor, messages, self.sources)
