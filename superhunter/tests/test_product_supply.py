import json
from pathlib import Path
import tempfile
import unittest

from superhunter import product_review as product
from superhunter import product_supply_review as supply
from superhunter.safe_io import canonical, read_artifact, write_new_bundle


class SupplyTests(unittest.TestCase):
    def setUp(self):
        self.catalog = product.repositories()
        self.snapshot = read_artifact(product.ROOT, supply.IDENTITIES)
        self.catalog_bytes = read_artifact(product.ROOT, product.CATALOG)

    def test_200_ids_and_distinct_license_outcomes(self):
        rows = supply.identity_rows(self.snapshot, self.catalog, self.catalog_bytes)
        self.assertEqual(len(set(r['github_id'] for r in rows)), 200)
        self.assertEqual(sum(r['label_comparison'] == 'UNDETERMINED' for r in rows), 33)
        self.assertEqual(sum(r['label_comparison'] == 'DIFFERENT_TEXT' for r in rows), 18)
        self.assertEqual(sum(r['label_comparison'] == 'SAME_TEXT' for r in rows), 149)
        self.assertEqual(rows[135]['full_name'], 'anchore/syft')

    def test_one_modified_github_identity_or_mismatched_catalog_is_rejected(self):
        data = json.loads(self.snapshot)
        data['repositories'][0]['github_id'] = data['repositories'][1]['github_id']
        with self.assertRaisesRegex(ValueError, 'snapshot digest'):
            supply.identity_rows(canonical(data), self.catalog, self.catalog_bytes)
        with self.assertRaisesRegex(ValueError, 'disagree'):
            supply.identity_rows(self.snapshot, list(reversed(self.catalog)), self.catalog_bytes)
        with self.assertRaisesRegex(ValueError, 'catalog digest'):
            supply.identity_rows(self.snapshot, self.catalog, self.catalog_bytes+b' ')

    def test_python_verification_binds_every_byte_and_claims_no_signature(self):
        materials = {'product/review.json': b'one', 'identities.json': b'two'}
        link = supply.python_link(materials, b'three')
        self.assertEqual(link['signatures'], [])
        self.assertEqual(set(link['signed']['materials']), set(materials))
        self.assertEqual(link['signed']['products']['supply.json']['sha256'], product.sha(b'three'))
        self.assertNotEqual(link, supply.python_link({**materials, 'identities.json': b'Two'}, b'three'))

    def test_wrong_owasp_revision_fails_before_interpretation(self):
        with self.assertRaisesRegex(ValueError, 'OWASP data differs'):
            supply.guidance({'asvs.csv': b'altered', 'asvs-guides.md': b''}, {})

    def test_missing_artifact_fails_even_with_a_valid_complete_marker(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent)/'evidence'
            write_new_bundle(root, {'supply.json': b'{}', 'supply.link': b'{}'})
            with self.assertRaisesRegex(ValueError, 'incomplete or altered'):
                supply.verify(root, {}, {})

    def test_metadata_alone_cannot_promote_a_candidate_to_an_integration(self):
        rows = supply.identity_rows(self.snapshot, self.catalog, self.catalog_bytes)
        report = {'repositories': self.catalog, 'packages': [], 'census_graph': {'nodes': []},
                  'conflicting_python_pins': {}, 'tools': {}, 'minimum_python_pin_groups': 1,
                  'profile_whose_isolation_resolves_all_observed_pin_conflicts': None}
        index = product.ProductIndex(report, supply=({'source_roles': {}, 'controls': []}, rows))
        self.assertIsNone(index.lookup('crytic/slither')['supply_role'])
        self.assertNotIn('evidence', index.lookup('crytic/slither'))
        self.assertNotIn('github_identity', report['repositories'][0])


class NoticeTests(unittest.TestCase):
    @staticmethod
    def wheel(entries):
        from io import BytesIO
        from zipfile import ZipFile
        buffer = BytesIO()
        with ZipFile(buffer, 'w') as archive:
            for path, content in entries.items():
                archive.writestr(path, content)
        return buffer.getvalue()

    def test_only_digest_matched_declared_documentation_is_returned(self):
        from superhunter.product_notices import collect
        prefix = 'example-1.dist-info/'
        raw = self.wheel({prefix + 'METADATA': b'Name: Example\nVersion: 1\nLicense-File: LICENSE\n',
                          prefix + 'licenses/LICENSE': b'notice bytes', 'example/module.py': b'unrelated'})
        lock = f'example==1 --hash=sha256:{product.sha(raw)}\n'.encode()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root/'example-1-py3-none-any.whl'
            path.write_bytes(raw)
            packages, files = collect(root, lock)
            self.assertEqual(files, {'example-1-1.txt': b'notice bytes'})
            self.assertEqual(packages['example']['notices'][0]['sha256'], product.sha(b'notice bytes'))
            self.assertIsNone(packages['example']['declared_license_expression'])
            path.write_bytes(raw + b'changed')
            with self.assertRaisesRegex(ValueError, 'digest-matched'):
                collect(root, lock)

    def test_legacy_license_and_missing_or_ambiguous_declarations(self):
        from superhunter.product_notices import wheel_notices
        prefix = 'example-1.dist-info/'
        meta = prefix + 'METADATA'
        headers = b'Name: example\nVersion: 1\n'
        entries = {meta: headers, prefix + 'LICENSE': b'legacy'}
        self.assertEqual(wheel_notices(self.wheel(entries), 'example', '1')[1],
                         {prefix + 'LICENSE': b'legacy'})
        for wrong in ('MISSING', '../LICENSE', '/LICENSE'):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                wheel_notices(self.wheel({**entries, meta: headers + f'License-File: {wrong}\n'.encode()}),
                              'example', '1')
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            wheel_notices(self.wheel({**entries, meta: headers + b'License-File: LICENSE\n',
                                      prefix + 'licenses/LICENSE': b'other'}), 'example', '1')


class NativeLicenseTests(unittest.TestCase):
    def test_scancode_matches_bind_paths_digests_and_line_numbers(self):
        from copy import deepcopy
        from superhunter.product_licenses import scan_result
        data = b'first\nsecond\n'
        match = {'license_expression_spdx': 'MIT', 'from_file': 'notices/license.txt',
                 'start_line': 1, 'end_line': 2, 'rule_identifier': 'sample'}
        file = {'type': 'file', 'path': 'notices/license.txt', 'name': 'license.txt',
                'sha256': product.sha(data), 'scan_errors': [], 'detected_license_expression_spdx': 'MIT',
                'license_detections': [{'matches': [match]}]}
        report = {'headers': [{'tool_name': 'scancode-toolkit', 'tool_version': '32.5.0', 'errors': []}],
                  'files': [file]}
        notices = {'license.txt': data}
        self.assertEqual(scan_result(report, notices)['notices']['license.txt']['detected_expression'], 'MIT')
        for field, value in [('path', 'elsewhere/license.txt'), ('sha256', '0'*64), ('scan_errors', ['error'])]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                scan_result({**report, 'files': [{**file, field: value}]}, notices)
        for files in ([], [file, file]):
            with self.assertRaises(ValueError):
                scan_result({**report, 'files': files}, notices)
        bad = deepcopy(report)
        bad['files'][0]['license_detections'][0]['matches'][0]['end_line'] = 3
        with self.assertRaisesRegex(ValueError, 'outside'):
            scan_result(bad, notices)

    def test_cargo_comparison_retains_missing_license_and_checks_every_crate(self):
        from superhunter.product_licenses import alternatives, cargo_result
        workspace = Path('/example/nqc-census')
        inputs = {'nqc-census/Cargo.lock': b'[[package]]\nname="one"\nversion="1"',
                  'nqc-census/Cargo.toml': b'[workspace]\nmembers=["crates/one"]\n[workspace.package]\nversion="1"',
                  'nqc-census/crates/one/Cargo.toml': b'[package]\nname="one"\nversion.workspace=true'}
        key = 'one 1 path+file:///example/nqc-census/crates/one'
        row, = cargo_result({key: {'licenses': []}}, inputs, workspace, Path('/unused'))['packages']
        self.assertIsNone(row['declared_expression'])
        self.assertTrue(row['workspace_member'])
        for invalid in ({}, {key: {'licenses': ['MIT']}}, {key + '-other': {'licenses': []}}):
            with self.assertRaisesRegex(ValueError, 'disagrees'):
                cargo_result(invalid, inputs, workspace, Path('/unused'))
        self.assertEqual(alternatives('MIT/Apache-2.0'), alternatives('Apache-2.0 OR MIT'))
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            alternatives('MIT AND Apache-2.0')
