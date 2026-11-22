"""Case-sensitive dependency joins and incomplete or malformed attribution controls."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from superhunter import product_dependency_attributions as d


HEADER = 'component,origin,license,copyright\r\n'


def module(rows, **other):
    return {'Module': {'Path': 'example.org/main'}, 'Require': rows, **other}


def requirement(path, *, indirect=False):
    return {'Path': path, 'Version': 'v1.0.0', 'Indirect': indirect}


class AttributionTests(unittest.TestCase):
    def test_private_go_reader_disables_the_telemetry_child_before_it_starts(self):
        def run(argv, **options):
            config = Path(options['env']['XDG_CONFIG_HOME'])
            self.assertTrue(config.is_relative_to(options['cwd']))
            self.assertEqual((config/'go/telemetry/mode').read_text(), 'off\n')
            return SimpleNamespace(returncode=0, stdout=b'{"Module":{"Path":"example.org/main"},"Require":'
                                   b'[{"Path":"example.org/pkg","Version":"v1.0.0"}]}')

        with patch.object(d, 'copy_release'), patch.object(d.subprocess, 'run', side_effect=run):
            name, rows = d.parse_mod(b'module example.org/main\n', Path(__file__))
        self.assertEqual((name, rows), ('example.org/main', {'example.org/pkg': ('direct', 'v1.0.0')}))

    def test_csv_keeps_case_and_does_not_promote_children_to_parent(self):
        raw = HEADER + '''example.org/dep,https://example.org/dep,"['Apache-2.0']",[]\r
example.org/other,https://example.org/other,"['MIT']",[]\r
'''
        name, requirements = d.declared(module([
            requirement('example.org/dep'), requirement('example.org/dep/sdk'),
            requirement('example.org/OTHER', indirect=True)]))
        r = d.reconcile(name, requirements, d.notices(raw.encode()))
        self.assertEqual(r['requirement_counts']['direct']['exact_csv_row'], 1)
        self.assertEqual(r['absent_from_csv']['direct'], [{'module': 'example.org/dep/sdk', 'version': 'v1.0.0'}])
        self.assertEqual(r['absent_from_csv']['indirect'], [{'module': 'example.org/OTHER', 'version': 'v1.0.0'}])
        self.assertEqual(r['csv_only_outside_requirements'], ['example.org/other'])

    def test_blank_fields_are_distinct_from_malformed_label_lists(self):
        for text in ('', '[]'):
            with self.subTest(text=text):
                self.assertEqual(d.license_field(text), ('missing_license', []))
        for text in ('''['(MIT', 'Apache-2.0)', 'MIT']''', 'MIT', '[""]', '[2]', "'MIT'", '[None]'):
            with self.subTest(text=text):
                self.assertEqual(d.license_field(text), ('malformed_license', []))
        self.assertEqual(d.license_field("['BSD-2-Clause', 'MIT']"), ('has_labels', ['BSD-2-Clause', 'MIT']))

    def test_issue_memberships_preserve_absent_unlicensed_and_malformed(self):
        name, requirements = d.declared(module([requirement('example.org/unlicensed', indirect=True),
                                                 requirement('example.org/broken'), requirement('example.org/missing')]))
        rows = {'example.org/main': d.license_field('[]'), 'example.org/outside': d.license_field('[]'),
                'example.org/unlicensed': d.license_field(''), 'example.org/broken': d.license_field("['MIT)']")}
        r = d.reconcile(name, requirements, rows)
        self.assertEqual(r['requirement_counts']['direct']['absent_from_csv'], 1)
        self.assertEqual(r['requirement_counts']['direct']['malformed_license'], 1)
        self.assertEqual(r['requirement_counts']['indirect']['missing_license'], 1)
        self.assertEqual(r['license_field_issues']['example.org/main']['membership'], 'main_module')
        self.assertEqual(r['license_field_issues']['example.org/outside']['membership'], 'outside_requirements')

    def test_physical_blank_line_and_quoted_commas_are_parsed(self):
        raw = HEADER + '''example.org/p,https://example.org/p,"['Apache-2.0', 'MIT']","['A, Inc.']"\r
\r
'''
        self.assertEqual(d.notices(raw.encode()), {'example.org/p': ('has_labels', ['Apache-2.0', 'MIT'])})

    def test_duplicate_or_malformed_csv_records_fail_closed(self):
        good = 'example.org/a,https://example.org/a,[],[]\n'
        for body in (good + good, ',https://example.org/x,[],[]\n', 'example.org/a,,[],[]\n',
                     'example.org/a,https://example.org/a,[]\n', 'example.org/a,https://example.org/a,[],[],extra\n',
                     'example.org/a,https://example.org/a,"unterminated\n'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                d.notices((HEADER + body).encode())

    def test_bad_go_metadata_and_duplicate_requirements_fail_closed(self):
        base = requirement('example.org/a')
        for doc in (module([base, base]), module([dict(base, Indirect=1)]),
                    module([dict(base, Path='../../work path')]), module([dict(base, Version='latest')]),
                    module([dict(base, Path='example.org/main')]), module([base], Replace=[{'New': {'Path': '../local'}}])):
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                d.declared(doc)
