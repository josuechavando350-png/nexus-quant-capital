import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_source_audit as audit
from superhunter import product_source_references as refs
from superhunter.product_batches import receipt
from superhunter.product_census_header import check_geth
from superhunter.repository_boundary import git_object
from superhunter.safe_io import canonical
from superhunter.tools.check_catalog_origins import RepoHead


class GitTreeAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE)
        git('init', '-q')
        raw = b'Example license notice\n'
        (self.root/'LICENSE').write_bytes(raw)
        (self.root/'.gitattributes').write_text('# ignored filter=lfs\n*.bin filter=lfs diff=lfs\n')
        (self.root/'Cargo.lock').write_text('version = 4\n')
        pointer = audit.LFS_HEADER + b'oid sha256:' + b'a'*64 + b'\nsize 37\n'
        (self.root/'fixture.bin').write_bytes(pointer)
        (self.root/'ambiguous').write_bytes(audit.LFS_HEADER + b'size broken\n')
        git('add', '.')
        self.child = 'b'*40
        git('update-index', '--add', '--cacheinfo', f'160000,{self.child},nested/child')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
        self.source = {'revision': git('rev-parse', 'HEAD').decode().strip(), 'id': 123,
                       'notice': {'path': 'LICENSE', 'git_blob': git_object('blob', raw),
                                  'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}

    def test_committed_tree_and_pointer_are_reported_separately(self):
        (self.root/'fixture.bin').write_bytes(b'uncommitted data')
        result = audit.tree_inventory(self.root, self.source)
        self.assertEqual(result['nested_gitlinks'], {'nested/child': self.child})
        self.assertEqual(result['lfs_pointers'], {'fixture.bin': {'oid': 'a'*64, 'bytes': 37}})
        self.assertEqual(result['lfs_attribute_files'], ['.gitattributes'])
        self.assertEqual(result['manifest_counts_by_filename'], {'Cargo.lock': 1})
        self.assertEqual(result['unrecognized_lfs_headers'], ['ambiguous'])
        self.assertEqual(result['root_notice_files'], {'LICENSE': self.source['notice']['git_blob']})

    def test_notice_cannot_be_reassigned_to_another_blob(self):
        self.source['notice']['git_blob'] = '0'*40
        with self.assertRaisesRegex(ValueError, 'notice path differs'):
            audit.tree_inventory(self.root, self.source)

    def test_internal_and_external_license_links_use_git_objects_only(self):
        (self.root/'local-link').symlink_to('LICENSE')
        (self.root/'external-link').symlink_to('../private')
        subprocess.run(['git', '-C', self.root, 'add', 'local-link', 'external-link'], check=True)
        tree = subprocess.check_output(['git', '-C', self.root, 'write-tree']).decode().strip()
        result = audit.resolve_notice_link(self.root, tree, 'local-link')
        self.assertEqual(result['path'], 'LICENSE')
        self.assertEqual(result['sha256'], self.source['notice']['sha256'])
        self.assertEqual(audit.resolve_notice_link(self.root, tree, 'external-link'),
                         {'status': 'external_target'})

    def test_github_duplicate_identity_is_rejected(self):
        parser = RepoHead()
        tag = '<meta name="octolytics-dimension-repository_id" content="12">'
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            parser.feed(tag + tag)

    def test_remote_inventory_rejects_missing_identity(self):
        with self.assertRaisesRegex(ValueError, 'commit metadata'):
            audit.remote_trees(audit.ROOT, {})

    def test_reviewed_snapshot_cannot_be_replaced_with_self_consistent_forgery(self):
        with patch.object(audit, 'read_artifact', return_value=canonical({'entries': []})):
            with self.assertRaisesRegex(ValueError, 'reviewed evidence'):
                audit.attach(None)


class ProductComparisonTests(unittest.TestCase):
    def test_geth_requires_both_exact_comparisons(self):
        expected = {'original': {'rlp_bytes': 649}, 'changed_gas_used': {'rlp_bytes': 649}}
        self.assertEqual(check_geth(expected, {'cases': expected})['cases'], expected)
        with self.assertRaisesRegex(ValueError, 'Geth disagrees'):
            check_geth({'original': expected['original']}, {'cases': expected})
        with self.assertRaisesRegex(ValueError, 'Geth disagrees'):
            check_geth({'original': {'rlp_bytes': '649'}, 'changed_gas_used': expected['changed_gas_used']},
                       {'cases': expected})

    def test_typed_payload_rejects_overflow_padding_and_missing_field(self):
        fields = {'gas_used': 'Uint64', 'extra_data': 'ExtraData', 'block_hash': 'Hash32'}
        valid = {'gasUsed': hex(2**64-1), 'extraData': '0x', 'hash': '0x' + 'f'*64}
        self.assertEqual(refs.invalid_fields(valid, fields, 256, 32), [])
        for invalid in ('0x00', '0x', hex(2**64)):
            self.assertEqual(refs.invalid_fields({**valid, 'gasUsed': invalid}, fields, 256, 32), ['gasUsed'])
        self.assertEqual(refs.invalid_fields({'gasUsed': '0x0', 'extraData': '0xf'}, fields, 256, 32),
                         ['extraData', 'hash'])

    def test_a_placeholder_or_mismatched_receipt_cannot_count_as_a_comparison(self):
        for name, key in [('ethereum/go-ethereum', 'geth_header_evidence'),
                          ('ethereum/consensus-specs', 'source_reference'),
                          ('openzeppelin/openzeppelin-contracts', 'source_reference')]:
            for bad in ({}, {'report': 'test'}, {'report_sha256': '0'*64}):
                with self.assertRaisesRegex(ValueError, 'accepted product result'):
                    receipt({'repository': name, key: bad})

    def test_audit_rows_cannot_promote_project_to_runtime(self):
        for name in ('ethereum/go-ethereum', 'ethereum/consensus-specs', 'OpenZeppelin/openzeppelin-contracts'):
            self.assertEqual(receipt({'repository': name, 'source_inventory': {'tree': 'reviewed'}}),
                             ('pending', None))
        self.assertEqual(receipt({'repository': 'some/project', 'source_reference': {'report': 'test'}}),
                         ('pending', None))
