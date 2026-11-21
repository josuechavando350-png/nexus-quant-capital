from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import subprocess
from subprocess import SubprocessError

from superhunter.product_sources import gitlinks
from superhunter.safe_io import strict_json, read_artifact
from superhunter.tools import verify_source_materialization as audit


class NestedArtifactTests(TestCase):
    def test_distinguishes_a_commit_in_another_store_from_a_checkout_and_payload(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            parent, dependency = root/'parent', root/'dependency'
            def git(folder, *args):
                return subprocess.check_output(['/usr/bin/git', '-c', 'user.name=Local',
                                                '-c', 'user.email=local@example.invalid',
                                                '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null',
                                                '-C', str(folder), *args]).decode().strip()
            for path in (dependency, parent):
                path.mkdir()
                git(path, 'init', '-q')
            git(dependency, 'commit', '--allow-empty', '-qm', 'fixture')
            commit = git(dependency, 'rev-parse', 'HEAD')
            (parent/'dep').mkdir()
            payload = b'local data'
            pointer = {'bytes': len(payload), 'oid': audit.sha(payload)}
            (parent/'asset').write_bytes(audit.pointer_bytes(pointer))
            git(parent, 'add', 'asset')
            git(parent, 'update-index', '--add', '--cacheinfo', f'160000,{commit},dep')
            git(parent, 'commit', '-qm', 'pinned dependencies')
            authorities, entries = [], []
            for number, folder in enumerate((parent, dependency), 1):
                head, tree = git(folder, 'rev-parse', 'HEAD', 'HEAD^{tree}').splitlines()
                contents = {'nested_gitlinks': {'dep': commit} if number == 1 else {},
                            'lfs_pointers': {'asset': pointer} if number == 1 else {}}
                entries.append({'id': number, 'repository': folder.name, 'tree': tree, 'revision': head,
                                'contents': contents})
                authorities.append({'catalog_id': number, 'repository': folder.name,
                                    'commit': head, 'tree': tree, 'path': folder.name})
            raw = audit.canonical({'entries': entries})
            (root/'fixture.json').write_bytes(raw)
            with patch.object(audit, 'ROOT', root), patch.object(audit, 'SNAPSHOT', 'fixture.json'), \
                    patch.object(audit, 'SNAPSHOT_SHA', audit.sha(raw)), \
                    patch.object(audit, 'expected_rows', return_value=authorities):
                actual = audit.nested_artifacts(root)
                self.assertEqual(actual['checkout_states'], {'empty': 1})
                self.assertEqual(actual['commit_hits_in_direct_object_databases'], {commit: [2]})
                self.assertEqual(actual['lfs'][0]['worktree_state'], 'pointer_only')
                oid = pointer['oid']
                cache = dependency/'.git/lfs/objects'/oid[:2]/oid[2:4]/oid
                cache.parent.mkdir(parents=True)
                cache.write_bytes(payload)
                self.assertEqual(audit.nested_artifacts(root)['lfs'][0]['canonical_cache_hits_by_catalog_id'],
                                 {'2': 'verified_payload'})
                (parent/'asset').write_bytes(payload)
                self.assertEqual(audit.nested_artifacts(root)['lfs'][0]['worktree_state'], 'verified_payload')
                (parent/'asset').write_bytes(payload[::-1])
                with self.assertRaisesRegex(ValueError, 'LFS candidate differs'):
                    audit.nested_artifacts(root)

    def test_rejects_symlinked_assets_and_out_of_scope_git_directories(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as other:
            root = Path(directory).resolve()
            (root/'link').symlink_to(other)
            with self.assertRaisesRegex(ValueError, 'physical workspace'):
                audit.local_path(root, root/'link'/'asset')
            (root/'.git').write_text('gitdir: ' + other + '\n')
            with self.assertRaisesRegex(ValueError, 'physical workspace'):
                audit.git_directory(root, root)


class SourceMaterializationTests(TestCase):
    def setUp(self):
        self.product = gitlinks(audit.ROOT)
        self.records = audit.unpack_records()

    def test_published_receipt_reproduces_offline(self):
        observed = audit.verify(self.records, self.product)
        receipt = strict_json(read_artifact(audit.ROOT, 'superhunter/product_supply/source-materialization-review.json'))
        historical = observed['historical_record']
        self.assertEqual(historical, {k: receipt[k] for k in historical})
        self.assertEqual((observed['current_product_gitlinks'], observed['preserved_gitlinks'],
                          observed['added_gitlinks'], observed['new_functional_credits']), (200, 153, 47, 0))
        self.assertEqual(historical['product_gitlinks'], 153)
        self.assertEqual(observed['current_product_upstream_tree'], historical['separate_upstream_tree'])
        self.assertEqual(receipt['local_checkouts_observed'], 200)
        rows = [[x['catalog_id'], x['commit'], x['tree']] for x in audit.expected_rows()]
        self.assertEqual(audit.sha(audit.canonical(rows)), receipt['commit_tree_pairs_sha256'])

    def test_duplicate_subject_is_rejected(self):
        rows = self.records['all200-checkouts.json']['sources']
        rows[-1] = rows[0].copy()
        with self.assertRaisesRegex(ValueError, 'catalog rows'):
            audit.verify(self.records, self.product)

    def test_missing_or_changed_current_product_gitlink_is_rejected(self):
        path = self.records['summary.json'][0]['path']
        for value in (None, '7' * 40):
            links = self.product.copy()
            if value is None:
                del links[path]
            else:
                links[path] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'current product gitlinks'):
                audit.verify(self.records, links)

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
