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


class RemoteRootTests(unittest.TestCase):
    def test_all_root_objects_reconstruct_and_bind_to_different_catalog_ids(self):
        from superhunter.product_remote_roots import roots
        rows = list(roots())
        self.assertEqual(len({r['id'] for r, _ in rows}), 47)
        self.assertEqual(len({r['tree'] for r, _ in rows}), 47)

    def test_hash_mismatch_bad_order_and_ambiguous_entries_fail(self):
        from superhunter.product_remote_roots import parse_tree
        a = b'100644 a\0' + b'0'*20
        b = b'100644 b\0' + b'1'*20
        for obj, expected in ((a, git_object('tree', b)), (b+a, git_object('tree', b+a)),
                              (a+a, git_object('tree', a+a))):
            with self.assertRaises(ValueError):
                parse_tree(obj, expected)

    def test_source_scripts_and_links_are_never_manifest_inputs(self):
        from superhunter.product_remote_roots import manifests
        entries = {b'setup.py': (b'100644','0'*40), b'Cargo.toml': (b'120000','1'*40),
                   b'go.mod': (b'100644','2'*40)}
        self.assertEqual(manifests(entries), {'go.mod': '2'*40})

    def test_go_blocks_and_cargo_renames(self):
        from superhunter.product_remote_roots import declared_names
        self.assertEqual(declared_names('go.mod', b'require (\n ex.org/test v1.0.0 // indirect\n)\n')['names'],
                         ['ex.org/test'])
        self.assertEqual(declared_names('Cargo.toml', b'[dependencies]\na={package="other",version="2"}')['names'],
                         ['other'])
        result = declared_names('requirements.txt', b'-r extra.txt\nMy_Pkg==2.0\n')
        self.assertEqual(result, {'names': ['my-pkg'], 'unparsed_lines': 1})


class OwnedSourceChecksTests(unittest.TestCase):
    def test_two_source_file_pins_are_derived_from_upstream_subtrees(self):
        from superhunter.product_owned_source_checks import excerpt_files
        rows = list(excerpt_files())
        self.assertEqual([(n, path, blob) for n, _, path, _, blob in rows], [
            (179, 'sb/sarif.py', 'f8b79acd9bc0d0dae11bae079c22465e5130fe0e'),
            (191, 'development-guidelines/token_integration.md', '04c5b7e00aab99ea103e15642120905d2644b363')])

    def test_replaced_publisher_source_is_rejected_before_execution(self):
        from superhunter.product_owned_source_checks import checked_excerpts
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'sarif-source.txt').write_text('def result_region(): pass\n')
            with self.assertRaisesRegex(ValueError, 'bounded source bytes differ from Git'):
                checked_excerpts(Path(tmp))

    def test_partial_source_or_invented_receipt_cannot_accredit_a_project(self):
        for name in ('smartbugs/smartbugs', 'crytic/building-secure-contracts', 'pycqa/bandit', 'ossf/malicious-packages'):
            self.assertEqual(receipt({'repository': name, 'root_declarations': {'id': 1}}), ('pending', None))
            with self.assertRaisesRegex(ValueError, 'accepted product result'):
                receipt({'repository': name, 'owned_source_receipt': {'query': 'owned-source-checks'}})

    def test_upstream_region_converts_only_supplied_coordinates(self):
        from superhunter.smartbugs_region import result_region
        self.assertIsNone(result_region({}))
        self.assertEqual(result_region({'line': 44, 'line_end': 45, 'column': 7}),
                         {'startLine': 44, 'startColumn': 7, 'endLine': 45})


class IndependentScoringTests(unittest.TestCase):
    def setUp(self):
        self.rows = {'all_fields': {'a': {'expected': 'valid', 'observed': 'valid'},
                                    'b': {'expected': 'bad', 'observed': 'bad'}},
                     'without_extra_data': {'a': {'expected': 'valid', 'observed': 'valid'},
                                            'b': {'expected': 'bad', 'observed': 'valid'}}}
        self.native = {'all_fields': {'by_id': {'a': True, 'b': True}, 'percentage': 100},
                       'without_extra_data': {'by_id': {'a': True, 'b': False}, 'percentage': 50}}

    def test_compares_individual_labels_and_detects_removed_check(self):
        from superhunter.product_score_comparison import assess
        self.assertEqual(assess(self.rows, self.native)['without_extra_data']['errors'], ['b'])
        self.native['without_extra_data']['by_id'] = {'a': False, 'b': True}
        with self.assertRaisesRegex(ValueError, 'case-level'):
            assess(self.rows, self.native)

    def test_missing_trials_and_invalid_score_are_rejected(self):
        from superhunter.product_score_comparison import assess
        for invalid in (float('nan'), '100', True):
            self.native['all_fields']['percentage'] = invalid
            with self.assertRaisesRegex(ValueError, 'case-level'):
                assess(self.rows, self.native)
        del self.native['all_fields']
        with self.assertRaisesRegex(ValueError, 'omitted'):
            assess(self.rows, self.native)

    def test_framework_presence_does_not_accredit_scoring(self):
        for repo in ('stanfordnlp/dspy', 'UKGovernmentBEIS/inspect_ai'):
            self.assertEqual(receipt({'repository': repo}), ('pending', None))
            with self.assertRaisesRegex(ValueError, 'accepted product result'):
                receipt({'repository': repo, 'score_comparison_receipt': {'score': 100}})
