from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from superhunter import product_remediation_batch as batch
from superhunter.safe_io import canonical, read_artifact


class RemediationBatchTests(TestCase):
    def test_archived_receipt_matches_a_fresh_native_run(self):
        rows = batch.review(Path('.'))
        receipt = read_artifact(batch.ROOT, 'superhunter/product_supply/remediation-batch-receipt.json')
        self.assertEqual(canonical(rows), receipt)
        self.assertEqual({r['combined_report_sha256'] for r in rows.values()},
                         {rows['WebGoat/WebGoat']['combined_report_sha256']})
        self.assertEqual(rows['juice-shop/juice-shop']['output']['rejected_alternatives'], 188)

    def test_independent_link_parser_requires_exact_endpoint(self):
        revision = '2'*40
        base = 'https://api.github.com/repos/team/project/git/commits/' + revision
        approved = {('team', 'project', revision)}
        self.assertTrue(batch.canonical_commit_link(base, approved))
        for altered in (base+'/', base+'?', base+'#x', base.replace('.com', '.org'),
                        base.replace('team', 'TEAM'), base.replace('https', 'http')):
            with self.subTest(altered=altered):
                self.assertFalse(batch.canonical_commit_link(altered, approved))

    def test_nonmember_content_and_filesystem_controls(self):
        raw = read_artifact(batch.ROOT, batch.DIRECTORY + '/approved-files.txt')
        report = batch.evidence_reader({'a.json': b'{"record":1}', 'b.json': b'{}'},
                                       batch.filename_reference(raw), True)
        self.assertEqual(report['refuted_string_prefix_on'],
                         ['external-link.json', '../evidence-old/other.json'])
        self.assertTrue(report['rejected_unregistered'])
        self.assertTrue(report['tampered_content_rejected'])

    def test_missing_and_duplicate_approved_names_fail(self):
        raw = read_artifact(batch.ROOT, batch.DIRECTORY + '/approved-files.txt')
        for mutation in (raw.replace(b'file3.php', b'file2.php'), raw.replace(b'!in_array', b'in_array')):
            with self.assertRaises(ValueError):
                batch.filename_reference(mutation)

    def test_containment_requires_the_specific_source_clause(self):
        with self.assertRaises(ValueError):
            batch.check_containment(b'The canonical path function')

    def test_unknown_node_binary_is_rejected_before_execution(self):
        with TemporaryDirectory() as temp:
            executable = Path(temp)/'node'
            executable.write_text('incorrect artifact')
            with patch.dict('os.environ', {'NQC_REMEDIATION_NODE': str(executable)}):
                with self.assertRaisesRegex(ValueError, 'Node build'):
                    batch.exact_links([], b'')

    def test_unknown_source_root_cannot_establish_provenance(self):
        from subprocess import SubprocessError
        with TemporaryDirectory() as temp, self.assertRaises((OSError, ValueError, SubprocessError)):
            batch.origins(Path(temp))
