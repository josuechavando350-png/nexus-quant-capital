from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from subprocess import SubprocessError

from superhunter.product_sources import gitlinks
from superhunter.safe_io import strict_json, read_artifact
from superhunter.tools import verify_source_materialization as audit


class SourceMaterializationTests(TestCase):
    def setUp(self):
        self.product = gitlinks(audit.ROOT)
        self.records = audit.unpack_records()

    def test_published_receipt_reproduces_offline(self):
        observed = audit.verify(self.records, self.product)
        receipt = strict_json(read_artifact(audit.ROOT, 'superhunter/product_supply/source-materialization-review.json'))
        self.assertEqual(observed, {k: receipt[k] for k in observed})
        self.assertEqual(receipt['local_checkouts_observed'], 200)
        rows = [[x['catalog_id'], x['commit'], x['tree']] for x in audit.expected_rows()]
        self.assertEqual(audit.sha(audit.canonical(rows)), receipt['commit_tree_pairs_sha256'])

    def test_duplicate_subject_is_rejected(self):
        rows = self.records['all200-checkouts.json']['sources']
        rows[-1] = rows[0].copy()
        with self.assertRaisesRegex(ValueError, 'catalog rows'):
            audit.verify(self.records, self.product)

    def test_second_workspace_source_cannot_be_counted_in_product(self):
        new = self.records['summary.json'][0]
        self.product[new['path']] = new['commit']
        with self.assertRaisesRegex(ValueError, '153'):
            audit.verify(self.records, self.product)

    def test_second_workspace_tree_substitution_is_rejected(self):
        row = self.records['summary.json'][0]
        row['tree'] = '1'*40
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            audit.verify(self.records, self.product)

    def test_historical_failure_is_not_counted_as_fsck_success(self):
        self.records['summary.json'][0]['status'] = 'blocked'
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            audit.verify(self.records, self.product)

    def test_substitution_between_preserved_and_new_groups_is_rejected(self):
        new = self.records['summary.json'][0]
        self.records['preserved153.json'][0].update(path=new['path'], commit=new['commit'])
        with self.assertRaisesRegex(ValueError, 'preserved'):
            audit.verify(self.records, self.product)

    def test_directory_without_recorded_superproject_is_rejected(self):
        with TemporaryDirectory() as d, self.assertRaises((SubprocessError, ValueError)):
            audit.compare_local(Path(d))
