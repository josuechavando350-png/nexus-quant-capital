from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import hashlib
import os
import subprocess
from subprocess import SubprocessError

from superhunter.product_sources import gitlinks
from superhunter.safe_io import strict_json, read_artifact
from superhunter.tools import verify_source_materialization as audit
from superhunter.tools import verify_staged_dependencies as staged


class StagedDependencyTests(TestCase):
    def test_published_batches_and_truncated_register(self):
        self.assertEqual(len(staged.batch_claims('report-interop')), 4)
        self.assertEqual(len(staged.batch_claims('evidence-contracts')), 17)
        with patch.object(staged, 'read_artifact', return_value=b'{"records":[]}'), self.assertRaisesRegex(
                ValueError, 'published receipt differs'):
            staged.batch_claims('evidence-contracts')

    def test_symlink_hash_uses_target_text_and_never_follows_parent_links(self):
        with TemporaryDirectory() as root:
            directory = Path(root)
            (directory / 'link').symlink_to('absent-file')
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                literal = b'absent-file'
                self.assertEqual(staged.working_blob(fd, b'link', b'120000'),
                                 (audit.git_object('blob', literal), hashlib.sha256(literal).hexdigest(), False))
                with self.assertRaises(OSError):
                    staged.working_blob(fd, b'link/file', b'100644')
            finally:
                os.close(fd)


class NestedArtifactTests(TestCase):
    def test_upstream_identity_normalizes_ssh_and_https_without_retaining_credentials(self):
        for url in ('git@github.com:foundry-rs/forge-std.git', 'https://github.com/foundry-rs/forge-std/'):
            self.assertEqual(audit.upstream_name(url), 'github.com/foundry-rs/forge-std')
        self.assertEqual(audit.upstream_name('https://gitlab.com/a/b/c.git'), 'gitlab.com/a/b/c')
        for bad in ('https://token@github.com/a/b', 'https://github.com/a/b?auth=a',
                    'file:///tmp/repo', 'git@github.com:a/../b', 'https://github.com/a//b'):
            with self.subTest(url=bad), self.assertRaisesRegex(ValueError, 'upstream'):
                audit.upstream_name(bad)

    def test_acquired_bytes_cannot_overwrite_or_alias_the_direct_sources(self):
        with TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            for workspace, staged in ((base, base), (base, base/'stage'), (base/'direct', base)):
                with self.subTest(workspace=workspace, staged=staged), \
                        self.assertRaisesRegex(ValueError, 'separate from the direct checkouts'):
                    audit.staged_assets(workspace, staged)

    def test_staged_payload_and_observation_are_both_bound_to_the_pinned_pointer(self):
        payload = b'owned LFS bytes'
        pointer = {'bytes': len(payload), 'oid': audit.sha(payload)}
        path = 'tests/e2e_tests/test_data/storage.tar.xz'
        row = {'repository': 'qdrant/qdrant', 'id': 159, 'tree': '1'*40, 'revision': '2'*40,
               'contents': {'lfs_pointers': {path: pointer}}}
        raw = audit.canonical({'entries': [row]})
        authority = {'catalog_id': 159, 'repository': row['repository'], 'tree': row['tree'],
                     'commit': row['revision'], 'path': 'qdrant'}
        def git(directory, command, *args):
            if command == 'cat-file':
                return audit.pointer_bytes(pointer)
            if len(args) == 2:
                return (row['revision'] + '\n' + row['tree'] + '\n').encode()
            return audit.git_object('blob', audit.pointer_bytes(pointer)).encode()
        with TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            direct, stage = base/'direct', base/'staged'
            (direct/'qdrant/.git').mkdir(parents=True)
            stage.mkdir()
            (base/'fixture.json').write_bytes(raw)
            with patch.object(audit, 'ROOT', base), patch.object(audit, 'SNAPSHOT', 'fixture.json'), \
                    patch.object(audit, 'SNAPSHOT_SHA', audit.sha(raw)), \
                    patch.object(audit, 'expected_rows', return_value=[authority]), \
                    patch.object(audit, 'local_git', side_effect=git):
                (stage/'qdrant-lfs-object').write_bytes(payload[::-1])
                with self.assertRaisesRegex(ValueError, 'LFS candidate differs'):
                    audit.staged_assets(direct, stage)
                (stage/'qdrant-lfs-object').write_bytes(payload)
                (stage/'qdrant-response.json').write_bytes(audit.canonical({'http_status': 200, 'url': 'untrusted'}))
                with self.assertRaisesRegex(ValueError, 'observation differs'):
                    audit.staged_assets(direct, stage)

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
