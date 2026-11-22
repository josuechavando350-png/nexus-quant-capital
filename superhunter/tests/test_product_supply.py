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


class ProfileNoticeTests(unittest.TestCase):
    def test_preserves_distinct_versions_and_cross_profile_digest_provenance(self):
        from superhunter.product_notices import collect_profiles
        from superhunter.product_reasoning import INPUTS, PROFILES
        wheel = NoticeTests.wheel({'example-1.dist-info/METADATA': b'Name: example\nVersion: 1\n',
                                   'example-1.dist-info/LICENSE': b'original public notice'})
        digest = product.sha(wheel)
        inputs = {INPUTS[scope + '/requirements.txt']: b'example==1\n' for scope in PROFILES}
        inputs[INPUTS['otel-qa/requirements.txt']] = f'example==1 --hash=sha256:{digest}\n'.encode()
        inputs[INPUTS['custody/requirements.txt']] = b'example==2\n'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'example-1-py3-none-any.whl').write_bytes(wheel)
            records, notices = collect_profiles(root, inputs)
            first, second = records['example']
            self.assertEqual(first['digest_sources'], {'otel-qa': digest})
            self.assertEqual(len(first['profiles']), 5)
            self.assertEqual(second['status'], 'NO_DIGEST_IN_PRODUCT_PROFILES')
            self.assertEqual(notices, {'example-1-1.txt': b'original public notice'})
            inputs[INPUTS['local-lab/requirements.txt']] = ('example==1 --hash=sha256:' + 'a'*64).encode()
            with self.assertRaisesRegex(ValueError, 'ambiguous wheel digest'):
                collect_profiles(root, inputs)


class NoticeSearchTests(unittest.TestCase):
    def test_sparse_results_must_match_independent_source_terms_and_bytes(self):
        from copy import deepcopy
        from superhunter.product_notice_search import NoticeCorpus, tokens
        corpus = NoticeCorpus({'a.txt': b'Patent patent, redistribution!', 'b.txt': b'Patent'})
        terms = tokens('PATENT; redistribution')
        points = corpus.points()
        self.assertEqual(len(corpus.sparse(terms)['indices']), 2)
        rows = [{'id': i, 'payload': p['payload'], 'score': s} for i, (p, s) in enumerate(zip(points, [2, 1]))]
        result = corpus.validate_matches(terms, list(reversed(rows)))
        self.assertEqual([r['file'] for r in result], ['a.txt', 'b.txt'])
        self.assertEqual(result[0]['matched_terms'], ['patent', 'redistribution'])
        self.assertEqual(corpus.validate_matches(tokens('absent'), []), [])
        for wrong in (rows[:1], rows * 2, [dict(rows[0], score=True), rows[1]],
                      [dict(rows[0], score=1), rows[1]], [dict(rows[0], id=-1), rows[1]]):
            with self.assertRaises(ValueError):
                corpus.validate_matches(terms, wrong)
        tampered = deepcopy(rows)
        tampered[0]['payload']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            corpus.validate_matches(terms, tampered)

    def test_notice_queries_require_a_nonempty_verified_corpus(self):
        from superhunter.product_notice_search import NoticeCorpus
        for data in ({}, {'no-terms.txt': b'   '}):
            with self.assertRaises(ValueError):
                NoticeCorpus(data)


class LicenseSarifTests(unittest.TestCase):
    def test_report_keeps_utf8_bytes_and_locates_the_actual_pin(self):
        from superhunter.product_license_sarif import findings, render
        from superhunter.product_reasoning import INPUTS
        path = INPUTS['owned-slither/requirements.txt']
        raw = '# Préparation\r\nexample==1\r\n'.encode()
        sources = {path: raw}
        profiles = {'example': [{'version': '1', 'status': 'NO_DIGEST_IN_PRODUCT_PROFILES',
                                 'profiles': ['owned-slither']}]}
        rows = findings(sources, [], profiles, {}, {})
        run = render(rows)['runs'][0]
        self.assertEqual(run['artifacts'][0]['contents']['text'].encode(), raw)
        loc = run['results'][0]['locations'][0]['physicalLocation']
        self.assertEqual(loc['artifactLocation']['uri'], path)
        reg = loc['region']
        self.assertEqual(raw[reg['byteOffset']:reg['byteOffset'] + reg['byteLength']], b'example==1\r\n')
        self.assertEqual((reg['startLine'], reg['endLine']), (2, 2))
        with self.assertRaises(ValueError):
            findings({path: raw + b'example==1\n'}, [], profiles, {}, {})

    def test_report_rejects_an_unbound_notice_and_preserves_non_utf8_artifacts(self):
        from superhunter.product_license_sarif import findings, render
        with self.assertRaises(ValueError):
            findings({}, [], {}, {'notice.txt': {'sha256': '0' * 64}}, {'notice.txt': b'different'})
        raw = bytes([255])
        scan = {'notice.txt': {'sha256': product.sha(raw), 'detected_expression': None}}
        run = render(findings({}, [], {}, scan, {'notice.txt': raw}))['runs'][0]
        self.assertEqual(run['artifacts'][0]['contents'], {'binary': '/w=='})
        self.assertEqual(run['results'][0]['ruleId'], 'NQC1003')


class ProducerElfTests(unittest.TestCase):
    def test_independent_header_loader_and_needed_libraries_must_agree(self):
        from superhunter.product_producer_elf import assess
        header = b'\x7fELF\x02\x01' + bytes(12) + b'\x3e\x00'
        lief = {'class': 'ELF64', 'byte_order': 'LSB', 'machine': 'X86_64',
                'interpreter': '/lib/loader', 'needed': ['liba.so', 'libb.so']}
        text = ('[Requesting program interpreter: /lib/loader]\n'
                '(NEEDED) Shared library: [libb.so]\n(NEEDED) Shared library: [liba.so]\n')
        self.assertEqual(assess(header, lief, text)['needed_shared_libraries'], ['liba.so', 'libb.so'])
        for h, record, output in [(header[:19], lief, text), (header, dict(lief, machine='ARM'), text),
                                  (header, lief, text.replace('libb.so', 'liba.so')),
                                  (header, lief, text.replace('/lib/loader', '/other'))]:
            with self.assertRaises(ValueError):
                assess(h, record, output)
        self.assertIsNone(assess(header, dict(lief, interpreter='', needed=[]), '')['interpreter'])


class NoticeRankingTests(unittest.TestCase):
    def test_real_term_counts_reject_missing_documents_wrong_weights_and_wrong_order(self):
        import math
        from superhunter.product_notice_ranking import RankingCorpus
        corpus = RankingCorpus({'a.txt': b'patent patent', 'b.txt': b'patent other'})
        idf = math.log1p(.5 / 2.5)
        rows = [{'file': 'a.txt', 'sha256': corpus.docs['a.txt']['sha256'], 'score': idf * (1 + 5 / 3.5)},
                {'file': 'b.txt', 'sha256': corpus.docs['b.txt']['sha256'], 'score': idf * 2}]
        self.assertEqual([r['file'] for r in corpus.validate({'patent'}, rows)], ['a.txt', 'b.txt'])
        self.assertEqual(corpus.validate({'unseen'}, []), [])
        for wrong in (rows[:1], list(reversed(rows)), [dict(rows[0], score=0), rows[1]],
                      [dict(rows[0], sha256='0' * 64), rows[1]]):
            with self.assertRaises(ValueError):
                corpus.validate({'patent'}, wrong)


class NoticeSimilarityTests(unittest.TestCase):
    def test_all_unordered_pairs_and_independent_cosines_are_required(self):
        from superhunter.product_notice_ranking import RankingCorpus
        from superhunter.product_notice_similarity import compare, weights
        corpus = RankingCorpus({'a.txt': b'patent', 'b.txt': b'patent', 'c.txt': b'source', 'd.txt': b'!? '})
        vectors = weights(corpus)
        pairs = [(0, 1, 1.0), (0, 2, 0.0), (1, 2, 0.0)]
        result, identical = compare(corpus, vectors, pairs)
        self.assertEqual(identical, 1)
        self.assertEqual(result['a.txt']['nearest'][0]['file'], 'b.txt')
        self.assertTrue(result['a.txt']['nearest'][0]['same_bytes'])
        self.assertFalse(result['d.txt']['has_terms'])
        for bad in (pairs[:-1], pairs + [pairs[0]], [(0, 1, .5), *pairs[1:]], [(1, 0, 1), *pairs[1:]]):
            with self.assertRaises(ValueError):
                compare(corpus, vectors, bad)


class FixedInventoryBundleTests(unittest.TestCase):
    def test_restore_preserves_complete_markers_and_rejects_modified_member(self):
        from hashlib import sha256
        from superhunter.tools.pack_remote_inputs import restore_inventory

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'inventories'
            restore_inventory(dest)
            restore_inventory(dest, check=True)
            files = [file for file in dest.rglob('*') if file.is_file()]
            self.assertEqual((12, 106246), (len(files), sum(f.stat().st_size for f in files)))
            for group in ('cdx', 'guac'):
                marker = json.loads((dest / group / 'COMPLETE.json').read_bytes())
                self.assertEqual(marker['sha256'], {f.name: sha256(f.read_bytes()).hexdigest()
                                 for f in (dest / group).iterdir() if f.name != 'COMPLETE.json'})
            report = dest / 'guac' / 'guac.json'
            data = report.read_bytes()
            report.write_bytes(b'!' + data[1:])
            with self.assertRaisesRegex(ValueError, 'inventory content differs'):
                restore_inventory(dest, check=True)

    def test_preexisting_directory_and_symlinks_are_refused(self):
        from superhunter.tools.pack_remote_inputs import restore_inventory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            occupied = root / 'existing'
            occupied.mkdir()
            with self.assertRaises(FileExistsError):
                restore_inventory(occupied)
            self.assertEqual(list(occupied.iterdir()), [])
            alias = root / 'alias'
            alias.symlink_to(occupied, target_is_directory=True)
            with self.assertRaises(OSError):
                restore_inventory(alias / 'new')
            dest = root / 'inventories'
            restore_inventory(dest)
            item = dest / 'cdx' / 'COMPLETE.json'
            item.rename(occupied / 'marker')
            item.symlink_to(occupied / 'marker')
            with self.assertRaises(OSError):
                restore_inventory(dest, check=True)
