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


class MetadataBoundaryTests(unittest.TestCase):
    def test_attributes_verify_the_blob_before_interpreting_attributes(self):
        from superhunter.tools.audit_tree_metadata import attributes
        raw = b'# ignore filter=lfs\n*.bin filter=lfs\n*.txt text\n'
        oid = git_object('blob', raw)
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            source = cache/(oid + '.txt')
            source.write_bytes(raw)
            self.assertEqual(attributes({}, '.gitattributes', oid, cache, False)['literal_filter_lfs_lines'], 1)
            source.write_bytes(raw + b'\n')
            with self.assertRaisesRegex(ValueError, 'attributes differ'):
                attributes({}, '.gitattributes', oid, cache, False)

    def test_blob_containing_checkout_cannot_pass_as_metadata_only(self):
        from superhunter.tools.audit_tree_metadata import verify_repository
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(['git', 'init', '-q', root], check=True)
            (root/'readme').write_text('own fixture')
            subprocess.run(['git', '-C', root, 'add', 'readme'], check=True)
            subprocess.run(['git', '-C', root, '-c', 'user.name=User', '-c', 'user.email=test@invalid',
                            'commit', '-qm', 'fixture'], check=True)
            trees = subprocess.check_output(['git', '-C', root, 'rev-parse', 'HEAD', 'HEAD^{tree}']).decode().split()
            with self.assertRaisesRegex(ValueError, 'unexpected object types'):
                verify_repository({'commit': trees[0], 'tree': trees[1]}, root)
            with self.assertRaisesRegex(ValueError, 'binding failed'):
                verify_repository({'commit': trees[0], 'tree': '0'*40}, root)

    def test_legacy_wheel_with_pep639_license_directory(self):
        from io import BytesIO
        from zipfile import ZipFile
        from superhunter.product_notices import wheel_notices
        data = BytesIO()
        with ZipFile(data, 'w') as z:
            z.writestr('sample-1.dist-info/METADATA', 'Name: sample\nVersion: 1\n')
            z.writestr('sample-1.dist-info/licenses/LICENSE.md', 'Own license example')
        self.assertEqual(wheel_notices(data.getvalue(), 'sample', '1'),
                         (None, {'sample-1.dist-info/licenses/LICENSE.md': b'Own license example'}))


class HeaderForkTests(unittest.TestCase):
    def test_chain_and_monotonic_schedule_must_match(self):
        from superhunter.product_fork_headers import schedule
        for config in ({'chainId': 2}, {'chainId': True}, {'chainId': 1, 'cancunTime': 0},
                       {'chainId': 1, 'shanghaiTime': 10, 'cancunTime': 9}):
            with self.assertRaises(ValueError):
                schedule({'config': config}, 1)

    def test_boundary_compares_active_fields_and_refuses_configuration_disagreement(self):
        from superhunter.product_fork_headers import boundary_agreement, discrepancies
        times = {'shanghai': 1, 'cancun': 5}
        self.assertEqual(boundary_agreement(times, times)[-2:],
                         [{'timestamp': 4, 'active': ['shanghai']}, {'timestamp': 5, 'active': ['shanghai', 'cancun']}])
        with self.assertRaisesRegex(ValueError, 'disagree'):
            boundary_agreement(times, {'shanghai': 1, 'cancun': 6})
        header = {'timestamp': '0x4', 'withdrawalsRoot': 'present', 'blobGasUsed': '0x0'}
        self.assertEqual(discrepancies(header, times), ['blobGasUsed'])

    def test_fork_receipts_cannot_be_replaced_by_a_git_revision(self):
        for name in ('paradigmxyz/reth', 'besu-eth/besu', 'ethereum/hive'):
            self.assertEqual(receipt({'repository': name}), ('pending', None))
            with self.assertRaisesRegex(ValueError, 'accepted product result'):
                receipt({'repository': name, 'fork_header_reference': {'revision': 'claimed'}})


class ProductCreditTests(unittest.TestCase):
    def test_reviewed_schema_rejects_an_unbound_producer_for_every_older_native_integration(self):
        from superhunter.product_batches import RECEIPTS
        for name, key in RECEIPTS.items():
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'reviewed producer contract'):
                receipt({'repository': name, key: {'ok': True}})

    def test_evidence_archive_identifies_the_historical_source_rows(self):
        from superhunter.product_batches import verified_history
        self.assertEqual(len(verified_history()['receipts']), 38)

    def test_scorecard_preserves_links_as_boundaries_and_rejects_foreign_ones(self):
        from superhunter.product_scorecard import reviewable_entries
        rev = '1'*40
        raw = f'100644 blob {rev}\tLICENSE\x00160000 commit {rev}\tupstream/example\x00'.encode()
        self.assertEqual(reviewable_entries(raw, {'upstream/example': rev}), {'LICENSE': rev})
        with self.assertRaisesRegex(ValueError, 'unreviewed submodule'):
            reviewable_entries(raw, {'upstream/example': '2'*40})

    def test_refuted_match_retains_its_evidence_and_cannot_enter_search_results(self):
        from superhunter.product_notice_overlap import assess
        a = ' '.join(['one'] * 45)
        b = ' '.join(['two'] * 45)
        docs = {'a.txt': a.encode(), 'b.txt': b.encode(), 'c.txt': a.encode()}
        records = ('F\ta.txt\t45\nF\tb.txt\t45\nF\tc.txt\t45\nB\t45\n'
                   'R\ta.txt\t1\t1\t1\t180\nR\tb.txt\t1\t1\t1\t180\nB\t45\n'
                   'R\ta.txt\t1\t1\t1\t180\nR\tc.txt\t1\t1\t1\t180')
        summary, matches = assess(records, docs, record_refutations=True)
        self.assertEqual((summary['passages'], summary['locations']), (1, 2))
        self.assertEqual(len(summary['refuted_candidates']), 1)
        self.assertEqual(matches['b.txt'], [])
        with self.assertRaisesRegex(ValueError, 'identical token'):
            assess(records, docs)

    def test_extended_profile_rejects_an_unknown_option_and_missing_slots(self):
        from superhunter.tools.catalog_session import native_inputs
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'inputs.json'
            path.write_text('{"exec":"not-a-path"}')
            with self.assertRaisesRegex(ValueError, 'reviewed input slots'):
                native_inputs(path)

    def test_review_query_manifest_contains_every_id_once_and_explicit_audits(self):
        from superhunter.tools.catalog_session import review_queries
        queries = review_queries()
        self.assertEqual(len(queries), 218)
        self.assertEqual(len(set(q.casefold() for q in queries)), 218)
        self.assertTrue({'integration-matrix', 'recursive-source-trees', 'fork-headers'} <= set(queries[200:]))

    def test_transcript_archive_rejects_another_hash_size_or_trailing_stream(self):
        import base64
        import gzip
        from superhunter.tools.verify_review_115 import unpack
        original = b'own short offline test\n'
        zipped = gzip.compress(original, mtime=0)
        record = {'format': 'gzip-base64-jsonl-v1', 'raw_size': len(original),
                  'raw_sha256': hashlib.sha256(original).hexdigest(), 'gzip_base64': base64.b64encode(zipped).decode()}
        self.assertEqual(unpack(canonical(record)), original)
        for altered in ({'raw_size': 1}, {'raw_sha256': '1'*64},
                        {'gzip_base64': base64.b64encode(zipped + zipped).decode()}):
            with self.assertRaisesRegex(ValueError, 'archive content'):
                unpack(canonical({**record, **altered}))

    def test_truncated_and_untrusted_transcript_fail_before_receiving_credit(self):
        from superhunter.tools.verify_review_115 import verify
        with self.assertRaisesRegex(ValueError, 'missing or extra'):
            verify(b'{}\n')
        with self.assertRaisesRegex(ValueError, 'digest differs'):
            verify(b'{}\n', '0'*64)


class PortableSourceReviewTests(unittest.TestCase):
    def test_portable_inputs_reconstruct_all_47_commits_and_34_root_declarations(self):
        from superhunter.product_portable_roots import inputs
        rows, files = inputs()
        self.assertEqual(len({r['commit'] for r in rows}), 47)
        self.assertEqual(len(files), 34)

    def test_dangling_compressed_data_is_rejected(self):
        import base64
        import zlib
        from superhunter.product_portable_roots import inflate
        blob = zlib.compress(b'data')
        for invalid in (blob[:-2], blob + blob, zlib.compress(b'x' * 256_001)):
            with self.assertRaisesRegex(ValueError, 'compressed Git object'):
                inflate(base64.b64encode(invalid))

    def test_empty_go_report_or_wrong_diagnostic_location_cannot_pass(self):
        from superhunter.product_header_digest import assess
        report = {'Golang errors': {}, 'Stats': {'files': 0, 'nosec': 0, 'found': 0}, 'Issues': []}
        with self.assertRaisesRegex(ValueError, 'incomplete Go'):
            assess(report, {}, Path('/nqc'))
        report['Stats'].update(files=3, found=1)
        report['Issues'] = [{'file': '/nqc/changed/main.go', 'line': '54', 'column': '12'}]
        with self.assertRaisesRegex(ValueError, 'outside source'):
            assess(report, {'changed': b'own source'}, Path('/nqc'))

    def test_go_revision_on_its_own_cannot_receive_credit(self):
        with self.assertRaisesRegex(ValueError, 'accepted product result'):
            receipt({'repository': 'securego/gosec', 'go_source_receipt': {'revision': 'empty'}})
