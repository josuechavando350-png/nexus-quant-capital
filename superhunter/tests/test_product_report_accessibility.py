from html.parser import HTMLParser
import unittest

from superhunter import product_report_accessibility as access
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import read_artifact, strict_json


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append(tag)
        if tag == 'a':
            self.current = {'attributes': attributes, 'text': '', 'isolates': []}
            self.links.append(self.current)
        if tag == 'bdi' and self.current:
            self.current['isolates'].append(attributes)

    def handle_endtag(self, tag):
        if tag == 'a':
            self.current = None

    def handle_data(self, text):
        if self.current:
            self.current['text'] += text


class ReportAccessibilityTests(unittest.TestCase):
    def test_only_exact_root_keys_and_literal_scalars_are_read(self):
        self.assertEqual(access.message('nested:\n  compare_report_saved: other\ncompare_report_saved: "{0} listo"'),
                         '{0} listo')
        self.assertIsNone(access.message('# compare_report_saved: {0}\n'))
        for source in ('compare_report_saved: a\ncompare_report_saved: b',
                       'compare_report_saved: |\n  hello',
                       'compare_report_saved: "first\\nsecond"'):
            with self.subTest(source=source), self.assertRaises((ValueError, EvidenceError)):
                access.message(source)

    def test_path_format_is_exact_and_cannot_access_attributes_or_lose_the_filename(self):
        self.assertEqual(access.split_path('Antes {{nota}} {0} después'), (('Antes {nota} ', ' después'), None))
        self.assertEqual(access.split_path('recibido'), (None, 'missing_path'))
        for invalid in ('{0.__class__}', '{0!r}', '{0}:{0}', '{name}', '{0:20}', '{'):
            with self.subTest(invalid=invalid):
                self.assertEqual(access.split_path(invalid), (None, 'invalid_path_field'))

    def test_render_uses_the_actual_report_labels_and_direction_with_a_ltr_path(self):
        templates = dict.fromkeys(access.LOCALES)
        templates.update(en='report saved in {0}', es='informe guardado en {0}', ar='ملف {0}',
                         uz='taqqoslash hisoboti saqlandi', ja='{0} <タグ> &')
        html, counts, statuses = access.render(templates, strict_json(read_artifact(access.ROOT, access.REPORT_PATH)))
        self.assertEqual(counts, {'parallel': 140, 'consolidated': 157, 'shared': 132})
        dom = Links()
        dom.feed(html.decode())
        self.assertEqual(len(dom.links), len(access.LOCALES))
        self.assertFalse({'script', 'img', 'link', 'iframe'} & set(dom.tags))
        links = dict(zip(access.LOCALES, dom.links, strict=True))
        for code, link in links.items():
            self.assertEqual(link['attributes']['href'], access.REPORT_FILE)
            self.assertEqual(link['attributes']['lang'], statuses[code]['text_language'])
            self.assertEqual(link['text'].count(access.REPORT_FILE), 1)
            self.assertEqual(link['isolates'], [{'dir': 'ltr'}])
        self.assertEqual(links['ar']['attributes']['dir'], 'rtl')
        self.assertEqual(links['fa']['attributes']['dir'], 'ltr')
        self.assertEqual(statuses['iw']['requested_language'], 'he')
        self.assertEqual(statuses['uz']['fallback_reason'], 'missing_path')
        self.assertEqual(links['uz']['text'], links['en']['text'])
        self.assertEqual(links['es']['text'], 'informe guardado en ' + access.REPORT_FILE)
        self.assertEqual(links['ja']['text'], access.REPORT_FILE + ' <タグ> &')
        self.assertNotIn('<タグ>', html.decode())

    def test_missing_catalog_or_invalid_english_prevents_rendering(self):
        report = strict_json(read_artifact(access.ROOT, access.REPORT_PATH))
        all_absent = dict.fromkeys(access.LOCALES)
        for incomplete in ({}, all_absent, {**all_absent, 'en': '{name}'}):
            with self.subTest(incomplete=incomplete), self.assertRaises(EvidenceError):
                access.render(incomplete, report)

    def test_markdown_keeps_relative_targets_source_notices_and_literal_link_text(self):
        templates = dict.fromkeys(access.LOCALES)
        templates.update(en='saved in {0}', es='informe [local] {0}', ar='{0} ملف')
        report = strict_json(read_artifact(access.ROOT, access.REPORT_PATH))
        md, counts, statuses = access.render(templates, report, markdown=True)
        html, html_counts, html_statuses = access.render(templates, report)
        self.assertEqual((counts, statuses), (html_counts, html_statuses))
        self.assertNotEqual(md, html)
        text = md.decode()
        self.assertEqual(text.count('](' + access.REPORT_FILE + ')'), len(access.LOCALES))
        self.assertIn(r'informe \[local\]', text)
        self.assertIn('lang="ar" dir="rtl"', text)
        self.assertIn('](nettacker-report-messages-license.txt)', text)
        self.assertIn(access.REVISION, text)
