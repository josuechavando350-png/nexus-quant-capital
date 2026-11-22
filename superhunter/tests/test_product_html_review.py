"""Verify the public review excerpt and real browser captures, including altered documents."""
from copy import deepcopy
from html.parser import HTMLParser
import unittest
from unittest.mock import patch

from superhunter import product_html_review as html
from superhunter.product_native_capabilities import contracts, expected_receipt
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import canonical, read_artifact, strict_json
from superhunter.tools.verify_review_115 import native_bindings, verify


class TextBlocks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tag = None
        self.blocks = {}

    def handle_starttag(self, tag, attrs):
        self.tag = tag if tag in ('h1', 'pre') else None
        if self.tag:
            self.blocks[self.tag] = ''

    def handle_endtag(self, tag):
        if self.tag == tag:
            self.tag = None

    def handle_data(self, data):
        if self.tag:
            self.blocks[self.tag] += data


class HtmlReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.text = html.inputs()
        cls.observed = strict_json(read_artifact(html.ROOT, html.SUPPLY + 'html-review-dom.json'))
        cls.report = strict_json(read_artifact(html.ROOT, html.SUPPLY + 'html-review-result.json'))

    def test_browser_reads_the_existing_renderer_and_distinguishes_two_alterations(self):
        self.assertEqual(html.reconcile(self.observed, self.text), self.report['cases'])
        for case, document in html.documents(self.text).items():
            with self.subTest(case=case):
                parser = TextBlocks()
                parser.feed(document.decode())
                self.assertEqual(self.observed[case]['text'], parser.blocks['pre'])
                self.assertEqual(self.observed[case]['heading'], [parser.blocks['h1']] if 'h1' in parser.blocks else [])
        results = self.report['cases']
        self.assertTrue(results['canonical']['canonical_view'])
        self.assertEqual(results['missing_row']['changed_dom_fields'], ['text'])
        self.assertEqual(results['missing_heading']['changed_dom_fields'], ['bodyChildren', 'heading', 'headingVisible'])

    def test_quality_inventory_selects_the_pinned_driver_and_assigns_one_component(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from superhunter import quality

        driver = 'product_html_review_worker.cjs'
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / driver).write_bytes(read_artifact(html.ROOT, 'superhunter/' + driver))
            snapshot = quality.source_snapshot(root)
        self.assertEqual(snapshot, {driver: html.WORKER_SHA})
        owners = [name for name, component in quality.COMPONENTS.items()
                  for path in quality.component_files(component, snapshot) if path == driver]
        self.assertEqual(owners, ['product_review'])

    def test_each_complete_dom_control_is_required(self):
        for case in self.observed:
            changed = deepcopy(self.observed)
            del changed[case]
            with self.subTest(case=case), self.assertRaisesRegex(EvidenceError, 'missing or unexpected'):
                html.reconcile(changed, self.text)
        changed = deepcopy(self.observed)
        changed['missing_heading'] = changed['canonical']
        with self.assertRaisesRegex(EvidenceError, 'missing_heading'):
            html.reconcile(changed, self.text)

    def test_hidden_content_changed_semantics_or_background_request_is_rejected(self):
        for field, forged in [('text', 'unrelated page'), ('heading', []), ('preVisible', False), ('requests', ['image']),
                              ('activeElements', True), ('documentURL', 'about:srcdoc'), ('csp', '')]:
            changed = deepcopy(self.observed)
            changed['canonical'][field] = forged
            with self.subTest(field=field), self.assertRaisesRegex(EvidenceError, 'canonical'):
                html.reconcile(changed, self.text)

    def test_twelve_group_contract_preserves_eleven_and_credits_one_identity(self):
        eleven = contracts('grpc-eleven')
        full = contracts('html-twelve')
        self.assertEqual({k: v for k, v in full.items() if k != 'html_review'}, eleven)
        self.assertEqual(len(eleven), 11)
        entry = full['html_review']
        self.assertEqual(entry['report_sha256'], html.sha(canonical(self.report)))
        name, = html.REPOSITORIES
        session = {'native-capabilities': {'groups': {'html_review': self.report}, 'repositories': [name],
                   'functional_participations': 1, 'original_vulnerabilities_confirmed': 0,
                   'scope': 'fixed_owned_controls_and_pinned_local_inputs'}}
        self.assertEqual(native_bindings(session), {name: expected_receipt('html_review', name, entry)})
        with self.assertRaisesRegex(EvidenceError, 'group membership'):
            native_bindings(session, version='grpc-eleven')
        with self.assertRaisesRegex(EvidenceError, 'one exact'):
            verify(b'', require_grpc_schema=True, require_html_review=True)

    def test_pins_and_control_anchors_are_required(self):
        with patch.object(html, 'read_artifact', return_value=b'{}'):
            with self.assertRaisesRegex(EvidenceError, 'pins differ'):
                html.inputs()
        with self.assertRaisesRegex(EvidenceError, 'anchors differ'):
            html.documents(self.text.replace(html.ROW, ''))
